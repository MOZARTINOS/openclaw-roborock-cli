"""Configuration management for Roborock CLI."""

import json
import os
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "roborock-cli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


def get_config_path() -> Path:
    """Get config file path, respecting XDG_CONFIG_HOME."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "roborock-cli" / "config.json"
    return DEFAULT_CONFIG_FILE


def load_config(path: Path | None = None) -> dict:
    """Load configuration from JSON file."""
    config_path = path or get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Run 'roborock-cli setup' to create one, or copy config.example.json"
        )
    with open(config_path) as f:
        return json.load(f)


def save_config(config: dict, path: Path | None = None) -> Path:
    """Save configuration to JSON file."""
    config_path = path or get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    # Restrict permissions — this file contains secrets
    config_path.chmod(0o600)
    return config_path
