import json
import re
import sqlite3
import html
from pathlib import Path
from datetime import datetime


# ============================================================
# Rajesh AI - Atomic Requirement Extractor v0.6
# ============================================================
# Purpose:
#   Convert raw job descriptions into structured,
#   machine-readable requirements.
#
# Important:
#   - Does NOT modify the jobs database.
#   - Does NOT perform candidate matching.
#   - Does NOT use an LLM.
#   - Metadata is treated separately from requirements.
#   - Evidence is kept short and local to the requirement.
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"
OUTPUT_PATH = BASE_DIR / "output" / "requirement_extraction_v06.json"


# ============================================================
# Configuration
# ============================================================

ROLE_PATTERNS = {
    "genai": [
        r"\bgen(?:erative)?[\s-]?ai\b",
        r"\bgenerative artificial intelligence\b",
        r"\bllm\b",
        r"\blarge language model",
        r"\brag\b",
        r"\bretrieval augmented generation\b",
    ],
    "machine_learning": [
        r"\bmachine learning\b",
        r"\bml engineer\b",
        r"\bai research engineer\b",
        r"\bresearch engineer\b",
        r"\bdeep learning\b",
        r"\breinforcement learning\b",
        r"\bcomputer vision\b",
    ],
    "nlp": [
        r"\bnlp\b",
        r"\bnatural language processing\b",
        r"\bnatural language\b",
    ],
    "qa_testing": [
        r"\bqa engineer\b",
        r"\bquality assurance\b",
        r"\btest engineer\b",
        r"\bsoftware testing\b",
        r"\bqa\b",
    ],
    "backend": [
        r"\bbackend\b",
        r"\bback-end\b",
        r"\bserver-side\b",
    ],
    "design": [
        r"\bdesigner\b",
        r"\bdesign specialist\b",
        r"\bproduct design\b",
        r"\bux\b",
        r"\bui design\b",
    ],
    "marketing": [
        r"\bmarketing\b",
        r"\bmarketing coordinator\b",
        r"\bgrowth\b",
    ],
    "communications": [
        r"\bcommunications\b",
        r"\bcorporate communications\b",
        r"\bpublic relations\b",
        r"\bpr\b",
    ],
    "sales": [
        r"\bsales\b",
        r"\bsolution executive\b",
        r"\bpre-sales\b",
        r"\bpresales\b",
        r"\bbusiness development\b",
    ],
}


SKILL_ALIASES = {
    "python": [r"\bpython\b"],
    "java": [r"\bjava\b"],
    "javascript": [r"\bjavascript\b"],
    "typescript": [r"\btypescript\b"],
    "c++": [r"\bc\+\+\b"],
    "sql": [r"\bsql\b"],
    "pytorch": [r"\bpytorch\b"],
    "tensorflow": [r"\btensorflow\b"],
    "keras": [r"\bkeras\b"],
    "scikit-learn": [r"\bscikit[\s-]?learn\b"],
    "hugging-face": [r"\bhugging[\s-]?face\b"],
    "transformers": [r"\btransformers\b"],
    "nlp": [r"\bnlp\b"],
    "machine-learning": [r"\bmachine learning\b"],
    "deep-learning": [r"\bdeep learning\b"],
    "computer-vision": [r"\bcomputer vision\b"],
    "reinforcement-learning": [r"\breinforcement learning\b"],
    "llm": [r"\bllms?\b", r"\blarge language models?\b"],
    "rag": [r"\brag\b", r"\bretrieval augmented generation\b"],
    "langchain": [r"\blangchain\b"],
    "llamaindex": [r"\bllamaindex\b", r"\bllamaindex\b"],
    "langgraph": [r"\blanggraph\b"],
    "embeddings": [r"\bembeddings?\b"],
    "vector-search": [r"\bvector search\b"],
    "vector-database": [r"\bvector (?:database|db)\b"],
    "prompt-engineering": [r"\bprompt engineering\b"],
    "fine-tuning": [r"\bfine[\s-]?tuning\b"],
    "lora": [r"\b(?:qlora|lora)\b"],
    "peft": [r"\bpeft\b"],
    "xgboost": [r"\bxgboost\b"],
    "lightgbm": [r"\blightgbm\b"],
    "aws": [r"\baws\b", r"\bamazon web services\b"],
    "azure": [r"\bazure\b"],
    "gcp": [r"\bgcp\b", r"\bgoogle cloud\b"],
    "databricks": [r"\bdatabricks\b"],
    "docker": [r"\bdocker\b"],
    "kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "airflow": [r"\bairflow\b", r"\bapache airflow\b"],
    "mlflow": [r"\bmlflow\b"],
    "git": [r"(?<!github)(?<!gitlab)\bgit\b"],
    "github-actions": [r"\bgithub actions\b"],
    "gitlab-ci": [r"\bgitlab ci\b"],
    "jenkins": [r"\bjenkins\b"],
    "figma": [r"\bfigma\b"],
    "adobe": [r"\badobe(?: creative cloud)?\b"],
    "photoshop": [r"\bphotoshop\b"],
    "blender": [r"\bblender\b"],
    "comfyui": [r"\bcomfyui\b"],
    "regression-testing": [r"\bregression testing\b"],
    "automation": [r"\bautomation\b"],
    "ai-agents": [r"\bai agents?\b", r"\bagentic ai\b"],
}


EDUCATION_PATTERNS = [
    ("phd", r"\bph\.?d\.?\b|\bdoctorate\b"),
    ("master", r"\bmaster'?s?\b|\bm\.?s\.?\b|\bm\.?tech\b|\bmba\b"),
    ("bachelor", r"\bbachelor'?s?\b|\bb\.?s\.?\b|\bb\.?tech\b|\bb\.?e\.?\b"),
    ("associate", r"\bassociate'?s?\b"),
    ("high_school", r"\bhigh school\b"),
]


CERTIFICATION_TERMS = [
    "certification",
    "certified",
    "certificate",
    "certifications",
]


REQUIRED_MARKERS = [
    r"\brequired\b",
    r"\bmust\b",
    r"\bminimum\b",
    r"\bat least\b",
    r"\bmandatory\b",
    r"\bneed to have\b",
    r"\bshould have\b",
    r"\bwill have\b",
    r"\bhave\b",
    r"\bhas\b",
]


PREFERRED_MARKERS = [
    r"\bpreferred\b",
    r"\bprefer\b",
    r"\bnice to have\b",
    r"\bnice-to-have\b",
    r"\bbonus\b",
    r"\bdesired\b",
    r"\bplus\b",
    r"\bideally\b",
    r"\bwould be a plus\b",
]


CONTEXT_MARKERS = [
    r"\bresponsibilities\b",
    r"\bwhat you.ll do\b",
    r"\babout the role\b",
    r"\babout us\b",
    r"\bcompany\b",
    r"\bbenefits\b",
]


AUTHORIZATION_PATTERNS = [
    (
        "no_sponsorship",
        [
            r"\bdo not sponsor\b",
            r"\bdoes not sponsor\b",
            r"\bno visa sponsorship\b",
            r"\bno sponsorship\b",
            r"\bcannot provide visa sponsorship\b",
            r"\bunable to provide visa sponsorship\b",
            r"\bnot able to sponsor\b",
            r"\bwill not sponsor\b",
            r"\bwon't sponsor\b",
            r"\bcannot take over sponsorship\b",
            r"\bnot able to take over sponsorship\b",
        ],
    ),
    (
        "work_authorization_required",
        [
            r"\bmust be authorized to work\b",
            r"\bmust have authorization to work\b",
            r"\blegally authorized to work\b",
            r"\bauthorized to work in\b",
            r"\bexisting work authorization\b",
            r"\bvalid work authorization\b",
        ],
    ),
]


# ============================================================
# Text cleaning
# ============================================================

def clean_html(raw):
    if not raw:
        return ""

    text = html.unescape(str(raw))

    text = re.sub(
        r"(?is)<script.*?>.*?</script>",
        " ",
        text,
    )

    text = re.sub(
        r"(?is)<style.*?>.*?</style>",
        " ",
        text,
    )

    text = re.sub(r"<[^>]+>", " ", text)

    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def normalize_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def short_evidence(text, limit=320):
    text = normalize_spaces(text)

    if len(text) <= limit:
        return text

    return text[:limit].rsplit(" ", 1)[0] + "..."


# ============================================================
# Section detection
# ============================================================

SECTION_ALIASES = {
    "required": [
        "requirements",
        "required qualifications",
        "minimum qualifications",
        "basic qualifications",
        "must have",
        "what we're looking for",
        "what we are looking for",
        "qualifications",
    ],
    "preferred": [
        "preferred qualifications",
        "preferred",
        "nice to have",
        "nice-to-have",
        "bonus",
        "additional qualifications",
    ],
    "responsibilities": [
        "responsibilities",
        "what you'll do",
        "what you will do",
        "your responsibilities",
        "key responsibilities",
        "role responsibilities",
    ],
    "education": [
        "education",
        "educational qualifications",
        "academic qualifications",
    ],
}


def detect_section(line):
    value = normalize_spaces(line).lower()

    value = re.sub(r"[:\-]+$", "", value)

    for section, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if value == alias:
                return section

    return None


def annotate_sections(text):
    """
    Returns list of (section, clause).
    """
    lines = text.splitlines()

    result = []
    current_section = None

    for line in lines:
        line = line.strip()

        if not line:
            continue

        detected = detect_section(line)

        if detected:
            current_section = detected
            continue

        result.append((current_section, line))

    return result


# ============================================================
# Atomic clause splitting
# ============================================================

def split_clauses(text):
    """
    Conservative clause splitting.

    We intentionally do NOT blindly split every 'and'/'or'.
    That caused major v0.5 false OR groups.
    """

    text = normalize_spaces(text)

    # Normalize bullets.
    text = re.sub(r"^[Ã¢â‚¬Â¢Ã¢â€”ÂÃ¢â€“ÂªÃ¢â€”Â¦\-*]+\s*", "", text)

    # Split semicolon-separated requirements.
    parts = re.split(r"\s*;\s*", text)

    final_parts = []

    for part in parts:
        part = part.strip()

        if not part:
            continue

        # Split sentence boundaries only.
        sentences = re.split(
            r"(?<=[.!?])\s+(?=[A-Z0-9])",
            part,
        )

        for sentence in sentences:
            sentence = sentence.strip()

            if sentence:
                final_parts.append(sentence)

    return final_parts


# ============================================================
# Classification
# ============================================================

def has_marker(text, patterns):
    value = text.lower()

    return any(re.search(pattern, value) for pattern in patterns)


def classify_requirement(text, section=None):
    """
    Explicit wording beats section inheritance.

    This prevents:
      'Bachelor's degree ...'
    inside a Required section from becoming CONTEXT.
    """

    value = text.lower()

    if has_marker(value, PREFERRED_MARKERS):
        return "PREFERRED"

    if has_marker(value, REQUIRED_MARKERS):
        return "REQUIRED"

    if section == "preferred":
        return "PREFERRED"

    if section in {"required", "education"}:
        return "REQUIRED"

    return "CONTEXT"


# ============================================================
# Experience extraction
# ============================================================

EXPERIENCE_PATTERN = re.compile(
    r"\b"
    r"(?P<minimum>\d+(?:\.\d+)?)"
    r"\s*(?:\+|plus)?"
    r"\s*(?:to|-)\s*"
    r"(?P<maximum>\d+(?:\.\d+)?)"
    r"\s*years?"
    r"|"
    r"\b"
    r"(?P<minimum_single>\d+(?:\.\d+)?)"
    r"\s*(?:\+|plus)?"
    r"\s*years?"
    r")",
    re.IGNORECASE,
)


def extract_experience(text):
    matches = list(EXPERIENCE_PATTERN.finditer(text))

    results = []

    for match in matches:
        if match.group("minimum") is not None:
            minimum = float(match.group("minimum"))
            maximum = float(match.group("maximum"))
        else:
            minimum = float(match.group("minimum_single"))
            maximum = None

        start = match.start()
        end = match.end()

        # Capture a bounded local window around the number.
        before = text[max(0, start - 120):start]
        after = text[end:min(len(text), end + 180)]

        context = normalize_spaces(before + " " + after)

        # Identify likely domain.
        domain = []

        domain_patterns = [
            r"\bin\s+([^,.;]+)",
            r"\bof\s+([^,.;]+)",
            r"\bexperience\s+(?:in|with)\s+([^,.;]+)",
            r"\b(?:leading|managing)\s+([^,.;]+)",
        ]

        for pattern in domain_patterns:
            m = re.search(pattern, context, re.IGNORECASE)
            if m:
                candidate = normalize_spaces(m.group(1))

                # Avoid swallowing huge clauses.
                if 2 <= len(candidate) <= 100:
                    domain.append(candidate)

        # Deduplicate.
        clean_domains = []

        for item in domain:
            item = re.sub(
                r"\b(?:and|or)\s*$",
                "",
                item,
                flags=re.IGNORECASE,
            ).strip()

            if item and item.lower() not in {
                x.lower() for x in clean_domains
            }:
                clean_domains.append(item)

        results.append(
            {
                "minimum_years": int(minimum)
                if minimum.is_integer()
                else minimum,
                "maximum_years": (
                    int(maximum)
                    if maximum is not None and maximum.is_integer()
                    else maximum
                ),
                "domain": clean_domains,
                "evidence": short_evidence(text),
            }
        )

    return results


# ============================================================
# Education extraction
# ============================================================

def extract_education(text, requirement_level):
    results = []

    lower = text.lower()

    for level, pattern in EDUCATION_PATTERNS:
        if re.search(pattern, lower):
            results.append(
                {
                    "level": level,
                    "requirement": requirement_level,
                    "evidence": short_evidence(text),
                }
            )

    return results


# ============================================================
# Certification extraction
# ============================================================

def extract_certification(text, requirement_level):
    lower = text.lower()

    if not any(term in lower for term in CERTIFICATION_TERMS):
        return []

    return [
        {
            "requirement": requirement_level,
            "evidence": short_evidence(text),
        }
    ]


# ============================================================
# Skill extraction
# ============================================================

def extract_skill_mentions(text):
    found = []

    for skill, patterns in SKILL_ALIASES.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found.append(skill)
                break

    return sorted(set(found))


def is_education_sentence(text):
    lower = text.lower()

    education_words = [
        "bachelor",
        "master",
        "phd",
        "doctorate",
        "degree",
        "academic",
        "university",
        "college",
    ]

    return any(word in lower for word in education_words)


def is_certification_sentence(text):
    lower = text.lower()

    return any(term in lower for term in CERTIFICATION_TERMS)


def extract_skill_operator(text, skills):
    """
    Detect OR/AND only when the wording actually connects
    the listed technologies.

    Examples:
      'at least one of TypeScript, JavaScript, or Python'
        -> OR

      'Python and PyTorch'
        -> AND

      'Python, PyTorch, and AWS'
        -> AND

    Generic 'or' elsewhere in the sentence is ignored.
    """

    lower = text.lower()

    if len(skills) < 2:
        return None

    # Explicit alternative wording.
    if re.search(
        r"\bat least one of\b|\bone of\b",
        lower,
    ):
        if re.search(r"\bor\b", lower):
            return "OR"

    # Explicit X, Y, or Z pattern.
    if re.search(
        r",\s*(?:and\s+)?(?:or)\s+",
        lower,
    ):
        return "OR"

    # Direct 'X or Y'.
    if re.search(r"\b\w[\w+#.-]*\s+or\s+\w[\w+#.-]*\b", lower):
        # Only use this if both sides correspond to known skills.
        or_index = lower.find(" or ")

        if or_index >= 0:
            left = lower[:or_index]
            right = lower[or_index + 4:]

            left_skills = extract_skill_mentions(left)
            right_skills = extract_skill_mentions(right)

            if left_skills and right_skills:
                return "OR"

    # Explicit AND.
    if re.search(r"\band\b", lower):
        return "AND"

    # Comma-separated technology list under a requirement.
    if "," in lower:
        return "AND"

    return None


def extract_skills_from_clause(text, requirement_level):
    if is_education_sentence(text):
        return []

    if is_certification_sentence(text):
        return []

    skills = extract_skill_mentions(text)

    if not skills:
        return []

    operator = extract_skill_operator(text, skills)

    return [
        {
            "requirement": requirement_level,
            "skills": skills,
            "operator": operator,
            "evidence": short_evidence(text),
        }
    ]


# ============================================================
# Authorization extraction
# ============================================================

def extract_authorization(text):
    results = []

    lower = text.lower()

    for restriction, patterns in AUTHORIZATION_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lower):
                results.append(
                    {
                        "type": restriction,
                        "evidence": short_evidence(text),
                    }
                )
                break

    return results


# ============================================================
# Role classification
# ============================================================

def detect_role_families(title, description):
    title_text = normalize_spaces(title or "")
    title_lower = title_text.lower()

    result = []

    # Title has priority.
    for role, patterns in ROLE_PATTERNS.items():
        if any(re.search(p, title_lower) for p in patterns):
            result.append(role)

    if result:
        return sorted(set(result))

    # Fallback to description.
    description_lower = description.lower()

    for role, patterns in ROLE_PATTERNS.items():
        if any(
            re.search(p, description_lower)
            for p in patterns
        ):
            result.append(role)

    return sorted(set(result))


# ============================================================
# Location extraction
# ============================================================

def extract_location_metadata(row):
    remote_type = normalize_spaces(row["remote_type"] or "")
    location = normalize_spaces(row["location"] or "")
    restrictions = normalize_spaces(
        row["location_restrictions"] or ""
    )

    combined = " ".join(
        [
            remote_type,
            location,
            restrictions,
        ]
    ).lower()

    worldwide = False
    remote = False

    if "worldwide" in combined or "global" in combined:
        worldwide = True

    if "remote" in combined:
        remote = True

    return {
        "raw_location": location,
        "remote_type": remote_type,
        "location_restrictions": restrictions,
        "remote": remote,
        "worldwide": worldwide,
        "source": "database_metadata",
    }


# ============================================================
# Employment metadata
# ============================================================

def extract_employment_metadata(row):
    value = normalize_spaces(row["employment_type"] or "")

    if not value:
        return []

    return [
        {
            "type": "metadata",
            "value": value,
            "evidence": "Database employment_type field",
        }
    ]


# ============================================================
# Main job extraction
# ============================================================

def extract_job(row):
    title = normalize_spaces(row["title"] or "")
    description = clean_html(row["description"] or "")

    role_families = detect_role_families(
        title,
        description,
    )

    sections = annotate_sections(description)

    experience = []
    education = []
    certifications = []

    required_skills = []
    preferred_skills = []
    context_skills = []

    authorization = []

    validation_warnings = []

    for section, raw_clause in sections:
        clauses = split_clauses(raw_clause)

        for clause in clauses:
            clause = normalize_spaces(clause)

            if not clause:
                continue

            level = classify_requirement(
                clause,
                section,
            )

            # ------------------------------------------------
            # Experience
            # ------------------------------------------------

            experience_matches = extract_experience(clause)

            for exp in experience_matches:
                exp["requirement"] = level
                experience.append(exp)

            # ------------------------------------------------
            # Education
            # ------------------------------------------------

            education.extend(
                extract_education(
                    clause,
                    level,
                )
            )

            # ------------------------------------------------
            # Certifications
            # ------------------------------------------------

            certifications.extend(
                extract_certification(
                    clause,
                    level,
                )
            )

            # ------------------------------------------------
            # Authorization
            # ------------------------------------------------

            authorization.extend(
                extract_authorization(clause)
            )

            # ------------------------------------------------
            # Skills
            # ------------------------------------------------

            skill_groups = extract_skills_from_clause(
                clause,
                level,
            )

            for group in skill_groups:
                if level == "REQUIRED":
                    required_skills.append(group)

                elif level == "PREFERRED":
                    preferred_skills.append(group)

                else:
                    context_skills.append(group)

    # --------------------------------------------------------
    # Remove duplicate experience records
    # --------------------------------------------------------

    unique_experience = []
    exp_keys = set()

    for item in experience:
        key = (
            item["requirement"],
            item["minimum_years"],
            item["maximum_years"],
            tuple(item["domain"]),
        )

        if key not in exp_keys:
            exp_keys.add(key)
            unique_experience.append(item)

    # --------------------------------------------------------
    # Remove duplicate education records
    # --------------------------------------------------------

    unique_education = []
    edu_keys = set()

    for item in education:
        key = (
            item["requirement"],
            item["level"],
        )

        if key not in edu_keys:
            edu_keys.add(key)
            unique_education.append(item)

    # --------------------------------------------------------
    # Remove duplicate skills
    # --------------------------------------------------------

    def dedupe_skill_groups(groups):
        output = []
        seen = set()

        for group in groups:
            key = (
                group["requirement"],
                tuple(group["skills"]),
                group["operator"],
            )

            if key not in seen:
                seen.add(key)
                output.append(group)

        return output

    required_skills = dedupe_skill_groups(required_skills)
    preferred_skills = dedupe_skill_groups(preferred_skills)
    context_skills = dedupe_skill_groups(context_skills)

    # --------------------------------------------------------
    # Validation warnings
    # --------------------------------------------------------

    all_skill_groups = (
        required_skills
        + preferred_skills
        + context_skills
    )

    for group in all_skill_groups:
        if group["operator"] == "OR" and len(group["skills"]) > 5:
            validation_warnings.append(
                "Large OR skill group detected; review syntax."
            )

    if not role_families:
        validation_warnings.append(
            "No role family detected from title/description."
        )

    if len(description) < 100:
        validation_warnings.append(
            "Very short job description."
        )

    # --------------------------------------------------------
    # Final structured record
    # --------------------------------------------------------

    return {
        "job_id": row["id"],
        "title": title,
        "company": normalize_spaces(row["company"] or ""),
        "source": normalize_spaces(row["source"] or ""),
        "source_job_id": normalize_spaces(
            row["source_job_id"] or ""
        ),
        "source_url": normalize_spaces(
            row["source_url"] or row["url"] or ""
        ),
        "application_url": normalize_spaces(
            row["application_url"] or ""
        ),
        "role_families": role_families,
        "requirements": {
            "experience": unique_experience,
            "education": unique_education,
            "skills": {
                "required": required_skills,
                "preferred": preferred_skills,
                "context": context_skills,
            },
            "certifications": certifications,
            "authorization": authorization,
            "employment": extract_employment_metadata(row),
            "location": extract_location_metadata(row),
        },
        "validation_warnings": sorted(
            set(validation_warnings)
        ),
    }


# ============================================================
# Database
# ============================================================

def get_jobs():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                source_job_id,
                title,
                company,
                location,
                remote_type,
                source,
                url,
                description,
                employment_type,
                source_url,
                application_url,
                location_restrictions
            FROM jobs
            ORDER BY id DESC
            """
        )

        return cursor.fetchall()

    finally:
        connection.close()


# ============================================================
# Diagnostics
# ============================================================

def print_job_summary(job):
    requirements = job["requirements"]

    experience = requirements["experience"]
    education = requirements["education"]

    required = requirements["skills"]["required"]
    preferred = requirements["skills"]["preferred"]
    context = requirements["skills"]["context"]

    print()
    print("=" * 78)
    print(f"JOB {job['job_id']} | {job['title']}")
    print(f"Company : {job['company']}")
    print(f"Role    : {', '.join(job['role_families']) or 'NONE'}")

    print(
        f"Experience : {len(experience)} | "
        f"Education : {len(education)}"
    )

    for item in experience:
        print(
            f"  EXP [{item['requirement']}] "
            f"{item['minimum_years']}+"
            f"{'-' + str(item['maximum_years']) if item['maximum_years'] else ''} "
            f"years | "
            f"{', '.join(item['domain']) or 'general'}"
        )

    for item in education:
        print(
            f"  EDU [{item['requirement']}] "
            f"{item['level']}"
        )

    print(
        f"Skills : required={len(required)}, "
        f"preferred={len(preferred)}, "
        f"context={len(context)}"
    )

    for group in required:
        print(
            f"  SKILL [REQUIRED] "
            f"{group['operator'] or 'SINGLE'}: "
            f"{', '.join(group['skills'])}"
        )

    for group in preferred:
        print(
            f"  SKILL [PREFERRED] "
            f"{group['operator'] or 'SINGLE'}: "
            f"{', '.join(group['skills'])}"
        )

    auth = requirements["authorization"]

    if auth:
        print("Authorization:")
        for item in auth:
            print(
                f"  AUTH [{item['type']}] "
                f"{item['evidence']}"
            )

    location = requirements["location"]

    print(
        f"Location : "
        f"{location['raw_location'] or 'NONE'} | "
        f"Remote={location['remote']} | "
        f"Worldwide={location['worldwide']}"
    )

    if job["validation_warnings"]:
        print("WARNINGS:")
        for warning in job["validation_warnings"]:
            print(f"  - {warning}")


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 78)
    print("RAJESH AI - ATOMIC REQUIREMENT EXTRACTOR v0.6")
    print("=" * 78)
    print(f"Database : {DB_PATH}")
    print(f"Output   : {OUTPUT_PATH}")
    print()

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    jobs = get_jobs()

    print(f"Jobs found: {len(jobs)}")

    results = []

    for row in jobs:
        results.append(
            extract_job(row)
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "version": "0.6",
        "generated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "job_count": len(results),
        "jobs": results,
    }

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(f"Saved: {OUTPUT_PATH}")

    print()
    print("LATEST 10 JOBS")
    print("=" * 78)

    for job in results[:10]:
        print_job_summary(job)

    print()
    print("=" * 78)
    print("v0.6 EXTRACTION COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    main()
