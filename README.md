# GNOME Pomodoro Timer

A lightweight, **always-on-top** Pomodoro timer app for Ubuntu GNOME, built with Python & Tkinter.  
Designed for developers, students, and professionals who want a distraction-free time management tool right on their desktop.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

---

## Features

- **Always-on-Top Watchdog**: Stays visible using smart re-assert & event hooks (even on GNOME Wayland)
- **Task Input Field**: Write your current task with seamless, borderless design
- **Draggable Window**: Move the timer anywhere on your screen
- **Work & Break Cycles**: 25-min focus sessions, 5-min breaks (Pomodoro Technique)
- **Dynamic Colors**: Blue for Deep Work, Green for Rest Time
- **Custom Icons**: Supports `play.png`, `pause.png`, `refresh.png` (with emoji fallback)
- **Minimal & Clean UI**: Distraction-free design with Montserrat font

---

## Quick Start

### Requirements
- Python 3.8+
- Tkinter (pre-installed on most Linux systems)

### Installation & Run
```bash
# Clone the repository
git clone https://github.com/ilhamz922/gnomepomodoro.git
cd gnomepomodoro

# Run the app
python3 pomodoro.py
```

### Optional: Add Custom Icons
Place these PNG files in the same directory as `pomodoro.py`:
- `play.png` - Start button icon
- `pause.png` - Pause button icon  
- `refresh.png` - Reset button icon

If icons aren't found, the app will use text fallbacks.

---

## Usage

1. **Write Your Task**: Click the task field at the top and type what you're working on
2. **Start Timer**: Click the play button to begin your 25-minute Deep Work session
3. **Take Breaks**: Timer auto-switches to 5-minute Rest Time after each work session
4. **Reset Anytime**: Click the refresh button to reset to Deep Work phase
5. **Drag Anywhere**: Click and drag anywhere on the window to reposition
6. **Force Raise**: Press `Ctrl+Shift+Up` to bring window to front if it gets buried

---

## Technical Details

### Always-on-Top Strategy
The app uses multiple techniques to ensure it stays visible:
- **Initial topmost flag** set on startup
- **Periodic watchdog** (every 2 seconds) to re-assert topmost status
- **Event hooks** on focus/visibility changes to nudge window manager
- **Manual hotkey** (`Ctrl+Shift+Up`) for forcing window to front

### UI Components
- **Task Entry**: Borderless text field with placeholder ("type your task here")
- **Timer Display**: Large countdown in MM:SS format
- **Status Label**: Shows current phase and timer state
- **Control Buttons**: Play/Pause and Reset with icon support
- **Phase Indicator**: "Deep Work" or "Rest Time" label

---

## Roadmap & Vision

We aim to grow this into a full productivity toolkit for Ubuntu (and beyond), integrating multiple time & task management methodologies.

### Short-term Goals (v1.x)
- Configurable work/break durations
- Sound notifications & desktop alerts
- Session statistics (completed pomodoros, total focus time)
- Settings menu (custom durations, colors, sounds)
- Task history log

### Mid-term Goals (v2.x)
- Eisenhower Matrix for task prioritization
- Time-blocking calendar view
- Integration with project management tools (Trello, Jira, Notion)
- Theme customization (dark mode, custom colors)
- Export session logs as CSV/JSON

### Long-term Goals (v3.x+)
- Cross-platform support (Windows & macOS)
- Mobile companion apps (Android & iOS)
- Cloud sync for tasks and sessions
- Collaboration mode (shared focus sessions)
- Browser extension for web-based task tracking

---

## Contributing

We're looking for collaborators! Whether you're a:
- **Python Developer** (Tkinter, PyQt, GTK)
- **UI/UX Designer** (clean & intuitive interfaces)
- **Integration Expert** (APIs for productivity tools)
- **Mobile Developer** (Android/iOS)
- **Tester** (Windows, macOS, other Linux distros)

### How to Contribute
1. Fork this repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

For major changes, please open an issue first to discuss what you'd like to change.

---

## Contact

**Muhammad Ilham**  
Email: contact.muhammad.ilham@gmail.com  
GitHub: [@ilhamz922](https://github.com/ilhamz922)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Inspired by the [Pomodoro Technique](https://francescocirillo.com/pages/pomodoro-technique) by Francesco Cirillo
- Built for the GNOME desktop environment
- Font: Montserrat (system default fallback if unavailable)

---

**Let's build the ultimate open-source productivity suite for Ubuntu together!**

---

## Preview

*Coming soon - add screenshots of your timer in action!*