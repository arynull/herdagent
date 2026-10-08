import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def data_dir() -> Path:
    raw = os.environ.get("HERDAGENT_DATA_DIR")
    base = Path(raw).expanduser() if raw else Path.home() / ".herdagent"
    base.mkdir(parents=True, exist_ok=True)
    return base


def connect() -> sqlite3.Connection:
    path = data_dir() / "herdagent.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            label TEXT UNIQUE NOT NULL,
            limit_tokens_day INTEGER,
            used_tokens INTEGER DEFAULT 0,
            limit_rpm INTEGER,
            observed_429s INTEGER DEFAULT 0,
            last_429_at TEXT,
            status TEXT DEFAULT 'active',
            notes TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            backend TEXT NOT NULL,
            cwd TEXT NOT NULL,
            branch TEXT DEFAULT '',
            account_label TEXT,
            status TEXT DEFAULT 'running',
            pid INTEGER,
            started_at TEXT,
            last_heartbeat TEXT,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT DEFAULT '',
            status TEXT DEFAULT 'queued',
            claimed_by TEXT,
            created_at TEXT,
            done_at TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            session TEXT,
            account TEXT,
            detail TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS meta (
            k TEXT PRIMARY KEY,
            v TEXT
        );
        """
    )
    conn.execute("INSERT OR IGNORE INTO meta(k, v) VALUES ('schema_version', '1')")
    conn.commit()
