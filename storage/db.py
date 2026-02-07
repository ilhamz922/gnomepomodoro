#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import time


class Database:
    def __init__(self, db_path: str = "pomodoro.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def _table_exists(self, name: str) -> bool:
        r = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return bool(r)

    def _cols(self, table: str):
        try:
            return [
                r["name"]
                for r in self.conn.execute(f"PRAGMA table_info({table});").fetchall()
            ]
        except Exception:
            return []

    def init_schema(self):
        cur = self.conn.cursor()

        # --- core tables ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # tasks (new schema)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                notes_md TEXT NOT NULL DEFAULT '',
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'P2'
            );
        """)

        # tasks migrations (if older tasks table existed)
        cols = self._cols("tasks")
        if "notes_md" not in cols:
            cur.execute(
                "ALTER TABLE tasks ADD COLUMN notes_md TEXT NOT NULL DEFAULT '';"
            )
        if "due_date" not in cols:
            cur.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT;")
        if "priority" not in cols:
            cur.execute(
                "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'P2';"
            )

        # --- deps table migration ---
        # Desired schema:
        # task_deps(task_id, dep_id, kind, created_at)
        if not self._table_exists("task_deps"):
            cur.execute("""
                CREATE TABLE IF NOT EXISTS task_deps (
                    task_id TEXT NOT NULL,
                    dep_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (task_id, dep_id, kind),
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(dep_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
            """)
        else:
            dcols = self._cols("task_deps")

            # If dep_id missing or schema is legacy → migrate
            needs_migrate = ("dep_id" not in dcols) or ("kind" not in dcols)
            if needs_migrate:
                old_name = f"task_deps_legacy_{int(time.time())}"
                cur.execute(f"ALTER TABLE task_deps RENAME TO {old_name};")

                # create new
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS task_deps (
                        task_id TEXT NOT NULL,
                        dep_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (task_id, dep_id, kind),
                        FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                        FOREIGN KEY(dep_id) REFERENCES tasks(id) ON DELETE CASCADE
                    );
                """)

                legacy_cols = self._cols(old_name)
                ts_now = int(time.time())

                # Best-effort copy from legacy formats
                # 1) If legacy already had (task_id, dep_id) but no kind
                if ("task_id" in legacy_cols) and ("dep_id" in legacy_cols):
                    # assume all are blockers (safe default), or try infer if legacy has "type"
                    if "kind" in legacy_cols:
                        cur.execute(f"""
                            INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at)
                            SELECT task_id, dep_id, kind, COALESCE(created_at, {ts_now}) FROM {old_name}
                        """)
                    elif "type" in legacy_cols:
                        cur.execute(f"""
                            INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at)
                            SELECT task_id, dep_id,
                                   CASE
                                     WHEN LOWER(type) IN ('waiting','waiting_on','waiting-on') THEN 'waiting'
                                     ELSE 'blocker'
                                   END,
                                   COALESCE(created_at, {ts_now})
                            FROM {old_name}
                        """)
                    else:
                        cur.execute(f"""
                            INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at)
                            SELECT task_id, dep_id, 'blocker', COALESCE(created_at, {ts_now}) FROM {old_name}
                        """)

                # 2) If legacy used blocker_task_id
                if ("task_id" in legacy_cols) and ("blocker_task_id" in legacy_cols):
                    cur.execute(f"""
                        INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at)
                        SELECT task_id, blocker_task_id, 'blocker', COALESCE(created_at, {ts_now})
                        FROM {old_name}
                        WHERE blocker_task_id IS NOT NULL AND blocker_task_id <> ''
                    """)

                # 3) If legacy used waiting_on_task_id
                if ("task_id" in legacy_cols) and ("waiting_on_task_id" in legacy_cols):
                    cur.execute(f"""
                        INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at)
                        SELECT task_id, waiting_on_task_id, 'waiting', COALESCE(created_at, {ts_now})
                        FROM {old_name}
                        WHERE waiting_on_task_id IS NOT NULL AND waiting_on_task_id <> ''
                    """)

                # 4) Another common name: depends_on_id
                if ("task_id" in legacy_cols) and ("depends_on_id" in legacy_cols):
                    cur.execute(f"""
                        INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at)
                        SELECT task_id, depends_on_id, 'blocker', COALESCE(created_at, {ts_now})
                        FROM {old_name}
                        WHERE depends_on_id IS NOT NULL AND depends_on_id <> ''
                    """)

                # Note: we intentionally keep legacy table (renamed) so you can recover if needed.
                # If you want to delete it later manually, you can DROP TABLE <old_name>;

        # --- sessions ---
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

        # --- indexes (safe: only create if columns exist) ---
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);"
        )

        dcols2 = self._cols("task_deps")
        if "task_id" in dcols2:
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_deps_task ON task_deps(task_id);"
            )
        if "dep_id" in dcols2:
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_deps_dep ON task_deps(dep_id);"
            )

        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
