#!/usr/bin/env python3
"""Roborock Cloud CLI - control your vacuum from the terminal.

Usage:
    roborock-cli setup              Interactive first-time setup
    roborock-cli adb-setup          Build config from Android ADB extraction
    roborock-cli devices            List configured devices
    roborock-cli status             Get vacuum status
    roborock-cli start              Start cleaning
    roborock-cli stop               Stop cleaning
    roborock-cli pause              Pause cleaning
    roborock-cli dock               Return to dock
    roborock-cli find               Make the robot beep
    roborock-cli fan_quiet          Set fan to quiet mode
    roborock-cli fan_balanced       Set fan to balanced mode
    roborock-cli fan_turbo          Set fan to turbo mode
    roborock-cli fan_max            Set fan to max mode
    roborock-cli consumables        Show consumable status
    roborock-cli clean_summary      Show cleaning history
    roborock-cli raw <method> [params_json]   Send raw command
    roborock-cli bot --token <token>          Start Telegram bot
    roborock-cli snapshot                          Take camera snapshot (camera models)
    roborock-cli record                            Record camera video (camera models)
    roborock-cli stream                            Start MJPEG stream (camera models)
"""

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
        raise RuntimeError("No devices configured. Run 'roborock-cli setup' first.")

    if json_output:
        print(json.dumps(devices, indent=2, ensure_ascii=False))
        return

    print(f"Configured devices ({len(devices)}):")
    for i, dev in enumerate(devices):
        name = dev.get("name", "Unknown")
        model = dev.get("model", "unknown")
        online = dev.get("online")
        if online is True:
            status = "online"
        elif online is False:
            status = "offline"
        else:
            status = "unknown"
        print(f"  [{i}] {name} ({model}) - {status}")


def setup_interactive() -> None:
    """Interactive setup: login, discover devices, save config."""
    print("Roborock Cloud CLI - Setup\n")

    email = input("Enter your Roborock account email: ").strip()
    if not email:
        print("Error: email is required")
        sys.exit(1)

    print(f"\nDiscovering region for {email}...")
    region = asyncio.run(discover_region(email))
    base_url = region["base_url"]
    print(f"Region: {region['country']} ({base_url})")

    print(f"\nSending verification code to {email}...")
    asyncio.run(request_code(email, base_url))
    print("Code sent. Check your email.")

    code = input("\nEnter verification code: ").strip()
    if not code:
        print("Error: verification code is required")
        sys.exit(1)

    print("\nLogging in...")
    try:
        user_data = asyncio.run(login_with_code(email, code, base_url))
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    print(f"Logged in as {user_data.get('nickname', email)}")

    print("\nFetching devices...")
    home_data = asyncio.run(get_home_data(user_data))
    config = build_config(email, user_data, home_data)

    devices = config.get("devices", [])
    if not devices:
        print("Warning: no devices found. Check your Roborock app.")
        sys.exit(1)

    print(f"Found {len(devices)} device(s):")
    for i, dev in enumerate(devices):
        status = "online" if dev.get("online") else "offline"
        print(f"   [{i}] {dev['name']} ({dev.get('model', '?')}) - {status}")

    config_path = save_config(config)
    print(f"\nConfig saved to: {config_path}")
    print("   (permissions: 600 - only you can read it)")
    print("\nDone. Try: roborock-cli status")


def run_adb_setup(args: argparse.Namespace) -> None:
    """Build configuration using extracted Android ADB login payload."""
    if args.log_file:
        try:
            extracted = extract_payload_from_log(Path(args.log_file))
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        try:
            extracted = load_extracted_payload(Path(args.extracted_json))
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)

    if args.output_extracted:
        output_path = save_extracted_payload(extracted, Path(args.output_extracted))
        if not args.json_output:
            print(f"Saved normalized extracted payload to: {output_path}")

    email = args.email
    if not email:
        if args.json_output:
            print("Error: --email is required when --json is used.")
            sys.exit(1)
        email = input("Enter your Roborock account email: ").strip()
        if not email:
            print("Error: email is required")
            sys.exit(1)

    home_data: dict[str, Any] = {}
    if not args.skip_home_fetch:
        api_base = args.api_base or extracted["rriot"]["r"]["a"]
        if not args.json_output:
            print(f"Fetching home data from: {api_base}")
        try:
            home_data = asyncio.run(get_home_data_from_token(extracted["token"], api_base))
        except Exception as e:  # noqa: BLE001 - surface HTTP/API errors directly
            print(f"Error: failed to fetch home data: {e}")
            sys.exit(1)

    config = build_config(email, {"rriot": extracted["rriot"]}, home_data)
    config_path = save_config(config, Path(args.config_path).expanduser() if args.config_path else None)
    devices = config.get("devices", [])

    if args.json_output:
        print(
            json.dumps(
                {
                    "config_path": str(config_path),
                    "devices_found": len(devices),
                    "email": email,
                    "region": extracted.get("region"),
                    "country": extracted.get("country"),
                    "rruid": extracted.get("rruid"),
                    "token": extracted.get("token"),
                },
                indent=2,
                ensure_ascii=False,
            )
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


def run_bot(args: argparse.Namespace) -> None:
    """Start the Telegram bot process."""
    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: Telegram bot token is required.")
        print("Use --token or set TELEGRAM_BOT_TOKEN in the environment.")
        sys.exit(1)

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    allowed_users: list[int] | None = None
    if args.users:
        try:
            allowed_users = [int(uid.strip()) for uid in args.users.split(",") if uid.strip()]
        except ValueError:
            print("Error: --users must be a comma-separated list of numeric Telegram user IDs.")
            sys.exit(1)

        if not allowed_users:
            print("Error: --users was provided but no valid user IDs were found.")
            sys.exit(1)

        print(f"Restricted to Telegram user IDs: {allowed_users}")

    try:
        from .telegram_bot import start_bot
    except ModuleNotFoundError:
        print("Error: Telegram dependencies are not installed.")
        print("Install with: pip install roborock-cloud-cli[telegram]")
        sys.exit(1)

    start_bot(token, config, allowed_users)


def run_camera(args: argparse.Namespace) -> None:
    """Run camera commands (snapshot, record, stream)."""
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        from .camera import camera_record, camera_snapshot, camera_stream
    except ModuleNotFoundError:
        print("Error: Camera dependencies are not installed.")
        print("Install with: pip install roborock-cloud-cli[camera]")
        sys.exit(1)

    try:
        if args.command == "snapshot":
            print("Taking snapshot...")
            path = asyncio.run(
                camera_snapshot(
                    config,
                    output=args.output,
                    password=args.password,
                    quality=args.quality,
                    device_index=args.device,
                )
            )
            print(f"Saved: {path}")

        elif args.command == "record":
            print(f"Recording {args.duration}s video...")
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
            print(f"Saved: {path}")

        elif args.command == "stream":
            print("Starting camera stream...")
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

    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped")


def run_command(args: argparse.Namespace) -> None:
    """Execute a vacuum command."""
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    cmd_name = args.command

    if cmd_name == "devices":
        try:
            print_devices(config, json_output=args.json_output)
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    if cmd_name == "raw":
        method = args.method
        if args.params:
            try:
                params = json.loads(args.params)
            except json.JSONDecodeError as e:
                print(f"Error: invalid JSON params: {e.msg} (pos {e.pos})")
                sys.exit(1)
        else:
            params = None

        if not args.json_output:
            print(f"Sending raw: {method} {params or ''}")
        result = asyncio.run(send_command(config, method, params=params, device_index=args.device))
        if args.json_output:
            if isinstance(result, (dict, list)):
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(json.dumps({"result": result}, ensure_ascii=False))
        elif isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)
        return

    if cmd_name not in COMMANDS:
        print(f"Error: unknown command: {cmd_name}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    method, params, description = COMMANDS[cmd_name]
    if not args.json_output:
        print(f"{description}...")

    try:
        result = asyncio.run(send_command(config, method, params=params, device_index=args.device))
    except Exception as e:  # noqa: BLE001 - surface remote/API failure to user
        print(f"Error: command failed: {e}")
        sys.exit(1)

    if args.json_output:
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"result": result}, ensure_ascii=False))
        return

    if cmd_name == "status":
        print(format_status(result))
    elif cmd_name == "consumables":
        print(format_consumables(result))
    elif cmd_name == "clean_summary":
        print(format_clean_summary(result))
    elif isinstance(result, (dict, list)):
        if result == ["ok"]:
            print("OK")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
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
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Interactive first-time setup")
    adb_setup_parser = subparsers.add_parser(
        "adb-setup",
        help="Build config from Android ADB log/extracted payload",
    )
    subparsers.add_parser("devices", help="List configured devices")

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
        help="Override API base URL for getHomeDetail (default: use extracted rriot.r.a)",
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

    for name, (_, _, desc) in COMMANDS.items():
        subparsers.add_parser(name, help=desc)

    raw_parser = subparsers.add_parser("raw", help="Send a raw command")
    raw_parser.add_argument("method", help="Command method name")
    raw_parser.add_argument("params", nargs="?", help="JSON params")

    bot_parser = subparsers.add_parser("bot", help="Start Telegram bot with control panel")
    bot_parser.add_argument("--token", help="Telegram bot token (or set TELEGRAM_BOT_TOKEN env)")
    bot_parser.add_argument("--users", help="Comma-separated allowed Telegram user IDs (optional)")

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
    stream_parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    stream_parser.add_argument("--port", type=int, default=8554, help="Port (default: 8554)")
    stream_parser.add_argument("--password", default="", help="Camera pattern password")
    stream_parser.add_argument("--quality", default="HD", choices=["HD", "SD"], help="Video quality")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "setup":
        setup_interactive()
    elif args.command == "adb-setup":
        run_adb_setup(args)
    elif args.command == "bot":
        run_bot(args)
    elif args.command in ("snapshot", "record", "stream"):
        run_camera(args)
    else:
        run_command(args)


if __name__ == "__main__":
    main()