#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from ui.todo_window import TodoWindow

from services.stats_service import StatsService
from services.task_service import TaskService
from storage.db import Database
from storage.repos import SessionRepo, TaskRepo


def main():
    db = Database(db_path="pomodoro.db")
    db.init_schema()

    task_repo = TaskRepo(db)
    session_repo = SessionRepo(db)

    task_service = TaskService(task_repo)
    stats_service = StatsService(db)

    app = TodoWindow(task_service, stats_service)
    app.run()


if __name__ == "__main__":
    main()
