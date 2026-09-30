"""
NEXPLY - DATABASE v2.0
Upgraded schema with applications, resume_versions, and interactions tables.
Includes migration from v1 (jobs-only) schema.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jobs.db"


# ============================================================
# CONNECTION
# ============================================================

def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ============================================================
# SCHEMA SETUP & MIGRATION
# ============================================================

def initialize_database() -> None:
    """Create all tables if they don't exist. Safe to call repeatedly."""
    conn = get_connection()
    cur = conn.cursor()

    # ---- JOBS TABLE (extended from v1) ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_job_id TEXT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,

            location TEXT,
            location_codes TEXT,
            remote_type TEXT,
            timezone_restrictions TEXT,

            source TEXT,
            url TEXT UNIQUE,

            description TEXT,
            skills TEXT,

            employment_type TEXT,
            seniority TEXT,

            salary_min REAL,
            salary_max REAL,
            salary_currency TEXT,
            salary_period TEXT,

            published_at TEXT,
            expires_at TEXT,

            -- AI analysis results
            jd_required_skills TEXT,           -- JSON array
            jd_preferred_skills TEXT,          -- JSON array
            jd_role_type TEXT,
            jd_seniority TEXT,
            jd_work_mode TEXT,
            jd_location_format TEXT,           -- india|us|uk|eu|worldwide
            jd_summary TEXT,
            jd_analyzed_at TEXT,
            jd_provider TEXT,                  -- gemini|ollama|lmstudio

            -- Match scoring
            match_score REAL,
            ai_match_score REAL,               -- AI-powered score
            matched_skills TEXT,               -- JSON array
            missing_skills TEXT,               -- JSON array
            gap_analysis TEXT,
            recommendation TEXT,               -- strong_apply|apply|stretch|skip
            scored_at TEXT,

            -- Pipeline status
            status TEXT DEFAULT 'NEW',
            -- NEW → ANALYZED → MATCHED → TAILORED → QUEUED → APPLIED
            -- → INTERVIEW_SCREEN → INTERVIEW_TECH → OFFER → ACCEPTED
            -- → REJECTED → GHOSTED → WITHDRAWN

            -- Resume
            resume_version TEXT,
            resume_path TEXT,
            ats_score REAL,
            resume_generated_at TEXT,

            -- Application
            application_date TEXT,
            interview_status TEXT,

            -- Tracking
            follow_up_due TEXT,
            notes TEXT,

            -- Visa / Location filter metadata
            visa_sponsoring INTEGER DEFAULT 0,      -- 1 if job sponsors a visa
            detected_visa_country TEXT DEFAULT '',  -- e.g. 'UK', 'Singapore', 'USA (H1B)'

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---- APPLICATIONS TABLE ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id),

            applied_at TEXT,
            platform TEXT,                     -- himalayas|linkedin|naukri|wellfound|email
            resume_path TEXT,
            cover_letter_path TEXT,
            ats_score REAL,

            -- Submission details
            submission_method TEXT,            -- browser_auto|browser_manual|email|api
            form_data TEXT,                    -- JSON: what was entered in the form
            confirmation_id TEXT,              -- Application reference number if given

            -- Outcome
            status TEXT DEFAULT 'SUBMITTED',   -- SUBMITTED|VIEWED|REJECTED|INTERVIEW|OFFER|WITHDRAWN
            response_received_at TEXT,
            follow_up_sent_at TEXT,
            follow_up_due TEXT,

            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---- RESUME VERSIONS TABLE ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resume_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id),

            version_tag TEXT,                  -- e.g. "genai_acme_2026-09-23"
            file_path TEXT,                    -- .docx path
            pdf_path TEXT,                     -- .pdf path
            template TEXT,                     -- india|us|uk|eu

            ats_score REAL,
            keyword_density REAL,
            warnings TEXT,                     -- JSON array of ATS warnings

            provider TEXT,                     -- AI provider used
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---- INTERACTIONS TABLE ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id),
            application_id INTEGER REFERENCES applications(id),

            type TEXT,                         -- email_received|call_scheduled|interview|offer|rejection
            direction TEXT,                    -- inbound|outbound
            channel TEXT,                      -- email|phone|linkedin|portal
            summary TEXT,
            details TEXT,

            occurred_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---- Run migration first (adds missing columns to pre-existing tables) ----
    conn.commit()
    conn.close()
    migrate_v1_to_v2()

    # Re-open for indexes and triggers
    conn = get_connection()
    cur = conn.cursor()

    # ---- INDEXES (created after migration so columns exist) ----
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id)")

    # ai_match_score index (safe — column now exists after migration)
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(ai_match_score DESC)")
    except Exception:
        pass  # Column doesn't exist yet — safe to skip

    # ---- TRIGGER: auto-update updated_at ----
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS jobs_updated_at
        AFTER UPDATE ON jobs
        BEGIN
            UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END
    """)

    conn.commit()
    conn.close()


def migrate_v1_to_v2() -> None:
    """Add new v2 columns to an existing v1 database without data loss."""
    conn = get_connection()
    cur = conn.cursor()

    # Get existing columns
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row["name"] for row in cur.fetchall()}

    new_columns = [
        ("jd_required_skills", "TEXT"),
        ("jd_preferred_skills", "TEXT"),
        ("jd_role_type", "TEXT"),
        ("jd_seniority", "TEXT"),
        ("jd_work_mode", "TEXT"),
        ("jd_location_format", "TEXT"),
        ("jd_summary", "TEXT"),
        ("jd_analyzed_at", "TEXT"),
        ("jd_provider", "TEXT"),
        ("ai_match_score", "REAL"),
        ("matched_skills", "TEXT"),
        ("missing_skills", "TEXT"),
        ("gap_analysis", "TEXT"),
        ("recommendation", "TEXT"),
        ("scored_at", "TEXT"),
        ("resume_path", "TEXT"),
        ("ats_score", "REAL"),
        ("resume_generated_at", "TEXT"),
        ("follow_up_due", "TEXT"),
        # Visa / location filter columns (v3)
        ("visa_sponsoring", "INTEGER DEFAULT 0"),
        ("detected_visa_country", "TEXT DEFAULT ''"),
    ]

    added = []
    for col_name, col_type in new_columns:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
            added.append(col_name)

    conn.commit()
    conn.close()

    if added:
        print(f"Migration complete. Added columns: {added}")
    else:
        print("Database already up to date.")


# ============================================================
# JOBS CRUD
# ============================================================

def add_job(
    title: str,
    company: str,
    location: str = "",
    location_codes: str = "",
    remote_type: str = "",
    timezone_restrictions: str = "",
    source: str = "",
    url: str = "",
    description: str = "",
    skills: str = "",
    source_job_id: str = "",
    employment_type: str = "",
    seniority: str = "",
    salary_min: Optional[float] = None,
    salary_max: Optional[float] = None,
    salary_currency: str = "",
    salary_period: str = "",
    published_at: str = "",
    expires_at: str = "",
    visa_sponsoring: bool = False,
    detected_visa_country: str = "",
) -> bool:
    """Insert a new job. Returns True if inserted, False if duplicate."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO jobs (
            source_job_id, title, company, location, location_codes,
            remote_type, timezone_restrictions, source, url, description,
            skills, employment_type, seniority, salary_min, salary_max,
            salary_currency, salary_period, published_at, expires_at,
            visa_sponsoring, detected_visa_country
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_job_id, title, company, location, location_codes,
        remote_type, timezone_restrictions, source, url, description,
        skills, employment_type, seniority, salary_min, salary_max,
        salary_currency, salary_period, published_at, expires_at,
        1 if visa_sponsoring else 0, detected_visa_country,
    ))

    inserted = cur.rowcount == 1
    conn.commit()
    conn.close()
    return inserted


def update_job_analysis(
    job_id: int,
    required_skills: list,
    preferred_skills: list,
    role_type: str,
    seniority: str,
    work_mode: str,
    location_format: str,
    summary: str,
    provider: str,
) -> None:
    """Save AI JD analysis results back to the job record."""
    import json as _json
    conn = get_connection()
    conn.execute("""
        UPDATE jobs SET
            jd_required_skills = ?,
            jd_preferred_skills = ?,
            jd_role_type = ?,
            jd_seniority = ?,
            jd_work_mode = ?,
            jd_location_format = ?,
            jd_summary = ?,
            jd_analyzed_at = ?,
            jd_provider = ?,
            status = CASE WHEN status = 'NEW' THEN 'ANALYZED' ELSE status END
        WHERE id = ?
    """, (
        _json.dumps(required_skills),
        _json.dumps(preferred_skills),
        role_type, seniority, work_mode, location_format, summary,
        datetime.now().isoformat(),
        provider, job_id,
    ))
    conn.commit()
    conn.close()


def update_job_match(
    job_id: int,
    ai_score: float,
    matched_skills: list,
    missing_skills: list,
    gap_analysis: str,
    recommendation: str,
) -> None:
    """Save AI match scoring results."""
    import json as _json
    conn = get_connection()
    conn.execute("""
        UPDATE jobs SET
            ai_match_score = ?,
            matched_skills = ?,
            missing_skills = ?,
            gap_analysis = ?,
            recommendation = ?,
            scored_at = ?,
            status = CASE
                WHEN ? >= 70 AND status = 'ANALYZED' THEN 'MATCHED'
                ELSE status
            END
        WHERE id = ?
    """, (
        ai_score,
        _json.dumps(matched_skills),
        _json.dumps(missing_skills),
        gap_analysis, recommendation,
        datetime.now().isoformat(),
        ai_score, job_id,
    ))
    conn.commit()
    conn.close()


def update_job_status(job_id: int, status: str, notes: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status = ?, notes = ? WHERE id = ?",
        (status, notes, job_id)
    )
    conn.commit()
    conn.close()


def get_jobs_by_status(status: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status = ? ORDER BY ai_match_score DESC",
        (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_top_matches(min_score: float = 70, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM jobs
        WHERE ai_match_score >= ? AND status IN ('MATCHED', 'ANALYZED')
        ORDER BY ai_match_score DESC
        LIMIT ?
    """, (min_score, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pipeline_stats() -> dict:
    """Return counts for each status in the pipeline."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
    ).fetchall()
    conn.close()
    return {row["status"]: row["count"] for row in rows}


def add_application(
    job_id: int,
    platform: str,
    resume_path: str,
    cover_letter_path: str = "",
    ats_score: float = 0.0,
    submission_method: str = "browser_auto",
    form_data: dict | None = None,
    confirmation_id: str = "",
) -> int:
    """Record a job application. Returns the new application ID."""
    import json as _json
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications (
            job_id, applied_at, platform, resume_path, cover_letter_path,
            ats_score, submission_method, form_data, confirmation_id,
            follow_up_due
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now', '+7 days'))
    """, (
        job_id,
        datetime.now().isoformat(),
        platform, resume_path, cover_letter_path,
        ats_score, submission_method,
        _json.dumps(form_data or {}),
        confirmation_id,
    ))

    app_id = cur.lastrowid
    # Update the job status to APPLIED
    cur.execute(
        "UPDATE jobs SET status = 'APPLIED', application_date = ? WHERE id = ?",
        (datetime.now().isoformat(), job_id)
    )
    conn.commit()
    conn.close()
    return app_id


def get_follow_up_queue() -> list[dict]:
    """Jobs applied 7+ days ago with no response."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT j.id, j.title, j.company, j.url, a.applied_at, a.follow_up_due
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE a.status = 'SUBMITTED'
          AND date(a.follow_up_due) <= date('now')
        ORDER BY a.follow_up_due ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_count() -> int:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    return count


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    initialize_database()
    migrate_v1_to_v2()

    print("=" * 50)
    print("NEXPLY — DATABASE v2.0")
    print("=" * 50)
    print(f"Database : {DB_PATH}")
    print(f"Total jobs: {get_job_count()}")

    stats = get_pipeline_stats()
    for status, count in sorted(stats.items()):
        print(f"  {status:<20} {count}")
    print("=" * 50)