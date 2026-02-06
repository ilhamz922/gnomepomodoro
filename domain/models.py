# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: str  # todo | doing | done
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class SessionLog:
    id: str
    task_id: str
    kind: str  # work | break
    start_ts: int
    end_ts: Optional[int]
    duration_sec: Optional[int]
