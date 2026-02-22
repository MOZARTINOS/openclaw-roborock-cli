#!/usr/bin/env python3
"""Roborock Cloud CLI — control your vacuum from the terminal.

Usage:
    roborock-cli setup              Interactive first-time setup
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
"""

import argparse
import asyncio
import json
import logging
import sys

from . import __version__
from .auth import build_config, discover_region, get_home_data, login_with_code, request_code
from .commands import COMMANDS, format_status
from .config import get_config_path, load_config, save_config
from .mqtt import send_command


def setup_interactive():
    """Interactive setup: login, discover devices, save config."""
    print("🤖 Roborock Cloud CLI — Setup\n")

    email = input("Enter your Roborock account email: ").strip()
    if not email:
        print("❌ Email is required")
        sys.exit(1)

    print(f"\n🔍 Discovering region for {email}...")
    region = asyncio.run(discover_region(email))
    base_url = region["base_url"]
    print(f"✅ Region: {region['country']} ({base_url})")

    print(f"\n📧 Sending verification code to {email}...")
    asyncio.run(request_code(email, base_url))
    print("✅ Code sent! Check your email.")

    code = input("\nEnter verification code: ").strip()
    if not code:
        print("❌ Code is required")
        sys.exit(1)

    print("\n🔐 Logging in...")
    try:
        user_data = asyncio.run(login_with_code(email, code, base_url))
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print(f"✅ Logged in as {user_data.get('nickname', email)}")

    print("\n🏠 Fetching devices...")
    home_data = asyncio.run(get_home_data(user_data))
    config = build_config(email, user_data, home_data)

    devices = config.get("devices", [])
    if not devices:
        print("⚠️  No devices found. Check your Roborock app.")
        sys.exit(1)

    print(f"✅ Found {len(devices)} device(s):")
    for i, dev in enumerate(devices):
        status = "🟢 online" if dev.get("online") else "🔴 offline"
        print(f"   [{i}] {dev['name']} ({dev.get('model', '?')}) — {status}")

    config_path = save_config(config)
    print(f"\n💾 Config saved to: {config_path}")
    print(f"   (permissions: 600 — only you can read it)")
    print(f"\n🎉 Done! Try: roborock-cli status")


def run_command(args):
    """Execute a vacuum command."""
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    cmd_name = args.command

    if cmd_name == "raw":
        # Raw command mode
        method = args.method
        params = json.loads(args.params) if args.params else None
        print(f"📡 Sending raw: {method} {params or ''}")
        result = asyncio.run(send_command(config, method, params=params, device_index=args.device))
        print(json.dumps(result, indent=2, ensure_ascii=False) if isinstance(result, (dict, list)) else result)
        return

    if cmd_name not in COMMANDS:
        print(f"❌ Unknown command: {cmd_name}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    method, params, description = COMMANDS[cmd_name]
    print(f"📡 {description}...")

    try:
        result = asyncio.run(send_command(config, method, params=params, device_index=args.device))
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)

    if cmd_name == "status":
        print(format_status(result))
    elif isinstance(result, (dict, list)):
        if result == ["ok"]:
            print("✅ OK")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"✅ {result}")


def main():
    parser = argparse.ArgumentParser(
        prog="roborock-cli",
        description="Control your Roborock vacuum from the terminal",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("-d", "--device", type=int, default=0, help="Device index (default: 0)")

    subparsers = parser.add_subparsers(dest="command")

    # Setup
    subparsers.add_parser("setup", help="Interactive first-time setup")

    # All standard commands
    for name, (_, _, desc) in COMMANDS.items():
        subparsers.add_parser(name, help=desc)

    # Raw command
    raw_parser = subparsers.add_parser("raw", help="Send a raw command")
    raw_parser.add_argument("method", help="Command method name")
    raw_parser.add_argument("params", nargs="?", help="JSON params")

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
    else:
        run_command(args)


if __name__ == "__main__":
    main()
