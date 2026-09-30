"""
NEXPLY - JOB HUNTER v2.0
Plugin-based job scraper supporting multiple sources.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import yaml
from rich.console import Console

from agent.database import add_job

console = Console()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class JobHunter:
    """
    Orchestrates job scraping across all enabled sources.
    Each source is a plugin that implements BaseJobSource.
    """

    def __init__(self, settings: dict | None = None):
        if settings is None:
            cfg_path = BASE_DIR / "config" / "settings.yaml"
            with open(cfg_path, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f) or {}

        self._settings = settings
        self._sources_cfg = settings.get("sources", {})
        self._candidate_cfg = settings.get("candidate", {})
        self._roles = self._candidate_cfg.get("roles", ["GenAI Engineer"])
        self._locations = self._candidate_cfg.get("locations", ["Remote"])

    def _get_enabled_sources(self):
        """Dynamically load and return all enabled source plugins."""
        sources = []

        # ---- FREE PUBLIC APIs (no auth, worldwide remote) ----

        # Himalayas
        if self._sources_cfg.get("himalayas", {}).get("enabled", True):
            try:
                from agent.sources.himalayas_source import HimalayasSource
                sources.append(HimalayasSource(self._sources_cfg.get("himalayas", {})))
            except ImportError as e:
                logger.warning(f"Himalayas source unavailable: {e}")

        # RemoteOK
        if self._sources_cfg.get("remoteok", {}).get("enabled", True):
            try:
                from agent.sources.remoteok_source import RemoteOKSource
                sources.append(RemoteOKSource(self._sources_cfg.get("remoteok", {})))
            except ImportError as e:
                logger.warning(f"RemoteOK source unavailable: {e}")

        # Jobicy
        if self._sources_cfg.get("jobicy", {}).get("enabled", True):
            try:
                from agent.sources.jobicy_source import JobicySource
                sources.append(JobicySource(self._sources_cfg.get("jobicy", {})))
            except ImportError as e:
                logger.warning(f"Jobicy source unavailable: {e}")

        # Remotive
        if self._sources_cfg.get("remotive", {}).get("enabled", True):
            try:
                from agent.sources.remotive_source import RemotiveSource
                sources.append(RemotiveSource(self._sources_cfg.get("remotive", {})))
            except ImportError as e:
                logger.warning(f"Remotive source unavailable: {e}")

        # We Work Remotely
        if self._sources_cfg.get("weworkremotely", {}).get("enabled", True):
            try:
                from agent.sources.weworkremotely_source import WeWorkRemotelySource
                sources.append(WeWorkRemotelySource(self._sources_cfg.get("weworkremotely", {})))
            except ImportError as e:
                logger.warning(f"WeWorkRemotely source unavailable: {e}")

        # AI-Jobs.net
        if self._sources_cfg.get("aijobs", {}).get("enabled", True):
            try:
                from agent.sources.aijobs_source import AIJobsSource
                sources.append(AIJobsSource(self._sources_cfg.get("aijobs", {})))
            except ImportError as e:
                logger.warning(f"AI-Jobs source unavailable: {e}")

        # Remote First Jobs
        if self._sources_cfg.get("remotefirstjobs", {}).get("enabled", False):
            try:
                from agent.sources.remotefirstjobs_source import RemoteFirstJobsSource
                src = RemoteFirstJobsSource(self._sources_cfg.get("remotefirstjobs", {}))
                if src.is_available():
                    sources.append(src)
            except ImportError as e:
                logger.warning(f"RemoteFirstJobs source unavailable: {e}")

        # Visa-Sponsoring Jobs (new!)
        if self._sources_cfg.get("visa_jobs", {}).get("enabled", True):
            try:
                from agent.sources.visa_jobs_source import VisaJobsSource
                sources.append(VisaJobsSource(self._sources_cfg.get("visa_jobs", {})))
                console.print("  [cyan]🌍 Visa-sponsoring jobs source enabled (H1B, UK, EU, Canada)[/cyan]")
            except ImportError as e:
                logger.warning(f"Visa jobs source unavailable: {e}")

        # ---- AUTH-REQUIRED SOURCES ----

        # LinkedIn
        if self._sources_cfg.get("linkedin", {}).get("enabled", False):
            try:
                from agent.sources.linkedin_source import LinkedInSource
                src = LinkedInSource(self._sources_cfg.get("linkedin", {}))
                if src.is_available():
                    sources.append(src)
                else:
                    console.print("  [yellow]⚠ LinkedIn: set LINKEDIN_SESSION_COOKIE env var.[/yellow]")
            except ImportError as e:
                logger.warning(f"LinkedIn source unavailable: {e}")

        # Naukri
        if self._sources_cfg.get("naukri", {}).get("enabled", False):
            try:
                from agent.sources.naukri_source import NaukriSource
                sources.append(NaukriSource(self._sources_cfg.get("naukri", {})))
            except ImportError as e:
                logger.warning(f"Naukri source unavailable: {e}")

        # Wellfound
        if self._sources_cfg.get("wellfound", {}).get("enabled", False):
            try:
                from agent.sources.wellfound_source import WellfoundSource
                sources.append(WellfoundSource(self._sources_cfg.get("wellfound", {})))
            except ImportError as e:
                logger.warning(f"Wellfound source unavailable: {e}")

        return sources

    def run(self) -> int:
        """Fetch jobs from all enabled sources. Returns count of new jobs inserted."""
        sources = self._get_enabled_sources()

        if not sources:
            console.print("  [red]No job sources enabled! Check config/settings.yaml[/red]")
            return 0

        # --- Filter configuration ---
        from agent.job_filter import should_keep
        filter_cfg      = self._settings.get("filter", {})
        filter_enabled  = filter_cfg.get("foreign_without_sponsorship", True)
        home_country    = self._candidate_cfg.get("home_country", "India")

        total_new      = 0
        total_filtered = 0

        for source in sources:
            console.print(f"  🌐 Fetching from [bold]{source.name}[/bold]...")
            try:
                jobs = source.fetch(self._roles, self._locations)
                new_count      = 0
                filtered_count = 0

                for job in jobs:
                    # ── Location filter ──────────────────────────────────
                    keep, reason = should_keep(
                        title=job.title,
                        location=job.location,
                        remote_type=job.remote_type,
                        description=job.description,
                        source=job.source,
                        home_country=home_country,
                        enabled=filter_enabled,
                    )

                    if not keep:
                        filtered_count += 1
                        logger.debug(
                            f"[FILTERED] {job.title} @ {job.company} "
                            f"({job.location}) — {reason}"
                        )
                        continue

                    # Annotate visa data onto the job object
                    if "visa" in reason.lower() or "sponsored" in reason.lower():
                        job.visa_sponsoring = True
                        # Extract country from reason like "Foreign (UK) + Visa sponsored: UK"
                        import re as _re
                        m = _re.search(r"Visa sponsored:\s*(.+)$", reason)
                        job.detected_visa_country = m.group(1).strip() if m else ""

                    # ── Insert into DB ────────────────────────────────────
                    inserted = add_job(
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        location_codes=job.location_codes,
                        remote_type=job.remote_type,
                        timezone_restrictions=job.timezone_restrictions,
                        source=job.source,
                        url=job.url,
                        description=job.description,
                        skills=job.skills,
                        source_job_id=job.source_job_id,
                        employment_type=job.employment_type,
                        seniority=job.seniority,
                        salary_min=job.salary_min,
                        salary_max=job.salary_max,
                        salary_currency=job.salary_currency,
                        salary_period=job.salary_period,
                        published_at=job.published_at,
                        expires_at=job.expires_at,
                        visa_sponsoring=job.visa_sponsoring,
                        detected_visa_country=job.detected_visa_country,
                    )
                    if inserted:
                        new_count += 1

                total_filtered += filtered_count
                console.print(
                    f"    → {len(jobs)} fetched, "
                    f"[green]{new_count} new[/green] added, "
                    f"[yellow]{filtered_count} filtered[/yellow] "
                    f"(foreign, no sponsorship)"
                )
                total_new += new_count
                time.sleep(2)  # Polite delay between sources

            except Exception as e:
                logger.error(f"Source {source.name} failed: {e}")
                console.print(f"  [red]  ✗ {source.name} error: {e}[/red]")

        if filter_enabled and total_filtered:
            console.print(
                f"\n  [dim]🔍 Location filter: kept {total_new} jobs, "
                f"discarded {total_filtered} foreign jobs without visa sponsorship[/dim]"
            )

        return total_new


if __name__ == "__main__":
    import yaml
    cfg_path = BASE_DIR / "config" / "settings.yaml"
    with open(cfg_path) as f:
        settings = yaml.safe_load(f)

    hunter = JobHunter(settings)
    count = hunter.run()
    print(f"\nTotal new jobs: {count}")