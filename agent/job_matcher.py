import json
import re
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "jobs.db"
PROFILE_PATH = BASE_DIR / "output" / "candidate_profile.json"


# =========================================================
# CANONICAL SKILLS
# =========================================================

SKILL_ALIASES = {
    "generative ai": "genai",
    "generative-ai": "genai",
    "gen ai": "genai",

    "large language model": "llm",
    "large language models": "llm",
    "llms": "llm",

    "retrieval augmented generation": "rag",
    "retrieval-augmented generation": "rag",

    "hugging face": "huggingface",

    "scikit learn": "scikit-learn",

    "question answering": "question-answering",

    "semantic search": "semantic-search",

    "vector search": "vector-search",

    "vector database": "vector-database",
    "vector databases": "vector-database",

    "machine learning": "machine-learning",

    "deep learning": "deep-learning",

    "model evaluation": "model-evaluation",

    "model monitoring": "model-monitoring",

    "prompt engineering": "prompt-engineering",

    "agentic ai": "agentic-ai",

    "fine tuning": "fine-tuning",
    "fine-tuning": "fine-tuning",

    "lora/qlora": "lora",
}


KNOWN_SKILLS = [
    "python",
    "sql",
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",

    "machine learning",
    "regression",
    "classification",
    "clustering",
    "feature engineering",
    "ensemble methods",
    "xgboost",
    "lightgbm",
    "scikit-learn",

    "pytorch",
    "tensorflow",
    "keras",
    "transformers",
    "hugging face",
    "nltk",
    "spacy",
    "rnn",
    "lstm",
    "cnn",

    "llm",
    "llms",
    "prompt engineering",
    "rag",
    "retrieval augmented generation",
    "semantic search",
    "question answering",
    "embeddings",
    "vector search",
    "vector database",
    "langchain",
    "langgraph",
    "llamaindex",
    "fine-tuning",
    "lora",
    "qlora",
    "peft",
    "agentic ai",

    "mlflow",
    "model deployment",
    "model monitoring",

    "aws",
    "sagemaker",
    "azure",
    "azure ml",
    "databricks",

    "mongodb",
    "oracle",
    "sql server",
    "nosql",

    "tableau",
    "power bi",

    "apache airflow",
]


def normalize(text):
    text = text.lower()

    text = text.replace(
        "retrieval-augmented generation",
        "retrieval augmented generation"
    )

    text = text.replace(
        "fine-tuning",
        "fine tuning"
    )

    text = text.replace(
        "large language models",
        "llm"
    )

    text = text.replace(
        "large language model",
        "llm"
    )

    text = re.sub(
        r"[^a-z0-9+#./ -]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def canonical_skill(skill):

    skill = skill.lower().strip()

    return SKILL_ALIASES.get(
        skill,
        skill
    )


def contains_skill(text, skill):

    normalized_text = normalize(text)

    normalized_skill = normalize(skill)

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(normalized_skill)
        + r"(?![a-z0-9])"
    )

    return bool(
        re.search(
            pattern,
            normalized_text
        )
    )


def extract_skills(text):

    skills = set()

    for skill in KNOWN_SKILLS:

        if contains_skill(
            text,
            skill
        ):

            skills.add(
                canonical_skill(skill)
            )

    return skills


# =========================================================
# CANDIDATE
# =========================================================

def extract_candidate_skills(profile):

    return extract_skills(
        profile.get(
            "raw_text",
            ""
        )
    )


# =========================================================
# ROLE MATCHING
# =========================================================

ROLE_GROUPS = {

    "genai": [
        "genai",
        "generative ai",
        "gen ai",
        "llm",
        "large language model",
        "rag",
        "retrieval augmented generation",
        "ai engineer",
        "generative ai engineer",
        "genai engineer",
    ],

    "ml": [
        "machine learning",
        "machine learning engineer",
        "ml engineer",
        "ai/ml engineer",
        "data scientist",
    ],

    "nlp": [
        "nlp",
        "natural language processing",
        "nlp engineer",
        "language model",
    ],
}


def detect_role_family(title):

    title = normalize(title)

    matches = set()

    for family, keywords in ROLE_GROUPS.items():

        for keyword in keywords:

            if contains_skill(
                title,
                keyword
            ):

                matches.add(family)
                break

    return matches


def candidate_role_fit(title):

    families = detect_role_family(
        title
    )

    if "genai" in families:
        return True, "GenAI/LLM/RAG"

    if "nlp" in families:
        return True, "NLP"

    if "ml" in families:
        return True, "ML/Data Science"

    return False, "No target role family"


# =========================================================
# LOCATION
# =========================================================

def location_fit(job):

    remote_type = (
        job["remote_type"] or ""
    ).lower()

    location = (
        job["location"] or ""
    ).lower()

    restrictions = (
        job["location_restrictions"] or ""
    ).lower()

    combined = (
        remote_type
        + " "
        + location
        + " "
        + restrictions
    )

    if "worldwide" in combined:

        return True, "Worldwide"

    if "india" in combined:

        return True, "India eligible"

    if remote_type == "remote" and not location:

        return True, "Remote; location unspecified"

    return False, "India eligibility not confirmed"


# =========================================================
# EMPLOYMENT
# =========================================================

def employment_fit(job):

    employment = (
        job["employment_type"] or ""
    ).lower()

    if not employment:

        return True, "Not specified"

    if "full" in employment:

        return True, "Full-time"

    return False, employment


# =========================================================
# MATCH
# =========================================================

def match_job(
    job,
    candidate_skills
):

    title = job["title"] or ""

    description = job["description"] or ""

    skills_text = job["skills"] or ""

    job_text = (
        title
        + " "
        + description
        + " "
        + skills_text
    )

    role_ok, role_reason = (
        candidate_role_fit(title)
    )

    location_ok, location_reason = (
        location_fit(job)
    )

    employment_ok, employment_reason = (
        employment_fit(job)
    )

    job_skills = extract_skills(
        job_text
    )

    matched = sorted(
        candidate_skills
        & job_skills
    )

    gaps = sorted(
        job_skills
        - candidate_skills
    )

    # We deliberately do NOT call this
    # "percentage fit".
    #
    # It is simply skill coverage among
    # the skills detectable by our current
    # dictionary.

    if job_skills:

        skill_coverage = (
            len(matched)
            / len(job_skills)
        )

    else:

        skill_coverage = None

    if not role_ok:

        classification = "LOW"

    elif not location_ok:

        classification = "REVIEW"

    elif (
        skill_coverage is not None
        and skill_coverage >= 0.60
    ):

        classification = "STRONG"

    elif (
        skill_coverage is not None
        and skill_coverage >= 0.30
    ):

        classification = "POTENTIAL"

    else:

        classification = "REVIEW"

    return {

        "job_id": job["id"],

        "title": title,

        "company": job["company"],

        "classification":
            classification,

        "role_fit":
            role_ok,

        "role_reason":
            role_reason,

        "location_fit":
            location_ok,

        "location_reason":
            location_reason,

        "employment_fit":
            employment_ok,

        "employment_reason":
            employment_reason,

        "job_skills":
            sorted(job_skills),

        "matched_skills":
            matched,

        "skill_gaps":
            gaps,

        "skill_coverage":
            skill_coverage,

        "source_url":
            job["source_url"],

        "application_url":
            job["application_url"],
    }


# =========================================================
# DATABASE
# =========================================================

def get_jobs():

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = sqlite3.Row

    rows = connection.execute("""
        SELECT *
        FROM jobs
        ORDER BY id DESC
    """).fetchall()

    connection.close()

    return rows


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 70)
    print("NEXPLY - EXPLAINABLE JOB MATCHER")
    print("=" * 70)

    if not PROFILE_PATH.exists():

        print(
            "Candidate profile not found."
        )

        return

    with open(
        PROFILE_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        profile = json.load(file)

    candidate_skills = (
        extract_candidate_skills(
            profile
        )
    )

    print()
    print(
        "Canonical candidate skills:",
        len(candidate_skills)
    )

    print()
    print(
        ", ".join(
            sorted(candidate_skills)
        )
    )

    jobs = get_jobs()

    results = []

    for job in jobs:

        results.append(
            match_job(
                job,
                candidate_skills
            )
        )

    counts = {}

    for result in results:

        value = result[
            "classification"
        ]

        counts[value] = (
            counts.get(value, 0) + 1
        )

    print()
    print("MATCH SUMMARY")
    print("-" * 50)

    for value in [
        "STRONG",
        "POTENTIAL",
        "REVIEW",
        "LOW",
    ]:

        print(
            f"{value}: "
            f"{counts.get(value, 0)}"
        )

    priority = {
        "STRONG": 0,
        "POTENTIAL": 1,
        "REVIEW": 2,
        "LOW": 3,
    }

    results.sort(
        key=lambda x: (
            priority[
                x["classification"]
            ],

            -(
                x["skill_coverage"]
                if x["skill_coverage"]
                is not None
                else -1
            ),
        )
    )

    print()
    print("TOP 20")
    print("-" * 70)

    for result in results[:20]:

        print()
        print(
            f'[{result["classification"]}] '
            f'{result["title"]}'
        )

        print(
            f'Company: '
            f'{result["company"]}'
        )

        print(
            f'Role: '
            f'{result["role_reason"]}'
        )

        print(
            f'Location: '
            f'{result["location_reason"]}'
        )

        if result["skill_coverage"] is not None:

            print(
                f'Detectable skill coverage: '
                f'{result["skill_coverage"]:.0%}'
            )

        if result["matched_skills"]:

            print(
                "Matched: "
                + ", ".join(
                    result[
                        "matched_skills"
                    ]
                )
            )

        if result["skill_gaps"]:

            print(
                "Gaps: "
                + ", ".join(
                    result[
                        "skill_gaps"
                    ]
                )
            )

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()