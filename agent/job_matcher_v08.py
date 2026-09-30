import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime


# ============================================================
# RAJESH AI - JOB MATCHER v1.0
# ============================================================
# Uses:
#   data/jobs.db
#   output/requirement_extraction_v08.json
#   output/candidate_profile.json
#
# Output:
#   output/job_matches_v09.json
#
# Scoring:
#   Role relevance       40
#   Required skills      30
#   Preferred skills     10
#   Experience           10
#   Education             5
#   Location              5
#   -------------------------
#   Total               100
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "jobs.db"
REQUIREMENTS_PATH = BASE_DIR / "output" / "requirement_extraction_v08.json"
CANDIDATE_PATH = BASE_DIR / "output" / "candidate_profile.json"
OUTPUT_PATH = BASE_DIR / "output" / "job_matches_v09.json"


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_text(value):
    value = clean_text(value).lower()

    # Normalize common Unicode punctuation
    value = value.replace("–", "-")
    value = value.replace("—", "-")
    value = value.replace("’", "'")
    value = value.replace("“", '"')
    value = value.replace("”", '"')

    # Normalize common resume/API variations
    value = value.replace("retrieval-augmented generation", "rag")
    value = value.replace("large language model", "llm")
    value = value.replace("large language models", "llm")
    value = value.replace("generative artificial intelligence", "generative ai")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def canonical_skill(skill):
    """
    Normalize equivalent skill names so that:

        LLMs -> llm
        LLM -> llm
        Retrieval-Augmented Generation -> rag
        Hugging Face -> huggingface
        Scikit-learn -> sklearn
        Vector Databases -> vector database
    """

    s = normalize_text(skill)

    replacements = {
        "llms": "llm",
        "large language model": "llm",
        "large language models": "llm",

        "retrieval augmented generation": "rag",
        "retrieval-augmented generation": "rag",

        "hugging face": "huggingface",
        "huggingface transformers": "huggingface",

        "scikit learn": "sklearn",
        "scikit-learn": "sklearn",

        "vector databases": "vector database",
        "vector db": "vector database",
        "vector databases": "vector database",

        "machine learning": "machine learning",
        "deep learning": "deep learning",

        "question answering": "question answering",
        "question-answering": "question answering",

        "prompt-engineering": "prompt engineering",

        "fine tuning": "fine-tuning",
        "fine-tuning": "fine-tuning",

        "agentic ai": "agentic ai",

        "natural language processing": "nlp",

        "powerbi": "power bi",
        "tableau": "tableau",

        "aws s3": "aws",
        "amazon web services": "aws",

        "microsoft azure": "azure",
    }

    return replacements.get(s, s)


def skill_tokens(skill):
    """
    Return several normalized representations of a skill.
    """

    original = canonical_skill(skill)

    tokens = {original}

    compact = re.sub(r"[^a-z0-9+#.]+", "", original)
    if compact:
        tokens.add(compact)

    spaced = re.sub(r"[^a-z0-9+#.]+", " ", original).strip()
    if spaced:
        tokens.add(spaced)

    return tokens


# ============================================================
# CANDIDATE PROFILE
# ============================================================

def load_candidate():
    if not CANDIDATE_PATH.exists():
        raise FileNotFoundError(
            f"Candidate profile not found: {CANDIDATE_PATH}"
        )

    with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_candidate_skills(candidate):
    """
    Extract skills from the ACTUAL candidate_profile.json structure.

    Current structure:

        "skills_text":
            "Programming & Data: Python, SQL, Pandas...
             Machine Learning: Regression, Classification...
             Generative AI, LLM & RAG: LLMs, RAG..."

    Also supports structured future formats.
    """

    skills = set()

    def add_skill(value):
        if value is None:
            return

        if isinstance(value, str):

            # Split only when this is clearly a skill list
            parts = re.split(r",|;|\n", value)

            for part in parts:
                skill = part.strip()

                if not skill:
                    continue

                # Remove bullet characters
                skill = re.sub(r"^[•\-\*]+\s*", "", skill)

                if skill:
                    skills.add(canonical_skill(skill))

        elif isinstance(value, list):

            for item in value:
                add_skill(item)

        elif isinstance(value, dict):

            for value2 in value.values():
                add_skill(value2)

    # --------------------------------------------------------
    # PRIMARY SOURCE
    # --------------------------------------------------------

    skills_text = candidate.get("skills_text", "")

    if skills_text:

        for line in skills_text.splitlines():

            line = line.strip()

            if not line:
                continue

            # Example:
            #
            # Programming & Data: Python, SQL, Pandas
            #
            # Only take text after the category colon.

            if ":" in line:

                category, skill_part = line.split(":", 1)

                # Prevent category itself from becoming a skill
                if skill_part.strip():
                    add_skill(skill_part)

            else:
                add_skill(line)

    # --------------------------------------------------------
    # COMPATIBILITY WITH OTHER PROFILE FORMATS
    # --------------------------------------------------------

    possible_keys = [
        "skills",
        "technical_skills",
        "candidate_skills",
        "skill_list",
    ]

    for key in possible_keys:

        if key in candidate:
            add_skill(candidate[key])

    # --------------------------------------------------------
    # NESTED STRUCTURES
    # --------------------------------------------------------

    for parent_key in [
        "candidate",
        "profile",
        "resume",
    ]:

        parent = candidate.get(parent_key)

        if isinstance(parent, dict):

            for key in possible_keys + ["skills_text"]:

                if key in parent:
                    add_skill(parent[key])

    # Remove empty values
    skills = {
        skill
        for skill in skills
        if skill and len(skill) > 1
    }

    return sorted(skills)


def get_candidate_experience(candidate):
    """
    Current candidate settings/profile indicate approximately
    6 years of experience.
    """

    # Try explicit fields first
    for key in [
        "experience_years",
        "years_experience",
        "total_experience_years",
    ]:

        value = candidate.get(key)

        if value is not None:

            try:
                return float(value)
            except Exception:
                pass

    # Current target profile
    return 6.0


def get_candidate_education(candidate):
    """
    Extract education levels from education_text.
    """

    education = set()

    text = normalize_text(
        candidate.get("education_text", "")
    )

    if re.search(r"\bmaster\b|\bmasters\b|\bmsc\b|\bms\b", text):
        education.add("master")

    if re.search(
        r"\bbachelor\b|\bbachelors\b|\bbtech\b|\bbe\b|\bb\.tech\b",
        text
    ):
        education.add("bachelor")

    if re.search(
        r"\bphd\b|\bdoctorate\b|\bdoctoral\b",
        text
    ):
        education.add("phd")

    return education


# ============================================================
# JOB DATA
# ============================================================

def load_requirements():
    if not REQUIREMENTS_PATH.exists():
        raise FileNotFoundError(
            f"Requirement file not found: {REQUIREMENTS_PATH}"
        )

    with open(REQUIREMENTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jobs_from_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM jobs
            ORDER BY id DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def index_requirements(requirements):
    """
    Create lookup by database/source job ID.
    """

    index = {}

    if isinstance(requirements, dict):

        # Possible formats
        if isinstance(requirements.get("jobs"), list):

            for item in requirements["jobs"]:

                job_id = (
                    item.get("id")
                    or item.get("job_id")
                    or item.get("database_id")
                    or item.get("source_job_id")
                )

                if job_id is not None:
                    index[str(job_id)] = item

        else:

            for key, value in requirements.items():

                if isinstance(value, dict):
                    index[str(key)] = value

    elif isinstance(requirements, list):

        for item in requirements:

            if not isinstance(item, dict):
                continue

            job_id = (
                item.get("id")
                or item.get("job_id")
                or item.get("database_id")
                or item.get("source_job_id")
            )

            if job_id is not None:
                index[str(job_id)] = item

    return index


# ============================================================
# ROLE CLASSIFICATION
# ============================================================

def detect_role(job):
    """
    Classify job using TITLE FIRST.

    Important:
    We do NOT allow a generic role_family='genai' to
    automatically make a non-engineering title a primary match.
    """

    title = normalize_text(
        job.get("title", "")
    )

    company = normalize_text(
        job.get("company", "")
    )

    combined = f"{title} {company}"

    role_family = normalize_text(
        job.get("role_family", "")
    )

    # --------------------------------------------------------
    # 1. CLEARLY UNRELATED ROLES
    # --------------------------------------------------------

    unrelated_patterns = [

        # Marketing / communications
        r"\bmarketing\b",
        r"\bcommunications?\b",
        r"\bpublic relations\b",
        r"\bpr specialist\b",
        r"\bcontent writer\b",
        r"\bcopywriter\b",
        r"\bseo\b",
        r"\bsearch engine optimization\b",

        # Sales
        r"\bsales\b",
        r"\bbusiness development\b",
        r"\baccount executive\b",
        r"\baccount manager\b",
        r"\bsales engineer\b",

        # HR / recruiting
        r"\bhuman resources\b",
        r"\bhr manager\b",
        r"\brecruiter\b",
        r"\brecruiting\b",
        r"\btalent acquisition\b",

        # Finance
        r"\baccountant\b",
        r"\baccounting\b",
        r"\bfinancial analyst\b",

        # Legal
        r"\blawyer\b",
        r"\blegal counsel\b",
        r"\blegal\b",

        # Design/content
        r"\bdesigner\b",
        r"\bdesign specialist\b",
        r"\bgraphic designer\b",
        r"\bux designer\b",
        r"\bui designer\b",

        # Education/content roles
        r"\btutor\b",
        r"\binstructor\b",
        r"\bteacher\b",
        r"\blearning content\b",
        r"\bcontent developer\b",

        # Product/program/project management
        r"\bproduct manager\b",
        r"\bproduct management\b",
        r"\bprogram manager\b",
        r"\bproject manager\b",

        # Trading
        r"\btrader\b",
        r"\btrading analyst\b",

        # Administrative
        r"\bcoordinator\b",
        r"\badministrative\b",
        r"\badministrator\b",
    ]

    for pattern in unrelated_patterns:

        if re.search(pattern, title):

            # Exception:
            # Technical Project Manager can still be adjacent,
            # but not primary.
            return "unrelated"

    # --------------------------------------------------------
    # 2. AI LEADERSHIP
    # --------------------------------------------------------

    leadership_patterns = [

        r"\bhead of\b.*\bai\b",
        r"\bhead of\b.*\bmachine learning\b",
        r"\bhead of\b.*\bml\b",
        r"\bvp\b.*\bai\b",
        r"\bvice president\b.*\bai\b",
        r"\bdirector\b.*\bai\b",
        r"\bdirector\b.*\bmachine learning\b",
        r"\bdirector\b.*\bml\b",
        r"\bchief\b.*\bai\b",
        r"\bchief ai\b",
    ]

    for pattern in leadership_patterns:

        if re.search(pattern, title):
            return "leadership"

    # --------------------------------------------------------
    # 3. PRIMARY GENAI / LLM / RAG ENGINEERING
    # --------------------------------------------------------

    primary_genai_patterns = [

        r"\bgenai engineer\b",
        r"\bgenerative ai engineer\b",
        r"\bgenerative ai developer\b",
        r"\bgen ai engineer\b",

        r"\bllm engineer\b",
        r"\bllm developer\b",
        r"\bllmops engineer\b",
        r"\bllmops\b",

        r"\brag engineer\b",
        r"\brag developer\b",
        r"\brag applications?\b",

        r"\bai engineer\b",
        r"\bai/ml engineer\b",
        r"\bai ml engineer\b",

        r"\bmachine learning engineer\b",
        r"\bmachine learning scientist\b",

        r"\bml engineer\b",
        r"\bml scientist\b",

        r"\bai architect\b",
        r"\bgenai architect\b",
        r"\bgenerative ai architect\b",
        r"\bllm architect\b",

        r"\bai platform engineer\b",
        r"\bml platform engineer\b",
        r"\bai platform\b",

        r"\bapplied ai engineer\b",
        r"\bapplied machine learning engineer\b",

        r"\bai research engineer\b",
        r"\bmachine learning research engineer\b",

        r"\bai scientist\b",
        r"\bmachine learning scientist\b",

        r"\bdata scientist\b.*\bai\b",
        r"\bdata scientist\b.*\bgenai\b",
        r"\bdata scientist\b.*\bllm\b",
        r"\bdata science\b.*\bgenai\b",

        r"\bai solutions engineer\b",
        r"\bai solutions architect\b",

        r"\bai applications? engineer\b",
    ]

    for pattern in primary_genai_patterns:

        if re.search(pattern, title):

            return "primary"

    # --------------------------------------------------------
    # 4. MLOPS / DATA ENGINEERING WITH STRONG AI SIGNAL
    # --------------------------------------------------------

    mlops_patterns = [

        r"\bmlops\b",
        r"\bmlops engineer\b",
        r"\bml platform\b",
        r"\bmachine learning platform\b",

        r"\bllmops\b",

        r"\bdata engineer\b.*\bgenai\b",
        r"\bdata engineer\b.*\bllm\b",
        r"\bdata engineer\b.*\bai\b",

        r"\bdata engineering\b.*\bgenai\b",
    ]

    for pattern in mlops_patterns:

        if re.search(pattern, title):

            return "primary"

    # --------------------------------------------------------
    # 5. SECONDARY AI / QA / SOFTWARE ENGINEERING
    # --------------------------------------------------------

    secondary_patterns = [

        # AI testing
        r"\bai test\b",
        r"\bai testing\b",
        r"\bai qa\b",
        r"\bai quality\b",
        r"\bai test automation\b",
        r"\btest automation\b.*\bai\b",
        r"\bqa\b.*\bai\b",

        # Software engineering with AI
        r"\bsoftware engineer\b.*\bai\b",
        r"\bsoftware developer\b.*\bai\b",
        r"\bsoftware development\b.*\bai\b",

        r"\bfull stack\b.*\bai\b",
        r"\bfull-stack\b.*\bai\b",

        # Agentic / AI integration
        r"\bagentic\b",
        r"\bai applications?\b",
        r"\bai integration\b",
        r"\bai enablement\b",
        r"\bai security\b",

        # AI solutions
        r"\bai solutions?\b",
        r"\bai consultant\b",
        r"\bai consulting\b",
    ]

    for pattern in secondary_patterns:

        if re.search(pattern, title):

            return "secondary"

    # --------------------------------------------------------
    # 6. GENERIC QA
    # --------------------------------------------------------

    if re.search(
        r"\bqa\b|\bquality assurance\b|\btest engineer\b|\btest automation\b",
        title
    ):
        return "qa"

    # --------------------------------------------------------
    # 7. RELATED TECHNICAL ROLES
    # --------------------------------------------------------

    related_patterns = [

        r"\bdata scientist\b",
        r"\bdata science\b",
        r"\bdata analyst\b",

        r"\bmachine learning\b",

        r"\bsoftware engineer\b",
        r"\bsoftware developer\b",
        r"\bbackend engineer\b",
        r"\bbackend developer\b",

        r"\bfull stack\b",
        r"\bfull-stack\b",

        r"\bdevops\b",
        r"\bcloud engineer\b",
        r"\bplatform engineer\b",

        r"\bdata engineer\b",

        r"\btechnical consultant\b",
    ]

    for pattern in related_patterns:

        if re.search(pattern, title):
            return "related"

    # --------------------------------------------------------
    # 8. VERY CONTROLLED ROLE-FAMILY FALLBACK
    # --------------------------------------------------------
    #
    # Important:
    # role_family alone does NOT create a primary AI match.
    #
    # Only use it when the TITLE also contains a strong
    # technical AI signal.

    title_engineering_signal = any(
        re.search(
            pattern,
            title
        )
        for pattern in [
            r"\bai engineer\b",
            r"\bai/ml engineer\b",
            r"\bml engineer\b",
            r"\bmachine learning engineer\b",
            r"\bgenai engineer\b",
            r"\bgenerative ai engineer\b",
            r"\bllm engineer\b",
            r"\brag engineer\b",
            r"\bllmops\b",
            r"\bmlops\b",
            r"\bai architect\b",
            r"\bml architect\b",
            r"\bai platform\b",
            r"\bmachine learning\b",
            r"\bartificial intelligence\b",
        ]
    )

    if (
        role_family in {
            "genai",
            "machine_learning",
            "data_science",
        }
        and title_engineering_signal
    ):
        return "primary"

    return "unrelated"


# ============================================================
# SKILL MATCHING
# ============================================================

def skill_matches(candidate_skill, job_skill):
    """
    Flexible but controlled skill matching.
    """

    c = canonical_skill(candidate_skill)
    j = canonical_skill(job_skill)

    if not c or not j:
        return False

    if c == j:
        return True

    c_tokens = skill_tokens(c)
    j_tokens = skill_tokens(j)

    if c_tokens.intersection(j_tokens):
        return True

    # Controlled aliases
    aliases = {
        "python": {"python"},
        "pytorch": {"pytorch"},
        "tensorflow": {"tensorflow"},
        "keras": {"keras"},
        "sklearn": {"sklearn", "scikit-learn"},
        "huggingface": {"huggingface", "hugging face"},
        "llm": {"llm", "llms"},
        "rag": {
            "rag",
            "retrieval augmented generation",
            "retrieval-augmented generation",
        },
        "vector search": {
            "vector search",
            "vector database",
            "vector databases",
        },
        "vector database": {
            "vector database",
            "vector databases",
            "vector db",
            "vector search",
        },
        "semantic search": {"semantic search"},
        "prompt engineering": {
            "prompt engineering",
            "prompt-engineering",
        },
        "langchain": {"langchain"},
        "langgraph": {"langgraph"},
        "llamaindex": {"llamaindex", "llama index"},
        "fine-tuning": {
            "fine-tuning",
            "fine tuning",
            "fine-tune",
            "fine tuning",
        },
        "nlp": {
            "nlp",
            "natural language processing",
        },
        "machine learning": {
            "machine learning",
            "ml",
        },
        "deep learning": {
            "deep learning",
            "dl",
        },
    }

    for canonical, values in aliases.items():

        c_is_alias = c == canonical or c in values
        j_is_alias = j == canonical or j in values

        if c_is_alias and j_is_alias:
            return True

    return False


def find_skill_match(job_skill, candidate_skills):
    """
    Return the candidate skill that satisfies the job skill.
    """

    for candidate_skill in candidate_skills:

        if skill_matches(candidate_skill, job_skill):
            return candidate_skill

    return None


# ============================================================
# REQUIREMENT HELPERS
# ============================================================

def get_skill_requirements(req):
    """
    Safely retrieve required/preferred/context skill lists.
    """

    skills = req.get("skills", {})

    if not isinstance(skills, dict):
        return [], [], []

    required = skills.get("required", [])
    preferred = skills.get("preferred", [])
    context = skills.get("context", [])

    if not isinstance(required, list):
        required = []

    if not isinstance(preferred, list):
        preferred = []

    if not isinstance(context, list):
        context = []

    return required, preferred, context


def flatten_requirement_skill(item):
    """
    Convert a requirement item into a structure:

        {
            "type": "single" | "or" | "and",
            "skills": [...]
        }
    """

    if isinstance(item, str):

        return {
            "type": "single",
            "skills": [item],
        }

    if isinstance(item, dict):

        group_type = (
            item.get("type")
            or item.get("group_type")
            or item.get("operator")
            or ""
        )

        group_type = normalize_text(group_type)

        skills = (
            item.get("skills")
            or item.get("items")
            or item.get("values")
            or []
        )

        if isinstance(skills, str):
            skills = [skills]

        if not isinstance(skills, list):
            skills = []

        if group_type in {"or", "any"}:

            return {
                "type": "or",
                "skills": skills,
            }

        if group_type in {"and", "all"}:

            return {
                "type": "and",
                "skills": skills,
            }

        # Some extractor versions use:
        # {"OR": [...]}
        if "OR" in item:

            values = item["OR"]

            if isinstance(values, str):
                values = [values]

            return {
                "type": "or",
                "skills": values,
            }

        if "AND" in item:

            values = item["AND"]

            if isinstance(values, str):
                values = [values]

            return {
                "type": "and",
                "skills": values,
            }

    return {
        "type": "single",
        "skills": [],
    }


# ============================================================
# REQUIRED SKILL SCORING
# ============================================================

def evaluate_required_skills(required_skills, candidate_skills):
    """
    Required skills = 30 points.

    No requirements:
        20 points

    This avoids the old 0/0 = 30 problem.

    But no-requirement jobs can NEVER receive the full
    required-skill score.
    """

    if not required_skills:

        return {
            "score": 20.0,
            "matched": [],
            "missing": [],
            "coverage": None,
            "requirement_count": 0,
        }

    total = len(required_skills)

    satisfied = 0
    matched = []
    missing = []

    for item in required_skills:

        group = flatten_requirement_skill(item)

        group_type = group["type"]
        group_skills = group["skills"]

        if not group_skills:

            continue

        if group_type == "single":

            job_skill = group_skills[0]

            match = find_skill_match(
                job_skill,
                candidate_skills
            )

            if match:

                satisfied += 1

                matched.append({
                    "required": job_skill,
                    "candidate": match,
                })

            else:

                missing.append(job_skill)

        elif group_type == "or":

            matched_option = None

            for option in group_skills:

                match = find_skill_match(
                    option,
                    candidate_skills
                )

                if match:

                    matched_option = {
                        "required": option,
                        "candidate": match,
                    }

                    break

            if matched_option:

                satisfied += 1
                matched.append(matched_option)

            else:

                missing.append({
                    "OR": group_skills
                })

        elif group_type == "and":

            group_matched = []
            group_missing = []

            for skill in group_skills:

                match = find_skill_match(
                    skill,
                    candidate_skills
                )

                if match:

                    group_matched.append({
                        "required": skill,
                        "candidate": match,
                    })

                else:

                    group_missing.append(skill)

            if not group_missing:

                satisfied += 1
                matched.extend(group_matched)

            else:

                missing.append({
                    "AND": group_missing
                })

    coverage = satisfied / total if total else 0

    score = coverage * 30.0

    return {
        "score": round(score, 2),
        "matched": matched,
        "missing": missing,
        "coverage": round(coverage, 3),
        "requirement_count": total,
    }


# ============================================================
# PREFERRED SKILLS
# ============================================================

def evaluate_preferred_skills(preferred_skills, candidate_skills):

    if not preferred_skills:

        return {
            "score": 0.0,
            "matched": [],
        }

    matched = []

    for item in preferred_skills:

        group = flatten_requirement_skill(item)

        for skill in group["skills"]:

            match = find_skill_match(
                skill,
                candidate_skills
            )

            if match:

                matched.append({
                    "preferred": skill,
                    "candidate": match,
                })

                break

    # Maximum 10 points
    coverage = (
        len(matched) / len(preferred_skills)
        if preferred_skills
        else 0
    )

    score = min(
        10.0,
        coverage * 10.0
    )

    return {
        "score": round(score, 2),
        "matched": matched,
    }


# ============================================================
# EXPERIENCE
# ============================================================

def extract_required_experience(req, job):
    """
    Look for numeric years in requirement extraction first,
    then job description.
    """

    experience = req.get("experience", [])

    if isinstance(experience, dict):

        experience = [
            experience
        ]

    if isinstance(experience, list):

        for item in experience:

            text = ""

            if isinstance(item, str):
                text = item

            elif isinstance(item, dict):

                text = " ".join(
                    str(v)
                    for v in item.values()
                    if v is not None
                )

            match = re.search(
                r"(\d+(?:\.\d+)?)\s*\+?\s*years?",
                text.lower()
            )

            if match:

                return float(match.group(1))

    description = normalize_text(
        job.get("description", "")
    )

    # Only inspect sentences that clearly describe experience
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+of\s+experience",
        r"minimum\s+of\s+(\d+(?:\.\d+)?)\s*years?",
        r"at\s+least\s+(\d+(?:\.\d+)?)\s*years?",
        r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*years?",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            description
        )

        if match:

            return float(match.group(1))

    return None


def score_experience(required_years, candidate_years):

    if required_years is None:

        return {
            "score": 7.0,
            "required": None,
            "candidate": candidate_years,
            "status": "not_specified",
        }

    if candidate_years >= required_years:

        return {
            "score": 10.0,
            "required": required_years,
            "candidate": candidate_years,
            "status": "meets",
        }

    gap = required_years - candidate_years

    # Significant shortfall
    if gap >= 4:

        score = 0.0

    elif gap >= 3:

        score = 2.0

    elif gap >= 2:

        score = 4.0

    elif gap >= 1:

        score = 5.0

    else:

        score = 7.0

    return {
        "score": score,
        "required": required_years,
        "candidate": candidate_years,
        "status": "shortfall",
        "gap": round(gap, 1),
    }


# ============================================================
# EDUCATION
# ============================================================

def score_education(req, candidate_education):

    education = req.get("education", [])

    if not education:

        return {
            "score": 3.0,
            "status": "not_specified",
            "matched": [],
        }

    if isinstance(education, dict):
        education = [education]

    matched = []

    for item in education:

        if isinstance(item, str):

            text = normalize_text(item)

        elif isinstance(item, dict):

            text = normalize_text(
                " ".join(
                    str(v)
                    for v in item.values()
                    if v is not None
                )
            )

        else:

            continue

        required_level = None

        if "phd" in text or "doctorate" in text:
            required_level = "phd"

        elif "master" in text or "msc" in text or "ms " in text:
            required_level = "master"

        elif (
            "bachelor" in text
            or "btech" in text
            or "b.tech" in text
            or "degree" in text
        ):
            required_level = "bachelor"

        if not required_level:
            continue

        if required_level == "phd":

            if "phd" in candidate_education:
                matched.append(required_level)

        elif required_level == "master":

            if (
                "master" in candidate_education
                or "phd" in candidate_education
            ):
                matched.append(required_level)

        elif required_level == "bachelor":

            if (
                "bachelor" in candidate_education
                or "master" in candidate_education
                or "phd" in candidate_education
            ):
                matched.append(required_level)

    if matched:

        return {
            "score": 5.0,
            "status": "meets",
            "matched": matched,
        }

    return {
        "score": 0.0,
        "status": "not_met",
        "matched": [],
    }


# ============================================================
# LOCATION
# ============================================================

def location_score(job):

    location = normalize_text(
        job.get("location", "")
    )

    location_codes = normalize_text(
        job.get("location_codes", "")
    )

    remote_type = normalize_text(
        job.get("remote_type", "")
    )

    location_restrictions = normalize_text(
        job.get("location_restrictions", "")
    )

    worldwide = bool(
        job.get("worldwide")
    )

    remote = bool(
        job.get("remote")
    )

    combined = " ".join([
        location,
        location_codes,
        remote_type,
        location_restrictions,
    ])

    # Worldwide remote
    if worldwide:

        return {
            "score": 5.0,
            "status": "worldwide",
        }

    # Explicit India
    if re.search(
        r"\bindia\b|\bind\b|\bin\s*india\b",
        combined
    ):

        return {
            "score": 5.0,
            "status": "india",
        }

    # Hyderabad
    if "hyderabad" in combined:

        return {
            "score": 5.0,
            "status": "hyderabad",
        }

    # Remote with no restrictive geography
    if remote:

        # If explicit non-India restriction exists,
        # don't call it fully eligible.
        restrictive_patterns = [
            r"\bunited states only\b",
            r"\bu\.s\. only\b",
            r"\bus only\b",
            r"\bcanada only\b",
            r"\buk only\b",
            r"\beurope only\b",
            r"\beu only\b",
        ]

        if any(
            re.search(pattern, combined)
            for pattern in restrictive_patterns
        ):

            return {
                "score": 1.0,
                "status": "restricted_remote",
            }

        return {
            "score": 4.0,
            "status": "remote_unclear",
        }

    return {
        "score": 1.0,
        "status": "unclear",
    }


# ============================================================
# ROLE SCORE
# ============================================================

def role_score(role):

    mapping = {
        "primary": 40.0,
        "secondary": 28.0,
        "qa": 22.0,
        "related": 18.0,
        "leadership": 20.0,
        "unrelated": 0.0,
    }

    return mapping.get(
        role,
        0.0
    )


# ============================================================
# FINAL SCORE
# ============================================================

def calculate_score(
    job,
    req,
    candidate_skills,
    candidate_years,
    candidate_education,
):

    role = detect_role(job)

    role_points = role_score(role)

    required_skills = get_skill_requirements(req)

    required_result = evaluate_required_skills(
        required_skills[0],
        candidate_skills
    )

    preferred_result = evaluate_preferred_skills(
        required_skills[1],
        candidate_skills
    )

    required_years = extract_required_experience(
        req,
        job
    )

    experience_result = score_experience(
        required_years,
        candidate_years
    )

    education_result = score_education(
        req,
        candidate_education
    )

    location_result = location_score(job)

    total = (
        role_points
        + required_result["score"]
        + preferred_result["score"]
        + experience_result["score"]
        + education_result["score"]
        + location_result["score"]
    )

    # --------------------------------------------------------
    # HARDER CAPS FOR CLEARLY WRONG JOBS
    # --------------------------------------------------------

    if role == "unrelated":

        total = min(total, 35.0)

    elif role == "leadership":

        # Candidate has 6 years, so director/head roles
        # should not outrank normal target engineering jobs.
        total = min(total, 55.0)

    # Open applications are weakly defined
    title = normalize_text(
        job.get("title", "")
    )

    if (
        "open application" in title
        or "don't see what you're looking for" in title
    ):

        total = min(total, 55.0)

    # --------------------------------------------------------
    # EXPERIENCE HARD PENALTY
    # --------------------------------------------------------

    if experience_result["status"] == "shortfall":

        gap = experience_result.get(
            "gap",
            0
        )

        if gap >= 3:
            total = min(total, 65.0)

        elif gap >= 2:
            total = min(total, 75.0)

    # --------------------------------------------------------
    # REQUIRED SKILL PENALTY
    # --------------------------------------------------------

    if required_result["requirement_count"] > 0:

        coverage = required_result["coverage"]

        if coverage < 0.25:
            total = min(total, 50.0)

        elif coverage < 0.50:
            total = min(total, 65.0)

        elif coverage < 0.75:
            total = min(total, 80.0)

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    if total >= 80:
        bucket = "STRONG"

    elif total >= 65:
        bucket = "GOOD"

    elif total >= 50:
        bucket = "POTENTIAL"

    else:
        bucket = "LOW"

    return {
        "score": round(total, 2),
        "bucket": bucket,
        "role": role,

        "components": {
            "role": round(role_points, 2),
            "required_skills": required_result["score"],
            "preferred_skills": preferred_result["score"],
            "experience": experience_result["score"],
            "education": education_result["score"],
            "location": location_result["score"],
        },

        "required_skills": required_result,
        "preferred_skills": preferred_result,
        "experience": experience_result,
        "education": education_result,
        "location": location_result,
    }


# ============================================================
# EXPLANATION
# ============================================================

def build_explanation(result):

    reasons = []

    role = result["role"]

    if role == "primary":
        reasons.append(
            "Primary GenAI/AI/ML target role"
        )

    elif role == "secondary":
        reasons.append(
            "AI-adjacent technical role"
        )

    elif role == "qa":
        reasons.append(
            "QA/testing role with potential AI relevance"
        )

    elif role == "related":
        reasons.append(
            "Related technical role"
        )

    elif role == "leadership":
        reasons.append(
            "AI leadership role"
        )

    else:
        reasons.append(
            "Role is outside the primary target"
        )

    required = result["required_skills"]

    if required["requirement_count"] > 0:

        matched_count = len(
            required["matched"]
        )

        total_count = required["requirement_count"]

        reasons.append(
            f"Required skill coverage: "
            f"{matched_count}/{total_count}"
        )

    else:

        reasons.append(
            "No explicit required skills detected"
        )

    preferred = result["preferred_skills"]

    if preferred["matched"]:

        names = []

        for item in preferred["matched"][:5]:

            names.append(
                item["preferred"]
            )

        reasons.append(
            "Preferred skills matched: "
            + ", ".join(names)
        )

    experience = result["experience"]

    if experience["status"] == "meets":

        reasons.append(
            "Experience requirement met"
        )

    elif experience["status"] == "shortfall":

        reasons.append(
            f"Candidate is "
            f"{experience['gap']:.1f} year(s) below "
            f"stated requirement"
        )

    else:

        reasons.append(
            "Experience requirement not clearly specified"
        )

    location = result["location"]

    if location["status"] == "worldwide":
        reasons.append(
            "Worldwide remote eligibility"
        )

    elif location["status"] == "india":
        reasons.append(
            "India location eligibility"
        )

    elif location["status"] == "hyderabad":
        reasons.append(
            "Hyderabad location"
        )

    elif location["status"] == "remote_unclear":
        reasons.append(
            "Remote but geographic eligibility is unclear"
        )

    return "; ".join(reasons)


# ============================================================
# MATCH ONE JOB
# ============================================================

def match_job(
    job,
    req,
    candidate_skills,
    candidate_years,
    candidate_education,
):

    result = calculate_score(
        job=job,
        req=req,
        candidate_skills=candidate_skills,
        candidate_years=candidate_years,
        candidate_education=candidate_education,
    )

    output = {

        "job_id": job.get("id"),

        "source_job_id": job.get(
            "source_job_id"
        ),

        "title": job.get(
            "title",
            ""
        ),

        "company": job.get(
            "company",
            ""
        ),

        "location": job.get(
            "location",
            ""
        ),

        "remote": job.get(
            "remote",
            False
        ),

        "worldwide": job.get(
            "worldwide",
            False
        ),

        "source": job.get(
            "source",
            ""
        ),

        "url": job.get(
            "url",
            ""
        ),

        "source_url": job.get(
            "source_url",
            job.get("url", "")
        ),

        "application_url": job.get(
            "application_url",
            ""
        ),

        "score": result["score"],

        "bucket": result["bucket"],

        "role": result["role"],

        "components": result["components"],

        "required_skills": result[
            "required_skills"
        ],

        "preferred_skills": result[
            "preferred_skills"
        ],

        "experience": result[
            "experience"
        ],

        "education": result[
            "education"
        ],

        "location_match": result[
            "location"
        ],

        "why": build_explanation(
            result
        ),

        "matched_at": datetime.now().isoformat(),
    }

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("RAJESH AI - JOB MATCHER v1.0")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    jobs = load_jobs_from_db()

    requirements = load_requirements()

    requirement_index = index_requirements(
        requirements
    )

    candidate = load_candidate()

    candidate_skills = extract_candidate_skills(
        candidate
    )

    candidate_years = get_candidate_experience(
        candidate
    )

    candidate_education = get_candidate_education(
        candidate
    )

    print(
        f"Jobs loaded        : {len(jobs)}"
    )

    print(
        f"Candidate skills   : {len(candidate_skills)}"
    )

    print(
        f"Experience         : {candidate_years:g} years"
    )

    print(
        "Education          : "
        + ", ".join(
            sorted(candidate_education)
        )
    )

    print()

    # --------------------------------------------------------
    # SHOW FIRST SKILLS
    # --------------------------------------------------------

    print("Candidate skill sample:")

    for skill in candidate_skills[:20]:

        print(
            f"  - {skill}"
        )

    print()

    # --------------------------------------------------------
    # MATCH JOBS
    # --------------------------------------------------------

    results = []

    for job in jobs:

        job_id = job.get("id")

        req = requirement_index.get(
            str(job_id),
            {}
        )

        if not isinstance(req, dict):
            req = {}

        result = match_job(
            job=job,
            req=req,
            candidate_skills=candidate_skills,
            candidate_years=candidate_years,
            candidate_education=candidate_education,
        )

        results.append(result)

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    results.sort(
        key=lambda x: (
            x["score"],
            x["components"]["required_skills"],
            x["components"]["role"],
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    strong = sum(
        1
        for r in results
        if r["bucket"] == "STRONG"
    )

    good = sum(
        1
        for r in results
        if r["bucket"] == "GOOD"
    )

    potential = sum(
        1
        for r in results
        if r["bucket"] == "POTENTIAL"
    )

    low = sum(
        1
        for r in results
        if r["bucket"] == "LOW"
    )

    print("=" * 70)
    print("MATCH SUMMARY")
    print("=" * 70)

    print(
        f"Strong matches  : {strong}"
    )

    print(
        f"Good matches    : {good}"
    )

    print(
        f"Potential       : {potential}"
    )

    print(
        f"Low matches     : {low}"
    )

    print()

    # --------------------------------------------------------
    # TOP 20
    # --------------------------------------------------------

    print("=" * 70)
    print("TOP 20 MATCHES")
    print("=" * 70)

    for i, result in enumerate(
        results[:20],
        start=1
    ):

        print(
            f"{i:2}. "
            f"{result['title']} | "
            f"{result['company']}"
        )

        print(
            f"    Score: {result['score']:.0f} | "
            f"{result['bucket']} | "
            f"Role: {result['role']}"
        )

        required = result[
            "required_skills"
        ]

        if required["requirement_count"] > 0:

            print(
                f"    Required skills: "
                f"{len(required['matched'])}/"
                f"{required['requirement_count']}"
            )

        else:

            print(
                "    Required skills: "
                "not explicitly specified"
            )

        print(
            f"    Why: {result['why']}"
        )

        print()

    # --------------------------------------------------------
    # ROLE DISTRIBUTION
    # --------------------------------------------------------

    print("=" * 70)
    print("ROLE DISTRIBUTION")
    print("=" * 70)

    role_counts = {}

    for result in results:

        role = result["role"]

        role_counts[role] = (
            role_counts.get(role, 0)
            + 1
        )

    for role, count in sorted(
        role_counts.items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(
            f"{role:15} : {count}"
        )

    print()

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    payload = {

        "version": "1.0",

        "generated_at": datetime.now().isoformat(),

        "candidate": {

            "experience_years":
                candidate_years,

            "education":
                sorted(candidate_education),

            "skill_count":
                len(candidate_skills),

            "skills":
                candidate_skills,
        },

        "summary": {

            "jobs_loaded":
                len(jobs),

            "strong":
                strong,

            "good":
                good,

            "potential":
                potential,

            "low":
                low,
        },

        "jobs":
            results,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Saved: {OUTPUT_PATH}"
    )

    print()
    print("=" * 70)
    print("MATCHING COMPLETE")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()