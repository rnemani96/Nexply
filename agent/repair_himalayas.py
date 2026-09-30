import requests
import time

from database import get_connection

API_URL = "https://himalayas.app/jobs/api/search"


def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, list):
        return ", ".join(str(x) for x in value)

    return str(value)


def normalize_locations(locations):
    names = []
    codes = []

    for item in locations or []:
        if isinstance(item, dict):
            if item.get("name"):
                names.append(str(item["name"]))

            if item.get("alpha2"):
                codes.append(str(item["alpha2"]))
        else:
            names.append(str(item))

    return ", ".join(names), ", ".join(codes)


def normalize_seniority(value):
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)

    return clean_text(value)


def normalize_timezone(value):
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)

    return clean_text(value)


def fetch_job_by_guid(guid):
    """
    Search using the listing URL's identifying slug.
    We use the existing GUID as the source identifier.
    """

    # Extract the final slug from the Himalayas job URL.
    slug = guid.rstrip("/").split("/")[-1]

    response = requests.get(
        API_URL,
        params={
            "q": slug,
            "page": 1
        },
        timeout=30,
        headers={
            "User-Agent": "RajeshAI-JobAgent/0.1"
        }
    )

    response.raise_for_status()

    jobs = response.json().get("jobs", [])

    for job in jobs:
        if job.get("guid") == guid:
            return job

    return None


def repair_job(connection, old_row, job):
    locations, location_codes = normalize_locations(
        job.get("locationRestrictions")
    )

    timezone = normalize_timezone(
        job.get("timezoneRestrictions")
    )

    seniority = normalize_seniority(
        job.get("seniority")
    )

    categories = job.get("categories") or []

    skills = ", ".join(
        str(x) for x in categories
    )

    if locations:
        remote_type = "Remote"
    else:
        remote_type = "Worldwide"

    connection.execute(
        """
        UPDATE jobs
        SET
            source_job_id = ?,
            title = ?,
            company = ?,
            location = ?,
            location_codes = ?,
            remote_type = ?,
            timezone_restrictions = ?,
            description = ?,
            skills = ?,
            employment_type = ?,
            seniority = ?,
            salary_min = ?,
            salary_max = ?,
            salary_currency = ?,
            salary_period = ?,
            published_at = ?,
            expires_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            job.get("guid", ""),
            clean_text(job.get("title")),
            clean_text(job.get("companyName")),
            locations,
            location_codes,
            remote_type,
            timezone,
            clean_text(job.get("description")),
            skills,
            clean_text(job.get("employmentType")),
            seniority,
            job.get("minSalary"),
            job.get("maxSalary"),
            clean_text(job.get("currency")),
            clean_text(job.get("salaryPeriod")) or "annual",
            clean_text(job.get("pubDate")),
            clean_text(job.get("expiryDate")),
            old_row["id"]
        )
    )


def main():
    print("=" * 60)
    print("RAJESH AI - HIMALAYAS DATABASE REPAIR")
    print("=" * 60)

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT id, url
        FROM jobs
        WHERE source = 'Himalayas'
        ORDER BY id
        """
    ).fetchall()

    print(f"Jobs to inspect: {len(rows)}")
    print()

    repaired = 0
    not_found = 0
    failed = 0

    for index, row in enumerate(rows, start=1):

        try:
            job = fetch_job_by_guid(row["url"])

            if job is None:
                not_found += 1
                print(
                    f"[{index}/{len(rows)}] "
                    f"NOT FOUND | {row['id']}"
                )
                continue

            repair_job(
                connection,
                row,
                job
            )

            repaired += 1

            print(
                f"[{index}/{len(rows)}] "
                f"REPAIRED | "
                f"{job.get('title', '')}"
            )

            connection.commit()

            # Be conservative with API requests.
            time.sleep(0.25)

        except Exception as error:
            failed += 1

            print(
                f"[{index}/{len(rows)}] "
                f"FAILED | {row['id']} | {error}"
            )

    connection.commit()
    connection.close()

    print()
    print("=" * 60)
    print("REPAIR RESULT")
    print("=" * 60)
    print(f"Repaired  : {repaired}")
    print(f"Not found : {not_found}")
    print(f"Failed    : {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()