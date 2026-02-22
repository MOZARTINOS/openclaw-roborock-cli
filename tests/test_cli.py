import argparse

import pytest

from roborock_cli import cli


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


def test_raw_command_rejects_invalid_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: {"devices": [{"duid": "d", "local_key": "k"}], "rriot": {}})

    args = argparse.Namespace(command="raw", method="get_status", params="{bad", json_output=False, device=0)

    with pytest.raises(SystemExit) as error:
        cli.run_command(args)

    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "invalid JSON params" in output


def test_status_with_json_flag_outputs_machine_readable_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: {"devices": [{"duid": "d", "local_key": "k"}], "rriot": {}})

    async def fake_send_command(*_args, **_kwargs):
        return [{"state": 8, "battery": 50}]

    monkeypatch.setattr(cli, "send_command", fake_send_command)

    args = argparse.Namespace(command="status", json_output=True, device=0)
    cli.run_command(args)

    output = capsys.readouterr().out
    assert '"state": 8' in output
    assert '"battery": 50' in output


def test_raw_with_json_flag_wraps_scalar_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: {"devices": [{"duid": "d", "local_key": "k"}], "rriot": {}})

    async def fake_send_command(*_args, **_kwargs):
        return "ok"

    monkeypatch.setattr(cli, "send_command", fake_send_command)

    args = argparse.Namespace(
        command="raw",
        method="get_status",
        params=None,
        json_output=True,
        device=0,
    )
    cli.run_command(args)

    output = capsys.readouterr().out
    assert '"result": "ok"' in output


def test_adb_setup_builds_and_saves_config(monkeypatch, capsys) -> None:
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

    async def fake_home_data(_token: str, _api_base: str):
        return {
            "devices": [{"duid": "d1", "name": "S8", "local_key": "lk", "product_id": "p1", "online": True}],
            "products": [{"id": "p1", "model": "a51"}],
        }

    monkeypatch.setattr(cli, "get_home_data_from_token", fake_home_data)

    captured = {}

    def fake_save_config(config, path=None):
        captured["config"] = config
        captured["path"] = path
        return "fake-config-path"

    monkeypatch.setattr(cli, "save_config", fake_save_config)

    args = argparse.Namespace(
        log_file="dummy-log.txt",
        extracted_json=None,
        output_extracted=None,
        email="test@example.com",
        api_base=None,
        skip_home_fetch=False,
        config_path=None,
        json_output=False,
    )
    cli.run_adb_setup(args)

    assert captured["config"]["email"] == "test@example.com"
    assert len(captured["config"]["devices"]) == 1
    output = capsys.readouterr().out
    assert "ADB setup completed." in output
    assert "Devices:     1" in output


def test_adb_setup_requires_email_with_json(monkeypatch, capsys) -> None:
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

    with pytest.raises(SystemExit) as error:
        cli.run_adb_setup(args)

    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "--email is required" in output
