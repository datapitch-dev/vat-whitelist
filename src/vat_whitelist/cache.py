"""SQLite cache of lookups and a per-day counter of API requests.

A re-run for the same date reads from the cache, so it costs no requests. When the daily limit
runs out mid-list, the next day's run picks up only the NIPs that are still missing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lookups (
    nip TEXT NOT NULL,
    date TEXT NOT NULL,
    request_id TEXT NOT NULL,
    subjects TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (nip, date)
);
CREATE TABLE IF NOT EXISTS usage (
    day TEXT PRIMARY KEY,
    requests INTEGER NOT NULL
);
"""


class Cache:
    def __init__(self, path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(_SCHEMA)

    def get(self, nip: str, date: str) -> tuple[str, list[dict]] | None:
        row = self.conn.execute(
            "SELECT request_id, subjects FROM lookups WHERE nip = ? AND date = ?", (nip, date)
        ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def put(self, nip: str, date: str, request_id: str, subjects: list[dict]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO lookups VALUES (?, ?, ?, ?, ?)",
            (
                nip,
                date,
                request_id,
                json.dumps(subjects, ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()

    def requests_today(self, today: str | None = None) -> int:
        today = today or date_cls.today().isoformat()
        row = self.conn.execute("SELECT requests FROM usage WHERE day = ?", (today,)).fetchone()
        return row[0] if row else 0

    def count_request(self, today: str | None = None) -> None:
        today = today or date_cls.today().isoformat()
        self.conn.execute(
            "INSERT INTO usage VALUES (?, 1) "
            "ON CONFLICT(day) DO UPDATE SET requests = requests + 1",
            (today,),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
