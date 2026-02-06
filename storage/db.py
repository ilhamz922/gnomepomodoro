# storage/db.py  (REPLACE) — adds notes_md column + safe migration
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3


class Database:
    def __init__(self, db_path: str = "pomodoro.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def init_schema(self):
        cur = self.conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # tasks (notes_md included)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                notes_md TEXT NOT NULL DEFAULT ''
            );
        """)

        # MIGRATION: if old DB doesn't have notes_md, add it
        cols = [r["name"] for r in cur.execute("PRAGMA table_info(tasks);").fetchall()]
        if "notes_md" not in cols:
            cur.execute(
                "ALTER TABLE tasks ADD COLUMN notes_md TEXT NOT NULL DEFAULT '';"
            )

        # sessions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_ts INTEGER NOT NULL,
                end_ts INTEGER,
                duration_sec INTEGER
            );
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);"
        )

        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
