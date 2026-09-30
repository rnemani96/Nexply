"""
NEXPLY - Remotive Source
Fetches remote job listings from https://remotive.com/api/remote-jobs.

API notes:
- No authentication required.
- Response schema: {"jobs": [{...}]}
- Rate limit: wait 1 second between category requests to stay polite.
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.sources.base_source import BaseJobSource, Job

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_DEFAULT_CATEGORIES: list[str] = [
    "data",
    "software-dev",
    "testing",
    "qa",
    "machine-learning",
]

_API_BASE: str = "https://remotive.com/api/remote-jobs"
_RATE_LIMIT_SECONDS: float = 1.0

# candidate_required_location values treated as "Worldwide" remote.
_WORLDWIDE_LOCATIONS: frozenset[str] = frozenset(
    {"", "worldwide", "anywhere", "remote", "global"}
)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _clean_html(html: str) -> str:
    """Strip HTML tags from *html* and collapse whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _safe_float(value: Any) -> float | None:
    """Convert *value* to float, returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_remote_type(candidate_required_location: str) -> str:
    """Infer remote type from the *candidate_required_location* field.

    Args:
        candidate_required_location: The raw location restriction field from
            the Remotive API response.

    Returns:
        ``'Worldwide'`` when the location is empty or a worldwide indicator,
        otherwise ``'Remote'``.
    """
    normalised = (candidate_required_location or "").strip().lower()
    if normalised in _WORLDWIDE_LOCATIONS:
        return "Worldwide"
    return "Remote"


# ---------------------------------------------------------------------------
# Source plugin
# ---------------------------------------------------------------------------


class RemotiveSource(BaseJobSource):
    """Fetches remote jobs from the Remotive public REST API.

    Configuration keys (all optional):
        ``remotive_categories`` (list[str]): Override the default category list.
        ``remotive_limit`` (int): Number of jobs per category request. Default 100.
        ``max_jobs_per_run`` (int): Cap on total jobs returned. Default 200.
    """

    name = "remotive"

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """Fetch jobs for all configured categories.

        *roles* and *locations* are accepted for interface compatibility but
        the primary filter mechanism is the category list from config.

        Returns:
            A deduplicated list of :class:`~agent.sources.base_source.Job`
            objects, capped at ``max_jobs_per_run``.
        """
        categories: list[str] = self._config.get(
            "remotive_categories", _DEFAULT_CATEGORIES
        )
        limit: int = self._config.get("remotive_limit", 100)
        max_jobs: int = self._config.get("max_jobs_per_run", 200)

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for index, category in enumerate(categories):
            if len(jobs) >= max_jobs:
                self._logger.debug(
                    "Reached max_jobs_per_run=%d, stopping early.", max_jobs
                )
                break

            if index > 0:
                time.sleep(_RATE_LIMIT_SECONDS)

            try:
                fetched = self._fetch_category(category, limit)
                for job in fetched:
                    if job.source_job_id and job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)
                self._logger.info(
                    "Remotive category='%s' returned %d jobs (total so far: %d).",
                    category,
                    len(fetched),
                    len(jobs),
                )
            except Exception as exc:
                self._logger.error(
                    "Remotive category='%s' failed: %s", category, exc, exc_info=True
                )

        return jobs[:max_jobs]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _fetch_category(self, category: str, limit: int) -> list[Job]:
        """Fetch and normalise all jobs for a single *category*.

        Args:
            category: The category slug to query (e.g. ``"machine-learning"``).
            limit:    Number of results to request per API call.

        Returns:
            A list of normalised :class:`~agent.sources.base_source.Job` objects.

        Raises:
            httpx.HTTPError: On non-2xx responses (triggers tenacity retry).
        """
        url = f"{_API_BASE}?category={category}&limit={limit}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        raw_jobs: list[dict[str, Any]] = data.get("jobs", [])
        if not isinstance(raw_jobs, list):
            self._logger.warning(
                "Remotive: unexpected 'jobs' type %s for category '%s'.",
                type(raw_jobs).__name__,
                category,
            )
            return []

        return [self._normalize(j) for j in raw_jobs if isinstance(j, dict)]

    def _normalize(self, raw: dict[str, Any]) -> Job:
        """Map a raw Remotive API dict to a :class:`~agent.sources.base_source.Job`.

        Args:
            raw: A single job dict from the Remotive JSON response.

        Returns:
            A normalised :class:`~agent.sources.base_source.Job` instance.
        """
        candidate_location: str = str(
            raw.get("candidate_required_location") or ""
        ).strip()
        remote_type: str = _infer_remote_type(candidate_location)
        location: str = candidate_location if candidate_location else "Worldwide"

        # Skills: tags list joined with comma.
        raw_tags: list[str] | str = raw.get("tags") or []
        if isinstance(raw_tags, list):
            skills = ", ".join(str(t) for t in raw_tags if t)
        else:
            skills = str(raw_tags).strip()

        # Salary: Remotive returns a free-text salary string; store in description.
        # We also attempt to persist it as skills metadata if numeric parsing fails.
        salary_text: str = str(raw.get("salary") or "").strip()

        return Job(
            source_job_id=str(raw.get("id") or "").strip(),
            title=str(raw.get("title") or "").strip(),
            company=str(raw.get("company_name") or "").strip(),
            location=location,
            remote_type=remote_type,
            source=self.name,
            url=str(raw.get("url") or "").strip(),
            description=_clean_html(raw.get("description") or ""),
            skills=skills,
            employment_type=str(raw.get("job_type") or "").strip(),
            # Remotive salary is a free-text string; store in salary_period for visibility.
            salary_period=salary_text,
            published_at=str(raw.get("publication_date") or "").strip(),
        )
