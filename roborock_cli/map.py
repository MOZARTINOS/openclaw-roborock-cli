"""Map fetching and rendering for Roborock devices."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from roborock.map.map_parser import MapParser, MapParserConfig
from roborock.roborock_typing import RoborockCommand

from .mqtt import send_map_command


async def fetch_map_image(
    config: dict[str, Any],
    device_index: int = 0,
) -> bytes:
    """Fetch the current map from the device and return a PNG image as bytes.

    Uses the dedicated map RPC channel which applies the correct decoder for
    Roborock's binary map format.

    Returns:
        PNG image bytes of the rendered map.

    Raises:
        RuntimeError: If the map cannot be fetched or parsed.
    """
    raw = await send_map_command(config, RoborockCommand.GET_MAP_V1, device_index=device_index)

    if not isinstance(raw, bytes):
        raise RuntimeError(f"Unexpected map data type: {type(raw).__name__} (expected bytes)")

    parser = MapParser(MapParserConfig())
    parsed = parser.parse(raw)

    if parsed is None or parsed.image_content is None:
        raise RuntimeError(
            "Map data received but image could not be rendered. "
            "Try again during or just after a cleaning session."
        )

    return parsed.image_content


async def save_map_image(
    config: dict[str, Any],
    output: str | Path = "map.png",
    device_index: int = 0,
) -> Path:
    """Fetch the map and save it as a PNG file.

    Args:
        config: Loaded roborock-cli config dict.
        output: Output file path (default: map.png).
        device_index: Device index to use.

    Returns:
        Resolved Path of the saved file.
    """
    image_bytes = await fetch_map_image(config, device_index=device_index)

    out_path = Path(output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)

    return out_path
