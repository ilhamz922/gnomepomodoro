# services/task_service.py  (REPLACE) — remove subtasks, add markdown notes
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

from storage.db import Database
from storage.repos import AppStateRepo, Task, TaskRepo


class TaskService:
    def __init__(self, db: Database):
        self.db = db
        self.tasks = TaskRepo(db)
        self.state = AppStateRepo(db)

    # ---- tasks ----
    def create_task(self, title: str) -> Task:
        title = (title or "").strip()
        if not title:
            raise ValueError("Task title cannot be empty.")
        return self.tasks.create(title=title, status="todo")

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        return self.tasks.list(status=status)

    def set_status(self, task_id: str, status: str) -> None:
        if status not in ("todo", "doing", "done"):
            raise ValueError("Invalid status.")
        self.tasks.set_status(task_id, status)

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
