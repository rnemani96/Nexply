@echo off
setlocal EnableDelayedExpansion
title Nexply — Starting...

:: ============================================================
::  NEXPLY — Portable Launcher
::  Drop this file anywhere. It finds and runs the app.
:: ============================================================

:: ── Where is this batch file? ──────────────────────────────
set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"

:: ── Look for the EXE (pre-built, no install needed) ────────
set "EXE="

:: 1. Same folder as this bat
if exist "%HERE%\Nexply.exe"              set "EXE=%HERE%\Nexply.exe"
if exist "%HERE%\RajeshAI.exe"            set "EXE=%HERE%\RajeshAI.exe"

:: 2. dist\Nexply or dist\RajeshAI sub-folder
if exist "%HERE%\dist\Nexply\Nexply.exe"        set "EXE=%HERE%\dist\Nexply\Nexply.exe"
if exist "%HERE%\dist\RajeshAI\RajeshAI.exe"    set "EXE=%HERE%\dist\RajeshAI\RajeshAI.exe"

:: 3. Parent folder (if launcher dropped inside dist)
if exist "%HERE%\..\Nexply.exe"           set "EXE=%HERE%\..\Nexply.exe"
if exist "%HERE%\..\RajeshAI.exe"         set "EXE=%HERE%\..\RajeshAI.exe"

:: ── If EXE found — launch it ───────────────────────────────
if defined EXE (
    for %%F in ("!EXE!") do set "WORK_DIR=%%~dpF"
    echo Starting Nexply (pre-built)...
    start "" /D "!WORK_DIR!" "!EXE!"
    exit /b 0
)

:: ── No EXE — try Python source mode ────────────────────────
echo Pre-built EXE not found. Trying Python source mode...

:: Find Python
set "PY="
for %%P in (python python3 py) do (
    if not defined PY (
        %%P --version >nul 2>&1 && set "PY=%%P"
    )
)

if not defined PY (
    echo.
    echo  ╔══════════════════════════════════════════════════╗
    echo  ║            Nexply — Cannot Start                 ║
    echo  ╠══════════════════════════════════════════════════╣
    echo  ║  Neither the pre-built EXE nor Python was found. ║
    echo  ║                                                  ║
    echo  ║  Options:                                        ║
    echo  ║  1. Use the EXE: dist\RajeshAI\RajeshAI.exe     ║
    echo  ║  2. Install Python 3.11+ from python.org         ║
    echo  ║     then run:  pip install -r requirements.txt   ║
    echo  ╚══════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

:: Check gui_app.py exists here
if not exist "%HERE%\gui_app.py" (
    echo Could not find gui_app.py in: %HERE%
    echo Place this file next to gui_app.py or the Nexply.exe
    pause
    exit /b 1
)

:: Install dependencies if needed
if exist "%HERE%\requirements.txt" (
    echo Checking dependencies...
    %PY% -m pip install -q -r "%HERE%\requirements.txt" --no-warn-script-location
)

:: Launch from Python source
echo Launching Nexply from source...
start "" /D "%HERE%" %PY% -X utf8 "%HERE%\gui_app.py"
exit /b 0
