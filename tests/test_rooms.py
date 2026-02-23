import asyncio

import pytest

from roborock_cli import rooms


def test_resolve_room_names_exact_partial_and_deduplicate() -> None:
    room_map = {
        16: "Kitchen",
        17: "Living Room",
        18: "Bedroom",
    }

    resolved = rooms.resolve_room_names(room_map, ["kitchen", "liv", "Kitchen"])
    assert resolved == [16, 17]


def test_resolve_room_names_ambiguous_match() -> None:
    room_map = {
        16: "Kids Room",
        17: "Kitchen",
    }

    with pytest.raises(ValueError):
        rooms.resolve_room_names(room_map, ["ki"])


def test_load_room_map_handles_missing_or_invalid() -> None:
    assert rooms.load_room_map({}) == {}
    assert rooms.load_room_map({"room_segments": "bad"}) == {}
    assert rooms.load_room_map({"room_segments": {"16": "Kitchen"}}) == {16: "Kitchen"}


def test_discover_rooms_uses_cloud_names(monkeypatch) -> None:
    async def fake_send_command(_config, _method, device_index=0):
        assert device_index == 1
        return [[16, "111"], [17, "222"]]

    monkeypatch.setattr(rooms, "send_command", fake_send_command)
    config = {"rooms": {"111": "Kitchen", "222": "Bedroom"}}

    mapping = asyncio.run(rooms.discover_rooms(config, device_index=1))
    assert mapping == {16: "Kitchen", 17: "Bedroom"}
