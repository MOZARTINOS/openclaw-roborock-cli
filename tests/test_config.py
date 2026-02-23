from pathlib import Path

from roborock_cli.config import get_config_path, load_config, save_config


def test_get_config_path_prefers_roborock_env(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / "my-config.json"
    monkeypatch.setenv("ROBOROCK_CONFIG", str(cfg))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert get_config_path() == cfg


def test_get_config_path_uses_xdg(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ROBOROCK_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert get_config_path() == tmp_path / "roborock-cli" / "config.json"


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    data = {
        "email": "test@example.com",
        "rriot": {
            "u": "u",
            "s": "s",
            "h": "h",
            "k": "k",
            "r": {"r": "EU", "a": "a", "m": "m", "l": "l"},
        },
        "devices": [{"duid": "d", "name": "Bot", "local_key": "key", "product_id": "p"}],
    }

    saved = save_config(data, path)
    loaded = load_config(path)

    assert saved == path
    assert loaded == data
