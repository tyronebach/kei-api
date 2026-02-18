"""Configuration management."""

import os
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR = Path.home() / ".config" / "kei"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def load_config() -> dict:
    """Load config from file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(config: dict) -> None:
    """Save config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get_api_base() -> str:
    """Get API base URL."""
    # Priority: env var > config file > default
    if env_base := os.environ.get("KEI_API_BASE"):
        return env_base.rstrip("/")
    config = load_config()
    return config.get("api_base", "http://localhost:8081").rstrip("/")


def get_token() -> Optional[str]:
    """Get API token."""
    # Priority: env var > config file
    if env_token := os.environ.get("KEI_API_TOKEN"):
        return env_token
    config = load_config()
    return config.get("token")


def get_default_scope() -> Optional[str]:
    """Get default scope."""
    if env_scope := os.environ.get("KEI_SCOPE"):
        return env_scope
    config = load_config()
    return config.get("default_scope")
