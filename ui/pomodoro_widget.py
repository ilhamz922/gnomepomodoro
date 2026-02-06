# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from core.timer_engine import EngineSnapshot
from services.timer_service import TimerService


def format_time(seconds: int) -> str:
    m = max(0, seconds) // 60
    s = max(0, seconds) % 60
    return f"{m:02d}:{s:02d}"


class PomodoroWidget(ttk.Frame):
    def __init__(
        self,
        master,
        timer_service: TimerService,
        get_active_task_id: Callable[[], Optional[str]],
        on_request_refresh: Callable[[], None],
    ):
        super().__init__(master)

        self.timer_service = timer_service
        self.get_active_task_id = get_active_task_id
        self.on_request_refresh = on_request_refresh

        self._tick_job = None
        self._is_fullscreen = False
        self._prev_geometry = None
        self._prev_topmost = True

        self._build_ui()

        # wire callbacks from service -> widget UI
        self.timer_service.set_on_tick(self._on_tick)
        self.timer_service.set_on_phase_change(self._on_phase_change)
        self.timer_service.set_on_state_change(self._on_state_change)

        # ESC to exit fullscreen
        self.winfo_toplevel().bind("<Escape>", lambda e: self._exit_fullscreen())

        # initial render
        self._render(self.timer_service.get_snapshot())
        self._update_buttons()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        self.phase_var = tk.StringVar(value="Deep Work")
        self.time_var = tk.StringVar(value="25:00")
        self.info_var = tk.StringVar(value="Select a task to start")

        title = ttk.Label(self, text="Pomodoro", font=("Sans", 12, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.phase_label = ttk.Label(self, textvariable=self.phase_var)
        self.phase_label.grid(row=1, column=0, sticky="w")

        self.time_label = ttk.Label(
            self, textvariable=self.time_var, font=("Sans", 32, "bold")
        )
        self.time_label.grid(row=2, column=0, sticky="w", pady=(8, 4))

        self.info_label = ttk.Label(self, textvariable=self.info_var)
        self.info_label.grid(row=3, column=0, sticky="w", pady=(0, 10))

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, sticky="w")

        self.start_btn = ttk.Button(btns, text="Start", command=self._start)
        self.pause_btn = ttk.Button(btns, text="Pause", command=self._pause)
        self.reset_btn = ttk.Button(btns, text="Reset", command=self._reset)

        self.start_btn.grid(row=0, column=0, padx=(0, 6))
        self.pause_btn.grid(row=0, column=1, padx=(0, 6))
        self.reset_btn.grid(row=0, column=2)

    def _update_buttons(self):
        snap = self.timer_service.get_snapshot()
        has_task = bool(self.get_active_task_id())

        # Start is only enabled if task selected AND (idle or paused)
        if not has_task:
            self.start_btn.state(["disabled"])
        else:
            if snap.is_running:
                self.start_btn.state(["disabled"])
            else:
                self.start_btn.state(["!disabled"])

        # Pause enabled only if running
        if snap.is_running:
            self.pause_btn.state(["!disabled"])
        else:
            self.pause_btn.state(["disabled"])

        # Reset enabled if not idle
        if snap.is_idle:
            self.reset_btn.state(["disabled"])
        else:
            self.reset_btn.state(["!disabled"])

    def _start(self):
        task_id = self.get_active_task_id()
        if not task_id:
            self.info_var.set("Pick a task first.")
            self._update_buttons()
            return

        self.timer_service.start(task_id)
        self._ensure_tick_loop()
        self.on_request_refresh()

    def _pause(self):
        self.timer_service.pause()
        self._stop_tick_loop()
        self.on_request_refresh()

    def _reset(self):
        self.timer_service.reset()
        self._stop_tick_loop()
        self._exit_fullscreen()
        self.on_request_refresh()

    # ---- Tick loop (UI-driven) ----
    def _ensure_tick_loop(self):
        if self._tick_job is None:
            self._tick_job = self.after(1000, self._tick_once)

    def _stop_tick_loop(self):
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None

    def _tick_once(self):
        self._tick_job = None
        snap = self.timer_service.get_snapshot()
        if snap.is_running:
            self.timer_service.tick()
            # schedule next tick
            self._tick_job = self.after(1000, self._tick_once)

    # ---- Service callbacks ----
    def _on_tick(self, snap: EngineSnapshot):
        self._render(snap)
        self._update_buttons()

    def _on_phase_change(self, snap: EngineSnapshot):
        # break => fullscreen, work => exit
        if snap.phase == "break":
            self._enter_fullscreen()
            self.info_var.set("Break time. Press ESC to exit fullscreen.")
        else:
            self._exit_fullscreen()
            self.info_var.set("Back to work.")
        self._render(snap)
        self._update_buttons()
        self.on_request_refresh()

    def _on_state_change(self, snap: EngineSnapshot):
        self._render(snap)
        self._update_buttons()
        self.on_request_refresh()

    def _render(self, snap: EngineSnapshot):
        self.time_var.set(format_time(snap.remaining_sec))
        self.phase_var.set("Deep Work" if snap.phase == "work" else "Rest Time")

        if not self.get_active_task_id():
            self.info_var.set("Select a task to start")
        else:
            if snap.is_idle:
                self.info_var.set("Ready")
            elif snap.is_running:
                self.info_var.set("Running...")
            else:
                self.info_var.set("Paused")

    # ---- Fullscreen helpers ----
    def _enter_fullscreen(self):
        if self._is_fullscreen:
            return
        top = self.winfo_toplevel()
        try:
            self._prev_geometry = top.geometry()
            self._prev_topmost = bool(top.attributes("-topmost"))
        except Exception:
            self._prev_geometry = None
            self._prev_topmost = True

        self._is_fullscreen = True
        try:
            top.attributes("-fullscreen", True)
        except Exception:
            top.update_idletasks()
            w = top.winfo_screenwidth()
            h = top.winfo_screenheight_
