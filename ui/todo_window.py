# ui/todo_window.py  (REPLACE) — Kanban + hidden scrollbars + Markdown Render/Edit + AUTOSAVE
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Optional

from markdown import markdown
from tkinterweb import HtmlFrame

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

        # notes state
        self._notes_current_task_id: Optional[str] = None
        self._notes_editing = False
        self._notes_dirty = False
        self._notes_save_job = None

        self._build_ui()
        self._refresh_all()

        # close hook (autosave)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- Hidden-scroll support ----------
    def _bind_mousewheel(self, widget):
        widget.bind(
            "<MouseWheel>",
            lambda e: widget.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: widget.yview_scroll(1, "units"))

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

        # Notes panel (Markdown Render/Edit)
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

    # ---------- Notes panel ----------
    def _build_notes_panel(self, parent: tk.Frame):
        header = tk.Frame(parent, bg=self.bg)
        header.pack(fill="x")

        tk.Label(
            header,
            text="Description",
            bg=self.bg,
            fg=self.text,
            font=("Montserrat", 14, "bold"),
        ).pack(anchor="w")
        self.notes_hint = tk.Label(
            header,
            text="Select a task to view description",
            bg=self.bg,
            fg=self.muted,
            font=("Montserrat", 9),
        )
        self.notes_hint.pack(anchor="w", pady=(2, 10))

        # one toggle button: Edit / Save
        topbar = tk.Frame(parent, bg=self.bg)
        topbar.pack(fill="x", pady=(0, 10))

        self.btn_edit_save = tk.Button(
            topbar,
            text="Edit",
            command=self._toggle_edit_save,
            bg=self.accent,
            fg="white",
            relief="flat",
            bd=0,
            activebackground=self.accent,
            activeforeground="white",
            font=("Montserrat", 10, "bold"),
            padx=14,
            pady=8,
            state="disabled",
        )
        self.btn_edit_save.pack(side="right")

        card = tk.Frame(
            parent, bg=self.panel, highlightthickness=1, highlightbackground=self.border
        )
        card.pack(fill="both", expand=True)

        # Render widget (HTML)
        self.md_view = HtmlFrame(card, horizontal_scrollbar="auto")
        self.md_view.pack(fill="both", expand=True)

        # Editor widget (Text) — hidden by default
        self.md_edit = tk.Text(
            card,
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

        # textarea UX
        self._bind_mousewheel(self.md_edit)
        self.md_edit.bind(
            "<Control-a>",
            lambda e: (self.md_edit.tag_add("sel", "1.0", "end-1c"), "break"),
        )
        self.md_edit.bind("<KeyRelease>", lambda e: self._notes_on_change())

        self._render_markdown_to_view("Select a task…")

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
        if not self.active_task_id:
            return
        if not self._notes_editing:
            return
        if not self._notes_dirty:
            return

        md_new = self.md_edit.get("1.0", "end-1c")
        try:
            self.task_service.set_notes_md(self.active_task_id, md_new)
            self._notes_dirty = False
            self.err.config(text="")
        except Exception as e:
            self.err.config(text=str(e))

    def _autosave_if_needed(self) -> bool:
        """
        Returns True if safe to continue.
        If editing and dirty, it autosaves now.
        If autosave fails, returns False (blocks action).
        """
        if not self._notes_editing:
            return True
        if not self.active_task_id:
            return True

        if self._notes_dirty:
            md_new = self.md_edit.get("1.0", "end-1c")
            try:
                self.task_service.set_notes_md(self.active_task_id, md_new)
                self._notes_dirty = False
                self.err.config(text="")
            except Exception as e:
                self.err.config(text=str(e))
                return False
        return True

    def _render_markdown_to_view(self, md_text: str):
        html_body = markdown(
            md_text or "", extensions=["extra", "sane_lists", "tables", "fenced_code"]
        )
        html = f"""
        <html>
          <head>
            <meta charset="utf-8"/>
            <style>
              body {{
                font-family: sans-serif;
                margin: 12px;
                color: #111827;
              }}
              h1,h2,h3 {{ margin: 12px 0 8px 0; }}
              p, li {{ line-height: 1.45; }}
              code {{
                background: #F3F4F6;
                padding: 2px 4px;
                border-radius: 6px;
              }}
              pre code {{
                display: block;
                padding: 10px;
                overflow-x: auto;
              }}
              table {{
                border-collapse: collapse;
                width: 100%;
              }}
              th, td {{
                border: 1px solid #E5E7EB;
                padding: 8px;
              }}
              blockquote {{
                border-left: 4px solid #E5E7EB;
                padding-left: 10px;
                color: #374151;
              }}
            </style>
          </head>
          <body>
            {html_body}
          </body>
        </html>
        """
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
            # enter edit mode
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

        # Save (manual) + back to render
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
        # autosave current edit first
        if not self._autosave_if_needed():
            return

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

        # when switching task, force view mode
        if self._notes_editing:
            self.md_edit.pack_forget()
            self.md_view.pack(fill="both", expand=True)
            self.btn_edit_save.config(text="Edit")
            self._notes_editing = False
            self._notes_dirty = False

        self.active_task_id = task_id
        self.active_task_title = title
        self.active_task_status = column if task_id else None

        if task_id and title:
            self.sel_label.config(text=f"Selected: {title}")
            self.err.config(text="")
            self.notes_hint.config(text=f"Viewing: {title}")
            self.btn_edit_save.config(state="normal", text="Edit")

            md = self.task_service.get_notes_md(task_id) or ""
            self._notes_current_task_id = task_id
            self._render_markdown_to_view(
                md
                if md.strip()
                else "_No description yet. Click **Edit** to write one._"
            )
        else:
            self.sel_label.config(text="Selected: -")
            self.notes_hint.config(text="Select a task to view description")
            self.btn_edit_save.config(state="disabled", text="Edit")
            self._notes_current_task_id = None
            self._render_markdown_to_view("Select a task…")

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

        if not self._autosave_if_needed():
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
            self.notes_hint.config(text="Select a task to view description")
            self.btn_edit_save.config(state="disabled", text="Edit")
            self._render_markdown_to_view("Select a task…")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _move_left(self):
        if not self.active_task_id or not self.active_task_status:
            self.err.config(text="Select a task first.")
            return

        if not self._autosave_if_needed():
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
            self.btn_edit_save.config(state="disabled", text="Edit")
            self._render_markdown_to_view("Select a task…")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _move_right(self):
        if not self.active_task_id or not self.active_task_status:
            self.err.config(text="Select a task first.")
            return

        if not self._autosave_if_needed():
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
            self.btn_edit_save.config(state="disabled", text="Edit")
            self._render_markdown_to_view("Select a task…")
            self._refresh_all()
        except Exception as e:
            self.err.config(text=str(e))

    def _open_pomodoro_for_selected(self):
        if not self.active_task_id:
            self.err.config(text="Select a task first.")
            return

        if not self._autosave_if_needed():
            return

        # exit edit mode to view (clean)
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

    def _on_close(self):
        # autosave before close
        try:
            self._autosave_if_needed()
        except Exception:
            pass
        try:
            self._db.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
