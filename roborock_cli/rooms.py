"""Room management: discover, cache, and clean named rooms."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from roborock.roborock_typing import RoborockCommand

from .config import get_config_path, load_config, save_config
from .mqtt import send_command


async def discover_rooms(config: dict[str, Any], device_index: int = 0) -> dict[int, str]:
    """Discover room segments by combining device mapping and cloud room names.

    Returns:
        Mapping of ``segment_id -> room_name``.
    """
    result = await send_command(config, "get_room_mapping", device_index=device_index)
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected room mapping response: {result}")

    cloud_rooms_raw = config.get("rooms", {})
    cloud_rooms: dict[str, str]
    if isinstance(cloud_rooms_raw, dict):
        cloud_rooms = {str(key): str(value) for key, value in cloud_rooms_raw.items()}
    else:
        cloud_rooms = {}

    room_map: dict[int, str] = {}
    for entry in result:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        segment_id = int(entry[0])
        cloud_id = str(entry[1])
        room_map[segment_id] = cloud_rooms.get(cloud_id, f"Room {segment_id}")

    return room_map


async def clean_rooms(
    config: dict[str, Any],
    segment_ids: list[int],
    repeat: int = 1,
    device_index: int = 0,
) -> Any:
    """Run segment cleaning for one or more room segments."""
    if not segment_ids:
        raise ValueError("No rooms specified")
    if repeat < 1 or repeat > 3:
        raise ValueError("Repeat must be in range 1-3")

    params: list[int] | list[dict[str, Any]]
    if repeat == 1:
        params = segment_ids
    else:
        params = [{"segments": segment_ids, "repeat": repeat}]

    return await send_command(
        config,
        RoborockCommand.APP_SEGMENT_CLEAN,
        params=params,
        device_index=device_index,
    )


def resolve_room_names(room_map: dict[int, str], names: list[str]) -> list[int]:
    """Resolve room names to segment IDs using exact or partial case-insensitive match."""
    if not room_map:
        raise ValueError("No room mapping available")

    name_to_id = {name.lower(): segment_id for segment_id, name in room_map.items()}
    resolved: list[int] = []

    for query in names:
        normalized = query.lower().strip()
        if not normalized:
            continue

        if normalized in name_to_id:
            segment_id = name_to_id[normalized]
        else:
            matches = [(name, sid) for name, sid in name_to_id.items() if normalized in name]
            if len(matches) == 1:
                segment_id = matches[0][1]
            elif len(matches) > 1:
                options = ", ".join(match[0] for match in matches)
                raise ValueError(f"Ambiguous room '{query}' - matches: {options}")
            else:
                available = ", ".join(sorted(name_to_id.keys()))
                raise ValueError(f"Unknown room '{query}'. Available: {available}")

        if segment_id not in resolved:
            resolved.append(segment_id)

    if not resolved:
        raise ValueError("No rooms matched")

    return resolved


def save_room_map(room_map: dict[int, str], config_path: Path | None = None) -> None:
    """Persist discovered room mapping into config as ``room_segments``."""
    path = config_path or get_config_path()
    config = load_config(path)
    config["room_segments"] = {str(segment_id): name for segment_id, name in room_map.items()}
    save_config(config, path)


def load_room_map(config: dict[str, Any]) -> dict[int, str]:
    """Load room mapping from config. Returns an empty mapping when missing."""
    segments = config.get("room_segments", {})
    if not isinstance(segments, dict):
        return {}
    return {int(segment_id): str(name) for segment_id, name in segments.items()}
