# Pomodoro Kanban --- Productivity Suite

A local-first **Kanban + Pomodoro desktop app** built with **Python &
Tkinter**.

Originally started as a GNOME-focused Pomodoro timer, this project has
evolved into a lightweight productivity suite combining:

-   🗂 Kanban task management
-   📝 Markdown-powered task notes
-   ⏳ Built-in Pomodoro timer (25--5)
-   📊 Work session tracking
-   🎯 Priority & dependency system

------------------------------------------------------------------------

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)

------------------------------------------------------------------------

# Core Features

## 🗂 Kanban Board

-   3 Columns: **TODO / DOING / DONE**
-   Drag & drop between columns
-   Move with buttons (← / →)
-   Keyboard shortcuts:
    -   `Ctrl + Left`
    -   `Ctrl + Right`
-   Auto-sorted by prioritization score
-   Task deletion with confirmation

------------------------------------------------------------------------

## 📝 Task Panel

### Properties (Accordion)

-   Name (auto-save)
-   Due date (manual input or 📅 picker)
-   Priority (P0 / P1 / P2)
-   Dependencies:
    -   Blockers
    -   Waiting-on

### Description (Markdown)

-   Edit / Save toggle
-   Auto-save (debounced)
-   Markdown rendering via `markdown` + optional `pymdown-extensions`
-   Slash command expansion

------------------------------------------------------------------------

## ⏳ Pomodoro Timer

Built-in Pomodoro session system.

### Default Cycle

-   **25 min Deep Work**
-   **5 min Rest Time**

### Features

-   Always-on-top window
-   Smart re-assert (Wayland-safe approach)
-   Fullscreen during break (optional) for stronger visibility
-   Draggable timer window
-   Dynamic colors:
    -   Blue → Deep Work
    -   Green → Rest Time
-   Session tracking per task
-   Today total focus time display
-   Selected task total focus time display

### Controls

-   `Ctrl + Enter` → Start Pomodoro
-   Play / Pause / Reset buttons
-   Auto phase switching

------------------------------------------------------------------------

# Slash Commands (Markdown Editor)

Type command and press **Space** or **Enter**.

## Date / Time

  Command        Output Example
  -------------- --------------------------
  `/now`         Tue, 24 Feb 2026 • 01:22
  `/today`       Tue, 24 Feb 2026
  `/yesterday`   Mon, 23 Feb 2026
  `/tomorrow`    Wed, 25 Feb 2026

## Log Helpers

  Command     Output
  ----------- ------------------------------------------
  `/log`      `### Tue, 24 Feb 2026 • 01:22`
  `/start`    `Started: Tue, 24 Feb 2026 • 01:22`
  `/done`     `Completed: Tue, 24 Feb 2026 • 01:22`
  `/review`   `Review: Tue, 24 Feb 2026 • 01:22`
  `/update`   `Last updated: Tue, 24 Feb 2026 • 01:22`

## Metadata Injectors

  Command            Output
  ------------------ ------------------
  `/priority high`   `priority: high`
  `/status done`     `status: done`
  `/tag frontend`    `#frontend`

------------------------------------------------------------------------

### 🔁 Repetitive Tasks (NEW)

Tasks can repeat:

| Rule     | Behavior |
|----------|----------|
| `none`   | Normal task |
| `daily`  | Creates new task next day when completed |
| `weekly` | Creates new task +7 days |
| `monthly`| Creates new task next month (safe date clamp) |

When a repeating task is moved to **DONE**:
- It is marked completed
- A new instance is automatically created in **TODO**
- Due date is shifted according to rule

Kanban column shows badges:
- 🔁D = Daily  
- 🔁W = Weekly  
- 🔁M = Monthly  

------------------------------------------------------------------------

# Installation

## Requirements

-   Python 3.10+
-   Tkinter (pre-installed on most Linux systems)

## Install Dependencies

``` bash
pip install tkinterweb markdown
pip install pymdown-extensions  # optional but recommended
```

------------------------------------------------------------------------

# Run

``` bash
python main.py
```

------------------------------------------------------------------------

# Architecture Overview

    ui/
      markdown_renderer.py
      slash_commands.py

    services/
      task_service.py
      stats_service.py

    storage/
      repos.py
      database layer

    pomodoro.py
    main.py (TodoWindow)

------------------------------------------------------------------------

# Roadmap

## 🐞 Bugs

-   [x] Fix markdown error
-   [ ] Fix dependency connection issue (blockers & waiting-on)
-   [x] Update move right / left logic

## 🚀 Development

-   [ ] Add progress bar
-   [x] Add /now slash command
-   [ ] Add timeline view
-   [ ] Improve time tracker
-   [ ] Add analytics dashboard
-   [ ] Add project view & management
-   [ ] Simple account management
-   [ ] Repetitive tasks
-   [ ] Duplicate tasks
-   [ ] Task templates
-   [ ] Cloud integration

------------------------------------------------------------------------

# Vision

### Short-term

A powerful offline-first productivity tool.

### Mid-term

Move UI toward web-based frontend (React / Next.js).

### Long-term

Cloud sync, multi-device access, analytics layer, and collaboration
mode.

------------------------------------------------------------------------

# License

MIT License

------------------------------------------------------------------------

# Author

Muhammad Ilham\
GitHub: https://github.com/ilhamz922
# 🧠 Pomodoro Kanban
