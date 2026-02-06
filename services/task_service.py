# -*- coding: utf-8 -*-

from typing import List, Optional

from domain.models import Task
from storage.repos import TaskRepo


class TaskService:
    def __init__(self, repo: TaskRepo):
        self.repo = repo

    def create_task(self, title: str) -> Task:
        title = (title or "").strip()
        if not title:
            raise ValueError("Task title cannot be empty.")
        return self.repo.create(title=title, status="todo")

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        return self.repo.list(status=status)

    def set_status(self, task_id: str, status: str) -> None:
        self.repo.set_status(task_id, status)

    def rename(self, task_id: str, title: str) -> None:
        title = (title or "").strip()
        if not title:
            raise ValueError("Task title cannot be empty.")
        self.repo.rename(task_id, title)

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.repo.get(task_id)
