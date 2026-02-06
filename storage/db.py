# storage/db.py  (REPLACE)
# -*- coding: utf-8 -*-

import sqlite3
from typing import Optional


class Database:
    def __init__(self, db_path: str = "pomodoro.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        conn = self.connect()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('todo','doing','done')),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('work','break')),
                start_ts INTEGER NOT NULL,
                end_ts INTEGER,
                duration_sec INTEGER,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
        """)

        # app_state for cross-app coordination (todo_window -> pomodoro.py)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_task_id ON sessions(task_id);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_start_ts ON sessions(start_ts);"
        )

        cur.execute("""
            INSERT INTO schema_meta(key, value)
            VALUES('schema_version', '2')
            ON CONFLICT(key) DO UPDATE SET value=excluded.value;
        """)

        conn.commit()
