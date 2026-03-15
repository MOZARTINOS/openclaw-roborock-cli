import argparse
import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for module_name in ("roborock_cli.cli", "roborock_cli"):
    if module_name in sys.modules:
        del sys.modules[module_name]
cli = importlib.import_module("roborock_cli.cli")


def test_devices_command_prints_configured_devices(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {
            "devices": [
                {"name": "Downstairs", "model": "S8", "duid": "d1", "local_key": "k1", "online": True},
                {"name": "Upstairs", "model": "Q5", "duid": "d2", "local_key": "k2", "online": False},
            ]
        },
    )

    args = argparse.Namespace(command="devices", json_output=False, device=0)
    cli.run_command(args)

    output = capsys.readouterr().out
    assert "Configured devices (2):" in output
    assert "[0] Downstairs (S8) - online" in output
    assert "[1] Upstairs (Q5) - offline" in output


def test_status_with_json_flag_outputs_wrapped_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: {"devices": [{"duid": "d", "local_key": "k"}], "rriot": {}})

    async def fake_send_command(*_args, **_kwargs):
        return [{"state": 8, "battery": 50}]

    monkeypatch.setattr(cli, "send_command", fake_send_command)

    args = argparse.Namespace(command="status", json_output=True, device=0)
    cli.run_command(args)

    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"state": 8' in output
    assert '"battery": 50' in output


def test_raw_command_rejects_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: {"devices": [{"duid": "d", "local_key": "k"}], "rriot": {}})

    args = argparse.Namespace(command="raw", method="get_status", params="{bad", json_output=False, device=0)

    with pytest.raises(cli.CLIError) as error:
        cli.run_command(args)

    assert error.value.code == "command_failed"
    assert "Invalid JSON params" in error.value.message


def test_adb_setup_requires_email_with_json(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "extract_payload_from_log",
        lambda _path: {
            "token": "rr123:abc:def",
            "uid": 123,
            "rruid": "rr123",
            "region": "eu",
            "country": "NO",
            "nickname": "Tester",
            "rriot": {
                "u": "u",
                "s": "s",
                "h": "h",
                "k": "k",
                "r": {"a": "https://api-eu.roborock.com", "m": "m", "l": "l", "r": "EU"},
            },
        },
    )

    args = argparse.Namespace(
        log_file="dummy-log.txt",
        extracted_json=None,
        output_extracted=None,
        email=None,
        api_base=None,
        skip_home_fetch=True,
        config_path=None,
        json_output=True,
    )

    with pytest.raises(cli.CLIError) as error:
        cli.run_adb_setup(args)

    assert error.value.code == "command_failed"
    assert "--email is required" in error.value.message


def test_health_json_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {"devices": [{"duid": "d1", "name": "S8", "local_key": "k1", "online": True}], "rriot": {}},
    )
    args = argparse.Namespace(command="health", json_output=True)

    cli.run_command(args)

    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"config_exists": true' in output
    assert '"devices": 1' in output
    assert f'"version": "{cli.__version__}"' in output


def test_health_json_config_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: (_ for _ in ()).throw(FileNotFoundError("Config not found: x")))
    args = argparse.Namespace(command="health", json_output=True)

    cli.run_command(args)

    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert '"error": "config_missing"' in output
    assert '"config_exists": false' in output
    assert f'"version": "{cli.__version__}"' in output


def test_main_json_error_format_for_config_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: (_ for _ in ()).throw(FileNotFoundError("Config not found: x")))
    monkeypatch.setattr(sys, "argv", ["roborock-cli", "--json", "status"])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 1
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert '"error": "config_missing"' in output
    assert '"message": "Config not found: x"' in output


def test_run_clean_reports_room_ambiguous(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {"room_segments": {"16": "Kitchen", "17": "Kids Room"}, "devices": [{"duid": "d", "local_key": "k"}]},
    )

    args = argparse.Namespace(command="clean", rooms=["ki"], repeat=1, device=0, json_output=True)

    with pytest.raises(cli.CLIError) as error:
        cli.run_clean(args)

    assert error.value.code == "room_ambiguous"


def test_run_command_maps_device_not_found(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: {"devices": [{"duid": "d", "local_key": "k"}], "rriot": {}})

    async def fake_send_command(*_args, **_kwargs):
        raise ValueError("Device index 3 out of range (have 1)")

    monkeypatch.setattr(cli, "send_command", fake_send_command)
    args = argparse.Namespace(command="status", json_output=True, device=3)

    with pytest.raises(cli.CLIError) as error:
        cli.run_command(args)

    assert error.value.code == "device_not_found"


def test_run_map_json_success(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {"devices": [{"duid": "d1", "local_key": "k1"}], "rriot": {"u": "u", "s": "s", "h": "h", "k": "k"}},
    )

    async def fake_save_map_image(_config, output, device_index=0):
        path = Path(output)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        assert device_index == 0
        return path

    monkeypatch.setitem(sys.modules, "roborock_cli.map", types.SimpleNamespace(save_map_image=fake_save_map_image))
    out_path = tmp_path / "map.png"
    args = argparse.Namespace(command="map", output=str(out_path), json_output=True, device=0)

    cli.run_map(args)

    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"output":' in output
    assert '"size_bytes": 8' in output
    assert out_path.exists()


def test_run_map_maps_timeout_to_device_offline(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {"devices": [{"duid": "d1", "local_key": "k1"}], "rriot": {"u": "u", "s": "s", "h": "h", "k": "k"}},
    )

    async def fake_save_map_image(_config, output, device_index=0):
        _ = output
        _ = device_index
        raise RuntimeError("Request timeout while fetching map")

    monkeypatch.setitem(sys.modules, "roborock_cli.map", types.SimpleNamespace(save_map_image=fake_save_map_image))
    args = argparse.Namespace(command="map", output=str(tmp_path / "map.png"), json_output=False, device=0)

    with pytest.raises(cli.CLIError) as error:
        cli.run_map(args)

    assert error.value.code == "device_offline"
    assert "timeout" in error.value.message.lower()
