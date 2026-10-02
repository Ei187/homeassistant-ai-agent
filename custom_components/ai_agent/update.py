"""Update entity for AI Agent Pro to enable 1-click updates from Home Assistant Settings Dashboard."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Any
import aiohttp

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components import persistent_notification

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
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.RELEASE_NOTES
        | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the update entity."""
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update"
        self._attr_installed_version = VERSION
        self._attr_latest_version = VERSION
        self._attr_release_url = f"https://github.com/{GITHUB_REPO}/releases"
        self._attr_release_summary = ""

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information linking this entity to the AI Agent integration."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="AI Agent Pro",
            manufacturer="Ei187",
            model="AI Agent Pro Assistant",
            sw_version=self._attr_installed_version,
        )

    async def async_update(self) -> None:
        """Check GitHub for the latest release."""
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={"User-Agent": "HomeAssistant-AIAgentPro"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tag = str(data.get("tag_name", "")).strip().lstrip("v")
                    if tag:
                        self._attr_latest_version = tag
                        self._attr_release_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
                        self._attr_release_summary = data.get("body", f"גרסה חדשה v{tag} זמינה להתקנה.")
        except Exception as err:
            _LOGGER.warning("Could not check for AI Agent Pro updates: %s", err)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Install update directly into custom_components from GitHub."""
        _LOGGER.info("Starting in-place update for AI Agent Pro...")
        raw_v = str(version or self._attr_latest_version or VERSION).strip().lstrip("v")
        tag = f"v{raw_v}"

        self._attr_in_progress = True
        self.async_write_ha_state()

        session = async_get_clientsession(self.hass)
        urls_to_try = [
            f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/ai_agent.zip",
            f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.zip",
            f"https://codeload.github.com/{GITHUB_REPO}/zip/refs/tags/{tag}",
            f"https://api.github.com/repos/{GITHUB_REPO}/zipball/{tag}",
            f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip",
        ]

        zip_data = None
        last_err = None

        for u in urls_to_try:
            try:
                _LOGGER.info("Attempting download from %s", u)
                async with session.get(
                    u,
                    headers={"User-Agent": "HomeAssistant-AIAgentPro"},
                    timeout=aiohttp.ClientTimeout(total=60),
                    allow_redirects=True,
                ) as response:
                    if response.status == 200:
                        zip_data = await response.read()
                        _LOGGER.info("Successfully downloaded update from %s (%d bytes)", u, len(zip_data))
                        break
                    else:
                        _LOGGER.warning("Download from %s returned status %d", u, response.status)
            except Exception as ex:
                last_err = ex
                _LOGGER.warning("Download from %s failed: %s", u, ex)

        if not zip_data:
            self._attr_in_progress = False
            self.async_write_ha_state()
            _LOGGER.error("All download URLs failed for AI Agent Pro update to %s: %s", tag, last_err)
            raise HomeAssistantError(f"לא ניתן היה להוריד את חבילת העדכון מ-GitHub: {last_err}")

        def _extract(data: bytes) -> int:
            zf = zipfile.ZipFile(io.BytesIO(data))
            dest_dir = self.hass.config.path("custom_components", "ai_agent")
            prefix = "custom_components/ai_agent/"

            extracted_count = 0
            for member in zf.namelist():
                if prefix in member and not member.endswith("/"):
                    idx = member.index(prefix) + len(prefix)
                    rel_path = member[idx:]
                    target_file = os.path.join(dest_dir, rel_path)
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        dst.write(src.read())
                    extracted_count += 1

            if extracted_count == 0:
                manifest_members = [m for m in zf.namelist() if m.endswith("manifest.json") and not m.endswith("/")]
                if manifest_members:
                    root_prefix = manifest_members[0].rsplit("manifest.json", 1)[0]
                    for member in zf.namelist():
                        if member.startswith(root_prefix) and not member.endswith("/"):
                            rel_path = member[len(root_prefix):]
                            target_file = os.path.join(dest_dir, rel_path)
                            os.makedirs(os.path.dirname(target_file), exist_ok=True)
                            with zf.open(member) as src, open(target_file, "wb") as dst:
                                dst.write(src.read())
                            extracted_count += 1

            _LOGGER.info("Extracted %d files to %s", extracted_count, dest_dir)
            return extracted_count

        try:
            count = await self.hass.async_add_executor_job(_extract, zip_data)
            if count == 0:
                raise RuntimeError("No files were extracted from the update archive")
        except Exception as err:
            self._attr_in_progress = False
            self.async_write_ha_state()
            _LOGGER.exception("Failed to extract AI Agent Pro update: %s", err)
            raise HomeAssistantError(f"חילוץ קבצי העדכון נכשל: {err}") from err

        # Update entity state smoothly so HA updates UI
        self._attr_installed_version = raw_v
        self._attr_in_progress = False
        self.async_write_ha_state()

        persistent_notification.async_create(
            self.hass,
            f"**AI Agent Pro שודרג בהצלחה לגרסה v{raw_v}!** 🎉\n\n"
            f"הקבצים הוטמעו בהצלחה. יש להפעיל מחדש את Home Assistant (הגדרות ➔ מערכת ➔ הפעלה מחדש) כדי להפעיל את הקוד החדש.",
            title=f"AI Agent Pro עודכן ל-v{raw_v}",
            notification_id="ai_agent_update_success",
        )
