# ui/slash_commands.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SlashCommandConfig:
    # Default stamp format yang lo pake
    stamp_fmt: str = "%a, %d %b %Y • %H:%M"
    day_fmt: str = "%a, %d %b %Y"


class SlashCommandExpander:
    """
    Single responsibility:
    - Expand slash commands in a tk.Text widget
    - Intended usage: call from <space> and <Return> key binds BEFORE insertion happens

    Supported:
      /now
      /today
      /yesterday
      /tomorrow
      /log
      /start
      /done
      /review
      /update
      /priority high|med|low
      /status todo|doing|done
      /tag <name>
    """

    def __init__(self, cfg: Optional[SlashCommandConfig] = None):
        self.cfg = cfg or SlashCommandConfig()

    def try_expand(self, text_widget) -> bool:
        """
        Returns True if expanded (replaced something), else False.
        """
        try:
            insert = text_widget.index("insert")
            # Get current line up to cursor (cursor is BEFORE current key is inserted)
            upto = text_widget.get("insert linestart", insert)
        except Exception:
            return False

        if not upto:
            return False

        # We only expand if cursor is at end of a token (no trailing whitespace)
        # Since this runs before space/enter insertion, this is usually true.
        if upto[-1].isspace():
            return False

        # Find the last token(s) from this line segment
        parts = upto.split()
        if not parts:
            return False

        last = parts[-1]
        last2 = parts[-2] if len(parts) >= 2 else ""

        now = dt.datetime.now()

        def fmt_now() -> str:
            return now.strftime(self.cfg.stamp_fmt)

        def fmt_day(d: dt.date) -> str:
            return d.strftime(self.cfg.day_fmt)

        replacement: Optional[str] = None
        token_to_replace: Optional[str] = None

        # --- date/time ---
        if last == "/now":
            replacement = fmt_now()
            token_to_replace = last
        elif last == "/today":
            replacement = fmt_day(now.date())
            token_to_replace = last
        elif last == "/yesterday":
            replacement = fmt_day((now - dt.timedelta(days=1)).date())
            token_to_replace = last
        elif last == "/tomorrow":
            replacement = fmt_day((now + dt.timedelta(days=1)).date())
            token_to_replace = last

        # --- log helpers ---
        elif last == "/log":
            replacement = f"### {fmt_now()}"
            token_to_replace = last
        elif last == "/start":
            replacement = f"Started: {fmt_now()}"
            token_to_replace = last
        elif last == "/done":
            replacement = f"Completed: {fmt_now()}"
            token_to_replace = last
        elif last == "/review":
            replacement = f"Review: {fmt_now()}"
            token_to_replace = last
        elif last == "/update":
            replacement = f"Last updated: {fmt_now()}"
            token_to_replace = last

        # --- metadata injectors (2 tokens) ---
        elif last2 == "/priority" and last in ("high", "med", "low"):
            replacement = f"priority: {last}"
            token_to_replace = f"{last2} {last}"
        elif last2 == "/status" and last in ("todo", "doing", "done"):
            replacement = f"status: {last}"
            token_to_replace = f"{last2} {last}"
        elif last2 == "/tag" and last:
            tag = "".join(ch for ch in last if ch.isalnum() or ch in ("_", "-")).strip()
            if tag:
                replacement = f"#{tag}"
                token_to_replace = f"{last2} {last}"

        if not replacement or not token_to_replace:
            return False

        # Replace only if the line actually ends with that token(s)
        suffix = upto.rstrip()
        if not suffix.endswith(token_to_replace):
            return False

        start_col = len(suffix) - len(token_to_replace)
        end_col = len(suffix)

        line_str, _ = insert.split(".")
        start_idx = f"{line_str}.{start_col}"
        end_idx = f"{line_str}.{end_col}"

        try:
            text_widget.delete(start_idx, end_idx)
            text_widget.insert(start_idx, replacement)
            return True
        except Exception:
            return False
