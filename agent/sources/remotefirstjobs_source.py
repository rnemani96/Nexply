"""
NEXPLY - Remote First Jobs Source
Fetches remote-first job listings from https://remotefirstjobs.com/api/jobs.

The Remote First Jobs API is free and requires no authentication.
One search request is made per role keyword; results are deduplicated.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Optional
from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.sources.base_source import BaseJobSource, Job

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_BASE = "https://remotefirstjobs.com/api/jobs"
_DEFAULT_PAGE_SIZE = 50
_REQUEST_DELAY = 1.0  # seconds between role searches (polite rate limit)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class RemoteFirstJobsSource(BaseJobSource):
    """
    Job source plugin for https://remotefirstjobs.com.

    Queries the free public REST API once per role keyword and aggregates
    the results.  The site focuses exclusively on remote-first positions so
    ``remote_type`` is set to ``"Worldwide"`` for all returned jobs.

    Configuration keys (from ``config`` dict):
        max_jobs_per_run (int): Upper bound on returned jobs.  Default 80.
        request_timeout  (int): HTTP timeout in seconds.  Default 30.
    """

    name = "remotefirstjobs"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """
        Fetch remote-first job listings filtered by *roles*.

        A separate API call is made for each unique role keyword.  Results
        are deduplicated by ``source_job_id`` before being returned.

        Args:
            roles:     List of role keywords (e.g. ``["LLM Engineer", "ML Engineer"]``).
            locations: Accepted for interface compatibility; not used (API is global).

        Returns:
            A deduplicated list of :class:`~agent.sources.base_source.Job` objects,
            capped at ``config['max_jobs_per_run']``.
        """
        max_jobs: int = self._config.get("max_jobs_per_run", 80)
        queries = _deduplicated_queries(roles)

        self._logger.info(
            "RemoteFirstJobs: searching %d query/queries (limit=%d).",
            len(queries),
            max_jobs,
        )

        all_jobs: list[Job] = []
        seen_ids: set[str] = set()

        for idx, query in enumerate(queries):
            if len(all_jobs) >= max_jobs:
                break

            try:
                fetched = self._search(query)
                for job in fetched:
                    if job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        all_jobs.append(job)
                self._logger.debug(
                    "Query '%s' → %d result(s) (%d total so far).",
                    query,
                    len(fetched),
                    len(all_jobs),
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    # API endpoint not found — stop all queries and return early.
                    self._logger.warning(
                        "RemoteFirstJobs API returned 404; endpoint may be unavailable. "
                        "Returning %d job(s) collected so far.",
                        len(all_jobs),
                    )
                    break
                self._logger.error(
                    "HTTP %d for query '%s': %s",
                    exc.response.status_code,
                    query,
                    exc,
                )
            except httpx.TimeoutException:
                self._logger.warning("Request timed out for query '%s'.", query)
            except Exception as exc:  # noqa: BLE001
                self._logger.error(
                    "Unexpected error for query '%s': %s", query, exc
                )

            # Polite rate limit between searches.
            if idx < len(queries) - 1:
                time.sleep(_REQUEST_DELAY)

        result = all_jobs[:max_jobs]
        self._logger.info(
            "RemoteFirstJobs: returning %d job(s).", len(result)
        )
        return result

    def is_available(self) -> bool:
        """
        Probe the API with a lightweight HEAD request.

        Returns ``False`` (instead of raising) if the endpoint is unreachable
        so the orchestrator can skip this source gracefully.
        """
        try:
            timeout: int = self._config.get("request_timeout", 30)
            resp = httpx.head(_API_BASE, headers=_DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    def _search(self, query: str) -> list[Job]:
        """
        Perform a single API search for *query* and return normalised jobs.

        The retry decorator retries on low-level transport errors (e.g. timeouts,
        connection resets) but **not** on HTTP 4xx/5xx errors — those are handled
        by the caller.

        Args:
            query: URL-encoded search string.

        Returns:
            List of :class:`Job` objects parsed from the API response.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses (not retried).
            httpx.TransportError:  On network failures (retried up to 3 ×).
        """
        timeout: int = self._config.get("request_timeout", 30)
        limit: int = _DEFAULT_PAGE_SIZE

        url = f"{_API_BASE}?search={quote(query)}&limit={limit}"
        resp = httpx.get(url, headers=_DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()

        data = resp.json()

        # The API may return a bare list or a wrapper object.
        if isinstance(data, list):
            raw_jobs = data
        elif isinstance(data, dict):
            # Common wrapper key names:
            raw_jobs = (
                data.get("jobs")
                or data.get("data")
                or data.get("results")
                or []
            )
        else:
            self._logger.warning(
                "Unexpected response type from RemoteFirstJobs API: %s", type(data)
            )
            return []

        return [
            self._normalize(raw)
            for raw in raw_jobs
            if isinstance(raw, dict)
        ]

    def _normalize(self, raw: dict) -> Job:
        """
        Convert a raw API job dict into a normalised :class:`Job`.

        The Remote First Jobs API does not publish a formal schema; field names
        are inferred from common REST conventions.  Unknown keys are handled
        gracefully via ``dict.get`` with defaults.
        """
        # --- Identifiers -------------------------------------------------------
        job_id = str(raw.get("id") or raw.get("job_id") or raw.get("slug") or "")
        url = str(raw.get("url") or raw.get("link") or raw.get("apply_url") or "").strip()
        source_job_id = _stable_id(job_id or url)

        # --- Core fields -------------------------------------------------------
        title = str(raw.get("title") or raw.get("job_title") or "").strip()
        company = str(raw.get("company") or raw.get("company_name") or "").strip()

        # --- Location ----------------------------------------------------------
        # The site is remote-first so location is the candidate's requirement,
        # not an office address.
        location_raw = raw.get("location") or raw.get("region") or ""
        if isinstance(location_raw, list):
            location = ", ".join(str(l) for l in location_raw)
        else:
            location = str(location_raw).strip()

        # --- Description -------------------------------------------------------
        desc_raw = str(
            raw.get("description")
            or raw.get("summary")
            or raw.get("body")
            or ""
        )
        description = _strip_html(desc_raw)

        # --- Tags / Skills -----------------------------------------------------
        tags = raw.get("tags") or raw.get("skills") or raw.get("categories") or []
        if isinstance(tags, list):
            skills = ", ".join(str(t) for t in tags)
        else:
            skills = str(tags).strip()

        # --- Salary ------------------------------------------------------------
        salary_raw = raw.get("salary") or raw.get("compensation") or {}
        if isinstance(salary_raw, dict):
            salary_min = _to_float(salary_raw.get("min") or salary_raw.get("salary_min"))
            salary_max = _to_float(salary_raw.get("max") or salary_raw.get("salary_max"))
            salary_currency = str(salary_raw.get("currency") or "").upper()
            salary_period = str(salary_raw.get("period") or salary_raw.get("type") or "")
        else:
            # Flat salary value
            salary_min = _to_float(
                raw.get("salary_min") or raw.get("min_salary")
            )
            salary_max = _to_float(
                raw.get("salary_max") or raw.get("max_salary")
            )
            salary_currency = str(
                raw.get("currency") or raw.get("salary_currency") or ""
            ).upper()
            salary_period = str(
                raw.get("salary_period") or raw.get("pay_period") or ""
            )

        # --- Dates -------------------------------------------------------------
        published_at = str(
            raw.get("published_at")
            or raw.get("created_at")
            or raw.get("date_posted")
            or raw.get("pubDate")
            or ""
        ).strip()

        expires_at = str(
            raw.get("expires_at")
            or raw.get("expiry_date")
            or raw.get("deadline")
            or ""
        ).strip()

        # --- Misc --------------------------------------------------------------
        employment_type = str(
            raw.get("employment_type")
            or raw.get("job_type")
            or raw.get("type")
            or ""
        )
        seniority = str(
            raw.get("seniority")
            or raw.get("level")
            or raw.get("experience_level")
            or ""
        )

        return Job(
            source_job_id=source_job_id,
            title=title,
            company=company,
            location=location or "Worldwide",
            location_codes="",
            remote_type="Worldwide",
            timezone_restrictions="",
            source=self.name,
            url=url,
            description=description,
            skills=skills,
            employment_type=employment_type,
            seniority=seniority,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_period=salary_period,
            published_at=published_at,
            expires_at=expires_at,
        )


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def _deduplicated_queries(roles: list[str]) -> list[str]:
    """
    Return a list of search query strings derived from *roles*, preserving
    order and removing exact duplicates (case-insensitive).
    """
    seen: set[str] = set()
    result: list[str] = []
    for role in roles:
        key = role.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(role.strip())
    return result


def _stable_id(raw: str) -> str:
    """Return a short, stable hex ID derived from *raw* (e.g. a URL or guid)."""
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalise whitespace from *html*."""
    if not html:
        return ""
    from html import unescape
    text = unescape(html)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _to_float(value: object) -> Optional[float]:
    """Coerce *value* to ``float``, returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
