#!/usr/bin/env python3
"""Roborock Cloud CLI - control your vacuum from the terminal.

Usage:
    roborock-cli setup                             Interactive first-time setup
    roborock-cli adb-setup                         Build config from Android ADB extraction
    roborock-cli health                            Readiness check (version/config/devices)
    roborock-cli devices                           List configured devices
    roborock-cli rooms                             Discover and list cleanable rooms
    roborock-cli clean Kitchen "Living Room"       Clean room(s) by name
    roborock-cli status                            Get vacuum status
    roborock-cli start|stop|pause|dock|find        Core vacuum commands
    roborock-cli consumables|clean_summary         Maintenance/history commands
    roborock-cli raw <method> [params_json]        Send a raw Roborock command
    roborock-cli bot --token <token>               Start Telegram bot (optional extra)
    roborock-cli snapshot|record|stream            Camera commands (optional extra)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .adb import (
    extract_payload_from_log,
    get_home_data_from_token,
    load_extracted_payload,
    redact_secret,
    save_extracted_payload,
)
from .auth import build_config, discover_region, get_home_data, login_with_code, request_code
from .commands import COMMANDS, format_clean_summary, format_consumables, format_status
from .config import load_config, save_config
from .mqtt import send_command


class CLIError(Exception):
    """Structured CLI error used for stable JSON error responses."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _emit_ok(result: Any | None = None, **extra: Any) -> None:
    payload: dict[str, Any] = {"ok": True}
    if result is not None:
        payload["result"] = result
    payload.update(extra)
    _print_json(payload)


def _emit_error(code: str, message: str, **extra: Any) -> None:
    payload: dict[str, Any] = {"ok": False, "error": code, "message": message}
    payload.update(extra)
    _print_json(payload)


def _classify_error(error: Exception) -> str:
    """Map exceptions/messages to stable JSON error codes."""
    message = str(error).lower()

    if isinstance(error, FileNotFoundError):
        return "config_missing"
    if "ambiguous room" in message:
        return "room_ambiguous"
    if "unknown room" in message or "no rooms matched" in message or "no room mapping available" in message:
        return "room_not_found"
    if "device index" in message or "index must" in message or "no configured devices" in message:
        return "device_not_found"
    if "offline" in message or "unreachable" in message or "timeout" in message:
        return "device_offline"
    if (
        "auth" in message
        or "unauthorized" in message
        or "forbidden" in message
        or "invalid verification code" in message
        or "credentials" in message
        or "login failed" in message
    ):
        return "auth_error"

    return "command_failed"


def _raise_config_missing(error: FileNotFoundError) -> None:
    raise CLIError("config_missing", str(error)) from error


def _load_config_or_raise() -> dict[str, Any]:
    try:
        return load_config()
    except FileNotFoundError as error:
        _raise_config_missing(error)


def get_devices(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return configured devices in a normalized list."""
    devices = config.get("devices")
    if isinstance(devices, list) and devices:
        return devices

    legacy = config.get("device")
    if isinstance(legacy, dict) and legacy:
        return [legacy]

    return []


def print_devices(config: dict[str, Any], json_output: bool = False) -> None:
    """Print configured devices."""
    devices = get_devices(config)
    if not devices:
        raise CLIError("device_not_found", "No devices configured. Run 'roborock-cli setup' first.")

    if json_output:
        _emit_ok(result=devices, devices=len(devices))
        return

    print(f"Configured devices ({len(devices)}):")
    for index, device in enumerate(devices):
        name = device.get("name", "Unknown")
        model = device.get("model", "unknown")
        online = device.get("online")
        status = "online" if online is True else "offline" if online is False else "unknown"
        print(f"  [{index}] {name} ({model}) - {status}")


def setup_interactive() -> None:
    """Interactive setup: login, discover devices, save config."""
    print("Roborock Cloud CLI - Setup\n")

    email = input("Enter your Roborock account email: ").strip()
    if not email:
        raise CLIError("command_failed", "Email is required")

    print(f"\nDiscovering region for {email}...")
    region = asyncio.run(discover_region(email))
    base_url = region["base_url"]
    print(f"Region: {region['country']} ({base_url})")

    print(f"\nSending verification code to {email}...")
    asyncio.run(request_code(email, base_url))
    print("Code sent. Check your email.")

    code = input("\nEnter verification code: ").strip()
    if not code:
        raise CLIError("command_failed", "Verification code is required")

    print("\nLogging in...")
    try:
        user_data = asyncio.run(login_with_code(email, code, base_url))
    except RuntimeError as error:
        raise CLIError("auth_error", str(error)) from error
    print(f"Logged in as {user_data.get('nickname', email)}")

    print("\nFetching devices...")
    home_data = asyncio.run(get_home_data(user_data))
    config = build_config(email, user_data, home_data)

    devices = config.get("devices", [])
    if not devices:
        raise CLIError("device_not_found", "No devices found. Check your Roborock app.")

    print(f"Found {len(devices)} device(s):")
    for index, device in enumerate(devices):
        status = "online" if device.get("online") else "offline"
        print(f"  [{index}] {device['name']} ({device.get('model', '?')}) - {status}")

    config_path = save_config(config)
    print(f"\nConfig saved to: {config_path}")
    print("  (permissions: 600 where supported)")

    # Best effort: discover segment-room mapping now so room cleaning works out of the box.
    try:
        from .rooms import discover_rooms, save_room_map

        room_map = asyncio.run(discover_rooms(config))
        if room_map:
            save_room_map(room_map, config_path)
            print(f"Discovered {len(room_map)} room segment(s).")
    except Exception as error:  # noqa: BLE001 - setup should continue if room discovery fails
        print(f"Room discovery skipped: {error}")
        print("You can retry later with: roborock-cli rooms")

    print("\nDone. Try: roborock-cli status")


def run_health(args: argparse.Namespace) -> None:
    """Health preflight command for agents/automation."""
    try:
        config = load_config()
    except FileNotFoundError as error:
        if args.json_output:
            _emit_error(
                "config_missing",
                str(error),
                version=__version__,
                config_exists=False,
            )
            return
        raise CLIError("config_missing", str(error)) from error

    devices = get_devices(config)
    if args.json_output:
        _emit_ok(
            version=__version__,
            config_exists=True,
            devices=len(devices),
        )
        return

    print(f"Version:       {__version__}")
    print("Config exists: yes")
    print(f"Devices:       {len(devices)}")


def run_adb_setup(args: argparse.Namespace) -> None:
    """Build configuration using extracted Android ADB login payload."""
    if args.log_file:
        try:
            extracted = extract_payload_from_log(Path(args.log_file))
        except RuntimeError as error:
            raise CLIError("command_failed", str(error)) from error
    else:
        try:
            extracted = load_extracted_payload(Path(args.extracted_json))
        except RuntimeError as error:
            raise CLIError("command_failed", str(error)) from error

    if args.output_extracted:
        output_path = save_extracted_payload(extracted, Path(args.output_extracted))
        if not args.json_output:
            print(f"Saved normalized extracted payload to: {output_path}")

    email = args.email
    if not email:
        if args.json_output:
            raise CLIError("command_failed", "--email is required when --json is used.")
        email = input("Enter your Roborock account email: ").strip()
        if not email:
            raise CLIError("command_failed", "Email is required")

    home_data: dict[str, Any] = {}
    if not args.skip_home_fetch:
        api_base = args.api_base or extracted["rriot"]["r"]["a"]
        if not args.json_output:
            print(f"Fetching home data from: {api_base}")
        try:
            home_data = asyncio.run(get_home_data_from_token(extracted["token"], api_base))
        except Exception as error:  # noqa: BLE001 - surface API details directly
            raise CLIError("auth_error", f"Failed to fetch home data: {error}") from error

    config = build_config(email, {"rriot": extracted["rriot"]}, home_data)
    config_path = save_config(config, Path(args.config_path).expanduser() if args.config_path else None)
    devices = config.get("devices", [])

    if args.json_output:
        _emit_ok(
            result={
                "config_path": str(config_path),
                "devices_found": len(devices),
                "email": email,
                "region": extracted.get("region"),
                "country": extracted.get("country"),
                "rruid": extracted.get("rruid"),
            }
        )
        return

    print("ADB setup completed.")
    print(f"  Email:       {email}")
    print(f"  Country:     {extracted.get('country', 'Unknown')}")
    print(f"  Region:      {extracted.get('region', 'Unknown')}")
    print(f"  RRUId:       {extracted.get('rruid', 'Unknown')}")
    print(f"  Token:       {redact_secret(extracted.get('token', ''))}")
    print(f"  Devices:     {len(devices)}")
    print(f"  Config path: {config_path}")
    if devices:
        print("  Device list:")
        for index, device in enumerate(devices):
            print(f"    [{index}] {device.get('name', 'Unknown')} ({device.get('model', 'unknown')})")
    else:
        print("  Warning: no devices discovered in home data.")
    print("\nRun: roborock-cli devices")


def run_rooms(args: argparse.Namespace) -> None:
    """Discover and list cleanable rooms."""
    config = _load_config_or_raise()
    from .rooms import discover_rooms, save_room_map

    try:
        room_map = asyncio.run(discover_rooms(config, device_index=args.device))
    except Exception as error:  # noqa: BLE001 - show remote/API details
        raise CLIError(_classify_error(error), f"Room discovery failed: {error}") from error

    save_room_map(room_map)

    if args.json_output:
        _emit_ok(
            result={
                "count": len(room_map),
                "rooms": [{"segment_id": segment_id, "name": name} for segment_id, name in sorted(room_map.items())],
            }
        )
        return

    if not room_map:
        print("No rooms discovered for this device/map.")
        return

    print(f"Rooms discovered: {len(room_map)}")
    print(f"  {'ID':>4}  Room Name")
    print(f"  {'-' * 4}  {'-' * 20}")
    for segment_id, name in sorted(room_map.items()):
        print(f"  {segment_id:>4}  {name}")

    first = next(iter(room_map.values()))
    print(f"\nClean one room: roborock-cli clean \"{first}\"")


def run_clean(args: argparse.Namespace) -> None:
    """Clean one or more rooms by human-friendly names."""
    config = _load_config_or_raise()
    from .rooms import clean_rooms, discover_rooms, load_room_map, resolve_room_names, save_room_map

    room_map = load_room_map(config)
    if not room_map:
        try:
            room_map = asyncio.run(discover_rooms(config, device_index=args.device))
            if room_map:
                save_room_map(room_map)
        except Exception as error:  # noqa: BLE001 - show actionable failure
            raise CLIError(_classify_error(error), f"Room discovery failed: {error}") from error

    if not room_map:
        raise CLIError("room_not_found", "No room mapping available. Run 'roborock-cli rooms' first.")

    try:
        segment_ids = resolve_room_names(room_map, args.rooms)
    except ValueError as error:
        text = str(error)
        if "Ambiguous room" in text:
            raise CLIError("room_ambiguous", text) from error
        raise CLIError("room_not_found", text) from error

    room_names = [room_map[segment_id] for segment_id in segment_ids]

    try:
        result = asyncio.run(clean_rooms(config, segment_ids, repeat=args.repeat, device_index=args.device))
    except Exception as error:  # noqa: BLE001 - show device command failure
        raise CLIError(_classify_error(error), f"Failed to start room cleaning: {error}") from error

    if args.json_output:
        _emit_ok(
            result={
                "rooms": room_names,
                "segment_ids": segment_ids,
                "repeat": args.repeat,
                "result": result,
            }
        )
        return

    repeat_suffix = f" x{args.repeat}" if args.repeat > 1 else ""
    print(f"Cleaning rooms: {', '.join(room_names)}{repeat_suffix}")
    if result == ["ok"]:
        print("Started.")
    else:
        print(f"Result: {result}")


def run_bot(args: argparse.Namespace) -> None:
    """Start the Telegram bot process."""
    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise CLIError(
            "command_failed",
            "Telegram bot token is required. Use --token or set TELEGRAM_BOT_TOKEN.",
        )

    config = _load_config_or_raise()

    allowed_users: list[int] | None = None
    if args.users:
        try:
            allowed_users = [int(user_id.strip()) for user_id in args.users.split(",") if user_id.strip()]
        except ValueError as error:
            raise CLIError(
                "command_failed",
                "--users must be a comma-separated list of numeric Telegram user IDs.",
            ) from error

        if not allowed_users:
            raise CLIError("command_failed", "--users was provided but no valid user IDs were found.")

        print(f"Restricted to Telegram user IDs: {allowed_users}")

    try:
        from .telegram_bot import start_bot
    except ModuleNotFoundError as error:
        raise CLIError(
            "command_failed",
            "Telegram dependencies are not installed. Install with: pip install roborock-cloud-cli[telegram]",
        ) from error

    start_bot(token, config, allowed_users, camera_password=args.camera_password or "")


def run_camera(args: argparse.Namespace) -> None:
    """Run camera commands (snapshot, record, stream)."""
    config = _load_config_or_raise()

    try:
        from .camera import camera_record, camera_snapshot, camera_stream
    except ModuleNotFoundError as error:
        raise CLIError(
            "command_failed",
            "Camera dependencies are not installed. Install with: pip install roborock-cloud-cli[camera]",
        ) from error

    try:
        if args.command == "snapshot":
            path = asyncio.run(
                camera_snapshot(
                    config,
                    output=args.output,
                    password=args.password,
                    quality=args.quality,
                    device_index=args.device,
                )
            )
            if args.json_output:
                _emit_ok(result={"output": path, "beta_warning": "camera_commands_are_beta"})
            else:
                print(f"Saved: {path}")

        elif args.command == "record":
            path = asyncio.run(
                camera_record(
                    config,
                    output=args.output,
                    duration=args.duration,
                    password=args.password,
                    quality=args.quality,
                    device_index=args.device,
                )
            )
            if args.json_output:
                _emit_ok(
                    result={
                        "output": path,
                        "duration": args.duration,
                        "beta_warning": "camera_commands_are_beta",
                    }
                )
            else:
                print(f"Saved: {path}")

        elif args.command == "stream":
            if not args.json_output:
                print("Camera commands are beta.")
                print(f"Starting stream on http://{args.host}:{args.port}/")
            asyncio.run(
                camera_stream(
                    config,
                    host=args.host,
                    port=args.port,
                    password=args.password,
                    quality=args.quality,
                    device_index=args.device,
                )
            )

    except RuntimeError as error:
        raise CLIError(_classify_error(error), str(error)) from error
    except KeyboardInterrupt:
        print("\nStopped")


def run_command(args: argparse.Namespace) -> None:
    """Execute non-room command flows."""
    if args.command == "health":
        run_health(args)
        return

    config = _load_config_or_raise()
    command_name = args.command

    if command_name == "devices":
        print_devices(config, json_output=args.json_output)
        return

    if command_name == "raw":
        method = args.method
        if args.params:
            try:
                params = json.loads(args.params)
            except json.JSONDecodeError as error:
                raise CLIError("command_failed", f"Invalid JSON params: {error.msg} (pos {error.pos})") from error
        else:
            params = None

        try:
            result = asyncio.run(send_command(config, method, params=params, device_index=args.device))
        except Exception as error:  # noqa: BLE001 - classify connection/auth/device failures
            raise CLIError(_classify_error(error), f"Command failed: {error}") from error

        if args.json_output:
            _emit_ok(result=result)
            return

        if isinstance(result, (dict, list)):
            _print_json(result)
        else:
            print(result)
        return

    if command_name not in COMMANDS:
        raise CLIError("command_failed", f"Unknown command: {command_name}")

    method, params, description = COMMANDS[command_name]
    if not args.json_output:
        print(f"{description}...")

    try:
        result = asyncio.run(send_command(config, method, params=params, device_index=args.device))
    except Exception as error:  # noqa: BLE001 - keep remote/API errors visible
        raise CLIError(_classify_error(error), f"Command failed: {error}") from error

    if args.json_output:
        _emit_ok(result=result)
        return

    if command_name == "status":
        print(format_status(result))
    elif command_name == "consumables":
        print(format_consumables(result))
    elif command_name == "clean_summary":
        print(format_clean_summary(result))
    elif isinstance(result, (dict, list)):
        if result == ["ok"]:
            print("OK")
        else:
            _print_json(result)
    else:
        print(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="roborock-cli",
        description="Control your Roborock vacuum from the terminal",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-d", "--device", type=int, default=0, help="Device index (default: 0)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output machine-readable JSON")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Interactive first-time setup")
    subparsers.add_parser("health", help="Health preflight check")

    adb_setup_parser = subparsers.add_parser(
        "adb-setup",
        help="Build config from Android ADB log/extracted payload",
    )
    adb_source_group = adb_setup_parser.add_mutually_exclusive_group(required=True)
    adb_source_group.add_argument(
        "--log-file",
        help="Path to adb logcat capture file (contains FeatureCacheService->loadLoginResponse)",
    )
    adb_source_group.add_argument(
        "--extracted-json",
        help="Path to extracted payload JSON (token/rriot) from previous extraction",
    )
    adb_setup_parser.add_argument("--email", help="Roborock account email to store in config")
    adb_setup_parser.add_argument(
        "--api-base",
        help="Override API base URL for getHomeDetail (default: extracted rriot.r.a)",
    )
    adb_setup_parser.add_argument(
        "--skip-home-fetch",
        action="store_true",
        help="Skip cloud home-data fetch (config will contain zero devices)",
    )
    adb_setup_parser.add_argument(
        "--output-extracted",
        help="Optional path to save normalized extracted payload JSON",
    )
    adb_setup_parser.add_argument(
        "--config-path",
        help="Optional explicit config output path (default: ROBOROCK_CONFIG/XDG path)",
    )

    subparsers.add_parser("devices", help="List configured devices")
    subparsers.add_parser("rooms", help="Discover and list room segments")

    clean_parser = subparsers.add_parser("clean", help="Clean room(s) by name")
    clean_parser.add_argument("rooms", nargs="+", help="Room name(s) to clean (partial match is supported)")
    clean_parser.add_argument("--repeat", type=int, default=1, choices=[1, 2, 3], help="Cleaning passes (1-3)")

    for command_name, (_, _, description) in COMMANDS.items():
        subparsers.add_parser(command_name, help=description)

    raw_parser = subparsers.add_parser("raw", help="Send a raw command")
    raw_parser.add_argument("method", help="Command method name")
    raw_parser.add_argument("params", nargs="?", help="JSON params")

    bot_parser = subparsers.add_parser("bot", help="Start Telegram bot control panel")
    bot_parser.add_argument("--token", help="Telegram bot token (or set TELEGRAM_BOT_TOKEN env)")
    bot_parser.add_argument("--users", help="Comma-separated allowed Telegram user IDs (optional)")
    bot_parser.add_argument(
        "--camera-password",
        default="",
        help="Optional camera pattern password for /snapshot command",
    )

    snap_parser = subparsers.add_parser("snapshot", help="Take a camera snapshot (camera models only)")
    snap_parser.add_argument("-o", "--output", default="snapshot.jpg", help="Output file (default: snapshot.jpg)")
    snap_parser.add_argument("--password", default="", help="Camera pattern password")
    snap_parser.add_argument("--quality", default="HD", choices=["HD", "SD"], help="Video quality")

    rec_parser = subparsers.add_parser("record", help="Record camera video (camera models only)")
    rec_parser.add_argument("-o", "--output", default="recording.mp4", help="Output file (default: recording.mp4)")
    rec_parser.add_argument("--duration", type=int, default=30, help="Duration in seconds (default: 30)")
    rec_parser.add_argument("--password", default="", help="Camera pattern password")
    rec_parser.add_argument("--quality", default="HD", choices=["HD", "SD"], help="Video quality")

    stream_parser = subparsers.add_parser("stream", help="Start MJPEG camera stream (camera models only)")
    stream_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    stream_parser.add_argument("--port", type=int, default=8554, help="Port (default: 8554)")
    stream_parser.add_argument("--password", default="", help="Camera pattern password")
    stream_parser.add_argument("--quality", default="HD", choices=["HD", "SD"], help="Video quality")

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    if not args.command:
        parser.print_help()
        raise SystemExit(1)

    try:
        if args.command == "setup":
            setup_interactive()
        elif args.command == "adb-setup":
            run_adb_setup(args)
        elif args.command == "rooms":
            run_rooms(args)
        elif args.command == "clean":
            run_clean(args)
        elif args.command == "bot":
            run_bot(args)
        elif args.command in ("snapshot", "record", "stream"):
            run_camera(args)
        else:
            run_command(args)
    except CLIError as error:
        if args.json_output:
            _emit_error(error.code, error.message, **error.extra)
        else:
            print(f"Error: {error.message}")
        raise SystemExit(1) from error
    except Exception as error:  # noqa: BLE001 - final safety net
        if args.json_output:
            _emit_error("command_failed", str(error))
        else:
            print(f"Error: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
