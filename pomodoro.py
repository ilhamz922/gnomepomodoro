#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
import os

class PomodoroTimer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pomodoro Timer")
        self.root.geometry("300x240")  # Tinggi ditambahin buat task field

        # =========================
        # ALWAYS-ON-TOP (NO PERIODIC WATCHDOG)
        # =========================
        # set awal aja (tanpa alert/watchdog berkala)
        self.root.attributes('-topmost', True)
        self.root.lift()

        # event hooks (opsional, non-berkala): hanya nudge saat event
        for ev in ('<FocusOut>', '<FocusIn>', '<Map>', '<Unmap>', '<Visibility>'):
            self.root.bind(ev, lambda e: self._nudge_topmost())

        # hotkey manual angkat
        self.root.bind('<Control-Shift-Up>', lambda e: self._force_raise())

        # hotkey aman: ESC keluar fullscreen (biar gak kejebak)
        self.root.bind('<Escape>', lambda e: self._exit_fullscreen())

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
        # Fullscreen state
        # =========================
        self._is_fullscreen = False
        self._prev_geometry = None
        self._prev_topmost = True

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
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, fill='both', padx=10, pady=10)

        # ========== TASK FIELD ==========
        self.task_entry = tk.Entry(
            main_frame,
            font=('Montserrat', 10),
            fg='white',
            bg='#4A90E2',
            relief='flat',
            justify='center',
            highlightthickness=0,
            borderwidth=0,
            insertbackground='white'
        )
        self.task_entry.insert(0, "type your task here")
        self.task_entry.pack(pady=(0, 10), fill='x')

        self.task_entry.bind('<FocusIn>', self._on_task_focus_in)
        self.task_entry.bind('<FocusOut>', self._on_task_focus_out)
        # ======================================

        self.time_label = tk.Label(
            main_frame,
            text="25:00",
            font=('Montserrat', 46, 'bold'),
            fg='white'
        )
        self.time_label.pack(pady=(0, 5))

        self.info_label = tk.Label(
            main_frame,
            text="Click Start to begin",
            font=('Montserrat', 8),
            fg='white'
        )
        self.info_label.pack(pady=(0, 5))

        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=0)

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

        self.phase_label = tk.Label(
            main_frame,
            text="Deep Work",
            font=('Montserrat', 8, 'bold'),
            fg='white'
        )
        self.phase_label.pack(pady=(0, 0))

    # ---------- Task Entry Placeholder ----------
    def _on_task_focus_in(self, event):
        if self.task_entry.get() == "type your task here":
            self.task_entry.delete(0, tk.END)

    def _on_task_focus_out(self, event):
        if self.task_entry.get().strip() == "":
            self.task_entry.insert(0, "type your task here")

    def configure_bg_recursive(self, widget, bg_color):
        try:
            if widget.winfo_class() not in ('Button', 'Entry'):
                widget.configure(bg=bg_color)
        except Exception:
            pass
        for child in widget.winfo_children():
            self.configure_bg_recursive(child, bg_color)

    # ---------- AOT helpers (NO PERIODIC WATCHDOG) ----------
    def _nudge_topmost(self):
        try:
            # kalau fullscreen, tetap boleh, tapi jangan spam
            self.root.attributes('-topmost', False)
            self.root.after(10, lambda: (
                self.root.lift(),
                self.root.attributes('-topmost', True)
            ))
        except Exception:
            pass

    def _force_raise(self):
        self.root.lift()
        self.root.attributes('-topmost', True)

    # ---------- Fullscreen helpers ----------
    def _enter_fullscreen(self):
        if self._is_fullscreen:
            return
        try:
            self._prev_geometry = self.root.geometry()
            self._prev_topmost = bool(self.root.attributes('-topmost'))
        except Exception:
            self._prev_geometry = None
            self._prev_topmost = True

        self._is_fullscreen = True

        # fullscreen + keep on top supaya bener-bener nutup layar
        try:
            self.root.attributes('-fullscreen', True)
        except Exception:
            # fallback kalau fullscreen attribute gak ada
            self.root.update_idletasks()
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+0+0")

        self.root.attributes('-topmost', True)
        self.root.lift()

    def _exit_fullscreen(self):
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False

        try:
            self.root.attributes('-fullscreen', False)
        except Exception:
            pass

        if self._prev_geometry:
            try:
                self.root.geometry(self._prev_geometry)
            except Exception:
                pass

        # restore topmost (tetap default True sesuai behaviour awal)
        try:
            self.root.attributes('-topmost', bool(self._prev_topmost))
        except Exception:
            pass

        self.root.lift()

    # ---------- Drag-anywhere ----------
    def _on_drag_start(self, event):
        # disable drag kalau fullscreen (biar gak aneh)
        if self._is_fullscreen:
            return
        if event.widget == self.task_entry:
            return
        self._dragging = True
        self._drag_start = (event.x_root, event.y_root)
        try:
            geo = self.root.geometry()  # "300x200+X+Y"
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
        bg_color = '#4A90E2' if self.is_working else '#7ED321'
        self.root.configure(bg=bg_color)
        for widget in self.root.winfo_children():
            self.configure_bg_recursive(widget, bg_color)

        self.start_pause_btn.config(bg=bg_color, activebackground=bg_color)
        self.reset_btn.config(bg=bg_color, activebackground=bg_color)
        self.task_entry.config(bg=bg_color)

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

        # keluar fullscreen kalau lagi break fullscreen
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
        # Switch phases
        if self.is_working:
            self.is_working = False
            self.current_time = self.break_time
            self.info_label.config(text="Work complete! Take a break!")
            # BREAK => fullscreen
            self._enter_fullscreen()
        else:
            self.is_working = True
            self.current_time = self.work_time
            self.info_label.config(text="Break over! Back to work!")
            # WORK => exit fullscreen
            self._exit_fullscreen()

        self.update_display()
        self.update_background()

        # Auto-start next phase
        self.timer_job = self.root.after(1000, self.countdown)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = PomodoroTimer()
    app.run()
