# ui/todo_window.py  (REPLACE) — Modern Kanban (Todo/Doing/Done) + Start Pomodoro
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

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

        # Shared DB for app_state
        self._db = Database(db_path="pomodoro.db")
        self._db.init_schema()
        self._state_repo = AppStateRepo(self._db)

        self.root = tk.Tk()
        self.root.title("Tasks — Kanban")
        self.root.geometry("980x620")

        # ===== Modern palette =====
        self.bg = "#F4F6FA"
        self.panel = "#FFFFFF"
        self.border = "#E6EAF2"
        self.text = "#1F2937"
        self.muted = "#6B7280"
        self.accent = "#111827"
        self.green = "#10B981"
        self.blue = "#3B82F6"
        self.graybtn = "#EEF2F7"

        self.root.configure(bg=self.bg)

        # Optional AOT like pomodoro (feel free to turn off)
        # self.root.attributes("-topmost", True)
        # self.root.lift()

        # Drag window anywhere (except entry/list widgets)
        self._dragging = False
        self._drag_start = (0, 0)
        self._win_start = (0, 0)
        self.root.bind("<ButtonPress-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_motion)
        self.root.bind("<ButtonRelease-1>", self._on_drag_end)

        # selection
        self.active_task_id: Optional[str] = None
        self.active_task_title: Optional[str] = None
        self.active_task_status: Optional[str] = None

        # map listbox index -> task_id per column
        self._map_todo: Dict[int, str] = {}
        self._map_doing: Dict[int, str] = {}
        self._map_done: Dict[int, str] = {}

        # ttk styling (modern)
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self._build_ui()
        self._refresh_all()

    # ---------- Drag window ----------
    def _on_drag_start(self, event):
        # Don't drag when interacting with inputs/lists/buttons
        cls = event.widget.winfo_class()
        if cls in ("Entry", "Listbox", "TButton", "Button", "Scrollbar"):
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
        x = max(0, self._win_start[0] + int(dx))
        y = max(0, self._win_start[1] + int(dy))
        self.root.geometry(f"+{x}+{y}")

    def _on_drag_end(self, event):
        self._dragging = False

    # ---------- UI ----------
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self.root, bg=self.bg)
        top.pack(fill="x", padx=18, pady=(16, 10))

        title = tk.Label(
            top,
            text="Kanban Tasks",
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 18, "bold"),
        )
        title.pack(side="left")

        self.stats_top = tk.Label(
            top, text="Today: -", bg=self.bg, fg=self.muted, font=("Montserrat", 10)
        )
        self.stats_top.pack(side="left", padx=(14, 0))

        right = tk.Frame(top, bg=self.bg)
        right.pack(side="right")

        self.btn_refresh = tk.Button(
            right,
            text="Refresh",
            command=self._refresh_all,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            activebackground=self.graybtn,
            activeforeground=self.text,
            font=("Montserrat", 10, "bold"),
            padx=14,
            pady=8,
        )
        self.btn_refresh.pack(side="right", padx=(10, 0))

        self.btn_pomo = tk.Button(
            right,
            text="Start Pomodoro",
            command=self._open_pomodoro_for_selected,
            bg=self.accent,
            fg="white",
            relief="flat",
            bd=0,
            activebackground=self.accent,
            activeforeground="white",
            font=("Montserrat", 10, "bold"),
            padx=14,
            pady=8,
        )
        self.btn_pomo.pack(side="right")

        # Add task row
        addrow = tk.Frame(self.root, bg=self.bg)
        addrow.pack(fill="x", padx=18, pady=(0, 14))

        self.task_entry = tk.Entry(
            addrow,
            font=("Montserrat", 11),
            fg=self.text,
            bg=self.panel,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.border,
            insertbackground=self.text,
        )
        self.task_entry.pack(side="left", fill="x", expand=True, ipady=10)
        self.task_entry.insert(0, "Add a task and press Enter…")
        self.task_entry.bind("<FocusIn>", self._entry_focus_in)
        self.task_entry.bind("<FocusOut>", self._entry_focus_out)
        self.task_entry.bind("<Return>", lambda e: self._add_task())

        self.btn_add = tk.Button(
            addrow,
            text="Add",
            command=self._add_task,
            bg=self.blue,
            fg="white",
            relief="flat",
            bd=0,
            activebackground=self.blue,
            activeforeground="white",
            font=("Montserrat", 10, "bold"),
            padx=16,
            pady=10,
        )
        self.btn_add.pack(side="left", padx=(10, 0))

        # Main kanban area
        board = tk.Frame(self.root, bg=self.bg)
        board.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self.col_todo = self._make_column(
            board, "TODO", hint="Backlog / next up", color=self.blue
        )
        self.col_doing = self._make_column(
            board, "DOING", hint="In progress", color=self.green
        )
        self.col_done = self._make_column(
            board, "DONE", hint="Completed", color=self.muted
        )

        self.col_todo.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.col_doing.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.col_done.pack(side="left", fill="both", expand=True)

        # Bottom action bar
        bottom = tk.Frame(self.root, bg=self.bg)
        bottom.pack(fill="x", padx=18, pady=(0, 16))

        self.sel_label = tk.Label(
            bottom,
            text="Selected: -",
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 10),
        )
        self.sel_label.pack(side="left")

        self.btn_left = tk.Button(
            bottom,
            text="← Move Left",
            command=self._move_left,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            activebackground=self.graybtn,
            activeforeground=self.text,
            font=("Montserrat", 10, "bold"),
            padx=12,
            pady=8,
        )
        self.btn_left.pack(side="right", padx=(10, 0))

        self.btn_right = tk.Button(
            bottom,
            text="Move Right →",
            command=self._move_right,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            activebackground=self.graybtn,
            activeforeground=self.text,
            font=("Montserrat", 10, "bold"),
            padx=12,
            pady=8,
        )
        self.btn_right.pack(side="right")

        self.err = tk.Label(
            self.root, text="", bg=self.bg, fg="#EF4444", font=("Montserrat", 9)
        )
        self.err.pack(anchor="w", padx=18)

        # Keybinds
        self.root.bind("<Control-Return>", lambda e: self._open_pomodoro_for_selected())
        self.root.bind("<Control-Left>", lambda e: self._move_left())
        self.root.bind("<Control-Right>", lambda e: self._move_right())

    def _make_column(self, parent, title: str, hint: str, color: str):
        wrap = tk.Frame(parent, bg=self.bg)

        head = tk.Frame(wrap, bg=self.bg)
        head.pack(fill="x")

        dot = tk.Frame(head, bg=color, width=10, height=10)
        dot.pack(side="left", pady=6)
        dot.pack_propagate(False)

        self._count_vars = getattr(self, "_count_vars", {})
        count_var = tk.StringVar(value="0")
        self._count_vars[title.lower()] = count_var

        lbl = tk.Label(
            head, text=title, bg=self.bg, fg=self.text, font=("Montserrat", 12, "bold")
        )
        lbl.pack(side="left", padx=(8, 6))

        cnt = tk.Label(
            head,
            textvariable=count_var,
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 10, "bold"),
        )
        cnt.pack(side="left")

        hintlbl = tk.Label(
            wrap, text=hint, bg=self.bg, fg=self.muted, font=("Montserrat", 9)
        )
        hintlbl.pack(anchor="w", pady=(0, 8))

        card = tk.Frame(
            wrap, bg=self.panel, highlightthickness=1, highlightbackground=self.border
        )
        card.pack(fill="both", expand=True)

        listbox = tk.Listbox(
            card,
            bg=self.panel,
            fg=self.text,
            selectbackground="#E8EEF9",
            selectforeground=self.text,
            font=("Montserrat", 10),
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            borderwidth=0,
        )
        listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        sb = tk.Scrollbar(card, orient="vertical", command=listbox.yview)
        sb.pack(side="right", fill="y")
        listbox.config(yscrollcommand=sb.set)

        # bind selection handler based on which column
        if title == "TODO":
            self.list_todo = listbox
            listbox.bind("<<ListboxSelect>>", lambda e: self._on_select("todo"))
            listbox.bind(
                "<Double-Button-1>", lambda e: self._open_pomodoro_for_selected()
            )
        elif title == "DOING":
            self.list_doing = listbox
            listbox.bind("<<ListboxSelect>>", lambda e: self._on_select("doing"))
            listbox.bind(
                "<Double-Button-1>", lambda e: self._open_pomodoro_for_selected()
            )
        else:
            self.list_done = listbox
            listbox.bind("<<ListboxSelect>>", lambda e: self._on_select("done"))

        return wrap

    # ---------- Entry placeholder ----------
    def _entry_focus_in(self, event):
        if self.task_entry.get().strip() == "Add a task and press Enter…":
            self.task_entry.delete(0, tk.END)

    def _entry_focus_out(self, event):
        if self.task_entry.get().strip() == "":
            self.task_entry.insert(0, "Add a task and press Enter…")

    # ---------- Data actions ----------
    def _clear_other_selections(self, keep: str):
        try:
            if keep != "todo":
                self.list_todo.selection_clear(0, tk.END)
        except Exception:
            pass
        try:
            if keep != "doing":
                self.list_doing.selection_clear(0, tk.END)
        except Exception:
            pass
        try:
            if keep != "done":
                self.list_done.selection_clear(0, tk.END)
        except Exception:
            pass

    def _on_select(self, column: str):
        self._clear_other_selections(column)

        task_id = None
        title = None

        try:
            if column == "todo":
                sel = self.list_todo.curselection()
                if sel:
                    idx = int(sel[0])
                    task_id = self._map_todo.get(idx)
                    title = self.list_todo.get(idx)
            elif column == "doing":
                sel = self.list_doing.curselection()
                if sel:
                    idx = int(sel[0])
                    task_id = self._map_doing.get(idx)
                    title = self.list_doing.get(idx)
            else:
                sel = self.list_done.curselection()
                if sel:
                    idx = int(sel[0])
                    task_id = self._map_done.get(idx)
                    title = self.list_done.get(idx)
        except Exception:
            task_id = None
            title = None

        self.active_task_id = task_id
        self.active_task_title = title
        self.active_task_status = column if task_id else None

        if task_id and title:
            self.sel_label.config(text=f"Selected: {title}")
            self.err.config(text="")
        else:
            self.sel_label.config(text="Selected: -")

        self._refresh_top_stats()

    def _add_task(self):
        title = (self.task_entry.get() or "").strip()
        if title == "" or title == "Add a task and press Enter…":
            self.err.config(text="Task title cannot be empty.")
            return
        try:
            self.task_service.create_task(title)
            self.err.config(text="")
            self.task_entry.delete(0, tk.END)
            self.task_entry.insert(0, "Add a task and press Enter…")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _move_left(self):
        if not self.active_task_id or not self.active_task_status:
            self.err.config(text="Select a task first.")
            return

        if self.active_task_status == "doing":
            new_status = "todo"
        elif self.active_task_status == "done":
            new_status = "doing"
        else:
            return

        try:
            self.task_service.set_status(self.active_task_id, new_status)
            self.err.config(text="")
            self.active_task_id = None
            self.active_task_title = None
            self.active_task_status = None
            self.sel_label.config(text="Selected: -")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _move_right(self):
        if not self.active_task_id or not self.active_task_status:
            self.err.config(text="Select a task first.")
            return

        if self.active_task_status == "todo":
            new_status = "doing"
        elif self.active_task_status == "doing":
            new_status = "done"
        else:
            return

        try:
            self.task_service.set_status(self.active_task_id, new_status)
            self.err.config(text="")
            self.active_task_id = None
            self.active_task_title = None
            self.active_task_status = None
            self.sel_label.config(text="Selected: -")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _open_pomodoro_for_selected(self):
        if not self.active_task_id:
            self.err.config(text="Select a task first.")
            return

        # Persist selection for pomodoro.py
        self._state_repo.set("active_task_id", self.active_task_id)

        # Optional: set DOING when starting pomodoro
        try:
            self.task_service.set_status(self.active_task_id, "doing")
        except Exception:
            pass

        self.err.config(text="")

        # Launch pomodoro.py
        try:
            subprocess.Popen([sys.executable, "pomodoro.py"], cwd=os.getcwd())
        except Exception as e:
            self.err.config(text=str(e))

        self._refresh_all()

    # ---------- Refresh ----------
    def _refresh_all(self):
        self._refresh_columns()
        self._refresh_top_stats()

    def _refresh_columns(self):
        todo = self.task_service.list_tasks(status="todo")
        doing = self.task_service.list_tasks(status="doing")
        done = self.task_service.list_tasks(status="done")

        # clear
        self.list_todo.delete(0, tk.END)
        self.list_doing.delete(0, tk.END)
        self.list_done.delete(0, tk.END)
        self._map_todo.clear()
        self._map_doing.clear()
        self._map_done.clear()

        # fill
        for i, t in enumerate(todo):
            self.list_todo.insert(tk.END, t.title)
            self._map_todo[i] = t.id

        for i, t in enumerate(doing):
            self.list_doing.insert(tk.END, t.title)
            self._map_doing[i] = t.id

        for i, t in enumerate(done):
            self.list_done.insert(tk.END, t.title)
            self._map_done[i] = t.id

        # update counts
        try:
            self._count_vars["todo"].set(str(len(todo)))
            self._count_vars["doing"].set(str(len(doing)))
            self._count_vars["done"].set(str(len(done)))
        except Exception:
            pass

    def _refresh_top_stats(self):
        today = self.stats_service.total_today_work_sec()
        if self.active_task_id:
            sel = self.stats_service.total_task_work_sec(self.active_task_id)
            self.stats_top.config(
                text=f"Today: {_fmt_hms(today)}  •  Selected: {_fmt_hms(sel)}"
            )
        else:
            self.stats_top.config(text=f"Today: {_fmt_hms(today)}")

    def run(self):
        self.root.mainloop()
