# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

from services.stats_service import StatsService
from services.task_service import TaskService
from services.timer_service import TimerService
from ui.pomodoro_widget import PomodoroWidget


def _fmt_hms(sec: int) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


class MainWindow:
    def __init__(
        self,
        task_service: TaskService,
        timer_service: TimerService,
        stats_service: StatsService,
    ):
        self.task_service = task_service
        self.timer_service = timer_service
        self.stats_service = stats_service

        self.root = tk.Tk()
        self.root.title("Pomodoro + Task Manager")
        self.root.geometry("860x420")

        self.active_task_id: Optional[str] = None
        self._list_index_to_task_id: Dict[int, str] = {}

        self._build_ui()
        self._refresh_all()

    def _build_ui(self):
        root = self.root

        outer = ttk.Frame(root, padding=10)
        outer.pack(fill="both", expand=True)

        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(0, weight=1)

        # LEFT: Tasks panel
        left = ttk.Labelframe(outer, text="Tasks", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        # add task row
        add_row = ttk.Frame(left)
        add_row.grid(row=0, column=0, sticky="ew")
        add_row.columnconfigure(0, weight=1)

        self.new_task_var = tk.StringVar()
        self.new_task_entry = ttk.Entry(add_row, textvariable=self.new_task_var)
        self.new_task_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(add_row, text="Add", command=self._add_task).grid(
            row=0, column=1, padx=(6, 0)
        )

        self.err_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.err_var, foreground="red").grid(
            row=1, column=0, sticky="w", pady=(6, 6)
        )

        # listbox
        self.task_list = tk.Listbox(left, height=12)
        self.task_list.grid(row=2, column=0, sticky="nsew")
        self.task_list.bind("<<ListboxSelect>>", self._on_select_task)

        # actions
        actions = ttk.Frame(left)
        actions.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self.done_btn = ttk.Button(
            actions, text="Mark Done (auto stop)", command=self._mark_done
        )
        self.done_btn.pack(side="left")

        self.refresh_btn = ttk.Button(
            actions, text="Refresh", command=self._refresh_all
        )
        self.refresh_btn.pack(side="right")

        # RIGHT: Pomodoro + Stats
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=0)
        right.rowconfigure(1, weight=1)

        self.pomodoro = PomodoroWidget(
            right,
            timer_service=self.timer_service,
            get_active_task_id=self.get_active_task_id,
            on_request_refresh=self._refresh_stats_only,
        )
        self.pomodoro.grid(row=0, column=0, sticky="ew")

        stats = ttk.Labelframe(right, text="Stats", padding=10)
        stats.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        stats.columnconfigure(0, weight=1)

        self.stats_var = tk.StringVar(value="")
        ttk.Label(stats, textvariable=self.stats_var, font=("Sans", 11)).grid(
            row=0, column=0, sticky="w"
        )

        self.active_var = tk.StringVar(value="Active task: (none)")
        ttk.Label(stats, textvariable=self.active_var).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

    def run(self):
        self.root.mainloop()

    # ----- Active task helpers -----
    def get_active_task_id(self) -> Optional[str]:
        return self.active_task_id

    def _on_select_task(self, event=None):
        try:
            sel = self.task_list.curselection()
            if not sel:
                self.active_task_id = None
            else:
                idx = int(sel[0])
                self.active_task_id = self._list_index_to_task_id.get(idx)
        except Exception:
            self.active_task_id = None

        self.timer_service.set_active_task(self.active_task_id)
        self._refresh_stats_only()

    # ----- UI actions -----
    def _add_task(self):
        title = self.new_task_var.get()
        try:
            self.task_service.create_task(title)
            self.new_task_var.set("")
            self.err_var.set("")
            self._refresh_tasks_only()
            self._refresh_stats_only()
        except Exception as e:
            self.err_var.set(str(e))

    def _mark_done(self):
        if not self.active_task_id:
            return
        self.timer_service.mark_done_and_stop(self.active_task_id)
        self._refresh_all()

    # ----- Refresh -----
    def _refresh_all(self):
        self._refresh_tasks_only()
        self._refresh_stats_only()

    def _refresh_tasks_only(self):
        tasks = self.task_service.list_tasks()

        # preserve selection if possible
        prev_active = self.active_task_id

        self.task_list.delete(0, tk.END)
        self._list_index_to_task_id.clear()

        selected_index = None
        for i, t in enumerate(tasks):
            label = f"[{t.status}] {t.title}"
            self.task_list.insert(tk.END, label)
            self._list_index_to_task_id[i] = t.id
            if prev_active and t.id == prev_active:
                selected_index = i

        if selected_index is not None:
            self.task_list.selection_set(selected_index)
            self.task_list.activate(selected_index)
            self.active_task_id = self._list_index_to_task_id.get(selected_index)
        else:
            # if no selection, clear
            if not tasks:
                self.active_task_id = None

        self.timer_service.set_active_task(self.active_task_id)

    def _refresh_stats_only(self):
        today = self.stats_service.total_today_work_sec()
        if self.active_task_id:
            active_total = self.stats_service.total_task_work_sec(self.active_task_id)
            task = self.task_service.get_task(self.active_task_id)
            title = task.title if task else "(unknown)"
            self.active_var.set(f"Active task: {title}")
            self.stats_var.set(
                f"Today (work): {_fmt_hms(today)}\nSelected task total (work): {_fmt_hms(active_total)}"
            )
        else:
            self.active_var.set("Active task: (none)")
            self.stats_var.set(
                f"Today (work): {_fmt_hms(today)}\nSelected task total (work): -"
            )
