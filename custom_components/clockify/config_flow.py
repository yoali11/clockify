"""Config flow for Clockify integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_API_KEY, CONF_WORKSPACE_ID, DOMAIN
from .coordinator import validate_and_get_workspaces

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


class ClockifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Clockify config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._api_key: str = ""
        self._workspaces: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step – ask for the API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                _, workspaces = await validate_and_get_workspaces(api_key)
                self._api_key = api_key
                self._workspaces = workspaces
            except aiohttp.ClientResponseError as err:
                if err.status in (401, 403):
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Clockify setup")
                errors["base"] = "unknown"
            else:
                if len(self._workspaces) == 1:
                    workspace_id = self._workspaces[0]["id"]
                    workspace_name = self._workspaces[0]["name"]
                    await self.async_set_unique_id(workspace_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=workspace_name,
                        data={
                            CONF_API_KEY: self._api_key,
                            CONF_WORKSPACE_ID: workspace_id,
                        },
                    )
                return await self.async_step_workspace()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_workspace(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick a workspace when there are multiple."""
        errors: dict[str, str] = {}

        workspace_options = {ws["id"]: ws["name"] for ws in self._workspaces}

        if user_input is not None:
            workspace_id = user_input[CONF_WORKSPACE_ID]
            workspace_name = workspace_options[workspace_id]
            await self.async_set_unique_id(workspace_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=workspace_name,
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_WORKSPACE_ID: workspace_id,
                },
            )

        return self.async_show_form(
            step_id="workspace",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WORKSPACE_ID): vol.In(workspace_options),
                }
            ),
            errors=errors,
        )
