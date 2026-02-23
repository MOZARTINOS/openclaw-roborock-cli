---
name: roborock
description: Control Roborock vacuum cleaners via cloud MQTT. Use when the user asks to start/stop cleaning, check vacuum status, clean specific rooms by name, find the robot, adjust fan speed, or view consumable/cleaning history.
---

# Roborock Vacuum Control

## Prerequisites

Config must exist at `~/.config/roborock-cli/config.json`.
If missing, run setup first: `roborock-cli setup` or `roborock-cli adb-setup`.

Check with: `roborock-cli --json health`

If response includes `{"ok": false, "error": "config_missing"}` then run setup before proceeding.

## Command Rules

- Always use `--json` for machine-readable output.
- Parse `ok: false` responses and surface `message` to the user.
- Never expose `rriot`, `local_key`, or `token` values in responses.
- Default to device index `0` unless user specifies another device.

## Intent To Command Mapping

| User intent | Command |
| --- | --- |
| "status / what is vacuum doing" | `roborock-cli --json status` |
| "start cleaning / vacuum everything" | `roborock-cli --json start` |
| "stop" | `roborock-cli --json stop` |
| "pause" | `roborock-cli --json pause` |
| "go home / return to dock / charge" | `roborock-cli --json dock` |
| "find / where is the robot / beep" | `roborock-cli --json find` |
| "clean [room name]" | `roborock-cli --json clean "Kitchen"` |
| "clean [multiple rooms]" | `roborock-cli --json clean "Kitchen" "Bedroom"` |
| "deep clean [room]" | `roborock-cli --json clean "Kitchen" --repeat 2` |
| "list rooms / what rooms are there" | `roborock-cli --json rooms` |
| "quiet / silent mode" | `roborock-cli --json fan_quiet` |
| "balanced / normal speed" | `roborock-cli --json fan_balanced` |
| "turbo / stronger" | `roborock-cli --json fan_turbo` |
| "max power" | `roborock-cli --json fan_max` |
| "consumables / brushes / filter" | `roborock-cli --json consumables` |
| "cleaning history / last clean" | `roborock-cli --json clean_summary` |
| "list devices" | `roborock-cli --json devices` |
| "preflight check" | `roborock-cli --json health` |

## Room Name Handling

Room names are fetched from the Roborock app.
Partial matching is supported (`"kit"` matches `"Kitchen"`).
If ambiguous, ask the user to clarify.

Before cleaning by room, if room map is unknown, run:
`roborock-cli --json rooms`

## Error Handling

When `--json` is used, errors return:

`{"ok": false, "error": "error_code", "message": "..."}`

| error code | action |
| --- | --- |
| `config_missing` | Tell user to run `roborock-cli setup` |
| `device_offline` | Tell user the vacuum is offline/unreachable |
| `auth_error` | Tell user credentials may have expired, re-run setup |
| `device_not_found` | Tell user to check device index and run `roborock-cli --json devices` |
| `room_not_found` | Tell user to refresh/list rooms and retry with exact room name |
| `room_ambiguous` | Ask user to clarify the exact room name |
| `command_failed` | Surface the `message` field to the user |

## Safety Rules

- Do not start cleaning if the user is only asking for status.
- Camera commands (`snapshot`, `record`, `stream`) are beta; warn user before running.
- Never share config file contents in responses.
