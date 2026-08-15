"""Config flow for the Clockify integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CLOCKIFY_API_BASE_URL,
    CONF_PROJECT_ID,
    CONF_PROJECT_NAME,
    CONF_STARTED_WEBHOOK_ID,
    CONF_STARTED_WEBHOOK_URL,
    CONF_STOPPED_WEBHOOK_ID,
    CONF_STOPPED_WEBHOOK_URL,
    CONF_USER_ID,
    CONF_WORKSPACE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ANY_PROJECT = ""


class ClockifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Clockify."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._config_data: dict[str, Any] | None = None
        self._workspaces: list[dict[str, Any]] = []
        self._projects: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                user_data, workspaces = await self._async_validate_credentials(user_input[CONF_API_KEY])
                self._workspaces = workspaces

                self._config_data = {
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_USER_ID: user_data.get("id"),
                }

                if len(workspaces) > 1:
                    return await self.async_step_workspace()

                self._config_data[CONF_WORKSPACE_ID] = workspaces[0].get("id")
                return await self.async_step_project()

            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("Unexpected exception during Clockify config flow setup")
                errors["base"] = "unknown"

        data_schema = vol.Schema({vol.Required(CONF_API_KEY): str})
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_workspace(self, user_input: dict[str, Any] | None = None):
        """Handle workspace selection step if user has multiple workspaces."""
        if user_input is not None and self._config_data:
            self._config_data[CONF_WORKSPACE_ID] = user_input[CONF_WORKSPACE_ID]
            return await self.async_step_project()

        workspace_options = {ws["id"]: ws["name"] for ws in self._workspaces}
        return self.async_show_form(
            step_id="workspace",
            data_schema=vol.Schema({vol.Required(CONF_WORKSPACE_ID): vol.In(workspace_options)}),
        )

    async def async_step_project(self, user_input: dict[str, Any] | None = None):
        """Handle project selection so a single Clockify account can add multiple instances."""
        errors: dict[str, str] = {}

        if user_input is not None and self._config_data:
            project_id = user_input.get(CONF_PROJECT_ID, ANY_PROJECT)
            project_name = next(
                (p.get("name") for p in self._projects if p.get("id") == project_id),
                None,
            )

            workspace_id = self._config_data[CONF_WORKSPACE_ID]
            user_id = self._config_data[CONF_USER_ID]
            await self.async_set_unique_id(f"{workspace_id}-{user_id}-{project_id or 'all'}")
            self._abort_if_unique_id_configured()

            self._config_data[CONF_PROJECT_ID] = project_id
            self._config_data[CONF_PROJECT_NAME] = project_name
            return await self.async_step_webhook_urls()

        try:
            self._projects = await self._async_fetch_projects(
                self._config_data[CONF_WORKSPACE_ID], self._config_data[CONF_API_KEY]
            )
        except CannotConnect:
            errors["base"] = "cannot_connect"
            self._projects = []

        project_options = {ANY_PROJECT: "Any running timer (no specific project)"}
        project_options.update({p["id"]: p["name"] for p in self._projects if p.get("id")})

        return self.async_show_form(
            step_id="project",
            data_schema=vol.Schema({vol.Required(CONF_PROJECT_ID, default=ANY_PROJECT): vol.In(project_options)}),
            errors=errors,
        )

    async def async_step_webhook_urls(self, user_input: dict[str, Any] | None = None):
        """Show generated webhook URLs to the user and finalize entry."""
        if user_input is not None:
            if not self._config_data:
                return self.async_abort(reason="unknown")

            # FIX: Correct persistent notification call
            persistent_notification.async_create(
                self.hass,
                title="Clockify Webhook Setup",
                message=(
                    "Copy these webhook URLs into **Clockify** "
                    "(`Preferences -> Advanced -> Webhooks`). If you track a specific "
                    "project, scope each webhook's trigger source to that project so "
                    "multiple instances don't cross-update each other:\n\n"
                    f"**Timer Started URL:**\n`{self._config_data[CONF_STARTED_WEBHOOK_URL]}`\n\n"
                    f"**Timer Stopped URL:**\n`{self._config_data[CONF_STOPPED_WEBHOOK_URL]}`"
                ),
                notification_id=f"clockify_webhooks_{self._config_data[CONF_WORKSPACE_ID]}_{self._config_data.get(CONF_PROJECT_ID) or 'all'}",
            )

            title = "Clockify" if not self._config_data.get(CONF_PROJECT_NAME) else f"Clockify ({self._config_data[CONF_PROJECT_NAME]})"
            return self.async_create_entry(title=title, data=self._config_data)

        if not self._config_data:
            return self.async_abort(reason="unknown")

        started_webhook_id, stopped_webhook_id = self._build_webhook_ids(self._config_data)
        started_url, stopped_url = self._build_webhook_urls(started_webhook_id, stopped_webhook_id)

        self._config_data[CONF_STARTED_WEBHOOK_ID] = started_webhook_id
        self._config_data[CONF_STOPPED_WEBHOOK_ID] = stopped_webhook_id
        self._config_data[CONF_STARTED_WEBHOOK_URL] = started_url
        self._config_data[CONF_STOPPED_WEBHOOK_URL] = stopped_url

        return self.async_show_form(
            step_id="webhook_urls",
            data_schema=vol.Schema({}),
            description_placeholders={"started_url": started_url, "stopped_url": stopped_url},
            errors={},
        )

    def _build_webhook_ids(self, config_data: dict[str, Any]) -> tuple[str, str]:
        """Create deterministic webhook IDs from config data."""
        seed = (
            f"{config_data.get(CONF_API_KEY, '')}:{config_data.get(CONF_WORKSPACE_ID, '')}:"
            f"{config_data.get(CONF_USER_ID, '')}:{config_data.get(CONF_PROJECT_ID, '')}"
        )
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"{digest}_timer_started", f"{digest}_timer_stopped"

    def _build_webhook_urls(self, started_webhook_id: str, stopped_webhook_id: str) -> tuple[str, str]:
        """Build display-only webhook URLs; the host is a placeholder for the user to fill in."""
        base_url = "https://INSERT_URL/"
        return f"{base_url}api/webhook/{started_webhook_id}", f"{base_url}api/webhook/{stopped_webhook_id}"

    async def _async_validate_credentials(self, api_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Validate provided API key and return user data + workspaces."""
        session = async_get_clientsession(self.hass)
        headers = {"X-Api-Key": api_key}

        try:
            async with asyncio.timeout(10):
                async with session.get(f"{CLOCKIFY_API_BASE_URL}/user", headers=headers) as response:
                    if response.status in (401, 403):
                        raise InvalidAuth
                    if response.status >= 400:
                        raise CannotConnect
                    user_data = await response.json()

                async with session.get(f"{CLOCKIFY_API_BASE_URL}/workspaces", headers=headers) as response:
                    if response.status in (401, 403):
                        raise InvalidAuth
                    if response.status >= 400:
                        raise CannotConnect
                    workspaces = await response.json()

        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Clockify connection error: %s", err)
            raise CannotConnect from err

        if not isinstance(workspaces, list) or not workspaces:
            raise CannotConnect

        return user_data, workspaces

    async def _async_fetch_projects(self, workspace_id: str, api_key: str) -> list[dict[str, Any]]:
        """Fetch the list of projects available on the given workspace."""
        session = async_get_clientsession(self.hass)
        headers = {"X-Api-Key": api_key}
        url = f"{CLOCKIFY_API_BASE_URL}/workspaces/{workspace_id}/projects"

        try:
            async with asyncio.timeout(10):
                async with session.get(url, headers=headers, params={"page-size": 200, "archived": "false"}) as response:
                    if response.status >= 400:
                        raise CannotConnect
                    projects = await response.json()
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Clockify connection error while fetching projects: %s", err)
            raise CannotConnect from err

        return projects if isinstance(projects, list) else []


class InvalidAuth(Exception):
    """Raised when credentials are invalid."""


class CannotConnect(Exception):
    """Raised when the Clockify API cannot be reached."""