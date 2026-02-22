# Camera Livestream Guide

Stream live video from your Roborock vacuum's camera to a browser, VLC, file, or Telegram.

## Supported Models

Camera streaming requires a vacuum with a **user-accessible camera**:

| Model | Camera | Livestream |
|-------|--------|------------|
| S8 MaxV Ultra | ✅ | ✅ Supported |
| S8 Pro Ultra | ✅ | ✅ Supported |
| Qrevo MaxV | ✅ | ✅ Supported |
| Qrevo Curv | ✅ | ✅ Tested |
| Qrevo S | ✅ | ✅ Supported |
| **S8 (standard)** | ❌ | ❌ No camera |
| S7 / S6 series | ❌ | ❌ No camera |
| E / Q series | ❌ | ❌ No camera |

> **Note:** The standard Roborock S8 has an infrared obstacle sensor, NOT a user-accessible camera.

## Installation

Camera features require extra dependencies:

```bash
pip install roborock-cloud-cli[camera]

# Or install everything:
pip install roborock-cloud-cli[all]
```

## Camera Pattern Password

Your vacuum may require a **pattern password** for camera access. This is the numeric pattern you set in the Roborock app under:

**Settings → Home Security → Pattern Password**

Common patterns: `1234`, `0000`, `9876`, etc.

If you haven't set a pattern password, try without `--password` first.

## Commands

### 📸 Snapshot

Take a single photo:

```bash
roborock-cli snapshot
roborock-cli snapshot -o kitchen.jpg
roborock-cli snapshot --password 1234 --quality HD
```

### 🎬 Record Video

Record video to MP4:

```bash
roborock-cli record
roborock-cli record --duration 60 -o cleaning.mp4
roborock-cli record --password 1234 --quality SD
```

### 🎥 Live Stream (MJPEG)

Start an HTTP stream server:

```bash
roborock-cli stream
roborock-cli stream --port 9000
roborock-cli stream --host 0.0.0.0 --port 8554
```

Then open in browser or VLC:
- **Browser:** `http://localhost:8554/`
- **VLC:** `http://localhost:8554/stream`
- **OBS:** Add Browser source → `http://localhost:8554/`

### 📱 Telegram Snapshot

If running the Telegram bot:

```
/snapshot
```

The bot will capture a frame and send it as a photo.

## Streaming to External Services

### OBS Studio
1. Start the MJPEG stream: `roborock-cli stream`
2. In OBS: Add Source → Browser → URL: `http://localhost:8554/`

### YouTube / Twitch (via FFmpeg)
```bash
# Start MJPEG stream first
roborock-cli stream --port 8554 &

# Then pipe to RTMP
ffmpeg -i http://localhost:8554/stream -c:v libx264 -preset ultrafast \
  -f flv rtmp://live.twitch.tv/app/YOUR_STREAM_KEY
```

### Home Assistant
Use the MJPEG camera integration:
```yaml
camera:
  - platform: mjpeg
    name: Roborock Camera
    mjpeg_url: http://YOUR_IP:8554/stream
```

### Frigate / NVR
Add as a generic camera source:
```
http://YOUR_IP:8554/stream
```

## Troubleshooting

### "Failed to start camera preview"
- **Close the Roborock app** on your phone first (only one session at a time)
- Your model may not have a camera (see supported models above)
- Try with `--password` if you have a pattern set

### "Camera password authentication failed"
- Wrong pattern password — check in Roborock app → Home Security
- Too many failed attempts may temporarily lock camera access

### "WebRTC connection failed"
- Check your firewall allows outbound UDP traffic
- TURN server relay should handle NAT, but strict firewalls may block it
- Try `--quality SD` for lower bandwidth requirements

### Poor video quality
- Use `--quality HD` for better resolution
- MJPEG has compression artifacts; direct WebRTC (via the Python API) gives better quality
- Network latency affects stream smoothness

## Python API

For programmatic access:

```python
import asyncio
from roborock_cli.camera import RoborockCamera, CameraConfig
from roborock_cli.config import load_config

async def main():
    config = load_config()
    camera = RoborockCamera(config, CameraConfig(
        pattern_password="1234",
        quality="HD",
    ))

    await camera.connect()

    # Take a snapshot
    await camera.snapshot("photo.jpg")

    # Or record video
    await camera.record("video.mp4", duration=30)

    # Or start MJPEG stream
    # await camera.stream_mjpeg(port=8554)

    await camera.disconnect()

asyncio.run(main())
```

## Technical Details

The camera uses **WebRTC** with **MQTT-based signaling**:

1. `start_camera_preview` → initiates camera session
2. `get_turn_server` → TURN relay credentials for NAT traversal
3. `send_sdp_to_robot` / `get_device_sdp` → SDP offer/answer exchange
4. `send_ice_to_robot` / `get_device_ice` → ICE candidate exchange
5. WebRTC peer connection established → video + audio tracks

See [PROTOCOL.md](PROTOCOL.md) and the [python-roborock camera PR](https://github.com/Python-roborock/python-roborock/pull/764) for full protocol documentation.
