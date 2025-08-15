#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
import time
import os

class PomodoroTimer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pomodoro Timer")
        self.root.geometry("300x200")

        # =========================
        # ALWAYS-ON-TOP Enhancements
        # =========================
        # set awal
        self.root.attributes('-topmost', True)
        self.root.lift()

        # watchdog berkala
        self.root.after(2000, self._keep_on_top)

        # event hooks: saat fokus hilang / muncul lagi / di-map ulang → nudge
        for ev in ('<FocusOut>', '<FocusIn>', '<Map>', '<Unmap>', '<Visibility>'):
            self.root.bind(ev, lambda e: self._nudge_topmost())

        # hotkey manual angkat
        self.root.bind('<Control-Shift-Up>', lambda e: self._force_raise())

        # Keep window decorations for easy dragging via titlebar (sesuai kode asli)
        self.root.overrideredirect(False)

        # =========================
        # Timer states (asli)
        # =========================
        self.work_time = 25 * 60  # 25 minutes
        self.break_time = 5 * 60  # 5 minutes
        self.current_time = self.work_time
        self.is_working = True
        self.is_running = False
        self.timer_job = None

        # =========================
        # Load icons (fallback ke label kalau ikon tidak ada)
        # =========================
        self.icon_play = self._safe_image("play.png")
        self.icon_pause = self._safe_image("pause.png")
        self.icon_refresh = self._safe_image("refresh.png")

        # Build UI
        self._build_ui()
        self.update_display()
        self.update_background()

        # =========================
        # Drag-anywhere (opsional)
        # =========================
        # Kamu tetap bisa drag dari titlebar; ini tambahan biar bisa drag di area mana saja.
        self._dragging = False
        self._drag_start = (0, 0)
        self.root.bind("<ButtonPress-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_motion)
        self.root.bind("<ButtonRelease-1>", self._on_drag_end)

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
        # Main frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, fill='both', padx=10, pady=10)

        # Progress info
        self.info_label = tk.Label(
            main_frame,
            text="Click Start to begin",
            font=('Montserrat', 8),
            fg='white'
        )
        self.info_label.pack(pady=(0, 0))

        # Timer display
        self.time_label = tk.Label(
            main_frame,
            text="25:00",
            font=('Montserrat', 46, 'bold'),
            fg='white'
        )
        self.time_label.pack(pady=(0, 0))

        # Button frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=0)

        # Start/Pause button
        if self.icon_play:
            self.start_pause_btn = tk.Button(
                button_frame,
                image=self.icon_play,
                command=self.toggle_timer,
                bg=self.root.cget('bg'),
                activebackground=self.root.cget('bg'),
                highlightthickness=0,
                borderwidth=0,
                relief='flat'
            )
        else:
            self.start_pause_btn = tk.Button(
                button_frame,
                text="▶",
                command=self.toggle_timer,
                bg=self.root.cget('bg'),
                activebackground=self.root.cget('bg'),
                highlightthickness=0,
                borderwidth=0,
                relief='flat',
                fg='white',
                font=('Montserrat', 12, 'bold')
            )
        self.start_pause_btn.pack(side='left', padx=5)

        # Reset button
        if self.icon_refresh:
            self.reset_btn = tk.Button(
                button_frame,
                image=self.icon_refresh,
                command=self.reset_timer,
                bg=self.root.cget('bg'),
                activebackground=self.root.cget('bg'),
                highlightthickness=0,
                borderwidth=0,
                relief='flat'
            )
        else:
            self.reset_btn = tk.Button(
                button_frame,
                text="⟲",
                command=self.reset_timer,
                bg=self.root.cget('bg'),
                activebackground=self.root.cget('bg'),
                highlightthickness=0,
                borderwidth=0,
                relief='flat',
                fg='white',
                font=('Montserrat', 12, 'bold')
            )
        self.reset_btn.pack(side='left', padx=5)

        # Phase label
        self.phase_label = tk.Label(
            main_frame,
            text="Deep Work",
            font=('Montserrat', 8, 'bold'),
            fg='white'
        )
        self.phase_label.pack(pady=(0, 0))

    def configure_bg_recursive(self, widget, bg_color):
        try:
            # jangan ubah bg Button karena kita set manual
            if widget.winfo_class() != 'Button':
                widget.configure(bg=bg_color)
        except Exception:
            pass
        for child in widget.winfo_children():
            self.configure_bg_recursive(child, bg_color)

    # ---------- AOT helpers ----------
    def _keep_on_top(self):
        """Watchdog: re-assert topmost & lift berkala."""
        try:
            # Skip kalau minimized/withdrawn
            if self.root.state() not in ('iconic', 'withdrawn'):
                self.root.lift()
                self.root.attributes('-topmost', True)
        finally:
            self.root.after(2000, self._keep_on_top)

    def _nudge_topmost(self):
        """Toggle cepat supaya WM ‘ngeh’ perubahan."""
        try:
            self.root.attributes('-topmost', False)
            self.root.after(10, lambda: (
                self.root.lift(),
                self.root.attributes('-topmost', True)
            ))
        except Exception:
            pass

    def _force_raise(self):
        """Hotkey angkat manual (Ctrl+Shift+Up)."""
        self.root.lift()
        self.root.attributes('-topmost', True)

    # ---------- Drag-anywhere ----------
    def _on_drag_start(self, event):
        # mulai drag di area manapun
        self._dragging = True
        self._drag_start = (event.x_root, event.y_root)
        # simpan posisi awal
        try:
            geo = self.root.geometry()  # e.g. "300x200+X+Y"
            _, pos = geo.split('+', 1)
            x_str, y_str = pos.split('+', 1)
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
        if self.is_working:
            bg_color = '#4A90E2'  # Blue for deep work
        else:
            bg_color = '#7ED321'  # Green for rest

        self.root.configure(bg=bg_color)
        for widget in self.root.winfo_children():
            self.configure_bg_recursive(widget, bg_color)

        # Update button backgrounds to match
        self.start_pause_btn.config(bg=bg_color, activebackground=bg_color)
        self.reset_btn.config(bg=bg_color, activebackground=bg_color)

    def toggle_timer(self):
        if self.is_running:
            self.pause_timer()
        else:
            self.start_timer()

    def start_timer(self):
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
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def reset_timer(self):
        self.is_running = False
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

        # Reset to work phase
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
        # Switch phases
        if self.is_working:
            self.is_working = False
            self.current_time = self.break_time
            self.info_label.config(text="Work complete! Take a break!")
        else:
            self.is_working = True
            self.current_time = self.work_time
            self.info_label.config(text="Break over! Back to work!")

        # Update UI
        self.update_display()
        self.update_background()

        # Auto-start next phase
        self.timer_job = self.root.after(1000, self.countdown)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = PomodoroTimer()
    app.run()
