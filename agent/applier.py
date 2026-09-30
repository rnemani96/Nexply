"""
NEXPLY - APPLICATION ENGINE v2.0
Browser automation for submitting job applications via Playwright.

Supported platforms:
  - Himalayas (direct apply link)
  - LinkedIn (Easy Apply)
  - Email (compose + attach resume)
  - Generic (fill standard web forms)
"""
from __future__ import annotations

import logging
import os
import smtplib
import time
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# RESULT MODEL
# ============================================================

@dataclass
class ApplicationResult:
    success: bool
    platform: str
    method: str                        # browser_auto | email | manual
    confirmation_id: str = ""
    error: str = ""
    screenshot_path: str = ""
    notes: str = ""


# ============================================================
# BASE APPLIER
# ============================================================

class BaseApplier:
    """Abstract base for platform-specific appliers."""

    platform: str = "generic"

    def __init__(self, settings: dict):
        self._settings = settings

    def can_handle(self, job: dict) -> bool:
        return False

    def apply(
        self,
        job: dict,
        resume_path: Path,
        cover_letter_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> ApplicationResult:
        raise NotImplementedError


# ============================================================
# HIMALAYAS APPLIER
# ============================================================

class HimalayasApplier(BaseApplier):
    """Apply to Himalayas jobs via their direct apply link."""

    platform = "himalayas"

    def can_handle(self, job: dict) -> bool:
        url = job.get("url", "").lower()
        source = job.get("source", "").lower()
        return "himalayas.app" in url or source == "himalayas"

    def apply(
        self,
        job: dict,
        resume_path: Path,
        cover_letter_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> ApplicationResult:
        url = job.get("url", "")
        if not url:
            return ApplicationResult(
                success=False,
                platform=self.platform,
                method="browser_auto",
                error="No application URL found",
            )

        logger.info(f"Applying to Himalayas job: {job.get('title')} at {job.get('company')}")

        if dry_run:
            logger.info(f"[DRY RUN] Would open: {url}")
            return ApplicationResult(
                success=True,
                platform=self.platform,
                method="browser_auto",
                notes="dry_run — browser not launched",
            )

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False, slow_mo=500)
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = ctx.new_page()

                # Open application URL
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

                # Take screenshot for records
                screenshot_path = str(resume_path.parent / f"screenshot_{job['id']}.png")
                page.screenshot(path=screenshot_path)

                # Look for file upload field (for resume)
                upload_selector = "input[type='file']"
                if page.locator(upload_selector).count() > 0:
                    page.locator(upload_selector).first.set_input_files(str(resume_path))
                    logger.info("Resume uploaded successfully")
                    time.sleep(1)

                # Common "Apply" button patterns
                apply_buttons = [
                    "button:has-text('Apply')",
                    "button:has-text('Submit Application')",
                    "button:has-text('Submit')",
                    "a:has-text('Apply Now')",
                    "[data-testid='apply-button']",
                ]

                clicked = False
                for selector in apply_buttons:
                    btn = page.locator(selector).first
                    if btn.count() > 0:
                        btn.click()
                        clicked = True
                        logger.info(f"Clicked: {selector}")
                        time.sleep(3)
                        break

                final_screenshot = str(resume_path.parent / f"confirm_{job['id']}.png")
                page.screenshot(path=final_screenshot)

                browser.close()

                return ApplicationResult(
                    success=clicked,
                    platform=self.platform,
                    method="browser_auto",
                    screenshot_path=final_screenshot,
                    notes="Applied via Playwright" if clicked else "Apply button not found — manual review needed",
                )

        except Exception as e:
            logger.error(f"Himalayas apply error: {e}")
            return ApplicationResult(
                success=False,
                platform=self.platform,
                method="browser_auto",
                error=str(e),
            )


# ============================================================
# LINKEDIN EASY APPLY
# ============================================================

class LinkedInApplier(BaseApplier):
    """Apply to LinkedIn Easy Apply jobs."""

    platform = "linkedin"

    def can_handle(self, job: dict) -> bool:
        url = job.get("url", "").lower()
        source = job.get("source", "").lower()
        return "linkedin.com" in url or source == "linkedin"

    def apply(
        self,
        job: dict,
        resume_path: Path,
        cover_letter_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> ApplicationResult:
        session_cookie = os.environ.get("LINKEDIN_SESSION_COOKIE", "")
        url = job.get("url", "")

        if not url:
            return ApplicationResult(
                success=False,
                platform=self.platform,
                method="browser_auto",
                error="No LinkedIn job URL",
            )

        if dry_run:
            logger.info(f"[DRY RUN] Would Easy Apply: {url}")
            return ApplicationResult(
                success=True,
                platform=self.platform,
                method="browser_auto",
                notes="dry_run",
            )

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False, slow_mo=800)
                ctx = browser.new_context()

                # Set LinkedIn session cookie
                if session_cookie:
                    ctx.add_cookies([{
                        "name": "li_at",
                        "value": session_cookie,
                        "domain": ".linkedin.com",
                        "path": "/",
                    }])

                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                # Click "Easy Apply" button
                easy_apply_btn = page.locator("button.jobs-apply-button").first
                if easy_apply_btn.count() == 0:
                    easy_apply_btn = page.locator("button:has-text('Easy Apply')").first

                if easy_apply_btn.count() == 0:
                    browser.close()
                    return ApplicationResult(
                        success=False,
                        platform=self.platform,
                        method="browser_auto",
                        error="Easy Apply button not found — job may require external application",
                    )

                easy_apply_btn.click()
                time.sleep(2)

                # Handle multi-step Easy Apply dialog
                confirmation_id = _handle_linkedin_easy_apply(
                    page, resume_path, cover_letter_path
                )

                screenshot_path = str(resume_path.parent / f"linkedin_{job.get('id', 'job')}.png")
                page.screenshot(path=screenshot_path)
                browser.close()

                return ApplicationResult(
                    success=bool(confirmation_id),
                    platform=self.platform,
                    method="browser_auto",
                    confirmation_id=confirmation_id,
                    screenshot_path=screenshot_path,
                )

        except Exception as e:
            logger.error(f"LinkedIn apply error: {e}")
            return ApplicationResult(
                success=False,
                platform=self.platform,
                method="browser_auto",
                error=str(e),
            )


def _handle_linkedin_easy_apply(page, resume_path: Path, cover_letter_path: Optional[Path]) -> str:
    """Navigate the LinkedIn Easy Apply multi-step dialog."""
    from playwright.sync_api import Page

    max_steps = 8
    for step in range(max_steps):
        time.sleep(1.5)

        # Upload resume if field present
        file_inputs = page.locator("input[type='file']")
        if file_inputs.count() > 0:
            try:
                file_inputs.first.set_input_files(str(resume_path))
                logger.info(f"Resume uploaded on step {step + 1}")
                time.sleep(1)
            except Exception:
                pass

        # Fill phone number if empty
        phone_field = page.locator("input[id*='phoneNumber']").first
        if phone_field.count() > 0 and not phone_field.input_value():
            phone_field.fill(os.environ.get("CANDIDATE_PHONE", "+91 9999999999"))

        # Click Next / Review / Submit
        next_btn = page.locator("button[aria-label='Continue to next step']").first
        review_btn = page.locator("button[aria-label='Review your application']").first
        submit_btn = page.locator("button[aria-label='Submit application']").first

        if submit_btn.count() > 0:
            submit_btn.click()
            time.sleep(2)
            logger.info("Application submitted!")
            return f"linkedin-submitted-{int(time.time())}"
        elif review_btn.count() > 0:
            review_btn.click()
        elif next_btn.count() > 0:
            next_btn.click()
        else:
            # Try generic Next button
            generic_next = page.locator("button:has-text('Next')").last
            if generic_next.count() > 0:
                generic_next.click()
            else:
                break

    return ""


# ============================================================
# EMAIL APPLIER
# ============================================================

class EmailApplier(BaseApplier):
    """Send application by email for jobs that list an email address."""

    platform = "email"

    def can_handle(self, job: dict) -> bool:
        url = job.get("url", "")
        return url.startswith("mailto:")

    def apply(
        self,
        job: dict,
        resume_path: Path,
        cover_letter_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> ApplicationResult:
        to_email = job.get("url", "").replace("mailto:", "").strip()
        from_email = os.environ.get("CANDIDATE_EMAIL", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))

        if not to_email or not from_email:
            return ApplicationResult(
                success=False,
                platform=self.platform,
                method="email",
                error="Missing to/from email. Set CANDIDATE_EMAIL env var.",
            )

        subject = f"Application for {job.get('title')} — {job.get('company')}"
        body = _build_email_body(job)

        if dry_run:
            logger.info(f"[DRY RUN] Would email: {to_email} | Subject: {subject}")
            return ApplicationResult(
                success=True,
                platform=self.platform,
                method="email",
                notes="dry_run",
            )

        try:
            msg = MIMEMultipart()
            msg["From"] = from_email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            # Attach resume
            with open(resume_path, "rb") as f:
                attach = MIMEApplication(f.read(), _subtype="docx")
                attach.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=resume_path.name,
                )
                msg.attach(attach)

            # Attach cover letter if present
            if cover_letter_path and cover_letter_path.exists():
                with open(cover_letter_path, "rb") as f:
                    attach = MIMEApplication(f.read(), _subtype="pdf")
                    attach.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=cover_letter_path.name,
                    )
                    msg.attach(attach)

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(from_email, smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent to {to_email}")
            return ApplicationResult(
                success=True,
                platform=self.platform,
                method="email",
                confirmation_id=f"email-{int(time.time())}",
            )

        except Exception as e:
            logger.error(f"Email apply error: {e}")
            return ApplicationResult(
                success=False,
                platform=self.platform,
                method="email",
                error=str(e),
            )


def _build_email_body(job: dict) -> str:
    name = os.environ.get("CANDIDATE_NAME", "Rajesh")
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to apply for the {job.get('title')} position at {job.get('company')}.\n\n"
        f"Please find my resume attached. I believe my experience in GenAI, RAG systems, "
        f"and LLM engineering aligns well with your requirements.\n\n"
        f"I would welcome the opportunity to discuss how my skills can contribute to your team.\n\n"
        f"Best regards,\n{name}"
    )


# ============================================================
# MAIN APPLICATION ENGINE
# ============================================================

class ApplicationEngine:
    """
    Orchestrates job applications across all platforms.

    Usage:
        engine = ApplicationEngine(settings)
        result = engine.apply(job, resume_path, dry_run=True)
    """

    def __init__(self, settings: dict):
        self._settings = settings
        self._appliers: list[BaseApplier] = [
            HimalayasApplier(settings),
            LinkedInApplier(settings),
            EmailApplier(settings),
        ]

    def apply(
        self,
        job: dict,
        resume_path: Path,
        cover_letter_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> ApplicationResult:
        """Apply to a job using the appropriate platform handler."""
        for applier in self._appliers:
            if applier.can_handle(job):
                logger.info(
                    f"Using {applier.platform} applier for: "
                    f"{job.get('title')} @ {job.get('company')}"
                )
                return applier.apply(job, resume_path, cover_letter_path, dry_run)

        # Fallback: open browser for manual application
        logger.warning(
            f"No automatic applier found for: {job.get('url', '')}. "
            "Opening browser for manual application."
        )
        return self._manual_open(job, resume_path, dry_run)

    def _manual_open(
        self,
        job: dict,
        resume_path: Path,
        dry_run: bool,
    ) -> ApplicationResult:
        """Open the application URL in a browser for manual completion."""
        url = job.get("url", "")
        if not url:
            return ApplicationResult(
                success=False,
                platform="manual",
                method="manual",
                error="No URL available",
            )

        if not dry_run:
            import webbrowser
            webbrowser.open(url)
            logger.info(f"Opened in browser: {url}")

        return ApplicationResult(
            success=True,
            platform="manual",
            method="browser_manual",
            notes=f"Opened for manual application: {url}",
        )
