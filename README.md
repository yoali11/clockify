# Clockify – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

A [Home Assistant](https://www.home-assistant.io/) custom integration that connects to the [Clockify](https://clockify.me/) time-tracking API. Install it via [HACS](https://hacs.xyz/) for automatic updates.

---

## Features

| Sensor | Description |
|--------|-------------|
| **Active Timer** | `running` when a timer is active, `stopped` otherwise. Attributes include project, description, start time, and billable flag. |
| **Last Time Entry** | Description of the most recently completed time entry. Attributes include project, start time, duration, and billable flag. |

---

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations → Custom repositories**.
3. Add `https://github.com/yoali11/clockify` as a custom repository (category: *Integration*).
4. Search for **Clockify** and install it.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/clockify` directory into your HA `config/custom_components/` folder.
2. Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Clockify**.
3. Enter your **API Key** (found in Clockify under *Profile Settings → API*).
4. If you have multiple workspaces, select the one you want to monitor.

---

## Requirements

- Home Assistant 2023.1 or newer
- A [Clockify](https://clockify.me/) account with an API key

---

## License

[MIT](LICENSE)