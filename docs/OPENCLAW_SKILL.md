# OpenClaw Skill Integration

This project can be used as an OpenClaw-compatible skill backend.

It exposes a stable command-line interface (`roborock-cli`) that an agent can call as tool actions.

## Skill Scope

Recommended actions to expose:

- status and health: `status`, `consumables`, `clean_summary`
- core control: `start`, `stop`, `pause`, `dock`, `find`
- room workflows: `rooms`, `clean`
- diagnostics: `devices`, `raw`

Optional actions:

- camera: `snapshot`, `record`, `stream` (camera models only, beta)
- Telegram bot: `bot`

## Agent Safety Defaults

- Always use `--json` for machine parsing.
- Keep device selection explicit with `-d`.
- Bind camera stream to localhost by default:
  - `roborock-cli stream --host 127.0.0.1 --port 8554`
- Never return secrets from config (`rriot`, `local_key`, tokens) in agent responses.

## Suggested Action Mapping

Example intent-to-command mapping:

- `vacuum.status` -> `roborock-cli --json status`
- `vacuum.start` -> `roborock-cli --json start`
- `vacuum.stop` -> `roborock-cli --json stop`
- `vacuum.dock` -> `roborock-cli --json dock`
- `vacuum.find` -> `roborock-cli --json find`
- `vacuum.rooms.list` -> `roborock-cli --json rooms`
- `vacuum.rooms.clean` -> `roborock-cli --json clean "Kitchen" --repeat 1`

## Minimal Runtime Contract

The skill backend expects:

- valid local config at `~/.config/roborock-cli/config.json`
- or explicit config via `ROBOROCK_CONFIG`

Initial provisioning options:

- standard auth flow: `roborock-cli setup`
- Android fallback: `roborock-cli adb-setup ...`

## Notes

- This repository is an OpenClaw-compatible integration project, not OpenClaw core.
- Keep camera support marked as beta in user-facing agent responses.
