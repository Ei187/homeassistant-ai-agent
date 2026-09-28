"""Update entity for AI Agent Pro to enable 1-click updates from Home Assistant Settings Dashboard."""

from __future__ import annotations

import io
import logging
import os
import urllib.request
import zipfile
from typing import Any
import aiohttp

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)
GITHUB_REPO = "Ei187/homeassistant-ai-agent"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AI Agent Pro update entity."""
    async_add_entities([AIAgentUpdateEntity(hass, entry)], True)


class AIAgentUpdateEntity(UpdateEntity):
    """Update entity for AI Agent Pro."""

    _attr_has_entity_name = True
    _attr_name = "Update"
    _attr_title = "AI Agent Pro"
    _attr_icon = "mdi:robot"
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the update entity."""
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update"
        self._attr_installed_version = VERSION
        self._attr_latest_version = VERSION
        self._attr_release_url = f"https://github.com/{GITHUB_REPO}/releases"
        self._attr_release_summary = ""

    async def async_update(self) -> None:
        """Check GitHub for the latest tag/release."""
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"User-Agent": "HomeAssistant-AIAgentPro"}, timeout=10) as resp:
                    if resp.status == 200:
                        tags = await resp.json()
                        if tags and isinstance(tags, list):
                            latest_tag = tags[0].get("name", "").lstrip("v")
                            if latest_tag:
                                self._attr_latest_version = latest_tag
                                self._attr_installed_version = VERSION
                                if latest_tag != VERSION:
                                    self._attr_release_summary = f"גרסה חדשה {latest_tag} זמינה להתקנה בלחיצה אחת מלוח הבקרה."
        except Exception as err:
            _LOGGER.warning("Could not check for AI Agent Pro updates: %s", err)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Install update directly into custom_components from GitHub."""
        _LOGGER.info("Starting in-place update for AI Agent Pro...")
        tag = f"v{version}" if version and not version.startswith("v") else (version or f"v{self._attr_latest_version}")

        def _download_and_extract() -> None:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/zipball/{tag}"
            req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant-AIAgentPro"})
            with urllib.request.urlopen(req, timeout=30) as response:
                zip_data = response.read()

            zf = zipfile.ZipFile(io.BytesIO(zip_data))
            dest_dir = self.hass.config.path("custom_components", "ai_agent")
            prefix = "custom_components/ai_agent/"

            for member in zf.namelist():
                if prefix in member and not member.endswith("/"):
                    idx = member.index(prefix) + len(prefix)
                    rel_path = member[idx:]
                    target_file = os.path.join(dest_dir, rel_path)
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        dst.write(src.read())

        await self.hass.async_add_executor_job(_download_and_extract)
        self._attr_installed_version = self._attr_latest_version
        self.async_write_ha_state()

        # Reload entry to apply update
        await self.hass.config_entries.async_reload(self.entry.entry_id)
