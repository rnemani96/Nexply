"""
RAJESH AI - Path Resolver
Handles paths correctly whether running as source or PyInstaller .exe
"""
from __future__ import annotations
import sys
from pathlib import Path


def get_app_dir() -> Path:
    """
    User-data directory: config, database, resumes.
    - Running as .exe  → folder containing the .exe
    - Running as source → project root
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_bundle_dir() -> Path:
    """
    Bundled assets directory (read-only in PyInstaller builds).
    - Running as .exe  → sys._MEIPASS (temp extract dir)
    - Running as source → project root
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


# Singleton references used across all modules
APP_DIR    = get_app_dir()
BUNDLE_DIR = get_bundle_dir()

CONFIG_PATH  = APP_DIR / "config" / "settings.yaml"
DB_PATH      = APP_DIR / "data" / "jobs.db"
RESUME_PATH  = APP_DIR / "resume" / "master_resume.docx"
OUTPUT_DIR   = APP_DIR / "output"
LOG_DIR      = APP_DIR / "logs"


def ensure_dirs():
    """Create required directories if they don't exist (first-run setup)."""
    for d in [APP_DIR / "config", APP_DIR / "data", APP_DIR / "resume",
              APP_DIR / "output", APP_DIR / "logs",
              APP_DIR / "resume" / "generated"]:
        d.mkdir(parents=True, exist_ok=True)

    # Copy bundled default config if missing
    if not CONFIG_PATH.exists():
        bundled_cfg = BUNDLE_DIR / "config" / "settings.yaml"
        if bundled_cfg.exists():
            import shutil
            shutil.copy2(bundled_cfg, CONFIG_PATH)
