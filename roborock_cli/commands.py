"""Available Roborock commands and response formatters."""

from __future__ import annotations

from roborock.roborock_typing import RoborockCommand

# Command name -> (RoborockCommand, params, description)
COMMANDS = {
    # Basic control
    "start": (RoborockCommand.APP_START, None, "Start cleaning"),
    "stop": (RoborockCommand.APP_STOP, None, "Stop cleaning"),
    "pause": (RoborockCommand.APP_PAUSE, None, "Pause cleaning"),
    "dock": (RoborockCommand.APP_CHARGE, None, "Return to dock"),
    "find": (RoborockCommand.FIND_ME, None, "Make the robot beep"),

    # Status
    "status": (RoborockCommand.GET_STATUS, None, "Get current status"),
    "consumables": (RoborockCommand.GET_CONSUMABLE, None, "Get consumable status"),
    "clean_summary": (RoborockCommand.GET_CLEAN_SUMMARY, None, "Get cleaning history"),

    # Fan speed
    "fan_quiet": (RoborockCommand.SET_CUSTOM_MODE, [101], "Set fan to quiet"),
    "fan_balanced": (RoborockCommand.SET_CUSTOM_MODE, [102], "Set fan to balanced"),
    "fan_turbo": (RoborockCommand.SET_CUSTOM_MODE, [103], "Set fan to turbo"),
    "fan_max": (RoborockCommand.SET_CUSTOM_MODE, [104], "Set fan to max"),
}

# Human-readable status state mapping
STATE_MAP = {
    1: "Starting",
    2: "Idle",
    3: "Idle",
    5: "Cleaning",
    6: "Returning to dock",
    7: "Manual mode",
    8: "Charging",
    9: "Charging problem",
    10: "Paused",
    11: "Spot cleaning",
    12: "Error",
    13: "Shutting down",
    14: "Updating",
    15: "Docking",
    16: "Going to target",
    17: "Zoned cleaning",
    18: "Segment cleaning",
    22: "Emptying dustbin",
    23: "Washing mop",
    26: "Going to wash mop",
    28: "In call",
    29: "Mapping",
    100: "Fully charged",
}

ERROR_MAP = {
    0: "None",
    1: "Laser sensor fault",
    2: "Collision sensor fault",
    3: "Wheel floating",
    4: "Cliff sensor fault",
    5: "Main brush jammed",
    6: "Side brush jammed",
    7: "Wheel jammed",
    8: "Robot stuck",
    9: "Dustbin missing",
    10: "Filter clogged",
    11: "Magnetic field detected",
    12: "Low battery",
    13: "Charging problem",
    14: "Battery failure",
    15: "Wall sensor fault",
    16: "Uneven surface",
    17: "Side brush failure",
    18: "Suction fan failure",
    19: "Unpowered charging station",
    20: "Unknown error",
    21: "Laser pressure sensor fault",
    22: "Charge sensor fault",
    23: "Dock problem",
    24: "No-go zone detected",
    254: "Bin full",
    255: "Internal error",
}

FAN_SPEED_MAP = {
    101: "Quiet",
    102: "Balanced",
    103: "Turbo",
    104: "Max",
    105: "Off (Mop only)",
}

# Approximate replacement intervals used by Roborock mobile app (seconds).
CONSUMABLE_LIMITS = {
    "main_brush_work_time": (1080000, "Main brush"),
    "side_brush_work_time": (720000, "Side brush"),
    "filter_work_time": (540000, "Filter"),
    "sensor_dirty_time": (108000, "Sensors"),
    "strainer_work_times": (540000, "Strainer"),
}


def _to_mapping(data: list | dict) -> dict:
    """Return first mapping entry from a command response."""
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first
    if isinstance(data, dict):
        return data
    return {}


def _seconds_to_hours(seconds: int | float) -> float:
    return max(0.0, float(seconds)) / 3600.0


def format_status(data: list | dict) -> str:
    """Format status response into human-readable output."""
    payload = _to_mapping(data)
    if not payload:
        return str(data)

    state = payload.get("state", -1)
    battery = payload.get("battery", -1)
    fan = payload.get("fan_power", -1)
    error = payload.get("error_code", 0)
    clean_time = payload.get("clean_time", 0)
    clean_area = payload.get("clean_area", 0)

    lines = [
        f"  State:      {STATE_MAP.get(state, f'Unknown ({state})')}",
        f"  Battery:    {battery}%",
        f"  Fan speed:  {FAN_SPEED_MAP.get(fan, f'Custom ({fan})')}",
        f"  Clean time: {clean_time // 60}m {clean_time % 60}s",
        f"  Clean area: {clean_area / 1000000:.1f} m^2",
    ]

    if error:
        lines.append(f"  Warning:    {ERROR_MAP.get(error, f'Unknown ({error})')}")

    if payload.get("water_box_status"):
        lines.append("  Water tank: Installed")
    if payload.get("water_box_carriage_status"):
        lines.append("  Mop:        Attached")

    return "\n".join(lines)


def format_consumables(data: list | dict, warn_threshold: float = 0.15) -> str:
    """Format consumable response with remaining life and warnings."""
    payload = _to_mapping(data)
    if not payload:
        return str(data)

    lines = ["Consumables:"]
    warnings: list[str] = []

    for key, (limit_seconds, label) in CONSUMABLE_LIMITS.items():
        used_seconds = payload.get(key)
        if used_seconds is None:
            continue

        used = max(0, int(used_seconds))
        remaining = max(0, limit_seconds - used)
        used_pct = min(100.0, (used / limit_seconds) * 100)
        remaining_hours = _seconds_to_hours(remaining)

        lines.append(
            f"  {label:<11} {used_pct:5.1f}% used ({remaining_hours:6.1f}h remaining)"
        )

        if remaining <= limit_seconds * warn_threshold:
            warnings.append(f"{label} is near replacement")

    if not lines[1:]:
        return str(data)

    if warnings:
        lines.append("Maintenance alerts:")
        for item in warnings:
            lines.append(f"  - {item}")

    return "\n".join(lines)


def format_clean_summary(data: list | dict) -> str:
    """Format clean summary output if available."""
    payload = _to_mapping(data)
    if not payload:
        return str(data)

    total_seconds = payload.get("clean_time", 0)
    total_area = payload.get("clean_area", 0)
    clean_count = payload.get("clean_count", 0)

    return "\n".join(
        [
            "Clean summary:",
            f"  Sessions:   {clean_count}",
            f"  Total time: {int(total_seconds) // 3600}h {(int(total_seconds) % 3600) // 60}m",
            f"  Total area: {float(total_area) / 1000000:.1f} m^2",
        ]
    )
