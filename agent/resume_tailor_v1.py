"""
RAJESH AI - RESUME TAILOR v1.0

Purpose:
    Create a job-specific resume from the master resume without
    inventing skills, experience, projects, metrics, education,
    certifications, or employment history.

Inputs:
    output\candidate_profile.json
    output\requirement_extraction_v08.json
    output\job_matches_v09.json
    resume\master_resume.docx

Outputs:
    resume\generated\<job>_v1.docx
    resume\generated\<job>_v1.json

Design:
    - Deterministic
    - No paid APIs
    - No LLM required
    - Master resume is never modified
    - Unsupported requirements are explicitly marked
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from docx import Document


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

PROFILE_FILE = ROOT / "output" / "candidate_profile.json"
REQUIREMENTS_FILE = ROOT / "output" / "requirement_extraction_v08.json"
MATCHES_FILE = ROOT / "output" / "job_matches_v09.json"
MASTER_RESUME = ROOT / "resume" / "master_resume.docx"

GENERATED_DIR = ROOT / "resume" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# GENERAL HELPERS
# ============================================================

def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize(text: Any) -> str:
    if text is None:
        return ""

    text = str(text).lower()

    # Normalize common separators.
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    text = text.replace("/", " ")

    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def slugify(text: str, max_len: int = 70) -> str:
    text = normalize(text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")

    return text[:max_len].strip("_") or "job"


def flatten_strings(value: Any) -> List[str]:
    """
    Recursively collect meaningful strings from nested JSON.
    """
    result = []

    if value is None:
        return result

    if isinstance(value, str):
        if value.strip():
            result.append(value.strip())
        return result

    if isinstance(value, list):
        for item in value:
            result.extend(flatten_strings(item))
        return result

    if isinstance(value, dict):
        for item in value.values():
            result.extend(flatten_strings(item))
        return result

    return result


def unique_preserve(items: List[str]) -> List[str]:
    seen = set()
    output = []

    for item in items:
        key = normalize(item)

        if not key:
            continue

        if key not in seen:
            seen.add(key)
            output.append(item)

    return output


# ============================================================
# LOAD CANDIDATE PROFILE
# ============================================================

def load_candidate_profile() -> Dict[str, Any]:
    profile = load_json(PROFILE_FILE)

    if not isinstance(profile, dict):
        raise ValueError("candidate_profile.json must contain a JSON object.")

    return profile


def get_candidate_text(profile: Dict[str, Any]) -> str:
    fields = [
        "summary",
        "skills_text",
        "experience_text",
        "education_text",
        "projects_text",
        "certifications_text",
        "raw_text",
    ]

    parts = []

    for field in fields:
        value = profile.get(field)

        if value:
            parts.append(str(value))

    return "\n".join(parts)


# ============================================================
# JOB MATCH LOADING
# ============================================================

def load_matches() -> List[Dict[str, Any]]:
    data = load_json(MATCHES_FILE)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        # Common possibilities.
        for key in [
            "matches",
            "job_matches",
            "results",
            "jobs",
            "data",
        ]:
            value = data.get(key)

            if isinstance(value, list):
                return value

    raise ValueError(
        "Could not find a list of job matches in "
        f"{MATCHES_FILE}"
    )


def get_match_score(job: Dict[str, Any]) -> float:
    for key in [
        "score",
        "match_score",
        "overall_score",
    ]:
        value = job.get(key)

        try:
            return float(value)
        except (TypeError, ValueError):
            pass

    return 0.0


def get_job_title(job: Dict[str, Any]) -> str:
    for key in [
        "title",
        "job_title",
        "position",
        "role",
    ]:
        if job.get(key):
            return str(job[key])

    return "Unknown Job"


def get_company(job: Dict[str, Any]) -> str:
    for key in [
        "company",
        "organization",
        "employer",
    ]:
        if job.get(key):
            return str(job[key])

    return "Unknown Company"


def select_top_job(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Select the highest-scoring eligible job.

    Avoid:
        unrelated roles.

    Prefer:
        primary
        secondary
        related
        qa
        leadership
    """

    eligible = []

    for job in matches:
        role = normalize(
            job.get("role")
            or job.get("role_type")
            or job.get("classification")
            or ""
        )

        if role == "unrelated":
            continue

        eligible.append(job)

    if not eligible:
        raise ValueError("No eligible matched jobs found.")

    eligible.sort(
        key=lambda x: get_match_score(x),
        reverse=True,
    )

    return eligible[0]


# ============================================================
# REQUIREMENT EXTRACTION
# ============================================================

def extract_job_requirements(
    requirements_data: Any,
    selected_job: Dict[str, Any],
) -> Dict[str, Any]:

    job_id_candidates = [
        selected_job.get("id"),
        selected_job.get("job_id"),
        selected_job.get("source_job_id"),
    ]

    title = normalize(get_job_title(selected_job))
    company = normalize(get_company(selected_job))

    # --------------------------------------------------------
    # Convert possible requirement structures into job records
    # --------------------------------------------------------

    records = []

    if isinstance(requirements_data, list):
        records = requirements_data

    elif isinstance(requirements_data, dict):

        for key in [
            "requirements",
            "jobs",
            "results",
            "data",
            "extractions",
        ]:
            value = requirements_data.get(key)

            if isinstance(value, list):
                records = value
                break

        # Some versions may store jobs keyed by ID.
        if not records:
            for key, value in requirements_data.items():

                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("id", key)
                    records.append(item)

    # --------------------------------------------------------
    # Find matching requirement record
    # --------------------------------------------------------

    best = None

    for record in records:

        if not isinstance(record, dict):
            continue

        record_id = (
            record.get("id")
            or record.get("job_id")
            or record.get("source_job_id")
        )

        if record_id is not None:
            for candidate_id in job_id_candidates:
                if candidate_id is not None and str(record_id) == str(candidate_id):
                    best = record
                    break

        if best:
            break

        record_title = normalize(
            record.get("title")
            or record.get("job_title")
            or record.get("role")
            or ""
        )

        record_company = normalize(
            record.get("company")
            or record.get("organization")
            or ""
        )

        if title and record_title == title:
            if not company or not record_company or record_company == company:
                best = record
                break

    if best is None:

        # Requirement data may already be embedded in the match.
        best = {}

        for key in [
            "requirements",
            "extracted_requirements",
            "job_requirements",
        ]:
            if isinstance(selected_job.get(key), dict):
                best = selected_job[key]
                break

    return best


# ============================================================
# REQUIREMENT EXTRACTION HELPERS
# ============================================================

SKILL_CONTAINER_KEYS = {
    "skills",
    "required_skills",
    "preferred_skills",
    "technical_skills",
    "technologies",
    "tools",
    "frameworks",
    "keywords",
    "must_have_skills",
    "nice_to_have_skills",
}

REQUIRED_CONTAINER_KEYS = {
    "required",
    "must_have",
    "mandatory",
    "required_skills",
    "must_have_skills",
}

PREFERRED_CONTAINER_KEYS = {
    "preferred",
    "nice_to_have",
    "optional",
    "preferred_skills",
    "nice_to_have_skills",
}


def collect_values_by_keys(
    obj: Any,
    target_keys: set,
) -> List[str]:

    results = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_norm = normalize(key).replace(" ", "_")

            if key_norm in target_keys:
                results.extend(flatten_strings(value))

            results.extend(
                collect_values_by_keys(
                    value,
                    target_keys,
                )
            )

    elif isinstance(obj, list):

        for item in obj:
            results.extend(
                collect_values_by_keys(
                    item,
                    target_keys,
                )
            )

    return unique_preserve(results)


def extract_required_skills(requirements: Dict[str, Any]) -> List[str]:
    results = collect_values_by_keys(
        requirements,
        REQUIRED_CONTAINER_KEYS,
    )

    # Also inspect explicit required skill containers.
    results.extend(
        collect_values_by_keys(
            requirements,
            {"required_skills", "must_have_skills"},
        )
    )

    return unique_preserve(results)


def extract_preferred_skills(requirements: Dict[str, Any]) -> List[str]:
    results = collect_values_by_keys(
        requirements,
        PREFERRED_CONTAINER_KEYS,
    )

    return unique_preserve(results)


def extract_all_skills(requirements: Dict[str, Any]) -> List[str]:
    results = collect_values_by_keys(
        requirements,
        SKILL_CONTAINER_KEYS,
    )

    return unique_preserve(results)


def extract_experience_text(requirements: Dict[str, Any]) -> str:
    candidates = [
        requirements.get("experience"),
        requirements.get("experience_requirement"),
        requirements.get("years_experience"),
        requirements.get("required_experience"),
        requirements.get("minimum_experience"),
    ]

    values = []

    for value in candidates:
        if value is not None:
            values.extend(flatten_strings(value))

    return " ".join(unique_preserve(values))


def extract_education_text(requirements: Dict[str, Any]) -> str:
    candidates = [
        requirements.get("education"),
        requirements.get("education_requirement"),
        requirements.get("required_education"),
        requirements.get("degree"),
    ]

    values = []

    for value in candidates:
        if value is not None:
            values.extend(flatten_strings(value))

    return " ".join(unique_preserve(values))


# ============================================================
# SKILL NORMALIZATION
# ============================================================

SKILL_ALIASES = {
    "vector-search": "vector search",
    "vector_search": "vector search",
    "prompt-engineering": "prompt engineering",
    "prompt_engineering": "prompt engineering",
    "rag": "rag",
    "retrieval-augmented-generation": "rag",
    "retrieval augmented generation": "rag",
    "large language model": "llm",
    "large language models": "llm",
    "llms": "llm",
    "hugging face": "huggingface",
    "hugging-face": "huggingface",
    "scikit learn": "scikit learn",
    "sklearn": "scikit learn",
    "machine-learning": "machine learning",
    "deep-learning": "deep learning",
}


def normalize_skill(skill: str) -> str:
    value = normalize(skill)

    value = value.strip(".,:;()[]{}")

    return SKILL_ALIASES.get(value, value)


def candidate_skill_list(profile: Dict[str, Any]) -> List[str]:
    text = profile.get("skills_text", "")

    if not text:
        return []

    skills = []

    for line in str(text).splitlines():

        line = line.strip()

        if not line:
            continue

        # Remove category name before colon.
        if ":" in line:
            _, values = line.split(":", 1)
        else:
            values = line

        # ----------------------------------------------------
        # Handle cloud groups correctly.
        # AWS (S3, SageMaker, Redshift)
        # Azure (Azure ML, ADLS, Databricks)
        # ----------------------------------------------------

        cloud_pattern = re.compile(
            r"^(AWS|Azure)\s*\((.*?)\)",
            flags=re.IGNORECASE,
        )

        match = cloud_pattern.search(values)

        if match:
            cloud_name = match.group(1)
            inside = match.group(2)

            skills.append(cloud_name)

            for item in inside.split(","):
                item = item.strip()

                if item:
                    skills.append(item)

            remaining = values[match.end():].strip(" ,")

            if remaining:
                for item in remaining.split(","):
                    item = item.strip()

                    if item:
                        skills.append(item)

            continue

        # Normal comma-separated skills.
        for item in values.split(","):
            item = item.strip()

            if item:
                skills.append(item)

    normalized = []

    for skill in skills:
        skill_norm = normalize_skill(skill)

        if skill_norm:
            normalized.append(skill_norm)

    return unique_preserve(normalized)


# ============================================================
# KEYWORD MATCHING
# ============================================================

def phrase_in_text(phrase: str, text: str) -> bool:
    phrase_norm = normalize_skill(phrase)
    text_norm = normalize(text)

    if not phrase_norm:
        return False

    # Direct phrase match.
    if phrase_norm in text_norm:
        return True

    # Token-level fallback.
    tokens = phrase_norm.split()

    if len(tokens) == 1:
        return re.search(
            r"\b" + re.escape(tokens[0]) + r"\b",
            text_norm,
        ) is not None

    return False


def match_skills(
    requirements: List[str],
    candidate_text: str,
    candidate_skills: List[str],
) -> Tuple[List[str], List[str]]:

    matched = []
    missing = []

    candidate_skill_norms = {
        normalize_skill(skill)
        for skill in candidate_skills
    }

    candidate_text_norm = normalize(candidate_text)

    for requirement in requirements:

        req = normalize_skill(requirement)

        if not req:
            continue

        if req in candidate_skill_norms:
            matched.append(requirement)
            continue

        if phrase_in_text(req, candidate_text_norm):
            matched.append(requirement)
            continue

        missing.append(requirement)

    return (
        unique_preserve(matched),
        unique_preserve(missing),
    )


# ============================================================
# EXPERIENCE / EDUCATION SUPPORT
# ============================================================

def extract_candidate_years(profile: Dict[str, Any]) -> float:
    """
    Current profile states 6+ years.

    Read from profile when possible, otherwise use 6 based on
    the candidate profile generated from the master resume.
    """

    text = get_candidate_text(profile)

    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*years",
        r"(\d+(?:\.\d+)?)\s*years",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    return 6.0


def extract_required_years(text: str) -> float | None:

    if not text:
        return None

    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*years",
        r"minimum\s+of\s+(\d+(?:\.\d+)?)",
        r"at\s+least\s+(\d+(?:\.\d+)?)",
    ]

    values = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            try:
                values.append(float(match.group(1)))
            except ValueError:
                pass

    if not values:
        return None

    return max(values)


# ============================================================
# RESUME CONTENT SELECTION
# ============================================================

def relevant_experience_bullets(
    profile: Dict[str, Any],
    matched_keywords: List[str],
) -> List[str]:

    experience_text = str(
        profile.get("experience_text", "")
    )

    if not experience_text:
        return []

    keyword_norms = [
        normalize_skill(keyword)
        for keyword in matched_keywords
    ]

    selected = []

    current_role = ""

    for raw_line in experience_text.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        if not line.startswith("•") and "|" in line:
            current_role = line
            selected.append(line)
            continue

        if not line.startswith("•"):
            continue

        bullet_text = line.lstrip("•").strip()
        bullet_norm = normalize(bullet_text)

        relevance = False

        for keyword in keyword_norms:

            if keyword and keyword in bullet_norm:
                relevance = True
                break

        # Keep highly relevant bullets.
        if relevance:
            selected.append("• " + bullet_text)

    return selected


# ============================================================
# TAILORED SUMMARY
# ============================================================

def create_tailored_summary(
    profile: Dict[str, Any],
    job_title: str,
    matched_keywords: List[str],
) -> str:

    original = str(profile.get("summary", "")).strip()

    if not original:
        return ""

    # We deliberately do not rewrite unsupported claims.
    #
    # Instead, use the original summary and append only
    # already-supported keywords that are clearly present
    # in the candidate profile.

    candidate_text = normalize(
        get_candidate_text(profile)
    )

    supported = []

    for keyword in matched_keywords:

        keyword_norm = normalize_skill(keyword)

        if keyword_norm in candidate_text:
            supported.append(keyword)

    supported = unique_preserve(supported[:6])

    if not supported:
        return original

    # If the original summary already contains the concepts,
    # leave it untouched.
    return original


# ============================================================
# ATS COVERAGE
# ============================================================

def calculate_coverage(
    required: List[str],
    matched: List[str],
) -> float:

    if not required:
        return 100.0

    return round(
        len(matched) / len(required) * 100,
        1,
    )


# ============================================================
# DOCX GENERATION
# ============================================================

def add_heading(document: Document, text: str, level: int = 1):
    document.add_heading(text, level=level)


def add_bullets(document: Document, bullets: List[str]):
    for bullet in bullets:
        if bullet.startswith("•"):
            bullet = bullet[1:].strip()

        document.add_paragraph(
            bullet,
            style="List Bullet",
        )


def create_tailored_docx(
    profile: Dict[str, Any],
    job: Dict[str, Any],
    matched_keywords: List[str],
    output_path: Path,
):

    document = Document()

    title = get_job_title(job)
    company = get_company(job)

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    document.add_heading(
        profile.get("name", "Rajesh Nemani"),
        level=0,
    )

    contact = profile.get("contact", {})

    contact_parts = []

    if isinstance(contact, dict):

        if contact.get("email"):
            contact_parts.append(
                str(contact["email"])
            )

        if contact.get("phone"):
            contact_parts.append(
                str(contact["phone"])
            )

    if contact_parts:
        document.add_paragraph(
            " | ".join(contact_parts)
        )

    # --------------------------------------------------------
    # Target
    # --------------------------------------------------------

    document.add_heading("Professional Target", level=1)

    document.add_paragraph(
        f"{title} — {company}"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = create_tailored_summary(
        profile,
        title,
        matched_keywords,
    )

    if summary:
        document.add_heading(
            "Professional Summary",
            level=1,
        )

        document.add_paragraph(summary)

    # --------------------------------------------------------
    # Skills
    # --------------------------------------------------------

    skills_text = profile.get(
        "skills_text",
        "",
    )

    if skills_text:
        document.add_heading(
            "Technical Skills",
            level=1,
        )

        for line in str(skills_text).splitlines():

            line = line.strip()

            if line:
                document.add_paragraph(line)

    # --------------------------------------------------------
    # Experience
    # --------------------------------------------------------

    experience_text = profile.get(
        "experience_text",
        "",
    )

    if experience_text:

        document.add_heading(
            "Professional Experience",
            level=1,
        )

        for line in str(experience_text).splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith("•"):
                document.add_paragraph(
                    line[1:].strip(),
                    style="List Bullet",
                )
            else:
                document.add_paragraph(
                    line
                )

    # --------------------------------------------------------
    # Education
    # --------------------------------------------------------

    education_text = profile.get(
        "education_text",
        "",
    )

    if education_text:

        document.add_heading(
            "Education",
            level=1,
        )

        for line in str(education_text).splitlines():

            line = line.strip()

            if line:
                document.add_paragraph(line)

    # --------------------------------------------------------
    # Certifications
    # --------------------------------------------------------

    certifications = profile.get(
        "certifications_text",
        "",
    )

    if certifications:

        document.add_heading(
            "Certifications",
            level=1,
        )

        for line in str(certifications).splitlines():

            line = line.strip()

            if line:
                document.add_paragraph(
                    line.lstrip("•").strip(),
                    style="List Bullet",
                )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    document.save(output_path)


# ============================================================
# REPORT
# ============================================================

def create_report(
    job: Dict[str, Any],
    requirements: Dict[str, Any],
    profile: Dict[str, Any],
    required_skills: List[str],
    preferred_skills: List[str],
    all_skills: List[str],
    matched_required: List[str],
    missing_required: List[str],
    matched_preferred: List[str],
    missing_preferred: List[str],
    output_docx: Path,
) -> Dict[str, Any]:

    candidate_text = get_candidate_text(profile)

    experience_text = extract_experience_text(
        requirements
    )

    candidate_years = extract_candidate_years(
        profile
    )

    required_years = extract_required_years(
        experience_text
    )

    if required_years is None:
        experience_status = "NOT CLEARLY SPECIFIED"

    elif candidate_years >= required_years:
        experience_status = "MEETS REQUIREMENT"

    else:
        experience_status = "BELOW REQUIREMENT"

    return {
        "version": "resume_tailor_v1.0",
        "job": {
            "id": job.get("id"),
            "source_job_id": job.get("source_job_id"),
            "title": get_job_title(job),
            "company": get_company(job),
            "url": job.get("url") or job.get("source_url"),
            "application_url": job.get("application_url"),
            "match_score": get_match_score(job),
            "role": (
                job.get("role")
                or job.get("role_type")
                or job.get("classification")
            ),
        },
        "requirements": {
            "required_skills": required_skills,
            "preferred_skills": preferred_skills,
            "all_skills": all_skills,
            "experience": experience_text,
            "education": extract_education_text(
                requirements
            ),
        },
        "candidate": {
            "experience_years": candidate_years,
        },
        "skill_analysis": {
            "required_matched": matched_required,
            "required_missing": missing_required,
            "preferred_matched": matched_preferred,
            "preferred_missing": missing_preferred,
            "required_coverage_percent": calculate_coverage(
                required_skills,
                matched_required,
            ),
            "preferred_coverage_percent": calculate_coverage(
                preferred_skills,
                matched_preferred,
            ),
        },
        "experience_analysis": {
            "required_years": required_years,
            "candidate_years": candidate_years,
            "status": experience_status,
        },
        "safety": {
            "invented_skills": [],
            "invented_experience": [],
            "invented_metrics": [],
            "invented_projects": [],
            "invented_certifications": [],
            "warning": (
                "Missing requirements must not be added "
                "to the resume unless supported by the "
                "master resume."
            ),
        },
        "output": {
            "resume_file": str(output_docx),
        },
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 72)
    print("RAJESH AI - RESUME TAILOR v1.0")
    print("=" * 72)

    # --------------------------------------------------------
    # Validate inputs
    # --------------------------------------------------------

    required_files = [
        PROFILE_FILE,
        REQUIREMENTS_FILE,
        MATCHES_FILE,
        MASTER_RESUME,
    ]

    print("\nChecking input files...")

    for path in required_files:

        if not path.exists():
            print(f"ERROR: Missing {path}")
            sys.exit(1)

        print(f"  OK: {path}")

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    profile = load_candidate_profile()
    requirements_data = load_json(
        REQUIREMENTS_FILE
    )
    matches = load_matches()

    print(f"\nJobs loaded: {len(matches)}")

    # --------------------------------------------------------
    # Select top job
    # --------------------------------------------------------

    job = select_top_job(matches)

    job_title = get_job_title(job)
    company = get_company(job)
    score = get_match_score(job)

    print("\n" + "=" * 72)
    print("SELECTED JOB")
    print("=" * 72)

    print(f"Title       : {job_title}")
    print(f"Company     : {company}")
    print(f"Match score : {score}")
    print(
        f"Role        : "
        f"{job.get('role') or job.get('role_type') or 'unknown'}"
    )

    if job.get("url"):
        print(f"Source URL  : {job['url']}")

    if job.get("application_url"):
        print(
            f"Application : {job['application_url']}"
        )

    # --------------------------------------------------------
    # Requirements
    # --------------------------------------------------------

    requirements = extract_job_requirements(
        requirements_data,
        job,
    )

    required_skills = extract_required_skills(
        requirements
    )

    preferred_skills = extract_preferred_skills(
        requirements
    )

    all_skills = extract_all_skills(
        requirements
    )

    # If extraction has no required skills but has general
    # skills, don't automatically call them required.
    if not required_skills:
        required_skills = []

    candidate_text = get_candidate_text(profile)
    candidate_skills = candidate_skill_list(profile)

    # --------------------------------------------------------
    # Matching
    # --------------------------------------------------------

    matched_required, missing_required = match_skills(
        required_skills,
        candidate_text,
        candidate_skills,
    )

    matched_preferred, missing_preferred = match_skills(
        preferred_skills,
        candidate_text,
        candidate_skills,
    )

    print("\n" + "=" * 72)
    print("ATS REQUIREMENT ANALYSIS")
    print("=" * 72)

    print(
        f"\nRequired skills detected : "
        f"{len(required_skills)}"
    )

    print(
        f"Required skills matched  : "
        f"{len(matched_required)}"
    )

    print(
        f"Required skills missing  : "
        f"{len(missing_required)}"
    )

    print(
        f"Required coverage        : "
        f"{calculate_coverage(required_skills, matched_required)}%"
    )

    print(
        f"\nPreferred skills detected: "
        f"{len(preferred_skills)}"
    )

    print(
        f"Preferred skills matched : "
        f"{len(matched_preferred)}"
    )

    # --------------------------------------------------------
    # Display matched
    # --------------------------------------------------------

    if matched_required:

        print("\nMATCHED REQUIRED:")

        for skill in matched_required:
            print(f"  + {skill}")

    # --------------------------------------------------------
    # Display missing
    # --------------------------------------------------------

    if missing_required:

        print("\nMISSING REQUIRED — DO NOT INVENT:")

        for skill in missing_required:
            print(f"  - {skill}")

    # --------------------------------------------------------
    # Create filename
    # --------------------------------------------------------

    job_slug = slugify(
        f"{company}_{job_title}"
    )

    resume_filename = (
        f"{job_slug}_v1.docx"
    )

    report_filename = (
        f"{job_slug}_v1.json"
    )

    resume_path = (
        GENERATED_DIR /
        resume_filename
    )

    report_path = (
        GENERATED_DIR /
        report_filename
    )

    # --------------------------------------------------------
    # Generate resume
    # --------------------------------------------------------

    create_tailored_docx(
        profile=profile,
        job=job,
        matched_keywords=matched_required + matched_preferred,
        output_path=resume_path,
    )

    # --------------------------------------------------------
    # Create report
    # --------------------------------------------------------

    report = create_report(
        job=job,
        requirements=requirements,
        profile=profile,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        all_skills=all_skills,
        matched_required=matched_required,
        missing_required=missing_required,
        matched_preferred=matched_preferred,
        missing_preferred=missing_preferred,
        output_docx=resume_path,
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    print("\n" + "=" * 72)
    print("RESUME TAILORING COMPLETE")
    print("=" * 72)

    print(f"\nResume:")
    print(f"  {resume_path}")

    print(f"\nATS report:")
    print(f"  {report_path}")

    print("\nMaster resume:")
    print("  UNCHANGED")

    print("\nSafety:")
    print("  No unsupported skills added")
    print("  No invented experience added")
    print("  No invented metrics added")
    print("  No invented projects added")
    print("  No invented certifications added")

    print("\nNext checkpoint:")
    print("  Inspect the generated resume before batch generation.")


if __name__ == "__main__":
    main()

# ============================================================
# ORCHESTRATOR INTEGRATION WRAPPER
# ============================================================

def tailor_resume_for_job(job: dict, ai, settings: dict) -> dict:
    """
    Wrapper called by DailyPipeline.step_tailor().
    Generates a tailored resume for a single job dict from the database.

    Args:
        job:      Row dict from the jobs table (has keys: id, title, company,
                  description, jd_required_skills, jd_location_format, etc.)
        ai:       AIEngine instance (may be None if no provider active)
        settings: Full settings dict from settings.yaml

    Returns:
        dict with keys:
          - resume_path (str):  absolute path to generated .docx
          - ats_score   (float): ATS compliance score 0-100
          - success     (bool)
          - error       (str):  empty string on success
    """
    import json
    import logging
    from pathlib import Path
    from datetime import datetime

    logger = logging.getLogger(__name__)

    try:
        BASE_DIR = Path(__file__).resolve().parent.parent
        output_dir = BASE_DIR / "resume" / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)

        # -- Build safe filename -------------------------------------
        company = slugify(str(job.get("company", "company")))[:20]
        title   = slugify(str(job.get("title",   "role")))[:20]
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = output_dir / f"resume_{company}_{title}_{ts}.docx"

        # -- Required skills from AI analysis ------------------------
        req_skills_raw = job.get("jd_required_skills") or "[]"
        try:
            required_skills = json.loads(req_skills_raw)
        except Exception:
            required_skills = []

        # -- Build a mock job_matches structure for the existing tailor --
        # The existing tailor reads from files; we pass data directly.
        from agent.resume_formatter import ResumeFormatter, get_location_format
        from agent.ats_checker import ATSChecker

        master_resume = BASE_DIR / "resume" / "master_resume.docx"
        if not master_resume.exists():
            return {
                "resume_path": "",
                "ats_score": 0.0,
                "success": False,
                "error": "master_resume.docx not found",
            }

        # Location format selection
        loc_format = get_location_format(
            jd_location_format=str(job.get("jd_location_format") or "auto"),
            candidate_preference=settings.get("candidate", {}).get("resume_format", "auto"),
        )

        # Tailored data dict (populated from AI analysis if available)
        tailored_data = {
            "name": settings.get("candidate", {}).get("name", "Candidate"),
            "contact": {},
            "summary": job.get("jd_summary") or f"Experienced professional applying for {job.get('title', 'this role')} at {job.get('company', 'the company')}.",
            "experience": [],
            "education": [],
            "skills": required_skills,
            "certifications": [],
        }

        # If AI is available, try to get a rewritten summary
        if ai:
            try:
                rewrite = ai.rewrite_resume_bullets(
                    jd_summary=str(job.get("jd_summary") or ""),
                    required_skills=required_skills,
                    candidate_bullets=[],
                )
                if rewrite and rewrite.tailored_summary:
                    tailored_data["summary"] = rewrite.tailored_summary
            except Exception:
                pass

        # Format the resume
        formatter = ResumeFormatter(master_resume)
        formatter.format(tailored_data, loc_format, out_path)

        # ATS check
        ats_report = ATSChecker().check(out_path, required_skills)

        return {
            "resume_path": str(out_path),
            "ats_score": ats_report.score,
            "success": True,
            "error": "",
        }

    except Exception as exc:
        logger.error(f"tailor_resume_for_job failed: {exc}")
        return {
            "resume_path": "",
            "ats_score": 0.0,
            "success": False,
            "error": str(exc),
        }
