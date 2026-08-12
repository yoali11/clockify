"""Clockify API coordinator."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CLOCKIFY_API_BASE, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ClockifyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache data from the Clockify API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        workspace_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._workspace_id = workspace_id
        self._headers = {"X-Api-Key": api_key}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Clockify API."""
        session = async_get_clientsession(self.hass)
        try:
            user = await self._get_user(session)
            user_id = user["id"]
            active_entry = await self._get_active_entry(session, user_id)
            recent_entries = await self._get_recent_entries(session, user_id)
            return {
                "user": user,
                "active_entry": active_entry,
                "recent_entries": recent_entries,
            }
        except aiohttp.ClientResponseError as err:
            raise UpdateFailed(f"Clockify API error: {err.status} {err.message}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Clockify API: {err}") from err

    async def _get_user(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Return the current user."""
        async with session.get(
            f"{CLOCKIFY_API_BASE}/user", headers=self._headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _get_active_entry(
        self, session: aiohttp.ClientSession, user_id: str
    ) -> dict[str, Any] | None:
        """Return the currently running time entry, or None."""
        url = (
            f"{CLOCKIFY_API_BASE}/workspaces/{self._workspace_id}"
            f"/user/{user_id}/time-entries?in-progress=true&page-size=1"
        )
        async with session.get(url, headers=self._headers) as resp:
            resp.raise_for_status()
            entries = await resp.json()
            return entries[0] if entries else None

    async def _get_recent_entries(
        self, session: aiohttp.ClientSession, user_id: str
    ) -> list[dict[str, Any]]:
        """Return the 10 most recent time entries."""
        url = (
            f"{CLOCKIFY_API_BASE}/workspaces/{self._workspace_id}"
            f"/user/{user_id}/time-entries?page-size=10"
        )
        async with session.get(url, headers=self._headers) as resp:
            resp.raise_for_status()
            return await resp.json()


async def validate_and_get_workspaces(
    api_key: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate an API key and return (user, workspaces) in one shared session."""
    headers = {"X-Api-Key": api_key}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{CLOCKIFY_API_BASE}/user") as resp:
            resp.raise_for_status()
            user = await resp.json()
        async with session.get(f"{CLOCKIFY_API_BASE}/workspaces") as resp:
            resp.raise_for_status()
            workspaces = await resp.json()
    return user, workspaces
