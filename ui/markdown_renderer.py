# ui/markdown_renderer.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from markdown import markdown


@dataclass(frozen=True)
class MarkdownTheme:
    text: str = "#111827"
    muted: str = "#6B7280"
    border: str = "#E5E7EB"
    panel: str = "#FFFFFF"
    codebg: str = "#F3F4F6"
    link: str = "#2563EB"
    quote: str = "#3B82F6"


class MarkdownRenderer:
    """
    Single responsibility:
    - Convert MD -> HTML
    - Provide CSS

    Notes (important):
    tkinterweb (tkhtml) is limited HTML. Even if pymdown works, tags like <input>, <details>,
    and tabbed radio/label constructs may not render.

    So we do TWO layers:
    1) Preprocess: turn tasklists/tabs/details into "safe" markdown that will render in tkhtml.
    2) Still enable pymdown extensions when available (best effort).
    """

    def __init__(self, theme: Optional[MarkdownTheme] = None):
        self.theme = theme or MarkdownTheme()

    # ---------- preprocessing (make features render in tkinterweb) ----------
    def preprocess(self, md_text: str) -> str:
        """
        Convert features that rely on unsupported HTML (tkhtml) into safe equivalents:
        - Tasklist: "- [ ]" -> "- ☐", "- [x]" -> "- ☑"
        - Tabbed:   === "Title" blocks -> headings + separators
        - Details:  ??? note "Title"   -> !!! note "Title" (admonition)
        """
        if not md_text:
            return ""

        lines = md_text.splitlines()

        # 1) task list -> unicode checkbox (works everywhere)
        task_unchecked = re.compile(r"^(\s*[-*+]\s+)\[ \]\s+")
        task_checked = re.compile(r"^(\s*[-*+]\s+)\[(x|X)\]\s+")

        # 2) tabbed syntax support (fallback)
        #    === "Tab"
        tab_re = re.compile(r'^\s*===\s+"([^"]+)"\s*$')

        # 3) details syntax fallback: ??? note "Title" -> !!! note "Title"
        details_re = re.compile(r'^\s*\?\?\?\+?\s+(\w+)(\s+"[^"]+")?\s*$')

        out: List[str] = []
        in_tab = False
        tab_started = False

        for raw in lines:
            line = raw

            # details -> admonition
            m_det = details_re.match(line)
            if m_det:
                kind = m_det.group(1) or "note"
                title = (m_det.group(2) or "").strip()
                # Convert to admonition syntax (div-based HTML => tkhtml friendly)
                out.append(f"!!! {kind}{(' ' + title) if title else ''}")
                in_tab = False
                continue

            # tabs fallback
            m_tab = tab_re.match(line)
            if m_tab:
                tab_title = m_tab.group(1).strip()
                if tab_started:
                    out.append("")
                    out.append("---")
                    out.append("")
                out.append(f"### {tab_title}")
                out.append("")
                in_tab = True
                tab_started = True
                continue

            # if inside tabbed content, pymdown expects 4-space indent,
            # but for our fallback we want normal markdown -> strip 4 leading spaces if present.
            if in_tab:
                if line.startswith("    "):
                    line = line[4:]
                elif line.strip() == "":
                    # keep blank lines
                    pass
                else:
                    # if content is not indented, treat as outside tab content
                    in_tab = False

            # tasklist -> unicode
            line = task_checked.sub(r"\1☑ ", line)
            line = task_unchecked.sub(r"\1☐ ", line)

            out.append(line)

        return "\n".join(out)

    # ---------- extensions ----------
    def extensions(self) -> Tuple[List[str], Dict]:
        exts: List[str] = [
            "extra",
            "sane_lists",
            "tables",
            "fenced_code",
            "nl2br",
            "attr_list",
            "admonition",
            "toc",
        ]
        cfg: Dict = {}

        # best-effort: enable pymdown features (even if tkhtml may ignore some HTML tags)
        try:
            import pymdownx  # noqa: F401

            exts += [
                "pymdownx.tasklist",
                "pymdownx.superfences",
                "pymdownx.highlight",
                "pymdownx.tilde",
                "pymdownx.strikethrough",
                "pymdownx.details",
                "pymdownx.magiclink",
                "pymdownx.tabbed",
            ]
            cfg.update(
                {
                    "pymdownx.tasklist": {
                        "custom_checkbox": True,
                        "clickable_checkbox": False,
                    },
                    "pymdownx.highlight": {"use_pygments": False},
                    "pymdownx.tabbed": {"alternate_style": True},
                }
            )
        except Exception:
            pass

        return exts, cfg

    # ---------- CSS ----------
    def css(self) -> str:
        t = self.theme
        return f"""
        :root {{
          --text: {t.text};
          --muted: {t.muted};
          --border: {t.border};
          --panel: {t.panel};
          --codebg: {t.codebg};
          --link: {t.link};
          --quote: {t.quote};
          --soft: #F9FAFB;
        }}

        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          margin: 14px;
          color: var(--text);
          background: var(--panel);
          font-size: 14px;
          line-height: 1.55;
          word-wrap: break-word;
          overflow-wrap: anywhere;
        }}

        h1, h2, h3, h4 {{
          margin: 1.0em 0 0.5em;
          line-height: 1.2;
        }}
        h1 {{ font-size: 1.35em; }}
        h2 {{ font-size: 1.20em; }}
        h3 {{ font-size: 1.08em; }}

        p {{ margin: 0.6em 0; }}

        a {{ color: var(--link); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        hr {{
          border: 0;
          border-top: 1px solid var(--border);
          margin: 1em 0;
        }}

        ul, ol {{ padding-left: 1.2em; margin: 0.6em 0; }}
        li {{ margin: 0.25em 0; }}

        blockquote {{
          margin: 0.8em 0;
          padding: 0.2em 0 0.2em 0.9em;
          border-left: 4px solid var(--quote);
          color: var(--muted);
          background: var(--soft);
          border-radius: 8px;
        }}

        table {{
          border-collapse: collapse;
          width: 100%;
          margin: 0.8em 0;
          font-size: 0.95em;
        }}
        th, td {{
          border: 1px solid var(--border);
          padding: 8px 10px;
          vertical-align: top;
        }}
        th {{
          background: var(--soft);
          font-weight: 700;
        }}

        code {{
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
          background: var(--codebg);
          padding: 2px 5px;
          border-radius: 6px;
          font-size: 0.92em;
        }}

        pre {{
          background: var(--codebg);
          padding: 10px 12px;
          border-radius: 10px;
          overflow-x: auto;
          border: 1px solid var(--border);
          margin: 0.9em 0;
        }}
        pre code {{
          background: transparent;
          padding: 0;
          border-radius: 0;
          display: block;
          white-space: pre;
        }}

        /* admonition (div-based) => tkhtml friendly */
        .admonition {{
          border: 1px solid var(--border);
          background: var(--soft);
          border-radius: 10px;
          padding: 10px 12px;
          margin: 0.8em 0;
        }}
        .admonition-title {{
          font-weight: 800;
          margin-bottom: 6px;
        }}
        """

    # ---------- render ----------
    def to_html(self, md_text: str) -> str:
        safe_md = self.preprocess(md_text or "")
        exts, cfg = self.extensions()
        body = markdown(
            safe_md,
            extensions=exts,
            extension_configs=cfg,
            output_format="html5",
        )
        return f"""
        <html>
          <head>
            <meta charset="utf-8"/>
            <style>{self.css()}</style>
          </head>
          <body>{body}</body>
        </html>
        """
