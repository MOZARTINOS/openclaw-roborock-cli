"""Configuration management for Roborock CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "roborock-cli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
CONFIG_ENV_VAR = "ROBOROCK_CONFIG"


def get_config_path() -> Path:
    """Get config file path, respecting ROBOROCK_CONFIG/XDG_CONFIG_HOME."""
    explicit_path = os.environ.get(CONFIG_ENV_VAR)
    if explicit_path:
        return Path(explicit_path).expanduser()

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "roborock-cli" / "config.json"
    return DEFAULT_CONFIG_FILE


def resolve_config_path(path: Path | None = None) -> Path:
    """Resolve config path from explicit path, env var, or default location."""
    config_env = os.environ.get(CONFIG_ENV_VAR)
    return path or (Path(config_env).expanduser() if config_env else get_config_path())


def load_config(path: Path | None = None) -> dict:
    """Load configuration from JSON file."""
    config_path = resolve_config_path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            "Run 'roborock-cli setup' to create one, or copy config.example.json"
        )
    with open(config_path, encoding="utf-8") as file:
        return json.load(file)


def save_config(config: dict, path: Path | None = None) -> Path:
    """Save configuration to JSON file with best-effort restricted permissions."""
    config_path = resolve_config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=config_path.parent,
        prefix=".config.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        json.dump(config, temp_file, indent=2)
        temp_path = Path(temp_file.name)

    temp_path.replace(config_path)

    # Restrict permissions where supported.
    try:
        config_path.chmod(0o600)
    except OSError:
        pass

    return config_path
