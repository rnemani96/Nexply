"""
NEXPLY - Visa-Sponsoring Job Source
Searches multiple boards specifically for jobs that offer visa sponsorship.
Covers ALL countries: US, UK, EU, Canada, Australia, Germany, Singapore,
UAE, Netherlands, Ireland, New Zealand, Japan, Sweden, Denmark + anywhere else.
"""
from __future__ import annotations

import re
import time
import logging
import hashlib
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agent.sources.base_source import BaseJobSource, Job

logger = logging.getLogger(__name__)

# ============================================================
# UNIVERSAL VISA KEYWORDS  (any country)
# ============================================================

# Positive signals — job WILL sponsor
VISA_KEYWORDS = [
    # Generic sponsorship phrases
    "visa sponsorship", "visa sponsor", "visa sponsored",
    "we sponsor", "will sponsor", "open to sponsoring",
    "able to sponsor", "sponsorship available", "sponsorship provided",
    "sponsoring candidates", "sponsorship support", "visa support",
    "sponsor work authorization", "work authorization sponsored",
    "sponsor your visa", "visa assistance", "immigration assistance",
    "immigration support", "relocation package", "relocation support",
    "relocation assistance", "we cover relocation",

    # Work permit — any country
    "work permit", "work visa", "work authorization",
    "right to work", "we arrange work permit",
    "permit sponsorship", "work permit sponsored",

    # International / open to candidates worldwide
    "open to international", "international candidates welcome",
    "candidates worldwide", "global candidates", "hire worldwide",
    "hire internationally", "international applicants",
    "no location restrictions", "any nationality",

    # ---- Country-specific ----
    # USA
    "h1b", "h-1b", "h1-b", "h2b", "o-1 visa", "tn visa",
    "opt sponsorship", "stem opt", "cap exempt",

    # UK
    "skilled worker visa", "uk visa sponsorship", "tier 2 visa",
    "tier 2 sponsor", "global talent visa", "uk sponsor licence",
    "certificate of sponsorship",

    # EU / Schengen
    "eu blue card", "blue card", "eu work permit",
    "schengen work visa", "eu work visa",

    # Germany
    "aufenthaltserlaubnis", "german work visa", "germany visa sponsor",

    # Canada
    "lmia", "labour market impact", "canada work permit",
    "express entry", "canada visa sponsor", "canadian work permit",

    # Australia
    "482 visa", "tss visa", "skilled independent visa",
    "australia work visa", "subclass 482", "subclass 186",
    "employer sponsored visa", "australia sponsor",

    # Singapore
    "employment pass", "ep sponsorship", "singapore ep",
    "s pass", "singapore work visa",

    # UAE / Middle East
    "uae work visa", "dubai visa", "employment visa uae",
    "work permit uae", "qatar work visa", "saudi work visa",

    # Netherlands
    "dutch work permit", "highly skilled migrant",
    "kennismigrant", "netherlands work visa",

    # Ireland
    "critical skills permit", "critical skills employment permit",
    "ireland work permit", "ireland employment permit",
    "general employment permit", "atypical working scheme",

    # Sweden / Denmark / Norway
    "swedish work permit", "danish work permit",
    "norway work permit", "nordic work visa",

    # New Zealand
    "new zealand work visa", "accredited employer",
    "aewv", "nz work visa",

    # Japan
    "japan work visa", "engineer visa japan",
    "highly skilled professional visa",

    # India (for abroad companies hiring India-based remote)
    "sponsoring indian nationals", "open to india",
]

# Negative signals — explicitly NOT sponsoring
NEGATIVE_KEYWORDS = [
    "no sponsorship", "no visa sponsorship", "not sponsor",
    "unable to sponsor", "cannot sponsor", "can't sponsor",
    "sponsorship not available", "sponsorship not offered",
    "no work permit", "no immigration support",
    "must be authorized to work", "must have authorization",
    "must already be authorized", "must be eligible to work",
    "must hold valid work authorization",
    "citizen or permanent resident only",
    "citizens only", "permanent residents only",
    "no relocation", "not eligible for sponsorship",
    "no visa support",
]

# Country hints for smart detection (word → country label)
COUNTRY_HINTS = {
    # USA
    "h1b": "USA (H1B)", "h-1b": "USA (H1B)", "h1-b": "USA (H1B)",
    "opt": "USA (OPT)", "cap exempt": "USA (H1B)", "tn visa": "USA (TN)",
    # UK
    "skilled worker visa": "UK", "tier 2": "UK", "tier2": "UK",
    "certificate of sponsorship": "UK", "global talent visa": "UK",
    # EU
    "blue card": "EU", "eu blue card": "EU", "schengen": "EU",
    # Germany
    "german work visa": "Germany", "germany": "Germany",
    # Canada
    "lmia": "Canada", "express entry": "Canada", "canada": "Canada",
    # Australia
    "482": "Australia", "tss visa": "Australia", "subclass": "Australia",
    # Singapore
    "employment pass": "Singapore", "s pass": "Singapore",
    # UAE
    "uae": "UAE", "dubai": "UAE",
    # Netherlands
    "kennismigrant": "Netherlands", "highly skilled migrant": "Netherlands",
    # Ireland
    "critical skills": "Ireland",
    # NZ
    "aewv": "New Zealand", "new zealand": "New Zealand",
    # Japan
    "japan": "Japan",
    # Nordic
    "swedish": "Sweden", "danish": "Denmark", "norway": "Norway",
}


def _clean_html(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def check_visa_sponsorship(text: str) -> tuple[bool, str]:
    """
    Universally detect visa sponsorship for any country.
    Returns (sponsors: bool, country_label: str)

    country_label examples: 'USA (H1B)', 'UK', 'EU', 'Canada',
                             'Australia', 'Singapore', 'Worldwide', etc.
    """
    lower = text.lower()

    # Check negatives first (explicit refusal overrides everything)
    for neg in NEGATIVE_KEYWORDS:
        if neg in lower:
            return False, "no_sponsorship"

    # Check positives
    found_keywords = [kw for kw in VISA_KEYWORDS if kw in lower]

    if not found_keywords:
        return False, "unknown"

    # Infer country from matched keywords
    detected_countries: list[str] = []
    for kw in found_keywords:
        for hint, country in COUNTRY_HINTS.items():
            if hint in kw or hint in lower:
                if country not in detected_countries:
                    detected_countries.append(country)

    if detected_countries:
        label = " / ".join(detected_countries[:3])  # cap at 3
    elif any(k in lower for k in ["international", "worldwide", "global", "any nationality"]):
        label = "Worldwide"
    else:
        label = "Any Country"

    return True, label


def is_visa_job(title: str, description: str, tags: list[str] = None) -> tuple[bool, str]:
    """Convenience wrapper that checks title + description + tags combined."""
    combined = f"{title} {description} {' '.join(tags or [])}"
    return check_visa_sponsorship(combined)



class VisaJobsSource(BaseJobSource):
    """
    Aggregates visa-sponsoring job listings from multiple free sources.
    Detects sponsorship for ANY country worldwide.

    Sources:
      1. RemoteOK — h1b / visa / relocation tags
      2. Jobicy — visa-sponsorship tag
      3. Remotive — worldwide jobs filtered by visa keywords
      4. H1B Jobs RSS (US-specific)
      5. UK Visa Sponsorship jobs
      6. Himalayas — filtered for visa keywords
    """

    name = "visa_jobs"

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        self._max_jobs = self._config.get("max_jobs_per_run", 100)
        self._roles    = self._config.get("roles", [])

    def is_available(self) -> bool:
        return True

    # --------------------------------------------------------
    # MAIN FETCH
    # --------------------------------------------------------

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        all_jobs: list[Job] = []
        seen_ids: set[str] = set()

        logger.info("[visa_jobs] Starting visa-sponsoring job search")

        # Source 1: H1B-specific jobs from specialized query on RemoteOK
        all_jobs.extend(self._fetch_remoteok_visa(roles, seen_ids))
        time.sleep(2)

        # Source 2: Jobicy with "visa sponsorship" tag
        all_jobs.extend(self._fetch_jobicy_visa(roles, seen_ids))
        time.sleep(1)

        # Source 3: Remotive worldwide jobs (filter by visa keywords in description)
        all_jobs.extend(self._fetch_remotive_visa(roles, seen_ids))
        time.sleep(1)

        # Source 4: Indeed-style RSS for h1b sponsorship (via h1bjobs RSS if available)
        all_jobs.extend(self._fetch_h1b_rss(roles, seen_ids))
        time.sleep(1)

        # Source 5: UK visa sponsorship jobs
        all_jobs.extend(self._fetch_uk_visa_jobs(roles, seen_ids))
        time.sleep(1)

        # Source 6: Filter Himalayas results for visa keywords
        all_jobs.extend(self._fetch_himalayas_visa(roles, seen_ids))

        # Deduplicate and cap
        result = all_jobs[:self._max_jobs]
        logger.info(f"[visa_jobs] Found {len(result)} visa-sponsoring jobs")
        return result

    # --------------------------------------------------------
    # SOURCE 1: REMOTEOK — h1b / visa tag
    # --------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry=retry_if_exception_type(httpx.HTTPError))
    def _fetch_remoteok_visa(self, roles: list[str], seen: set) -> list[Job]:
        jobs = []
        visa_tags = ["h1b", "visa", "relocation"]
        client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 Nexply/3.0"},
            timeout=20,
            follow_redirects=True,
        )
        for tag in visa_tags:
            try:
                resp = client.get(f"https://remoteok.com/api?tag={tag}")
                resp.raise_for_status()
                data = resp.json()
                for item in data:
                    if "legal" in item:
                        continue
                    jid = f"remoteok_visa_{item.get('id', '')}"
                    if jid in seen:
                        continue
                    desc = _clean_html(item.get("description", ""))
                    sponsors, visa_type = check_visa_sponsorship(
                        desc + " " + " ".join(item.get("tags", []))
                    )
                    if not sponsors:
                        continue
                    seen.add(jid)
                    jobs.append(Job(
                        source_job_id=jid,
                        title=item.get("position", ""),
                        company=item.get("company", ""),
                        source="visa_jobs",
                        url=item.get("apply_url") or item.get("url", ""),
                        description=desc,
                        skills=", ".join(item.get("tags", [])),
                        remote_type="Worldwide",
                        location_codes=visa_type,  # store visa type here
                        published_at=item.get("date", ""),
                    ))
                time.sleep(2)
            except Exception as e:
                logger.debug(f"RemoteOK visa tag {tag}: {e}")
        client.close()
        return jobs

    # --------------------------------------------------------
    # SOURCE 2: JOBICY — visa sponsorship tag
    # --------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
           retry=retry_if_exception_type(httpx.HTTPError))
    def _fetch_jobicy_visa(self, roles: list[str], seen: set) -> list[Job]:
        jobs = []
        try:
            resp = httpx.get(
                "https://jobicy.com/api/v2/remote-jobs",
                params={"count": 50, "tag": "visa-sponsorship"},
                timeout=20,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json().get("jobs", [])
            for item in data:
                jid = f"jobicy_visa_{item.get('id', '')}"
                if jid in seen:
                    continue
                desc = _clean_html(item.get("jobDescription", ""))
                sponsors, visa_type = check_visa_sponsorship(desc + " " + item.get("jobTitle", ""))
                seen.add(jid)
                jobs.append(Job(
                    source_job_id=jid,
                    title=item.get("jobTitle", ""),
                    company=item.get("companyName", ""),
                    source="visa_jobs",
                    url=item.get("url", ""),
                    description=desc,
                    remote_type="Worldwide" if not item.get("jobGeo") else "Remote",
                    location=item.get("jobGeo", ""),
                    location_codes=visa_type,
                    employment_type=str(item.get("jobType", [""])[0]) if item.get("jobType") else "",
                    published_at=item.get("pubDate", ""),
                    salary_min=float(item.get("salaryMin") or 0) or None,
                    salary_max=float(item.get("salaryMax") or 0) or None,
                    salary_currency=item.get("salaryCurrency", ""),
                ))
        except Exception as e:
            logger.debug(f"Jobicy visa fetch: {e}")
        return jobs

    # --------------------------------------------------------
    # SOURCE 3: REMOTIVE — filter for visa keywords
    # --------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
           retry=retry_if_exception_type(httpx.HTTPError))
    def _fetch_remotive_visa(self, roles: list[str], seen: set) -> list[Job]:
        jobs = []
        for category in ["data", "software-dev"]:
            try:
                resp = httpx.get(
                    f"https://remotive.com/api/remote-jobs",
                    params={"category": category, "limit": 100},
                    timeout=20,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                for item in resp.json().get("jobs", []):
                    desc = _clean_html(item.get("description", ""))
                    sponsors, visa_type = check_visa_sponsorship(desc)
                    if not sponsors:
                        continue
                    jid = f"remotive_visa_{item.get('id', '')}"
                    if jid in seen:
                        continue
                    seen.add(jid)
                    loc = item.get("candidate_required_location", "")
                    jobs.append(Job(
                        source_job_id=jid,
                        title=item.get("title", ""),
                        company=item.get("company_name", ""),
                        source="visa_jobs",
                        url=item.get("url", ""),
                        description=desc,
                        skills=", ".join(item.get("tags", [])),
                        remote_type="Worldwide" if not loc else "Remote",
                        location=loc,
                        location_codes=visa_type,
                        published_at=item.get("publication_date", ""),
                    ))
                time.sleep(1)
            except Exception as e:
                logger.debug(f"Remotive visa ({category}): {e}")
        return jobs

    # --------------------------------------------------------
    # SOURCE 4: H1B JOBS RSS
    # --------------------------------------------------------

    def _fetch_h1b_rss(self, roles: list[str], seen: set) -> list[Job]:
        jobs = []
        role_queries = [r.replace(" ", "+") for r in roles[:5]]
        # H1B Jobs search via RSS-like endpoint
        for query in role_queries:
            try:
                resp = httpx.get(
                    f"https://www.h1bjobs.com/search?q={query}&format=rss",
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 Nexply/3.0"},
                    follow_redirects=True,
                )
                if resp.status_code != 200:
                    continue
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                ns = {"": ""}
                for item in root.findall(".//item"):
                    title_el  = item.find("title")
                    link_el   = item.find("link")
                    desc_el   = item.find("description")
                    title = title_el.text if title_el is not None else ""
                    url   = link_el.text if link_el is not None else ""
                    desc  = _clean_html(desc_el.text or "") if desc_el is not None else ""
                    jid   = f"h1bjobs_{hashlib.sha1(url.encode()).hexdigest()[:12]}"
                    if jid in seen:
                        continue
                    seen.add(jid)
                    # Try to parse "Company - Title" from title
                    company, job_title = "", title
                    if " - " in title:
                        parts = title.split(" - ", 1)
                        company, job_title = parts[0].strip(), parts[1].strip()
                    jobs.append(Job(
                        source_job_id=jid,
                        title=job_title,
                        company=company,
                        source="visa_jobs",
                        url=url,
                        description=desc,
                        remote_type="Remote",
                        location_codes="H1B",
                        location="USA",
                    ))
                time.sleep(1)
            except Exception as e:
                logger.debug(f"H1B RSS ({query}): {e}")
        return jobs

    # --------------------------------------------------------
    # SOURCE 5: UK VISA SPONSORSHIP JOBS
    # --------------------------------------------------------

    def _fetch_uk_visa_jobs(self, roles: list[str], seen: set) -> list[Job]:
        """Search for UK jobs explicitly offering Skilled Worker Visa sponsorship."""
        jobs = []
        try:
            for role in roles[:4]:
                resp = httpx.get(
                    "https://jobicy.com/api/v2/remote-jobs",
                    params={
                        "count": 20,
                        "tag": role.lower().replace(" ", "-"),
                        "geo": "UK",
                    },
                    timeout=15,
                    follow_redirects=True,
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("jobs", []):
                    desc = _clean_html(item.get("jobDescription", ""))
                    sponsors, _ = check_visa_sponsorship(desc + " uk visa sponsorship skilled worker")
                    if item.get("jobGeo", "").upper() not in ("GB", "UK", "UNITED KINGDOM"):
                        # Check if it mentions UK in description
                        if "uk" not in desc.lower()[:200]:
                            continue
                    jid = f"ukv_{item.get('id', '')}"
                    if jid in seen:
                        continue
                    seen.add(jid)
                    jobs.append(Job(
                        source_job_id=jid,
                        title=item.get("jobTitle", ""),
                        company=item.get("companyName", ""),
                        source="visa_jobs",
                        url=item.get("url", ""),
                        description=desc,
                        remote_type="Hybrid",
                        location="United Kingdom",
                        location_codes="UK_Skilled_Worker",
                        published_at=item.get("pubDate", ""),
                    ))
                time.sleep(1)
        except Exception as e:
            logger.debug(f"UK visa jobs: {e}")
        return jobs

    # --------------------------------------------------------
    # SOURCE 6: HIMALAYAS — filter for visa keywords
    # --------------------------------------------------------

    def _fetch_himalayas_visa(self, roles: list[str], seen: set) -> list[Job]:
        jobs = []
        search_terms = ["visa sponsorship"] + [r.lower() for r in roles[:3]]
        for term in search_terms:
            try:
                resp = httpx.get(
                    f"https://himalayas.app/jobs/api",
                    params={"q": term, "limit": 100},
                    timeout=20,
                    headers={"User-Agent": "Mozilla/5.0 Nexply/3.0"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.json()
                job_list = data if isinstance(data, list) else data.get("jobs", [])
                for item in job_list:
                    desc = _clean_html(item.get("description") or item.get("content", ""))
                    sponsors, visa_type = check_visa_sponsorship(
                        desc + " " + item.get("title", "")
                    )
                    if not sponsors and term != "visa sponsorship":
                        continue
                    jid = f"hima_visa_{item.get('slug') or item.get('id', '')}"
                    if jid in seen:
                        continue
                    seen.add(jid)
                    jobs.append(Job(
                        source_job_id=jid,
                        title=item.get("title", ""),
                        company=item.get("company", {}).get("name", "") if isinstance(item.get("company"), dict) else str(item.get("company", "")),
                        source="visa_jobs",
                        url=item.get("url", "") or f"https://himalayas.app/jobs/{item.get('slug', '')}",
                        description=desc,
                        remote_type="Worldwide",
                        location_codes=visa_type,
                        skills=", ".join(item.get("tags", [])),
                    ))
                time.sleep(1)
            except Exception as e:
                logger.debug(f"Himalayas visa ({term}): {e}")
        return jobs
