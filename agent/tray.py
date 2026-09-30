"""
RAJESH AI - System Tray Icon
Runs in background, scans every 30 minutes, shows notifications.

Features:
  - Minimize to tray (window close → tray, not exit)
  - Right-click tray menu: Open, Pause/Resume, Next Scan, Quit
  - Windows toast notifications on new jobs found
  - Live countdown to next scan
"""
from __future__ import annotations

import sys
import threading
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# ============================================================
# TRAY ICON
# ============================================================

class TrayManager:
    """
    Manages the system tray icon and 30-minute auto-scan loop.
    Uses pystray + Pillow for the icon.
    """

    def __init__(
        self,
        on_open: Callable,
        on_quit: Callable,
        scan_interval_minutes: int = 30,
    ):
        self._on_open     = on_open
        self._on_quit     = on_quit
        self._interval    = scan_interval_minutes * 60   # seconds
        self._paused      = False
        self._running     = True
        self._next_scan   = datetime.now() + timedelta(seconds=self._interval)
        self._icon        = None
        self._scan_thread: Optional[threading.Thread] = None

    # --------------------------------------------------------
    # BUILD ICON IMAGE
    # --------------------------------------------------------

    def _make_icon_image(self, active: bool = True):
        """Create a simple icon using Pillow."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return None

        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background circle
        bg_color = "#6C63FF" if active else "#5A5A8A"
        draw.ellipse([2, 2, size - 2, size - 2], fill=bg_color)

        # Robot face
        draw.ellipse([16, 14, 48, 42], fill="white", outline="#0D0D1A", width=2)
        # Eyes
        draw.ellipse([22, 20, 30, 28], fill="#0D0D1A")
        draw.ellipse([34, 20, 42, 28], fill="#0D0D1A")
        # Mouth
        draw.arc([22, 30, 42, 40], 0, 180, fill="#0D0D1A", width=2)
        # Antenna
        draw.line([32, 14, 32, 6], fill="white", width=2)
        draw.ellipse([29, 3, 35, 9], fill="#48CFAD")

        return img

    # --------------------------------------------------------
    # TRAY SETUP
    # --------------------------------------------------------

    def start(self):
        """Start tray icon in a background thread."""
        threading.Thread(target=self._run_tray, daemon=True).start()
        threading.Thread(target=self._scan_loop,  daemon=True).start()

    def _run_tray(self):
        try:
            import pystray
        except ImportError:
            logger.warning("pystray not installed — tray icon disabled")
            return

        icon_image = self._make_icon_image(True)
        if not icon_image:
            logger.warning("Pillow not installed — tray icon disabled")
            return

        menu = pystray.Menu(
            pystray.MenuItem("🤖  RAJESH AI", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📂  Open Dashboard", self._menu_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "⏸  Pause Scanning",
                self._menu_toggle_pause,
                checked=lambda item: self._paused,
            ),
            pystray.MenuItem(
                lambda item: f"⏰  Next scan: {self._next_scan_label()}",
                None,
                enabled=False,
            ),
            pystray.MenuItem("🔍  Scan Now", self._menu_scan_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌  Quit", self._menu_quit),
        )

        self._icon = pystray.Icon(
            name="RajeshAI",
            icon=icon_image,
            title="RAJESH AI — Autonomous Job Applier",
            menu=menu,
        )

        logger.info("System tray icon started")
        self._icon.run()

    # --------------------------------------------------------
    # MENU ACTIONS
    # --------------------------------------------------------

    def _menu_open(self, icon, item):
        self._on_open()

    def _menu_toggle_pause(self, icon, item):
        self._paused = not self._paused
        status = "paused" if self._paused else "resumed"
        logger.info(f"Auto-scan {status}")
        self._notify(
            "RAJESH AI",
            f"Auto-scan {'paused' if self._paused else 'resumed'}."
        )

    def _menu_scan_now(self, icon, item):
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _menu_quit(self, icon, item):
        self._running = False
        if self._icon:
            self._icon.stop()
        self._on_quit()

    # --------------------------------------------------------
    # AUTO-SCAN LOOP (every 30 minutes)
    # --------------------------------------------------------

    def _scan_loop(self):
        """Background loop that triggers a scan every N minutes."""
        # Wait for the first interval before scanning
        while self._running:
            now = datetime.now()
            if not self._paused and now >= self._next_scan:
                self._do_scan()
                self._next_scan = datetime.now() + timedelta(seconds=self._interval)
            time.sleep(30)  # Check every 30 seconds

    def _do_scan(self):
        """Run the hunt stage of the pipeline."""
        logger.info("Auto-scan triggered")
        try:
            import yaml
            from agent.paths import CONFIG_PATH
            with open(CONFIG_PATH) as f:
                settings = yaml.safe_load(f)

            from agent.job_hunter import JobHunter
            hunter = JobHunter(settings)
            count = hunter.run()

            if count > 0:
                self._notify(
                    "RAJESH AI — New Jobs Found!",
                    f"Found {count} new job(s). Open the dashboard to review."
                )
                logger.info(f"Auto-scan found {count} new jobs")
            else:
                logger.info("Auto-scan: no new jobs")

        except Exception as e:
            logger.error(f"Auto-scan failed: {e}")

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    def _next_scan_label(self) -> str:
        delta = self._next_scan - datetime.now()
        total_sec = max(0, int(delta.total_seconds()))
        m, s = divmod(total_sec, 60)
        return f"{m}m {s}s"

    def _notify(self, title: str, message: str):
        """Show a Windows toast notification if possible."""
        try:
            # Try Windows 10 toast notifications
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5, threaded=True)
            return
        except ImportError:
            pass
        try:
            # Fallback: pystray balloon
            if self._icon:
                self._icon.notify(message, title)
        except Exception:
            pass
        logger.info(f"Notification: {title} — {message}")

    def set_interval(self, minutes: int):
        """Update scan interval (called from settings)."""
        self._interval = minutes * 60
        self._next_scan = datetime.now() + timedelta(seconds=self._interval)


# ============================================================
# GLOBAL TRAY INSTANCE
# ============================================================

_tray: Optional[TrayManager] = None


def start_tray(on_open: Callable, on_quit: Callable, interval_minutes: int = 30):
    """Initialize and start the system tray."""
    global _tray
    _tray = TrayManager(on_open, on_quit, interval_minutes)
    _tray.start()
    return _tray


def get_tray() -> Optional[TrayManager]:
    return _tray
