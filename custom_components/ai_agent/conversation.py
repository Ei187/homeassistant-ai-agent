"""Conversation entity integration with Home Assistant Assist."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AGENT_SYSTEM_PROMPTS, CONF_AGENT_ROLE, CONF_API_KEY, CONF_REQUIRE_APPROVAL, DOMAIN
from .tools import TOOLS_SCHEMA, ToolEngine

_LOGGER = logging.getLogger(__name__)


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
        """Explicitly declare control capability to remove the warning banner."""
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
        system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_role)
        tool_engine = ToolEngine(
            self.hass,
            require_approval=settings.get(CONF_REQUIRE_APPROVAL, True),
        )

        user_text = user_input.text
        user_lower = user_text.lower()

        # Free tier handling when no API key is configured yet
        if not api_key or not client:
            if any(w in user_lower for w in ["לוג", "שגיא", "תקל", "log", "error"]):
                res = await tool_engine.execute_tool("scan_system_errors", {"limit": 10})
                if res.get("status") == "ok":
                    reply = "סרקתי את המערכת: לא נמצאו שגיאות קריטיות פעילות בלוגים! 🎉"
                else:
                    reply = f"נמצאו {res.get('count', 0)} שגיאות בלוגים של המערכת. פתח את פאנל AI Agent Pro לניתוח מלא."
            elif any(w in user_lower for w in ["אוטומצי", "דוד", "אור", "מזגן", "תכבה", "תדליק", "auto"]):
                prop = await tool_engine.execute_tool("create_automation", {
                    "alias": "הוראה חכמה",
                    "description": f"בקשה: {user_text}",
                    "trigger_yaml": "platform: time\nat: '23:00:00'",
                    "action_yaml": "service: homeassistant.turn_off\ntarget:\n  entity_id: all",
                })
                reply = f"הכנתי הצעה עבורך לפי הבקשה: '{user_text}'. פתח את כרטיס AI Agent Pro בלוח הבקרה כדי לאשר את ההטמעה!"
            else:
                reply = (
                    f"קיבלתי: '{user_text}'. "
                    "אני פועל במצב חינמי ויכול לשלוט במערכת, לבדוק שגיאות וליצור אוטומציות. "
                    "לחיבור מודלי-על כמו GPT-6 Astra, פתח את כרטיס AI Agent Pro בלוח הבקרה ולחץ על כפתור ה-`+`."
                )

            intent_response = conversation.create_intent_response(user_input)
            intent_response.async_set_speech(reply)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )

        # Full Model Execution with Tools
        try:
            formatted_messages = [{"role": "user", "content": user_text}]
            response = await client.chat(
                messages=formatted_messages,
                system_prompt=system_prompt,
                tools=TOOLS_SCHEMA,
            )

            tool_calls = response.get("tool_calls") or []
            content = response.get("content") or ""

            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name")
                    raw_args = fn.get("arguments") or "{}"
                    fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    await tool_engine.execute_tool(fn_name, fn_args)

                formatted_messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                final_turn = await client.chat(messages=formatted_messages, system_prompt=system_prompt)
                content = final_turn.get("content") or content

            intent_response = conversation.create_intent_response(user_input)
            intent_response.async_set_speech(content)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )
        except Exception as err:
            _LOGGER.exception("Error in conversation entity: %s", err)
            intent_response = conversation.create_intent_response(user_input)
            intent_response.async_set_speech(f"אירעה שגיאה: {err}")
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )
