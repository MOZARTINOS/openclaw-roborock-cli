"""Telegram bot with inline button control panel for Roborock."""

import asyncio
import logging
import signal
import sys

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .commands import COMMANDS, FAN_SPEED_MAP, STATE_MAP, format_status
from .config import load_config
from .mqtt import send_command

logger = logging.getLogger(__name__)

# State emoji mapping
STATE_EMOJI = {
    1: "🔄", 2: "💤", 3: "💤", 5: "🧹", 6: "🏠", 7: "🕹",
    8: "🔋", 9: "⚠️", 10: "⏸", 11: "🎯", 12: "❌", 13: "📴",
    14: "📥", 15: "🏠", 16: "🎯", 17: "🧹", 18: "🧹",
    22: "🗑", 23: "🚿", 26: "🚿", 100: "✅",
}

FAN_EMOJI = {101: "🔇", 102: "⚖️", 103: "💨", 104: "🌪"}


def build_keyboard() -> InlineKeyboardMarkup:
    """Build the inline keyboard for vacuum control."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Start", callback_data="rr:start"),
            InlineKeyboardButton("⏸ Pause", callback_data="rr:pause"),
            InlineKeyboardButton("⏹ Stop", callback_data="rr:stop"),
        ],
        [
            InlineKeyboardButton("🏠 Dock", callback_data="rr:dock"),
            InlineKeyboardButton("📍 Find", callback_data="rr:find"),
            InlineKeyboardButton("🔄 Status", callback_data="rr:status"),
        ],
        [
            InlineKeyboardButton("🔇 Quiet", callback_data="rr:fan_quiet"),
            InlineKeyboardButton("⚖️ Balanced", callback_data="rr:fan_balanced"),
            InlineKeyboardButton("💨 Turbo", callback_data="rr:fan_turbo"),
        ],
    ])


def format_panel_header(status_data: list | dict) -> str:
    """Format a one-line status header for the control panel."""
    if isinstance(status_data, list) and len(status_data) > 0:
        status_data = status_data[0]
    if not isinstance(status_data, dict):
        return "🤖 **Roborock** | Status unknown"

    state = status_data.get("state", -1)
    battery = status_data.get("battery", -1)
    fan = status_data.get("fan_power", -1)
    error = status_data.get("error_code", 0)

    state_emoji = STATE_EMOJI.get(state, "❓")
    state_name = STATE_MAP.get(state, "Unknown")
    fan_name = FAN_SPEED_MAP.get(fan, f"Custom")
    fan_icon = FAN_EMOJI.get(fan, "🔧")

    header = f"🤖 *Roborock* | 🔋 {battery}% | {state_emoji} {state_name} | {fan_icon} {fan_name}"

    if error:
        header += f"\n⚠️ Error: {error}"

    clean_area = status_data.get("clean_area", 0)
    clean_time = status_data.get("clean_time", 0)
    if status_data.get("in_cleaning"):
        header += f"\n🧹 {clean_area / 1000000:.1f} m² | ⏱ {clean_time // 60}m {clean_time % 60}s"

    return header


async def get_status_text(config: dict, device_index: int = 0) -> str:
    """Get formatted status from the vacuum."""
    try:
        from roborock.roborock_typing import RoborockCommand
        result = await send_command(config, RoborockCommand.GET_STATUS, device_index=device_index)
        return format_panel_header(result)
    except Exception as e:
        return f"🤖 *Roborock* | ❌ Error: {e}"


async def execute_command(config: dict, cmd_name: str, device_index: int = 0) -> str:
    """Execute a command and return result text."""
    if cmd_name not in COMMANDS:
        return f"❌ Unknown: {cmd_name}"

    method, params, description = COMMANDS[cmd_name]
    try:
        result = await send_command(config, method, params=params, device_index=device_index)
        if cmd_name == "status":
            return format_panel_header(result)
        if result == ["ok"]:
            return f"✅ {description}"
        return str(result)
    except Exception as e:
        return f"❌ {description} failed: {e}"


class RoborockBot:
    """Telegram bot for Roborock vacuum control."""

    def __init__(self, token: str, config: dict, allowed_users: list[int] | None = None,
                 camera_password: str = ""):
        self.config = config
        self.allowed_users = allowed_users
        self.app = Application.builder().token(token).build()

        self.camera_password = camera_password or ""

        # Register handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("panel", self.cmd_panel))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("snapshot", self.cmd_snapshot))
        self.app.add_handler(CallbackQueryHandler(self.on_callback, pattern=r"^rr:"))

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        if self.allowed_users is None:
            return True
        return user_id in self.allowed_users

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized")
            return

        await update.message.reply_text(
            "🤖 *Roborock Cloud CLI*\n\n"
            "Commands:\n"
            "/panel — Control panel with buttons\n"
            "/status — Detailed status\n"
            "/snapshot — 📸 Camera snapshot (camera models)\n\n"
            "Or just use the panel buttons!",
            parse_mode="Markdown",
        )

    async def cmd_snapshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Take a camera snapshot and send as photo."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized")
            return

        await update.message.reply_text("📸 Capturing snapshot...")
        try:
            from .camera import camera_snapshot
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                tmp_path = f.name

            await camera_snapshot(self.config, output=tmp_path, password=self.camera_password)
            with open(tmp_path, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption="📸 Roborock Camera")
            os.unlink(tmp_path)
        except Exception as e:
            await update.message.reply_text(f"❌ Snapshot failed: {e}")

    async def cmd_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the control panel with inline buttons."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized")
            return

        status_text = await get_status_text(self.config)
        await update.message.reply_text(
            status_text,
            reply_markup=build_keyboard(),
            parse_mode="Markdown",
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send detailed status."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized")
            return

        try:
            from roborock.roborock_typing import RoborockCommand
            result = await send_command(self.config, RoborockCommand.GET_STATUS)
            text = format_status(result)
            await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button presses."""
        query = update.callback_query
        if not self._is_authorized(query.from_user.id):
            await query.answer("⛔ Unauthorized", show_alert=True)
            return

        cmd_name = query.data.replace("rr:", "")
        await query.answer(f"⏳ {cmd_name}...")

        result_text = await execute_command(self.config, cmd_name)

        if cmd_name == "find":
            await query.answer("📍 Beeping!", show_alert=True)
            return

        # Update the panel message with new status
        if cmd_name == "status":
            status_text = result_text
        else:
            # After any command, refresh status
            await asyncio.sleep(2)  # Wait for state change
            status_text = await get_status_text(self.config)

        try:
            await query.edit_message_text(
                status_text,
                reply_markup=build_keyboard(),
                parse_mode="Markdown",
            )
        except Exception:
            # Message unchanged — ignore
            pass

    def run(self):
        """Start the bot (blocking)."""
        print("🤖 Roborock Telegram Bot started! Press Ctrl+C to stop.")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def start_bot(telegram_token: str, config: dict, allowed_users: list[int] | None = None,
              camera_password: str = ""):
    """Start the Telegram bot."""
    bot = RoborockBot(telegram_token, config, allowed_users, camera_password)
    bot.run()
