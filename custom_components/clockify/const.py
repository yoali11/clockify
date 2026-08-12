"""Constants for the Clockify integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY

DOMAIN = "clockify"

# Configuration keys
CONF_WORKSPACE_ID = "workspace_id"
CONF_USER_ID = "user_id"
CONF_PROJECT_ID = "project_id"
CONF_PROJECT_NAME = "project_name"

# Webhook configuration keys
CONF_STARTED_WEBHOOK_ID = "started_webhook_id"
CONF_STOPPED_WEBHOOK_ID = "stopped_webhook_id"
CONF_STARTED_WEBHOOK_URL = "started_webhook_url"
CONF_STOPPED_WEBHOOK_URL = "stopped_webhook_url"

# Defaults
DEFAULT_NAME = "Clockify Timer"


def get_update_signal(entry_id: str) -> str:
    """Return the entry-scoped dispatcher signal used for entity updates."""
    return f"{DOMAIN}_{entry_id}_update"