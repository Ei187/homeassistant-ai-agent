"""Zero-Friction Config Flow for AI Agent Pro Integration."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_SETTINGS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AIAgentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a zero-friction config flow for AI Agent Pro."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Single-click instant setup step without complex questions."""
        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="AI Agent Pro (Apple Edition)",
                data=dict(DEFAULT_SETTINGS),
            )

        # Empty schema so user just clicks 'Submit' to finish!
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "info": "התקנה מהירה בלחיצה אחת. כל ההגדרות, בחירת ספק ומודל ניתנות לשינוי ישירות דרך כפתור ה-`+` בתוך הצ'אט."
            },
        )
