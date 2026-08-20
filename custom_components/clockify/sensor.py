"""Sensor platform for the Clockify integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN, get_in_progress_time_entries_url, get_update_signal
from .entity import ClockifyEntity

_LOGGER = logging.getLogger(__name__)

# Poll summary statistics every 5 minutes so hours-worked totals stay current
SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Clockify sensor entities."""
    entities: list[SensorEntity] = [
        ClockifySensor(entry),
        ClockifySummarySensor(entry, "today", "Hours Today"),
        ClockifySummarySensor(entry, "week", "Hours This Week"),
        ClockifySummarySensor(entry, "month", "Hours This Month"),
        ClockifySummarySensor(entry, "year", "Hours This Year"),
    ]
    async_add_entities(entities)


class ClockifySensor(ClockifyEntity, SensorEntity):
    """Expose the real-time Clockify timer status as a sensor."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the Clockify timer status sensor."""
        super().__init__(entry)
        self._attr_name = "Timer Status"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_status"
        self._attr_native_value = "Idle"
        self._attr_extra_state_attributes: dict[str, Any] = {
            "description": None,
            "project_id": None,
            "project": None,
            "start_time": None,
        }

    @property
    def icon(self) -> str:
        """Return dynamic icon based on timer status."""
        return (
            "mdi:timer-play-outline"
            if self._attr_native_value == "Running"
            else "mdi:timer-off-outline"
        )

    async def async_added_to_hass(self) -> None:
        """Register for updates from webhooks and sync initial state."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                get_update_signal(self._entry.entry_id),
                self._handle_update,
            )
        )

        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        if entry_data:
            self._handle_update(entry_data)

    @callback
    def _handle_update(self, entry_data: dict[str, Any]) -> None:
        """Update the sensor from the latest entry data."""
        is_running = bool(entry_data.get("is_running"))
        self._attr_native_value = "Running" if is_running else "Idle"

        self._attr_extra_state_attributes["description"] = entry_data.get("description")
        self._attr_extra_state_attributes["project_id"] = entry_data.get("project_id")
        self._attr_extra_state_attributes["project"] = entry_data.get("project")
        self._attr_extra_state_attributes["start_time"] = entry_data.get("start_time")

        self.async_write_ha_state()


class ClockifySummarySensor(ClockifyEntity, SensorEntity):
    """Expose aggregated hours worked (today, week, month) from Clockify API."""

    _attr_native_unit_of_measurement = "h"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:clock-outline"

    def __init__(self, entry: ConfigEntry, period_type: str, name: str) -> None:
        """Initialize the Clockify summary sensor."""
        super().__init__(entry)
        self._period_type = period_type
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{period_type}_hours"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Listen for webhook updates and set up periodic polling."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                get_update_signal(self._entry.entry_id),
                self._handle_signal,
            )
        )
        # Refresh stats every SCAN_INTERVAL automatically
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_interval_update,
                SCAN_INTERVAL,
            )
        )
        await self.async_update()

    @callback
    def _handle_signal(self, entry_data: dict[str, Any]) -> None:
        """Schedule an API fetch when a webhook fires."""
        self.hass.async_create_task(self.async_update_ha_state(force_refresh=True))

    async def _async_interval_update(self, _now: Any) -> None:
        """Handle interval timer updates."""
        await self.async_update_ha_state(force_refresh=True)

    async def async_update(self) -> None:
        """Fetch total hours for the specified period directly from Clockify API."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        workspace_id = entry_data.get("workspace_id")
        user_id = entry_data.get("user_id")
        api_key = entry_data.get("api_key")

        if not workspace_id or not user_id or not api_key:
            return

        start_dt, end_dt = self._get_period_bounds()

        session = async_get_clientsession(self.hass)
        url = f"https://reports.api.clockify.me/v1/workspaces/{workspace_id}/reports/summary"
        headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
        }
        body = {
            "dateRangeStart": start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "dateRangeEnd": end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "summaryFilter": {
                "groups": ["USER"]
            },
            "users": {
                "ids": [user_id],
                "contains": "CONTAINS",
                "status": "ALL"
            },
            "exportType": "JSON"
        }

        try:
            async with session.post(url, headers=headers, json=body, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    total_seconds = self._extract_total_time(data)
                    # The report only covers stopped entries, so add the still-running timer's elapsed time
                    total_seconds += await self._get_running_seconds(entry_data, start_dt, end_dt)
                    self._attr_native_value = round(total_seconds / 3600.0, 2)
                else:
                    _LOGGER.warning(
                        "Clockify summary report API returned status %s for %s",
                        response.status,
                        self._period_type,
                    )
        except Exception as err:
            _LOGGER.warning("Failed to fetch Clockify %s summary: %s", self._period_type, err)

    async def _get_running_seconds(
        self, entry_data: dict[str, Any], start_dt: datetime, end_dt: datetime
    ) -> float:
        """Fetch the live in-progress entry so edits to its start time in Clockify are reflected."""
        if not entry_data.get("is_running"):
            return 0.0

        workspace_id = entry_data.get("workspace_id")
        user_id = entry_data.get("user_id")
        api_key = entry_data.get("api_key")
        if not workspace_id or not user_id or not api_key:
            return 0.0

        session = async_get_clientsession(self.hass)
        url = get_in_progress_time_entries_url(workspace_id, user_id)
        headers = {"X-Api-Key": api_key}

        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status != 200:
                    return 0.0
                entries = await response.json()
        except Exception as err:
            _LOGGER.debug("Failed to fetch running Clockify timer: %s", err)
            return 0.0

        if not isinstance(entries, list) or not entries:
            return 0.0

        active = entries[0]
        project_filter = entry_data.get("project_id_config") or None
        if project_filter and active.get("projectId") != project_filter:
            return 0.0

        start_time = dt_util.parse_datetime(active.get("timeInterval", {}).get("start") or "")
        if start_time is None:
            return 0.0

        clamped_start = max(dt_util.as_utc(start_time), start_dt)
        return max((end_dt - clamped_start).total_seconds(), 0.0)

    def _extract_total_time(self, data: dict[str, Any]) -> float:
        """Safely parse totalTime in seconds from Clockify API response."""
        try:
            totals = data.get("totals")
            if isinstance(totals, list) and len(totals) > 0:
                return float(totals[0].get("totalTime") or 0)
            if isinstance(totals, dict):
                return float(totals.get("totalTime") or 0)
            
            # Fallback to groupOne user total if totals array is empty
            group_one = data.get("groupOne")
            if isinstance(group_one, list) and len(group_one) > 0:
                return float(group_one[0].get("duration") or 0)
        except Exception as err:
            _LOGGER.debug("Error parsing total time from Clockify payload: %s", err)

        return 0.0

    def _get_period_bounds(self) -> tuple[datetime, datetime]:
        """Calculate local start and end bounds converted to UTC."""
        now = dt_util.now()
        end_dt = now

        if self._period_type == "today":
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._period_type == "week":
            start_dt = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif self._period_type == "month":
            start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif self._period_type == "year":
            start_dt = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)

        return dt_util.as_utc(start_dt), dt_util.as_utc(end_dt)