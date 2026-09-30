"""
NEXPLY - Scheduler
Windows Task Scheduler integration for daily automated runs.
Also provides a simple in-process scheduler using the 'schedule' library.

Usage (in-process):
    python -m agent.scheduler        # Run scheduler loop (keeps running)

Usage (Windows Task Scheduler):
    python -m agent.scheduler --install  # Register as Windows scheduled task
    python -m agent.scheduler --remove   # Remove scheduled task
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

import click
import schedule
import yaml
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
MAIN = str(BASE_DIR / "main.py")


def _load_settings() -> dict:
    cfg = BASE_DIR / "config" / "settings.yaml"
    if cfg.exists():
        with open(cfg, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _run_pipeline() -> None:
    """Trigger the full pipeline via subprocess."""
    console.print("\n[bold cyan]⏰ Scheduler: Starting daily pipeline...[/bold cyan]")
    try:
        result = subprocess.run(
            [PYTHON, MAIN, "run"],
            cwd=str(BASE_DIR),
            capture_output=False,
        )
        if result.returncode == 0:
            console.print("[green]✅ Daily pipeline completed.[/green]")
        else:
            console.print(f"[red]Pipeline exited with code {result.returncode}[/red]")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")


def _run_followup_check() -> None:
    """Run follow-up check."""
    console.print("[cyan]⏰ Checking follow-ups...[/cyan]")
    try:
        from agent.tracker import PipelineTracker
        from agent.dashboard import Dashboard
        items = PipelineTracker().get_follow_ups_due()
        if items:
            console.print(f"[yellow]⏰ {len(items)} follow-up(s) due![/yellow]")
            for item in items:
                console.print(
                    f"  • {item.get('title')} @ {item.get('company')} "
                    f"(due: {item.get('follow_up_due')})"
                )
        else:
            console.print("[green]✅ No follow-ups due.[/green]")
    except Exception as e:
        logger.error(f"Follow-up check failed: {e}")


def run_loop(hunt_time: str = "08:00", followup_time: str = "17:00") -> None:
    """Run the in-process scheduler loop."""
    console.print(f"\n[bold]🕐 Scheduler started[/bold]")
    console.print(f"   Daily pipeline : [cyan]{hunt_time}[/cyan]")
    console.print(f"   Follow-up check: [cyan]{followup_time}[/cyan]")
    console.print("   Press Ctrl+C to stop.\n")

    schedule.every().day.at(hunt_time).do(_run_pipeline)
    schedule.every().day.at(followup_time).do(_run_followup_check)

    while True:
        schedule.run_pending()
        next_run = schedule.next_run()
        console.print(f"[dim]Next run: {next_run}[/dim]", end="\r")
        time.sleep(60)


# ============================================================
# WINDOWS TASK SCHEDULER
# ============================================================

TASK_NAME_PIPELINE = "Nexply_DailyPipeline"
TASK_NAME_FOLLOWUP = "Nexply_FollowUp"


def install_windows_tasks(hunt_time: str = "08:00", followup_time: str = "17:00") -> None:
    """Register tasks with Windows Task Scheduler using schtasks."""
    hunt_hour, hunt_min = hunt_time.split(":")
    followup_hour, followup_min = followup_time.split(":")

    # Daily pipeline task
    cmd_pipeline = (
        f'schtasks /create /tn "{TASK_NAME_PIPELINE}" /f '
        f'/tr "\\"{PYTHON}\\" \\"{MAIN}\\" run" '
        f'/sc DAILY /st {hunt_time} '
        f'/rl HIGHEST'
    )

    # Follow-up check task
    cmd_followup = (
        f'schtasks /create /tn "{TASK_NAME_FOLLOWUP}" /f '
        f'/tr "\\"{PYTHON}\\" \\"{MAIN}\\" follow-up" '
        f'/sc DAILY /st {followup_time} '
        f'/rl HIGHEST'
    )

    for cmd, name in [
        (cmd_pipeline, TASK_NAME_PIPELINE),
        (cmd_followup, TASK_NAME_FOLLOWUP),
    ]:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            console.print(f"✅ Registered: [bold]{name}[/bold]")
        else:
            console.print(f"[red]❌ Failed to register {name}: {result.stderr}[/red]")
            console.print(f"[dim]Try running as Administrator[/dim]")


def remove_windows_tasks() -> None:
    """Remove Nexply scheduled tasks."""
    for name in [TASK_NAME_PIPELINE, TASK_NAME_FOLLOWUP]:
        result = subprocess.run(
            f'schtasks /delete /tn "{name}" /f',
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            console.print(f"✅ Removed: [bold]{name}[/bold]")
        else:
            console.print(f"[yellow]Task {name} not found or already removed.[/yellow]")


# ============================================================
# CLI
# ============================================================

@click.command()
@click.option("--install", is_flag=True, help="Install Windows scheduled tasks")
@click.option("--remove", is_flag=True, help="Remove Windows scheduled tasks")
@click.option("--hunt-time", default=None, help="Daily pipeline time (HH:MM)")
@click.option("--followup-time", default=None, help="Follow-up check time (HH:MM)")
def main(install: bool, remove: bool, hunt_time: str | None, followup_time: str | None) -> None:
    """NEXPLY Scheduler — manages daily automation."""
    settings = _load_settings()
    sched_cfg = settings.get("scheduler", {})

    hunt = hunt_time or sched_cfg.get("daily_hunt_time", "08:00")
    followup = followup_time or sched_cfg.get("follow_up_check_time", "17:00")

    if install:
        console.print("[bold]Installing Windows scheduled tasks...[/bold]")
        install_windows_tasks(hunt, followup)
    elif remove:
        console.print("[bold]Removing Windows scheduled tasks...[/bold]")
        remove_windows_tasks()
    else:
        run_loop(hunt, followup)


if __name__ == "__main__":
    main()
