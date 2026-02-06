# -*- coding: utf-8 -*-

import time
from typing import Any, Dict, Optional

from storage.db import Database


def _start_of_today_ts() -> int:
    now = time.time()
    lt = time.localtime(now)
    start = time.mktime(
        (
            lt.tm_year,
            lt.tm_mon,
            lt.tm_mday,
            0,
            0,
            0,
            lt.tm_wday,
            lt.tm_yday,
            lt.tm_isdst,
        )
    )
    return int(start)


class StatsService:
    def __init__(self, db: Database):
        self.db = db

    def get_db_info(self) -> Dict[str, Any]:
        conn = self.db.connect()
        v = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        version = v["value"] if v else "unknown"

        tasks = conn.execute("SELECT COUNT(1) AS c FROM tasks").fetchone()["c"]
        sessions = conn.execute("SELECT COUNT(1) AS c FROM sessions").fetchone()["c"]
        return {
            "schema_version": version,
            "tasks_count": tasks,
            "sessions_count": sessions,
            "now_ts": int(time.time()),
        }

    def total_today_work_sec(self) -> int:
        conn = self.db.connect()
        start_ts = _start_of_today_ts()
        row = conn.execute(
            """
            SELECT COALESCE(SUM(duration_sec), 0) AS total
            FROM sessions
            WHERE kind='work'
              AND end_ts IS NOT NULL
              AND start_ts >= ?
            """,
            (start_ts,),
        ).fetchone()
        return int(row["total"] or 0)

    def total_task_work_sec(self, task_id: str, since_ts: Optional[int] = None) -> int:
        conn = self.db.connect()
        if since_ts is None:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(duration_sec), 0) AS total
                FROM sessions
                WHERE kind='work'
                  AND end_ts IS NOT NULL
                  AND task_id = ?
                """,
                (task_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(duration_sec), 0) AS total
                FROM sessions
                WHERE kind='work'
                  AND end_ts IS NOT NULL
                  AND task_id = ?
                  AND start_ts >= ?
                """,
                (task_id, since_ts),
            ).fetchone()

        return int(row["total"] or 0)
