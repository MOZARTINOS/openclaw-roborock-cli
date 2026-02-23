# Roborock Cloud Protocol Notes

This document summarizes the protocol flow used by `openclaw-roborock-cli`.

## High-Level Architecture

```text
CLI / Agent Skill -> Roborock Cloud API (auth + home data) -> MQTT (TLS) -> Robot
```

## Authentication Flow

1. Discover region using `getUrlByEmail`.
2. Request email verification code.
3. Login via `loginWithCode`.
4. Receive `rriot` credentials and token.
5. Build MQTT session credentials via `python-roborock`.

ADB fallback (`adb-setup`) can bootstrap the same config from Android app logs.

## MQTT Command Path

- Commands are sent through the V1 RPC channel from `python-roborock`.
- Typical commands include:
  - `app_start`, `app_stop`, `app_pause`, `app_charge`
  - `get_status`, `get_consumable`, `get_clean_summary`
  - `set_custom_mode`
  - `app_segment_clean`
  - `get_room_mapping`

## Room Cleaning Model

Room cleaning combines two sources:

1. Cloud room names (`rooms` in home payload): `cloud_room_id -> room_name`
2. Device segment mapping (`get_room_mapping`): `segment_id -> cloud_room_id`

Resulting runtime map:

```text
segment_id -> room_name
```

`clean <room...>` resolves names to segment IDs and sends `app_segment_clean`.

## Camera Signaling Model (Beta)

Camera path uses WebRTC signaling over MQTT commands:

- `start_camera_preview`
- `get_turn_server`
- SDP offer/answer exchange
- ICE candidate exchange

The implementation is intentionally marked beta because compatibility can change by model and firmware.

## Security Notes

- Treat `rriot`, token, and `local_key` as secrets.
- Do not commit raw ADB captures or extracted payloads.
- Prefer localhost camera stream binding unless remote access is required.

## Dependencies

Protocol implementation relies on:

- `python-roborock`
- `aiohttp`
- optional: `python-telegram-bot`, `aiortc`, `av`
