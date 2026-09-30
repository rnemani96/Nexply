"""
RAJESH AI - Jobicy Source
Fetches remote job listings from https://jobicy.com/api/v2/remote-jobs.

API notes:
- No authentication required.
- Response schema: {"jobs": [{...}]}
- Rate limit: wait 1 second between tag requests to stay polite.
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

_DEFAULT_TAGS: list[str] = [
    "machine-learning",
    "data-science",
    "artificial-intelligence",
    "quality-assurance",
    "nlp",
    "python",
]

_API_BASE: str = "https://jobicy.com/api/v2/remote-jobs"
_RATE_LIMIT_SECONDS: float = 1.0

# jobGeo values treated as "Worldwide" remote.
_WORLDWIDE_GEO: frozenset[str] = frozenset({"", "worldwide", "anywhere", "remote"})


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


def _infer_remote_type(job_geo: str) -> str:
    """Return ``'Worldwide'`` when *job_geo* is empty or a worldwide indicator.

    Args:
        job_geo: The raw ``jobGeo`` field from the Jobicy API response.

    Returns:
        Either ``'Worldwide'`` or ``'Remote'``.
    """
    if (job_geo or "").strip().lower() in _WORLDWIDE_GEO:
        return "Worldwide"
    return "Remote"


# ---------------------------------------------------------------------------
# Source plugin
# ---------------------------------------------------------------------------


class JobicySource(BaseJobSource):
    """Fetches remote jobs from the Jobicy public REST API.

    Configuration keys (all optional):
        ``jobicy_tags`` (list[str]): Override the default tag list.
        ``jobicy_count`` (int): Number of jobs per tag request. Default 50.
        ``max_jobs_per_run`` (int): Cap on total jobs returned. Default 200.
    """

    name = "jobicy"

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """Fetch jobs for all configured tags.

        *roles* and *locations* are accepted for interface compatibility but
        the primary filter mechanism is the tag list from config.

        Returns:
            A deduplicated list of :class:`~agent.sources.base_source.Job`
            objects, capped at ``max_jobs_per_run``.
        """
        tags: list[str] = self._config.get("jobicy_tags", _DEFAULT_TAGS)
        count: int = self._config.get("jobicy_count", 50)
        max_jobs: int = self._config.get("max_jobs_per_run", 200)

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for index, tag in enumerate(tags):
            if len(jobs) >= max_jobs:
                self._logger.debug(
                    "Reached max_jobs_per_run=%d, stopping early.", max_jobs
                )
                break

            if index > 0:
                time.sleep(_RATE_LIMIT_SECONDS)

            try:
                fetched = self._fetch_tag(tag, count)
                for job in fetched:
                    if job.source_job_id and job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)
                self._logger.info(
                    "Jobicy tag='%s' returned %d jobs (total so far: %d).",
                    tag,
                    len(fetched),
                    len(jobs),
                )
            except Exception as exc:
                self._logger.error(
                    "Jobicy tag='%s' failed: %s", tag, exc, exc_info=True
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
    def _fetch_tag(self, tag: str, count: int) -> list[Job]:
        """Fetch and normalise all jobs for a single *tag*.

        Args:
            tag:   The tag string to query (e.g. ``"machine-learning"``).
            count: Number of results to request per API call.

        Returns:
            A list of normalised :class:`~agent.sources.base_source.Job` objects.

        Raises:
            httpx.HTTPError: On non-2xx responses (triggers tenacity retry).
        """
        url = f"{_API_BASE}?count={count}&tag={tag}"
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
                "Jobicy: unexpected 'jobs' type %s for tag '%s'.",
                type(raw_jobs).__name__,
                tag,
            )
            return []

        return [self._normalize(j) for j in raw_jobs if isinstance(j, dict)]

    def _normalize(self, raw: dict[str, Any]) -> Job:
        """Map a raw Jobicy API dict to a :class:`~agent.sources.base_source.Job`.

        Args:
            raw: A single job dict from the Jobicy JSON response.

        Returns:
            A normalised :class:`~agent.sources.base_source.Job` instance.
        """
        job_geo: str = str(raw.get("jobGeo") or "").strip()
        remote_type: str = _infer_remote_type(job_geo)
        location: str = job_geo if job_geo else "Worldwide"

        # Skills: derive from jobIndustry when present.
        industry: Any = raw.get("jobIndustry") or ""
        if isinstance(industry, list):
            skills = ", ".join(str(i) for i in industry if i)
        else:
            skills = str(industry).strip()

        return Job(
            source_job_id=str(raw.get("id") or "").strip(),
            title=str(raw.get("jobTitle") or "").strip(),
            company=str(raw.get("companyName") or "").strip(),
            location=location,
            remote_type=remote_type,
            source=self.name,
            url=str(raw.get("url") or "").strip(),
            description=_clean_html(raw.get("jobDescription") or ""),
            skills=skills,
            employment_type=str(raw.get("jobType") or "").strip(),
            seniority=str(raw.get("jobLevel") or "").strip(),
            salary_min=_safe_float(raw.get("salaryMin")),
            salary_max=_safe_float(raw.get("salaryMax")),
            salary_currency=str(raw.get("salaryCurrency") or "").strip(),
            salary_period=str(raw.get("salaryPeriod") or "").strip(),
            published_at=str(raw.get("pubDate") or "").strip(),
        )
