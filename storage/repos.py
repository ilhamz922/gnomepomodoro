# storage/repos.py  (REPLACE) — TaskRepo includes notes_md column
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
    created_at: int
    updated_at: int


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

    def create(self, title: str, status: str = "todo") -> Task:
        tid = str(uuid.uuid4())
        ts = _now_ts()
        self.db.conn.execute(
            "INSERT INTO tasks(id, title, status, created_at, updated_at, notes_md) VALUES(?,?,?,?,?,?)",
            (tid, title, status, ts, ts, ""),
        )
        self.db.conn.commit()
        return Task(id=tid, title=title, status=status, created_at=ts, updated_at=ts)

    def list(self, status: Optional[str] = None) -> List[Task]:
        if status:
            rows = self.db.conn.execute(
                "SELECT id, title, status, created_at, updated_at FROM tasks WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT id, title, status, created_at, updated_at FROM tasks ORDER BY updated_at DESC"
            ).fetchall()
        return [Task(**dict(r)) for r in rows]

    def get(self, task_id: str) -> Optional[Task]:
        r = self.db.conn.execute(
            "SELECT id, title, status, created_at, updated_at FROM tasks WHERE id=?",
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

    def delete_task(self, task_id: str) -> None:
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
