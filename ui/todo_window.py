#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import calendar
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List, Optional

from tkinterweb import HtmlFrame

from services.stats_service import StatsService
from services.task_service import TaskService
from storage.repos import AppStateRepo, Task
from ui.markdown_renderer import MarkdownRenderer, MarkdownTheme
from ui.slash_commands import SlashCommandConfig, SlashCommandExpander


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

        self._db = self.task_service.db
        self._state_repo = AppStateRepo(self._db)

        self.root = tk.Tk()
        self.root.title("Tasks — Kanban")
        self.root.geometry("1260x760")

        self.bg = "#F4F6FA"
        self.panel = "#FFFFFF"
        self.border = "#E6EAF2"
        self.text = "#111827"
        self.muted = "#6B7280"
        self.accent = "#111827"
        self.green = "#10B981"
        self.blue = "#3B82F6"
        self.graybtn = "#EEF2F7"
        self.danger = "#EF4444"

        self._md = MarkdownRenderer(
            MarkdownTheme(
                text=self.text,
                muted=self.muted,
                border=self.border,
                panel=self.panel,
                codebg="#F3F4F6",
                link=self.blue,
                quote=self.blue,
            )
        )
        self._slash = SlashCommandExpander(
            SlashCommandConfig(stamp_fmt="%a, %d %b %Y • %H:%M", day_fmt="%a, %d %b %Y")
        )
        self.root.configure(bg=self.bg)

        self.active_task_id: Optional[str] = None
        self.active_task_title: Optional[str] = None
        self.active_task_status: Optional[str] = None

        self._map_todo: Dict[int, str] = {}
        self._map_doing: Dict[int, str] = {}
        self._map_done: Dict[int, str] = {}

        self._task_by_id: Dict[str, Task] = {}
        self._scores: Dict[str, int] = {}

        # notes state
        self._notes_editing = False
        self._notes_dirty = False
        self._notes_save_job = None

        # drag state
        self._dnd_active = False
        self._dnd_src_kind: Optional[str] = None
        self._dnd_src_index: Optional[int] = None
        self._dnd_task_id: Optional[str] = None
        self._drag_gesture_active = False

        # properties accordion
        self._props_open = True

        # property autosave (debounced)
        self._prop_save_job = None
        self._prop_block_programmatic = False  # prevent autosave during UI fill

        self._build_ui()
        self._refresh_all()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- scroll ----------
    def _bind_mousewheel(self, widget):
        widget.bind(
            "<MouseWheel>",
            lambda e: widget.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: widget.yview_scroll(1, "units"))

    # ---------- deterministic click selection ----------
    def _bind_click_select(self, listbox: tk.Listbox, kind: str):
        def _click(e):
            if self._drag_gesture_active or self._dnd_active:
                return

            if not self._autosave_if_needed():
                return "break"

            try:
                idx = listbox.nearest(e.y)
            except Exception:
                return "break"
            if idx is None:
                return "break"

            try:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(idx)
                listbox.activate(idx)
                listbox.focus_set()
            except Exception:
                pass

            self._clear_other_selections(kind)

            task_id = None
            if kind == "todo":
                task_id = self._map_todo.get(idx)
            elif kind == "doing":
                task_id = self._map_doing.get(idx)
            else:
                task_id = self._map_done.get(idx)

            self._apply_selected_task(kind, task_id)
            return "break"

        listbox.bind("<Button-1>", _click, add=False)

    def _apply_selected_task(self, column: str, task_id: Optional[str]):
        if not self._autosave_if_needed():
            return

        # Exit notes edit mode when switching selection
        if self._notes_editing:
            self.md_edit.pack_forget()
            self.md_view.pack(fill="both", expand=True)
            self.btn_edit_save.config(text="Edit")
            self._notes_editing = False
            self._notes_dirty = False

        self.active_task_id = task_id
        self.active_task_status = column if task_id else None

        if task_id:
            t = self._task_by_id.get(task_id)
            self.active_task_title = t.title if t else None
            self.sel_label.config(text=f"Selected: {self.active_task_title or '-'}")
            self.details_hint.config(text=f"{self.active_task_title or '-'}")

            self._enable_side_controls(True)
            self._refresh_selected_details()
        else:
            self._clear_selected_ui()

        self._refresh_top_stats()

    # ---------- UI ----------
    def _build_ui(self):
        top = tk.Frame(self.root, bg=self.bg)
        top.pack(fill="x", padx=18, pady=(16, 10))

        tk.Label(
            top,
            text="Kanban Tasks",
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 18, "bold"),
        ).pack(side="left")

        self.stats_top = tk.Label(
            top, text="Today: -", bg=self.bg, fg=self.muted, font=("Montserrat", 10)
        )
        self.stats_top.pack(side="left", padx=(14, 0))

        right = tk.Frame(top, bg=self.bg)
        right.pack(side="right")

        tk.Button(
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
        ).pack(side="right", padx=(10, 0))

        tk.Button(
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
        ).pack(side="right")

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

        tk.Button(
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
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            addrow,
            text="Delete Task",
            command=self._delete_selected_task,
            bg=self.danger,
            fg="white",
            relief="flat",
            bd=0,
            activebackground=self.danger,
            activeforeground="white",
            font=("Montserrat", 10, "bold"),
            padx=16,
            pady=10,
        ).pack(side="left", padx=(10, 0))

        body = tk.Frame(self.root, bg=self.bg)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        board = tk.Frame(body, bg=self.bg)
        board.pack(side="left", fill="both", expand=True, padx=(0, 14))

        side = tk.Frame(body, bg=self.bg, width=480)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)

        self.col_todo = self._make_column(board, "TODO", "Backlog / next up", self.blue)
        self.col_doing = self._make_column(board, "DOING", "In progress", self.green)
        self.col_done = self._make_column(board, "DONE", "Completed", self.muted)

        self.col_todo.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.col_doing.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.col_done.pack(side="left", fill="both", expand=True)

        self._build_side_panel(side)

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

        tk.Button(
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
        ).pack(side="right")

        tk.Button(
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
        ).pack(side="right", padx=(10, 0))

        self.err = tk.Label(
            self.root, text="", bg=self.bg, fg=self.danger, font=("Montserrat", 9)
        )
        self.err.pack(anchor="w", padx=18)

        self.root.bind("<Control-Return>", lambda e: self._open_pomodoro_for_selected())
        self.root.bind("<Control-Left>", lambda e: self._move_left())
        self.root.bind("<Control-Right>", lambda e: self._move_right())
        self.root.bind("<Delete>", lambda e: self._delete_selected_task())

    # ---------- Side panel: Properties accordion (top) + Description (always visible) ----------
    def _build_side_panel(self, parent: tk.Frame):
        tk.Label(
            parent,
            text="Task Panel",
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 14, "bold"),
        ).pack(anchor="w")

        self.details_hint = tk.Label(
            parent,
            text="Select a task…",
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 9),
        )
        self.details_hint.pack(anchor="w", pady=(2, 10))

        # ---- Properties accordion (TOP) ----
        acc = tk.Frame(parent, bg=self.bg)
        acc.pack(fill="x", pady=(0, 10))

        acc_head = tk.Frame(acc, bg=self.bg)
        acc_head.pack(fill="x", pady=(0, 6))

        self.btn_toggle_props = tk.Button(
            acc_head,
            text="▼ Properties",
            command=self._toggle_properties_accordion,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            font=("Montserrat", 10, "bold"),
        )
        self.btn_toggle_props.pack(side="left")

        # Score quick glance on the right (biar gak perlu buka accordion)
        self.score_pill = tk.Label(
            acc_head,
            text="Score: -",
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 10, "bold"),
        )
        self.score_pill.pack(side="right")

        self.frame_props = tk.Frame(acc, bg=self.bg)
        self.frame_props.pack(fill="x")

        self._build_properties_content(self.frame_props)

        # ---- Description (ALWAYS visible) ----
        desc_header = tk.Frame(parent, bg=self.bg)
        desc_header.pack(fill="x", pady=(0, 6))

        tk.Label(
            desc_header,
            text="Description",
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 13, "bold"),
        ).pack(side="left")

        self.btn_edit_save = tk.Button(
            desc_header,
            text="Edit",
            command=self._toggle_edit_save,
            bg=self.accent,
            fg="white",
            relief="flat",
            bd=0,
            activebackground=self.accent,
            activeforeground="white",
            font=("Montserrat", 10, "bold"),
            padx=12,
            pady=6,
            state="disabled",
        )
        self.btn_edit_save.pack(side="right")

        note_card = tk.Frame(
            parent, bg=self.panel, highlightthickness=1, highlightbackground=self.border
        )
        note_card.pack(fill="both", expand=True)

        self.md_view = HtmlFrame(note_card, horizontal_scrollbar="auto")
        self.md_view.pack(fill="both", expand=True)

        self.md_edit = tk.Text(
            note_card,
            wrap="word",
            bg=self.panel,
            fg=self.text,
            insertbackground=self.text,
            relief="flat",
            highlightthickness=0,
            font=("Montserrat", 10),
            padx=12,
            pady=10,
            undo=True,
            autoseparators=True,
            maxundo=-1,
        )
        self._bind_mousewheel(self.md_edit)
        self.md_edit.bind(
            "<Control-a>",
            lambda e: (self.md_edit.tag_add("sel", "1.0", "end-1c"), "break"),
        )
        self.md_edit.bind(
            "<Control-A>",
            lambda e: (self.md_edit.tag_add("sel", "1.0", "end-1c"), "break"),
        )
        self.md_edit.bind("<KeyRelease>", lambda e: self._notes_on_change())

        def _on_space(e):
            expanded = self._slash.try_expand(self.md_edit)
            if expanded:
                self._notes_dirty = True
                self._notes_autosave_debounced(400)
            return None

        def _on_enter(e):
            expanded = self._slash.try_expand(self.md_edit)
            if expanded:
                self._notes_dirty = True
                self._notes_autosave_debounced(400)
            return None

        self.md_edit.bind("<space>", _on_space, add=True)
        self.md_edit.bind("<Return>", _on_enter, add=True)

        self._render_markdown_to_view("Select a task…")
        self._enable_side_controls(False)

    def _toggle_properties_accordion(self):
        self._props_open = not self._props_open
        if self._props_open:
            self.btn_toggle_props.config(text="▼ Properties")
            self.frame_props.pack(fill="x")
        else:
            self.btn_toggle_props.config(text="► Properties")
            self.frame_props.pack_forget()

    def _enable_side_controls(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_edit_save.config(state=state)

        try:
            self.name_entry.config(state=state)
            self.due_entry.config(state=state)
            self.btn_pick_date.config(state=state)
            self.priority_menu.config(state=state)

            self.btn_add_blocker.config(state=state)
            self.btn_rm_blocker.config(state=state)
            self.btn_add_waiting.config(state=state)
            self.btn_rm_waiting.config(state=state)
        except Exception:
            pass

    # ---------- property autosave ----------
    def _schedule_prop_autosave(self, delay_ms: int = 650):
        if self._prop_block_programmatic:
            return
        if not self.active_task_id:
            return
        if self._prop_save_job:
            try:
                self.root.after_cancel(self._prop_save_job)
            except Exception:
                pass
        self._prop_save_job = self.root.after(delay_ms, self._prop_autosave_now)

    def _prop_autosave_now(self):
        self._prop_save_job = None
        if self._prop_block_programmatic:
            return
        if not self.active_task_id:
            return
        try:
            name = (self.name_entry.get() or "").strip()
            due = (self.due_entry.get() or "").strip()
            pr = (self.priority_var.get() or "P2").strip().upper()

            self.task_service.rename_task(self.active_task_id, name)
            self.task_service.set_due_date(self.active_task_id, due)
            self.task_service.set_priority(self.active_task_id, pr)

            self.err.config(text="")
            self._refresh_all()
            self._refresh_selected_details()
        except Exception as e:
            self.err.config(text=str(e))

    # ---------- Properties content (includes deps) ----------
    def _build_properties_content(self, parent: tk.Frame):
        card = tk.Frame(
            parent, bg=self.panel, highlightthickness=1, highlightbackground=self.border
        )
        card.pack(fill="x")

        # Score row
        r0 = tk.Frame(card, bg=self.panel)
        r0.pack(fill="x", padx=12, pady=(10, 8))
        tk.Label(
            r0, text="Score", bg=self.panel, fg=self.muted, font=("Montserrat", 9)
        ).pack(side="left")
        self.score_label = tk.Label(
            r0, text="-", bg=self.panel, fg=self.text, font=("Montserrat", 10, "bold")
        )
        self.score_label.pack(side="right")

        # Name row
        r1 = tk.Frame(card, bg=self.panel)
        r1.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(
            r1, text="Name", bg=self.panel, fg=self.muted, font=("Montserrat", 9)
        ).pack(anchor="w")
        self.name_entry = tk.Entry(
            r1,
            bg=self.panel,
            fg=self.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.border,
            insertbackground=self.text,
        )
        self.name_entry.pack(fill="x", ipady=6)
        self.name_entry.bind("<KeyRelease>", lambda e: self._schedule_prop_autosave())

        # Due + Priority (2 columns same row)
        row2 = tk.Frame(card, bg=self.panel)
        row2.pack(fill="x", padx=12, pady=(0, 6))

        col_due = tk.Frame(row2, bg=self.panel)
        col_due.pack(side="left", fill="x", expand=True, padx=(0, 8))

        tk.Label(
            col_due,
            text="Due date",
            bg=self.panel,
            fg=self.muted,
            font=("Montserrat", 9),
        ).pack(anchor="w")

        due_row = tk.Frame(col_due, bg=self.panel)
        due_row.pack(fill="x")

        self.due_entry = tk.Entry(
            due_row,
            bg=self.panel,
            fg=self.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.border,
            insertbackground=self.text,
        )
        self.due_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.due_entry.bind(
            "<KeyRelease>",
            lambda e: (self._update_due_info(), self._schedule_prop_autosave()),
        )

        self.btn_pick_date = tk.Button(
            due_row,
            text="📅",
            command=self._open_date_picker,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            state="disabled",
        )
        self.btn_pick_date.pack(side="left", padx=(8, 0))

        col_pr = tk.Frame(row2, bg=self.panel)
        col_pr.pack(side="left", fill="x", expand=True, padx=(8, 0))

        tk.Label(
            col_pr,
            text="Priority",
            bg=self.panel,
            fg=self.muted,
            font=("Montserrat", 9),
        ).pack(anchor="w")

        self.priority_var = tk.StringVar(value="P2")
        self.priority_menu = tk.OptionMenu(col_pr, self.priority_var, "P0", "P1", "P2")
        self.priority_menu.config(
            bg=self.graybtn, fg=self.text, relief="flat", bd=0, highlightthickness=0
        )
        self.priority_menu["menu"].config(bg=self.panel, fg=self.text)
        self.priority_menu.pack(anchor="w", fill="x")
        self.priority_var.trace_add("write", lambda *_: self._schedule_prop_autosave())

        self.due_info = tk.Label(
            card, text="—", bg=self.panel, fg=self.muted, font=("Montserrat", 9)
        )
        self.due_info.pack(anchor="w", padx=12, pady=(0, 8))

        # Dependencies
        deps = tk.Frame(card, bg=self.panel)
        deps.pack(fill="x", padx=12, pady=(0, 12))

        tk.Label(
            deps,
            text="Dependencies",
            bg=self.panel,
            fg=self.muted,
            font=("Montserrat", 9),
        ).pack(anchor="w")

        body = tk.Frame(deps, bg=self.panel)
        body.pack(fill="x", pady=(6, 0))

        blk = tk.Frame(body, bg=self.panel)
        blk.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(
            blk, text="Blockers", bg=self.panel, fg=self.muted, font=("Montserrat", 9)
        ).pack(anchor="w")
        self.list_blockers = tk.Listbox(
            blk,
            height=6,
            bg=self.panel,
            fg=self.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.border,
            activestyle="none",
            exportselection=False,
        )
        self.list_blockers.pack(fill="both", expand=True, pady=(4, 6))
        br = tk.Frame(blk, bg=self.panel)
        br.pack(fill="x")
        self.btn_add_blocker = tk.Button(
            br,
            text="+",
            command=lambda: self._pick_dep("blocker"),
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            state="disabled",
        )
        self.btn_add_blocker.pack(side="left")
        self.btn_rm_blocker = tk.Button(
            br,
            text="−",
            command=lambda: self._remove_selected_dep("blocker"),
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            state="disabled",
        )
        self.btn_rm_blocker.pack(side="left", padx=(6, 0))

        wtg = tk.Frame(body, bg=self.panel)
        wtg.pack(side="left", fill="both", expand=True)
        tk.Label(
            wtg, text="Waiting-on", bg=self.panel, fg=self.muted, font=("Montserrat", 9)
        ).pack(anchor="w")
        self.list_waiting = tk.Listbox(
            wtg,
            height=6,
            bg=self.panel,
            fg=self.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.border,
            activestyle="none",
            exportselection=False,
        )
        self.list_waiting.pack(fill="both", expand=True, pady=(4, 6))
        wr = tk.Frame(wtg, bg=self.panel)
        wr.pack(fill="x")
        self.btn_add_waiting = tk.Button(
            wr,
            text="+",
            command=lambda: self._pick_dep("waiting"),
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            state="disabled",
        )
        self.btn_add_waiting.pack(side="left")
        self.btn_rm_waiting = tk.Button(
            wr,
            text="−",
            command=lambda: self._remove_selected_dep("waiting"),
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            state="disabled",
        )
        self.btn_rm_waiting.pack(side="left", padx=(6, 0))

    # ---------- Date picker ----------
    def _open_date_picker(self):
        if not self.active_task_id:
            return

        import datetime as dt

        today = dt.date.today()

        cur = (self.due_entry.get() or "").strip()
        selected = None
        try:
            if cur:
                selected = dt.date.fromisoformat(cur)
        except Exception:
            selected = None

        year = selected.year if selected else today.year
        month = selected.month if selected else today.month

        win = tk.Toplevel(self.root)
        win.title("Pick due date")
        win.geometry("360x410")
        win.configure(bg=self.bg)
        win.transient(self.root)
        win.grab_set()

        head = tk.Frame(win, bg=self.bg)
        head.pack(fill="x", padx=12, pady=(12, 8))

        label = tk.Label(
            head, text="", bg=self.bg, fg=self.text, font=("Montserrat", 12, "bold")
        )
        label.pack(side="left")

        state = {"y": year, "m": month}

        grid = tk.Frame(win, bg=self.bg)
        grid.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        info = tk.Label(win, text="", bg=self.bg, fg=self.muted, font=("Montserrat", 9))
        info.pack(anchor="w", padx=12, pady=(0, 12))

        def render(y, m):
            label.config(text=f"{calendar.month_name[m]} {y}")
            for w in grid.winfo_children():
                w.destroy()

            days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
            row = tk.Frame(grid, bg=self.bg)
            row.pack(fill="x")
            for dname in days:
                tk.Label(row, text=dname, bg=self.bg, fg=self.muted, width=4).pack(
                    side="left"
                )

            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdayscalendar(y, m)

            for wk in weeks:
                r = tk.Frame(grid, bg=self.bg)
                r.pack(fill="x", pady=2)
                for d in wk:
                    if d == 0:
                        tk.Label(r, text=" ", bg=self.bg, width=4).pack(side="left")
                    else:
                        dd = dt.date(y, m, d)

                        def pick(date_obj=dd):
                            self.due_entry.delete(0, tk.END)
                            self.due_entry.insert(0, date_obj.isoformat())
                            self._update_due_info()
                            self._schedule_prop_autosave(0)  # immediate
                            win.destroy()

                        bg = self.graybtn
                        fg = self.text

                        if selected and dd == selected:
                            bg = self.accent
                            fg = "white"
                        elif dd == today:
                            bg = self.blue
                            fg = "white"

                        btn = tk.Button(
                            r,
                            text=str(d),
                            command=pick,
                            bg=bg,
                            fg=fg,
                            relief="flat",
                            bd=0,
                            width=4,
                            padx=2,
                            pady=4,
                        )
                        btn.pack(side="left")

            try:
                cur2 = (self.due_entry.get() or "").strip()
                if cur2:
                    due = dt.date.fromisoformat(cur2)
                    days_until = (due - today).days
                    if days_until == 0:
                        info.config(text="Due today (0 days).")
                    elif days_until > 0:
                        info.config(text=f"Due in {days_until} day(s).")
                    else:
                        info.config(text=f"Overdue by {abs(days_until)} day(s).")
                else:
                    info.config(text="No due date.")
            except Exception:
                info.config(text="Invalid due date format.")

        nav = tk.Frame(head, bg=self.bg)
        nav.pack(side="right")

        def prev_month():
            m = state["m"] - 1
            y = state["y"]
            if m <= 0:
                m = 12
                y -= 1
            state["y"], state["m"] = y, m
            render(y, m)

        def next_month():
            m = state["m"] + 1
            y = state["y"]
            if m >= 13:
                m = 1
                y += 1
            state["y"], state["m"] = y, m
            render(y, m)

        tk.Button(
            nav,
            text="←",
            command=prev_month,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        ).pack(side="left")
        tk.Button(
            nav,
            text="→",
            command=next_month,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        ).pack(side="left", padx=(6, 0))

        render(state["y"], state["m"])

    def _update_due_info(self):
        import datetime as dt

        raw = (self.due_entry.get() or "").strip()
        if not raw:
            self.due_info.config(text="No due date.")
            return
        try:
            due = dt.date.fromisoformat(raw)
            today = dt.date.today()
            days_until = (due - today).days
            if days_until == 0:
                self.due_info.config(text="Due today (0 days).")
            elif days_until > 0:
                self.due_info.config(text=f"Due in {days_until} day(s).")
            else:
                self.due_info.config(text=f"Overdue by {abs(days_until)} day(s).")
        except Exception:
            self.due_info.config(text="Invalid date format. Use YYYY-MM-DD or pick 📅.")

    # ---------- Notes ----------
    def _notes_on_change(self):
        if not self._notes_editing:
            return
        self._notes_dirty = True
        self._notes_autosave_debounced(800)

    def _notes_autosave_debounced(self, delay_ms: int = 800):
        if self._notes_save_job:
            try:
                self.root.after_cancel(self._notes_save_job)
            except Exception:
                pass
        self._notes_save_job = self.root.after(delay_ms, self._notes_autosave_now)

    def _notes_autosave_now(self):
        self._notes_save_job = None
        if not self.active_task_id or not self._notes_editing or not self._notes_dirty:
            return
        md_new = self.md_edit.get("1.0", "end-1c")
        try:
            self.task_service.set_notes_md(self.active_task_id, md_new)
            self._notes_dirty = False
            self.err.config(text="")
        except Exception as e:
            self.err.config(text=str(e))

    def _autosave_if_needed(self) -> bool:
        # flush props autosave immediately
        if self._prop_save_job:
            try:
                self.root.after_cancel(self._prop_save_job)
            except Exception:
                pass
            self._prop_save_job = None
            try:
                self._prop_autosave_now()
            except Exception:
                pass

        if not self._notes_editing or not self.active_task_id:
            return True
        if self._notes_dirty:
            md_new = self.md_edit.get("1.0", "end-1c")
            try:
                self.task_service.set_notes_md(self.active_task_id, md_new)
                self._notes_dirty = False
            except Exception as e:
                self.err.config(text=str(e))
                return False
        return True

    def _render_markdown_to_view(self, md_text: str):
        html = self._md.to_html(md_text or "")
        try:
            self.md_view.load_html(html)
        except Exception:
            try:
                self.md_view.set_content(html)
            except Exception:
                pass

    def _toggle_edit_save(self):
        if not self.active_task_id:
            return

        if not self._notes_editing:
            md = self.task_service.get_notes_md(self.active_task_id) or ""
            self.md_view.pack_forget()
            self.md_edit.pack(fill="both", expand=True)
            self.md_edit.delete("1.0", tk.END)
            self.md_edit.insert("1.0", md)
            self.md_edit.focus_set()
            self.btn_edit_save.config(text="Save")
            self._notes_editing = True
            self._notes_dirty = False
            return

        if not self._autosave_if_needed():
            return

        md_new = self.task_service.get_notes_md(self.active_task_id) or ""
        self.md_edit.pack_forget()
        self.md_view.pack(fill="both", expand=True)
        self._render_markdown_to_view(
            md_new
            if md_new.strip()
            else "_No description yet. Click **Edit** to write one._"
        )
        self.btn_edit_save.config(text="Edit")
        self._notes_editing = False

    # ---------- deps ----------
    def _pick_dep(self, mode: str):
        if not self.active_task_id:
            self.err.config(text="Select a task first.")
            return
        if not self._autosave_if_needed():
            return

        target_id = self.active_task_id
        all_tasks = [t for t in self.task_service.list_all_tasks() if t.id != target_id]
        if not all_tasks:
            self.err.config(text="No other tasks available.")
            return

        scores = self._scores

        win = tk.Toplevel(self.root)
        win.title("Pick task")
        win.geometry("560x460")
        win.configure(bg=self.bg)
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text=("Pick Blocker" if mode == "blocker" else "Pick Waiting-on"),
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 12, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        lb = tk.Listbox(
            win,
            bg=self.panel,
            fg=self.text,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.border,
            highlightcolor=self.border,
            activestyle="none",
            exportselection=False,
        )
        lb.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        all_tasks = sorted(all_tasks, key=lambda t: scores.get(t.id, 0), reverse=True)

        id_map: Dict[int, str] = {}
        for i, t in enumerate(all_tasks):
            lb.insert(tk.END, f"[{scores.get(t.id, 0):>3}] {t.title}")
            id_map[i] = t.id

        btns = tk.Frame(win, bg=self.bg)
        btns.pack(fill="x", padx=14, pady=(0, 14))

        def _add():
            sel = lb.curselection()
            if not sel:
                return
            idx = int(sel[0])
            other_id = id_map.get(idx)
            if not other_id:
                return
            try:
                if mode == "blocker":
                    self.task_service.add_blocker(target_id, other_id)
                else:
                    self.task_service.add_waiting_on(target_id, other_id)
                self.err.config(text="")
                win.destroy()
                self._refresh_all()
                self._refresh_selected_details()
            except Exception as e:
                self.err.config(text=str(e))

        tk.Button(
            btns,
            text="Add",
            command=_add,
            bg=self.accent,
            fg="white",
            relief="flat",
            bd=0,
            activebackground=self.accent,
            activeforeground="white",
            font=("Montserrat", 10, "bold"),
            padx=14,
            pady=8,
        ).pack(side="right")

        tk.Button(
            btns,
            text="Cancel",
            command=win.destroy,
            bg=self.graybtn,
            fg=self.text,
            relief="flat",
            bd=0,
            activebackground=self.graybtn,
            activeforeground=self.text,
            font=("Montserrat", 10, "bold"),
            padx=14,
            pady=8,
        ).pack(side="right", padx=(0, 10))

    def _remove_selected_dep(self, mode: str):
        if not self.active_task_id:
            return
        try:
            if mode == "blocker":
                sel = self.list_blockers.curselection()
                if not sel:
                    return
                idx = int(sel[0])
                tid = self._dep_map_blockers.get(idx)
                if tid:
                    self.task_service.remove_blocker(self.active_task_id, tid)
            else:
                sel = self.list_waiting.curselection()
                if not sel:
                    return
                idx = int(sel[0])
                tid = self._dep_map_waiting.get(idx)
                if tid:
                    self.task_service.remove_waiting_on(self.active_task_id, tid)

            self.err.config(text="")
            self._refresh_all()
            self._refresh_selected_details()
        except Exception as e:
            self.err.config(text=str(e))

    # ---------- entry placeholders ----------
    def _entry_focus_in(self, event):
        if self.task_entry.get().strip() == "Add a task and press Enter…":
            self.task_entry.delete(0, tk.END)

    def _entry_focus_out(self, event):
        if self.task_entry.get().strip() == "":
            self.task_entry.insert(0, "Add a task and press Enter…")

    # ---------- columns + DnD ----------
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

        tk.Label(
            head, text=title, bg=self.bg, fg=self.text, font=("Montserrat", 12, "bold")
        ).pack(side="left", padx=(8, 6))
        tk.Label(
            head,
            textvariable=count_var,
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 10, "bold"),
        ).pack(side="left")

        tk.Label(
            wrap, text=hint, bg=self.bg, fg=self.muted, font=("Montserrat", 9)
        ).pack(anchor="w", pady=(0, 8))

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
            exportselection=False,
        )
        listbox.pack(fill="both", expand=True, padx=10, pady=10)
        self._bind_mousewheel(listbox)

        kind = "todo" if title == "TODO" else "doing" if title == "DOING" else "done"
        if kind == "todo":
            self.list_todo = listbox
        elif kind == "doing":
            self.list_doing = listbox
        else:
            self.list_done = listbox

        self._bind_click_select(listbox, kind)

        if kind in ("todo", "doing"):
            listbox.bind(
                "<Double-Button-1>", lambda e: self._open_pomodoro_for_selected()
            )

        listbox.bind(
            "<ButtonPress-1>", lambda e, k=kind: self._dnd_start(e, k), add=True
        )
        listbox.bind("<B1-Motion>", lambda e: self._dnd_motion(e), add=True)
        listbox.bind("<ButtonRelease-1>", lambda e: self._dnd_drop(e), add=True)

        return wrap

    def _dnd_start(self, event, kind: str):
        self._drag_gesture_active = False
        lb = event.widget
        try:
            idx = lb.nearest(event.y)
        except Exception:
            return
        if idx is None:
            return

        try:
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx)
            lb.activate(idx)
        except Exception:
            pass

        task_id = None
        if kind == "todo":
            task_id = self._map_todo.get(idx)
        elif kind == "doing":
            task_id = self._map_doing.get(idx)
        else:
            task_id = self._map_done.get(idx)

        if not task_id:
            return
        if not self._autosave_if_needed():
            return

        self._dnd_active = True
        self._dnd_src_kind = kind
        self._dnd_src_index = idx
        self._dnd_task_id = task_id

        self._clear_other_selections(kind)
        self._apply_selected_task(kind, task_id)

    def _dnd_motion(self, event):
        if self._dnd_active:
            self._drag_gesture_active = True

    def _dnd_drop(self, event):
        if not self._dnd_active or not self._dnd_task_id:
            self._dnd_active = False
            self._drag_gesture_active = False
            return

        target = self.root.winfo_containing(event.x_root, event.y_root)
        target_kind = None
        w = target
        for _ in range(6):
            if w is None:
                break
            if w is self.list_todo:
                target_kind = "todo"
                break
            if w is self.list_doing:
                target_kind = "doing"
                break
            if w is self.list_done:
                target_kind = "done"
                break
            w = getattr(w, "master", None)

        if target_kind and target_kind != self._dnd_src_kind:
            try:
                self.task_service.set_status(self._dnd_task_id, target_kind)
                self.err.config(text="")
                self.active_task_id = self._dnd_task_id
                self.active_task_status = target_kind
                self._refresh_all()
                self._refresh_selected_details()
            except Exception as e:
                self.err.config(text=str(e))

        self._dnd_active = False
        self._dnd_src_kind = None
        self._dnd_src_index = None
        self._dnd_task_id = None
        self._drag_gesture_active = False

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

    def _clear_selected_ui(self):
        self.active_task_id = None
        self.active_task_title = None
        self.active_task_status = None

        self.sel_label.config(text="Selected: -")
        self.details_hint.config(text="Select a task…")

        self._enable_side_controls(False)

        try:
            self.score_label.config(text="-")
            self.score_pill.config(text="Score: -")
        except Exception:
            pass

        self._prop_block_programmatic = True
        try:
            self.name_entry.delete(0, tk.END)
            self.due_entry.delete(0, tk.END)
            self.due_info.config(text="—")
            self.priority_var.set("P2")
        finally:
            self._prop_block_programmatic = False

        try:
            self.list_blockers.delete(0, tk.END)
            self.list_waiting.delete(0, tk.END)
        except Exception:
            pass

        self._render_markdown_to_view("Select a task…")

    def _refresh_selected_details(self):
        if not self.active_task_id:
            self._clear_selected_ui()
            return
        t = self._task_by_id.get(self.active_task_id)
        if not t:
            self._clear_selected_ui()
            return

        self.active_task_title = t.title
        self.sel_label.config(text=f"Selected: {t.title}")
        self.details_hint.config(text=t.title)

        sc = str(self._scores.get(t.id, 0))
        self.score_label.config(text=sc)
        self.score_pill.config(text=f"Score: {sc}")

        self._prop_block_programmatic = True
        try:
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, t.title)

            self.due_entry.delete(0, tk.END)
            if getattr(t, "due_date", None):
                self.due_entry.insert(0, t.due_date)
            self._update_due_info()

            self.priority_var.set((getattr(t, "priority", None) or "P2").upper())
        finally:
            self._prop_block_programmatic = False

        blockers = self.task_service.list_blockers(t.id)
        waiting = self.task_service.list_waiting_on(t.id)

        self._dep_map_blockers = {}
        self._dep_map_waiting = {}

        self.list_blockers.delete(0, tk.END)
        for i, bid in enumerate(blockers):
            tt = self._task_by_id.get(bid)
            name = tt.title if tt else bid
            self.list_blockers.insert(tk.END, name)
            self._dep_map_blockers[i] = bid

        self.list_waiting.delete(0, tk.END)
        for i, wid in enumerate(waiting):
            tt = self._task_by_id.get(wid)
            name = tt.title if tt else wid
            self.list_waiting.insert(tk.END, name)
            self._dep_map_waiting[i] = wid

        md = self.task_service.get_notes_md(t.id) or ""
        self._render_markdown_to_view(
            md if md.strip() else "_No description yet. Click **Edit** to write one._"
        )

    # ---------- actions ----------
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

    def _delete_selected_task(self):
        if not self.active_task_id:
            self.err.config(text="Select a task first.")
            return
        if not self._autosave_if_needed():
            return

        title = self.active_task_title or "this task"
        ok = messagebox.askyesno(
            "Delete task?",
            f"Delete '{title}'?\n\nThis will also delete deps + sessions.",
        )
        if not ok:
            return

        try:
            self.task_service.delete_task(self.active_task_id)
            self.err.config(text="")
            self._clear_selected_ui()
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _move_left(self):
        if not self.active_task_id or not self.active_task_status:
            return
        if not self._autosave_if_needed():
            return
        new_status = (
            "todo"
            if self.active_task_status == "doing"
            else "doing"
            if self.active_task_status == "done"
            else None
        )
        if not new_status:
            return
        try:
            self.task_service.set_status(self.active_task_id, new_status)
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _move_right(self):
        if not self.active_task_id or not self.active_task_status:
            return
        if not self._autosave_if_needed():
            return
        new_status = (
            "doing"
            if self.active_task_status == "todo"
            else "done"
            if self.active_task_status == "doing"
            else None
        )
        if not new_status:
            return
        try:
            self.task_service.set_status(self.active_task_id, new_status)
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _open_pomodoro_for_selected(self):
        if not self.active_task_id:
            self.err.config(text="Select a task first.")
            return
        if not self._autosave_if_needed():
            return

        if self._notes_editing:
            self.md_edit.pack_forget()
            self.md_view.pack(fill="both", expand=True)
            self.btn_edit_save.config(text="Edit")
            self._notes_editing = False
            self._notes_dirty = False

        self._state_repo.set("active_task_id", self.active_task_id)

        try:
            self.task_service.set_status(self.active_task_id, "doing")
        except Exception:
            pass

        try:
            subprocess.Popen([sys.executable, "pomodoro.py"], cwd=os.getcwd())
        except Exception as e:
            self.err.config(text=str(e))

        self._refresh_all()

    # ---------- refresh/sort ----------
    def _format_task_line(self, t: Task) -> str:
        score = self._scores.get(t.id, 0)
        return f"[{score:>3}] {t.title}"

    def _sort_by_score(self, tasks: List[Task]) -> List[Task]:
        return sorted(
            tasks, key=lambda x: (self._scores.get(x.id, 0), x.updated_at), reverse=True
        )

    def _refresh_all(self):
        self._scores = self.task_service.prioritization_scores()
        self._task_by_id = {t.id: t for t in self.task_service.list_all_tasks()}
        self._refresh_columns()
        self._refresh_top_stats()
        if self.active_task_id:
            self._refresh_selected_details()

    def _refresh_columns(self):
        todo = self._sort_by_score(self.task_service.list_tasks(status="todo"))
        doing = self._sort_by_score(self.task_service.list_tasks(status="doing"))
        done = self._sort_by_score(self.task_service.list_tasks(status="done"))

        self.list_todo.delete(0, tk.END)
        self.list_doing.delete(0, tk.END)
        self.list_done.delete(0, tk.END)
        self._map_todo.clear()
        self._map_doing.clear()
        self._map_done.clear()

        for i, t in enumerate(todo):
            self.list_todo.insert(tk.END, self._format_task_line(t))
            self._map_todo[i] = t.id
        for i, t in enumerate(doing):
            self.list_doing.insert(tk.END, self._format_task_line(t))
            self._map_doing[i] = t.id
        for i, t in enumerate(done):
            self.list_done.insert(tk.END, self._format_task_line(t))
            self._map_done[i] = t.id

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

    def _on_close(self):
        try:
            self._autosave_if_needed()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
