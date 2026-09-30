# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for NEXPLY - Autonomous Job Applier
Builds a self-contained Windows executable.

Usage:
    pyinstaller nexply.spec
Or use the helper:
    python build.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH)

# ============================================================
# HIDDEN IMPORTS (libraries PyInstaller may miss)
# ============================================================
hidden_imports = [
    # CustomTkinter
    "customtkinter",
    "customtkinter.windows",
    "customtkinter.windows.widgets",
    "customtkinter.windows.widgets.appearance_mode",
    "customtkinter.windows.widgets.theme",
    "customtkinter.windows.widgets.font",
    "customtkinter.windows.widgets.image",
    "customtkinter.windows.widgets.scaling",
    "customtkinter.windows.widgets.utility",

    # Matplotlib
    "matplotlib",
    "matplotlib.backends.backend_tkagg",
    "matplotlib.figure",
    "matplotlib.patches",
    "matplotlib.pyplot",

    # Data / ML
    "yaml",
    "pydantic",
    "httpx",
    "httpx._transports",
    "tenacity",
    "bs4",
    "feedparser",
    "docx",
    "docx.oxml",
    "jinja2",
    "schedule",

    # System tray
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL._tkinter_finder",

    # Google AI
    "google.genai",

    # Std library extras
    "email.utils",
    "email.mime.text",
    "email.mime.multipart",
    "email.mime.application",
    "smtplib",
    "sqlite3",
    "xml.etree.ElementTree",
    "html.parser",
    "urllib.parse",
    "hashlib",
    "threading",
    "queue",
    "subprocess",
    "webbrowser",
    "logging",
    "csv",
    "json",
    "re",
    "pathlib",
    "datetime",
    "dataclasses",
    "typing",
    "enum",
    "copy",
    "traceback",
    "textwrap",

    # Tkinter
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",

    # Click (CLI still available alongside GUI)
    "click",

    # Agent modules
    "agent",
    "agent.ai_engine",
    "agent.database",
    "agent.paths",
    "agent.tray",
    "agent.job_hunter",
    "agent.tracker",
    "agent.dashboard",
    "agent.orchestrator",
    "agent.scheduler",
    "agent.applier",
    "agent.approval_gate",
    "agent.ats_checker",
    "agent.resume_formatter",
    "agent.sources",
    "agent.sources.base_source",
    "agent.sources.himalayas_source",
    "agent.sources.remoteok_source",
    "agent.sources.jobicy_source",
    "agent.sources.remotive_source",
    "agent.sources.weworkremotely_source",
    "agent.sources.aijobs_source",
    "agent.sources.remotefirstjobs_source",
    "agent.sources.visa_jobs_source",
    "agent.sources.linkedin_source",
    "agent.sources.naukri_source",
    "agent.sources.wellfound_source",

    # GUI modules
    "gui",
    "gui.theme",
    "gui.dashboard_view",
    "gui.jobs_view",
    "gui.pipeline_view",
    "gui.apply_view",
    "gui.settings_view",
]

# ============================================================
# DATA FILES (bundled assets, read-only at runtime)
# These go into the PyInstaller temp dir (_MEIPASS)
# ============================================================

import customtkinter as ctk_pkg
import matplotlib as mpl_pkg

ctk_path = Path(ctk_pkg.__file__).parent
mpl_path = Path(mpl_pkg.get_data_path())

datas = [
    # CustomTkinter themes and assets
    (str(ctk_path), "customtkinter"),

    # Matplotlib data (fonts, colormaps, etc.)
    (str(mpl_path), "matplotlib/mpl-data"),

    # Default config (copied to app dir on first run)
    (str(ROOT / "config"), "config"),

    # Resume template
    (str(ROOT / "resume"), "resume"),
]

# ============================================================
# ANALYSIS
# ============================================================
a = Analysis(
    [str(ROOT / "gui_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "IPython",
        "notebook",
        "jupyter",
        "scipy",
        "sklearn",
        "numpy",           # Not used directly
        "pandas",
        "torch",
        "tensorflow",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# ============================================================
# EXE — one-directory mode (faster startup, easier to update)
# ============================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nexply",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
    version_file=str(ROOT / "assets" / "version.rc") if (ROOT / "assets" / "version.rc").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Nexply",
)
