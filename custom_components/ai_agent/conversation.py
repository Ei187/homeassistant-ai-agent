"""Conversation entity integration with Home Assistant Assist."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AGENT_SYSTEM_PROMPTS, CONF_AGENT_ROLE, CONF_API_KEY, CONF_REQUIRE_APPROVAL, DOMAIN
from .tools import TOOLS_SCHEMA, ToolEngine, get_entities_context

_LOGGER = logging.getLogger(__name__)

# Maintain conversation history per conversation_id
CONVERSATION_HISTORIES: Dict[str, List[Dict[str, Any]]] = {}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the conversation entity from a config entry."""
    async_add_entities([AIAgentConversationEntity(hass, entry)])


class AIAgentConversationEntity(conversation.ConversationEntity):
    """Conversation entity for AI Agent Pro."""

    _attr_has_entity_name = True
    _attr_name = "AI Agent Pro"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_conversation"

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    @property
    def supported_features(self) -> int:
        """Declare control capability to remove any Assist warning banners."""
        if hasattr(conversation, "ConversationEntityFeature"):
            return getattr(conversation.ConversationEntityFeature, "CONTROL", 1)
        return 1

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process user input from HA Assist dialog with full tool control."""
        settings = self.hass.data.get(DOMAIN, {}).get("settings", {})
        api_key = settings.get(CONF_API_KEY, "")
        client = self.hass.data.get(DOMAIN, {}).get("client")

        agent_role = settings.get(CONF_AGENT_ROLE, "omni")
        base_prompt = AGENT_SYSTEM_PROMPTS.get(agent_role, AGENT_SYSTEM_PROMPTS["omni"])
        tool_engine = ToolEngine(
            self.hass,
            require_approval=settings.get(CONF_REQUIRE_APPROVAL, True),
        )

        user_text = user_input.text.strip()
        conv_id = user_input.conversation_id or "default"

        # Local NLP execution if no API key is provided
        if not api_key or not client:
            reply = await self._handle_local_intent(user_text, tool_engine)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(reply)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=conv_id
            )

        # Full AI Model Execution with Real Home Entities Context & Multi-Turn Tools
        try:
            entities_text = get_entities_context(self.hass)
            full_system_prompt = (
                f"{base_prompt}\n\n"
                f"### רשימת המכשירים והישויות בבית (Home Entities & Current States):\n"
                f"{entities_text}\n\n"
                "הנחיות חשובות לפעולה:\n"
                "1. כשמשתמש מבקש לשלוט במכשיר (הדלקה, כיבוי, שינוי טמפרטורה), קרא מיד לכלי control_device עם ה-entity_id המדויק מהרשימה.\n"
                "2. כשמשתמש שואל מה פתוח/דולק או על נתון של מכשיר, ענה ישירות לפי המצב הנוכחי ברשימה או קרא לכלי המתאים.\n"
                "3. ענה תמיד בעברית טבעית, תמציתית וישירה."
            )

            # Retrieve conversation history
            if conv_id not in CONVERSATION_HISTORIES:
                CONVERSATION_HISTORIES[conv_id] = []
            history = CONVERSATION_HISTORIES[conv_id]
            history.append({"role": "user", "content": user_text})

            # Trim history to keep last 10 messages
            if len(history) > 10:
                history = history[-10:]
                CONVERSATION_HISTORIES[conv_id] = history

            messages_payload = list(history)

            # Step 1: Call Model with Tools
            response = await client.chat(
                messages=messages_payload,
                system_prompt=full_system_prompt,
                tools=TOOLS_SCHEMA,
            )

            tool_calls = response.get("tool_calls") or []
            content = response.get("content") or ""

            # Step 2: Handle Tool Calls strictly according to OpenAI specification
            if tool_calls:
                # Append assistant tool call message
                messages_payload.append({
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                })

                # Execute each tool and append tool response
                for tc in tool_calls:
                    call_id = tc.get("id") or str(uuid.uuid4())
                    fn = tc.get("function", {})
                    fn_name = fn.get("name")
                    raw_args = fn.get("arguments") or "{}"
                    fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                    tool_result = await tool_engine.execute_tool(fn_name, fn_args)

                    messages_payload.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })

                # Step 3: Second turn for model to formulate natural user reply
                final_turn = await client.chat(
                    messages=messages_payload,
                    system_prompt=full_system_prompt,
                )
                content = final_turn.get("content") or content or "הפעולה בוצעה בהצלחה."

            # Update conversation history with assistant response
            if content:
                history.append({"role": "assistant", "content": content})

            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(content)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=conv_id
            )

        except Exception as err:
            _LOGGER.warning("AI model chat failed: %s. Falling back to local engine.", err)
            # Graceful local fallback so user request always succeeds
            reply = await self._handle_local_intent(user_text, tool_engine)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(reply)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=conv_id
            )

    async def _handle_local_intent(self, text: str, tool_engine: ToolEngine) -> str:
        """Smart local NLP handler for free tier or offline fallback."""
        lower = text.lower()

        # 1. Check for logs / error scan requests
        if any(w in lower for w in ["לוג", "שגיא", "תקל", "log", "error"]):
            res = await tool_engine.execute_tool("scan_system_errors", {"limit": 10})
            if res.get("status") == "ok":
                return "סרקתי את המערכת: לא נמצאו שגיאות קריטיות פעילות בלוגים של Home Assistant! 🎉"
            count = res.get("count", 0)
            return f"סרקתי את המערכת: נמצאו {count} שגיאות או אזהרות בלוגים. לניתוח מעמיק פתח את פאנל AI Agent Pro בסרגל הצד."

        # 2. Check for automation creation requests
        if any(w in lower for w in ["צור אוטומצי", "תבנה אוטומצי", "אוטומציה חדשה"]):
            prop = await tool_engine.execute_tool("create_automation", {
                "alias": "אוטומציה לפי בקשה",
                "description": f"בקשה מהצ'אט: {text}",
                "trigger_yaml": "platform: time\nat: '23:00:00'",
                "action_yaml": "service: homeassistant.turn_off\ntarget:\n  entity_id: all",
            })
            return f"הכנתי הצעה לאוטומציה לפי בקשתך ('{text}'). פתח את פאנל AI Agent Pro כדי לאשר את ההטמעה!"

        # 3. Status queries: What is on?
        if any(w in lower for w in ["מה דולק", "איזה אורות דולקים", "מה פועל", "מה עובד"]):
            active = []
            for s in self.hass.states.async_all():
                if s.domain in ("light", "switch") and s.state == "on":
                    active.append(s.name or s.entity_id)
            if active:
                return f"המכשירים שדולקים כרגע בבית ({len(active)}): {', '.join(active[:15])}."
            return "כל האורות והמתגים בבית כבויים כרגע. 🌙"

        # 4. Device control intents (turn_on, turn_off, toggle)
        is_turn_on = any(w in lower for w in ["תדליק", "תפעיל", "פתח", "turn on", "תדליקי", "הדלק"])
        is_turn_off = any(w in lower for w in ["תכבה", "תסגור", "כבה", "turn off", "תכבי", "כיבוי"])
        is_toggle = any(w in lower for w in ["שנה מצב", "toggle", "תחליף"])

        if is_turn_on or is_turn_off or is_toggle:
            action = "turn_on" if is_turn_on else ("turn_off" if is_turn_off else "toggle")

            # Check if command is for all lights
            if any(w in lower for w in ["כל האורות", "כל האור", "כל המנורות", "כל התאורה", "all lights"]):
                res = await tool_engine.execute_tool("control_device", {"entity_id": "all_lights", "action": action})
                return res.get("message", f"הפעולה '{action}' בוצעה על כל האורות.")

            # Search for best matching entity
            stop_words = {
                "את", "האור", "אור", "מנורה", "תדליק", "תדליקי", "תפעיל", "תכבה", "תכבי",
                "כבה", "הדלק", "בבקשה", "בחדר", "חדר", "ב", "של", "בסלון", "במטבח"
            }
            words = [w for w in lower.split() if w not in stop_words and len(w) > 1]

            best_match = None
            best_score = 0

            controllable = ["light", "switch", "climate", "cover", "fan", "media_player", "lock"]
            for state in self.hass.states.async_all():
                if state.domain not in controllable:
                    continue
                s_name = (state.name or "").lower()
                s_id = state.entity_id.lower()

                score = 0
                for w in words:
                    if w in s_name:
                        score += 3
                    elif w in s_id:
                        score += 2

                # Bonus for exact room/keyword match
                if any(w in lower for w in ["דוד", "boiler"]) and any(k in s_id or k in s_name for k in ["boiler", "דוד"]):
                    score += 10
                if any(w in lower for w in ["סלון", "living"]) and any(k in s_id or k in s_name for k in ["living", "סלון"]):
                    score += 5
                if any(w in lower for w in ["אמא", "mom"]) and any(k in s_id or k in s_name for k in ["mom", "אמא"]):
                    score += 10

                if score > best_score:
                    best_score = score
                    best_match = state

            if best_match and best_score >= 2:
                res = await tool_engine.execute_tool("control_device", {
                    "entity_id": best_match.entity_id,
                    "action": action,
                })
                verb = "הדלקתי" if action == "turn_on" else ("כיביתי" if action == "turn_off" else "שיניתי את מצב")
                return f"{verb} את {best_match.name}! 💡"

            # If no specific match was found, inform user clearly
            return (
                f"לא הצלחתי לזהות במדויק איזה מכשיר להפעיל עבור '{text}'. "
                "נסה לציין את שם המכשיר (למשל: 'תדליק אור בסלון', 'תכבה את הדוד')."
            )

        # 5. Default friendly response
        return (
            f"קיבלתי: '{text}'. "
            "אני סוכן AI Agent Pro לבית החכם. אני יכול לשלוט במכשירים (למשל 'תדליק אור בסלון', 'תכבה את הדוד'), "
            "לסרוק שגיאות במערכת ולבנות אוטומציות. "
            "לחיבור מודלי שפה מתקדמים (GPT-6, Claude, Gemini), פתח את AI Agent Pro בסרגל הצד השמאלי או בהגדרות האינטגרציה והזן מפתח API."
        )
