# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass
class EngineSnapshot:
    phase: str  # "work" | "break"
    remaining_sec: int
    is_running: bool
    is_idle: bool


class TimerEngine:
    """
    Pure countdown engine (no Tkinter).
    UI / Service triggers tick() each second.
    """

    def __init__(self, work_sec: int = 25 * 60, break_sec: int = 5 * 60):
        self.work_sec = int(work_sec)
        self.break_sec = int(break_sec)

        self.phase = "work"
        self.remaining_sec = self.work_sec
        self.is_running = False
        self.is_idle = True  # not started yet

    def snapshot(self) -> EngineSnapshot:
        return EngineSnapshot(
            phase=self.phase,
            remaining_sec=self.remaining_sec,
            is_running=self.is_running,
            is_idle=self.is_idle,
        )

    def start(self) -> None:
        # start fresh work phase
        self.phase = "work"
        self.remaining_sec = self.work_sec
        self.is_running = True
        self.is_idle = False

    def pause(self) -> None:
        if self.is_idle:
            return
        self.is_running = False

    def resume(self) -> None:
        if self.is_idle:
            return
        self.is_running = True

    def reset(self) -> None:
        self.phase = "work"
        self.remaining_sec = self.work_sec
        self.is_running = False
        self.is_idle = True

    def tick(self) -> bool:
        """
        Returns True if phase changed on this tick.
        """
        if self.is_idle or (not self.is_running):
            return False

        if self.remaining_sec > 0:
            self.remaining_sec -= 1

        if self.remaining_sec <= 0:
            # switch phase
            if self.phase == "work":
                self.phase = "break"
                self.remaining_sec = self.break_sec
            else:
                self.phase = "work"
                self.remaining_sec = self.work_sec
            return True

        return False
