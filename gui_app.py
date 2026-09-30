"""
RAJESH AI - Main GUI Application
Beautiful dark-themed desktop app for the Autonomous Job Applier.

Run:
    python gui_app.py
    python -X utf8 gui_app.py
"""
from __future__ import annotations

import sys
import os
import threading
from pathlib import Path
from datetime import datetime

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import customtkinter as ctk
from tkinter import messagebox

# ---- Configure CustomTkinter before any window is created ----
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BASE_DIR = Path(__file__).resolve().parent

# GUI views (imported lazily to keep startup fast)
from gui.theme import *


# ============================================================
# SIDEBAR NAVIGATION BUTTON
# ============================================================

class NavButton(ctk.CTkButton):
    """Sidebar navigation item with active/inactive states."""

    def __init__(self, master, text: str, icon: str, command, **kwargs):
        self._icon = icon
        self._text_label = text
        super().__init__(
            master,
            text=f"  {icon}  {text}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color="transparent",
            hover_color=BG_CARD_HOVER,
            text_color=TEXT_SECONDARY,
            border_width=0,
            height=44,
            corner_radius=8,
            anchor="w",
            command=command,
            **kwargs,
        )

    def set_active(self, active: bool):
        if active:
            self.configure(
                fg_color=BG_CARD_HOVER,
                text_color=TEXT_PRIMARY,
                border_width=0,
            )
            # Left accent bar: use a thin colored frame overlaid
        else:
            self.configure(
                fg_color="transparent",
                text_color=TEXT_SECONDARY,
            )


# ============================================================
# STATUS BAR
# ============================================================

class StatusBar(ctk.CTkFrame):
    """Bottom status bar showing AI provider, DB stats, and clock."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=BG_SECONDARY, height=32, corner_radius=0, **kwargs)
        self.pack_propagate(False)
        self._build()
        self._tick()

    def _build(self):
        # Left: AI status
        self._ai_lbl = ctk.CTkLabel(
            self,
            text="AI: checking...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=TEXT_DIM,
        )
        self._ai_lbl.pack(side="left", padx=16)

        ctk.CTkFrame(self, width=1, height=16, fg_color=BORDER_SUBTLE).pack(side="left")

        # Middle: job count
        self._jobs_lbl = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=TEXT_DIM,
        )
        self._jobs_lbl.pack(side="left", padx=16)

        # Right: clock
        self._clock_lbl = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=TEXT_DIM,
        )
        self._clock_lbl.pack(side="right", padx=16)

        ctk.CTkLabel(
            self,
            text="RAJESH AI v3.0",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=TEXT_DIM,
        ).pack(side="right", padx=8)

    def _tick(self):
        now = datetime.now().strftime("%d %b %Y  %H:%M:%S")
        self._clock_lbl.configure(text=now)
        self.after(1000, self._tick)

    def update_ai(self, provider: str, ok: bool):
        icon = "●" if ok else "○"
        color = SCORE_STRONG if ok else ACCENT_PINK
        self._ai_lbl.configure(
            text=f"{icon}  AI: {provider}",
            text_color=color,
        )

    def update_jobs(self, total: int, applied: int):
        self._jobs_lbl.configure(
            text=f"Jobs: {total}  |  Applied: {applied}",
        )


# ============================================================
# MAIN APPLICATION WINDOW
# ============================================================

class RajeshAIApp(ctk.CTk):
    """Main application window with sidebar navigation."""

    NAV_ITEMS = [
        ("Dashboard",  "🏠", "dashboard"),
        ("Jobs",        "📋", "jobs"),
        ("Pipeline",    "⚡", "pipeline"),
        ("Apply Queue", "📤", "apply"),
        ("Settings",    "⚙️",  "settings"),
    ]

    def __init__(self):
        super().__init__()

        self.title("RAJESH AI — Autonomous Job Applier")
        self.geometry("1400x900")
        self.minsize(1100, 700)
        self.configure(fg_color=BG_PRIMARY)

        # Set window icon
        try:
            self.iconbitmap(str(BASE_DIR / "assets" / "icon.ico"))
        except Exception:
            pass

        self._active_nav: str = "dashboard"
        self._views: dict = {}
        self._nav_buttons: dict = {}

        self._build_layout()
        self._show_view("dashboard")

        # Load settings
        try:
            import yaml
            with open(BASE_DIR / "config" / "settings.yaml") as f:
                self._settings = yaml.safe_load(f) or {}
        except Exception:
            self._settings = {}

        gui_cfg = self._settings.get("gui", {})
        scan_interval = self._settings.get("scheduler", {}).get("scan_interval_minutes", 30)
        minimize_to_tray = gui_cfg.get("minimize_to_tray", True)

        # Start system tray with 30-minute auto-scan
        try:
            from agent.tray import start_tray
            self._tray = start_tray(
                on_open=self._show_window,
                on_quit=self._quit_app,
                interval_minutes=scan_interval,
            )
        except Exception as e:
            self._tray = None
            print(f"Tray not available: {e}")

        # Override close → minimize to tray (if enabled)
        if minimize_to_tray:
            self.protocol("WM_DELETE_WINDOW", self._on_close)
        else:
            self.protocol("WM_DELETE_WINDOW", self._quit_app)

        # Background: load AI status + job count
        threading.Thread(target=self._load_status_bar, daemon=True).start()

        # Auto-refresh dashboard every N seconds
        self._schedule_refresh()


    # --------------------------------------------------------
    # LAYOUT
    # --------------------------------------------------------

    def _build_layout(self):
        # ---- SIDEBAR ----
        self._sidebar = ctk.CTkFrame(
            self,
            width=SIDEBAR_WIDTH,
            fg_color=BG_SECONDARY,
            corner_radius=0,
        )
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        self._build_sidebar()

        # ---- CONTENT AREA ----
        self._content = ctk.CTkFrame(self, fg_color=BG_PRIMARY, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        # ---- STATUS BAR ----
        self._status_bar = StatusBar(self)
        self._status_bar.pack(side="bottom", fill="x")

    def _build_sidebar(self):
        # Logo / brand area
        brand = ctk.CTkFrame(self._sidebar, fg_color="transparent", height=80)
        brand.pack(fill="x", pady=(8, 4))
        brand.pack_propagate(False)

        ctk.CTkLabel(
            brand,
            text="🤖",
            font=ctk.CTkFont(size=32),
        ).pack(pady=(12, 0))

        ctk.CTkLabel(
            brand,
            text="RAJESH AI",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=ACCENT_PRIMARY,
        ).pack()

        # Divider
        ctk.CTkFrame(self._sidebar, height=1, fg_color=BORDER_SUBTLE).pack(fill="x", padx=12, pady=8)

        # Nav items
        nav_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=10, pady=4)

        for label, icon, key in self.NAV_ITEMS:
            btn = NavButton(
                nav_frame,
                text=label,
                icon=icon,
                command=lambda k=key: self._show_view(k),
            )
            btn.pack(fill="x", pady=2)
            self._nav_buttons[key] = btn

        # Divider
        ctk.CTkFrame(self._sidebar, height=1, fg_color=BORDER_SUBTLE).pack(fill="x", padx=12, pady=8)

        # Quick actions
        ctk.CTkLabel(
            self._sidebar,
            text="QUICK RUN",
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            text_color=TEXT_DIM,
        ).pack(padx=16, anchor="w")

        quick_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        quick_frame.pack(fill="x", padx=10, pady=4)

        for label, cmd in [("🔍  Hunt Now", "hunt"), ("🚀  Full Pipeline", "run")]:
            ctk.CTkButton(
                quick_frame,
                text=label,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                fg_color=BG_CARD,
                hover_color=ACCENT_PRIMARY,
                text_color=TEXT_PRIMARY,
                border_width=1,
                border_color=BORDER_SUBTLE,
                height=34,
                command=lambda c=cmd: self._quick_run(c),
            ).pack(fill="x", pady=2)

        # Bottom: version + links
        bottom = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=12)

        ctk.CTkButton(
            bottom,
            text="📅  Schedule Daily",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            fg_color="transparent",
            hover_color=BG_CARD,
            text_color=TEXT_DIM,
            height=28,
            command=self._schedule_daily,
        ).pack(fill="x", pady=1)

        ctk.CTkButton(
            bottom,
            text="📊  Export CSV",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            fg_color="transparent",
            hover_color=BG_CARD,
            text_color=TEXT_DIM,
            height=28,
            command=self._export_csv,
        ).pack(fill="x", pady=1)

        ctk.CTkLabel(
            bottom,
            text="v3.0  •  Worldwide 🌍",
            font=ctk.CTkFont(family=FONT_FAMILY, size=9),
            text_color=TEXT_DIM,
        ).pack(pady=(8, 0))

    # --------------------------------------------------------
    # VIEW SWITCHING
    # --------------------------------------------------------

    def _show_view(self, key: str):
        # Update nav button states
        for k, btn in self._nav_buttons.items():
            btn.set_active(k == key)

        # Clear content
        for w in self._content.winfo_children():
            w.pack_forget()

        # Create view if not cached
        if key not in self._views:
            self._views[key] = self._create_view(key)

        view = self._views[key]
        view.pack(fill="both", expand=True)
        self._active_nav = key

        # Trigger refresh when switching to dashboard
        if key == "dashboard" and hasattr(view, "refresh"):
            threading.Thread(target=view.refresh, daemon=True).start()

    def _create_view(self, key: str) -> ctk.CTkFrame:
        from gui.dashboard_view import DashboardView
        from gui.jobs_view import JobsView
        from gui.pipeline_view import PipelineView
        from gui.apply_view import ApplyView
        from gui.settings_view import SettingsView

        mapping = {
            "dashboard": DashboardView,
            "jobs":      JobsView,
            "pipeline":  PipelineView,
            "apply":     ApplyView,
            "settings":  SettingsView,
        }
        cls = mapping[key]
        return cls(self._content)

    # --------------------------------------------------------
    # QUICK ACTIONS
    # --------------------------------------------------------

    def _quick_run(self, command: str):
        """Switch to pipeline tab and trigger a command."""
        self._show_view("pipeline")
        pipeline_view = self._views.get("pipeline")
        if pipeline_view and hasattr(pipeline_view, "_run_stage"):
            self.after(200, lambda: pipeline_view._run_stage(command))

    def _schedule_daily(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "agent" / "scheduler.py"), "--install"],
            capture_output=True, text=True, cwd=str(BASE_DIR),
        )
        if result.returncode == 0:
            messagebox.showinfo("Scheduler", "✅ Windows daily tasks installed!\n\nPipeline will run at 8:00 AM daily.")
        else:
            messagebox.showerror("Error", result.stdout + result.stderr)

    def _export_csv(self):
        from agent.tracker import PipelineTracker
        path = BASE_DIR / "output" / "pipeline_export.csv"
        PipelineTracker().export_to_csv(path)
        messagebox.showinfo("Export", f"✅ Exported to:\n{path}")

    # --------------------------------------------------------
    # TRAY / WINDOW MANAGEMENT
    # --------------------------------------------------------

    def _on_close(self):
        """Minimize to system tray instead of exiting."""
        self.withdraw()  # Hide window
        # Show balloon tip on first minimize
        if self._tray and not getattr(self, "_tray_notified", False):
            self._tray_notified = True
            try:
                if self._tray._icon:
                    self._tray._icon.notify(
                        "RAJESH AI is still running in the background.\n"
                        "Scanning for jobs every 30 minutes.\n"
                        "Right-click the tray icon to open or quit.",
                        "RAJESH AI minimized to tray",
                    )
            except Exception:
                pass

    def _show_window(self):
        """Restore the main window from tray."""
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _quit_app(self):
        """Fully exit the application."""
        try:
            if self._tray and self._tray._icon:
                self._tray._icon.stop()
        except Exception:
            pass
        self.destroy()

    # --------------------------------------------------------
    # STATUS BAR BACKGROUND UPDATE
    # --------------------------------------------------------

    def _load_status_bar(self):
        try:
            from agent.ai_engine import get_ai_engine
            engine = get_ai_engine()
            active = engine.active_provider_name()
            ok = active != "none"
            self.after(0, lambda: self._status_bar.update_ai(active, ok))
        except Exception:
            self.after(0, lambda: self._status_bar.update_ai("none", False))

        try:
            from agent.database import get_job_count, get_pipeline_stats
            total = get_job_count()
            stats = get_pipeline_stats()
            applied = stats.get("APPLIED", 0)
            self.after(0, lambda: self._status_bar.update_jobs(total, applied))
        except Exception:
            pass

    def _schedule_refresh(self):
        """Auto-refresh status bar every 30 seconds."""
        try:
            import yaml
            cfg_path = BASE_DIR / "config" / "settings.yaml"
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f)
            interval_ms = cfg.get("gui", {}).get("auto_refresh_seconds", 30) * 1000
        except Exception:
            interval_ms = 30_000

        threading.Thread(target=self._load_status_bar, daemon=True).start()
        self.after(interval_ms, self._schedule_refresh)


# ============================================================
# SPLASH SCREEN
# ============================================================

class SplashScreen(ctk.CTkToplevel):
    """Quick splash while the app initializes."""

    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.configure(fg_color=BG_PRIMARY)
        w, h = 420, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.lift()
        self.attributes("-topmost", True)

        ctk.CTkLabel(self, text="🤖", font=ctk.CTkFont(size=60)).pack(pady=(40, 8))
        ctk.CTkLabel(
            self,
            text="RAJESH AI",
            font=ctk.CTkFont(family=FONT_FAMILY, size=28, weight="bold"),
            text_color=ACCENT_PRIMARY,
        ).pack()
        ctk.CTkLabel(
            self,
            text="Autonomous Job Applier v3.0",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=TEXT_SECONDARY,
        ).pack(pady=4)

        self._bar = ctk.CTkProgressBar(
            self,
            fg_color=BG_CARD,
            progress_color=ACCENT_PRIMARY,
            width=300,
        )
        self._bar.set(0)
        self._bar.pack(pady=24)

        self._status = ctk.CTkLabel(
            self,
            text="Initializing...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=TEXT_DIM,
        )
        self._status.pack()

        self._animate()

    def _animate(self, step=0):
        messages = [
            "Loading database...",
            "Checking AI providers...",
            "Loading job sources...",
            "Preparing dashboard...",
            "Ready!",
        ]
        if step < len(messages):
            self._bar.set((step + 1) / len(messages))
            self._status.configure(text=messages[step])
            self.after(300, lambda: self._animate(step + 1))
        else:
            self.after(200, self.destroy)


# ============================================================
# ENTRY POINT
# ============================================================

def run_gui():
    """Launch the Rajesh AI GUI application."""
    # Initialize DB first
    try:
        from agent.database import initialize_database, migrate_v1_to_v2
        initialize_database()
        migrate_v1_to_v2()
    except Exception as e:
        print(f"DB init warning: {e}")

    app = RajeshAIApp()

    # Show splash
    splash = SplashScreen()
    app.after(1800, splash.destroy)

    app.mainloop()


if __name__ == "__main__":
    run_gui()
