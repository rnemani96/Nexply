"""
NEXPLY - ORCHESTRATOR v2.0
Daily pipeline runner that coordinates all components:
  1. Hunt new jobs from all sources
  2. Analyze JDs with AI
  3. Score matches
  4. Generate tailored resumes for top matches
  5. Queue or auto-apply with approval gate
  6. Track pipeline progress
  7. Generate daily digest
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.yaml"


def _load_settings() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# ============================================================
# DAILY PIPELINE
# ============================================================

class DailyPipeline:
    """
    End-to-end job hunting and application pipeline.

    Steps:
      hunt → analyze → match → tailor → (approve) → apply → track
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        dry_run: bool = False,
    ):
        self._settings = settings or _load_settings()
        self._dry_run = dry_run

        # Import modules lazily to avoid circular imports
        from agent.ai_engine import get_ai_engine
        from agent.database import (
            initialize_database, migrate_v1_to_v2,
            get_pipeline_stats, update_job_analysis,
            update_job_match, get_top_matches,
        )

        self._ai = get_ai_engine(self._settings)
        initialize_database()
        migrate_v1_to_v2()

        self._search_cfg = self._settings.get("search", {})
        self._app_cfg = self._settings.get("application", {})
        self._ats_cfg = self._settings.get("ats", {})
        self._candidate_cfg = self._settings.get("candidate", {})

    # ----------------------------------------------------------------
    # STEP 1: HUNT
    # ----------------------------------------------------------------

    def run_hunt(self) -> int:
        """Scrape jobs from all enabled sources. Returns count of new jobs."""
        from agent.job_hunter import JobHunter

        console.print("\n[bold cyan]🔍 Step 1: Job Hunting[/bold cyan]")
        hunter = JobHunter(self._settings)
        new_count = hunter.run()
        console.print(f"  ✅ Found [bold]{new_count}[/bold] new jobs")
        return new_count

    # ----------------------------------------------------------------
    # STEP 2: ANALYZE JDs
    # ----------------------------------------------------------------

    def run_analyze(self, limit: int = 50) -> int:
        """Run AI JD analysis on NEW jobs. Returns count analyzed."""
        from agent.database import get_jobs_by_status, update_job_analysis

        console.print("\n[bold cyan]🧠 Step 2: JD Analysis[/bold cyan]")

        jobs = get_jobs_by_status("NEW")[:limit]
        if not jobs:
            console.print("  ℹ No NEW jobs to analyze.")
            return 0

        analyzed = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing JDs...", total=len(jobs))

            for job in jobs:
                try:
                    desc = job.get("description", "")
                    if not desc or len(desc) < 50:
                        progress.advance(task)
                        continue

                    jd_profile = self._ai.analyze_jd(desc)
                    update_job_analysis(
                        job_id=job["id"],
                        required_skills=jd_profile.required_skills,
                        preferred_skills=jd_profile.preferred_skills,
                        role_type=jd_profile.role_type,
                        seniority=jd_profile.seniority,
                        work_mode=jd_profile.work_mode,
                        location_format=jd_profile.location_format,
                        summary=jd_profile.summary,
                        provider=jd_profile.raw_provider,
                    )
                    analyzed += 1
                    time.sleep(0.5)  # Rate limiting for Ollama

                except Exception as e:
                    logger.error(f"JD analysis failed for job {job['id']}: {e}")

                finally:
                    progress.advance(task)

        console.print(f"  ✅ Analyzed [bold]{analyzed}[/bold] job descriptions")
        return analyzed

    # ----------------------------------------------------------------
    # STEP 3: MATCH SCORING
    # ----------------------------------------------------------------

    def run_match(self) -> int:
        """AI match scoring for all ANALYZED jobs. Returns count scored."""
        from agent.database import get_jobs_by_status, update_job_match

        console.print("\n[bold cyan]🎯 Step 3: Match Scoring[/bold cyan]")

        # Load candidate profile
        candidate_profile = self._load_candidate_profile()
        jobs = get_jobs_by_status("ANALYZED")

        if not jobs:
            console.print("  ℹ No ANALYZED jobs to score.")
            return 0

        scored = 0
        min_score = self._search_cfg.get("min_match_score", 60)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("Scoring matches...", total=len(jobs))

            for job in jobs:
                try:
                    from agent.ai_engine import JDProfile
                    jd_profile = JDProfile(
                        required_skills=self._parse_json_list(job.get("jd_required_skills")),
                        preferred_skills=self._parse_json_list(job.get("jd_preferred_skills")),
                        role_type=job.get("jd_role_type", ""),
                        seniority=job.get("jd_seniority", ""),
                        work_mode=job.get("jd_work_mode", ""),
                        location_format=job.get("jd_location_format", ""),
                    )

                    result = self._ai.score_match(candidate_profile, jd_profile)
                    update_job_match(
                        job_id=job["id"],
                        ai_score=result.score,
                        matched_skills=result.matched_skills,
                        missing_skills=result.missing_skills,
                        gap_analysis=result.gap_analysis,
                        recommendation=result.recommendation,
                    )
                    scored += 1
                    time.sleep(0.3)

                except Exception as e:
                    logger.error(f"Scoring failed for job {job['id']}: {e}")
                finally:
                    progress.advance(task)

        console.print(f"  ✅ Scored [bold]{scored}[/bold] jobs")
        return scored

    # ----------------------------------------------------------------
    # STEP 4: TAILOR RESUMES
    # ----------------------------------------------------------------

    def run_tailor(self, limit: Optional[int] = None) -> int:
        """Generate tailored resumes for top matches."""
        from agent.database import get_top_matches, update_job_status
        from agent.resume_tailor_v1 import tailor_resume_for_job

        console.print("\n[bold cyan]📝 Step 4: Resume Tailoring[/bold cyan]")

        max_per_day = limit or self._search_cfg.get("top_matches_per_day", 15)
        min_score = self._search_cfg.get("min_match_score", 60)
        jobs = get_top_matches(min_score=min_score, limit=max_per_day)

        if not jobs:
            console.print(f"  ℹ No jobs with score ≥ {min_score} to tailor.")
            return 0

        tailored = 0
        for job in jobs:
            try:
                resume_path = tailor_resume_for_job(job, self._ai, self._settings)
                if resume_path:
                    update_job_status(job["id"], "TAILORED")
                    tailored += 1
                    console.print(
                        f"  ✅ [green]{job.get('title')}[/green] @ {job.get('company')} "
                        f"— score: {job.get('ai_match_score', 0):.0f}"
                    )
            except Exception as e:
                logger.error(f"Resume tailoring failed for job {job['id']}: {e}")

        console.print(f"  ✅ Tailored [bold]{tailored}[/bold] resumes")
        return tailored

    # ----------------------------------------------------------------
    # STEP 5: APPLY
    # ----------------------------------------------------------------

    def run_apply(self) -> int:
        """Apply to TAILORED jobs via approval gate + automation."""
        from agent.database import get_jobs_by_status, update_job_status, add_application
        from agent.applier import ApplicationEngine
        from agent.approval_gate import show_approval_prompt, auto_approve_check

        console.print("\n[bold cyan]📤 Step 5: Applying[/bold cyan]")

        jobs = get_jobs_by_status("TAILORED")
        if not jobs:
            console.print("  ℹ No TAILORED jobs ready to apply.")
            return 0

        mode = self._app_cfg.get("mode", "human_approval")
        auto_score = self._app_cfg.get("auto_apply_score", 85)
        app_engine = ApplicationEngine(self._settings)
        applied = 0

        for job in jobs:
            resume_path = Path(job.get("resume_path", ""))
            if not resume_path.exists():
                logger.warning(f"Resume not found for job {job['id']}: {resume_path}")
                continue

            ats_score = job.get("ats_score", 0) or 0
            ats_warnings: list[str] = []

            # Decision gate
            if mode == "auto":
                decision = auto_approve_check(job, auto_score)
                if decision is None:
                    decision = show_approval_prompt(job, resume_path, ats_score, ats_warnings)
            else:
                decision = show_approval_prompt(job, resume_path, ats_score, ats_warnings)

            if decision.action == "apply":
                result = app_engine.apply(
                    job, resume_path, dry_run=self._dry_run
                )
                if result.success:
                    app_id = add_application(
                        job_id=job["id"],
                        platform=result.platform,
                        resume_path=str(resume_path),
                        ats_score=ats_score,
                        submission_method=result.method,
                        confirmation_id=result.confirmation_id,
                    )
                    applied += 1
                    console.print(
                        f"  ✅ Applied to [green]{job.get('title')}[/green] "
                        f"@ {job.get('company')}"
                    )
                else:
                    console.print(f"  ❌ Failed: {result.error}")

            elif decision.action == "blacklist":
                update_job_status(job["id"], "WITHDRAWN", notes=decision.notes)

            elif decision.action == "skip":
                update_job_status(job["id"], "WITHDRAWN", notes=decision.notes or "Skipped by user")

        console.print(f"  ✅ Applied to [bold]{applied}[/bold] jobs")
        return applied

    # ----------------------------------------------------------------
    # FULL PIPELINE
    # ----------------------------------------------------------------

    def run_all(self) -> dict:
        """Run the complete pipeline end-to-end."""
        dry_tag = " [DRY RUN]" if self._dry_run else ""
        console.print(f"\n[bold magenta]{'='*55}[/bold magenta]")
        console.print(f"[bold magenta]  NEXPLY — DAILY PIPELINE{dry_tag}[/bold magenta]")
        console.print(f"[bold magenta]  {datetime.now().strftime('%Y-%m-%d %H:%M')}[/bold magenta]")
        console.print(f"[bold magenta]  AI Provider: {self._ai.active_provider_name()}[/bold magenta]")
        console.print(f"[bold magenta]{'='*55}[/bold magenta]")

        stats = {}
        start = time.time()

        stats["hunted"] = self.run_hunt()
        stats["analyzed"] = self.run_analyze()
        stats["scored"] = self.run_match()
        stats["tailored"] = self.run_tailor()
        stats["applied"] = self.run_apply()

        elapsed = time.time() - start

        console.print(f"\n[bold magenta]{'='*55}[/bold magenta]")
        console.print("[bold]Pipeline complete:[/bold]")
        for k, v in stats.items():
            console.print(f"  {k.capitalize():<12}: {v}")
        console.print(f"  Duration    : {elapsed:.0f}s")
        console.print(f"[bold magenta]{'='*55}[/bold magenta]\n")

        return stats

    # ----------------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------------

    def _load_candidate_profile(self) -> dict:
        profile_path = BASE_DIR / "output" / "candidate_profile.json"
        if profile_path.exists():
            with open(profile_path, "r", encoding="utf-8") as f:
                return json.load(f)
        # Fallback from settings
        return {
            "roles": self._candidate_cfg.get("roles", []),
            "experience_years": self._candidate_cfg.get("experience_years", 6),
            "skills_text": "",
        }

    @staticmethod
    def _parse_json_list(value) -> list:
        if not value:
            return []
        if isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except Exception:
            return []
