"""The Clockify integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_PROJECT_ID,
    CONF_PROJECT_NAME,
    CONF_USER_ID,
    CONF_WORKSPACE_ID,
    DOMAIN,
)
from .webhook import async_setup_webhooks, async_unregister_webhooks

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Clockify from a config entry."""
    entry_data: dict[str, Any] = {
        "entry": entry,
        "is_running": False,
        "description": None,
        "project_id": None,
        "project": None,
        "start_time": None,
        "api_key": entry.data.get(CONF_API_KEY),
        "workspace_id": entry.data.get(CONF_WORKSPACE_ID),
        "user_id": entry.data.get(CONF_USER_ID),
        "project_id_config": entry.data.get(CONF_PROJECT_ID),
        "project_name_config": entry.data.get(CONF_PROJECT_NAME),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry_data

    # Setup webhooks
    webhook_ids = await async_setup_webhooks(hass, entry, entry_data)
    entry_data.update(webhook_ids)

    # Fetch active timer on startup (costs 1 API call per reboot to sync state)
    await _async_fetch_initial_state(hass, entry_data)

    # Forward setups to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data: dict[str, Any] | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if entry_data:
            async_unregister_webhooks(hass, entry_data)
        if not hass.data.get(DOMAIN):
            hass.data.pop(DOMAIN, None)
    return unload_ok


async def _async_fetch_initial_state(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Fetch active running timer on boot to initialize entity states."""
    workspace_id = entry_data.get("workspace_id")
    user_id = entry_data.get("user_id")
    api_key = entry_data.get("api_key")

    if not workspace_id or not user_id or not api_key:
        return

    session = async_get_clientsession(hass)
    url = f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/user/{user_id}/time-entries?in-progress=true"
    headers = {"X-Api-Key": api_key}

    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                entries = await response.json()
                if isinstance(entries, list) and len(entries) > 0:
                    active = entries[0]
                    project_filter = entry_data.get("project_id_config") or None
                    active_project_id = active.get("projectId")
                    if not project_filter or active_project_id == project_filter:
                        entry_data.update(
                            {
                                "is_running": True,
                                "description": active.get("description"),
                                "project_id": active_project_id,
                                "project": entry_data.get("project_name_config"),
                                "start_time": active.get("timeInterval", {}).get("start"),
                            }
                        )
    except Exception as err:
        _LOGGER.warning("Could not fetch initial Clockify state on boot: %s", err)