"""
NEXPLY - Build Script
Creates a standalone Windows EXE using PyInstaller.

Usage:
    python build.py              # Build release EXE
    python build.py --debug      # Build with console for debugging
    python build.py --clean      # Clean previous build first

Output:
    dist/Nexply/              -- Folder with EXE + all deps
    dist/Nexply/Nexply.exe  -- The main executable

After building:
    1. Copy dist/Nexply/ anywhere you want
    2. Run Nexply.exe
    3. First run creates config/, data/, resume/ next to the exe
"""
from __future__ import annotations

import sys
import os
import shutil
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "Nexply"
BUILD = ROOT / "build"


def clean():
    print("🧹 Cleaning previous build...")
    if DIST.exists():
        shutil.rmtree(DIST)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    for f in ROOT.glob("*.spec.bak"):
        f.unlink()
    print("   Done.")


def create_icon():
    """Create a simple ICO file if none exists."""
    icon_path = ROOT / "assets" / "icon.ico"
    if icon_path.exists():
        return

    (ROOT / "assets").mkdir(exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, size - 8, size - 8], fill="#6C63FF")
        # Robot face
        draw.ellipse([60, 55, 110, 100], fill="white")
        draw.ellipse([120, 55, 196, 100], fill="white")
        draw.ellipse([70, 65, 100, 90], fill="#0D0D1A")
        draw.ellipse([130, 65, 186, 90], fill="#0D0D1A")
        draw.arc([80, 110, 175, 150], 0, 180, fill="white", width=6)
        # Save as ICO
        img.save(str(icon_path), format="ICO", sizes=[(256, 256), (48, 48), (32, 32), (16, 16)])
        print(f"   Created icon: {icon_path}")
    except Exception as e:
        print(f"   Could not create icon (skipping): {e}")


def create_version_file():
    """Create a Windows version resource file."""
    version_dir = ROOT / "assets"
    version_dir.mkdir(exist_ok=True)

    version_rc = version_dir / "version.rc"
    content = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(3, 0, 0, 0),
    prodvers=(3, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Nexply'),
         StringStruct(u'FileDescription', u'Autonomous Job Applier'),
         StringStruct(u'FileVersion', u'3.0.0.0'),
         StringStruct(u'InternalName', u'Nexply'),
         StringStruct(u'OriginalFilename', u'Nexply.exe'),
         StringStruct(u'ProductName', u'Nexply - Job Applier'),
         StringStruct(u'ProductVersion', u'3.0.0.0')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    version_rc.write_text(content, encoding="utf-8")
    print(f"   Created version file: {version_rc}")


def post_process():
    """Copy user-facing files next to the EXE."""
    print("\n📦 Post-processing...")

    # Create empty user-data folders next to the EXE
    for folder in ["config", "data", "resume/generated", "output", "logs"]:
        (DIST / folder).mkdir(parents=True, exist_ok=True)

    # Copy default config
    src_cfg = ROOT / "config" / "settings.yaml"
    dst_cfg = DIST / "config" / "settings.yaml"
    if src_cfg.exists() and not dst_cfg.exists():
        shutil.copy2(src_cfg, dst_cfg)
        print(f"   Copied default config → {dst_cfg.relative_to(DIST)}")

    # Copy resume template if exists
    src_resume = ROOT / "resume" / "master_resume.docx"
    dst_resume = DIST / "resume" / "master_resume.docx"
    if src_resume.exists():
        shutil.copy2(src_resume, dst_resume)
        print(f"   Copied resume template → {dst_resume.relative_to(DIST)}")

    # Create a README next to the EXE
    readme = DIST / "README.txt"
    readme.write_text(
        "NEXPLY - Autonomous Job Applier v3.0\n"
        "=" * 42 + "\n\n"
        "FIRST RUN:\n"
        "  1. Put your master_resume.docx in the resume/ folder\n"
        "  2. Edit config/settings.yaml to set your AI provider\n"
        "  3. Run Nexply.exe\n\n"
        "AI PROVIDERS (free):\n"
        "  - Ollama: Install from https://ollama.com → ollama pull llama3.1\n"
        "  - Gemini: Set GEMINI_API_KEY environment variable\n\n"
        "FEATURES:\n"
        "  - Scans 9 job boards every 30 minutes automatically\n"
        "  - Includes visa-sponsoring jobs (H1B, UK, EU, Canada)\n"
        "  - AI-tailored resumes for each job\n"
        "  - System tray: runs in background\n\n"
        "DATA LOCATION:\n"
        "  config/settings.yaml  - All settings\n"
        "  data/jobs.db          - Job database\n"
        "  resume/               - Your resumes\n"
        "  output/               - Generated files\n"
        "  logs/                 - Application logs\n",
        encoding="utf-8",
    )
    print(f"   Created README.txt")


def build(debug: bool = False):
    print("🔨 Building NEXPLY EXE...\n")

    create_icon()
    create_version_file()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        str(ROOT / "nexply.spec"),
    ]

    if debug:
        # Patch spec to show console for debugging
        cmd.extend(["--log-level", "DEBUG"])
        print("⚠️  Debug mode: console window will be visible\n")

    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print("\n❌ Build failed! Check the output above for errors.")
        sys.exit(1)

    post_process()

    exe_path = DIST / "Nexply.exe"
    size_mb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"✅  BUILD SUCCESSFUL!")
    print(f"{'='*60}")
    print(f"   EXE: {exe_path}")
    print(f"   Folder: {DIST}")
    print(f"   Total size: {size_mb:.0f} MB")
    print(f"\n📋 NEXT STEPS:")
    print(f"   1. Put master_resume.docx in: {DIST / 'resume'}")
    print(f"   2. Edit: {DIST / 'config' / 'settings.yaml'}")
    print(f"   3. Run: {exe_path}")
    print(f"   4. Or distribute the entire '{DIST.name}' folder")


def main():
    parser = argparse.ArgumentParser(description="Build NEXPLY EXE")
    parser.add_argument("--clean", action="store_true", help="Clean previous build first")
    parser.add_argument("--debug", action="store_true", help="Build with console for debugging")
    args = parser.parse_args()

    if args.clean:
        clean()

    build(debug=args.debug)


if __name__ == "__main__":
    main()
