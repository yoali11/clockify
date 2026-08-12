"""Webhook support for Clockify updates."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import get_url

from .const import (
    CONF_STARTED_WEBHOOK_ID,
    CONF_STARTED_WEBHOOK_URL,
    CONF_STOPPED_WEBHOOK_ID,
    CONF_STOPPED_WEBHOOK_URL,
    DOMAIN,
    get_update_signal,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_webhooks(
    hass: HomeAssistant, entry: Any, entry_data: dict[str, Any]
) -> dict[str, str]:
    """Register separate start/stop webhook endpoints for the config entry."""
    entry_id = entry.entry_id
    started_webhook_id = (
        entry.data.get(CONF_STARTED_WEBHOOK_ID) or f"{entry_id}_timer_started"
    )
    stopped_webhook_id = (
        entry.data.get(CONF_STOPPED_WEBHOOK_ID) or f"{entry_id}_timer_stopped"
    )

    started_url = _build_webhook_url(hass, started_webhook_id)
    stopped_url = _build_webhook_url(hass, stopped_webhook_id)

    entry_data[CONF_STARTED_WEBHOOK_ID] = started_webhook_id
    entry_data[CONF_STOPPED_WEBHOOK_ID] = stopped_webhook_id
    entry_data[CONF_STARTED_WEBHOOK_URL] = started_url
    entry_data[CONF_STOPPED_WEBHOOK_URL] = stopped_url

    webhook.async_register(
        hass,
        DOMAIN,
        "Clockify Timer Started",
        started_webhook_id,
        _make_handler(hass, entry_id, entry_data, is_started=True),
    )
    webhook.async_register(
        hass,
        DOMAIN,
        "Clockify Timer Stopped",
        stopped_webhook_id,
        _make_handler(hass, entry_id, entry_data, is_started=False),
    )

    _LOGGER.info("Clockify webhooks registered: %s | %s", started_url, stopped_url)
    return {
        CONF_STARTED_WEBHOOK_ID: started_webhook_id,
        CONF_STOPPED_WEBHOOK_ID: stopped_webhook_id,
        CONF_STARTED_WEBHOOK_URL: started_url,
        CONF_STOPPED_WEBHOOK_URL: stopped_url,
    }


def async_unregister_webhooks(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    """Unregister the webhooks created for a config entry."""
    for webhook_id in (
        entry_data.get(CONF_STARTED_WEBHOOK_ID),
        entry_data.get(CONF_STOPPED_WEBHOOK_ID),
    ):
        if webhook_id:
            webhook.async_unregister(hass, webhook_id)


def _build_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Build the public webhook URL for a webhook ID."""
    try:
        base_url = get_url(hass, allow_external=True)
    except Exception:  # pragma: no cover - defensive
        base_url = "https://your-home-assistant-instance"
    if not base_url.endswith("/"):
        base_url = f"{base_url}/"
    return f"{base_url}api/webhook/{webhook_id}"


def _make_handler(
    hass: HomeAssistant, entry_id: str, entry_data: dict[str, Any], *, is_started: bool
):
    """Create a webhook handler that updates state and dispatches events."""

    async def _handler(_hass: HomeAssistant, _webhook_id: str, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning("Clockify webhook payload was not valid JSON: %s", err)
            return web.Response(text="Invalid JSON", status=400)

        # Clockify sends time entry directly at root or inside "timeEntry" key
        time_entry = (
            payload.get("timeEntry")
            if isinstance(payload.get("timeEntry"), dict)
            else payload
        )

        project_filter = entry_data.get("project_id_config") or None

        if is_started:
            # Extract nested project information if available
            project = time_entry.get("project") or {}
            project_id = time_entry.get("projectId") or (
                project.get("id") if isinstance(project, dict) else None
            )
            project_name = (
                project.get("name")
                if isinstance(project, dict)
                else time_entry.get("projectName")
            )

            if project_filter and project_id != project_filter:
                _LOGGER.debug("Ignoring Clockify timer for a different project: %s", project_id)
                return web.Response(text="Ignored - different project", status=200)

            entry_data.update(
                {
                    "is_running": True,
                    "description": time_entry.get("description"),
                    "project_id": project_id,
                    "project": project_name or entry_data.get("project_name_config"),
                    "start_time": time_entry.get("timeInterval", {}).get("start"),
                }
            )
        else:
            event_project_id = time_entry.get("projectId") or entry_data.get("project_id")
            if project_filter and event_project_id and event_project_id != project_filter:
                _LOGGER.debug("Ignoring Clockify stop event for a different project: %s", event_project_id)
                return web.Response(text="Ignored - different project", status=200)

            entry_data.update(
                {
                    "is_running": False,
                    "description": None,
                    "project_id": None,
                    "project": None,
                    "start_time": None,
                }
            )

        # Notify switch and sensor entities to write updated state
        async_dispatcher_send(hass, get_update_signal(entry_id), entry_data)
        return web.Response(text="OK", status=200)

    return _handler