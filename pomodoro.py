#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import time
import tkinter as tk
import uuid


def _now_ts() -> int:
    return int(time.time())


class PomodoroTimer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pomodoro Timer")
        self.root.geometry("300x240")

        # =========================
        # DB (shared with todo app)
        # =========================
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "pomodoro.db"
        )
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._ensure_schema_min()

        self.active_task_id = None
        self.active_task_title = None

        # current running session tracking
        self._active_session_id = None
        self._active_session_kind = None

        # =========================
        # ALWAYS-ON-TOP (NO PERIODIC WATCHDOG)
        # =========================
        self.root.attributes("-topmost", True)
        self.root.lift()

        for ev in ("<FocusOut>", "<FocusIn>", "<Map>", "<Unmap>", "<Visibility>"):
            self.root.bind(ev, lambda e: self._nudge_topmost())

        self.root.bind("<Control-Shift-Up>", lambda e: self._force_raise())
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen())
        self.root.bind("<Control-r>", lambda e: self._reload_active_task_from_db())

        self.root.overrideredirect(False)

        # =========================
        # Timer states
        # =========================
        self.work_time = 25 * 60
        self.break_time = 5 * 60
        self.current_time = self.work_time
        self.is_working = True
        self.is_running = False
        self.timer_job = None

        # =========================
        # Fullscreen state
        # =========================
        self._is_fullscreen = False
        self._prev_geometry = None
        self._prev_topmost = True

        # =========================
        # Load icons (fallback)
        # =========================
        self.icon_play = self._safe_image("play.png")
        self.icon_pause = self._safe_image("pause.png")
        self.icon_refresh = self._safe_image("refresh.png")

        # Build UI
        self._build_ui()

        # init task from todo selection
        self._reload_active_task_from_db()
        self.update_display()
        self.update_background()

        # Drag-anywhere
        self._dragging = False
        self._drag_start = (0, 0)
        self.root.bind("<ButtonPress-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_motion)
        self.root.bind("<ButtonRelease-1>", self._on_drag_end)

        # close db on exit
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- DB ----------
    def _ensure_schema_min(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_ts INTEGER NOT NULL,
                end_ts INTEGER,
                duration_sec INTEGER
            );
        """)
        self.conn.commit()

    def _db_get_app_state(self, key: str):
        r = self.conn.execute(
            "SELECT value FROM app_state WHERE key=?", (key,)
        ).fetchone()
        return r["value"] if r else None

    def _db_get_task(self, task_id: str):
        return self.conn.execute(
            "SELECT id, title, status FROM tasks WHERE id=?", (task_id,)
        ).fetchone()

    def _db_set_task_status(self, task_id: str, status: str):
        ts = _now_ts()
        self.conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?", (status, ts, task_id)
        )
        self.conn.commit()

    def _db_start_session(self, task_id: str, kind: str):
        self._db_end_session()
        sid = str(uuid.uuid4())
        ts = _now_ts()
        self.conn.execute(
            "INSERT INTO sessions(id, task_id, kind, start_ts, end_ts, duration_sec) VALUES(?,?,?,?,?,?)",
            (sid, task_id, kind, ts, None, None),
        )
        self.conn.commit()
        self._active_session_id = sid
        self._active_session_kind = kind

    def _db_end_session(self):
        if not self._active_session_id:
            return
        sid = self._active_session_id
        row = self.conn.execute(
            "SELECT start_ts FROM sessions WHERE id=?", (sid,)
        ).fetchone()
        if row:
            start_ts = int(row["start_ts"])
            end_ts = _now_ts()
            dur = max(0, end_ts - start_ts)
            self.conn.execute(
                "UPDATE sessions SET end_ts=?, duration_sec=? WHERE id=?",
                (end_ts, dur, sid),
            )
            self.conn.commit()
        self._active_session_id = None
        self._active_session_kind = None

    # ---------- FIX: this method must be at class level (not nested) ----------
    def _reload_active_task_from_db(self):
        bg = "#4A90E2" if self.is_working else "#7ED321"
        try:
            self.task_entry.config(disabledbackground=bg)
        except Exception:
            pass

        task_id = self._db_get_app_state("active_task_id")
        if not task_id:
            self.active_task_id = None
            self.active_task_title = None
            self.task_entry.config(state="normal")
            self.task_entry.delete(0, tk.END)
            self.task_entry.insert(0, "select task from todo window")
            self.task_entry.config(state="disabled")
            self.info_label.config(
                text="Pick a task in Todo Window (Pomodoro disabled)"
            )
            self._update_start_enabled()
            return

        task = self._db_get_task(task_id)
        if not task:
            self.active_task_id = None
            self.active_task_title = None
            self.task_entry.config(state="normal")
            self.task_entry.delete(0, tk.END)
            self.task_entry.insert(0, "selected task not found")
            self.task_entry.config(state="disabled")
            self.info_label.config(
                text="Selected task missing. Re-pick in Todo Window."
            )
            self._update_start_enabled()
            return

        self.active_task_id = task["id"]
        self.active_task_title = task["title"]

        self.task_entry.config(state="normal")
        self.task_entry.delete(0, tk.END)
        self.task_entry.insert(0, self.active_task_title)
        self.task_entry.config(state="disabled")

        self.info_label.config(text="Ready")
        self._update_start_enabled()

    # ---------- UTIL ----------
    def _safe_image(self, filename):
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            if os.path.exists(path):
                return tk.PhotoImage(file=path)
        except Exception:
            pass
        return None

    # ---------- UI ----------
    def _build_ui(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        self.task_entry = tk.Entry(
            main_frame,
            font=("Montserrat", 10),
            fg="white",
            bg="#4A90E2",
            disabledforeground="white",
            disabledbackground="#4A90E2",
            relief="flat",
            justify="center",
            highlightthickness=0,
            borderwidth=0,
            insertbackground="white",
        )
        self.task_entry.insert(0, "select task from todo window")
        self.task_entry.config(state="disabled")
        self.task_entry.pack(pady=(0, 10), fill="x")

        self.time_label = tk.Label(
            main_frame, text="25:00", font=("Montserrat", 46, "bold"), fg="white"
        )
        self.time_label.pack(pady=(0, 5))

        self.info_label = tk.Label(
            main_frame,
            text="Pick a task in Todo Window (Pomodoro disabled)",
            font=("Montserrat", 8),
            fg="white",
        )
        self.info_label.pack(pady=(0, 5))

        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=0)

        if self.icon_play:
            self.start_pause_btn = tk.Button(
                button_frame,
                image=self.icon_play,
                command=self.toggle_timer,
                bg=self.root.cget("bg"),
                activebackground=self.root.cget("bg"),
                highlightthickness=0,
                borderwidth=0,
                relief="flat",
            )
        else:
            self.start_pause_btn = tk.Button(
                button_frame,
                text="▶",
                command=self.toggle_timer,
                bg=self.root.cget("bg"),
                activebackground=self.root.cget("bg"),
                highlightthickness=0,
                borderwidth=0,
                relief="flat",
                fg="white",
                font=("Montserrat", 12, "bold"),
            )
        self.start_pause_btn.pack(side="left", padx=5)

        if self.icon_refresh:
            self.reset_btn = tk.Button(
                button_frame,
                image=self.icon_refresh,
                command=self.reset_timer,
                bg=self.root.cget("bg"),
                activebackground=self.root.cget("bg"),
                highlightthickness=0,
                borderwidth=0,
                relief="flat",
            )
        else:
            self.reset_btn = tk.Button(
                button_frame,
                text="⟲",
                command=self.reset_timer,
                bg=self.root.cget("bg"),
                activebackground=self.root.cget("bg"),
                highlightthickness=0,
                borderwidth=0,
                relief="flat",
                fg="white",
                font=("Montserrat", 12, "bold"),
            )
        self.reset_btn.pack(side="left", padx=5)

        self.phase_label = tk.Label(
            main_frame, text="Deep Work", font=("Montserrat", 8, "bold"), fg="white"
        )
        self.phase_label.pack(pady=(0, 0))

        self._update_start_enabled()

    def _update_start_enabled(self):
        self.start_pause_btn.config(
            state=("normal" if self.active_task_id else "disabled")
        )

    def configure_bg_recursive(self, widget, bg_color):
        try:
            if widget.winfo_class() not in ("Button", "Entry"):
                widget.configure(bg=bg_color)
        except Exception:
            pass
        for child in widget.winfo_children():
            self.configure_bg_recursive(child, bg_color)

    # ---------- AOT helpers ----------
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

    # ---------- Fullscreen helpers ----------
    def _enter_fullscreen(self):
        if self._is_fullscreen:
            return
        try:
            self._prev_geometry = self.root.geometry()
            self._prev_topmost = bool(self.root.attributes("-topmost"))
        except Exception:
            self._prev_geometry = None
            self._prev_topmost = True

        self._is_fullscreen = True
        try:
            self.root.attributes("-fullscreen", True)
        except Exception:
            self.root.update_idletasks()
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+0+0")

        self.root.attributes("-topmost", True)
        self.root.lift()

    def _exit_fullscreen(self):
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False

        try:
            self.root.attributes("-fullscreen", False)
        except Exception:
            pass

        if self._prev_geometry:
            try:
                self.root.geometry(self._prev_geometry)
            except Exception:
                pass

        try:
            self.root.attributes("-topmost", bool(self._prev_topmost))
        except Exception:
            pass

        self.root.lift()

    # ---------- Drag-anywhere ----------
    def _on_drag_start(self, event):
        if self._is_fullscreen:
            return
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

    # ---------- Timer UI/Logic ----------
    def format_time(self, seconds):
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def update_display(self):
        self.time_label.config(text=self.format_time(self.current_time))
        self.phase_label.config(text="Deep Work" if self.is_working else "Rest Time")

    def update_background(self):
        bg_color = "#4A90E2" if self.is_working else "#7ED321"
        self.root.configure(bg=bg_color)
        for widget in self.root.winfo_children():
            self.configure_bg_recursive(widget, bg_color)

        self.start_pause_btn.config(bg=bg_color, activebackground=bg_color)
        self.reset_btn.config(bg=bg_color, activebackground=bg_color)
        self.task_entry.config(bg=bg_color)
        try:
            self.task_entry.config(disabledbackground=bg_color)
        except Exception:
            pass

    def toggle_timer(self):
        if not self.active_task_id:
            self._reload_active_task_from_db()
            return

        if self.is_running:
            self.pause_timer()
        else:
            self.start_timer()

    def start_timer(self):
        if not self.active_task_id:
            self.info_label.config(
                text="Pick a task in Todo Window (Pomodoro disabled)"
            )
            self._update_start_enabled()
            return

        try:
            self._db_set_task_status(self.active_task_id, "doing")
        except Exception:
            pass

        kind = "work" if self.is_working else "break"
        self._db_start_session(self.active_task_id, kind)

        self.is_running = True
        if self.icon_pause:
            self.start_pause_btn.config(image=self.icon_pause)
        else:
            self.start_pause_btn.config(text="⏸")
        self.info_label.config(text="Timer running...")
        self.countdown()

    def pause_timer(self):
        self.is_running = False
        if self.icon_play:
            self.start_pause_btn.config(image=self.icon_play)
        else:
            self.start_pause_btn.config(text="▶")
        self.info_label.config(text="Timer paused")

        self._db_end_session()

        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def reset_timer(self):
        self.is_running = False
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

        self._db_end_session()
        self._exit_fullscreen()

        self.is_working = True
        self.current_time = self.work_time

        if self.icon_play:
            self.start_pause_btn.config(image=self.icon_play)
        else:
            self.start_pause_btn.config(text="▶")
        self.info_label.config(text="Timer reset to Deep Work")

        self.update_display()
        self.update_background()

    def countdown(self):
        if self.is_running and self.current_time > 0:
            self.current_time -= 1
            self.update_display()
            self.timer_job = self.root.after(1000, self.countdown)
        elif self.is_running and self.current_time == 0:
            self.phase_complete()

    def phase_complete(self):
        self._db_end_session()

        if self.is_working:
            self.is_working = False
            self.current_time = self.break_time
            self.info_label.config(text="Work complete! Take a break!")
            self._enter_fullscreen()
        else:
            self.is_working = True
            self.current_time = self.work_time
            self.info_label.config(text="Break over! Back to work!")
            self._exit_fullscreen()

        if self.active_task_id:
            kind = "work" if self.is_working else "break"
            self._db_start_session(self.active_task_id, kind)

        self.update_display()
        self.update_background()
        self.timer_job = self.root.after(1000, self.countdown)

    def _on_close(self):
        try:
            self._db_end_session()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = PomodoroTimer()
    app.run()
