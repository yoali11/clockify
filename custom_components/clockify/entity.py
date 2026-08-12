"""Shared entity base for the Clockify integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import CONF_PROJECT_ID, CONF_PROJECT_NAME, DOMAIN


class ClockifyEntity(Entity):
    """Base entity that groups Clockify entities under a per-project device."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the entity and its associated device."""
        self._entry = entry
        project_id = entry.data.get(CONF_PROJECT_ID) or None
        project_name = entry.data.get(CONF_PROJECT_NAME)
        # Identifier includes the project id so each project gets its own device.
        device_key = f"{entry.entry_id}_{project_id or 'default'}"
        if project_name:
            device_name = f"Clockify - {project_name}"
        elif project_id:
            device_name = f"Clockify Project {project_id}"
        else:
            device_name = "Clockify Timer"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=device_name,
            manufacturer="Clockify",
            model="Timer",
        )
