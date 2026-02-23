# ui/markdown_renderer.py
# -*- coding: utf-8 -*-

from __future__ import annotations

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
    - Optionally use pymdown-extensions if installed
    """

    def __init__(self, theme: Optional[MarkdownTheme] = None):
        self.theme = theme or MarkdownTheme()

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

        # Optional: GitHub-ish markdown improvements
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
            ]
            cfg.update(
                {
                    "pymdownx.tasklist": {
                        "custom_checkbox": True,
                        "clickable_checkbox": False,
                    },
                    "pymdownx.highlight": {
                        "use_pygments": False,
                    },
                }
            )
        except Exception:
            pass

        return exts, cfg

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
          background: #F9FAFB;
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
          background: #F9FAFB;
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

        /* pymdownx tasklist */
        .task-list-item {{
          list-style: none;
          margin-left: -1.1em;
        }}
        .task-list-item input[type="checkbox"] {{
          margin-right: 0.55em;
          transform: translateY(1px);
        }}

        /* admonition-ish */
        .admonition, details {{
          border: 1px solid var(--border);
          background: #F9FAFB;
          border-radius: 10px;
          padding: 10px 12px;
          margin: 0.8em 0;
        }}
        .admonition-title {{
          font-weight: 800;
          margin-bottom: 6px;
        }}
        """

    def to_html(self, md_text: str) -> str:
        exts, cfg = self.extensions()
        body = markdown(
            md_text or "",
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
