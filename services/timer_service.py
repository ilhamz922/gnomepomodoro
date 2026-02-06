# -*- coding: utf-8 -*-

import time
from typing import Callable, Optional

from core.timer_engine import EngineSnapshot, TimerEngine
from storage.repos import SessionRepo, TaskRepo


def _now_ts() -> int:
    return int(time.time())


class TimerService:
    """
    Orchestrates:
    - TimerEngine state
    - SQLite session logging
    - Task status transitions (todo -> doing)
    - Callbacks for UI
    """

    def __init__(self, session_repo: SessionRepo, task_repo: TaskRepo):
        self.session_repo = session_repo
        self.task_repo = task_repo

        self.engine = TimerEngine(work_sec=25 * 60, break_sec=5 * 60)

        self.active_task_id: Optional[str] = None
        self._active_session_id: Optional[str] = None
        self._active_session_kind: Optional[str] = None

        self._on_tick: Optional[Callable[[EngineSnapshot], None]] = None
        self._on_phase_change: Optional[Callable[[EngineSnapshot], None]] = None
        self._on_state_change: Optional[Callable[[EngineSnapshot], None]] = None

    # ----- Callbacks -----
    def set_on_tick(self, fn: Callable[[EngineSnapshot], None]) -> None:
        self._on_tick = fn

    def set_on_phase_change(self, fn: Callable[[EngineSnapshot], None]) -> None:
        self._on_phase_change = fn

    def set_on_state_change(self, fn: Callable[[EngineSnapshot], None]) -> None:
        self._on_state_change = fn

    def _emit_tick(self) -> None:
        if self._on_tick:
            self._on_tick(self.engine.snapshot())

    def _emit_phase_change(self) -> None:
        if self._on_phase_change:
            self._on_phase_change(self.engine.snapshot())

    def _emit_state_change(self) -> None:
        if self._on_state_change:
            self._on_state_change(self.engine.snapshot())

    # ----- Public API -----
    def get_snapshot(self) -> EngineSnapshot:
        return self.engine.snapshot()

    def set_active_task(self, task_id: Optional[str]) -> None:
        self.active_task_id = task_id

    def start(self, task_id: str) -> None:
        # hard constraint: must have task
        if not task_id:
            raise ValueError("Task must be selected before starting timer.")

        task = self.task_repo.get(task_id)
        if task is None:
            raise ValueError("Selected task not found.")

        self.active_task_id = task_id

        snap = self.engine.snapshot()
        if snap.is_idle:
            # start fresh
            self.engine.start()
            # auto set doing
            self.task_repo.set_status(task_id, "doing")
            # start session logging
            self._start_session(kind=self.engine.snapshot().phase)
        else:
            # if paused, resume
            if not snap.is_running:
                self.engine.resume()
                # resume creates a new session for current phase
                self._start_session(kind=self.engine.snapshot().phase)

        self._emit_state_change()
        self._emit_tick()

    def pause(self) -> None:
        snap = self.engine.snapshot()
        if snap.is_idle:
            return
        if snap.is_running:
            self.engine.pause()
            self._end_session()
        self._emit_state_change()
        self._emit_tick()

    def reset(self) -> None:
        # stop everything + end active session
        self._end_session()
        self.engine.reset()
        self._emit_state_change()
        self._emit_tick()

    def mark_done_and_stop(self, task_id: str) -> None:
        # set done
        self.task_repo.set_status(task_id, "done")
        # if currently active + running => stop
        if self.active_task_id == task_id:
            self.reset()

    def tick(self) -> None:
        """
        Should be called once per second by UI loop.
        Handles phase switching + logging boundaries.
        """
        snap_before = self.engine.snapshot()
        if snap_before.is_idle or (not snap_before.is_running):
            return

        phase_changed = self.engine.tick()

        # always emit tick
        self._emit_tick()

        if phase_changed:
            # close old session, open new session
            self._end_session()
            self._start_session(kind=self.engine.snapshot().phase)
            self._emit_phase_change()

    # ----- Session logging internals -----
    def _start_session(self, kind: str) -> None:
        if not self.active_task_id:
            # should never happen given product constraint
            return
        # end any previous session just in case
        self._end_session()

        log = self.session_repo.start_session(
            task_id=self.active_task_id,
            kind=kind,
            start_ts=_now_ts(),
        )
        self._active_session_id = log.id
        self._active_session_kind = kind

    def _end_session(self) -> None:
        if self._active_session_id:
            try:
                self.session_repo.end_session(self._active_session_id, end_ts=_now_ts())
            finally:
                self._active_session_id = None
                self._active_session_kind = None
