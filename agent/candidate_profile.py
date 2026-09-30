from pathlib import Path
import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.yaml"


def load_candidate_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    candidate = config.get("candidate", {})

    return {
        "target_roles": candidate.get("roles", []),
        "target_locations": candidate.get("locations", []),
        "experience_years": candidate.get("experience_years", 0),
        "employment_type": candidate.get("employment_type", []),

        # These remain empty until verified from the master resume.
        "skills": [],
        "education": [],
        "certifications": [],
        "work_history": [],
        "projects": [],
        "languages": [],
    }


def print_profile(profile):
    print("=" * 70)
    print("NEXPLY - CANDIDATE PROFILE")
    print("=" * 70)

    print()
    print("TARGET ROLES")
    print("-" * 50)

    for role in profile["target_roles"]:
        print("-", role)

    print()
    print("TARGET LOCATIONS")
    print("-" * 50)

    for location in profile["target_locations"]:
        print("-", location)

    print()
    print("EXPERIENCE")
    print("-" * 50)
    print(f'{profile["experience_years"]} years')

    print()
    print("EMPLOYMENT TYPE")
    print("-" * 50)

    for employment_type in profile["employment_type"]:
        print("-", employment_type)

    print()
    print("VERIFIED SKILLS")
    print("-" * 50)

    if profile["skills"]:
        for skill in profile["skills"]:
            print("-", skill)
    else:
        print("Not loaded yet.")

    print()
    print("=" * 70)


if __name__ == "__main__":
    profile = load_candidate_config()
    print_profile(profile)