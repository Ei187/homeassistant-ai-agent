"""Conversation entity integration with Home Assistant Assist."""

from __future__ import annotations

import logging
from typing import Any, Literal
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

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

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process user input from HA Assist dialog."""
        client = self.hass.data[DOMAIN].get("client")
        if not client:
            intent_response = conversation.create_intent_response(user_input)
            intent_response.async_set_speech(
                "שגיאה: סוכן ה-AI אינו מוגדר עדיין. נא להזין מפתח API בהגדרות התוסף."
            )
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )

        try:
            # We process via WebSocket or direct client
            result = await client.chat([{"role": "user", "content": user_input.text}])
            text_reply = result.get("content", "")
            notice = result.get("fallback_notice")
            if notice:
                text_reply = f"{notice}\n\n{text_reply}"

            intent_response = conversation.create_intent_response(user_input)
            intent_response.async_set_speech(text_reply)
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )
        except Exception as err:
            _LOGGER.exception("Error in conversation entity: %s", err)
            intent_response = conversation.create_intent_response(user_input)
            intent_response.async_set_speech(f"אירעה שגיאה בעיבוד הבקשה: {err}")
            return conversation.ConversationResult(
                response=intent_response, conversation_id=user_input.conversation_id
            )
