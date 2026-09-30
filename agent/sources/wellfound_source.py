"""
RAJESH AI - Wellfound (AngelList) Source
Scrapes startup and remote job listings from Wellfound.com
"""
from __future__ import annotations

import re
import time
import logging
from urllib.parse import quote

import httpx
from agent.sources.base_source import BaseJobSource, Job

logger = logging.getLogger(__name__)


class WellfoundSource(BaseJobSource):
    """Scrapes Wellfound (formerly AngelList Talent) for startup/remote jobs."""

    name = "wellfound"

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        max_jobs = self._config.get("max_jobs_per_run", 30)

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 required for Wellfound source")
            return []

        for role in roles[:3]:
            if len(jobs) >= max_jobs:
                break
            try:
                fetched = self._scrape_role(role)
                for job in fetched:
                    if job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)
                time.sleep(3)
            except Exception as e:
                logger.error(f"Wellfound scrape failed for '{role}': {e}")

        return jobs[:max_jobs]

    def _scrape_role(self, role: str) -> list[Job]:
        """Scrape Wellfound job listings for a given role."""
        from bs4 import BeautifulSoup

        # Build search URL
        slug = role.lower().replace(" ", "-").replace("/", "-")
        url = f"https://wellfound.com/jobs?role={quote(slug)}&remote=true"

        try:
            resp = httpx.get(url, headers=self._HEADERS, timeout=25.0, follow_redirects=True)
            if resp.status_code != 200:
                logger.warning(f"Wellfound returned {resp.status_code} for '{role}'")
                return []
        except Exception as e:
            logger.error(f"Wellfound request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        jobs = []

        # Job cards on Wellfound
        for card in soup.select("[data-test='StartupRow'], .styles_component__IYMr4, .job-listing"):
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception:
                continue

        # Fallback: look for JSON-LD structured data
        if not jobs:
            jobs = self._extract_json_ld(soup)

        return jobs

    def _parse_card(self, card) -> Job | None:
        """Extract job details from a Wellfound card element."""
        title_el = card.select_one("a[href*='/jobs/']")
        company_el = card.select_one("h2, .startup-name, .company-name")

        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else ""
        href = title_el.get("href", "")
        url = f"https://wellfound.com{href}" if href.startswith("/") else href

        # Extract job ID from URL
        job_id_match = re.search(r"/jobs/(\d+)", url)
        source_id = job_id_match.group(1) if job_id_match else url

        if not title:
            return None

        # Location
        location_el = card.select_one(".location, [data-test='location']")
        location = location_el.get_text(strip=True) if location_el else "Remote"

        # Salary
        salary_el = card.select_one(".compensation, [data-test='compensation']")
        salary_text = salary_el.get_text(strip=True) if salary_el else ""
        salary_min, salary_max = _parse_salary(salary_text)

        # Skills
        skill_els = card.select(".tag, .skill-tag, [data-test='skill']")
        skills = ", ".join(el.get_text(strip=True) for el in skill_els)

        return Job(
            source_job_id=source_id,
            title=title,
            company=company,
            location=location,
            remote_type="Remote" if "remote" in location.lower() else "",
            source="wellfound",
            url=url,
            skills=skills,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="USD",
            employment_type="Full-time",
        )

    def _extract_json_ld(self, soup) -> list[Job]:
        """Extract jobs from JSON-LD structured data if present."""
        import json
        jobs = []
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = [data]
                else:
                    continue

                for item in items:
                    if item.get("@type") != "JobPosting":
                        continue
                    org = item.get("hiringOrganization", {})
                    jobs.append(Job(
                        source_job_id=str(item.get("identifier", {}).get("value", "")),
                        title=str(item.get("title", "")),
                        company=str(org.get("name", "")),
                        location=str(item.get("jobLocation", {}).get("address", {}).get("addressLocality", "")),
                        remote_type="Remote" if item.get("jobLocationType") == "TELECOMMUTE" else "",
                        source="wellfound",
                        url=str(item.get("url", "")),
                        description=str(item.get("description", ""))[:5000],
                        employment_type=str(item.get("employmentType", "FULL_TIME")),
                    ))
            except Exception:
                continue
        return jobs


def _parse_salary(text: str) -> tuple[float | None, float | None]:
    """Extract min/max salary from a text like '$100k - $140k'."""
    if not text:
        return None, None
    nums = re.findall(r"[\$£€]?\s*(\d+\.?\d*)\s*[kK]?", text)
    values = []
    for n in nums:
        try:
            val = float(n)
            if val < 1000:
                val *= 1000  # Convert 120k → 120000
            values.append(val)
        except ValueError:
            pass
    if len(values) >= 2:
        return min(values), max(values)
    elif len(values) == 1:
        return values[0], None
    return None, None
