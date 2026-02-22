# OpenClaw Roborock CLI

[![CI](https://github.com/MOZARTINOS/OpenClaw-Roborock/actions/workflows/ci.yml/badge.svg)](https://github.com/MOZARTINOS/OpenClaw-Roborock/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

OpenClaw Roborock CLI is a Python command-line tool to control Roborock vacuums without the mobile app.

It connects to Roborock Cloud MQTT and supports terminal control, Telegram bot control, Android ADB fallback setup, and camera features for camera-equipped models.

## Preview

![Roborock control panel preview](assets/control-panel.png)

## Features

- Interactive setup (`roborock-cli setup`) using email verification.
- Core vacuum commands: start, stop, pause, dock, find, fan speed.
- Status, consumables, and cleaning summary output.
- Multi-device support with index selection (`-d`).
- `devices` command to list configured robots.
- Raw command mode for advanced/unsupported methods.
- JSON output mode (`--json`) for automation.
- Telegram bot control panel (optional dependency).
- Camera snapshot/record/MJPEG stream on camera models (optional dependency).
- Android ADB extraction stage via built-in `adb-setup`.

## Installation

Base CLI:

```bash
pip install roborock-cloud-cli
```

With Telegram support:

```bash
pip install roborock-cloud-cli[telegram]
```

With camera support:

```bash
pip install roborock-cloud-cli[camera]
```

Everything:

```bash
pip install roborock-cloud-cli[all]
```

From source:

```bash
git clone https://github.com/MOZARTINOS/OpenClaw-Roborock.git
cd OpenClaw-Roborock
pip install -e .
```

## Setup

Standard setup:

```bash
roborock-cli setup
```

Setup flow:
1. Discover account region.
2. Send email verification code.
3. Login and fetch cloud home data.
4. Save config to `~/.config/roborock-cli/config.json`.

You can override config location with:

```bash
export ROBOROCK_CONFIG=/path/to/config.json
```

### ADB Fallback (Built-in Stage)

If standard setup fails, run:

```bash
roborock-cli adb-setup --log-file roborock_log.txt --email you@example.com
```

Or with pre-extracted payload:

```bash
roborock-cli adb-setup --extracted-json roborock_extracted.json --email you@example.com
```

This command parses login payload (`FeatureCacheService->loadLoginResponse`), retrieves home/device data, and writes `config.json` directly.

Full guide: `docs/ADB_EXTRACTION.md`

## Usage

Basic control:

```bash
roborock-cli status
roborock-cli start
roborock-cli dock
roborock-cli consumables
```

Multi-device:

```bash
roborock-cli devices
roborock-cli -d 1 status
```

JSON output for scripts:

```bash
roborock-cli --json status
roborock-cli --json raw get_network_info
```

Raw command mode:

```bash
roborock-cli raw get_network_info
roborock-cli raw set_custom_mode '[102]'
```

## Telegram Bot

```bash
roborock-cli bot --token YOUR_BOT_TOKEN
```

Or with env var:

```bash
export TELEGRAM_BOT_TOKEN=your_token_here
roborock-cli bot
```

Restrict access:

```bash
roborock-cli bot --token YOUR_BOT_TOKEN --users 123456789,987654321
```

## Camera (Beta)

Camera commands are for camera-equipped models only (for example S8 MaxV / Qrevo camera variants):

```bash
roborock-cli snapshot -o photo.jpg
roborock-cli record --duration 30 -o clip.mp4
roborock-cli stream --port 8554
```

MJPEG endpoints:
- Browser: `http://localhost:8554/`
- Stream URL: `http://localhost:8554/stream`

Camera guide: `docs/CAMERA.md`

## Command Reference

| Command | Description |
| --- | --- |
| `setup` | Interactive first-time setup |
| `adb-setup` | Build config from Android ADB log/extracted payload |
| `devices` | List configured devices and indexes |
| `status` | Get current status |
| `start` | Start cleaning |
| `stop` | Stop cleaning |
| `pause` | Pause cleaning |
| `dock` | Return to charging dock |
| `find` | Make the robot beep |
| `fan_quiet` | Set fan to quiet mode |
| `fan_balanced` | Set fan to balanced mode |
| `fan_turbo` | Set fan to turbo mode |
| `fan_max` | Set fan to max mode |
| `consumables` | Show consumable wear and alerts |
| `clean_summary` | Show cleaning history summary |
| `raw <method> [json]` | Send raw Roborock command |
| `bot` | Start Telegram bot control panel |
| `snapshot` | Capture camera snapshot (camera models) |
| `record` | Record camera video (camera models) |
| `stream` | Start MJPEG camera stream (camera models) |

Global flags:

- `-d, --device <index>`: choose device index (default `0`).
- `--json`: print machine-readable JSON.
- `-v, --verbose`: enable debug logs.

## Security Notes

- Never commit `config.json`, tokens, or local keys.
- Never commit raw `adb logcat` captures or extracted payload JSON files.
- Rotate credentials if exposed.
- Redact logs before sharing publicly.

## Documentation

- Protocol details: `docs/PROTOCOL.md`
- Android credential extraction: `docs/ADB_EXTRACTION.md`
- Camera livestream and recording: `docs/CAMERA.md`

## Development

Install dev dependencies and run tests:

```bash
pip install -e .[dev]
pytest
```

Contribution guidelines: `CONTRIBUTING.md`

## License

MIT. See `LICENSE`.
