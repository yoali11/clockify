# Clockify for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for [Clockify](https://clockify.me/) time tracking. Track your current timer status, start/stop time entries, and see your daily/weekly/monthly hours directly in Home Assistant.

## Features

- `switch` entity to start/stop the Clockify timer for a configured project
- `sensor` entities for timer status and hours logged today/this week/this month
- Real-time updates via Clockify webhooks

## Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. In HACS, go to **Integrations**, click the three-dot menu, choose **Custom repositories**, and add this repository URL with category **Integration** (only needed until this integration is available in the default HACS list).
3. Search for "Clockify" in HACS and install it.
4. Restart Home Assistant.

### Manual

1. Copy the `custom_components/clockify` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

Configuration is done via the UI:

1. Create a Clockify API key at [app.clockify.me/manage-api-keys](https://app.clockify.me/manage-api-keys) and copy it.
2. In Home Assistant, go to **Settings** → **Devices & Services** → **Add Integration**, search for "Clockify", and paste in the API key.
3. Select the workspace and project you want to track.
4. Home Assistant will generate two webhook URLs (one for timer started, one for timer stopped). Go to [app.clockify.me/webhooks](https://app.clockify.me/webhooks) and create two webhooks, pasting in the matching URL for each:
   - **Timer started (anyone)** → the "started" URL
   - **Timer stopped (anyone)** → the "stopped" URL

Webhooks let Clockify push timer changes to Home Assistant instantly instead of the integration having to poll the Clockify API on a schedule, which keeps API usage low and avoids hitting Clockify's rate limits, even on a free-tier.

## License

See [LICENSE](LICENSE).
