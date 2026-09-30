"""
NEXPLY - Himalayas Source
Fetches remote jobs from https://himalayas.app/jobs/api
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agent.sources.base_source import BaseJobSource, Job


class HimalayasSource(BaseJobSource):
    """Scrapes Himalayas.app remote job listings."""

    name = "himalayas"
    _API_BASE = "https://himalayas.app/jobs/api"

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set[str] = set()

        search_queries = self._build_queries(roles)
        max_per_source = self._config.get("max_jobs_per_run", 100)

        for query in search_queries:
            if len(jobs) >= max_per_source:
                break
            try:
                fetched = self._fetch_query(query)
                for job in fetched:
                    if job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)
                time.sleep(1.0)  # Polite rate limit
            except Exception as e:
                self._logger.error(f"Himalayas query '{query}' failed: {e}")

        return jobs[:max_per_source]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _fetch_query(self, query: str) -> list[Job]:
        url = f"{self._API_BASE}?q={quote(query)}&limit=100"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        raw_jobs = data if isinstance(data, list) else data.get("jobs", [])
        return [self._normalize(j) for j in raw_jobs if isinstance(j, dict)]

    def _normalize(self, job: dict) -> Job:
        locations = job.get("locationRestrictions") or []
        location_names, location_codes = [], []

        for loc in locations:
            if isinstance(loc, dict):
                if loc.get("name"):
                    location_names.append(loc["name"])
                if loc.get("alpha2"):
                    location_codes.append(loc["alpha2"])
            else:
                location_names.append(str(loc))

        seniority = job.get("seniority") or []
        if isinstance(seniority, list):
            seniority = ", ".join(str(s) for s in seniority)

        categories = job.get("categories") or job.get("category") or []
        if isinstance(categories, list):
            skills = ", ".join(str(c) for c in categories)
        else:
            skills = str(categories)

        timezones = job.get("timezoneRestrictions") or []
        if isinstance(timezones, list):
            timezone_text = ", ".join(str(t) for t in timezones)
        else:
            timezone_text = str(timezones)

        remote_type = "Worldwide" if not locations else "Remote"

        return Job(
            source_job_id=str(job.get("guid") or ""),
            title=str(job.get("title") or "").strip(),
            company=str(job.get("companyName") or "").strip(),
            location=", ".join(location_names),
            location_codes=", ".join(location_codes),
            remote_type=remote_type,
            timezone_restrictions=timezone_text,
            source="himalayas",
            url=str(job.get("applicationLink") or "").strip(),
            description=_clean_html(job.get("description") or ""),
            skills=skills,
            employment_type=str(job.get("employmentType") or ""),
            seniority=seniority,
            salary_min=job.get("minSalary"),
            salary_max=job.get("maxSalary"),
            salary_currency=str(job.get("currency") or ""),
            salary_period=str(job.get("salaryPeriod") or "annual"),
            published_at=str(job.get("pubDate") or ""),
            expires_at=str(job.get("expiryDate") or ""),
        )

    @staticmethod
    def _build_queries(roles: list[str]) -> list[str]:
        """Map role names to Himalayas search queries."""
        query_map = {
            "GenAI Engineer": "generative ai engineer",
            "Generative AI Engineer": "generative ai engineer",
            "RAG Engineer": "rag engineer",
            "LLM Engineer": "llm engineer",
            "AI/ML Engineer": "ai ml engineer",
            "Machine Learning Engineer": "machine learning engineer",
            "NLP Engineer": "nlp engineer",
        }
        queries = []
        seen = set()
        for role in roles:
            q = query_map.get(role, role.lower())
            if q not in seen:
                seen.add(q)
                queries.append(q)
        return queries


def _clean_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
