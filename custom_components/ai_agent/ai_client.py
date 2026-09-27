"""Universal AI Client with Smart Reasoning Fallback and Transparent Reporting."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import aiohttp

from .const import (
    FALLBACK_ORDER,
    PROVIDER_ANTHROPIC,
    PROVIDER_CUSTOM,
    PROVIDER_DEEPSEEK,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    THINKING_HIGH,
    THINKING_LEVEL_NAMES,
    THINKING_LOW,
    THINKING_MAX,
    THINKING_MEDIUM,
    THINKING_OFF,
    THINKING_XHIGH,
)

_LOGGER = logging.getLogger(__name__)

# Token budgets for providers that use numeric token counts (Anthropic, Gemini)
THINKING_BUDGET_MAP = {
    THINKING_OFF: 0,
    THINKING_LOW: 2048,
    THINKING_MEDIUM: 8192,
    THINKING_HIGH: 16384,
    THINKING_XHIGH: 32768,
    THINKING_MAX: 65536,
}


class AIClient:
    """Universal AI Client with multi-provider and reasoning fallback support."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        thinking_level: str = THINKING_HIGH,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self.provider = provider
        self.model = model.strip()
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.requested_thinking_level = thinking_level
        self._session = session
        self._external_session = session is not None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if not self._external_session and self._session and not self._session.closed:
            await self._session.close()

    def get_supported_thinking_levels(self) -> List[str]:
        """Return list of supported thinking levels for current provider/model."""
        model_lower = self.model.lower()

        # OpenAI
        if self.provider == PROVIDER_OPENAI:
            if any(k in model_lower for k in ["o1", "o3", "astra", "gpt-6"]):
                return [THINKING_OFF, THINKING_LOW, THINKING_MEDIUM, THINKING_HIGH, THINKING_XHIGH, THINKING_MAX]
            # Standard GPT-4o / GPT-4o-mini don't have reasoning_effort
            return [THINKING_OFF]

        # Anthropic Claude
        if self.provider == PROVIDER_ANTHROPIC:
            if "3-7" in model_lower or "claude-4" in model_lower:
                return [THINKING_OFF, THINKING_LOW, THINKING_MEDIUM, THINKING_HIGH, THINKING_XHIGH, THINKING_MAX]
            return [THINKING_OFF]

        # DeepSeek
        if self.provider == PROVIDER_DEEPSEEK:
            if "reasoner" in model_lower or "r1" in model_lower:
                return [THINKING_LOW, THINKING_MEDIUM, THINKING_HIGH, THINKING_XHIGH, THINKING_MAX]
            return [THINKING_OFF]

        # Google Gemini
        if self.provider == PROVIDER_GEMINI:
            if "2.5" in model_lower or "3." in model_lower or "thinking" in model_lower:
                return [THINKING_OFF, THINKING_LOW, THINKING_MEDIUM, THINKING_HIGH, THINKING_XHIGH, THINKING_MAX]
            return [THINKING_OFF]

        # OpenRouter / Custom: Assume flexible
        return [THINKING_OFF, THINKING_LOW, THINKING_MEDIUM, THINKING_HIGH, THINKING_XHIGH, THINKING_MAX]

    def resolve_thinking_level(self, requested: str) -> Tuple[str, Optional[str]]:
        """Resolve requested thinking level with graceful cascade and user notification."""
        supported = self.get_supported_thinking_levels()

        if requested in supported:
            return requested, None

        # Cascade down until finding a supported level
        current_index = FALLBACK_ORDER.index(requested) if requested in FALLBACK_ORDER else 0
        for level in FALLBACK_ORDER[current_index:]:
            if level in supported:
                req_name = THINKING_LEVEL_NAMES.get(requested, requested)
                act_name = THINKING_LEVEL_NAMES.get(level, level)
                notice = (
                    f"ℹ️ **התאמת רמת חשיבה:** המודל `{self.model}` אינו תומך ברמת חשיבה '{req_name}'. "
                    f"המערכת התאימה אוטומטית לרמה הנתמכת הגבוהה ביותר: **{act_name}**."
                )
                return level, notice

        fallback = THINKING_OFF
        req_name = THINKING_LEVEL_NAMES.get(requested, requested)
        notice = (
            f"ℹ️ **התאמת רמת חשיבה:** המודל `{self.model}` אינו תומך במנגנון חשיבה מורחב. "
            f"הופעל במצב ישיר (כבוי)."
        )
        return fallback, notice

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send chat request with automatic fallback on API error."""
        resolved_level, fallback_notice = self.resolve_thinking_level(self.requested_thinking_level)

        # Attempt call with resolved level, if provider rejects it at runtime, cascade further down
        trial_levels = [resolved_level]
        if resolved_level in FALLBACK_ORDER:
            idx = FALLBACK_ORDER.index(resolved_level)
            trial_levels.extend(FALLBACK_ORDER[idx + 1:])

        last_error = None
        for level in trial_levels:
            try:
                result = await self._execute_chat(messages, system_prompt, tools, thinking_level=level)
                # If we had to drop down further at runtime
                if level != resolved_level:
                    req_name = THINKING_LEVEL_NAMES.get(self.requested_thinking_level, self.requested_thinking_level)
                    act_name = THINKING_LEVEL_NAMES.get(level, level)
                    fallback_notice = (
                        f"ℹ️ **התאמת רמת חשיבה בזמן ריצה:** המודל `{self.model}` דיווח על אי-תמיכה ברמה זו. "
                        f"בוצעה ירידה אוטומטית לרמת **{act_name}**."
                    )
                result["fallback_notice"] = fallback_notice
                result["actual_thinking_level"] = level
                return result
            except aiohttp.ClientResponseError as err:
                last_error = err
                # If error is related to unsupported reasoning_effort or parameter, continue fallback
                if err.status == 400 and ("reasoning" in str(err).lower() or "thinking" in str(err).lower()):
                    _LOGGER.warning("Thinking level '%s' rejected by API for model '%s', falling back", level, self.model)
                    continue
                raise
            except Exception as err:
                last_error = err
                # Check message text for reasoning error
                if "reasoning" in str(err).lower() or "thinking" in str(err).lower():
                    _LOGGER.warning("Thinking level '%s' error for model '%s': %s, falling back", level, self.model, err)
                    continue
                raise

        _LOGGER.error("All thinking level fallbacks failed: %s", last_error)
        return {
            "content": f"⚠️ לא ניתן היה לקבל מענה מהמודל `{self.model}`: {last_error}",
            "tool_calls": [],
            "raw": {},
        }

    async def _execute_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
    ) -> Dict[str, Any]:
        """Internal dispatch to appropriate provider API."""
        if self.provider == PROVIDER_ANTHROPIC:
            return await self._call_anthropic(messages, system_prompt, tools, thinking_level)
        if self.provider == PROVIDER_GEMINI and not self.base_url.endswith("/v1"):
            return await self._call_gemini_native(messages, system_prompt, tools, thinking_level)
        # Default OpenAI-compatible endpoint (OpenAI, DeepSeek, OpenRouter, Custom, or Gemini OpenAI compatibility)
        return await self._call_openai_compatible(messages, system_prompt, tools, thinking_level)

    async def _call_openai_compatible(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
    ) -> Dict[str, Any]:
        """Call standard OpenAI compatible endpoint."""
        session = await self._get_session()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
        }

        # Reasoning effort for OpenAI/OpenRouter
        if thinking_level != THINKING_OFF:
            payload["reasoning_effort"] = thinking_level
        else:
            payload["reasoning_effort"] = "none"

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
            if resp.status >= 400:
                err_text = await resp.text()

                # If model requires reasoning_effort: 'none' when function tools are used
                if "reasoning_effort" in err_text and ("'none'" in err_text or "not supported" in err_text):
                    _LOGGER.info("OpenAI API requires reasoning_effort='none' with function tools. Retrying with 'none'.")
                    payload["reasoning_effort"] = "none"
                    async with session.post(url, headers=headers, json=payload, timeout=90) as retry_resp:
                        if retry_resp.status < 400:
                            data = await retry_resp.json()
                            choice = data["choices"][0]["message"]
                            return {
                                "content": choice.get("content") or "",
                                "tool_calls": choice.get("tool_calls") or [],
                                "raw": data,
                                "fallback_notice": f"ℹ️ המודל `{self.model}` מחייב כיבוי reasoning ('none') בעת שימוש בכלים ב-API זה. בוצעה התאמה אוטומטית.",
                            }
                        err_text = await retry_resp.text()

                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"API Error ({resp.status}): {err_text}",
                )
            data = await resp.json()

        choice = data["choices"][0]["message"]
        return {
            "content": choice.get("content") or "",
            "tool_calls": choice.get("tool_calls") or [],
            "raw": data,
        }

    async def _call_anthropic(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
    ) -> Dict[str, Any]:
        """Call Anthropic Claude API."""
        session = await self._get_session()
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
        }

        if system_prompt:
            payload["system"] = system_prompt

        # Extended Thinking for Claude
        if thinking_level != THINKING_OFF:
            budget = THINKING_BUDGET_MAP.get(thinking_level, 2048)
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
            payload["max_tokens"] = max(budget + 2048, 4096)

        if tools:
            anthropic_tools = []
            for t in tools:
                func = t.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description"),
                    "input_schema": func.get("parameters"),
                })
            payload["tools"] = anthropic_tools

        async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
            if resp.status >= 400:
                err_text = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"Anthropic API Error ({resp.status}): {err_text}",
                )
            data = await resp.json()

        content_blocks = data.get("content", [])
        text_content = ""
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        return {
            "content": text_content,
            "tool_calls": tool_calls,
            "raw": data,
        }

    async def _call_gemini_native(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
    ) -> Dict[str, Any]:
        """Call Google Gemini REST API."""
        session = await self._get_session()
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}],
            })

        payload: Dict[str, Any] = {"contents": contents}

        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        # Thinking config for Gemini
        if thinking_level != THINKING_OFF:
            budget = THINKING_BUDGET_MAP.get(thinking_level, 2048)
            payload["generationConfig"] = {
                "thinkingConfig": {"thinkingBudget": budget}
            }

        async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
            if resp.status >= 400:
                err_text = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"Gemini API Error ({resp.status}): {err_text}",
                )
            data = await resp.json()

        candidates = data.get("candidates", [])
        text = ""
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            for p in parts:
                text += p.get("text", "")

        return {
            "content": text,
            "tool_calls": [],
            "raw": data,
        }
