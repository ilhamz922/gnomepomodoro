# storage/repos.py  (REPLACE)
# -*- coding: utf-8 -*-

import time
import uuid
from typing import List, Optional

from domain.models import SessionLog, Task
from storage.db import Database


def _now_ts() -> int:
    return int(time.time())


def _uuid() -> str:
    return str(uuid.uuid4())


class TaskRepo:
    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str, status: str = "todo") -> Task:
        ts = _now_ts()
        task_id = _uuid()
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO tasks(id, title, status, created_at, updated_at) VALUES(?,?,?,?,?)",
            (task_id, title, status, ts, ts),
        )
        conn.commit()
        return Task(
            id=task_id, title=title, status=status, created_at=ts, updated_at=ts
        )

    def list(self, status: Optional[str] = None) -> List[Task]:
        conn = self.db.connect()
        if status is None:
            rows = conn.execute(
                "SELECT id, title, status, created_at, updated_at FROM tasks ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, status, created_at, updated_at FROM tasks WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()

        return [
            Task(
                id=r["id"],
                title=r["title"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get(self, task_id: str) -> Optional[Task]:
        conn = self.db.connect()
        r = conn.execute(
            "SELECT id, title, status, created_at, updated_at FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if not r:
            return None
        return Task(
            id=r["id"],
            title=r["title"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def set_status(self, task_id: str, status: str) -> None:
        ts = _now_ts()
        conn = self.db.connect()
        conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (status, ts, task_id),
        )
        conn.commit()

    def rename(self, task_id: str, title: str) -> None:
        ts = _now_ts()
        conn = self.db.connect()
        conn.execute(
            "UPDATE tasks SET title=?, updated_at=? WHERE id=?",
            (title, ts, task_id),
        )
        conn.commit()


class SessionRepo:
    def __init__(self, db: Database):
        self.db = db

    def start_session(
        self, task_id: str, kind: str, start_ts: Optional[int] = None
    ) -> SessionLog:
        sid = _uuid()
        ts = start_ts if start_ts is not None else _now_ts()
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO sessions(id, task_id, kind, start_ts, end_ts, duration_sec) VALUES(?,?,?,?,?,?)",
            (sid, task_id, kind, ts, None, None),
        )
        conn.commit()
        return SessionLog(
            id=sid,
            task_id=task_id,
            kind=kind,
            start_ts=ts,
            end_ts=None,
            duration_sec=None,
        )

    def end_session(self, session_id: str, end_ts: Optional[int] = None) -> None:
        ts_end = end_ts if end_ts is not None else _now_ts()
        conn = self.db.connect()
        row = conn.execute(
            "SELECT start_ts FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return
        start_ts = int(row["start_ts"])
        duration = max(0, ts_end - start_ts)

        conn.execute(
            "UPDATE sessions SET end_ts=?, duration_sec=? WHERE id=?",
            (ts_end, duration, session_id),
        )
        conn.commit()


class AppStateRepo:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str) -> Optional[str]:
        conn = self.db.connect()
        r = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def set(self, key: str, value: Optional[str]) -> None:
        conn = self.db.connect()
        conn.execute(
            """
            INSERT INTO app_state(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        conn.commit()
