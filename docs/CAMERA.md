# Camera Guide (Beta)

Use this guide for Roborock models with a user-accessible camera.

Disclaimer:
- Camera support is beta.
- Behavior can vary by model, region, firmware, and app version.
- Community testing is welcome. Please report model, firmware, command, and redacted logs.

## Supported Scope

Camera commands are intended for camera-capable variants (for example MaxV/Qrevo camera models).

Known limitation:
- Standard Roborock S8 does not provide a user-accessible camera feed.

## Install Camera Dependencies

```bash
pip install roborock-cloud-cli[camera]
```

Or all extras:

```bash
pip install roborock-cloud-cli[all]
```

## Camera Password

If your model requires a camera pattern password, pass it with `--password`.

Examples:

```bash
roborock-cli snapshot --password 1234
roborock-cli record --password 1234 --duration 30
```

## Commands

Snapshot:

```bash
roborock-cli snapshot -o photo.jpg
```

Record video:

```bash
roborock-cli record --duration 30 -o clip.mp4
```

Start MJPEG stream (safe local default):

```bash
roborock-cli stream --host 127.0.0.1 --port 8554
```

Stream URLs:

- Browser: `http://127.0.0.1:8554/`
- MJPEG: `http://127.0.0.1:8554/stream`

LAN sharing (only if required):

```bash
roborock-cli stream --host 0.0.0.0 --port 8554
```

## Telegram Snapshot

If bot mode is active:

```text
/snapshot
```

## Troubleshooting

`Failed to start camera preview`:
- close Roborock app on phone (single active session limit)
- verify model supports camera preview
- retry with correct `--password` if set

`Camera password authentication failed`:
- verify app pattern password
- wait and retry if too many attempts were made

`WebRTC connection failed`:
- check outbound network/firewall rules
- try lower quality (`--quality SD`)

Poor video quality:
- use `--quality HD`
- expect compression artifacts in MJPEG mode

## Protocol Notes

Camera signaling uses WebRTC + MQTT commands:

- `start_camera_preview`
- `get_turn_server`
- `send_sdp_to_robot` / `get_device_sdp`
- `send_ice_to_robot` / `get_device_ice`

See also: `docs/PROTOCOL.md`
