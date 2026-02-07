#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from services.stats_service import StatsService
from services.task_service import TaskService
from storage.db import Database
from ui.todo_window import TodoWindow


def main():
    db = Database(db_path="pomodoro.db")
    db.init_schema()

    task_service = TaskService(db)
    stats_service = StatsService(db)

    win = TodoWindow(task_service=task_service, stats_service=stats_service)
    win.run()

    db.close()


if __name__ == "__main__":
    main()
