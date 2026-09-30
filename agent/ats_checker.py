"""
Nexply - ATS Checker
Scores a generated resume for ATS (Applicant Tracking System) compatibility.

Inputs:
    resume_path           – Path to a .docx resume file
    jd_required_skills    – list[str] of skills extracted from the JD
    min_score             – pass/fail threshold (default 75)

Outputs:
    ATSReport dataclass instance with:
        score             – composite score 0–100
        keyword_density   – fraction of required skills found in the document
        matched_keywords  – skills found in document text
        missing_keywords  – skills NOT found in document text
        warnings          – list of human-readable ATS issue descriptions
        passed            – True when score >= min_score

Design:
    - Deterministic; no LLM required
    - Read-only: never modifies the resume
    - Works entirely from plain text extracted from the .docx
    - Penalises known ATS-hostile structural elements
    - Provides actionable warnings the candidate can act on
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Standard section headings every ATS expects to find.  Absence of any
#: of these headings incurs a penalty.
STANDARD_SECTIONS: list[str] = [
    "experience",
    "education",
    "skills",
]

#: Broader set of acceptable heading synonyms used for detection only
#: (no penalty – they are aliases for the standard headings above).
_SECTION_SYNONYMS: dict[str, list[str]] = {
    "experience": [
        "experience",
        "work experience",
        "professional experience",
        "career history",
        "employment history",
        "work history",
    ],
    "education": [
        "education",
        "education and training",
        "academic background",
        "qualifications",
    ],
    "skills": [
        "skills",
        "core competencies",
        "key skills",
        "technical skills",
        "digital and technical skills",
        "competencies",
    ],
}

#: Common ATS-safe font families.  Anything outside this list triggers a
#: warning (but NO score penalty – non-standard fonts are cosmetic, not fatal).
_ATS_SAFE_FONTS: set[str] = {
    "arial",
    "calibri",
    "cambria",
    "garamond",
    "georgia",
    "helvetica",
    "times new roman",
    "trebuchet ms",
    "verdana",
    "palatino",
    "tahoma",
    "century gothic",
    "gill sans",
    "open sans",
    "roboto",
    "lato",
    "ubuntu",
    "source sans pro",
}

# ---------------------------------------------------------------------------
# Penalty weights
# ---------------------------------------------------------------------------

_PENALTY_TABLE_LAYOUT: int = 10   # Tables used for visual layout
_PENALTY_TEXT_BOX: int = 15       # Text boxes (often invisible to parsers)
_PENALTY_HEADER_FOOTER_KEY_INFO: int = 10  # Critical contact in header/footer
_PENALTY_MISSING_SECTION: int = 5  # Per missing standard section
_PENALTY_IMAGES: int = 10          # Embedded images in body
_PENALTY_PER_MISSING_SKILL: int = 3  # Per missing required keyword


# ---------------------------------------------------------------------------
# ATSReport
# ---------------------------------------------------------------------------


@dataclass
class ATSReport:
    """Result of an ATS compatibility check.

    Attributes:
        score:            Composite ATS score from 0 to 100.
        keyword_density:  Fraction of required skills present (0.0 – 1.0).
        matched_keywords: Required skills found in document text.
        missing_keywords: Required skills NOT found in document text.
        warnings:         List of human-readable ATS issue descriptions.
        passed:           ``True`` when ``score >= min_score`` threshold.
    """

    score: float
    keyword_density: float
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: bool = False

    def __str__(self) -> str:  # pragma: no cover
        status = "PASS ✓" if self.passed else "FAIL ✗"
        lines = [
            f"ATS Report  [{status}]",
            f"  Score            : {self.score:.1f} / 100",
            f"  Keyword Density  : {self.keyword_density:.1%}",
            f"  Matched Skills   : {len(self.matched_keywords)}",
            f"  Missing Skills   : {len(self.missing_keywords)}",
        ]
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    • {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone helpers (importable independently)
# ---------------------------------------------------------------------------


def get_plain_text(docx_path: Path) -> str:
    """Extract all readable text from a .docx file as a single string.

    Extracts text from:
    - All body paragraphs (including numbered/bulleted lists)
    - All table cells
    - Headers and footers (concatenated separately so callers can detect
      whether key contact info lives only there)

    Args:
        docx_path: Absolute or relative path to the ``.docx`` file.

    Returns:
        A single string with all extracted text, newline-separated.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a valid .docx.
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"Resume file not found: {docx_path}")

    try:
        document = Document(str(docx_path))
    except Exception as exc:
        raise ValueError(f"Cannot open '{docx_path}' as a .docx file: {exc}") from exc

    parts: list[str] = []

    # Body paragraphs.
    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    # Table cells.
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    text = para.text.strip()
                    if text:
                        parts.append(text)

    return "\n".join(parts)


def _get_header_footer_text(document: Any) -> str:
    """Return concatenated text from all headers and footers in *document*."""
    parts: list[str] = []
    for section in document.sections:
        for hf in (
            section.header,
            section.footer,
            section.even_page_header,
            section.even_page_footer,
            section.first_page_header,
            section.first_page_footer,
        ):
            try:
                for para in hf.paragraphs:
                    text = para.text.strip()
                    if text:
                        parts.append(text)
            except Exception:
                pass
    return "\n".join(parts)


def check_section_headings(text: str) -> list[str]:
    """Identify which standard ATS section headings are missing from *text*.

    Checks against synonym lists so that regional heading variants (e.g.
    ``"Career History"`` for ``"Experience"``) are correctly recognised.

    Args:
        text: Full plain-text content of the resume (case-insensitive match).

    Returns:
        List of standard section names that are absent from *text*.  An empty
        list means all required sections are present.

    Example::

        missing = check_section_headings(plain_text)
        # → [] if all good, or ["education"] if that section is absent
    """
    text_lower = text.lower()
    missing: list[str] = []

    for section, synonyms in _SECTION_SYNONYMS.items():
        found = any(synonym in text_lower for synonym in synonyms)
        if not found:
            missing.append(section)

    return missing


# ---------------------------------------------------------------------------
# Internal structural checks (operate on the Document object directly)
# ---------------------------------------------------------------------------


def _has_layout_tables(document: Any) -> bool:
    """Return True if any table in the document appears to be used for layout.

    Heuristic: a table whose first cell spans the full width or whose first
    row has exactly 2 columns with no visible borders is likely a layout table.
    We flag ANY table as a potential layout table to be conservative.
    """
    return len(document.tables) > 0


def _has_text_boxes(document: Any) -> bool:
    """Return True if the document body contains any drawing / text box elements."""
    body = document.element.body
    # Text boxes are represented as <w:txbxContent> inside drawing elements.
    txbx_elements = body.findall(
        ".//" + qn("w:txbxContent")
    )
    drawing_elements = body.findall(
        ".//" + qn("wp:inline")
    ) + body.findall(
        ".//" + qn("wp:anchor")
    )
    return bool(txbx_elements) or bool(drawing_elements)


def _has_body_images(document: Any) -> bool:
    """Return True if any inline image (blip) exists in the body paragraphs."""
    body = document.element.body
    blips = body.findall(".//" + qn("a:blip"))
    return bool(blips)


def _collect_fonts(document: Any) -> set[str]:
    """Collect all font names referenced in the document body runs."""
    fonts: set[str] = set()
    for para in document.paragraphs:
        for run in para.runs:
            if run.font.name:
                fonts.add(run.font.name.lower())
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if run.font.name:
                            fonts.add(run.font.name.lower())
    return fonts


def _key_info_in_header_footer(hf_text: str) -> bool:
    """Return True if critical contact info (email or phone) appears only in header/footer."""
    email_pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    phone_pattern = re.compile(r"[\+\d][\d\s\-\(\)]{7,}")
    return bool(email_pattern.search(hf_text) or phone_pattern.search(hf_text))


# ---------------------------------------------------------------------------
# Keyword matching helpers
# ---------------------------------------------------------------------------


def _normalize_skill(skill: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    skill = skill.lower()
    skill = re.sub(r"[-_/]", " ", skill)
    skill = re.sub(r"[^\w\s]", "", skill)
    skill = re.sub(r"\s+", " ", skill)
    return skill.strip()


def _skill_in_text(skill: str, text_lower: str) -> bool:
    """Return True if *skill* (normalised) appears as a phrase in *text_lower*."""
    norm = _normalize_skill(skill)
    if not norm:
        return False
    # Whole-phrase search; for single-token skills use word boundary.
    tokens = norm.split()
    if len(tokens) == 1:
        return bool(re.search(r"\b" + re.escape(tokens[0]) + r"\b", text_lower))
    return norm in text_lower


# ---------------------------------------------------------------------------
# ATSChecker
# ---------------------------------------------------------------------------


class ATSChecker:
    """Checks a ``.docx`` resume for ATS compatibility and keyword coverage.

    The checker is stateless – each call to :meth:`check` is independent.
    Instantiate once and reuse across multiple resumes.

    Example::

        checker = ATSChecker()
        report = checker.check(
            resume_path=Path("resume/generated/acme_v1.docx"),
            jd_required_skills=["Python", "SQL", "AWS", "Docker"],
            min_score=75,
        )
        print(report)
        if not report.passed:
            print("Missing skills:", report.missing_keywords)
    """

    def check(
        self,
        resume_path: Path,
        jd_required_skills: list[str],
        min_score: float = 75.0,
    ) -> ATSReport:
        """Score *resume_path* for ATS compatibility against *jd_required_skills*.

        Penalty schedule (from 100-point base):
            - Layout tables detected                 → −10
            - Text boxes / floating objects detected → −15
            - Key contact info in header/footer only → −10
            - Missing section heading (per section)  → −5
            - Images in body                         → −10
            - Missing required skill (per skill)     → −3

        Non-standard fonts trigger a *warning* only (no score deduction) since
        font choice rarely breaks ATS parsing but is worth flagging.

        Args:
            resume_path:        Path to the ``.docx`` resume to audit.
            jd_required_skills: Skills extracted from the job description.
                                 These are checked against document text.
            min_score:          Score threshold for ``ATSReport.passed``.
                                 Default is 75.

        Returns:
            :class:`ATSReport` with full findings.

        Raises:
            FileNotFoundError: If *resume_path* does not exist.
            ValueError:        If the file cannot be parsed as .docx.
        """
        resume_path = Path(resume_path)

        # ----------------------------------------------------------------
        # Load document once; derive text from it.
        # ----------------------------------------------------------------
        if not resume_path.exists():
            raise FileNotFoundError(f"Resume not found: {resume_path}")

        try:
            document = Document(str(resume_path))
        except Exception as exc:
            raise ValueError(
                f"Cannot open '{resume_path}' as .docx: {exc}"
            ) from exc

        plain_text = get_plain_text(resume_path)
        hf_text = _get_header_footer_text(document)
        combined_text_lower = (plain_text + "\n" + hf_text).lower()

        warnings: list[str] = []
        score: float = 100.0

        # ----------------------------------------------------------------
        # Check 1: Layout tables
        # ----------------------------------------------------------------
        if _has_layout_tables(document):
            score -= _PENALTY_TABLE_LAYOUT
            warnings.append(
                f"Tables detected in document (−{_PENALTY_TABLE_LAYOUT} pts). "
                "Multi-column table layouts can prevent ATS parsers from reading "
                "content in the correct order. Use plain single-column layout instead."
            )
            logger.debug("ATS: layout table penalty applied.")

        # ----------------------------------------------------------------
        # Check 2: Text boxes / floating objects
        # ----------------------------------------------------------------
        if _has_text_boxes(document):
            score -= _PENALTY_TEXT_BOX
            warnings.append(
                f"Text boxes or floating drawing objects detected (−{_PENALTY_TEXT_BOX} pts). "
                "Content inside text boxes is often skipped entirely by ATS parsers. "
                "Move all text into standard paragraphs."
            )
            logger.debug("ATS: text box penalty applied.")

        # ----------------------------------------------------------------
        # Check 3: Key contact info only in header/footer
        # ----------------------------------------------------------------
        if _key_info_in_header_footer(hf_text):
            # Only penalise if the info does NOT also appear in the body.
            body_has_email = bool(
                re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", plain_text)
            )
            body_has_phone = bool(re.search(r"[\+\d][\d\s\-\(\)]{7,}", plain_text))
            if not body_has_email or not body_has_phone:
                score -= _PENALTY_HEADER_FOOTER_KEY_INFO
                warnings.append(
                    f"Contact information (email/phone) found in header or footer only "
                    f"(−{_PENALTY_HEADER_FOOTER_KEY_INFO} pts). "
                    "Many ATS systems do not parse headers/footers. "
                    "Repeat all contact details in the body of the document."
                )
                logger.debug("ATS: header/footer key info penalty applied.")

        # ----------------------------------------------------------------
        # Check 4: Missing standard section headings
        # ----------------------------------------------------------------
        missing_sections = check_section_headings(plain_text)
        for section in missing_sections:
            score -= _PENALTY_MISSING_SECTION
            warnings.append(
                f"Standard section '{section.title()}' not found "
                f"(−{_PENALTY_MISSING_SECTION} pts). "
                "ATS systems rely on section headings to categorise content. "
                f"Add a clearly labelled '{section.title()}' section."
            )
            logger.debug("ATS: missing section '%s' penalty applied.", section)

        # ----------------------------------------------------------------
        # Check 5: Embedded images in body
        # ----------------------------------------------------------------
        if _has_body_images(document):
            score -= _PENALTY_IMAGES
            warnings.append(
                f"Embedded images detected in document body (−{_PENALTY_IMAGES} pts). "
                "Images (including photo, logo, or icon graphics) are invisible to ATS "
                "text parsers. Remove images or replace with plain text equivalents."
            )
            logger.debug("ATS: body image penalty applied.")

        # ----------------------------------------------------------------
        # Check 6: Non-standard fonts (warn only, no penalty)
        # ----------------------------------------------------------------
        used_fonts = _collect_fonts(document)
        non_standard = used_fonts - _ATS_SAFE_FONTS
        if non_standard:
            warnings.append(
                f"Non-standard font(s) detected: {', '.join(sorted(non_standard))} "
                "(warning only – no score deduction). "
                "While most modern ATS handle font substitution, using a standard "
                "font (Arial, Calibri, Times New Roman, etc.) is safer."
            )
            logger.debug("ATS: non-standard fonts noted: %s", non_standard)

        # ----------------------------------------------------------------
        # Keyword density & missing skill penalties
        # ----------------------------------------------------------------
        matched_keywords: list[str] = []
        missing_keywords: list[str] = []

        for skill in jd_required_skills:
            if not skill or not skill.strip():
                continue
            if _skill_in_text(skill, combined_text_lower):
                matched_keywords.append(skill)
            else:
                missing_keywords.append(skill)
                score -= _PENALTY_PER_MISSING_SKILL

        if missing_keywords:
            # Single aggregated warning to avoid noise.
            warnings.append(
                f"{len(missing_keywords)} required skill(s) not found in resume "
                f"(−{len(missing_keywords) * _PENALTY_PER_MISSING_SKILL} pts total): "
                + ", ".join(missing_keywords[:10])
                + ("…" if len(missing_keywords) > 10 else "")
                + ". Incorporate these keywords naturally into your Skills or "
                  "Experience sections."
            )

        # ----------------------------------------------------------------
        # Keyword density
        # ----------------------------------------------------------------
        total_skills = len(jd_required_skills)
        keyword_density: float = (
            len(matched_keywords) / total_skills if total_skills > 0 else 1.0
        )

        # ----------------------------------------------------------------
        # Clamp score and determine pass/fail
        # ----------------------------------------------------------------
        score = max(0.0, min(100.0, score))
        passed = score >= min_score

        report = ATSReport(
            score=round(score, 2),
            keyword_density=round(keyword_density, 4),
            matched_keywords=matched_keywords,
            missing_keywords=missing_keywords,
            warnings=warnings,
            passed=passed,
        )

        logger.info(
            "ATS check complete for '%s': score=%.1f, passed=%s, "
            "matched=%d/%d skills, warnings=%d",
            resume_path.name,
            score,
            passed,
            len(matched_keywords),
            total_skills,
            len(warnings),
        )

        return report


# ---------------------------------------------------------------------------
# Module self-test (run directly: python ats_checker.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    _root = Path(__file__).resolve().parent.parent
    _generated_dir = _root / "resume" / "generated"

    _test_skills = [
        "Python",
        "SQL",
        "AWS",
        "Docker",
        "Kubernetes",
        "PyTorch",
        "RAG",
        "LLM",
    ]

    checker = ATSChecker()

    # Test against any generated resume found in the generated dir.
    _docx_files = list(_generated_dir.glob("*.docx"))

    if not _docx_files:
        print(
            "No .docx files found in",
            _generated_dir,
            "– run resume_formatter.py self-test first.",
        )
        sys.exit(0)

    for _resume in _docx_files:
        print(f"\n{'='*60}")
        print(f"Checking: {_resume.name}")
        print("=" * 60)
        try:
            _report = checker.check(_resume, _test_skills, min_score=75)
            print(_report)
        except Exception as _exc:
            print(f"ERROR: {_exc}")
