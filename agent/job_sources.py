def normalize_job(job):

    locations = job.get("locationRestrictions", []) or []
    timezones = job.get("timezoneRestrictions", []) or []

    # Himalayas returns locations as objects:
    # {"alpha2": "US", "name": "United States", "slug": "united-states"}

    location_names = []
    location_codes = []

    for location in locations:

        if isinstance(location, dict):

            name = location.get("name", "")
            alpha2 = location.get("alpha2", "")

            if name:
                location_names.append(str(name))

            if alpha2:
                location_codes.append(str(alpha2))

        else:
            location_names.append(str(location))

    # Seniority is returned as an array.
    seniority_values = job.get("seniority", []) or []

    if isinstance(seniority_values, list):
        seniority = ", ".join(
            str(value)
            for value in seniority_values
        )
    else:
        seniority = str(seniority_values)

    # Empty location restrictions = worldwide.
    if not locations:
        remote_type = "Worldwide"
    else:
        remote_type = "Remote"

    categories = (
        job.get("categories")
        or job.get("category")
        or []
    )

    if isinstance(categories, list):
        skills = ", ".join(
            str(value)
            for value in categories
        )
    else:
        skills = str(categories)

    if isinstance(timezones, list):
        timezone_text = ", ".join(
            str(value)
            for value in timezones
        )
    else:
        timezone_text = str(timezones)

    return {
        "source_job_id": str(
            job.get("guid") or ""
        ),

        "title": str(
            job.get("title") or ""
        ).strip(),

        "company": str(
            job.get("companyName") or ""
        ).strip(),

        "location": ", ".join(
            location_names
        ),

        "location_codes": ", ".join(
            location_codes
        ),

        "remote_type": remote_type,

        "timezone_restrictions": timezone_text,

        "source": "Himalayas",

        "url": str(
            job.get("applicationLink") or ""
        ).strip(),

        "description": clean_description(
            job.get("description")
        ),

        "skills": skills,

        "employment_type": str(
            job.get("employmentType") or ""
        ),

        "seniority": seniority,

        "salary_min": job.get(
            "minSalary"
        ),

        "salary_max": job.get(
            "maxSalary"
        ),

        "salary_currency": str(
            job.get("currency") or ""
        ),

        "salary_period": str(
            job.get("salaryPeriod") or "annual"
        ),

        "published_at": str(
            job.get("pubDate") or ""
        ),

        "expires_at": str(
            job.get("expiryDate") or ""
        ),
    }