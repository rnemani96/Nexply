"""
RAJESH AI - LinkedIn Source
Scrapes LinkedIn Easy Apply jobs using Playwright.

Setup: Set LINKEDIN_SESSION_COOKIE env var with your li_at cookie value.
  1. Log in to LinkedIn in Chrome
  2. Open DevTools → Application → Cookies → linkedin.com
  3. Copy the value of 'li_at' cookie
  4. Set: set LINKEDIN_SESSION_COOKIE=<value>
"""
from __future__ import annotations

import os
import re
import time
import logging

from agent.sources.base_source import BaseJobSource, Job

logger = logging.getLogger(__name__)


class LinkedInSource(BaseJobSource):
    """Scrapes LinkedIn Easy Apply job listings via Playwright."""

    name = "linkedin"

    def is_available(self) -> bool:
        cookie = os.environ.get("LINKEDIN_SESSION_COOKIE", "")
        if not cookie:
            logger.warning(
                "LinkedIn source disabled. To enable:\n"
                "  1. Log in to LinkedIn in Chrome\n"
                "  2. Open DevTools → Application → Cookies → linkedin.com\n"
                "  3. Copy the 'li_at' cookie value\n"
                "  4. Set env var: LINKEDIN_SESSION_COOKIE=<value>"
            )
            return False
        return True

    def fetch(self, roles: list[str], locations: list[str]) -> list[Job]:
        if not self.is_available():
            return []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        session_cookie = os.environ.get("LINKEDIN_SESSION_COOKIE", "")
        max_jobs = self._config.get("max_jobs_per_run", 50)
        jobs: list[Job] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            ctx.add_cookies([{
                "name": "li_at",
                "value": session_cookie,
                "domain": ".linkedin.com",
                "path": "/",
            }])

            page = ctx.new_page()

            for role in roles[:4]:  # Limit roles to avoid rate limiting
                if len(jobs) >= max_jobs:
                    break
                try:
                    fetched = self._scrape_role(page, role, max_jobs - len(jobs))
                    jobs.extend(fetched)
                    time.sleep(3)
                except Exception as e:
                    logger.error(f"LinkedIn scraping failed for role '{role}': {e}")

            browser.close()

        return jobs

    def _scrape_role(self, page, role: str, limit: int) -> list[Job]:
        from urllib.parse import quote
        search_url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={quote(role)}"
            f"&f_AL=true"          # Easy Apply only
            f"&f_E=3,4"            # Mid-Senior level
            f"&f_WT=2"             # Remote
            f"&sortBy=DD"          # Date posted
        )

        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Wait for job list
        try:
            page.wait_for_selector(".jobs-search__results-list", timeout=10000)
        except Exception:
            logger.warning(f"LinkedIn: job list not found for '{role}'")
            return []

        jobs: list[Job] = []

        # Get all job cards
        cards = page.query_selector_all(".jobs-search__results-list > li")
        logger.info(f"LinkedIn: found {len(cards)} cards for '{role}'")

        for card in cards[:limit]:
            try:
                job = self._parse_card(page, card, role)
                if job:
                    jobs.append(job)
                time.sleep(1.5)
            except Exception as e:
                logger.debug(f"Card parse error: {e}")

        return jobs

    def _parse_card(self, page, card, role: str) -> Job | None:
        try:
            # Click card to load details
            card.click()
            time.sleep(2)

            # Extract from detail panel
            detail = page.query_selector(".jobs-unified-top-card")
            if not detail:
                return None

            title_el = detail.query_selector(".jobs-unified-top-card__job-title")
            company_el = detail.query_selector(".jobs-unified-top-card__company-name")
            location_el = detail.query_selector(".jobs-unified-top-card__bullet")
            url = page.url

            title = title_el.inner_text().strip() if title_el else ""
            company = company_el.inner_text().strip() if company_el else ""
            location = location_el.inner_text().strip() if location_el else ""

            if not title or not company:
                return None

            # Get description
            desc_el = page.query_selector(".jobs-description-content__text")
            description = desc_el.inner_text().strip() if desc_el else ""

            # Extract job ID from URL
            job_id_match = re.search(r"/jobs/view/(\d+)", url)
            source_job_id = job_id_match.group(1) if job_id_match else ""

            return Job(
                source_job_id=source_job_id,
                title=title,
                company=company,
                location=location,
                remote_type="Remote" if "remote" in location.lower() else "",
                source="linkedin",
                url=url,
                description=description,
                employment_type="Full-time",
            )

        except Exception as e:
            logger.debug(f"Card parse exception: {e}")
            return None
