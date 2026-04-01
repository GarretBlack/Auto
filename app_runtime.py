import copy
import json
import os
import sys
from pathlib import Path
from typing import Any


APP_DIR_NAME = "EmulationWork"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_bundle_dir() -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def get_install_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        path = base / APP_DIR_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parent


def get_default_config_path() -> Path:
    return get_data_dir() / "config.json"


def get_bundled_config_path() -> Path:
    return get_bundle_dir() / "config.json"


def ensure_user_config(default_config: dict[str, Any]) -> Path:
    config_path = get_default_config_path()
    if config_path.exists():
        return config_path

    bundled_path = get_bundled_config_path()
    if bundled_path.exists():
        config_path.write_text(bundled_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        config_path.write_text(json.dumps(copy.deepcopy(default_config), ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def resolve_user_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return get_data_dir() / path
