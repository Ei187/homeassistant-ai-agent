"""Universal AI Client with Smart Reasoning Fallback and Transparent Reporting."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
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
            connector = aiohttp.TCPConnector(keepalive_timeout=75, enable_cleanup_closed=True)
            self._session = aiohttp.ClientSession(connector=connector)
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
        override_thinking_level: Optional[str] = None,
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Send chat request with automatic fallback on API error."""
        target_level = override_thinking_level or self.requested_thinking_level
        resolved_level, fallback_notice = self.resolve_thinking_level(target_level)

        # Attempt call with resolved level, if provider rejects it at runtime, cascade further down
        trial_levels = [resolved_level]
        if resolved_level in FALLBACK_ORDER:
            idx = FALLBACK_ORDER.index(resolved_level)
            trial_levels.extend(FALLBACK_ORDER[idx + 1:])

        last_error = None
        for level in trial_levels:
            try:
                result = await self._execute_chat(messages, system_prompt, tools, thinking_level=level, on_chunk=on_chunk)
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
                err_text = f"{err} {getattr(err, 'message', '')}".lower()
                # If error is related to unsupported reasoning_effort or parameter, continue fallback
                if err.status == 400 and ("reasoning" in err_text or "thinking" in err_text or "effort" in err_text):
                    _LOGGER.warning("Thinking level '%s' rejected by API for model '%s', falling back", level, self.model)
                    continue
                raise
            except Exception as err:
                last_error = err
                err_text = str(err).lower()
                # Check message text for reasoning error
                if "reasoning" in err_text or "thinking" in err_text or "effort" in err_text:
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
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Internal dispatch to appropriate provider API."""
        if self.provider == PROVIDER_ANTHROPIC:
            return await self._call_anthropic(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk)
        if self.provider == PROVIDER_GEMINI and not self.base_url.endswith("/v1"):
            return await self._call_gemini_native(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk)
        # Default OpenAI-compatible endpoint (OpenAI, DeepSeek, OpenRouter, Custom, or Gemini OpenAI compatibility)
        if self.provider == PROVIDER_OPENAI and "api.openai.com" in self.base_url:
            # If fast response or streaming requested, prefer standard /v1/chat/completions with SSE
            if on_chunk is not None or thinking_level == THINKING_OFF:
                try:
                    return await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk)
                except Exception as err:
                    _LOGGER.warning("OpenAI streaming chat/completions failed (%s). Falling back to responses API.", err)
            try:
                return await self._call_openai_responses(messages, system_prompt, tools, thinking_level)
            except Exception as err:
                _LOGGER.warning("OpenAI Responses API failed (%s). Falling back to /v1/chat/completions.", err)
                return await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk)
        return await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk)

    async def _call_openai_responses(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
    ) -> Dict[str, Any]:
        """Call OpenAI /v1/responses (supports function tools + reasoning together)."""
        session = await self._get_session()
        url = f"{self.base_url}/responses"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        def _text(content: Any) -> str:
            if content is None:
                return ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            return str(content)

        input_items: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            if role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": m.get("tool_call_id") or "",
                    "output": _text(m.get("content")),
                })
                continue
            if role == "assistant" and m.get("tool_calls"):
                txt = _text(m.get("content"))
                if txt:
                    input_items.append({"role": "assistant", "content": txt})
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments") or "{}"
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    input_items.append({
                        "type": "function_call",
                        "call_id": tc.get("id") or "",
                        "name": fn.get("name") or "",
                        "arguments": args,
                    })
                continue
            if role == "system":
                role = "developer"
            if role not in ("user", "assistant", "developer"):
                role = "user"
            input_items.append({"role": role, "content": _text(m.get("content"))})

        payload: Dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "store": False,
        }
        if system_prompt:
            payload["instructions"] = system_prompt

        has_fc_items = any(i.get("type") == "function_call" for i in input_items)
        if tools:
            self._last_tools = tools
        elif has_fc_items and getattr(self, "_last_tools", None):
            tools = self._last_tools

        if tools:
            resp_tools = []
            for t in tools:
                fn = t.get("function", t)
                resp_tools.append({
                    "type": "function",
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = resp_tools
            payload["tool_choice"] = "auto" if self._last_tools is not tools or not has_fc_items else "none"

        if thinking_level and thinking_level != THINKING_OFF:
            eff = thinking_level.lower()
            if eff == THINKING_MAX:
                eff = "xhigh"
            if eff in ("low", "medium", "high", "xhigh"):
                payload["reasoning"] = {"effort": eff}

        data = None
        err_text = ""
        status = 0
        req_info = None
        history: Any = ()
        tried_effort: set = {(payload.get("reasoning") or {}).get("effort")}
        for _attempt in range(4):
            async with session.post(url, headers=headers, json=payload, timeout=180) as resp:
                if resp.status < 400:
                    data = await resp.json()
                    break
                err_text = await resp.text()
                status = resp.status
                req_info, history = resp.request_info, resp.history
            low = err_text.lower()
            if "reasoning" not in low and "effort" not in low:
                break
            # Adjust reasoning effort based on API feedback
            next_eff: Any = None
            if "xhigh" in tried_effort and "high" not in tried_effort:
                next_eff = "high"
            elif None not in tried_effort:
                next_eff = None
            elif "low" not in tried_effort:
                next_eff = "low"
            else:
                break
            tried_effort.add(next_eff)
            if next_eff is None:
                payload.pop("reasoning", None)
            else:
                payload["reasoning"] = {"effort": next_eff}
            _LOGGER.info("Responses API: retrying model '%s' with reasoning effort=%s", self.model, next_eff)

        if data is None:
            raise aiohttp.ClientResponseError(
                req_info,
                history,
                status=status or 400,
                message=f"API Error ({status}): {err_text}",
            )

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for item in data.get("output", []) or []:
            itype = item.get("type")
            if itype == "message":
                for c in item.get("content", []) or []:
                    if c.get("type") in ("output_text", "text"):
                        content_parts.append(c.get("text", ""))
            elif itype == "function_call":
                tool_calls.append({
                    "id": item.get("call_id") or item.get("id"),
                    "type": "function",
                    "function": {
                        "name": item.get("name"),
                        "arguments": item.get("arguments") or "{}",
                    },
                })
        content = "".join(content_parts) or data.get("output_text") or ""
        return {"content": content, "tool_calls": tool_calls, "raw": data}

    async def _call_openai_compatible(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
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

        # Reasoning effort for OpenAI / OpenRouter
        # Valid values for OpenAI: 'low', 'medium', 'high', 'xhigh'
        # Never send 'none' or 'off'; simply omit reasoning_effort if off
        if thinking_level and thinking_level != THINKING_OFF:
            eff = thinking_level.lower()
            if eff == THINKING_MAX:
                eff = THINKING_HIGH
            if eff in ("low", "medium", "high", "xhigh"):
                payload["reasoning_effort"] = eff

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if on_chunk is not None:
            payload["stream"] = True

        # Adaptive retry: read the API error and adjust reasoning_effort accordingly.
        tried: set = {payload.get("reasoning_effort")}
        data = None
        err_text = ""
        last_status = 0
        last_resp_info = None
        for _attempt in range(5):
            async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
                if resp.status < 400:
                    if payload.get("stream"):
                        accumulated_text: List[str] = []
                        tool_calls_dict: Dict[int, Dict[str, Any]] = {}
                        async for raw_line in resp.content:
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except Exception:
                                continue
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            text_piece = delta.get("content")
                            if text_piece:
                                accumulated_text.append(text_piece)
                                if on_chunk:
                                    await on_chunk(text_piece)
                            tc_deltas = delta.get("tool_calls") or []
                            for tc in tc_deltas:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_dict:
                                    tool_calls_dict[idx] = {
                                        "id": tc.get("id") or f"call_{idx}_{uuid.uuid4().hex[:6]}",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                if tc.get("id"):
                                    tool_calls_dict[idx]["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    tool_calls_dict[idx]["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    tool_calls_dict[idx]["function"]["arguments"] += fn["arguments"]

                        final_tc = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]
                        content = "".join(accumulated_text)
                        return {
                            "content": content,
                            "tool_calls": final_tc,
                            "raw": {},
                        }
                    else:
                        data = await resp.json()
                        break

                err_text = await resp.text()
                last_status = resp.status
                last_resp_info = (resp.request_info, resp.history)

            low = err_text.lower()
            if "/v1/responses" in low:
                _LOGGER.info("API advised using /v1/responses endpoint. Redirecting to _call_openai_responses.")
                return await self._call_openai_responses(messages, system_prompt, tools, thinking_level)
            if "reasoning_effort" not in low:
                break

            next_effort: Any = "__stop__"
            if "'none'" in low and ("set reasoning_effort" in low or "to use function tools" in low):
                next_effort = "none"
            elif "does not support 'none'" in low or "supported values" in low:
                next_effort = "low"
            elif "unsupported parameter" in low or "not recognized" in low or "extra" in low:
                next_effort = None

            # Fallback ladder if the message didn't match a known pattern
            if next_effort == "__stop__" or next_effort in tried:
                for cand in ("none", None, "low"):
                    if cand not in tried:
                        next_effort = cand
                        break
                else:
                    break

            tried.add(next_effort)
            _LOGGER.info("Model '%s': retrying with reasoning_effort=%s", self.model, next_effort)
            if next_effort is None:
                payload.pop("reasoning_effort", None)
            else:
                payload["reasoning_effort"] = next_effort

        if data is None:
            info, hist = last_resp_info if last_resp_info else (None, ())
            raise aiohttp.ClientResponseError(
                info,
                hist,
                status=last_status or 400,
                message=f"API Error ({last_status}): {err_text}",
            )

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
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
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

        if on_chunk is not None:
            payload["stream"] = True

        async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
            if resp.status >= 400:
                err_text = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"Anthropic API Error ({resp.status}): {err_text}",
                )
            if payload.get("stream"):
                accumulated_text: List[str] = []
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue
                    ctype = chunk.get("type")
                    if ctype == "content_block_delta":
                        delta = chunk.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            t = delta.get("text")
                            if t:
                                accumulated_text.append(t)
                                if on_chunk:
                                    await on_chunk(t)
                return {"content": "".join(accumulated_text), "tool_calls": [], "raw": {}}

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
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Call Google Gemini REST API."""
        session = await self._get_session()
        method_name = "streamGenerateContent?alt=sse&key=" if on_chunk else "generateContent?key="
        url = f"{self.base_url}/v1beta/models/{self.model}:{method_name}{self.api_key}"
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
            if on_chunk:
                accumulated_text: List[str] = []
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue
                    candidates = chunk.get("candidates") or []
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts") or []
                        for p in parts:
                            t = p.get("text")
                            if t:
                                accumulated_text.append(t)
                                if on_chunk:
                                    await on_chunk(t)
                return {
                    "content": "".join(accumulated_text),
                    "tool_calls": [],
                    "raw": {},
                }

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
