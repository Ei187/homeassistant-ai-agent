"""Repairs platform for AI Agent Pro."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


class RestartRepairFlow(RepairsFlow):
    """Handler for an issue fixing flow to restart Home Assistant."""

    def __init__(self, issue_id: str, data: dict[str, Any] | None = None) -> None:
        """Initialize the repair flow."""
        self.issue_id = issue_id
        self.data = data or {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the first step of a fix flow."""
        return await self.async_step_confirm_restart(user_input)

    async def async_step_confirm_restart(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle restart confirmation and trigger Home Assistant restart."""
        if user_input is not None:
            _LOGGER.info("User confirmed restart via Repairs. Restarting Home Assistant...")
            await self.hass.services.async_call("homeassistant", "restart")
            return self.async_create_entry(title="", data={})

        version = self.data.get("version", "")
        return self.async_show_form(
            step_id="confirm_restart",
            data_schema=vol.Schema({}),
            description_placeholders={"version": version},
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None = None,
) -> RepairsFlow:
    """Create a repair fix flow for an issue."""
    return RestartRepairFlow(issue_id, data)
