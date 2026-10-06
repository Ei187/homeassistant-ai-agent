"""Universal AI Client with Smart Reasoning Fallback and Transparent Reporting."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import aiohttp

from .const import (
    FALLBACK_ORDER,
    PROVIDER_ANTHROPIC,
    PROVIDER_CUSTOM,
    PROVIDER_DEEPSEEK,
    PROVIDER_GEMINI,
    PROVIDER_GROQ,
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
        self.model = model.strip() if model else ""
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.requested_thinking_level = thinking_level
        self._session = session
        self._external_session = session is not None
        self._resolved_model_cache: Optional[str] = None
        self._resolved_model_timestamp: float = 0.0
        self._resolve_lock: Optional[asyncio.Lock] = None

    def _get_resolve_lock(self) -> asyncio.Lock:
        if self._resolve_lock is None:
            self._resolve_lock = asyncio.Lock()
        return self._resolve_lock

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(keepalive_timeout=75, enable_cleanup_closed=True)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self) -> None:
        if not self._external_session and self._session and not self._session.closed:
            await self._session.close()

    def is_auto_model(self, model_name: Optional[str] = None) -> bool:
        """Check if model is set to auto-latest."""
        target = model_name if model_name is not None else self.model
        if not target:
            return True
        target_str = str(target).strip().lower()
        return not target_str or target_str in ("auto-latest", "auto", "default")

    async def resolve_active_model(self, model_name: Optional[str] = None) -> str:
        """Resolve active model dynamically if auto-latest is requested, cached for 3 hours."""
        if not self.is_auto_model(model_name):
            return (model_name if model_name is not None else self.model).strip()

        now = time.time()
        # 3 hours TTL cache (10800 seconds)
        if self._resolved_model_cache and (now - self._resolved_model_timestamp) < (3 * 3600):
            return self._resolved_model_cache

        async with self._get_resolve_lock():
            now = time.time()
            if self._resolved_model_cache and (now - self._resolved_model_timestamp) < (3 * 3600):
                return self._resolved_model_cache

            resolved = await self._discover_latest_model()
            self._resolved_model_cache = resolved
            self._resolved_model_timestamp = now
            _LOGGER.info("Resolved auto-latest model for provider '%s': %s", self.provider, resolved)
            return resolved

    async def _discover_latest_model(self) -> str:
        """Discover the latest available model for the active provider."""
        # 1. Google Gemini
        if self.provider == PROVIDER_GEMINI:
            fallback = "gemini-2.5-flash"
            if not self.api_key:
                return fallback
            try:
                session = await self._get_session()
                base = (self.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
                if base.endswith("/v1beta") or base.endswith("/v1"):
                    base = base.rsplit("/", 1)[0]
                url = f"{base}/v1beta/models?key={self.api_key}"
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models", [])
                        flash_candidates: List[str] = []
                        for m in models:
                            m_name = m.get("name", "").replace("models/", "")
                            methods = m.get("supportedGenerationMethods", [])
                            if "generateContent" in methods and "flash" in m_name.lower():
                                low = m_name.lower()
                                if any(x in low for x in ("embedding", "aqa", "realtime", "imagen", "robotics")):
                                    continue
                                flash_candidates.append(m_name)

                        if flash_candidates:
                            def _gemini_version_key(name: str) -> Tuple[float, int, int]:
                                low = name.lower()
                                matches = re.findall(r"(\d+(?:\.\d+)?)", name)
                                nums = [float(x) for x in matches] if matches else [0.0]
                                ver = nums[0] if nums else 0.0
                                is_preview = 0 if ("preview" in low or "exp" in low) else 1
                                is_not_lite = 0 if ("lite" in low or "8b" in low) else 1
                                return (ver, is_not_lite, is_preview)

                            flash_candidates.sort(key=_gemini_version_key, reverse=True)
                            return flash_candidates[0]
            except Exception as err:
                _LOGGER.warning("Failed to discover latest Gemini model (%s), using fallback %s", err, fallback)
            return fallback

        # 2. OpenRouter
        if self.provider == PROVIDER_OPENROUTER:
            fallback = "openrouter/auto"
            try:
                session = await self._get_session()
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                url = "https://openrouter.ai/api/v1/models"
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_models = data.get("data", [])
                        free_models = [m for m in raw_models if str(m.get("id", "")).endswith(":free")]
                        if free_models:
                            def _openrouter_score(m: Dict[str, Any]) -> Tuple[int, int]:
                                mid = str(m.get("id", "")).lower()
                                score = 0
                                if "gemini" in mid:
                                    score += 100
                                    if "2.5" in mid:
                                        score += 50
                                    elif "2.0" in mid:
                                        score += 40
                                elif "google/" in mid or "gemma" in mid:
                                    score += 90
                                elif "llama" in mid:
                                    score += 80
                                elif "deepseek" in mid:
                                    score += 70
                                elif "qwen" in mid:
                                    score += 60
                                created = int(m.get("created", 0) or 0)
                                return (score, created)

                            free_models.sort(key=_openrouter_score, reverse=True)
                            return str(free_models[0]["id"])
            except Exception as err:
                _LOGGER.warning("Failed to discover OpenRouter free model (%s), using fallback %s", err, fallback)
            return fallback

        # 3. OpenAI
        if self.provider == PROVIDER_OPENAI:
            return "gpt-4o-mini"

        # 4. Anthropic Claude
        if self.provider == PROVIDER_ANTHROPIC:
            return "claude-3-7-sonnet-latest"

        # 5. DeepSeek
        if self.provider == PROVIDER_DEEPSEEK:
            return "deepseek-chat"

        # 6. Groq
        if self.provider == PROVIDER_GROQ:
            fallback = "llama-3.1-8b-instant"
            try:
                session = await self._get_session()
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                url = "https://api.groq.com/openai/v1/models"
                async with session.get(url, headers=headers, timeout=8) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_models = data.get("data", [])
                        chat_models = [
                            m for m in raw_models
                            if m.get("active", True) is not False
                            and not any(x in str(m.get("id", "")).lower() for x in ("whisper", "guard", "embed", "safetensor", "vision"))
                        ]
                        if chat_models:
                            def _groq_score(m: Dict[str, Any]) -> Tuple[int, int]:
                                mid = str(m.get("id", "")).lower()
                                score = 0
                                if "llama-3.3" in mid:
                                    score += 100
                                elif "llama-3.1" in mid:
                                    score += 90
                                elif "qwen" in mid:
                                    score += 85
                                elif "deepseek" in mid:
                                    score += 80
                                elif "gpt-oss" in mid:
                                    score += 75
                                elif "llama" in mid:
                                    score += 65
                                elif "mixtral" in mid:
                                    score += 50
                                elif "gemma" in mid:
                                    score += 40

                                if "70b" in mid:
                                    score += 15
                                elif "8b" in mid:
                                    score += 20  # Fast and guaranteed quota on free accounts

                                created = int(m.get("created", 0) or 0)
                                return (score, created)

                            chat_models.sort(key=_groq_score, reverse=True)
                            chosen = str(chat_models[0]["id"])
                            _LOGGER.info("Dynamically discovered active Groq model: %s", chosen)
                            return chosen
            except Exception as err:
                _LOGGER.warning("Failed to discover Groq model (%s), using fallback %s", err, fallback)
            return fallback

        # 7. Custom / Local
        if self.provider == PROVIDER_CUSTOM:
            fallback = "llama3.3"
            try:
                session = await self._get_session()
                url = f"{self.base_url}/models"
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                async with session.get(url, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list):
                            models = data
                        elif isinstance(data, dict):
                            models = data.get("data") or data.get("models") or []
                        else:
                            models = []

                        if models and isinstance(models, list):
                            first = models[0]
                            if isinstance(first, dict):
                                return str(first.get("id") or first.get("name") or fallback)
                            if isinstance(first, str):
                                return first
            except Exception as err:
                _LOGGER.debug("Custom endpoint models query failed (%s), using fallback %s", err, fallback)
            return fallback

        return self.model or "gpt-4o-mini"

    def get_supported_thinking_levels(self, model_name: Optional[str] = None) -> List[str]:
        """Return list of supported thinking levels for current provider/model."""
        target_model = model_name or self._resolved_model_cache or self.model
        if self.is_auto_model(target_model):
            default_map = {
                PROVIDER_GEMINI: "gemini-2.5-flash",
                PROVIDER_ANTHROPIC: "claude-3-7-sonnet-latest",
                PROVIDER_OPENAI: "chatgpt-4o-latest",
                PROVIDER_DEEPSEEK: "deepseek-chat",
                PROVIDER_OPENROUTER: "openrouter/auto",
                PROVIDER_CUSTOM: "llama3.3",
            }
            target_model = default_map.get(self.provider, "gpt-4o-mini")
        model_lower = target_model.lower()

        # OpenAI
        if self.provider == PROVIDER_OPENAI:
            if any(k in model_lower for k in ["o1", "o3", "astra", "gpt-6"]):
                return [THINKING_OFF, THINKING_LOW, THINKING_MEDIUM, THINKING_HIGH, THINKING_XHIGH, THINKING_MAX]
            # Standard GPT-4o / GPT-4o-mini / chatgpt-4o-latest don't have reasoning_effort
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

    def resolve_thinking_level(self, requested: str, model_name: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Resolve requested thinking level with graceful cascade and user notification."""
        target_model = model_name or self._resolved_model_cache or self.model
        supported = self.get_supported_thinking_levels(target_model)

        if requested in supported:
            return requested, None

        # Cascade down until finding a supported level
        current_index = FALLBACK_ORDER.index(requested) if requested in FALLBACK_ORDER else 0
        for level in FALLBACK_ORDER[current_index:]:
            if level in supported:
                req_name = THINKING_LEVEL_NAMES.get(requested, requested)
                act_name = THINKING_LEVEL_NAMES.get(level, level)
                notice = (
                    f"ℹ️ **התאמת רמת חשיבה:** המודל `{target_model}` אינו תומך ברמת חשיבה '{req_name}'. "
                    f"המערכת התאימה אוטומטית לרמה הנתמכת הגבוהה ביותר: **{act_name}**."
                )
                return level, notice

        fallback = THINKING_OFF
        req_name = THINKING_LEVEL_NAMES.get(requested, requested)
        notice = (
            f"ℹ️ **התאמת רמת חשיבה:** המודל `{target_model}` אינו תומך במנגנון חשיבה מורחב. "
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
        active_model = await self.resolve_active_model()
        target_level = override_thinking_level or self.requested_thinking_level
        resolved_level, fallback_notice = self.resolve_thinking_level(target_level, model_name=active_model)

        # Attempt call with resolved level, if provider rejects it at runtime, cascade further down
        trial_levels = [resolved_level]
        if resolved_level in FALLBACK_ORDER:
            idx = FALLBACK_ORDER.index(resolved_level)
            trial_levels.extend(FALLBACK_ORDER[idx + 1:])

        last_error = None
        for level in trial_levels:
            try:
                result = await self._execute_chat(
                    messages, system_prompt, tools, thinking_level=level, on_chunk=on_chunk, active_model=active_model
                )
                # If we had to drop down further at runtime
                if level != resolved_level:
                    req_name = THINKING_LEVEL_NAMES.get(self.requested_thinking_level, self.requested_thinking_level)
                    act_name = THINKING_LEVEL_NAMES.get(level, level)
                    fallback_notice = (
                        f"ℹ️ **התאמת רמת חשיבה בזמן ריצה:** המודל `{active_model}` דיווח על אי-תמיכה ברמה זו. "
                        f"בוצעה ירידה אוטומטית לרמת **{act_name}**."
                    )
                result["fallback_notice"] = fallback_notice
                result["actual_thinking_level"] = level
                result["actual_model"] = result.get("actual_model") or active_model
                return result
            except aiohttp.ClientResponseError as err:
                last_error = err
                err_text = f"{err} {getattr(err, 'message', '')}".lower()
                # If error is related to unsupported reasoning_effort or parameter, continue fallback
                if err.status == 400 and ("reasoning" in err_text or "thinking" in err_text or "effort" in err_text):
                    _LOGGER.warning("Thinking level '%s' rejected by API for model '%s', falling back", level, active_model)
                    continue
                raise
            except Exception as err:
                last_error = err
                err_text = str(err).lower()
                # Check message text for reasoning error
                if "reasoning" in err_text or "thinking" in err_text or "effort" in err_text:
                    _LOGGER.warning("Thinking level '%s' error for model '%s': %s, falling back", level, active_model, err)
                    continue
                raise

        _LOGGER.error("All thinking level fallbacks failed: %s", last_error)
        return {
            "content": f"⚠️ לא ניתן היה לקבל מענה מהמודל `{active_model}`: {last_error}",
            "tool_calls": [],
            "raw": {},
            "actual_model": active_model,
        }

    async def _execute_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
        active_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Internal dispatch to appropriate provider API."""
        target_model = active_model or await self.resolve_active_model()
        if self.provider == PROVIDER_ANTHROPIC:
            res = await self._call_anthropic(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)
        elif self.provider == PROVIDER_GEMINI and not self.base_url.endswith("/v1"):
            res = await self._call_gemini_native(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)
        # Default OpenAI-compatible endpoint (OpenAI, DeepSeek, OpenRouter, Custom, or Gemini OpenAI compatibility)
        elif self.provider == PROVIDER_OPENAI and "api.openai.com" in self.base_url:
            # If fast response or streaming requested, prefer standard /v1/chat/completions with SSE
            if on_chunk is not None or thinking_level == THINKING_OFF:
                try:
                    res = await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)
                except Exception as err:
                    _LOGGER.warning("OpenAI streaming chat/completions failed (%s). Falling back to responses API.", err)
                    res = None
            else:
                res = None

            if res is None:
                try:
                    res = await self._call_openai_responses(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)
                except Exception as err:
                    _LOGGER.warning("OpenAI Responses API failed (%s). Falling back to /v1/chat/completions.", err)
                    res = await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)
        else:
            res = await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)

        res["actual_model"] = target_model
        return res

    async def _call_openai_responses(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        thinking_level: str,
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call OpenAI /v1/responses (supports function tools + reasoning together)."""
        session = await self._get_session()
        target_model = model_name or self.model
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
            "model": target_model,
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

        if on_chunk is not None:
            payload["stream"] = True

        data = None
        err_text = ""
        status = 0
        req_info = None
        history: Any = ()
        tried_effort: set = {(payload.get("reasoning") or {}).get("effort")}
        for _attempt in range(4):
            async with session.post(url, headers=headers, json=payload, timeout=180) as resp:
                if resp.status < 400:
                    if payload.get("stream"):
                        accumulated_parts: List[str] = []
                        tool_calls_dict: Dict[str, Dict[str, Any]] = {}
                        current_call_id: Optional[str] = None
                        async for raw_line in resp.content:
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                event = json.loads(data_str)
                            except Exception:
                                continue
                            etype = event.get("type", "")
                            if "delta" in etype:
                                text_delta = event.get("delta")
                                if isinstance(text_delta, str):
                                    accumulated_parts.append(text_delta)
                                    if on_chunk:
                                        await on_chunk(text_delta)
                                elif "function_call" in etype:
                                    cid = event.get("call_id") or current_call_id or "call_0"
                                    if cid not in tool_calls_dict:
                                        tool_calls_dict[cid] = {
                                            "id": cid,
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    tool_calls_dict[cid]["function"]["arguments"] += str(event.get("delta") or "")
                            elif etype == "response.output_item.added":
                                it = event.get("item", {})
                                if it.get("type") == "function_call":
                                    current_call_id = it.get("call_id") or it.get("id") or str(uuid.uuid4())
                                    tool_calls_dict[current_call_id] = {
                                        "id": current_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": it.get("name", ""),
                                            "arguments": it.get("arguments", "") or "",
                                        },
                                    }
                            elif etype == "response.completed":
                                resp_obj = event.get("response", {})
                                if not accumulated_parts and resp_obj.get("output_text"):
                                    accumulated_parts.append(resp_obj["output_text"])
                                    if on_chunk:
                                        await on_chunk(resp_obj["output_text"])

                        final_tc = list(tool_calls_dict.values())
                        return {
                            "content": "".join(accumulated_parts),
                            "tool_calls": final_tc,
                            "raw": {},
                        }
                    else:
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
            _LOGGER.info("Responses API: retrying model '%s' with reasoning effort=%s", target_model, next_eff)

        if data is None:
            if status == 404 and target_model != "gpt-4o-mini":
                _LOGGER.warning("Model '%s' returned 404 on OpenAI Responses API. Falling back to 'gpt-4o-mini'.", target_model)
                return await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name="gpt-4o-mini")
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
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call standard OpenAI compatible endpoint."""
        session = await self._get_session()
        target_model = model_name or self.model
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            clean_m: Dict[str, Any] = {
                "role": m.get("role", "user"),
                "content": m.get("content") or "",
            }
            if m.get("tool_calls"):
                clean_m["tool_calls"] = m["tool_calls"]
            if m.get("tool_call_id"):
                clean_m["tool_call_id"] = m["tool_call_id"]
            if m.get("name"):
                clean_m["name"] = m["name"]
            formatted_messages.append(clean_m)

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": formatted_messages,
        }

        # Reasoning effort for OpenAI / OpenRouter (omit for Groq and non-reasoning providers)
        if self.provider not in (PROVIDER_GROQ, PROVIDER_CUSTOM) and thinking_level and thinking_level != THINKING_OFF:
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
                return await self._call_openai_responses(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=target_model)
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
            _LOGGER.info("Model '%s': retrying with reasoning_effort=%s", target_model, next_effort)
            if next_effort is None:
                payload.pop("reasoning_effort", None)
            else:
                payload["reasoning_effort"] = next_effort

        if data is None:
            if last_status == 404:
                # 1. Groq 404 Auto-Recovery
                if self.provider == PROVIDER_GROQ:
                    self._resolved_model_cache = None
                    groq_candidates = ["llama-3.1-8b-instant", "qwen-2.5-32b", "mixtral-8x7b-32768", "gemma2-9b-it", "deepseek-r1-distill-llama-70b"]
                    try:
                        fresh = await self._discover_latest_model()
                        if fresh and fresh != target_model:
                            groq_candidates.insert(0, fresh)
                    except Exception:
                        pass

                    for cand in groq_candidates:
                        if cand != target_model:
                            _LOGGER.warning("Groq model '%s' returned 404. Auto-recovering with '%s'", target_model, cand)
                            try:
                                res = await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=cand)
                                self._resolved_model_cache = cand
                                res["actual_model"] = cand
                                return res
                            except Exception as fb_err:
                                _LOGGER.debug("Groq recovery candidate '%s' failed: %s", cand, fb_err)
                                continue

                # 2. OpenAI 404 Auto-Recovery
                if self.provider == PROVIDER_OPENAI:
                    self._resolved_model_cache = None
                    openai_candidates = ["gpt-4o-mini", "gpt-4o"]
                    for cand in openai_candidates:
                        if cand != target_model:
                            _LOGGER.warning("OpenAI model '%s' returned 404. Auto-recovering with '%s'", target_model, cand)
                            try:
                                res = await self._call_openai_compatible(messages, system_prompt, tools, thinking_level, on_chunk=on_chunk, model_name=cand)
                                self._resolved_model_cache = cand
                                res["actual_model"] = cand
                                return res
                            except Exception:
                                continue

            # 3. 413 / Token rate limit auto-recovery (compression fallback)
            if last_status == 413 or ("rate_limit_exceeded" in err_text.lower() and "token" in err_text.lower()):
                _LOGGER.warning("Request too large (413/tokens) for model '%s'. Attempting automatic compression fallback.", target_model)
                short_prompt = "אתה סוכן AI ל-Home Assistant. בצע את פקודת המשתמש ישירות ובעברית."
                last_messages = messages[-2:] if len(messages) >= 2 else messages
                try:
                    res = await self._call_openai_compatible(
                        last_messages, short_prompt, tools, thinking_level=THINKING_OFF, on_chunk=on_chunk, model_name=target_model
                    )
                    return res
                except Exception as comp_err:
                    _LOGGER.warning("Compression fallback failed: %s", comp_err)

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
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call Anthropic Claude API."""
        session = await self._get_session()
        target_model = model_name or self.model
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        formatted_messages = []
        for m in messages:
            role = m.get("role")
            if role == "tool":
                formatted_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id") or "",
                        "content": str(m.get("content") or ""),
                    }],
                })
            elif role == "assistant" and m.get("tool_calls"):
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments") or "{}"
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id") or str(uuid.uuid4()),
                        "name": fn.get("name", ""),
                        "input": args,
                    })
                formatted_messages.append({"role": "assistant", "content": blocks})
            elif role in ("user", "assistant"):
                formatted_messages.append({
                    "role": role,
                    "content": str(m.get("content") or ""),
                })

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": formatted_messages,
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
                tool_calls_dict: Dict[int, Dict[str, Any]] = {}
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
                    idx = chunk.get("index", 0)
                    if ctype == "content_block_start":
                        cb = chunk.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            tool_calls_dict[idx] = {
                                "id": cb.get("id") or f"call_{idx}_{uuid.uuid4().hex[:6]}",
                                "type": "function",
                                "function": {
                                    "name": cb.get("name", ""),
                                    "arguments": "",
                                },
                            }
                    elif ctype == "content_block_delta":
                        delta = chunk.get("delta") or {}
                        dtype = delta.get("type")
                        if dtype == "text_delta":
                            t = delta.get("text", "")
                            if t:
                                accumulated_text.append(t)
                                if on_chunk:
                                    await on_chunk(t)
                        elif dtype == "input_json_delta":
                            if idx in tool_calls_dict:
                                tool_calls_dict[idx]["function"]["arguments"] += delta.get("partial_json", "")

                final_tc = [tool_calls_dict[i] for i in sorted(tool_calls_dict.keys())]
                return {"content": "".join(accumulated_text), "tool_calls": final_tc, "raw": {}}

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
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call Google Gemini REST API."""
        session = await self._get_session()
        target_model = (model_name or self.model).replace("models/", "")
        method_name = "streamGenerateContent?alt=sse&key=" if on_chunk else "generateContent?key="
        url = f"{self.base_url}/v1beta/models/{target_model}:{method_name}{self.api_key}"
        headers = {"Content-Type": "application/json"}

        contents = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": msg.get("name", "tool"),
                            "response": {"output": msg.get("content", "")},
                        }
                    }],
                })
            elif role == "assistant" and msg.get("tool_calls"):
                parts = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments") or "{}"
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    parts.append({
                        "functionCall": {
                            "name": fn.get("name", ""),
                            "args": args,
                        }
                    })
                contents.append({"role": "model", "parts": parts})
            else:
                gemini_role = "user" if role == "user" else "model"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": str(msg.get("content") or "")}],
                })

        payload: Dict[str, Any] = {"contents": contents}

        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        if tools:
            func_decls = []
            for t in tools:
                fn = t.get("function", t)
                func_decls.append({
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = [{"functionDeclarations": func_decls}]

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
                tool_calls: List[Dict[str, Any]] = []
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
                            fc = p.get("functionCall")
                            if fc:
                                tool_calls.append({
                                    "id": f"call_{uuid.uuid4().hex[:8]}",
                                    "type": "function",
                                    "function": {
                                        "name": fc.get("name", ""),
                                        "arguments": json.dumps(fc.get("args", {}), ensure_ascii=False),
                                    },
                                })
                return {
                    "content": "".join(accumulated_text),
                    "tool_calls": tool_calls,
                    "raw": {},
                }

            data = await resp.json()

        candidates = data.get("candidates", [])
        text = ""
        tool_calls = []
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            for p in parts:
                if p.get("text"):
                    text += p["text"]
                if p.get("functionCall"):
                    fc = p["functionCall"]
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": fc.get("name", ""),
                            "arguments": json.dumps(fc.get("args", {}), ensure_ascii=False),
                        },
                    })

        return {
            "content": text,
            "tool_calls": tool_calls,
            "raw": data,
        }
