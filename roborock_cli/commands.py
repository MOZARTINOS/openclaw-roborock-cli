"""Available Roborock commands."""

from roborock.roborock_typing import RoborockCommand

# Command name -> (RoborockCommand, params)
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


def format_status(data: list | dict) -> str:
    """Format status response into human-readable output."""
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if not isinstance(data, dict):
        return str(data)

    state = data.get("state", -1)
    battery = data.get("battery", -1)
    fan = data.get("fan_power", -1)
    error = data.get("error_code", 0)
    clean_time = data.get("clean_time", 0)
    clean_area = data.get("clean_area", 0)

    lines = [
        f"  State:      {STATE_MAP.get(state, f'Unknown ({state})')}",
        f"  Battery:    {battery}%",
        f"  Fan speed:  {FAN_SPEED_MAP.get(fan, f'Custom ({fan})')}",
        f"  Clean time: {clean_time // 60}m {clean_time % 60}s",
        f"  Clean area: {clean_area / 1000000:.1f} m²",
    ]

    if error:
        lines.append(f"  ⚠ Error:    {ERROR_MAP.get(error, f'Unknown ({error})')}")

    if data.get("water_box_status"):
        lines.append(f"  Water tank: Installed")
    if data.get("water_box_carriage_status"):
        lines.append(f"  Mop:        Attached")

    return "\n".join(lines)
