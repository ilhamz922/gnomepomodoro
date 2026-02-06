# ui/todo_window.py  (REPLACE)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import tkinter as tk
from typing import Dict, Optional

from services.stats_service import StatsService
from services.task_service import TaskService
from storage.db import Database
from storage.repos import AppStateRepo


def _fmt_hms(sec: int) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


class TodoWindow:
    def __init__(self, task_service: TaskService, stats_service: StatsService):
        self.task_service = task_service
        self.stats_service = stats_service

        # Use same DB for app_state
        self._db = Database(db_path="pomodoro.db")
        self._db.init_schema()
        self._state_repo = AppStateRepo(self._db)

        self.root = tk.Tk()
        self.root.title("Todo List")
        self.root.geometry("360x560")

        self.bg_color = "#4A90E2"
        self.text_color = "white"

        self.root.attributes("-topmost", True)
        self.root.lift()

        for ev in ("<FocusOut>", "<FocusIn>", "<Map>", "<Unmap>", "<Visibility>"):
            self.root.bind(ev, lambda e: self._nudge_topmost())
        self.root.bind("<Control-Shift-Up>", lambda e: self._force_raise())

        self._dragging = False
        self._drag_start = (0, 0)
        self._win_start = (0, 0)
        self.root.bind("<ButtonPress-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_motion)
        self.root.bind("<ButtonRelease-1>", self._on_drag_end)

        self.active_task_id: Optional[str] = None
        self._list_index_to_task_id: Dict[int, str] = {}
        self._status_filter = "todo"

        self._build_ui()
        self._refresh_all()

    def _safe_image(self, filename):
        try:
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", filename
            )
            path = os.path.abspath(path)
            if os.path.exists(path):
                return tk.PhotoImage(file=path)
        except Exception:
            pass
        return None

    def _nudge_topmost(self):
        try:
            self.root.attributes("-topmost", False)
            self.root.after(
                10, lambda: (self.root.lift(), self.root.attributes("-topmost", True))
            )
        except Exception:
            pass

    def _force_raise(self):
        self.root.lift()
        self.root.attributes("-topmost", True)

    def _on_drag_start(self, event):
        if event.widget == self.task_entry:
            return
        self._dragging = True
        self._drag_start = (event.x_root, event.y_root)
        try:
            geo = self.root.geometry()
            _, pos = geo.split("+", 1)
            x_str, y_str = pos.split("+", 1)
            self._win_start = (int(x_str), int(y_str))
        except Exception:
            self._win_start = (self.root.winfo_x(), self.root.winfo_y())

    def _on_drag_motion(self, event):
        if not self._dragging:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        new_x = max(0, self._win_start[0] + int(dx))
        new_y = max(0, self._win_start[1] + int(dy))
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_drag_end(self, event):
        self._dragging = False

    def _build_ui(self):
        self.root.configure(bg=self.bg_color)

        main = tk.Frame(self.root, bg=self.bg_color)
        main.pack(expand=True, fill="both", padx=12, pady=12)

        title = tk.Label(
            main,
            text="Todo List",
            font=("Montserrat", 16, "bold"),
            fg=self.text_color,
            bg=self.bg_color,
        )
        title.pack(anchor="w", pady=(0, 6))

        subtitle = tk.Label(
            main,
            text="Pick task → open Pomodoro",
            font=("Montserrat", 9),
            fg=self.text_color,
            bg=self.bg_color,
        )
        subtitle.pack(anchor="w", pady=(0, 10))

        self.task_entry = tk.Entry(
            main,
            font=("Montserrat", 10),
            fg="white",
            bg=self.bg_color,
            relief="flat",
            justify="center",
            highlightthickness=1,
            highlightbackground="white",
            highlightcolor="white",
            borderwidth=0,
            insertbackground="white",
        )
        self.task_entry.insert(0, "type your task here")
        self.task_entry.pack(fill="x", pady=(0, 10))
        self.task_entry.bind("<FocusIn>", self._on_task_focus_in)
        self.task_entry.bind("<FocusOut>", self._on_task_focus_out)
        self.task_entry.bind("<Return>", lambda e: self._add_task())

        filter_bar = tk.Frame(main, bg=self.bg_color)
        filter_bar.pack(fill="x", pady=(0, 10))

        self.btn_todo = self._make_chip(
            filter_bar, "TODO", lambda: self._set_filter("todo")
        )
        self.btn_doing = self._make_chip(
            filter_bar, "DOING", lambda: self._set_filter("doing")
        )
        self.btn_done = self._make_chip(
            filter_bar, "DONE", lambda: self._set_filter("done")
        )

        self.btn_todo.pack(side="left", padx=(0, 6))
        self.btn_doing.pack(side="left", padx=(0, 6))
        self.btn_done.pack(side="left")

        list_frame = tk.Frame(
            main, bg=self.bg_color, highlightthickness=1, highlightbackground="white"
        )
        list_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.task_list = tk.Listbox(
            list_frame,
            font=("Montserrat", 10),
            fg="white",
            bg=self.bg_color,
            selectbackground="white",
            selectforeground=self.bg_color,
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
        )
        self.task_list.pack(fill="both", expand=True, padx=6, pady=6)
        self.task_list.bind("<<ListboxSelect>>", self._on_select_task)

        actions = tk.Frame(main, bg=self.bg_color)
        actions.pack(fill="x", pady=(0, 10))

        self.add_btn = tk.Button(
            actions,
            text="＋ Add",
            command=self._add_task,
            fg="white",
            bg=self.bg_color,
            activebackground=self.bg_color,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Montserrat", 10, "bold"),
        )
        self.add_btn.pack(side="left")

        self.doing_btn = tk.Button(
            actions,
            text="→ Doing",
            command=lambda: self._set_status_selected("doing"),
            fg="white",
            bg=self.bg_color,
            activebackground=self.bg_color,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Montserrat", 10, "bold"),
        )
        self.doing_btn.pack(side="left", padx=(10, 0))

        self.done_btn = tk.Button(
            actions,
            text="✓ Done",
            command=lambda: self._set_status_selected("done"),
            fg="white",
            bg=self.bg_color,
            activebackground=self.bg_color,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Montserrat", 10, "bold"),
        )
        self.done_btn.pack(side="left", padx=(10, 0))

        self.pomo_btn = tk.Button(
            actions,
            text="⏱ Pomodoro",
            command=self._open_pomodoro_for_selected,
            fg="white",
            bg=self.bg_color,
            activebackground=self.bg_color,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Montserrat", 10, "bold"),
        )
        self.pomo_btn.pack(side="left", padx=(10, 0))

        self.refresh_btn = tk.Button(
            actions,
            text="↻",
            command=self._refresh_all,
            fg="white",
            bg=self.bg_color,
            activebackground=self.bg_color,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Montserrat", 12, "bold"),
        )
        self.refresh_btn.pack(side="right")

        stats = tk.Frame(
            main, bg=self.bg_color, highlightthickness=1, highlightbackground="white"
        )
        stats.pack(fill="x")

        self.stats_label = tk.Label(
            stats,
            text="Today: -\nSelected: -",
            font=("Montserrat", 9),
            fg="white",
            bg=self.bg_color,
            justify="left",
        )
        self.stats_label.pack(anchor="w", padx=8, pady=8)

        self.err_label = tk.Label(
            main, text="", font=("Montserrat", 8), fg="white", bg=self.bg_color
        )
        self.err_label.pack(anchor="w", pady=(8, 0))

        self._update_filter_chips()

    def _make_chip(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            fg="white",
            bg=self.bg_color,
            activebackground="white",
            activeforeground=self.bg_color,
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="white",
            highlightcolor="white",
            font=("Montserrat", 8, "bold"),
            padx=10,
            pady=4,
        )

    def _update_filter_chips(self):
        def style(btn, active: bool):
            if active:
                btn.configure(
                    bg="white",
                    fg=self.bg_color,
                    activebackground="white",
                    activeforeground=self.bg_color,
                )
            else:
                btn.configure(
                    bg=self.bg_color,
                    fg="white",
                    activebackground="white",
                    activeforeground=self.bg_color,
                )

        style(self.btn_todo, self._status_filter == "todo")
        style(self.btn_doing, self._status_filter == "doing")
        style(self.btn_done, self._status_filter == "done")

    def _on_task_focus_in(self, event):
        if self.task_entry.get() == "type your task here":
            self.task_entry.delete(0, tk.END)

    def _on_task_focus_out(self, event):
        if self.task_entry.get().strip() == "":
            self.task_entry.insert(0, "type your task here")

    def _set_filter(self, status: str):
        self._status_filter = status
        self.active_task_id = None
        self._update_filter_chips()
        self._refresh_tasks_only()
        self._refresh_stats_only()

    def _add_task(self):
        title = (self.task_entry.get() or "").strip()
        if title == "" or title == "type your task here":
            self.err_label.config(text="Task title cannot be empty.")
            return

        try:
            self.task_service.create_task(title)
            self.task_entry.delete(0, tk.END)
            self.task_entry.insert(0, "type your task here")
            self.err_label.config(text="")
            self._refresh_all()
        except Exception as e:
            self.err_label.config(text=str(e))

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
        self._refresh_stats_only()

    def _set_status_selected(self, status: str):
        if not self.active_task_id:
            self.err_label.config(text="Select a task first.")
            return
        try:
            self.task_service.set_status(self.active_task_id, status)
            self.err_label.config(text="")
            self.active_task_id = None
            self._refresh_all()
        except Exception as e:
            self.err_label.config(text=str(e))

    def _open_pomodoro_for_selected(self):
        if not self.active_task_id:
            self.err_label.config(text="Select a task first.")
            return

        # Persist selection for pomodoro.py to read
        self._state_repo.set("active_task_id", self.active_task_id)

        # Optional: auto set doing (so you see it in DOING tab)
        try:
            self.task_service.set_status(self.active_task_id, "doing")
        except Exception:
            pass

        self.err_label.config(text="")

        # Launch pomodoro.py
        try:
            subprocess.Popen([sys.executable, "pomodoro.py"], cwd=os.getcwd())
        except Exception as e:
            self.err_label.config(text=str(e))

        self._refresh_all()

    def _refresh_all(self):
        self._refresh_tasks_only()
        self._refresh_stats_only()

    def _refresh_tasks_only(self):
        tasks = self.task_service.list_tasks(status=self._status_filter)

        self.task_list.delete(0, tk.END)
        self._list_index_to_task_id.clear()

        for i, t in enumerate(tasks):
            self.task_list.insert(tk.END, f"{t.title}")
            self._list_index_to_task_id[i] = t.id

    def _refresh_stats_only(self):
        today = self.stats_service.total_today_work_sec()
        if self.active_task_id:
            selected_total = self.stats_service.total_task_work_sec(self.active_task_id)
            task = self.task_service.get_task(self.active_task_id)
            title = task.title if task else "(unknown)"
            self.stats_label.config(
                text=f"Today (work): {_fmt_hms(today)}\nSelected: {_fmt_hms(selected_total)} — {title}"
            )
        else:
            self.stats_label.config(
                text=f"Today (work): {_fmt_hms(today)}\nSelected: -"
            )

    def run(self):
        self.root.mainloop()
