"""AI Agent Pro Custom Integration for Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.components import frontend

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None

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
    VERSION,
)
from .websocket_api import async_setup_websocket_api

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.CONVERSATION, Platform.UPDATE]


import shutil
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

class AIAgentBrandView(HomeAssistantView):
    """Serve AI Agent Pro brand assets directly with 100% guarantee."""

    url = "/api/brands/integration/ai_agent/{image}"
    name = "api:brands:integration:ai_agent"
    requires_auth = False

    async def get(self, request: web.Request, image: str) -> web.Response:
        brand_dir = Path(__file__).parent / "brand"
        www_dir = Path(__file__).parent / "www"
        file_path = brand_dir / image
        if not file_path.is_file():
            if "logo" in image:
                file_path = brand_dir / "logo.png"
            elif "icon" in image:
                file_path = brand_dir / "icon.png"
            if not file_path.is_file():
                file_path = www_dir / "icon.png"

        if file_path.is_file():
            data = await request.app["hass"].async_add_executor_job(file_path.read_bytes)
            return web.Response(
                body=data,
                content_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )
        return web.Response(status=404)


async def async_setup_common(hass: HomeAssistant) -> None:
    """Ensure brand view, static paths, panel, and websocket API are registered once."""
    if hass.data.get(f"{DOMAIN}_common_registered"):
        return
    hass.data[f"{DOMAIN}_common_registered"] = True

    # Register custom brand view to intercept all brand image calls
    try:
        hass.http.register_view(AIAgentBrandView)
        _LOGGER.info("Registered AIAgentBrandView for /api/brands/integration/ai_agent/{image}")
    except Exception as err:
        _LOGGER.debug("Could not register AIAgentBrandView: %s", err)

    # Clear stale brand 404 cache in HA
    try:
        cache_dir = Path(hass.config.cache_path("brands"))
        for p in [
            cache_dir / "integrations" / "ai_agent",
            cache_dir / "brands" / "ai_agent",
        ]:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass

    # Register static path for custom card, panel and brand icon
    www_dir = Path(__file__).parent / "www"
    brand_dir = Path(__file__).parent / "brand"
    js_file = www_dir / "ai-agent-panel.js"
    icon_file = www_dir / "icon.png"
    logo_file = brand_dir / "logo.png"

    if hasattr(hass.http, "async_register_static_paths") and StaticPathConfig is not None:
        paths = []
        if js_file.exists():
            paths.append(StaticPathConfig(url_path="/ai_agent_panel/ai-agent-panel.js", path=str(js_file), cache_headers=False))
        if icon_file.exists():
            paths.append(StaticPathConfig(url_path="/ai_agent_panel/icon.png", path=str(icon_file), cache_headers=True))
        if logo_file.exists():
            paths.append(StaticPathConfig(url_path="/ai_agent_panel/logo.png", path=str(logo_file), cache_headers=True))
        if paths:
            await hass.http.async_register_static_paths(paths)
            _LOGGER.info("Registered AI Agent static paths via async_register_static_paths")
    elif hasattr(hass.http, "register_static_path"):
        if js_file.exists():
            hass.http.register_static_path("/ai_agent_panel/ai-agent-panel.js", str(js_file), cache_headers=False)
        if icon_file.exists():
            hass.http.register_static_path("/ai_agent_panel/icon.png", str(icon_file), cache_headers=True)
        if logo_file.exists():
            hass.http.register_static_path("/ai_agent_panel/logo.png", str(logo_file), cache_headers=True)
        _LOGGER.info("Registered AI Agent static paths via register_static_path")

    async_setup_websocket_api(hass)

    # Register dedicated panel in Home Assistant left sidebar and load card globally
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="AI Agent Pro",
            sidebar_icon="mdi:robot",
            frontend_url_path="ai-agent-pro",
            config={
                "_panel_custom": {
                    "name": "ai-agent-panel",
                    "module_url": f"/ai_agent_panel/ai-agent-panel.js?v={VERSION}",
                }
            },
            require_admin=False,
        )
        frontend.add_extra_js_url(hass, f"/ai_agent_panel/ai-agent-panel.js?v={VERSION}")
        _LOGGER.info("Registered AI Agent Pro sidebar panel and extra JS url")
    except Exception as err:
        _LOGGER.warning("Could not register sidebar panel or extra JS url: %s", err)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration via YAML."""
    hass.data.setdefault(DOMAIN, {})
    await async_setup_common(hass)
    # Ensure storage and settings exist even before config entry is added
    if "storage" not in hass.data[DOMAIN]:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        stored_data = await store.async_load()
        settings = dict(DEFAULT_SETTINGS)
        if stored_data:
            settings.update({k: v for k, v in stored_data.items() if v is not None and v != ""})
        hass.data[DOMAIN]["storage"] = store
        hass.data[DOMAIN]["settings"] = settings
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry with robust multi-source synchronization."""
    hass.data.setdefault(DOMAIN, {})
    await async_setup_common(hass)
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load()

    settings = dict(DEFAULT_SETTINGS)
    if entry.data:
        settings.update({k: v for k, v in entry.data.items() if v is not None and v != ""})
    if entry.options:
        settings.update({k: v for k, v in entry.options.items() if v is not None and v != ""})
    # Stored panel settings take highest precedence
    if stored_data:
        settings.update({k: v for k, v in stored_data.items() if v is not None and v != ""})

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
        if client:
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

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        client = hass.data[DOMAIN].get("client")
        if client:
            await client.close()
        hass.data.pop(DOMAIN)
    return unload_ok
