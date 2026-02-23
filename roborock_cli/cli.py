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
    roborock-cli rooms              Discover and list rooms
    roborock-cli clean Kitchen      Clean specific room(s)
    roborock-cli clean Kitchen Bedroom --repeat 2
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

    print("\n🏠 Fetching devices and rooms...")
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

    # Show rooms
    rooms = config.get("rooms", {})
    if rooms:
        print(f"\n🏠 Found {len(rooms)} room(s):")
        for rid, name in rooms.items():
            print(f"   • {name}")

    config_path = save_config(config)
    print(f"\n💾 Config saved to: {config_path}")
    print(f"   (permissions: 600 — only you can read it)")

    # Discover room segments
    print(f"\n🗺 Discovering room segments...")
    try:
        from .rooms import discover_rooms, save_room_map
        room_map = asyncio.run(discover_rooms(config))
        save_room_map(room_map, config_path)
        print(f"✅ Mapped {len(room_map)} room segments:")
        for sid, name in sorted(room_map.items()):
            print(f"   [{sid}] {name}")
    except Exception as e:
        print(f"⚠️  Room discovery failed: {e}")
        print("   You can retry later with: roborock-cli rooms")

    print(f"\n🎉 Done! Try: roborock-cli status")
    print(f"   Clean a room: roborock-cli clean Kitchen")


def run_rooms(args):
    """Discover and list room segments."""
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    from .rooms import discover_rooms, save_room_map

    print("🗺 Discovering rooms...")
    try:
        room_map = asyncio.run(discover_rooms(config, device_index=args.device))
    except Exception as e:
        print(f"❌ Room discovery failed: {e}")
        sys.exit(1)

    save_room_map(room_map)

    print(f"\n🏠 {len(room_map)} rooms found:\n")
    print(f"  {'ID':>4}  {'Room Name'}")
    print(f"  {'─' * 4}  {'─' * 20}")
    for sid, name in sorted(room_map.items()):
        print(f"  {sid:>4}  {name}")

    print(f"\n💡 Clean a room: roborock-cli clean \"{list(room_map.values())[0]}\"")
    print(f"   Multiple rooms: roborock-cli clean \"{list(room_map.values())[0]}\" \"{list(room_map.values())[-1]}\"")


def run_clean(args):
    """Clean specific rooms by name."""
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    from .rooms import clean_rooms, discover_rooms, load_room_map, resolve_room_names

    # Load cached room map or discover
    room_map = load_room_map(config)
    if not room_map:
        print("🗺 Room segments not cached — discovering...")
        try:
            room_map = asyncio.run(discover_rooms(config, device_index=args.device))
        except Exception as e:
            print(f"❌ Room discovery failed: {e}")
            print("   Run 'roborock-cli rooms' first.")
            sys.exit(1)

    # Resolve names to segment IDs
    try:
        segment_ids = resolve_room_names(room_map, args.rooms)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    room_names = [room_map[sid] for sid in segment_ids]
    repeat_str = f" (×{args.repeat})" if args.repeat > 1 else ""
    print(f"🧹 Cleaning: {', '.join(room_names)}{repeat_str}")

    try:
        result = asyncio.run(clean_rooms(config, segment_ids, repeat=args.repeat, device_index=args.device))
        if result == ["ok"]:
            print("✅ Started!")
        else:
            print(f"Result: {result}")
    except Exception as e:
        print(f"❌ Failed: {e}")
        sys.exit(1)


def run_bot(args):
    """Start the Telegram bot."""
    import os

    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Telegram bot token required.")
        print("   Use --token or set TELEGRAM_BOT_TOKEN environment variable.")
        print("   Create a bot via @BotFather on Telegram.")
        sys.exit(1)

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    allowed_users = None
    if args.users:
        allowed_users = [int(uid.strip()) for uid in args.users.split(",")]
        print(f"🔒 Restricted to user IDs: {allowed_users}")

    from .telegram_bot import start_bot
    start_bot(token, config, allowed_users)


def run_camera(args):
    """Run camera commands (snapshot, record, stream)."""
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    from .camera import camera_snapshot, camera_record, camera_stream

    try:
        if args.command == "snapshot":
            print(f"📸 Taking snapshot...")
            path = asyncio.run(camera_snapshot(
                config, output=args.output, password=args.password,
                quality=args.quality, device_index=args.device,
            ))
            print(f"✅ Saved: {path}")

        elif args.command == "record":
            print(f"🎬 Recording {args.duration}s video...")
            path = asyncio.run(camera_record(
                config, output=args.output, duration=args.duration,
                password=args.password, quality=args.quality,
                device_index=args.device,
            ))
            print(f"✅ Saved: {path}")

        elif args.command == "stream":
            print(f"🎥 Starting camera stream...")
            asyncio.run(camera_stream(
                config, host=args.host, port=args.port,
                password=args.password, quality=args.quality,
                device_index=args.device,
            ))

    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹ Stopped")


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

    # Room discovery
    subparsers.add_parser("rooms", help="Discover and list room segments")

    # Room cleaning
    clean_parser = subparsers.add_parser("clean", help="Clean specific room(s) by name")
    clean_parser.add_argument("rooms", nargs="+", help="Room name(s) to clean (partial match OK)")
    clean_parser.add_argument("--repeat", type=int, default=1, choices=[1, 2, 3],
                              help="Number of cleaning passes (default: 1)")

    # Raw command
    raw_parser = subparsers.add_parser("raw", help="Send a raw command")
    raw_parser.add_argument("method", help="Command method name")
    raw_parser.add_argument("params", nargs="?", help="JSON params")

    # Telegram bot
    bot_parser = subparsers.add_parser("bot", help="Start Telegram bot with control panel")
    bot_parser.add_argument("--token", help="Telegram bot token (or set TELEGRAM_BOT_TOKEN env)")
    bot_parser.add_argument("--users", help="Comma-separated allowed Telegram user IDs (optional)")

    # Camera commands
    snap_parser = subparsers.add_parser("snapshot", help="📸 Take a camera snapshot (camera models only)")
    snap_parser.add_argument("-o", "--output", default="snapshot.jpg", help="Output file (default: snapshot.jpg)")
    snap_parser.add_argument("--password", default="", help="Camera pattern password")
    snap_parser.add_argument("--quality", default="HD", choices=["HD", "SD"], help="Video quality")

    rec_parser = subparsers.add_parser("record", help="🎬 Record camera video (camera models only)")
    rec_parser.add_argument("-o", "--output", default="recording.mp4", help="Output file (default: recording.mp4)")
    rec_parser.add_argument("--duration", type=int, default=30, help="Duration in seconds (default: 30)")
    rec_parser.add_argument("--password", default="", help="Camera pattern password")
    rec_parser.add_argument("--quality", default="HD", choices=["HD", "SD"], help="Video quality")

    stream_parser = subparsers.add_parser("stream", help="🎥 Start MJPEG camera stream (camera models only)")
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


if __name__ == "__main__":
    main()
