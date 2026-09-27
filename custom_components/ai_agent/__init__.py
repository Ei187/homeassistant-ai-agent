"""AI Agent Pro Custom Integration for Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.components.http import StaticPathConfig

from .ai_client import AIClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_THINKING_LEVEL,
    DEFAULT_SETTINGS,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .websocket_api import async_setup_websocket_api

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.CONVERSATION]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration via YAML (registers static paths & websocket)."""
    hass.data.setdefault(DOMAIN, {})

    # Register static path for custom card and panel
    www_dir = Path(__file__).parent / "www"
    js_file = www_dir / "ai-agent-panel.js"
    if js_file.exists():
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                url_path="/ai_agent_panel/ai-agent-panel.js",
                path=str(js_file),
                cache_headers=False,
            )
        ])
        _LOGGER.info("Registered AI Agent frontend at /ai_agent_panel/ai-agent-panel.js")

    async_setup_websocket_api(hass)

    # Register dedicated panel in Home Assistant left sidebar
    try:
        hass.components.frontend.async_register_built_in_panel(
            component_name="custom",
            sidebar_title="AI Agent Pro",
            sidebar_icon="mdi:robot",
            frontend_url_path="ai-agent-pro",
            config={
                "_panel_custom": {
                    "name": "ai-agent-panel",
                    "module_url": "/ai_agent_panel/ai-agent-panel.js",
                }
            },
            require_admin=False,
        )
        _LOGGER.info("Registered AI Agent Pro sidebar panel at /ai-agent-pro")
    except Exception as err:
        _LOGGER.debug("Could not auto-register sidebar panel: %s", err)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()

    settings = dict(DEFAULT_SETTINGS)
    if stored_data:
        settings.update(stored_data)
    # Also merge entry data if present
    settings.update(entry.data)

    async def _create_client() -> AIClient:
        return AIClient(
            provider=settings.get(CONF_PROVIDER, DEFAULT_SETTINGS[CONF_PROVIDER]),
            model=settings.get(CONF_MODEL, DEFAULT_SETTINGS[CONF_MODEL]),
            api_key=settings.get(CONF_API_KEY, ""),
            base_url=settings.get(CONF_BASE_URL, DEFAULT_SETTINGS[CONF_BASE_URL]),
            thinking_level=settings.get(CONF_THINKING_LEVEL, DEFAULT_SETTINGS[CONF_THINKING_LEVEL]),
        )

    client = await _create_client()

    async def _refresh_client() -> None:
        nonlocal client
        await client.close()
        client = await _create_client()
        hass.data[DOMAIN]["client"] = client

    hass.data[DOMAIN] = {
        "entry": entry,
        "storage": store,
        "settings": settings,
        "client": client,
        "refresh_client": _refresh_client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        client = hass.data[DOMAIN].get("client")
        if client:
            await client.close()
        hass.data.pop(DOMAIN)
    return unload_ok
