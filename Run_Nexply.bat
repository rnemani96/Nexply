@echo off
setlocal
title Nexply

cd /d "%~dp0"

REM 1. Check for standalone EXE in current directory
if exist "Nexply.exe" goto :run_current_nexply
if exist "RajeshAI.exe" goto :run_current_rajesh

REM 2. Check in dist subfolder
if exist "dist\Nexply\Nexply.exe" goto :run_dist_nexply
if exist "dist\RajeshAI\RajeshAI.exe" goto :run_dist_rajesh

REM 3. Check in parent folder
if exist "..\Nexply.exe" goto :run_parent_nexply
if exist "..\RajeshAI.exe" goto :run_parent_rajesh

REM 4. Fallback to Python source
goto :run_python

:run_current_nexply
start "" "Nexply.exe"
exit /b 0

:run_current_rajesh
start "" "RajeshAI.exe"
exit /b 0

:run_dist_nexply
cd "dist\Nexply"
start "" "Nexply.exe"
exit /b 0

:run_dist_rajesh
cd "dist\RajeshAI"
start "" "RajeshAI.exe"
exit /b 0

:run_parent_nexply
cd ".."
start "" "Nexply.exe"
exit /b 0

:run_parent_rajesh
cd ".."
start "" "RajeshAI.exe"
exit /b 0

:run_python
echo Starting Nexply via Python...
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Neither Nexply.exe nor Python was found on this system.
        echo Please ensure Python 3.11+ is installed and on your PATH.
        pause
        exit /b 1
    ) else (
        set "PY_CMD=py"
    )
) else (
    set "PY_CMD=python"
)

if not exist "gui_app.py" (
    echo [ERROR] Could not find gui_app.py in %CD%
    pause
    exit /b 1
)

start "" %PY_CMD% -X utf8 gui_app.py
exit /b 0
