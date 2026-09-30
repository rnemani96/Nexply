"""
NEXPLY - Live Dashboard
Rich terminal interface showing pipeline status at a glance.

Run: python -m agent.dashboard
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

STATUS_ICONS = {
    "NEW":             "📥",
    "ANALYZED":        "🔍",
    "MATCHED":         "🎯",
    "TAILORED":        "📝",
    "QUEUED":          "⏳",
    "APPLIED":         "📤",
    "INTERVIEW_SCREEN":"📞",
    "INTERVIEW_TECH":  "💻",
    "OFFER":           "🏆",
    "ACCEPTED":        "✅",
    "REJECTED":        "❌",
    "GHOSTED":         "👻",
    "WITHDRAWN":       "🚫",
}

SCORE_COLOR = {
    "strong_apply": "green",
    "apply": "yellow",
    "stretch": "orange3",
    "skip": "red",
}


class Dashboard:
    """Rich terminal dashboard for the Nexply pipeline."""

    def show(self) -> None:
        """Render the full dashboard."""
        console.print()
        console.rule(
            f"[bold magenta]🤖 NEXPLY DASHBOARD  —  "
            f"{datetime.now().strftime('%A, %d %b %Y  %H:%M')}[/bold magenta]"
        )
        console.print()

        # Load data
        try:
            from agent.database import (
                get_pipeline_stats, get_top_matches,
                get_follow_up_queue, get_job_count, get_connection,
            )
            from agent.ai_engine import get_ai_engine

            stats = get_pipeline_stats()
            top_matches = get_top_matches(min_score=60, limit=10)
            follow_ups = get_follow_up_queue()
            total_jobs = get_job_count()
            ai_status = get_ai_engine().status()

        except Exception as e:
            console.print(f"[red]Failed to load data: {e}[/red]")
            return

        # ---- Row 1: Pipeline Overview + AI Status ----
        pipeline_panel = self._build_pipeline_panel(stats, total_jobs)
        ai_panel = self._build_ai_panel(ai_status)
        console.print(Columns([pipeline_panel, ai_panel], equal=True, expand=True))
        console.print()

        # ---- Row 2: Quick Stats ----
        console.print(self._build_quick_stats(stats))
        console.print()

        # ---- Row 3: Top Matches ----
        console.print(self._build_top_matches_panel(top_matches))
        console.print()

        # ---- Row 4: Follow-up Queue ----
        if follow_ups:
            console.print(self._build_followup_panel(follow_ups))
            console.print()

        console.rule("[dim]Run 'python main.py --help' for commands[/dim]")

    def _build_pipeline_panel(self, stats: dict, total: int) -> Panel:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Stage", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("", width=20)

        # Build funnel bar
        max_count = max(stats.values(), default=1)
        for stage in [
            "NEW", "ANALYZED", "MATCHED", "TAILORED",
            "APPLIED", "INTERVIEW_SCREEN", "OFFER", "ACCEPTED",
        ]:
            count = stats.get(stage, 0)
            icon = STATUS_ICONS.get(stage, "•")
            bar_width = max(1, int((count / max_count) * 15)) if max_count > 0 else 0
            bar = "█" * bar_width

            color = "cyan"
            if stage in ("OFFER", "ACCEPTED"):
                color = "green"
            elif stage in ("INTERVIEW_SCREEN", "INTERVIEW_TECH"):
                color = "yellow"

            table.add_row(
                f"{icon} {stage}",
                str(count),
                f"[{color}]{bar}[/{color}]",
            )

        # Terminal states
        rejected = stats.get("REJECTED", 0)
        ghosted = stats.get("GHOSTED", 0)
        if rejected or ghosted:
            table.add_section()
            table.add_row("❌ REJECTED", str(rejected), "")
            table.add_row("👻 GHOSTED", str(ghosted), "")

        return Panel(
            table,
            title=f"[bold]📊 Pipeline  ({total} total jobs)[/bold]",
            border_style="blue",
        )

    def _build_ai_panel(self, ai_status: dict) -> Panel:
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Provider", style="bold")
        table.add_column("Status")

        for name, available in ai_status.items():
            icon = "✅" if available else "❌"
            status = "[green]READY[/green]" if available else "[red]OFFLINE[/red]"
            table.add_row(f"{icon} {name.capitalize()}", status)

        # Show which local models are available
        if ai_status.get("ollama"):
            try:
                from agent.ai_engine import OllamaProvider
                models = OllamaProvider({}).list_models()
                if models:
                    table.add_section()
                    for m in models[:5]:
                        table.add_row(f"  └ {m}", "[dim]model[/dim]")
            except Exception:
                pass

        return Panel(
            table,
            title="[bold]🤖 AI Providers[/bold]",
            border_style="magenta",
        )

    def _build_quick_stats(self, stats: dict) -> Panel:
        applied = stats.get("APPLIED", 0) + stats.get("INTERVIEW_SCREEN", 0) + \
                  stats.get("INTERVIEW_TECH", 0) + stats.get("OFFER", 0) + \
                  stats.get("ACCEPTED", 0)
        interviews = stats.get("INTERVIEW_SCREEN", 0) + stats.get("INTERVIEW_TECH", 0)
        offers = stats.get("OFFER", 0) + stats.get("ACCEPTED", 0)

        response_rate = f"{(interviews / applied * 100):.0f}%" if applied > 0 else "—"
        offer_rate = f"{(offers / applied * 100):.0f}%" if applied > 0 else "—"

        table = Table(box=box.SIMPLE, show_header=False, expand=True)
        table.add_column("Metric", style="bold dim", width=22)
        table.add_column("Value", style="bold")
        table.add_column("Metric", style="bold dim", width=22)
        table.add_column("Value", style="bold")

        table.add_row(
            "Total Applied", f"[cyan]{applied}[/cyan]",
            "Interview Rate", f"[yellow]{response_rate}[/yellow]",
        )
        table.add_row(
            "Interviews", f"[yellow]{interviews}[/yellow]",
            "Offer Rate", f"[green]{offer_rate}[/green]",
        )
        table.add_row(
            "Offers", f"[green]{offers}[/green]",
            "Active Pipeline", f"[cyan]{stats.get('TAILORED', 0) + stats.get('QUEUED', 0)}[/cyan]",
        )

        return Panel(table, title="[bold]📈 Quick Stats[/bold]", border_style="cyan")

    def _build_top_matches_panel(self, jobs: list[dict]) -> Panel:
        if not jobs:
            return Panel("[dim]No matches yet. Run: python main.py hunt[/dim]",
                        title="🎯 Top Matches", border_style="green")

        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("#", width=3, justify="right")
        table.add_column("Title", min_width=25)
        table.add_column("Company", min_width=18)
        table.add_column("Score", justify="center", width=7)
        table.add_column("AI Says", width=14)
        table.add_column("Status", width=10)
        table.add_column("Location Format", width=6)

        for i, job in enumerate(jobs, 1):
            score = job.get("ai_match_score") or 0
            rec = job.get("recommendation", "")
            score_color = SCORE_COLOR.get(rec, "white")
            status = job.get("status", "")
            loc_fmt = job.get("jd_location_format", "?")

            table.add_row(
                str(i),
                Text(str(job.get("title", ""))[:30], no_wrap=True),
                Text(str(job.get("company", ""))[:20], no_wrap=True),
                f"[{score_color} bold]{score:.0f}[/{score_color} bold]",
                Text(rec.replace("_", " ").title()[:14], style=score_color),
                Text(status[:10], style="dim"),
                Text(loc_fmt.upper()[:6], style="dim"),
            )

        return Panel(
            table,
            title=f"[bold]🎯 Top Matches ({len(jobs)} shown)[/bold]",
            border_style="green",
        )

    def _build_followup_panel(self, follow_ups: list[dict]) -> Panel:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Applied")
        table.add_column("Follow-up Due", style="yellow bold")
        table.add_column("URL")

        for item in follow_ups[:8]:
            applied = str(item.get("applied_at", ""))[:10]
            due = str(item.get("follow_up_due", ""))[:10]
            url = str(item.get("url", ""))[:40] + "..."

            table.add_row(
                str(item.get("title", ""))[:28],
                str(item.get("company", ""))[:18],
                applied,
                due,
                url,
            )

        return Panel(
            table,
            title=f"[bold]⏰ Follow-up Queue ({len(follow_ups)} pending)[/bold]",
            border_style="yellow",
        )


if __name__ == "__main__":
    Dashboard().show()
