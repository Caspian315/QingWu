from __future__ import annotations

import os
import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = Path(getattr(sys, "_MEIPASS", PACKAGE_DIR.parents[1])).resolve()


def data_dir() -> Path:
    override = os.environ.get("QINGWU_DATA_DIR")
    if override:
        result = Path(override).expanduser().resolve()
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        result = base / "Qingwu"
    result.mkdir(parents=True, exist_ok=True)
    return result


def database_path() -> Path:
    return data_dir() / "qingwu.sqlite3"


def builtin_templates_dir() -> Path:
    override = os.environ.get("QINGWU_TEMPLATES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    source = PROJECT_DIR / "templates"
    if source.is_dir():
        return source
    return Path(sys.prefix) / "share" / "qingwu" / "templates"


def schema_path() -> Path:
    source = PROJECT_DIR / "schemas" / "workflow-template.schema.json"
    if source.is_file():
        return source
    return Path(sys.prefix) / "share" / "qingwu" / "schemas" / "workflow-template.schema.json"
