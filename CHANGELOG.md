# Changelog

## [0.2.0] — 2026-02-23

### Added
- **Room cleaning** — clean specific rooms by name (`roborock-cli clean Kitchen`)
- **Room discovery** — auto-discover rooms from cloud + device mapping (`roborock-cli rooms`)
- **Partial name matching** — `clean kit` matches "Kitchen"
- **Multi-room cleaning** — `clean Kitchen Bedroom Office` in one command
- **Repeat passes** — `clean Kitchen --repeat 2` for deep cleaning
- **Telegram room buttons** — control panel now includes room-specific clean buttons
- `/rooms` Telegram command — refresh room list from cloud
- Room names auto-fetched from Roborock app via cloud API (Hawk auth)
- `rooms.py` module — room resolution, caching, segment cleaning
- `rooms` and `maps` commands in CLI
- Room emoji auto-detection based on room name

### Changed
- Setup now auto-discovers rooms and saves segment mapping
- Telegram bot panel includes "── Rooms ──" separator with room buttons
- Config format extended with `rooms` (cloud IDs → names) and `room_segments` (segment IDs → names)
- Auth module now uses Hawk authentication for cloud API (room/home data)
- Version bumped to 0.2.0

### Fixed
- Improved `get_home_data` to use correct IoT endpoint for home ID discovery

## [0.1.0] — 2026-02-22

### Added
- Initial release
- Cloud authentication via email verification code
- MQTT control: start, stop, pause, dock, find, fan speed
- Status monitoring with human-readable output
- Consumable tracking
- Multi-device support
- Raw command mode
- Interactive setup wizard
- Telegram bot with inline button control panel
- Camera support (snapshot, record, MJPEG stream) — beta
- ADB credential extraction guide
- Protocol documentation
