"""Telegram bot with inline button control panel for Roborock."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .commands import COMMANDS, FAN_SPEED_MAP, STATE_MAP, format_status
from .mqtt import send_command
from .rooms import clean_rooms, discover_rooms, load_room_map, save_room_map

logger = logging.getLogger(__name__)

STATE_ICON = {
    1: "STARTING",
    2: "IDLE",
    3: "IDLE",
    5: "CLEANING",
    6: "DOCKING",
    8: "CHARGING",
    10: "PAUSED",
    12: "ERROR",
    17: "ZONED",
    18: "ROOM",
}

ROOM_ICON_HINTS = {
    "kitchen": "Kitchen",
    "dining": "Dining",
    "living": "Living",
    "bedroom": "Bedroom",
    "kids": "Kids",
    "office": "Office",
    "hallway": "Hallway",
    "bathroom": "Bathroom",
}


def _room_label(name: str) -> str:
    lowered = name.lower()
    for hint, label in ROOM_ICON_HINTS.items():
        if hint in lowered:
            return f"{label}: {name}"
    return name


def build_keyboard(room_map: dict[int, str] | None = None) -> InlineKeyboardMarkup:
    """Build inline control panel keyboard."""
    rows = [
        [
            InlineKeyboardButton("Start", callback_data="rr:start"),
            InlineKeyboardButton("Pause", callback_data="rr:pause"),
            InlineKeyboardButton("Stop", callback_data="rr:stop"),
        ],
        [
            InlineKeyboardButton("Dock", callback_data="rr:dock"),
            InlineKeyboardButton("Find", callback_data="rr:find"),
            InlineKeyboardButton("Status", callback_data="rr:status"),
        ],
        [
            InlineKeyboardButton("Quiet", callback_data="rr:fan_quiet"),
            InlineKeyboardButton("Balanced", callback_data="rr:fan_balanced"),
            InlineKeyboardButton("Turbo", callback_data="rr:fan_turbo"),
        ],
    ]

    if room_map:
        rows.append([InlineKeyboardButton("Rooms", callback_data="rr:noop")])
        room_buttons = [
            InlineKeyboardButton(_room_label(name), callback_data=f"rr:room:{segment_id}")
            for segment_id, name in sorted(room_map.items())
        ]
        for index in range(0, len(room_buttons), 2):
            rows.append(room_buttons[index : index + 2])
        rows.append([InlineKeyboardButton("All Rooms", callback_data="rr:start")])

    return InlineKeyboardMarkup(rows)


def format_panel_header(status_data: list | dict) -> str:
    """Format compact status text for the panel."""
    if isinstance(status_data, list) and status_data:
        status_data = status_data[0]
    if not isinstance(status_data, dict):
        return "Roborock\nStatus: unknown"

    state = status_data.get("state", -1)
    battery = status_data.get("battery", -1)
    fan = status_data.get("fan_power", -1)
    error = status_data.get("error_code", 0)

    state_name = STATE_MAP.get(state, f"Unknown({state})")
    state_icon = STATE_ICON.get(state, state_name.upper())
    fan_name = FAN_SPEED_MAP.get(fan, f"Custom({fan})")

    lines = [
        "Roborock",
        f"State:   {state_icon}",
        f"Battery: {battery}%",
        f"Fan:     {fan_name}",
    ]

    clean_area = status_data.get("clean_area", 0)
    clean_time = status_data.get("clean_time", 0)
    if status_data.get("in_cleaning") or state in (5, 11, 17, 18):
        lines.append(f"Cleaned: {clean_area / 1000000:.1f} m^2 in {clean_time // 60}m {clean_time % 60}s")

    if error:
        lines.append(f"Error: {error}")

    return "\n".join(lines)


async def get_status_text(config: dict, device_index: int = 0) -> str:
    """Fetch and format current robot status."""
    try:
        from roborock.roborock_typing import RoborockCommand

        result = await send_command(config, RoborockCommand.GET_STATUS, device_index=device_index)
        return format_panel_header(result)
    except Exception as error:  # noqa: BLE001
        return f"Roborock\nError: {error}"


async def execute_command(config: dict, cmd_name: str, device_index: int = 0) -> str:
    """Run a command and return summary text."""
    if cmd_name not in COMMANDS:
        return f"Unknown command: {cmd_name}"

    method, params, description = COMMANDS[cmd_name]
    try:
        result = await send_command(config, method, params=params, device_index=device_index)
        if cmd_name == "status":
            return format_panel_header(result)
        if result == ["ok"]:
            return f"OK: {description}"
        return str(result)
    except Exception as error:  # noqa: BLE001
        return f"Failed: {description}: {error}"


class RoborockBot:
    """Telegram bot for Roborock vacuum control with room support."""

    def __init__(
        self,
        token: str,
        config: dict,
        allowed_users: list[int] | None = None,
        camera_password: str = "",
    ) -> None:
        self.config = config
        self.allowed_users = allowed_users
        self.room_map: dict[int, str] = load_room_map(config)
        self.camera_password = camera_password or ""
        self.app = Application.builder().token(token).build()

        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("panel", self.cmd_panel))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("rooms", self.cmd_rooms))
        self.app.add_handler(CommandHandler("snapshot", self.cmd_snapshot))
        self.app.add_handler(CallbackQueryHandler(self.on_callback, pattern=r"^rr:"))

    def _is_authorized(self, user_id: int) -> bool:
        if self.allowed_users is None:
            return True
        return user_id in self.allowed_users

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_authorized(update.effective_user.id):
            await update.effective_message.reply_text("Unauthorized")
            return

        lines = [
            "Roborock Cloud CLI Bot",
            "",
            "/panel - control panel",
            "/status - detailed status",
            "/rooms - discover room list",
            "/snapshot - camera snapshot (camera models)",
        ]
        await update.effective_message.reply_text("\n".join(lines))

    async def cmd_rooms(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_authorized(update.effective_user.id):
            await update.effective_message.reply_text("Unauthorized")
            return

        await update.effective_message.reply_text("Discovering rooms...")
        try:
            self.room_map = await discover_rooms(self.config)
            save_room_map(self.room_map)
            if not self.room_map:
                await update.effective_message.reply_text("No rooms discovered.")
                return

            lines = [f"Rooms discovered: {len(self.room_map)}"]
            for segment_id, name in sorted(self.room_map.items()):
                lines.append(f"- [{segment_id}] {name}")
            await update.effective_message.reply_text("\n".join(lines))
        except Exception as error:  # noqa: BLE001
            await update.effective_message.reply_text(f"Room discovery failed: {error}")

    async def cmd_snapshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_authorized(update.effective_user.id):
            await update.effective_message.reply_text("Unauthorized")
            return

        await update.effective_message.reply_text("Capturing snapshot...")
        temp_path: str | None = None
        try:
            from .camera import camera_snapshot

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_path = temp_file.name

            await camera_snapshot(self.config, output=temp_path, password=self.camera_password)
            with open(temp_path, "rb") as photo:
                await update.effective_message.reply_photo(photo=photo, caption="Roborock camera")
        except Exception as error:  # noqa: BLE001
            await update.effective_message.reply_text(f"Snapshot failed: {error}")
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    async def cmd_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_authorized(update.effective_user.id):
            await update.effective_message.reply_text("Unauthorized")
            return

        status_text = await get_status_text(self.config)
        await update.effective_message.reply_text(
            status_text,
            reply_markup=build_keyboard(self.room_map),
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_message:
            return
        if not self._is_authorized(update.effective_user.id):
            await update.effective_message.reply_text("Unauthorized")
            return

        try:
            from roborock.roborock_typing import RoborockCommand

            result = await send_command(self.config, RoborockCommand.GET_STATUS)
            text = format_status(result)
            await update.effective_message.reply_text(text)
        except Exception as error:  # noqa: BLE001
            await update.effective_message.reply_text(f"Error: {error}")

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        if not self._is_authorized(query.from_user.id):
            await query.answer("Unauthorized", show_alert=True)
            return

        data = query.data.replace("rr:", "")
        if data == "noop":
            await query.answer()
            return

        if data.startswith("room:"):
            segment_id = int(data.split(":")[1])
            room_name = self.room_map.get(segment_id, f"Room {segment_id}")
            await query.answer(f"Cleaning {room_name}...")
            try:
                await clean_rooms(self.config, [segment_id])
                await asyncio.sleep(2)
                status_text = await get_status_text(self.config)
            except Exception as error:  # noqa: BLE001
                status_text = f"Failed to clean {room_name}: {error}"

            try:
                await query.edit_message_text(
                    status_text,
                    reply_markup=build_keyboard(self.room_map),
                )
            except Exception:
                pass
            return

        command_name = data
        await query.answer(f"Running {command_name}...")

        if command_name == "find":
            _ = await execute_command(self.config, command_name)
            await query.answer("Robot is beeping.", show_alert=True)
            return

        if command_name == "status":
            status_text = await execute_command(self.config, command_name)
        else:
            _ = await execute_command(self.config, command_name)
            await asyncio.sleep(2)
            status_text = await get_status_text(self.config)

        try:
            await query.edit_message_text(
                status_text,
                reply_markup=build_keyboard(self.room_map),
            )
        except Exception:
            pass

    def run(self) -> None:
        print("Roborock Telegram Bot started. Press Ctrl+C to stop.")
        if self.room_map:
            print(f"Loaded {len(self.room_map)} cached room(s).")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def start_bot(
    telegram_token: str,
    config: dict,
    allowed_users: list[int] | None = None,
    camera_password: str = "",
) -> None:
    """Start bot process."""
    bot = RoborockBot(telegram_token, config, allowed_users, camera_password)
    bot.run()
