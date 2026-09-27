"""Config flow for AI Agent Pro Integration."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    BooleanSelector,
)

from .const import (
    AGENT_ROLE_NAMES,
    AGENT_ROLES,
    CONF_AGENT_ROLE,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_REQUIRE_APPROVAL,
    CONF_THINKING_LEVEL,
    DEFAULT_BASE_URLS,
    DEFAULT_SETTINGS,
    DOMAIN,
    PROVIDER_NAMES,
    PROVIDERS,
    THINKING_LEVEL_NAMES,
    THINKING_LEVELS,
)

_LOGGER = logging.getLogger(__name__)


class AIAgentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AI Agent Pro."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Set default base URL if empty
            prov = user_input.get(CONF_PROVIDER)
            if not user_input.get(CONF_BASE_URL) and prov in DEFAULT_BASE_URLS:
                user_input[CONF_BASE_URL] = DEFAULT_BASE_URLS[prov]

            return self.async_create_entry(
                title=f"AI Agent Pro ({user_input.get(CONF_MODEL, 'Multi-Model')})",
                data=user_input,
            )

        provider_options = [{"value": p, "label": PROVIDER_NAMES.get(p, p)} for p in PROVIDERS]
        role_options = [{"value": r, "label": AGENT_ROLE_NAMES.get(r, r)} for r in AGENT_ROLES]
        thinking_options = [{"value": t, "label": THINKING_LEVEL_NAMES.get(t, t)} for t in THINKING_LEVELS]

        schema = vol.Schema({
            vol.Required(CONF_AGENT_ROLE, default=DEFAULT_SETTINGS[CONF_AGENT_ROLE]): SelectSelector(
                SelectSelectorConfig(options=role_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_PROVIDER, default=DEFAULT_SETTINGS[CONF_PROVIDER]): SelectSelector(
                SelectSelectorConfig(options=provider_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_MODEL, default=DEFAULT_SETTINGS[CONF_MODEL]): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_THINKING_LEVEL, default=DEFAULT_SETTINGS[CONF_THINKING_LEVEL]): SelectSelector(
                SelectSelectorConfig(options=thinking_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_BASE_URL, default=DEFAULT_SETTINGS[CONF_BASE_URL]): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(CONF_REQUIRE_APPROVAL, default=True): BooleanSelector(),
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
