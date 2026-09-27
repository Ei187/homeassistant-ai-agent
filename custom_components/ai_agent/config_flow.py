"""Zero-Friction Config Flow and Direct In-Integration Options Flow for AI Agent Pro."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
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
    """Handle a zero-friction config flow for AI Agent Pro."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow so user can configure directly from integration page."""
        return AIAgentOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Single-click instant setup step without complex questions."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="AI Agent Pro",
                data=dict(DEFAULT_SETTINGS),
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "info": "התקנה מהירה בלחיצה אחת. ניתן להגדיר הכל ישירות מתוך כפתור 'Configure' (קבע תצורה) באינטגרציה."
            },
        )


class AIAgentOptionsFlowHandler(config_entries.OptionsFlow):
    """Direct configuration inside Settings -> Devices & Services -> AI Agent Pro -> Configure."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage options directly from the integration page."""
        errors: dict[str, str] = {}
        settings = dict(self.config_entry.data)
        if self.config_entry.options:
            settings.update(self.config_entry.options)

        domain_settings = self.hass.data.get(DOMAIN, {}).get("settings", {})
        for k, v in domain_settings.items():
            if v and not settings.get(k):
                settings[k] = v

        if user_input is not None:
            prov = user_input.get(CONF_PROVIDER)
            if not user_input.get(CONF_BASE_URL) and prov in DEFAULT_BASE_URLS:
                user_input[CONF_BASE_URL] = DEFAULT_BASE_URLS[prov]

            # Keep storage and memory in lockstep
            domain_data = self.hass.data.get(DOMAIN, {})
            if "storage" in domain_data:
                await domain_data["storage"].async_save(user_input)
            if "settings" in domain_data:
                domain_data["settings"].update(user_input)

            # Save in integration data/options
            return self.async_create_entry(title="", data=user_input)

        provider_options = [{"value": p, "label": PROVIDER_NAMES.get(p, p)} for p in PROVIDERS]
        role_options = [{"value": r, "label": AGENT_ROLE_NAMES.get(r, r)} for r in AGENT_ROLES]
        thinking_options = [{"value": t, "label": THINKING_LEVEL_NAMES.get(t, t)} for t in THINKING_LEVELS]

        schema = vol.Schema({
            vol.Required(
                CONF_AGENT_ROLE,
                default=settings.get(CONF_AGENT_ROLE, DEFAULT_SETTINGS[CONF_AGENT_ROLE]),
            ): SelectSelector(
                SelectSelectorConfig(options=role_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(
                CONF_PROVIDER,
                default=settings.get(CONF_PROVIDER, DEFAULT_SETTINGS[CONF_PROVIDER]),
            ): SelectSelector(
                SelectSelectorConfig(options=provider_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(
                CONF_MODEL,
                default=settings.get(CONF_MODEL, DEFAULT_SETTINGS[CONF_MODEL]),
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_THINKING_LEVEL,
                default=settings.get(CONF_THINKING_LEVEL, DEFAULT_SETTINGS[CONF_THINKING_LEVEL]),
            ): SelectSelector(
                SelectSelectorConfig(options=thinking_options, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(
                CONF_API_KEY,
                default=settings.get(CONF_API_KEY, ""),
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_BASE_URL,
                default=settings.get(CONF_BASE_URL, DEFAULT_SETTINGS[CONF_BASE_URL]),
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(
                CONF_REQUIRE_APPROVAL,
                default=settings.get(CONF_REQUIRE_APPROVAL, True),
            ): BooleanSelector(),
        })

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
