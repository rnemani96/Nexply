import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime


BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "jobs.db"
OUTPUT_PATH = BASE / "output" / "requirement_extraction_v08.json"


# ---------------------------------------------------------
# Normalization
# ---------------------------------------------------------

ALIASES = {
    "generative ai": "genai",
    "generative-ai": "genai",
    "gen ai": "genai",
    "large language model": "llm",
    "large language models": "llm",
    "llms": "llm",
    "machine learning": "machine-learning",
    "deep learning": "deep-learning",
    "reinforcement learning": "reinforcement-learning",
    "computer vision": "computer-vision",
    "natural language processing": "nlp",
    "retrieval augmented generation": "rag",
    "retrieval-augmented generation": "rag",
    "retrieval augmented": "rag",
    "vector databases": "vector-db",
    "vector database": "vector-db",
    "vector search": "vector-search",
    "hugging face": "hugging-face",
    "huggingface": "hugging-face",
    "fine tuning": "fine-tuning",
    "fine-tuning": "fine-tuning",
    "prompt engineering": "prompt-engineering",
    "large-language-model": "llm",
    "aws": "aws",
    "azure": "azure",
    "gcp": "gcp",
    "python": "python",
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
    "keras": "keras",
    "langchain": "langchain",
    "llamaindex": "llamaindex",
    "llama index": "llamaindex",
    "langgraph": "langgraph",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "javascript": "javascript",
    "typescript": "typescript",
    "git": "git",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "sql": "sql",
    "nlp": "nlp",
    "rag": "rag",
    "mlops": "mlops",
    "airflow": "airflow",
    "spark": "spark",
    "tableau": "tableau",
    "power bi": "power-bi",
    "figma": "figma",
    "adobe creative cloud": "adobe-creative-cloud",
}


ROLE_PATTERNS = [
    ("genai", [
        "genai", "generative ai", "gen ai", "llm engineer",
        "rag engineer", "ai engineer", "generative-ai"
    ]),
    ("machine_learning", [
        "machine learning", "ml engineer", "ai/ml", "ai ml",
        "machine-learning"
    ]),
    ("data_science", [
        "data scientist", "data science"
    ]),
    ("nlp", [
        "nlp engineer", "nlp", "natural language"
    ]),
    ("qa_testing", [
        "qa engineer", "quality assurance", "test engineer",
        "software tester", "sdet", "quality engineer"
    ]),
    ("backend", [
        "backend", "back-end", "software engineer"
    ]),
    ("frontend", [
        "frontend", "front-end", "react developer"
    ]),
    ("devops", [
        "devops", "site reliability", "sre"
    ]),
    ("data_engineering", [
        "data engineer", "data engineering"
    ]),
    ("design", [
        "designer", "design specialist", "ux", "ui designer"
    ]),
    ("marketing", [
        "marketing", "growth marketing"
    ]),
    ("sales", [
        "sales", "solution executive", "pre-sales", "presales"
    ]),
    ("communications", [
        "communications", "corporate communications"
    ]),
]


SKILLS = sorted(
    set(ALIASES.values()),
    key=len,
    reverse=True
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def normalize(value):
    if value is None:
        return ""

    value = str(value).lower()

    for old, new in ALIASES.items():
        value = value.replace(old, new)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    # Preserve some structure before removing HTML.
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</h[1-6]\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)

    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


def job_value(job, key, default=None):
    try:
        value = job[key]
    except Exception:
        value = default

    return value if value is not None else default


def contains_any(text, patterns):
    text = normalize(text)
    return any(p in text for p in patterns)


def unique(items):
    result = []

    for item in items:
        if item and item not in result:
            result.append(item)

    return result


# ---------------------------------------------------------
# Role
# ---------------------------------------------------------

def extract_role(title, description):
    text = normalize(f"{title} {description}")

    # Title gets priority.
    title_norm = normalize(title)

    for role, patterns in ROLE_PATTERNS:
        if any(p in title_norm for p in patterns):
            return role

    for role, patterns in ROLE_PATTERNS:
        if any(p in text for p in patterns):
            return role

    return None


# ---------------------------------------------------------
# Experience
# ---------------------------------------------------------

def extract_experience(text):
    text = clean_text(text)

    results = []

    patterns = [
        r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?experience",
        r"(\d+)\s*-\s*(\d+)\s*years?\s+(?:of\s+)?experience",
        r"minimum\s+(?:of\s+)?(\d+)\s*years?",
        r"at\s+least\s+(\d+)\s*years?",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 160)

            clause = text[start:end]

            if re.search(
                r"\b(preferred|bonus|nice to have|plus|desired)\b",
                clause,
                re.I
            ):
                level = "PREFERRED"
            else:
                level = "REQUIRED"

            years = match.group(1)

            results.append({
                "level": level,
                "years": f"{years}+ years",
                "evidence": clause.strip()
            })

    # Remove duplicates.
    seen = set()
    output = []

    for item in results:
        key = (item["level"], item["years"])

        if key not in seen:
            seen.add(key)
            output.append(item)

    return output


# ---------------------------------------------------------
# Education
# ---------------------------------------------------------

def extract_education(text):
    text = clean_text(text)
    results = []

    degree_patterns = [
        ("phd", r"\b(?:ph\.?d\.?|doctorate)\b"),
        ("master", r"\b(?:master'?s?|ms|m\.s\.|mtech|m\.tech)\b"),
        ("bachelor", r"\b(?:bachelor'?s?|bs|b\.s\.|btech|b\.tech)\b"),
    ]

    for degree, pattern in degree_patterns:
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 140)
            clause = text[start:end]

            # Ignore generic mentions that aren't qualification statements.
            if not re.search(
                r"\b(degree|education|graduate|graduation|"
                r"qualification|required|preferred|equivalent|"
                r"bachelor|master|ph\.?d|doctorate)\b",
                clause,
                re.I
            ):
                continue

            if re.search(
                r"\b(preferred|bonus|nice to have|plus|desired)\b",
                clause,
                re.I
            ):
                level = "PREFERRED"
            else:
                level = "REQUIRED"

            results.append({
                "level": level,
                "degree": degree,
                "evidence": clause.strip()
            })

    # Deduplicate.
    seen = set()
    output = []

    for item in results:
        key = (item["level"], item["degree"])

        if key not in seen:
            seen.add(key)
            output.append(item)

    return output


# ---------------------------------------------------------
# Skills
# ---------------------------------------------------------

def extract_skills(text):
    text = clean_text(text)
    normalized = normalize(text)

    required = []
    preferred = []
    context = []

    for skill in SKILLS:
        # Convert canonical skill back to searchable forms.
        candidates = [skill]

        for alias, canonical in ALIASES.items():
            if canonical == skill:
                candidates.append(alias)

        found = False

        for candidate in candidates:
            if re.search(
                r"(?<![a-z0-9])" +
                re.escape(candidate) +
                r"(?![a-z0-9])",
                normalized,
                re.I
            ):
                found = True
                break

        if not found:
            continue

        # Find one local evidence window.
        pos = normalized.find(skill)

        if pos < 0:
            pos = 0

        start = max(0, pos - 100)
        end = min(len(normalized), pos + 180)

        clause = normalized[start:end]

        if re.search(
            r"\b(preferred|bonus|nice to have|nice-to-have|"
            r"plus|desired|ideally)\b",
            clause,
            re.I
        ):
            preferred.append(skill)

        elif re.search(
            r"\b(required|required to|must|"
            r"proficiency|proficient|experience with|"
            r"experience in|strong knowledge|expertise|"
            r"hands-on|hands on|ability to|"
            r"responsible for|you will)\b",
            clause,
            re.I
        ):
            required.append(skill)

        else:
            context.append(skill)

    # A skill mentioned in required/preferred should not remain context.
    context = [
        x for x in context
        if x not in required and x not in preferred
    ]

    return {
        "required": unique(required),
        "preferred": unique(preferred),
        "context": unique(context),
    }


# ---------------------------------------------------------
# OR groups
# ---------------------------------------------------------

def extract_or_groups(text):
    text = normalize(clean_text(text))

    groups = []

    patterns = [
        r"(?:experience|proficiency|knowledge|skills?)\s+(?:in|with)\s+"
        r"([a-z0-9 .+#/-]+?)\s+(?:or|alternatively)\s+"
        r"([a-z0-9 .+#/-]+)",

        r"([a-z0-9 .+#/-]+)\s*,\s*([a-z0-9 .+#/-]+)\s*,?\s*"
        r"(?:or)\s+([a-z0-9 .+#/-]+)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            parts = []

            for group in match.groups():
                if not group:
                    continue

                value = normalize(group).strip(" ,.;:")

                if value in ALIASES:
                    value = ALIASES[value]

                if value in SKILLS:
                    parts.append(value)

            parts = unique(parts)

            if len(parts) >= 2:
                groups.append({
                    "type": "OR",
                    "skills": parts
                })

    return groups


# ---------------------------------------------------------
# Employment
# ---------------------------------------------------------

def extract_employment(job, text):
    raw = job_value(job, "employment_type", "")

    if raw:
        return {
            "metadata": str(raw),
            "requirements": []
        }

    normalized = normalize(text)

    values = []

    for term in [
        "full-time",
        "full time",
        "part-time",
        "part time",
        "contract",
        "contractor",
        "internship",
        "intern",
    ]:
        if term in normalized:
            values.append(term.replace(" ", "-"))

    return {
        "metadata": unique(values),
        "requirements": []
    }


# ---------------------------------------------------------
# Location
# ---------------------------------------------------------

def extract_location(job, text):
    location = job_value(job, "location", "")
    location_codes = job_value(job, "location_codes", "")
    remote_type = job_value(job, "remote_type", "")
    restrictions = job_value(job, "location_restrictions", "")

    raw = " ".join([
        str(location or ""),
        str(location_codes or ""),
        str(remote_type or ""),
        str(restrictions or ""),
        clean_text(text)
    ])

    normalized = normalize(raw)

    remote = (
        "remote" in normalized
        or "work from home" in normalized
    )

    worldwide = any(
        x in normalized
        for x in [
            "worldwide",
            "work from anywhere",
            "anywhere in the world",
            "global",
            "global remote",
        ]
    )

    india = (
        "india" in normalized
        or "in" == str(location_codes).strip().lower()
        or "hyderabad" in normalized
        or "bangalore" in normalized
        or "bengaluru" in normalized
        or "mumbai" in normalized
        or "delhi" in normalized
        or "pune" in normalized
    )

    timezone = job_value(job, "timezone_restrictions", "")

    return {
        "raw_location": str(location or ""),
        "location_codes": str(location_codes or ""),
        "remote": remote,
        "worldwide": worldwide,
        "india_signal": india,
        "timezone_restrictions": str(timezone or ""),
        "location_restrictions": str(restrictions or ""),
        "source": "job_metadata_and_description"
    }


# ---------------------------------------------------------
# Authorization / visa
# ---------------------------------------------------------

def extract_authorization(text):
    normalized = normalize(clean_text(text))

    restrictions = []

    patterns = [
        "visa sponsorship",
        "visa sponsor",
        "sponsorship available",
        "sponsorship is not available",
        "must be authorized to work",
        "work authorization",
        "legally authorized to work",
        "right to work",
    ]

    for pattern in patterns:
        if pattern in normalized:
            pos = normalized.find(pattern)

            start = max(0, pos - 100)
            end = min(len(normalized), pos + 180)

            restrictions.append({
                "type": "work_authorization",
                "evidence": normalized[start:end]
            })

    return restrictions


# ---------------------------------------------------------
# Certifications
# ---------------------------------------------------------

def extract_certifications(text):
    normalized = normalize(clean_text(text))

    results = []

    patterns = [
        r"certification\s+(?:is\s+)?required",
        r"certification\s+(?:is\s+)?preferred",
        r"certified\s+(?:in|as)\s+[a-z0-9 .+#/-]+",
        r"\baws\s+certified\b",
        r"\bazure\s+certified\b",
        r"\bgcp\s+certified\b",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, normalized, re.I):
            start = max(0, match.start() - 100)
            end = min(len(normalized), match.end() + 150)

            clause = normalized[start:end]

            if "preferred" in clause:
                level = "PREFERRED"
            else:
                level = "REQUIRED"

            results.append({
                "level": level,
                "evidence": clause.strip()
            })

    return results


# ---------------------------------------------------------
# Main extraction
# ---------------------------------------------------------

def extract_job(job):
    job = dict(job)

    title = job_value(job, "title", "")
    description = clean_text(job_value(job, "description", ""))

    role = extract_role(title, description)
    experience = extract_experience(description)
    education = extract_education(description)
    skills = extract_skills(description)
    or_groups = extract_or_groups(description)
    employment = extract_employment(job, description)
    location = extract_location(job, description)
    authorization = extract_authorization(description)
    certifications = extract_certifications(description)

    warnings = []

    if not role:
        warnings.append("No role family detected")

    if not description:
        warnings.append("Job description is empty")

    return {
        "job_id": job_value(job, "id"),
        "source_job_id": job_value(job, "source_job_id"),
        "title": title,
        "company": job_value(job, "company", ""),
        "source": job_value(job, "source", ""),
        "url": job_value(job, "url", ""),
        "source_url": job_value(job, "source_url", ""),
        "application_url": job_value(job, "application_url", ""),

        "role_family": role,

        "experience": experience,
        "education": education,

        "skills": skills,
        "skill_or_groups": or_groups,

        "employment": employment,

        "location": location,

        "authorization": authorization,

        "certifications": certifications,

        "extraction": {
            "version": "0.8",
            "timestamp": datetime.now().isoformat(),
            "method": "deterministic_rule_based"
        },

        "warnings": warnings
    }


def main():
    print("NEXPLY - ATOMIC REQUIREMENT EXTRACTOR v0.8")
    print("Database :", DB_PATH)
    print("Output   :", OUTPUT_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY id"
    ).fetchall()

    conn.close()

    print("Jobs found:", len(rows))

    results = []

    for row in rows:
        try:
            results.append(extract_job(row))
        except Exception as exc:
            results.append({
                "job_id": row["id"],
                "title": row["title"],
                "error": str(exc),
                "extraction": {
                    "version": "0.8"
                }
            })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            results,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("Saved:", OUTPUT_PATH)
    print()

    print("LATEST 10 JOBS")

    for job in results[-10:]:
        print(
            f"JOB {job.get('job_id')} | "
            f"{job.get('title')}"
        )

        print(
            "Company:",
            job.get("company")
        )

        print(
            "Role:",
            job.get("role_family")
        )

        exp = job.get("experience", [])
        edu = job.get("education", [])
        skills = job.get("skills", {})
        loc = job.get("location", {})

        print(
            f"Experience: {len(exp)} | "
            f"Education: {len(edu)}"
        )

        print(
            f"Skills: "
            f"required={len(skills.get('required', []))} "
            f"preferred={len(skills.get('preferred', []))} "
            f"context={len(skills.get('context', []))}"
        )

        print(
            "Location:",
            loc.get("raw_location"),
            "| Remote:",
            loc.get("remote"),
            "| Worldwide:",
            loc.get("worldwide")
        )

        if job.get("warnings"):
            print(
                "WARNING:",
                "; ".join(job["warnings"])
            )

        print("-" * 60)


if __name__ == "__main__":
    main()