# 🤖 Roborock Cloud CLI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Control your Roborock vacuum from the terminal — no app needed.**

Roborock doesn't offer a desktop application. This CLI connects directly to the Roborock cloud via MQTT, giving you full control over your vacuum from any terminal.

```bash
$ roborock-cli status
📡 Get current status...
  State:      Charging
  Battery:    92%
  Fan speed:  Max
  Clean time: 51m 30s
  Clean area: 37.1 m²
  Water tank: Installed
  Mop:        Attached

$ roborock-cli start
📡 Start cleaning...
✅ OK
```

## ✨ Features

- 🔌 **No app required** — works entirely from the terminal
- 🔐 **Secure setup** — email verification, credentials stored locally with `600` permissions
- 🧹 **Full control** — start, stop, pause, dock, find, fan speed
- 📊 **Status monitoring** — battery, state, clean area, consumables
- 🏠 **Multi-device** — supports multiple vacuums on one account
- 🔧 **Raw commands** — send any Roborock command directly
- 📸 **Camera** — snapshot, record, MJPEG livestream (camera models)
- 📱 **ADB fallback** — extract credentials via Android Debug Bridge if needed

## 🚀 Quick Start

### Install

```bash
pip install roborock-cloud-cli
```

Or from source:

```bash
git clone https://github.com/MOZARTINOS/OpenClaw-Roborock.git
cd OpenClaw-Roborock
pip install -e .
```

### Setup

```bash
roborock-cli setup
```

This will:
1. Ask for your Roborock account email
2. Send a verification code
3. Log in and discover your devices
4. Save credentials to `~/.config/roborock-cli/config.json`

### Use

```bash
roborock-cli start          # Start cleaning
roborock-cli stop           # Stop
roborock-cli dock           # Return to dock
roborock-cli find           # Make it beep
roborock-cli status         # Check status
roborock-cli fan_turbo      # Set fan speed
```

## 📋 All Commands

| Command | Description |
|---------|-------------|
| `setup` | Interactive first-time setup |
| `status` | Get current status (battery, state, area) |
| `start` | Start cleaning |
| `stop` | Stop cleaning |
| `pause` | Pause cleaning |
| `dock` | Return to charging dock |
| `find` | Make the robot beep (locate it) |
| `fan_quiet` | Set fan to quiet mode |
| `fan_balanced` | Set fan to balanced mode |
| `fan_turbo` | Set fan to turbo mode |
| `fan_max` | Set fan to max mode |
| `consumables` | Show consumable wear status |
| `clean_summary` | Show cleaning history |
| `raw <method> [json]` | Send any raw command |

### Multi-device

If you have multiple Roborock devices:

```bash
roborock-cli -d 1 status    # Status of second device
roborock-cli -d 0 start     # Start first device (default)
```

### Raw Commands

Send any supported Roborock command:

```bash
roborock-cli raw get_network_info
roborock-cli raw set_custom_mode '[102]'
```

## 🤖 Telegram Bot

Control your vacuum with inline buttons directly in Telegram!

### Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Copy the bot token
3. Run:

```bash
roborock-cli bot --token YOUR_BOT_TOKEN
```

### Restrict access (recommended)

Only allow specific Telegram users to control the vacuum:

```bash
roborock-cli bot --token YOUR_BOT_TOKEN --users 123456789,987654321
```

Find your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot).

### Using environment variables

```bash
export TELEGRAM_BOT_TOKEN=your_token_here
roborock-cli bot
```

### Control Panel

Send `/panel` to your bot to get an interactive control panel:

```
🤖 Roborock S8 | 🔋 92% | 💤 Idle | 💨 Max

[▶️ Start]  [⏸ Pause]  [⏹ Stop]
[🏠 Dock]   [📍 Find]  [🔄 Status]
[🔇 Quiet]  [⚖️ Balanced] [💨 Turbo]
```

The panel auto-updates after each action — battery, state, and fan speed refresh in real-time.

## 📸 Camera Livestream (Beta)

For camera-equipped models (S8 MaxV, Qrevo, etc.) — stream live video!

```bash
# Install camera dependencies
pip install roborock-cloud-cli[camera]

# Take a snapshot
roborock-cli snapshot -o photo.jpg

# Record 30s video
roborock-cli record --duration 30

# Start live MJPEG stream (open http://localhost:8554 in browser)
roborock-cli stream
```

Works with **VLC, OBS, Home Assistant, Frigate**, or any MJPEG-compatible viewer.

👉 See [docs/CAMERA.md](docs/CAMERA.md) for full guide, supported models, and streaming setup.

> ⚠️ **Beta**: Camera support is based on reverse-engineered protocol documentation. 
> Tested on Qrevo Curv. Please report compatibility with other models!

## 🔐 Security

- Credentials are stored in `~/.config/roborock-cli/config.json` with `600` permissions (only you can read)
- No credentials are hardcoded or transmitted to third parties
- All communication uses TLS-encrypted MQTT
- Message payloads are encrypted with device-specific AES keys

**Never commit your `config.json` to git.** The `.gitignore` already excludes it.

## 🔧 Alternative Setup: ADB Extraction

If the email code flow doesn't work (2FA issues, rate limiting), you can extract credentials from the Roborock app on your Android phone:

👉 See [docs/ADB_EXTRACTION.md](docs/ADB_EXTRACTION.md)

## 🏗 How It Works

1. **Authentication**: Login via Roborock cloud API → receive `rriot` credentials
2. **MQTT**: Connect to Roborock's MQTT broker using derived credentials
3. **Commands**: Publish encrypted commands → receive encrypted responses
4. **Protocol**: Uses the V1 protocol from [python-roborock](https://github.com/Python-roborock/python-roborock)

👉 See [docs/PROTOCOL.md](docs/PROTOCOL.md) for technical details.

## 📱 Tested Devices

| Model | Status |
|-------|--------|
| Roborock S8 | ✅ Fully working |

Other Roborock models using the cloud API should work. Please open an issue to report compatibility.

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch
3. Test your changes
4. Open a PR

## 📄 License

MIT — see [LICENSE](LICENSE)

## 🙏 Credits

- [python-roborock](https://github.com/Python-roborock/python-roborock) — Protocol implementation
- Built with [OpenClaw](https://github.com/openclaw/openclaw) 🦞

---

**⭐ Star this repo if you find it useful!**
