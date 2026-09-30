"""
RAJESH AI - Pipeline Tracker
Manages job pipeline status transitions and follow-up scheduling.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Pipeline stages in order
PIPELINE_STAGES = [
    "NEW",
    "ANALYZED",
    "MATCHED",
    "TAILORED",
    "QUEUED",
    "APPLIED",
    "INTERVIEW_SCREEN",
    "INTERVIEW_TECH",
    "OFFER",
    "ACCEPTED",
]

TERMINAL_STATES = {"REJECTED", "GHOSTED", "WITHDRAWN"}
ALL_STATES = set(PIPELINE_STAGES) | TERMINAL_STATES


class PipelineTracker:
    """Manages job status transitions and application tracking."""

    def advance(self, job_id: int, to_status: str, notes: str = "") -> None:
        """Move a job to a new pipeline stage."""
        if to_status not in ALL_STATES:
            raise ValueError(
                f"Invalid status '{to_status}'. "
                f"Valid: {sorted(ALL_STATES)}"
            )
        from agent.database import update_job_status
        update_job_status(job_id, to_status, notes)
        logger.info(f"Job {job_id} → {to_status}")

    def mark_applied(
        self,
        job_id: int,
        platform: str,
        resume_path: str,
        ats_score: float = 0.0,
        cover_letter_path: str = "",
        confirmation_id: str = "",
    ) -> int:
        """Record a successful application. Returns application ID."""
        from agent.database import add_application
        app_id = add_application(
            job_id=job_id,
            platform=platform,
            resume_path=resume_path,
            cover_letter_path=cover_letter_path,
            ats_score=ats_score,
            confirmation_id=confirmation_id,
        )
        logger.info(f"Application recorded: job {job_id}, platform {platform}, app_id {app_id}")
        return app_id

    def schedule_follow_up(self, job_id: int, days: int = 7) -> None:
        """Schedule a follow-up for a job."""
        import sqlite3
        from agent.database import get_connection
        due = (datetime.now() + timedelta(days=days)).date().isoformat()
        conn = get_connection()
        conn.execute(
            "UPDATE jobs SET follow_up_due = ? WHERE id = ?",
            (due, job_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"Follow-up scheduled for job {job_id} on {due}")

    def get_follow_ups_due(self) -> list[dict]:
        """Return jobs that need follow-up today."""
        from agent.database import get_follow_up_queue
        return get_follow_up_queue()

    def get_stats(self) -> dict:
        """Return pipeline stage counts."""
        from agent.database import get_pipeline_stats
        return get_pipeline_stats()

    def export_to_csv(self, output_path: Path) -> None:
        """Export full pipeline to CSV for external tracking."""
        from agent.database import get_connection
        conn = get_connection()
        rows = conn.execute("""
            SELECT
                j.id, j.title, j.company, j.location, j.source, j.url,
                j.ai_match_score, j.recommendation, j.status,
                j.resume_path, j.ats_score,
                j.application_date, j.follow_up_due, j.notes,
                j.jd_required_skills, j.missing_skills,
                j.created_at, j.updated_at
            FROM jobs j
            ORDER BY j.ai_match_score DESC NULLS LAST
        """).fetchall()
        conn.close()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "id", "title", "company", "location", "source", "url",
                "ai_match_score", "recommendation", "status",
                "resume_path", "ats_score",
                "application_date", "follow_up_due", "notes",
                "jd_required_skills", "missing_skills",
                "created_at", "updated_at",
            ])
            writer.writeheader()
            writer.writerows([dict(r) for r in rows])

        logger.info(f"Pipeline exported to {output_path} ({len(rows)} jobs)")
        print(f"✅ Exported {len(rows)} jobs → {output_path}")
