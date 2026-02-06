# services/stats_service.py  (REPLACE)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from typing import Optional

from storage.db import Database


def _today_midnight_ts() -> int:
    """
    Returns local-time midnight timestamp for today.
    (Not UTC midnight, but your system local time / WIB)
    """
    now = time.time()
    lt = time.localtime(now)
    midnight_struct = (
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
    # mktime expects local time tuple
    return int(time.mktime(midnight_struct))


class StatsService:
    def __init__(self, db: Database):
        self.db = db

    def total_today_work_sec(self) -> int:
        """
        Sum duration_sec for all completed WORK sessions today (local day).
        """
        start = _today_midnight_ts()
        row = self.db.conn.execute(
            """
            SELECT COALESCE(SUM(duration_sec), 0) AS total
            FROM sessions
            WHERE kind='work'
              AND end_ts IS NOT NULL
              AND start_ts >= ?
            """,
            (start,),
        ).fetchone()
        return int(row["total"]) if row and row["total"] is not None else 0

    def total_task_work_sec(self, task_id: str) -> int:
        """
        Sum duration_sec for all completed WORK sessions for a given task_id (all time).
        """
        row = self.db.conn.execute(
            """
            SELECT COALESCE(SUM(duration_sec), 0) AS total
            FROM sessions
            WHERE kind='work'
              AND end_ts IS NOT NULL
              AND task_id = ?
            """,
            (task_id,),
        ).fetchone()
        return int(row["total"]) if row and row["total"] is not None else 0

    def total_task_break_sec(self, task_id: str) -> int:
        """
        Optional helper: Sum duration_sec for BREAK sessions for a given task_id (all time).
        """
        row = self.db.conn.execute(
            """
            SELECT COALESCE(SUM(duration_sec), 0) AS total
            FROM sessions
            WHERE kind='break'
              AND end_ts IS NOT NULL
              AND task_id = ?
            """,
            (task_id,),
        ).fetchone()
        return int(row["total"]) if row and row["total"] is not None else 0
