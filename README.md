# Clockify for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for [Clockify](https://clockify.me/) time tracking. Track your current timer status, start/stop time entries, and see your daily/weekly/monthly hours directly in Home Assistant.

## Features

- `switch` entity to start/stop the Clockify timer for a configured project
- `sensor` entities for timer status and hours logged today/this week/this month
- Real-time updates via Clockify webhooks

## Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. Search for "Clockify" in HACS and install it.
3. Restart Home Assistant.

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

   The URLs are built from the external URL set in Home Assistant under **Settings** → **System** → **Network**, since Clockify has to reach Home Assistant from the internet. If no external URL is configured, the URLs start with `https://INSERT_URL/`; replace that part with your Home Assistant's public address before pasting them into Clockify.

Webhooks let Clockify push timer changes to Home Assistant instantly instead of the integration having to poll the Clockify API on a schedule, which keeps API usage low and avoids hitting Clockify's rate limits, even on a free-tier.

## Entities

Each configured project gets a device named `Clockify - <project>` with these entities (shown for a project called "My Project"):

| Entity | Description |
| --- | --- |
| `switch.clockify_my_project_timer` | Start/stop the Clockify timer for the project |
| `sensor.clockify_my_project_timer_status` | `Running` or `Idle` |
| `sensor.clockify_my_project_hours_today` | Hours logged today, in decimal hours (e.g. `3.25`) |
| `sensor.clockify_my_project_hours_this_week` | Hours logged this week |
| `sensor.clockify_my_project_hours_this_month` | Hours logged this month |
| `sensor.clockify_my_project_hours_this_year` | Hours logged this year |

The hours sensors refresh immediately when a timer starts or stops, and otherwise on a schedule: today every 5 minutes, this week every 15 minutes, this month every 30 minutes and this year every hour. Longer periods need more report requests (the year is split into ~10), so they are polled less often to stay within the rate limit.

## Examples

Replace `my_project`, `your_phone`, `person.you` and `zone.work` with your own entities.

### Live timer notification on your phone

Shows a notification with a running stopwatch while the timer is on, starting from the hours already logged today, plus a second notification with a **Stop timer** button. The stopwatch ticks on the device, so Home Assistant sends no repeated updates. Requires the Home Assistant Companion app on a version that supports live update notifications.

```yaml
alias: "Clockify: Live timer notification"
triggers:
  - trigger: state
    entity_id: switch.clockify_my_project_timer
    to: "on"
    # Give the hours sensor a moment to refresh after the timer starts
    for:
      seconds: 10
    id: start
  - trigger: state
    entity_id: switch.clockify_my_project_timer
    to: "off"
    id: stop
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: clockify-stop-timer
    id: action-stop
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: start
        sequence:
          - variables:
              elapsed_seconds: >-
                {{ (states('sensor.clockify_my_project_hours_today') | float(0) * 3600) | int }}
          - action: notify.mobile_app_your_phone
            data:
              title: Clockify — My Project
              message: "Today: {{ states('sensor.clockify_my_project_hours_today') }} h"
              data:
                tag: clockify_timer_activity
                live_update: true
                chronometer: true
                when: "{{ -1 * elapsed_seconds }}"
                when_relative: true
                notification_icon: mdi:timer-play-outline
                notification_icon_color: "#03A9F4"
                color: "#03A9F4"
          # Live notifications can't show action buttons, so the stop button gets its own notification
          - action: notify.mobile_app_your_phone
            data:
              title: Clockify
              message: The timer is running.
              data:
                tag: clockify_timer_active
                actions:
                  - action: clockify-stop-timer
                    title: Stop timer
      - conditions:
          - condition: trigger
            id: stop
        sequence:
          - action: notify.mobile_app_your_phone
            data:
              message: clear_notification
              data:
                tag: clockify_timer_activity
          - action: notify.mobile_app_your_phone
            data:
              message: clear_notification
              data:
                tag: clockify_timer_active
      - conditions:
          - condition: trigger
            id: action-stop
        sequence:
          - action: switch.turn_off
            target:
              entity_id: switch.clockify_my_project_timer
mode: queued
max: 10
```

### Start and stop the timer when you arrive at and leave work

Starts the timer two minutes after you enter the work zone (so driving past doesn't count) and stops it when you leave, then sends you the hours logged today.

```yaml
alias: "Clockify: Track time at work"
triggers:
  - trigger: zone
    entity_id: person.you
    zone: zone.work
    event: enter
    id: enter
  - trigger: zone
    entity_id: person.you
    zone: zone.work
    event: leave
    id: leave
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: enter
        sequence:
          - delay:
              minutes: 2
          # Skip if you already left again during the delay
          - condition: zone
            entity_id: person.you
            zone: zone.work
          - action: switch.turn_on
            target:
              entity_id: switch.clockify_my_project_timer
      - conditions:
          - condition: trigger
            id: leave
        sequence:
          - action: switch.turn_off
            target:
              entity_id: switch.clockify_my_project_timer
          - action: notify.mobile_app_your_phone
            data:
              title: Clockify stopped
              message: >-
                You worked {{ states('sensor.clockify_my_project_hours_today') }} hours today.
mode: restart
```

## License

See [LICENSE](LICENSE).
