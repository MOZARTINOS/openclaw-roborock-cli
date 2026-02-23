# Changelog

## [0.4.0] - 2026-02-23

### Added

- Unified project positioning as both:
  - standalone CLI
  - OpenClaw-compatible agent skill backend
- Room workflow:
  - `rooms` discovery command
  - `clean <room...>` by name with `--repeat`
- `docs/OPENCLAW_SKILL.md` integration guide
- Test coverage for room mapping/resolution (`tests/test_rooms.py`)

### Changed

- Rebuilt `cli.py` with merged feature set:
  - `setup`, `adb-setup`, `devices`, room workflows, raw commands
  - JSON output support across major flows
  - Optional dependency handling for Telegram and camera extras
- Camera stream defaults now bind to `127.0.0.1` for safer local exposure
- Documentation refreshed for public/open-source clarity and security
- Packaging metadata updated to `0.4.0`

### Security and Repo Hygiene

- Removed internal-only `BRIEF.md` from tracked files
- Restored OSS community/security files:
  - `CONTRIBUTING.md`
  - `CODE_OF_CONDUCT.md`
  - `SECURITY.md`
  - PR template and issue templates
- Expanded ignore rules for sensitive/local artifacts

## [0.3.0] - 2026-02-23

### Added

- CLI stabilization for public release
- ADB extraction helpers and command integration
- Camera beta command set
- CI and initial test suite

## [0.2.0] - 2026-02-23

### Added

- Room-specific cleaning (initial implementation)
- Telegram room buttons

## [0.1.0] - 2026-02-22

### Added

- Initial public CLI implementation
