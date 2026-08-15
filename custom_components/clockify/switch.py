"""Switch platform for the Clockify integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CLOCKIFY_API_BASE_URL,
    CONF_API_KEY,
    CONF_PROJECT_ID,
    CONF_USER_ID,
    CONF_WORKSPACE_ID,
    DOMAIN,
    get_update_signal,
)
from .entity import ClockifyEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Clockify switch entity."""
    async_add_entities([ClockifySwitch(entry)])


class ClockifySwitch(ClockifyEntity, SwitchEntity):
    """Represent the current Clockify timer status."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the Clockify switch."""
        super().__init__(entry)
        self._attr_name = "Timer"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_timer"
        self._attr_is_on = False
        self._attr_extra_state_attributes: dict[str, Any] = {
            "description": None,
            "project_id": None,
            "project": None,
            "start_time": None,
        }

    async def async_added_to_hass(self) -> None:
        """Register for updates from webhooks and load initial state."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                get_update_signal(self._entry.entry_id),
                self._handle_update,
            )
        )

        # Restore initial state if available in hass.data
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        if entry_data:
            self._handle_update(entry_data)

    @callback
    def _handle_update(self, entry_data: dict[str, Any]) -> None:
        """Update the entity state from incoming webhook data or internal calls."""
        self._attr_is_on = bool(entry_data.get("is_running"))
        self._attr_extra_state_attributes["description"] = entry_data.get("description")
        self._attr_extra_state_attributes["project_id"] = entry_data.get("project_id")
        self._attr_extra_state_attributes["project"] = entry_data.get("project")
        self._attr_extra_state_attributes["start_time"] = entry_data.get("start_time")
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start a new Clockify timer entry."""
        entry_data = self.hass.data[DOMAIN][self._entry.entry_id]
        project_id = entry_data.get("project_id_config") or self._entry.data.get(CONF_PROJECT_ID)
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload: dict[str, Any] = {
            "start": now_utc,
            "description": "",
        }
        if project_id:
            payload["projectId"] = project_id

        await self._async_call_clockify(
            method="post",
            endpoint=f"/workspaces/{self._entry.data[CONF_WORKSPACE_ID]}/time-entries",
            json=payload,
        )

        entry_data.update(
            {
                "is_running": True,
                "description": payload["description"],
                "project_id": project_id,
                "project": entry_data.get("project_name_config"),
                "start_time": payload["start"],
            }
        )
        self._handle_update(entry_data)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the current Clockify timer entry."""
        entry_data = self.hass.data[DOMAIN][self._entry.entry_id]
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {"end": now_utc}

        await self._async_call_clockify(
            method="patch",
            endpoint=f"/workspaces/{self._entry.data[CONF_WORKSPACE_ID]}/user/{self._entry.data[CONF_USER_ID]}/time-entries",
            json=payload,
        )

        entry_data.update(
            {
                "is_running": False,
                "description": None,
                "project_id": None,
                "project": None,
                "start_time": None,
            }
        )
        self._handle_update(entry_data)

    async def _async_call_clockify(self, *, method: str, endpoint: str, json: dict[str, Any]) -> None:
        """Call the Clockify API using Home Assistant's shared ClientSession."""
        session = async_get_clientsession(self.hass)
        headers = {"X-Api-Key": self._entry.data[CONF_API_KEY]}

        async with session.request(
            method.upper(),
            f"{CLOCKIFY_API_BASE_URL}{endpoint}",
            headers=headers,
            json=json,
            timeout=10,
        ) as response:
            if response.status >= 400:
                body = await response.text()
                _LOGGER.error("Clockify API error %s: %s", response.status, body)
                raise RuntimeError(f"Clockify API error {response.status}: {body}")