"""Carga la configuración local de la app.

Si existe `config.json` junto a este módulo y define `server_url`,
la app actúa como cliente del servidor central.
Si no hay `server_url` (o está vacío), usa SQLite local (`tracker.db`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


CONFIG_FILENAME = "config.json"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return project_root() / CONFIG_FILENAME


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_server_url() -> str | None:
    """URL base del servidor, o None si el modo es local."""
    url = (load_config().get("server_url") or "").strip().rstrip("/")
    return url or None


def is_remote() -> bool:
    return get_server_url() is not None
