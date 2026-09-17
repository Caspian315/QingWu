from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .paths import database_path


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, organization TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS style_cards (
    id TEXT PRIMARY KEY, profile_id TEXT, name TEXT NOT NULL, document_kind TEXT NOT NULL,
    card_json TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
    sample_count INTEGER NOT NULL DEFAULT 0, cache_text TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS affairs (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, template_id TEXT NOT NULL,
    template_version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    current_fact_version INTEGER NOT NULL DEFAULT 1, source_text TEXT NOT NULL DEFAULT '',
    ai_used INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fact_snapshots (
    affair_id TEXT NOT NULL, version INTEGER NOT NULL, facts_json TEXT NOT NULL,
    changed_keys_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(affair_id, version),
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY, affair_id TEXT NOT NULL, document_id TEXT NOT NULL,
    title TEXT NOT NULL, kind TEXT NOT NULL, version INTEGER NOT NULL,
    body TEXT NOT NULL, fact_version INTEGER NOT NULL, used_fact_keys_json TEXT NOT NULL,
    required_fact_keys_json TEXT NOT NULL, status TEXT NOT NULL,
    locked_blocks_json TEXT NOT NULL DEFAULT '[]', ai_generated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(affair_id, document_id, version),
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, affair_id TEXT NOT NULL, template_task_id TEXT NOT NULL,
    title TEXT NOT NULL, stage TEXT NOT NULL, due_at TEXT, completed INTEGER NOT NULL DEFAULT 0,
    priority TEXT NOT NULL DEFAULT 'normal', notes TEXT NOT NULL DEFAULT '',
    reminder_enabled INTEGER NOT NULL DEFAULT 1, reminder_offsets_json TEXT NOT NULL DEFAULT '[]',
    sent_reminders_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL,
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY, affair_id TEXT NOT NULL, slot_id TEXT, group_instance_id TEXT,
    source_path TEXT NOT NULL, original_name TEXT NOT NULL, extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, imported_at TEXT NOT NULL,
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS group_instances (
    id TEXT PRIMARY KEY, affair_id TEXT NOT NULL, group_id TEXT NOT NULL,
    title TEXT NOT NULL, facts_json TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS recipients (
    id TEXT PRIMARY KEY, affair_id TEXT NOT NULL, name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ai_runs (
    id TEXT PRIMARY KEY, affair_id TEXT, purpose TEXT NOT NULL, model TEXT NOT NULL,
    success INTEGER NOT NULL, created_at TEXT NOT NULL, error_code TEXT,
    FOREIGN KEY(affair_id) REFERENCES affairs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_affair ON drafts(affair_id, document_id, version);
CREATE INDEX IF NOT EXISTS idx_tasks_affair ON tasks(affair_id);
CREATE INDEX IF NOT EXISTS idx_materials_affair ON materials(affair_id);
"""


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or database_path()).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(sql, tuple(parameters))
        self.connection.commit()
        return cursor

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        self.connection.executemany(sql, rows)
        self.connection.commit()

    def one(self, sql: str, parameters: Iterable[Any] = ()) -> dict[str, Any] | None:
        row = self.connection.execute(sql, tuple(parameters)).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, parameters: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(sql, tuple(parameters)).fetchall()]

    def transaction(self):
        return self.connection
