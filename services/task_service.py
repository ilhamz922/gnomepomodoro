# services/task_service.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Set

from storage.db import Database
from storage.repos import AppStateRepo, Task, TaskRepo

PRIORITY_WEIGHT = {"P0": 20, "P1": 5, "P2": 0}
REPEAT_RULES = ("none", "daily", "weekly", "monthly")


class TaskService:
    def __init__(self, db: Database):
        self.db = db
        self.tasks = TaskRepo(db)
        self.state = AppStateRepo(db)
        # optional hook from UI for debug
        self.debug_hook = None

    def _dbg(self, msg: str):
        if callable(self.debug_hook):
            try:
                self.debug_hook(msg)
            except Exception:
                pass

    # ---- tasks ----
    def create_task(self, title: str) -> Task:
        title = (title or "").strip()
        if not title:
            raise ValueError("Task title cannot be empty.")
        return self.tasks.create(title=title, status="todo")

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        return self.tasks.list(status=status)

    def list_all_tasks(self) -> List[Task]:
        return self.tasks.list(status=None)

    def set_status(self, task_id: str, status: str) -> None:
        if status not in ("todo", "doing", "done"):
            raise ValueError("Invalid status.")
        if not self.tasks.get(task_id):
            raise ValueError("Task not found.")
        self.tasks.set_status(task_id, status)

    def rename_task(self, task_id: str, title: str) -> None:
        title = (title or "").strip()
        if not title:
            raise ValueError("Name cannot be empty.")
        if not self.tasks.get(task_id):
            raise ValueError("Task not found.")
        self.tasks.rename(task_id, title)

    def set_due_date(self, task_id: str, due: str) -> None:
        due = (due or "").strip()
        if not self.tasks.get(task_id):
            raise ValueError("Task not found.")
        if due == "":
            self.tasks.set_due_date(task_id, None)
            return
        # validate yyyy-mm-dd
        try:
            dt.date.fromisoformat(due)
        except Exception:
            raise ValueError("Invalid date. Use YYYY-MM-DD.")
        self.tasks.set_due_date(task_id, due)

    def set_priority(self, task_id: str, pr: str) -> None:
        pr = (pr or "P2").strip().upper()
        if pr not in ("P0", "P1", "P2"):
            raise ValueError("Invalid priority. Use P0/P1/P2.")
        if not self.tasks.get(task_id):
            raise ValueError("Task not found.")
        self.tasks.set_priority(task_id, pr)

    # ---- repeat ----
    def set_repeat_rule(self, task_id: str, rule: str) -> None:
        if not self.tasks.get(task_id):
            raise ValueError("Task not found.")
        rule = (rule or "none").strip().lower()
        if rule not in REPEAT_RULES:
            raise ValueError("Invalid repeat rule. Use none/daily/weekly/monthly.")
        self.tasks.set_repeat_rule(task_id, rule)

    def get_repeat_rule(self, task_id: str) -> str:
        t = self.tasks.get(task_id)
        if not t:
            return "none"
        r = (getattr(t, "repeat_rule", None) or "none").strip().lower()
        return r if r in REPEAT_RULES else "none"

    def delete_task(self, task_id: str) -> None:
        active = self.state.get("active_task_id")
        if active and active == task_id:
            self.state.delete("active_task_id")
        self.tasks.delete_task(task_id)

    # ---- notes (markdown) ----
    def get_notes_md(self, task_id: str) -> str:
        t = self.tasks.get(task_id)
        if not t:
            return ""
        return self.tasks.get_notes_md(task_id) or ""

    def set_notes_md(self, task_id: str, md: str) -> None:
        if not self.tasks.get(task_id):
            raise ValueError("Task not found.")
        self.tasks.set_notes_md(task_id, md or "")

    # ---- deps ----
    def add_blocker(self, task_id: str, blocker_task_id: str) -> None:
        self._add_dep(task_id, blocker_task_id, "blocker")

    def add_waiting_on(self, task_id: str, waiting_task_id: str) -> None:
        self._add_dep(task_id, waiting_task_id, "waiting")

    def _add_dep(self, task_id: str, dep_id: str, kind: str) -> None:
        if kind not in ("blocker", "waiting"):
            raise ValueError("Invalid dep kind.")
        if not task_id or not dep_id:
            raise ValueError("Invalid dependency target.")
        if task_id == dep_id:
            raise ValueError("Task cannot depend on itself.")
        if not self.tasks.get(task_id):
            raise ValueError("Task not found (target).")
        if not self.tasks.get(dep_id):
            raise ValueError("Task not found (dep).")

        # avoid trivial duplicates (INSERT OR IGNORE)
        self.tasks.add_dep(task_id, dep_id, kind)

    def remove_blocker(self, task_id: str, blocker_task_id: str) -> None:
        self.tasks.remove_dep(task_id, blocker_task_id, "blocker")

    def remove_waiting_on(self, task_id: str, waiting_task_id: str) -> None:
        self.tasks.remove_dep(task_id, waiting_task_id, "waiting")

    def list_blockers(self, task_id: str) -> List[str]:
        return self.tasks.list_deps(task_id, "blocker")

    def list_waiting_on(self, task_id: str) -> List[str]:
        return self.tasks.list_deps(task_id, "waiting")

    # ---- repeat lifecycle ----
    def complete_task(self, task_id: str) -> Optional[str]:
        """
        Mark task as done.
        If task has repeat_rule, auto-create a new instance in TODO and return new task_id.
        """
        t = self.tasks.get(task_id)
        if not t:
            raise ValueError("Task not found.")

        self.tasks.set_status(task_id, "done")

        rule = (getattr(t, "repeat_rule", None) or "none").strip().lower()
        if rule not in REPEAT_RULES or rule == "none":
            return None

        next_due = self._compute_next_due_date(t.due_date, rule)
        new_task = self.tasks.create(
            title=t.title,
            status="todo",
            notes_md=t.notes_md or "",
            due_date=next_due,
            priority=(t.priority or "P2").upper(),
            repeat_rule=rule,
        )
        return new_task.id

    def _compute_next_due_date(
        self, due_date: Optional[str], rule: str
    ) -> Optional[str]:
        rule = (rule or "none").strip().lower()
        if rule not in REPEAT_RULES or rule == "none":
            return due_date

        base = None
        if due_date:
            try:
                base = dt.date.fromisoformat(due_date)
            except Exception:
                base = None
        if base is None:
            base = dt.date.today()

        if rule == "daily":
            nxt = base + dt.timedelta(days=1)
        elif rule == "weekly":
            nxt = base + dt.timedelta(days=7)
        elif rule == "monthly":
            # month add (preserve day where possible)
            y = base.year
            m = base.month + 1
            if m > 12:
                m = 1
                y += 1

            # clamp day to last day of target month
            import calendar as _cal

            last_day = _cal.monthrange(y, m)[1]
            d = min(base.day, last_day)
            nxt = dt.date(y, m, d)
        else:
            nxt = base

        return nxt.isoformat()

    # ---- scoring ----
    def prioritization_scores(self) -> Dict[str, int]:
        all_tasks = self.list_all_tasks()
        task_by_id: Dict[str, Task] = {t.id: t for t in all_tasks}

        def base_score(t: Task) -> int:
            due_score = 0
            if t.due_date:
                try:
                    due = dt.date.fromisoformat(t.due_date)
                    today = dt.date.today()
                    days_until = (due - today).days
                    if days_until < 0:
                        days_until = 0
                    if days_until > 25:
                        days_until = 25
                    due_score = 25 - days_until
                except Exception:
                    due_score = 0

            pr = (t.priority or "P2").strip().upper()
            pr_score = PRIORITY_WEIGHT.get(pr, 0)

            # small nudge for repeating tasks so they don't get buried
            rr = (getattr(t, "repeat_rule", None) or "none").strip().lower()
            rep_score = 2 if rr in ("daily", "weekly", "monthly") else 0

            return int(due_score + pr_score + rep_score)

        memo: Dict[str, int] = {}

        def total_score(task_id: str, visiting: Set[str]) -> int:
            if task_id in memo:
                return memo[task_id]
            if task_id in visiting:
                return 0
            visiting.add(task_id)

            t = task_by_id.get(task_id)
            if not t:
                visiting.remove(task_id)
                return 0

            score = base_score(t)

            blockers = self.list_blockers(task_id)
            for bid in blockers:
                score += total_score(bid, visiting)

            visiting.remove(task_id)
            memo[task_id] = int(score)
            return memo[task_id]

        out: Dict[str, int] = {}
        for t in all_tasks:
            out[t.id] = total_score(t.id, set())

        return out
