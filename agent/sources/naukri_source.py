"""
RAJESH AI - Naukri Source
Scrapes Indian job listings from Naukri.com
"""
from __future__ import annotations

import re
import time
import logging
from urllib.parse import quote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.sources.base_source import BaseJobSource, Job

logger = logging.getLogger(__name__)


class NaukriSource(BaseJobSource):
    """Scrapes Naukri.com job listings for India-based roles."""

    name = "naukri"

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.naukri.com/",
        "Accept": "application/json, text/plain, */*",
        "appid": "109",
        "systemid": "109",
    }

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        max_jobs = self._config.get("max_jobs_per_run", 50)

        for role in roles[:5]:
            if len(jobs) >= max_jobs:
                break
            try:
                fetched = self._fetch_role(role)
                for job in fetched:
                    if job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)
                time.sleep(2)
            except Exception as e:
                logger.error(f"Naukri fetch failed for '{role}': {e}")

        return jobs[:max_jobs]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def _fetch_role(self, role: str) -> list[Job]:
        """Fetch jobs via Naukri's search API."""
        url = (
            f"https://www.naukri.com/jobapi/v3/search"
            f"?noOfResults=50"
            f"&urlType=search_by_keyword"
            f"&searchType=adv"
            f"&keyword={quote(role)}"
            f"&location=india"
            f"&experience=4"
            f"&sort=1"
        )

        try:
            resp = httpx.get(url, headers=self._HEADERS, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
            job_list = data.get("jobDetails", [])
            return [self._normalize(j) for j in job_list if isinstance(j, dict)]
        except Exception:
            # Fallback to HTML scraping
            return self._scrape_html(role)

    def _scrape_html(self, role: str) -> list[Job]:
        """Fallback HTML scraper using BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed")
            return []

        url = f"https://www.naukri.com/{quote(role.lower().replace(' ', '-'))}-jobs"
        resp = httpx.get(url, headers=self._HEADERS, timeout=20.0)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        jobs = []

        for card in soup.select("article.jobTuple"):
            try:
                title = card.select_one("a.title")
                company = card.select_one("a.subTitle")
                location = card.select_one("li.location")
                link = card.select_one("a.title")

                if not title or not company:
                    continue

                job_url = link.get("href", "") if link else ""
                job_id = re.search(r"-(\d+)\.htm", job_url)

                jobs.append(Job(
                    source_job_id=job_id.group(1) if job_id else job_url,
                    title=title.get_text(strip=True),
                    company=company.get_text(strip=True),
                    location=location.get_text(strip=True) if location else "India",
                    source="naukri",
                    url=job_url,
                    employment_type="Full-time",
                ))
            except Exception:
                continue

        return jobs

    def _normalize(self, job: dict) -> Job:
        locations = job.get("placeholders", [])
        location_text = ""
        for p in locations:
            if p.get("type") == "location":
                location_text = p.get("label", "")
                break

        salary_label = ""
        for p in job.get("placeholders", []):
            if p.get("type") == "salary":
                salary_label = p.get("label", "")

        return Job(
            source_job_id=str(job.get("jobId", "")),
            title=str(job.get("title", "")).strip(),
            company=str(job.get("companyName", "")).strip(),
            location=location_text or "India",
            remote_type="Remote" if "remote" in location_text.lower() else "",
            source="naukri",
            url=f"https://www.naukri.com{job.get('jdURL', '')}",
            description=str(job.get("jobDescription", "")),
            employment_type="Full-time",
            seniority=str(job.get("experienceText", "")),
            skills=", ".join(job.get("tagsAndSkills", "").split(",")),
        )
