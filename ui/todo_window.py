# ui/todo_window.py  (REPLACE) — Modern Kanban + HIDDEN scrollbars + Markdown WYSIWYG (Editor + Preview)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
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

        # Shared DB state (active_task_id)
        self._db = Database(db_path="pomodoro.db")
        self._db.init_schema()
        self._state_repo = AppStateRepo(self._db)

        self.root = tk.Tk()
        self.root.title("Tasks — Kanban")
        self.root.geometry("1180x700")

        # ===== Modern palette =====
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

        self.root.configure(bg=self.bg)

        # selection
        self.active_task_id: Optional[str] = None
        self.active_task_title: Optional[str] = None
        self.active_task_status: Optional[str] = None

        # mapping
        self._map_todo: Dict[int, str] = {}
        self._map_doing: Dict[int, str] = {}
        self._map_done: Dict[int, str] = {}

        # markdown editor state
        self._notes_dirty = False
        self._notes_save_job = None
        self._notes_current_task_id: Optional[str] = None

        self._build_ui()
        self._refresh_all()

    # ---------- UI ----------
    def _build_ui(self):
        # Top bar
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

        # Body: board + notes panel
        body = tk.Frame(self.root, bg=self.bg)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        board = tk.Frame(body, bg=self.bg)
        board.pack(side="left", fill="both", expand=True, padx=(0, 14))

        notes = tk.Frame(body, bg=self.bg, width=430)
        notes.pack(side="right", fill="y")
        notes.pack_propagate(False)

        # Kanban columns (NO visible scrollbars)
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

        # Notes panel (Markdown WYSIWYG-ish)
        self._build_notes_panel(notes)

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

        self.err = tk.Label(
            self.root, text="", bg=self.bg, fg=self.danger, font=("Montserrat", 9)
        )
        self.err.pack(anchor="w", padx=18)

        # Keybinds
        self.root.bind("<Control-Return>", lambda e: self._open_pomodoro_for_selected())
        self.root.bind("<Control-Left>", lambda e: self._move_left())
        self.root.bind("<Control-Right>", lambda e: self._move_right())
        self.root.bind("<Delete>", lambda e: self._delete_selected_task())
        self.root.bind("<Control-s>", lambda e: self._notes_save_now())

    # ---------- Hidden-scroll support ----------
    def _bind_mousewheel(self, widget):
        # Windows / mac
        widget.bind(
            "<MouseWheel>",
            lambda e: widget.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        # Linux
        widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: widget.yview_scroll(1, "units"))

    # ---------- Notes panel ----------
    def _build_notes_panel(self, parent: tk.Frame):
        header = tk.Frame(parent, bg=self.bg)
        header.pack(fill="x")

        tk.Label(
            header,
            text="Notes (Markdown)",
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 14, "bold"),
        ).pack(anchor="w")
        self.notes_hint = tk.Label(
            header,
            text="Select a task to edit notes",
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 9),
        )
        self.notes_hint.pack(anchor="w", pady=(2, 10))

        # Toolbar
        bar = tk.Frame(parent, bg=self.bg)
        bar.pack(fill="x", pady=(0, 10))

        def _tool_btn(txt, cmd):
            return tk.Button(
                bar,
                text=txt,
                command=cmd,
                bg=self.graybtn,
                fg=self.text,
                relief="flat",
                bd=0,
                activebackground=self.graybtn,
                activeforeground=self.text,
                font=("Montserrat", 9, "bold"),
                padx=10,
                pady=6,
            )

        _tool_btn("H1", lambda: self._md_prefix_line("# ")).pack(
            side="left", padx=(0, 6)
        )
        _tool_btn("H2", lambda: self._md_prefix_line("## ")).pack(
            side="left", padx=(0, 6)
        )
        _tool_btn("H3", lambda: self._md_prefix_line("### ")).pack(
            side="left", padx=(0, 10)
        )
        _tool_btn("• List", lambda: self._md_prefix_line("- ")).pack(
            side="left", padx=(0, 6)
        )
        _tool_btn("☐ Check", lambda: self._md_prefix_line("- [ ] ")).pack(
            side="left", padx=(0, 6)
        )
        _tool_btn("Toggle ☑", self._md_toggle_checkbox_line).pack(
            side="left", padx=(0, 10)
        )
        _tool_btn("Save", self._notes_save_now).pack(side="right")

        # Editor card
        editor_card = tk.Frame(
            parent, bg=self.panel, highlightthickness=1, highlightbackground=self.border
        )
        editor_card.pack(fill="both", expand=True)

        # Split: editor (top) + preview (bottom)
        self.notes_editor = tk.Text(
            editor_card,
            wrap="word",
            bg=self.panel,
            fg=self.text,
            insertbackground=self.text,
            relief="flat",
            highlightthickness=0,
            font=("Montserrat", 10),
            padx=12,
            pady=10,
            height=14,
        )
        self.notes_editor.pack(fill="both", expand=True)

        sep = tk.Frame(editor_card, bg=self.border, height=1)
        sep.pack(fill="x")

        self.notes_preview = tk.Text(
            editor_card,
            wrap="word",
            bg=self.panel,
            fg=self.text,
            relief="flat",
            highlightthickness=0,
            font=("Montserrat", 10),
            padx=12,
            pady=10,
            height=10,
            state="disabled",
        )
        self.notes_preview.pack(fill="both", expand=True)

        # hide scrollbars visually but keep wheel scrolling
        self._bind_mousewheel(self.notes_editor)
        self._bind_mousewheel(self.notes_preview)

        # preview tags
        self.notes_preview.tag_configure("h1", font=("Montserrat", 14, "bold"))
        self.notes_preview.tag_configure("h2", font=("Montserrat", 12, "bold"))
        self.notes_preview.tag_configure("h3", font=("Montserrat", 11, "bold"))
        self.notes_preview.tag_configure("muted", foreground=self.muted)
        self.notes_preview.tag_configure(
            "check_on", foreground=self.green, font=("Montserrat", 10, "bold")
        )
        self.notes_preview.tag_configure(
            "check_off", foreground=self.muted, font=("Montserrat", 10, "bold")
        )

        # editor events
        self.notes_editor.bind("<KeyRelease>", lambda e: self._notes_on_change())
        self.notes_editor.bind("<FocusOut>", lambda e: self._notes_save_debounced(100))

        self._set_notes_enabled(False)
        self._notes_set_text("")

    def _set_notes_enabled(self, enabled: bool):
        self.notes_editor.config(state=("normal" if enabled else "disabled"))

    def _notes_set_text(self, text: str):
        self.notes_editor.config(state="normal")
        self.notes_editor.delete("1.0", tk.END)
        self.notes_editor.insert("1.0", text or "")
        self.notes_editor.edit_modified(False)
        if not (self.active_task_id):
            self.notes_editor.config(state="disabled")
        self._notes_dirty = False
        self._notes_render_preview()

    def _notes_get_text(self) -> str:
        return self.notes_editor.get("1.0", "end-1c")

    def _notes_on_change(self):
        if not self.active_task_id:
            return
        self._notes_dirty = True
        self._notes_save_debounced(650)  # autosave feel
        self._notes_render_preview()

    def _notes_save_debounced(self, delay_ms: int = 650):
        if self._notes_save_job:
            try:
                self.root.after_cancel(self._notes_save_job)
            except Exception:
                pass
        self._notes_save_job = self.root.after(delay_ms, self._notes_save_now)

    def _notes_save_now(self):
        if not self.active_task_id:
            return
        if not self._notes_dirty:
            return
        try:
            self.task_service.set_notes_md(self.active_task_id, self._notes_get_text())
            self._notes_dirty = False
            self.err.config(text="")
        except Exception as e:
            self.err.config(text=str(e))

    def _md_prefix_line(self, prefix: str):
        if not self.active_task_id:
            return
        try:
            idx = self.notes_editor.index("insert")
            line_start = idx.split(".")[0] + ".0"
            line_end = idx.split(".")[0] + ".end"
            line = self.notes_editor.get(line_start, line_end)

            # if already has that prefix, do nothing
            if line.startswith(prefix):
                return

            # remove existing header prefixes when switching headers
            if prefix.startswith("#"):
                stripped = line.lstrip()
                # remove leading #'s + spaces
                while stripped.startswith("#"):
                    stripped = stripped[1:]
                stripped = stripped.lstrip()
                self.notes_editor.delete(line_start, line_end)
                self.notes_editor.insert(line_start, prefix + stripped)
            else:
                self.notes_editor.insert(line_start, prefix)
            self._notes_on_change()
        except Exception:
            pass

    def _md_toggle_checkbox_line(self):
        if not self.active_task_id:
            return
        try:
            idx = self.notes_editor.index("insert")
            line_no = idx.split(".")[0]
            line_start = f"{line_no}.0"
            line_end = f"{line_no}.end"
            line = self.notes_editor.get(line_start, line_end)

            if "- [ ] " in line[:6]:
                line2 = line.replace("- [ ] ", "- [x] ", 1)
            elif "- [x] " in line[:6] or "- [X] " in line[:6]:
                line2 = line.replace("- [x] ", "- [ ] ", 1).replace(
                    "- [X] ", "- [ ] ", 1
                )
            else:
                # if no checkbox, make it
                line2 = "- [ ] " + line

            self.notes_editor.delete(line_start, line_end)
            self.notes_editor.insert(line_start, line2)
            self._notes_on_change()
        except Exception:
            pass

    def _notes_render_preview(self):
        text = self._notes_get_text() if self.active_task_id else ""

        self.notes_preview.config(state="normal")
        self.notes_preview.delete("1.0", tk.END)

        if not self.active_task_id:
            self.notes_preview.insert(
                "1.0", "Select a task to see preview.", ("muted",)
            )
            self.notes_preview.config(state="disabled")
            return

        lines = text.splitlines()
        for i, line in enumerate(lines):
            tag = None
            out = line

            if line.startswith("# "):
                tag = "h1"
                out = line[2:].strip()
            elif line.startswith("## "):
                tag = "h2"
                out = line[3:].strip()
            elif line.startswith("### "):
                tag = "h3"
                out = line[4:].strip()
            elif line.startswith("- [x] ") or line.startswith("- [X] "):
                self.notes_preview.insert(tk.END, "☑ ", ("check_on",))
                out = line[6:]
            elif line.startswith("- [ ] "):
                self.notes_preview.insert(tk.END, "☐ ", ("check_off",))
                out = line[6:]
            elif line.startswith("- "):
                self.notes_preview.insert(tk.END, "• ", ())
                out = line[2:]

            if tag:
                self.notes_preview.insert(tk.END, out + "\n", (tag,))
            else:
                self.notes_preview.insert(tk.END, out + "\n")

        self.notes_preview.config(state="disabled")

    # ---------- Entry placeholders ----------
    def _entry_focus_in(self, event):
        if self.task_entry.get().strip() == "Add a task and press Enter…":
            self.task_entry.delete(0, tk.END)

    def _entry_focus_out(self, event):
        if self.task_entry.get().strip() == "":
            self.task_entry.insert(0, "Add a task and press Enter…")

    # ---------- Columns ----------
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
        )
        listbox.pack(fill="both", expand=True, padx=10, pady=10)

        # NO visible scrollbar, but mousewheel works
        self._bind_mousewheel(listbox)

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

        # autosave previous task notes if switching
        if self._notes_current_task_id and self._notes_current_task_id != task_id:
            self._notes_save_now()

        self.active_task_id = task_id
        self.active_task_title = title
        self.active_task_status = column if task_id else None

        if task_id and title:
            self.sel_label.config(text=f"Selected: {title}")
            self.err.config(text="")
            self.notes_hint.config(text=f"Editing: {title}")
            self._set_notes_enabled(True)

            md = self.task_service.get_notes_md(task_id)
            self._notes_current_task_id = task_id
            self._notes_set_text(md or "")
        else:
            self.sel_label.config(text="Selected: -")
            self.notes_hint.config(text="Select a task to edit notes")
            self._notes_current_task_id = None
            self._set_notes_enabled(False)
            self._notes_set_text("")

        self._refresh_top_stats()

    # ---------- Tasks ----------
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

        title = self.active_task_title or "this task"
        ok = messagebox.askyesno(
            "Delete task?",
            f"Delete '{title}'?\n\nThis will also delete its sessions and notes.",
        )
        if not ok:
            return

        try:
            self.task_service.delete_task(self.active_task_id)
            self.err.config(text="")
            self.active_task_id = None
            self.active_task_title = None
            self.active_task_status = None
            self.sel_label.config(text="Selected: -")
            self.notes_hint.config(text="Select a task to edit notes")
            self._notes_current_task_id = None
            self._set_notes_enabled(False)
            self._notes_set_text("")
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
            self._set_notes_enabled(False)
            self._notes_set_text("")
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
            self._set_notes_enabled(False)
            self._notes_set_text("")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _open_pomodoro_for_selected(self):
        if not self.active_task_id:
            self.err.config(text="Select a task first.")
            return

        # ensure notes saved
        self._notes_save_now()

        self._state_repo.set("active_task_id", self.active_task_id)

        try:
            self.task_service.set_status(self.active_task_id, "doing")
        except Exception:
            pass

        self.err.config(text="")

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

        self.list_todo.delete(0, tk.END)
        self.list_doing.delete(0, tk.END)
        self.list_done.delete(0, tk.END)
        self._map_todo.clear()
        self._map_doing.clear()
        self._map_done.clear()

        for i, t in enumerate(todo):
            self.list_todo.insert(tk.END, t.title)
            self._map_todo[i] = t.id

        for i, t in enumerate(doing):
            self.list_doing.insert(tk.END, t.title)
            self._map_doing[i] = t.id

        for i, t in enumerate(done):
            self.list_done.insert(tk.END, t.title)
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

    def run(self):
        self.root.mainloop()
