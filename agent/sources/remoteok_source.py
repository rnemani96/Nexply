"""
RAJESH AI - RemoteOK Source
Fetches remote job listings from https://remoteok.com/api using tag-based queries.

API notes:
- No authentication required.
- The first element of the JSON array is always a legal/notice dict — it must be skipped.
- Rate limit: be polite and wait 2 seconds between tag requests.
"""
from __future__ import annotations

import re
import time
import logging
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_DEFAULT_TAGS: list[str] = [
    "machine-learning",
    "ai",
    "data-science",
    "python",
    "nlp",
    "qa",
    "testing",
]

_RATE_LIMIT_SECONDS: float = 2.0
_API_BASE: str = "https://remoteok.com/api"


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


# ---------------------------------------------------------------------------
# Source plugin
# ---------------------------------------------------------------------------


class RemoteOKSource(BaseJobSource):
    """Fetches remote jobs from the RemoteOK public JSON API.

    Configuration keys (all optional):
        ``remoteok_tags`` (list[str]): Override the default tag list.
        ``max_jobs_per_run`` (int): Cap on total jobs returned. Default 200.
    """

    name = "remoteok"

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """Fetch jobs for all configured tags.

        *roles* and *locations* are accepted for interface compatibility but
        the primary filter mechanism is the tag list from config.

        Returns:
            A deduplicated list of :class:`~agent.sources.base_source.Job`
            objects, capped at ``max_jobs_per_run``.
        """
        tags: list[str] = self._config.get("remoteok_tags", _DEFAULT_TAGS)
        max_jobs: int = self._config.get("max_jobs_per_run", 200)

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for index, tag in enumerate(tags):
            if len(jobs) >= max_jobs:
                self._logger.debug(
                    "Reached max_jobs_per_run=%d, stopping early.", max_jobs
                )
                break

            # Polite rate limiting — skip sleep before the very first request.
            if index > 0:
                time.sleep(_RATE_LIMIT_SECONDS)

            try:
                fetched = self._fetch_tag(tag)
                for job in fetched:
                    if job.source_job_id and job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)
                self._logger.info(
                    "RemoteOK tag='%s' returned %d jobs (total so far: %d).",
                    tag,
                    len(fetched),
                    len(jobs),
                )
            except Exception as exc:
                self._logger.error(
                    "RemoteOK tag='%s' failed: %s", tag, exc, exc_info=True
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
    def _fetch_tag(self, tag: str) -> list[Job]:
        """Fetch and normalise all jobs for a single *tag*.

        The RemoteOK API always returns the first array element as a metadata/
        legal notice dict (it contains a ``legal`` key).  We detect and skip it.

        Args:
            tag: The tag string to query (e.g. ``"machine-learning"``).

        Returns:
            A list of normalised :class:`~agent.sources.base_source.Job` objects.

        Raises:
            httpx.HTTPError: On non-2xx responses (triggers tenacity retry).
        """
        url = f"{_API_BASE}?tag={tag}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data: list[Any] = resp.json()

        if not isinstance(data, list):
            self._logger.warning(
                "RemoteOK: unexpected response type %s for tag '%s'.",
                type(data).__name__,
                tag,
            )
            return []

        jobs: list[Job] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            # Skip the legal-notice element (first item in the array).
            if "legal" in item:
                self._logger.debug("Skipping RemoteOK legal notice entry.")
                continue
            jobs.append(self._normalize(item))

        return jobs

    def _normalize(self, raw: dict[str, Any]) -> Job:
        """Map a raw RemoteOK API dict to a :class:`~agent.sources.base_source.Job`.

        Args:
            raw: A single job dict from the RemoteOK JSON response.

        Returns:
            A normalised :class:`~agent.sources.base_source.Job` instance.
        """
        # Skills: tags list joined with comma.
        raw_tags: list[str] | str = raw.get("tags") or []
        if isinstance(raw_tags, list):
            skills = ", ".join(str(t) for t in raw_tags if t)
        else:
            skills = str(raw_tags)

        # Location: RemoteOK jobs are worldwide remote by default.
        location: str = str(raw.get("location") or "Worldwide").strip() or "Worldwide"

        # Published date — epoch seconds or ISO string.
        raw_date: Any = raw.get("date") or ""
        published_at: str
        if isinstance(raw_date, (int, float)):
            # Convert Unix timestamp to ISO-8601.
            import datetime
            published_at = datetime.datetime.utcfromtimestamp(raw_date).isoformat()
        else:
            published_at = str(raw_date).strip()

        return Job(
            source_job_id=str(raw.get("id") or "").strip(),
            title=str(raw.get("position") or "").strip(),
            company=str(raw.get("company") or "").strip(),
            location=location,
            remote_type="Worldwide",
            source=self.name,
            url=str(raw.get("apply_url") or raw.get("url") or "").strip(),
            description=_clean_html(raw.get("description") or ""),
            skills=skills,
            salary_min=_safe_float(raw.get("salary_min")),
            salary_max=_safe_float(raw.get("salary_max")),
            published_at=published_at,
        )
