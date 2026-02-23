"""Room management — discover, map, and clean specific rooms."""

import json
import logging
from pathlib import Path

from roborock.roborock_typing import RoborockCommand

from .config import get_config_path, load_config, save_config
from .mqtt import send_command

logger = logging.getLogger(__name__)


async def discover_rooms(config: dict, device_index: int = 0) -> dict[int, str]:
    """Discover room segments by querying device + cloud room names.

    Returns: {segment_id: room_name}
    """
    # Step 1: Get room mapping from device (segment_id → cloud_id)
    result = await send_command(config, "get_room_mapping", device_index=device_index)
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected room mapping response: {result}")

    # Parse pairs: [[segment_id, cloud_id, ...], ...]
    segment_pairs = []
    for entry in result:
        if isinstance(entry, list) and len(entry) >= 2:
            segment_pairs.append((int(entry[0]), str(entry[1])))

    # Step 2: Get cloud room names from config
    cloud_rooms = config.get("rooms", {})

    # Step 3: Map segment_id → room_name
    room_map = {}
    for segment_id, cloud_id in segment_pairs:
        name = cloud_rooms.get(cloud_id, f"Room {segment_id}")
        room_map[segment_id] = name

    return room_map


async def clean_rooms(
    config: dict,
    segment_ids: list[int],
    repeat: int = 1,
    device_index: int = 0,
) -> any:
    """Clean specific room segments.

    Args:
        config: Config dict with credentials
        segment_ids: List of room segment IDs to clean
        repeat: Number of cleaning passes (1-3)
        device_index: Which device to use

    Returns: Command result
    """
    if not segment_ids:
        raise ValueError("No rooms specified")
    if repeat < 1 or repeat > 3:
        raise ValueError("Repeat must be 1-3")

    # app_segment_clean accepts [segment_ids] or
    # [{"segments": [...], "repeat": N}] for multi-pass
    if repeat == 1:
        params = segment_ids
    else:
        params = [{"segments": segment_ids, "repeat": repeat}]

    return await send_command(
        config, RoborockCommand.APP_SEGMENT_CLEAN, params=params,
        device_index=device_index,
    )


def resolve_room_names(
    room_map: dict[int, str],
    names: list[str],
) -> list[int]:
    """Resolve room names to segment IDs (case-insensitive, partial match).

    Args:
        room_map: {segment_id: room_name} from discover_rooms
        names: User-provided room names

    Returns: List of matching segment IDs

    Raises: ValueError if a name doesn't match any room
    """
    # Build reverse map (lowercase name → segment_id)
    name_to_id = {name.lower(): sid for sid, name in room_map.items()}

    resolved = []
    for query in names:
        q = query.lower().strip()

        # Exact match
        if q in name_to_id:
            resolved.append(name_to_id[q])
            continue

        # Partial match
        matches = [(name, sid) for name, sid in name_to_id.items() if q in name]
        if len(matches) == 1:
            resolved.append(matches[0][1])
            continue
        elif len(matches) > 1:
            options = ", ".join(m[0] for m in matches)
            raise ValueError(f"Ambiguous room '{query}' — matches: {options}")
        else:
            available = ", ".join(name_to_id.keys())
            raise ValueError(f"Unknown room '{query}'. Available: {available}")

    return resolved


def save_room_map(room_map: dict[int, str], config_path: Path | None = None) -> None:
    """Save discovered room mapping to config."""
    path = config_path or get_config_path()
    config = load_config(path)
    config["room_segments"] = {str(k): v for k, v in room_map.items()}
    save_config(config, path)


def load_room_map(config: dict) -> dict[int, str]:
    """Load room mapping from config. Returns empty dict if not discovered yet."""
    segments = config.get("room_segments", {})
    return {int(k): v for k, v in segments.items()}
