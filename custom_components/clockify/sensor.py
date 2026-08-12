"""Sensor entities for the Clockify integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BILLABLE,
    ATTR_DESCRIPTION,
    ATTR_DURATION,
    ATTR_PROJECT,
    ATTR_START,
    DOMAIN,
)
from .coordinator import ClockifyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Clockify sensors from a config entry."""
    coordinator: ClockifyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ClockifyActiveTimerSensor(coordinator, entry),
            ClockifyLastEntrySensor(coordinator, entry),
        ]
    )


class _ClockifyBaseSensor(CoordinatorEntity[ClockifyCoordinator], SensorEntity):
    """Base class for Clockify sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ClockifyCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for grouping sensors."""
        return {
            "identifiers": {(DOMAIN, self._entry.unique_id)},
            "name": self._entry.title,
            "manufacturer": "Clockify",
        }


class ClockifyActiveTimerSensor(_ClockifyBaseSensor):
    """Sensor that shows whether a timer is currently running."""

    _attr_icon = "mdi:timer"

    def __init__(self, coordinator: ClockifyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id}_active_timer"
        self._attr_name = "Active Timer"

    @property
    def native_value(self) -> str:
        """Return 'running' or 'stopped'."""
        data = self.coordinator.data
        if data and data.get("active_entry"):
            return "running"
        return "stopped"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for the active timer."""
        data = self.coordinator.data
        if not data:
            return {}
        entry = data.get("active_entry")
        if not entry:
            return {}
        attrs: dict[str, Any] = {
            ATTR_START: entry.get("timeInterval", {}).get("start"),
            ATTR_DESCRIPTION: entry.get("description", ""),
            ATTR_BILLABLE: entry.get("billable", False),
        }
        project = entry.get("project")
        if project:
            attrs[ATTR_PROJECT] = project.get("name", "")
        return attrs


class ClockifyLastEntrySensor(_ClockifyBaseSensor):
    """Sensor that shows the most recent completed time entry."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: ClockifyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id}_last_entry"
        self._attr_name = "Last Time Entry"

    def _last_completed_entry(self) -> dict[str, Any] | None:
        """Return the most recent completed time entry, or None."""
        data = self.coordinator.data
        if not data:
            return None
        entries = data.get("recent_entries") or []
        completed = [
            e for e in entries
            if e.get("timeInterval", {}).get("end") is not None
        ]
        return completed[0] if completed else None

    @property
    def native_value(self) -> str | None:
        """Return the description of the most recent completed entry."""
        last = self._last_completed_entry()
        if last is None:
            return None
        return last.get("description") or "No description"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for the last time entry."""
        last = self._last_completed_entry()
        if last is None:
            return {}
        interval = last.get("timeInterval", {})
        attrs: dict[str, Any] = {
            ATTR_START: interval.get("start"),
            ATTR_DURATION: interval.get("duration"),
            ATTR_DESCRIPTION: last.get("description", ""),
            ATTR_BILLABLE: last.get("billable", False),
        }
        project = last.get("project")
        if project:
            attrs[ATTR_PROJECT] = project.get("name", "")
        return attrs
