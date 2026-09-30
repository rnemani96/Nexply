"""
RAJESH AI - Autonomous Job Applier v2.0
Main CLI entry point.

Usage:
    python main.py                      # Show dashboard
    python main.py hunt                 # Scrape new jobs from all sources
    python main.py analyze              # AI analysis of NEW job descriptions
    python main.py match                # Score jobs against your profile
    python main.py tailor               # Generate tailored resumes for top matches
    python main.py apply                # Apply (with approval gate)
    python main.py run                  # Full pipeline: hunt→analyze→match→tailor→apply
    python main.py run --dry-run        # Full pipeline, no actual submissions
    python main.py dashboard            # Show pipeline dashboard
    python main.py status               # Quick pipeline status
    python main.py follow-up            # Show follow-up queue
    python main.py export               # Export pipeline to CSV
    python main.py ai-status            # Check AI provider availability
    python main.py setup                # First-time setup

Options:
    --dry-run     Run without submitting applications
    --job-id INT  Target a specific job by database ID
    --limit INT   Max jobs to process
    --provider    Override AI provider (gemini|ollama|lmstudio)
"""
from __future__ import annotations

import sys
import os
import logging
from pathlib import Path

# Fix Windows terminal encoding for emoji/unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import click
from rich.console import Console
from rich.table import Table
from rich import box

BASE_DIR = Path(__file__).resolve().parent
console = Console(force_terminal=True, emoji=True)


# ============================================================
# LOGGING SETUP
# ============================================================

def setup_logging(verbose: bool = False) -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "rajesh_ai.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout) if verbose else logging.NullHandler(),
        ],
    )


# ============================================================
# CLI
# ============================================================

@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--provider", type=click.Choice(["gemini", "ollama", "lmstudio"]),
              help="Override AI provider", default=None)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, provider: str | None) -> None:
    """🤖 RAJESH AI — Autonomous Job Applier"""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["provider"] = provider

    if ctx.invoked_subcommand is None:
        # Default: show dashboard
        from agent.dashboard import Dashboard
        Dashboard().show()


@cli.command()
@click.pass_context
def dashboard(ctx: click.Context) -> None:
    """Show pipeline dashboard."""
    from agent.dashboard import Dashboard
    Dashboard().show()


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Quick pipeline status summary."""
    from agent.database import get_pipeline_stats, get_job_count
    stats = get_pipeline_stats()
    total = get_job_count()

    console.print(f"\n[bold]📊 Pipeline Status — {total} total jobs[/bold]\n")
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    for stage in ["NEW", "ANALYZED", "MATCHED", "TAILORED", "APPLIED",
                  "INTERVIEW_SCREEN", "INTERVIEW_TECH", "OFFER", "ACCEPTED",
                  "REJECTED", "GHOSTED"]:
        count = stats.get(stage, 0)
        if count > 0:
            table.add_row(stage, str(count))
    console.print(table)


@cli.command()
@click.pass_context
def hunt(ctx: click.Context) -> None:
    """🔍 Scrape new jobs from all enabled sources."""
    from agent.orchestrator import DailyPipeline
    pipeline = DailyPipeline()
    count = pipeline.run_hunt()
    console.print(f"\n✅ Added [bold]{count}[/bold] new jobs to database.")


@cli.command()
@click.option("--limit", default=50, show_default=True, help="Max jobs to analyze")
@click.pass_context
def analyze(ctx: click.Context, limit: int) -> None:
    """🧠 AI analysis of NEW job descriptions."""
    from agent.orchestrator import DailyPipeline
    pipeline = DailyPipeline()
    count = pipeline.run_analyze(limit=limit)
    console.print(f"\n✅ Analyzed [bold]{count}[/bold] job descriptions.")


@cli.command()
@click.pass_context
def match(ctx: click.Context) -> None:
    """🎯 Score ANALYZED jobs against your profile."""
    from agent.orchestrator import DailyPipeline
    pipeline = DailyPipeline()
    count = pipeline.run_match()
    console.print(f"\n✅ Scored [bold]{count}[/bold] jobs.")


@cli.command()
@click.option("--limit", default=None, type=int, help="Max resumes to generate")
@click.option("--job-id", default=None, type=int, help="Tailor resume for a specific job ID")
@click.pass_context
def tailor(ctx: click.Context, limit: int | None, job_id: int | None) -> None:
    """📝 Generate tailored resumes for top matched jobs."""
    if job_id:
        # Tailor for a specific job
        from agent.database import get_connection
        from agent.ai_engine import get_ai_engine, JDProfile
        from agent.resume_tailor_v1 import tailor_resume_for_job
        import json

        conn = get_connection()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()

        if not row:
            console.print(f"[red]Job ID {job_id} not found.[/red]")
            return

        job = dict(row)
        ai = get_ai_engine()
        result = tailor_resume_for_job(job, ai, {})
        if result:
            console.print(f"✅ Resume generated: [link={result}]{result}[/link]")
    else:
        from agent.orchestrator import DailyPipeline
        pipeline = DailyPipeline()
        count = pipeline.run_tailor(limit=limit)
        console.print(f"\n✅ Tailored [bold]{count}[/bold] resumes.")


@cli.command()
@click.option("--dry-run", is_flag=True, help="Fill forms but don't click Submit")
@click.option("--job-id", default=None, type=int, help="Apply to a specific job ID")
@click.pass_context
def apply(ctx: click.Context, dry_run: bool, job_id: int | None) -> None:
    """📤 Apply to TAILORED jobs (with approval gate)."""
    if job_id:
        from agent.database import get_connection
        from agent.applier import ApplicationEngine
        from agent.approval_gate import show_approval_prompt
        from pathlib import Path

        conn = get_connection()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()

        if not row:
            console.print(f"[red]Job ID {job_id} not found.[/red]")
            return

        job = dict(row)
        resume_path = Path(job.get("resume_path", ""))
        if not resume_path.exists():
            console.print(f"[red]Resume not found: {resume_path}[/red]")
            console.print(f"[yellow]Run: python main.py tailor --job-id {job_id}[/yellow]")
            return

        decision = show_approval_prompt(job, resume_path, job.get("ats_score", 0), [])
        if decision.action == "apply":
            engine = ApplicationEngine({})
            result = engine.apply(job, resume_path, dry_run=dry_run)
            if result.success:
                console.print(f"✅ Applied! Confirmation: {result.confirmation_id or 'N/A'}")
            else:
                console.print(f"[red]Failed: {result.error}[/red]")
    else:
        from agent.orchestrator import DailyPipeline
        pipeline = DailyPipeline(dry_run=dry_run)
        count = pipeline.run_apply()
        console.print(f"\n✅ Applied to [bold]{count}[/bold] jobs.")


@cli.command("run")
@click.option("--dry-run", is_flag=True, help="Full pipeline without submitting applications")
@click.pass_context
def run_all(ctx: click.Context, dry_run: bool) -> None:
    """🚀 Run the complete pipeline: hunt→analyze→match→tailor→apply."""
    from agent.orchestrator import DailyPipeline
    pipeline = DailyPipeline(dry_run=dry_run)
    stats = pipeline.run_all()


@cli.command("follow-up")
@click.pass_context
def follow_up(ctx: click.Context) -> None:
    """⏰ Show jobs that need follow-up."""
    from agent.tracker import PipelineTracker
    tracker = PipelineTracker()
    items = tracker.get_follow_ups_due()

    if not items:
        console.print("✅ No follow-ups due today.")
        return

    console.print(f"\n[yellow bold]⏰ {len(items)} Follow-up(s) Due[/yellow bold]\n")
    for item in items:
        console.print(
            f"  • [bold]{item.get('title')}[/bold] @ {item.get('company')}\n"
            f"    Applied: {str(item.get('applied_at', ''))[:10]}  "
            f"Due: {item.get('follow_up_due')}\n"
            f"    URL: {item.get('url', '')}\n"
        )


@cli.command()
@click.option("--output", "-o", default="output/pipeline_export.csv", show_default=True)
@click.pass_context
def export(ctx: click.Context, output: str) -> None:
    """📊 Export pipeline to CSV."""
    from agent.tracker import PipelineTracker
    tracker = PipelineTracker()
    tracker.export_to_csv(BASE_DIR / output)


@cli.command("ai-status")
@click.pass_context
def ai_status(ctx: click.Context) -> None:
    """🤖 Check AI provider availability and active models."""
    from agent.ai_engine import get_ai_engine, OllamaProvider, LMStudioProvider

    engine = get_ai_engine()
    status = engine.status()

    console.print("\n[bold]AI Provider Status[/bold]\n")
    for name, available in status.items():
        icon = "✅" if available else "❌"
        console.print(f"  {icon}  [bold]{name.capitalize()}[/bold]  {'READY' if available else 'OFFLINE'}")

        # List available models for local providers
        if available and name == "ollama":
            try:
                models = OllamaProvider({}).list_models()
                for m in models:
                    console.print(f"       └ {m}")
            except Exception:
                pass
        elif available and name == "lmstudio":
            try:
                models = LMStudioProvider({}).list_models()
                for m in models:
                    console.print(f"       └ {m}")
            except Exception:
                pass

    active = engine.active_provider_name()
    console.print(f"\n  Active provider: [bold green]{active}[/bold green]")

    if active != "none":
        console.print("\n  Running test query...")
        try:
            result = engine.analyze_jd(
                "We are hiring a Senior GenAI Engineer. "
                "Requirements: Python, LangChain, RAG, vector databases. "
                "Nice to have: LangGraph, Docker."
            )
            console.print(f"  ✅ Required: {result.required_skills}")
            console.print(f"  ✅ Preferred: {result.preferred_skills}")
            console.print(f"  ✅ Seniority: {result.seniority}")
        except Exception as e:
            console.print(f"  [red]Test failed: {e}[/red]")


@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """⚙️ First-time setup: install deps, configure DB, check AI."""
    console.print("\n[bold cyan]RAJESH AI — Setup[/bold cyan]\n")

    # 1. Initialize database
    console.print("1. Initializing database...")
    from agent.database import initialize_database, migrate_v1_to_v2
    initialize_database()
    migrate_v1_to_v2()
    console.print("   ✅ Database ready")

    # 2. Check AI providers
    console.print("\n2. Checking AI providers...")
    from agent.ai_engine import get_ai_engine
    engine = get_ai_engine()
    status = engine.status()
    for name, available in status.items():
        icon = "✅" if available else "❌"
        console.print(f"   {icon} {name}")

    active = engine.active_provider_name()
    if active == "none":
        console.print("\n   [yellow]⚠ No AI provider available![/yellow]")
        console.print("   Quick fix — install Ollama:")
        console.print("   • Download from: https://ollama.com")
        console.print("   • Then run: ollama pull llama3.1")
    else:
        console.print(f"\n   Active: [green]{active}[/green]")

    # 3. Check resume
    console.print("\n3. Checking master resume...")
    resume = BASE_DIR / "resume" / "master_resume.docx"
    if resume.exists():
        console.print(f"   ✅ Found: {resume.name}")
    else:
        console.print(f"   [yellow]⚠ Not found: {resume}[/yellow]")
        console.print("   Place your resume at: resume/master_resume.docx")

    # 4. Check Playwright
    console.print("\n4. Checking Playwright for browser automation...")
    try:
        import playwright
        console.print("   ✅ Playwright installed")
    except ImportError:
        console.print("   ⚠ Playwright not installed. Run:")
        console.print("     pip install playwright && playwright install chromium")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("\nNext steps:")
    console.print("  1. Run: [bold]python main.py hunt[/bold]          # Find jobs")
    console.print("  2. Run: [bold]python main.py analyze[/bold]       # AI JD analysis")
    console.print("  3. Run: [bold]python main.py match[/bold]         # Score matches")
    console.print("  4. Run: [bold]python main.py tailor[/bold]        # Generate resumes")
    console.print("  5. Run: [bold]python main.py apply[/bold]         # Apply!")
    console.print("\n  Or run everything at once: [bold]python main.py run[/bold]")


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    cli()