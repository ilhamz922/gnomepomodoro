# storage/repos.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

from storage.db import Database


def _now_ts() -> int:
    return int(time.time())


@dataclass
class Task:
    id: str
    title: str
    status: str
    notes_md: str = ""
    due_date: Optional[str] = None  # yyyy-mm-dd
    priority: str = "P2"
    repeat_rule: str = "none"
    created_at: str = ""
    updated_at: str = ""


class AppStateRepo:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str) -> Optional[str]:
        row = self.db.conn.execute(
            "SELECT value FROM app_state WHERE key=?",
            (key,),
        ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        self.db.conn.execute(
            """
            INSERT INTO app_state(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        self.db.conn.commit()

    def delete(self, key: str) -> None:
        self.db.conn.execute("DELETE FROM app_state WHERE key=?", (key,))
        self.db.conn.commit()


class TaskRepo:
    def __init__(self, db: Database):
        self.db = db
        self._ensure_repeat_rule_column()

    def _ensure_repeat_rule_column(self) -> None:
        # SQLite: add column if missing
        try:
            cols = self.db.conn.execute("PRAGMA table_info(tasks)").fetchall()
            names = {c["name"] for c in cols} if cols else set()
            if "repeat_rule" not in names:
                self.db.conn.execute(
                    "ALTER TABLE tasks ADD COLUMN repeat_rule TEXT DEFAULT 'none'"
                )
                self.db.conn.commit()
        except Exception:
            # If PRAGMA fails for any reason, don't crash app startup.
            pass

    def create(
        self,
        title: str,
        status: str = "todo",
        notes_md: str = "",
        due_date: Optional[str] = None,
        priority: str = "P2",
        repeat_rule: str = "none",
    ) -> Task:
        tid = str(uuid.uuid4())
        ts = _now_ts()
        rr = (repeat_rule or "none").strip().lower()
        if rr not in ("none", "daily", "weekly", "monthly"):
            rr = "none"

        self.db.conn.execute(
            """
            INSERT INTO tasks(
                id, title, status, created_at, updated_at,
                notes_md, due_date, priority, repeat_rule
            )
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                tid,
                title,
                status,
                ts,
                ts,
                notes_md or "",
                due_date,
                (priority or "P2"),
                rr,
            ),
        )
        self.db.conn.commit()
        return self.get(tid)

    def list(self, status: Optional[str] = None) -> List[Task]:
        if status:
            rows = self.db.conn.execute(
                """
                SELECT id, title, status, created_at, updated_at,
                       notes_md, due_date, priority,
                       COALESCE(repeat_rule,'none') AS repeat_rule
                FROM tasks WHERE status=? ORDER BY updated_at DESC
                """,
                (status,),
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                """
                SELECT id, title, status, created_at, updated_at,
                       notes_md, due_date, priority,
                       COALESCE(repeat_rule,'none') AS repeat_rule
                FROM tasks ORDER BY updated_at DESC
                """
            ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get(self, task_id: str) -> Optional[Task]:
        r = self.db.conn.execute(
            """
            SELECT id, title, status, created_at, updated_at,
                   notes_md, due_date, priority,
                   COALESCE(repeat_rule,'none') AS repeat_rule
            FROM tasks WHERE id=?
            """,
            (task_id,),
        ).fetchone()
        return Task(**dict(r)) if r else None

    def set_status(self, task_id: str, status: str) -> None:
        ts = _now_ts()
        self.db.conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (status, ts, task_id),
        )
        self.db.conn.commit()

    def rename(self, task_id: str, title: str) -> None:
        ts = _now_ts()
        self.db.conn.execute(
            "UPDATE tasks SET title=?, updated_at=? WHERE id=?",
            (title, ts, task_id),
        )
        self.db.conn.commit()

    def set_due_date(self, task_id: str, due_date: Optional[str]) -> None:
        ts = _now_ts()
        self.db.conn.execute(
            "UPDATE tasks SET due_date=?, updated_at=? WHERE id=?",
            (due_date, ts, task_id),
        )
        self.db.conn.commit()

    def set_priority(self, task_id: str, priority: str) -> None:
        ts = _now_ts()
        self.db.conn.execute(
            "UPDATE tasks SET priority=?, updated_at=? WHERE id=?",
            (priority, ts, task_id),
        )
        self.db.conn.commit()

    def set_repeat_rule(self, task_id: str, repeat_rule: str) -> None:
        ts = _now_ts()
        rr = (repeat_rule or "none").strip().lower()
        if rr not in ("none", "daily", "weekly", "monthly"):
            rr = "none"
        self.db.conn.execute(
            "UPDATE tasks SET repeat_rule=?, updated_at=? WHERE id=?",
            (rr, ts, task_id),
        )
        self.db.conn.commit()

    def delete_task(self, task_id: str) -> None:
        # cascade deletes deps because FK ON DELETE CASCADE
        self.db.conn.execute("DELETE FROM sessions WHERE task_id=?", (task_id,))
        self.db.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.db.conn.commit()

    # ---- notes ----
    def get_notes_md(self, task_id: str) -> str:
        r = self.db.conn.execute(
            "SELECT notes_md FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        return r["notes_md"] if r and r["notes_md"] is not None else ""

    def set_notes_md(self, task_id: str, notes_md: str) -> None:
        ts = _now_ts()
        self.db.conn.execute(
            "UPDATE tasks SET notes_md=?, updated_at=? WHERE id=?",
            (notes_md, ts, task_id),
        )
        self.db.conn.commit()

    # ---- deps ----
    def add_dep(self, task_id: str, dep_id: str, kind: str) -> None:
        ts = _now_ts()
        self.db.conn.execute(
            "INSERT OR IGNORE INTO task_deps(task_id, dep_id, kind, created_at) VALUES(?,?,?,?)",
            (task_id, dep_id, kind, ts),
        )
        self.db.conn.commit()

    def remove_dep(self, task_id: str, dep_id: str, kind: str) -> None:
        self.db.conn.execute(
            "DELETE FROM task_deps WHERE task_id=? AND dep_id=? AND kind=?",
            (task_id, dep_id, kind),
        )
        self.db.conn.commit()

    def list_deps(self, task_id: str, kind: str) -> List[str]:
        rows = self.db.conn.execute(
            "SELECT dep_id FROM task_deps WHERE task_id=? AND kind=? ORDER BY created_at ASC",
            (task_id, kind),
        ).fetchall()
        return [r["dep_id"] for r in rows]
