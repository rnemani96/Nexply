"""
NEXPLY - APPROVAL GATE
Rich CLI prompt for human review before submitting a job application.

Shows:
  - Job details (title, company, location, salary)
  - Match score and AI recommendation
  - Matched vs missing skills
  - ATS score and warnings
  - Resume diff summary

Actions: Apply / Skip / Edit Notes / Blacklist Company
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


@dataclass
class ApprovalDecision:
    action: str              # "apply" | "skip" | "blacklist" | "edit"
    notes: str = ""


def show_approval_prompt(
    job: dict,
    resume_path: Path,
    ats_score: float,
    ats_warnings: list[str],
) -> ApprovalDecision:
    """
    Show a rich terminal prompt for reviewing a job application.
    Returns the user's decision.
    """
    console.print()
    console.rule("[bold cyan]📋 APPLICATION REVIEW[/bold cyan]")
    console.print()

    # ---- Job Details Panel ----
    salary = _format_salary(job)
    location_fmt = job.get("jd_location_format", "")
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold dim")
    details.add_column()
    details.add_row("Position", f"[bold]{job.get('title', '')}[/bold]")
    details.add_row("Company", job.get("company", ""))
    details.add_row("Location", f"{job.get('location', '')}  [{location_fmt}]" if location_fmt else job.get("location", ""))
    details.add_row("Work Mode", job.get("jd_work_mode", job.get("remote_type", "")))
    details.add_row("Salary", salary or "Not specified")
    details.add_row("Source", job.get("source", ""))
    details.add_row("URL", f"[link={job.get('url', '')}]{job.get('url', '')[:60]}...[/link]")

    console.print(Panel(details, title="Job Details", border_style="blue"))

    # ---- Match Score Panel ----
    score = job.get("ai_match_score") or job.get("match_score") or 0
    score_color = "green" if score >= 80 else "yellow" if score >= 65 else "red"
    recommendation = job.get("recommendation", "")
    rec_icons = {
        "strong_apply": "🟢 STRONG APPLY",
        "apply": "🟡 APPLY",
        "stretch": "🟠 STRETCH",
        "skip": "🔴 SKIP",
    }
    rec_text = rec_icons.get(recommendation, recommendation.upper())

    matched = _parse_json_list(job.get("matched_skills", "[]"))
    missing = _parse_json_list(job.get("missing_skills", "[]"))

    score_table = Table.grid(padding=(0, 2))
    score_table.add_column(style="bold dim")
    score_table.add_column()
    score_table.add_row("AI Match Score", f"[{score_color} bold]{score:.0f}/100[/{score_color} bold]")
    score_table.add_row("Recommendation", rec_text)
    score_table.add_row("Gap Analysis", job.get("gap_analysis", "N/A"))
    score_table.add_row("Matched Skills", Text(", ".join(matched[:8]) or "None", style="green"))
    score_table.add_row("Missing Skills", Text(", ".join(missing[:8]) or "None", style="red"))

    console.print(Panel(score_table, title="AI Match Analysis", border_style=score_color))

    # ---- Resume & ATS Panel ----
    ats_color = "green" if ats_score >= 80 else "yellow" if ats_score >= 60 else "red"
    resume_table = Table.grid(padding=(0, 2))
    resume_table.add_column(style="bold dim")
    resume_table.add_column()
    resume_table.add_row("Resume File", str(resume_path.name))
    resume_table.add_row("ATS Score", f"[{ats_color} bold]{ats_score:.0f}/100[/{ats_color} bold]")

    if ats_warnings:
        resume_table.add_row("ATS Warnings", Text("\n".join(f"⚠ {w}" for w in ats_warnings), style="yellow"))
    else:
        resume_table.add_row("ATS Warnings", Text("✅ None", style="green"))

    console.print(Panel(resume_table, title="Resume & ATS", border_style=ats_color))

    # ---- Action Prompt ----
    console.print()
    console.print("[bold]What would you like to do?[/bold]")
    console.print("  [green bold][A][/green bold] Apply now")
    console.print("  [yellow bold][S][/yellow bold] Skip this job")
    console.print("  [red bold][B][/red bold] Blacklist company")
    console.print("  [cyan bold][N][/cyan bold] Add note and skip")
    console.print()

    while True:
        choice = Prompt.ask("Choice", choices=["a", "s", "b", "n", "A", "S", "B", "N"]).lower()

        if choice == "a":
            console.print("[green]✅ Queued for application.[/green]")
            return ApprovalDecision(action="apply")

        elif choice == "s":
            console.print("[yellow]⏭ Skipped.[/yellow]")
            return ApprovalDecision(action="skip")

        elif choice == "b":
            company = job.get("company", "this company")
            if Confirm.ask(f"[red]Blacklist '{company}'? All future jobs from them will be skipped.[/red]"):
                return ApprovalDecision(action="blacklist", notes=f"Blacklisted: {company}")
            console.print("[dim]Blacklist cancelled.[/dim]")

        elif choice == "n":
            note = Prompt.ask("Enter note")
            return ApprovalDecision(action="skip", notes=note)


def auto_approve_check(
    job: dict,
    auto_apply_score: float = 85,
) -> Optional[ApprovalDecision]:
    """
    In auto mode, return ApprovalDecision('apply') if score is high enough.
    Returns None if human review is still needed.
    """
    score = job.get("ai_match_score") or job.get("match_score") or 0
    if score >= auto_apply_score:
        console.print(
            f"[green]🤖 Auto-applying: score {score:.0f} ≥ threshold {auto_apply_score}[/green]"
        )
        return ApprovalDecision(action="apply", notes="auto-approved")
    return None


# ============================================================
# HELPERS
# ============================================================

def _format_salary(job: dict) -> str:
    low = job.get("salary_min")
    high = job.get("salary_max")
    currency = job.get("salary_currency", "")
    period = job.get("salary_period", "annual")

    if low and high:
        return f"{currency}{int(low):,} – {currency}{int(high):,} / {period}"
    elif low:
        return f"{currency}{int(low):,}+ / {period}"
    return ""


def _parse_json_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except Exception:
        return []
