"""
NEXPLY - We Work Remotely Source
Fetches remote job listings from We Work Remotely RSS feeds.

Feed notes:
- No authentication required.
- Each RSS <item> title follows the format 'Company: Position'.
- feedparser is the primary RSS parser; falls back to httpx + xml.etree.ElementTree
  when feedparser is not installed.
- Rate limit: 1 second between feed requests.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
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
# Optional feedparser import
# ---------------------------------------------------------------------------

try:
    import feedparser  # type: ignore[import-untyped]

    _HAS_FEEDPARSER: bool = True
except ImportError:
    feedparser = None  # type: ignore[assignment]
    _HAS_FEEDPARSER = False

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_DEFAULT_FEED_URLS: list[str] = [
    "https://weworkremotely.com/categories/remote-data-science-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-quality-assurance-jobs.rss",
]

_RATE_LIMIT_SECONDS: float = 1.0

# XML namespace used by WWR RSS feeds.
_WWR_NS: dict[str, str] = {"media": "http://search.yahoo.com/mrss/"}


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


def _parse_title(raw_title: str) -> tuple[str, str]:
    """Split a WWR title of the form ``'Company: Position'`` into its parts.

    Args:
        raw_title: The raw ``<title>`` text from an RSS ``<item>``.

    Returns:
        A ``(company, position)`` tuple.  If no colon is present both values
        fall back to sensible defaults (empty company, full title as position).
    """
    raw_title = raw_title.strip()
    if ": " in raw_title:
        company, _, position = raw_title.partition(": ")
        return company.strip(), position.strip()
    return "", raw_title


def _rfc_date_to_iso(rfc_date: str) -> str:
    """Convert an RFC-2822 date string to ISO-8601 format.

    Args:
        rfc_date: An RFC-2822 date string (e.g. from ``<pubDate>``).

    Returns:
        An ISO-8601 string, or the original string if parsing fails.
    """
    if not rfc_date:
        return ""
    try:
        return parsedate_to_datetime(rfc_date).isoformat()
    except Exception:
        return rfc_date.strip()


# ---------------------------------------------------------------------------
# Source plugin
# ---------------------------------------------------------------------------


class WeWorkRemotelySource(BaseJobSource):
    """Fetches remote jobs from We Work Remotely RSS feeds.

    Uses ``feedparser`` when available; falls back to ``httpx`` +
    ``xml.etree.ElementTree`` otherwise.

    Configuration keys (all optional):
        ``wwr_feed_urls`` (list[str]): Override the default feed URL list.
        ``max_jobs_per_run`` (int): Cap on total jobs returned. Default 200.
    """

    name = "weworkremotely"

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        """Fetch jobs from all configured RSS feed URLs.

        *roles* and *locations* are accepted for interface compatibility.
        All returned jobs are classified as ``remote_type='Remote'``.

        Returns:
            A deduplicated list of :class:`~agent.sources.base_source.Job`
            objects, capped at ``max_jobs_per_run``.
        """
        feed_urls: list[str] = self._config.get("wwr_feed_urls", _DEFAULT_FEED_URLS)
        max_jobs: int = self._config.get("max_jobs_per_run", 200)

        parser_name = "feedparser" if _HAS_FEEDPARSER else "httpx+ElementTree"
        self._logger.info(
            "WeWorkRemotely using %s to parse %d feeds.", parser_name, len(feed_urls)
        )

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        for index, feed_url in enumerate(feed_urls):
            if len(jobs) >= max_jobs:
                self._logger.debug(
                    "Reached max_jobs_per_run=%d, stopping early.", max_jobs
                )
                break

            if index > 0:
                time.sleep(_RATE_LIMIT_SECONDS)

            try:
                if _HAS_FEEDPARSER:
                    fetched = self._fetch_feed_feedparser(feed_url)
                else:
                    fetched = self._fetch_feed_httpx(feed_url)

                for job in fetched:
                    if job.source_job_id and job.source_job_id not in seen_ids:
                        seen_ids.add(job.source_job_id)
                        jobs.append(job)

                self._logger.info(
                    "WeWorkRemotely feed='%s' returned %d jobs (total so far: %d).",
                    feed_url,
                    len(fetched),
                    len(jobs),
                )
            except Exception as exc:
                self._logger.error(
                    "WeWorkRemotely feed='%s' failed: %s", feed_url, exc, exc_info=True
                )

        return jobs[:max_jobs]

    # ------------------------------------------------------------------
    # feedparser path
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _fetch_feed_feedparser(self, feed_url: str) -> list[Job]:
        """Fetch and parse a single RSS feed using *feedparser*.

        Args:
            feed_url: The full URL of the RSS feed to parse.

        Returns:
            A list of normalised :class:`~agent.sources.base_source.Job` objects.

        Raises:
            RuntimeError: If feedparser reports a bozo (malformed feed) error.
        """
        parsed = feedparser.parse(feed_url)

        if parsed.get("bozo") and parsed.get("bozo_exception"):
            raise RuntimeError(
                f"feedparser bozo error for '{feed_url}': {parsed['bozo_exception']}"
            )

        jobs: list[Job] = []
        for entry in parsed.get("entries", []):
            job = self._normalize_feedparser_entry(entry)
            jobs.append(job)

        return jobs

    def _normalize_feedparser_entry(self, entry: Any) -> Job:
        """Convert a feedparser entry dict to a :class:`~agent.sources.base_source.Job`.

        Args:
            entry: A feedparser entry object.

        Returns:
            A normalised :class:`~agent.sources.base_source.Job` instance.
        """
        raw_title: str = str(getattr(entry, "title", "") or entry.get("title", ""))
        company, position = _parse_title(raw_title)

        link: str = str(getattr(entry, "link", "") or entry.get("link", "")).strip()

        # Use the URL path as a stable ID (WWR doesn't expose numeric IDs in RSS).
        source_job_id: str = link.strip("/").split("/")[-1] if link else ""

        summary: str = (
            str(getattr(entry, "summary", "") or entry.get("summary", ""))
        )

        published_raw: str = str(
            getattr(entry, "published", "") or entry.get("published", "")
        )
        published_at: str = _rfc_date_to_iso(published_raw)

        return Job(
            source_job_id=source_job_id,
            title=position,
            company=company,
            remote_type="Remote",
            source=self.name,
            url=link,
            description=_clean_html(summary),
            published_at=published_at,
        )

    # ------------------------------------------------------------------
    # httpx + ElementTree fallback path
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _fetch_feed_httpx(self, feed_url: str) -> list[Job]:
        """Fetch and parse a single RSS feed using *httpx* + *ElementTree*.

        This method is used only when ``feedparser`` is not installed.

        Args:
            feed_url: The full URL of the RSS feed to parse.

        Returns:
            A list of normalised :class:`~agent.sources.base_source.Job` objects.

        Raises:
            httpx.HTTPError: On non-2xx responses (triggers tenacity retry).
            ET.ParseError: If the XML is malformed.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml",
        }

        resp = httpx.get(feed_url, headers=headers, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        if channel is None:
            self._logger.warning(
                "WeWorkRemotely: no <channel> element found in feed '%s'.", feed_url
            )
            return []

        jobs: list[Job] = []
        for item in channel.findall("item"):
            job = self._normalize_xml_item(item)
            jobs.append(job)

        return jobs

    def _normalize_xml_item(self, item: ET.Element) -> Job:
        """Convert an XML ``<item>`` element to a :class:`~agent.sources.base_source.Job`.

        Args:
            item: An ``xml.etree.ElementTree.Element`` representing one RSS ``<item>``.

        Returns:
            A normalised :class:`~agent.sources.base_source.Job` instance.
        """

        def _text(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        raw_title = _text("title")
        company, position = _parse_title(raw_title)

        link = _text("link")
        # WWR <link> is sometimes preceded by a CDATA comment — try <guid> as fallback.
        if not link:
            link = _text("guid")

        source_job_id: str = link.strip("/").split("/")[-1] if link else ""

        summary = _text("description")
        published_raw = _text("pubDate")
        published_at = _rfc_date_to_iso(published_raw)

        return Job(
            source_job_id=source_job_id,
            title=position,
            company=company,
            remote_type="Remote",
            source=self.name,
            url=link,
            description=_clean_html(summary),
            published_at=published_at,
        )
