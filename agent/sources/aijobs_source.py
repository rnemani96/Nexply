"""
NEXPLY - ai-jobs.net Source
Fetches AI/ML specialist job listings from https://ai-jobs.net via RSS feed.
Falls back to the JSON endpoint if the RSS feed is unavailable.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Optional
from urllib.parse import urlparse

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

_RSS_URL = "https://ai-jobs.net/feed/"
_JSON_URL = "https://ai-jobs.net/jobs/?format=json"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, application/json, */*",
}

# Patterns for extracting company name from job titles.
# Common formats seen on ai-jobs.net:
#   "Senior ML Engineer at Acme Corp"
#   "Acme Corp - Senior ML Engineer"
#   "Acme Corp | Senior ML Engineer"
_COMPANY_AT_PATTERN = re.compile(r"^(.+?)\s+at\s+(.+)$", re.IGNORECASE)
_COMPANY_DASH_PATTERN = re.compile(r"^(.+?)\s*[-–—|]\s*(.+)$")


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class AIJobsSource(BaseJobSource):
    """
    Job source plugin for ai-jobs.net.

    Reads the public RSS feed (one HTTP request, no pagination needed — the
    feed typically contains the 100 most recent listings).  If the RSS feed
    is inaccessible a JSON fallback is attempted.

    Configuration keys (from ``config`` dict):
        max_jobs_per_run (int): Upper bound on returned jobs.  Default 80.
        request_timeout  (int): HTTP timeout in seconds.  Default 30.
    """

    name = "aijobs"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """
        Fetch AI/ML job listings from ai-jobs.net.

        Args:
            roles:     List of role keywords to filter by (e.g. ``["LLM Engineer"]``).
            locations: Ignored — ai-jobs.net is treated as worldwide remote.

        Returns:
            A deduplicated list of :class:`~agent.sources.base_source.Job` objects
            whose title or description matches at least one role keyword.
        """
        max_jobs: int = self._config.get("max_jobs_per_run", 80)
        keywords = _build_keyword_set(roles)

        self._logger.info(
            "Fetching RSS feed from %s (keywords=%s)", _RSS_URL, keywords
        )

        jobs: list[Job] = []

        # --- Primary: RSS feed -----------------------------------------
        try:
            jobs = self._fetch_rss(keywords)
        except Exception as rss_err:
            self._logger.warning(
                "RSS feed failed (%s); attempting JSON fallback.", rss_err
            )
            # --- Fallback: JSON endpoint -----------------------------------
            try:
                jobs = self._fetch_json(keywords)
            except Exception as json_err:
                self._logger.error(
                    "JSON fallback also failed (%s). Returning empty list.", json_err
                )
                return []

        self._logger.info(
            "ai-jobs.net: %d job(s) matched after filtering (limit=%d).",
            len(jobs),
            max_jobs,
        )
        return jobs[:max_jobs]

    # ------------------------------------------------------------------
    # RSS fetching
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _fetch_rss(self, keywords: set[str]) -> list[Job]:
        """
        GET the RSS feed, parse it and return filtered :class:`Job` objects.

        Raises:
            httpx.HTTPError: On network / HTTP errors (triggers retry).
            ET.ParseError:   If the response body is not valid XML.
        """
        timeout: int = self._config.get("request_timeout", 30)
        resp = httpx.get(_RSS_URL, headers=_DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        # RSS 2.0: <rss><channel><item>...</item></channel></rss>
        channel = root.find("channel")
        if channel is None:
            # Some feeds omit the <channel> wrapper; fall back to root.
            items = root.findall("item")
        else:
            items = channel.findall("item")

        self._logger.debug("RSS feed returned %d <item> entries.", len(items))

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for item in items:
            job = self._parse_rss_item(item)
            if job is None:
                continue
            if not _matches_keywords(job.title, job.description, keywords):
                continue
            if job.source_job_id in seen_ids:
                continue
            seen_ids.add(job.source_job_id)
            jobs.append(job)

        return jobs

    def _parse_rss_item(self, item: ET.Element) -> Optional[Job]:
        """
        Convert a single RSS ``<item>`` element into a :class:`Job`.

        Returns ``None`` if essential fields (title, link) are missing.
        """
        title_raw = _elem_text(item, "title")
        link = _elem_text(item, "link")

        if not title_raw or not link:
            return None

        description_html = _elem_text(item, "description") or ""
        pub_date_str = _elem_text(item, "pubDate") or ""
        category = _elem_text(item, "category") or ""

        # Derive a stable ID from the URL (the <guid> may equal the link).
        guid = _elem_text(item, "guid") or link
        source_job_id = _stable_id(guid)

        title, company = _split_title_company(title_raw)
        description = _strip_html(description_html)
        published_at = _parse_pub_date(pub_date_str)

        return Job(
            source_job_id=source_job_id,
            title=title,
            company=company,
            location="Worldwide",
            location_codes="",
            remote_type="Worldwide",
            timezone_restrictions="",
            source=self.name,
            url=link.strip(),
            description=description,
            skills=category,
            employment_type="",
            seniority="",
            salary_min=None,
            salary_max=None,
            salary_currency="",
            salary_period="",
            published_at=published_at,
            expires_at="",
        )

    # ------------------------------------------------------------------
    # JSON fallback
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=3, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _fetch_json(self, keywords: set[str]) -> list[Job]:
        """
        Attempt to retrieve jobs from the ai-jobs.net JSON endpoint.

        The JSON endpoint is undocumented and may change or return 404;
        all errors are propagated to the caller which handles them gracefully.

        Raises:
            httpx.HTTPError: On HTTP / network errors.
            ValueError:      If the response cannot be decoded as JSON.
        """
        timeout: int = self._config.get("request_timeout", 30)
        resp = httpx.get(
            _JSON_URL,
            headers={**_DEFAULT_HEADERS, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()

        data = resp.json()
        raw_jobs: list[dict] = data if isinstance(data, list) else data.get("jobs", [])

        self._logger.debug("JSON fallback returned %d raw job(s).", len(raw_jobs))

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for raw in raw_jobs:
            if not isinstance(raw, dict):
                continue
            job = self._normalize_json(raw)
            if not _matches_keywords(job.title, job.description, keywords):
                continue
            if job.source_job_id in seen_ids:
                continue
            seen_ids.add(job.source_job_id)
            jobs.append(job)

        return jobs

    def _normalize_json(self, raw: dict) -> Job:
        """Convert a raw JSON job dict from ai-jobs.net into a :class:`Job`."""
        title_raw = str(raw.get("title") or "").strip()
        title, company = _split_title_company(title_raw)
        company = company or str(raw.get("company") or "").strip()

        url = str(raw.get("url") or raw.get("link") or "").strip()
        source_job_id = _stable_id(str(raw.get("id") or raw.get("guid") or url))
        description_raw = str(raw.get("description") or raw.get("content") or "")
        description = _strip_html(description_raw)

        pub_date_str = str(raw.get("pubDate") or raw.get("published_at") or "")
        published_at = _parse_pub_date(pub_date_str) if pub_date_str else ""

        tags = raw.get("tags") or raw.get("category") or []
        if isinstance(tags, list):
            skills = ", ".join(str(t) for t in tags)
        else:
            skills = str(tags)

        return Job(
            source_job_id=source_job_id,
            title=title,
            company=company,
            location="Worldwide",
            location_codes="",
            remote_type="Worldwide",
            timezone_restrictions="",
            source=self.name,
            url=url,
            description=description,
            skills=skills,
            employment_type=str(raw.get("employment_type") or ""),
            seniority=str(raw.get("seniority") or ""),
            salary_min=_to_float(raw.get("salary_min")),
            salary_max=_to_float(raw.get("salary_max")),
            salary_currency=str(raw.get("currency") or ""),
            salary_period=str(raw.get("salary_period") or ""),
            published_at=published_at,
            expires_at=str(raw.get("expires_at") or ""),
        )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _elem_text(parent: ET.Element, tag: str) -> Optional[str]:
    """Return stripped text of a child element, or ``None`` if absent/empty."""
    el = parent.find(tag)
    if el is None or el.text is None:
        return None
    return unescape(el.text).strip() or None


def _stable_id(raw: str) -> str:
    """Return a short, stable hex ID derived from *raw* (e.g. a URL or guid)."""
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _split_title_company(raw_title: str) -> tuple[str, str]:
    """
    Heuristically split a job listing title into ``(title, company)``.

    Handles patterns commonly seen on ai-jobs.net:

    * ``"Senior ML Engineer at Acme Corp"``   → ``("Senior ML Engineer", "Acme Corp")``
    * ``"Acme Corp - Senior ML Engineer"``     → ``("Senior ML Engineer", "Acme Corp")``
    * ``"Acme Corp | Senior ML Engineer"``     → ``("Senior ML Engineer", "Acme Corp")``
    * ``"Senior ML Engineer"``                 → ``("Senior ML Engineer", "")``

    If no pattern matches the title is returned as-is with an empty company.
    """
    raw_title = raw_title.strip()

    # Pattern: "Position at Company"
    m = _COMPANY_AT_PATTERN.match(raw_title)
    if m:
        position, company = m.group(1).strip(), m.group(2).strip()
        return position, company

    # Pattern: "Company - Position" or "Company | Position"
    # Heuristic: if the LEFT side looks shorter and title-cased it's likely the company.
    m = _COMPANY_DASH_PATTERN.match(raw_title)
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        # Treat the shorter, Title-Cased left token as the company name
        if len(left) <= len(right) and left[:1].isupper():
            return right, left

    return raw_title, ""


_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalise whitespace from *html*."""
    if not html:
        return ""
    text = unescape(html)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _parse_pub_date(date_str: str) -> str:
    """
    Parse an RFC 2822 pubDate string (common in RSS) to ISO-8601 UTC.

    Returns the original string unchanged if parsing fails.
    """
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # Non-standard format — return as-is so we don't silently lose the value.
        return date_str.strip()


def _build_keyword_set(roles: list[str]) -> set[str]:
    """
    Expand a list of role strings into a flat set of lowercase keywords.

    For example ``["LLM Engineer", "RAG"]`` →
    ``{"llm", "engineer", "rag", "llm engineer", "rag engineer"}``.
    """
    keywords: set[str] = set()
    for role in roles:
        role_lower = role.lower().strip()
        keywords.add(role_lower)
        # Also add individual words so partial matches work.
        for word in role_lower.split():
            if len(word) > 2:  # skip short stop-words like "at", "in"
                keywords.add(word)
    # Always include generic AI/ML keywords so we don't miss obvious listings.
    keywords.update(
        {
            "ai",
            "ml",
            "llm",
            "nlp",
            "rag",
            "generative",
            "machine learning",
            "deep learning",
            "artificial intelligence",
            "data science",
        }
    )
    return keywords


def _matches_keywords(title: str, description: str, keywords: set[str]) -> bool:
    """Return ``True`` if title or description contains any keyword."""
    haystack = (title + " " + description).lower()
    return any(kw in haystack for kw in keywords)


def _to_float(value: object) -> Optional[float]:
    """Coerce *value* to ``float``, returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
