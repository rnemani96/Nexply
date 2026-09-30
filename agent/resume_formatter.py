"""
Rajesh AI - Resume Formatter
Adapts master resume format based on target job location.
Templates: india | us | uk | eu

Inputs:
    tailored_data dict (produced by resume_tailor_v1.py) with keys:
        name          – candidate full name
        contact       – dict: phone, email, linkedin, location (city, state, country)
        summary       – str professional summary / objective
        experience    – list of {company, title, dates, bullets: list[str]}
        education     – list of {institution, degree, dates, gpa (optional)}
        skills        – list of str  OR  dict of {category: [skill, ...]}
        certifications– list of {name, issuer, date}
        languages     – list of {language, proficiency}  (used prominently in eu)
        nationality   – str  (optional; used in uk/eu)
        dob           – str  (optional; used in eu only when candidate opts in)

Outputs:
    .docx file written to output_path.

Design:
    - No LLM required
    - Content is never invented – only layout / section order changes
    - Preserves all supplied content across all templates
    - Uses python-docx for reliable .docx generation
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, RGBColor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Location-format mapping
# ---------------------------------------------------------------------------

#: Maps JD location strings (lowercased) to template names.
_LOCATION_MAP: dict[str, str] = {
    # India
    "india": "india",
    "in": "india",
    "bengaluru": "india",
    "bangalore": "india",
    "hyderabad": "india",
    "mumbai": "india",
    "pune": "india",
    "chennai": "india",
    "delhi": "india",
    "gurugram": "india",
    "noida": "india",
    # United States
    "us": "us",
    "usa": "us",
    "united states": "us",
    "united states of america": "us",
    # United Kingdom
    "uk": "uk",
    "united kingdom": "uk",
    "gb": "uk",
    "great britain": "uk",
    "england": "uk",
    "scotland": "uk",
    "wales": "uk",
    "london": "uk",
    # European Union / Europe
    "eu": "eu",
    "europe": "eu",
    "germany": "eu",
    "france": "eu",
    "netherlands": "eu",
    "spain": "eu",
    "italy": "eu",
    "sweden": "eu",
    "norway": "eu",
    "denmark": "eu",
    "finland": "eu",
    "belgium": "eu",
    "austria": "eu",
    "switzerland": "eu",
    "poland": "eu",
    "portugal": "eu",
    "ireland": "eu",
    "remote": "us",  # Default remote → US single-page style
}

_VALID_TEMPLATES = {"india", "us", "uk", "eu"}


def get_location_format(
    jd_location_format: str,
    candidate_preference: str = "auto",
) -> str:
    """Return the template name to use for resume formatting.

    Priority:
    1. If ``candidate_preference`` is not ``'auto'`` and is a valid template,
       use it directly.
    2. Otherwise look up ``jd_location_format`` in the built-in mapping.
    3. Fall back to ``'india'`` when the location cannot be resolved.

    Args:
        jd_location_format: Location string extracted from the job description
            (e.g. ``"United States"``, ``"Germany"``, ``"in"``).
        candidate_preference: Explicit override chosen by the candidate.  Pass
            ``'auto'`` (default) to derive from the JD location.

    Returns:
        One of ``'india'``, ``'us'``, ``'uk'``, ``'eu'``.
    """
    if candidate_preference and candidate_preference.lower() != "auto":
        pref = candidate_preference.lower().strip()
        if pref in _VALID_TEMPLATES:
            logger.debug("Using candidate_preference template: %s", pref)
            return pref
        logger.warning(
            "Unknown candidate_preference '%s'; falling back to JD location mapping.",
            candidate_preference,
        )

    key = jd_location_format.lower().strip() if jd_location_format else ""
    template = _LOCATION_MAP.get(key)

    if template is None:
        # Partial-match fallback: check if any known key is a substring.
        for map_key, map_val in _LOCATION_MAP.items():
            if map_key in key or key in map_key:
                template = map_val
                break

    if template is None:
        logger.warning(
            "Cannot map location '%s' to a template; defaulting to 'india'.",
            jd_location_format,
        )
        template = "india"

    logger.debug("Resolved location '%s' → template '%s'", jd_location_format, template)
    return template


# ---------------------------------------------------------------------------
# Internal docx helpers
# ---------------------------------------------------------------------------

def _set_heading_style(
    paragraph: Any,
    text: str,
    level: int = 1,
    color: RGBColor | None = None,
    font_size_pt: int = 13,
    bold: bool = True,
    all_caps: bool = False,
) -> None:
    """Write *text* into *paragraph* with explicit character formatting.

    python-docx heading styles vary by template/theme; applying explicit
    run-level formatting makes output predictable regardless of the base .docx.
    """
    paragraph.clear()
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(font_size_pt)
    if color:
        run.font.color.rgb = color
    if all_caps:
        run.font.all_caps = True


def _add_horizontal_rule(document: Any) -> None:
    """Append a thin horizontal rule paragraph using bottom border XML."""
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(2)
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "auto")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_section_heading(
    document: Any,
    title: str,
    color: RGBColor | None = None,
    font_size_pt: int = 13,
    rule: bool = True,
) -> None:
    """Add a styled section heading followed by an optional horizontal rule."""
    p = document.add_paragraph()
    _set_heading_style(p, title.upper(), color=color, font_size_pt=font_size_pt)
    if rule:
        _add_horizontal_rule(document)


def _add_bullet(document: Any, text: str, level: int = 0) -> None:
    """Add a single bullet-point paragraph."""
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.add_run(text)
    # Indent nested bullets.
    if level > 0:
        paragraph.paragraph_format.left_indent = Pt(18 * level)


def _add_experience_entry(
    document: Any,
    entry: dict[str, Any],
    show_full_dates: bool = True,
) -> None:
    """Render a single work experience block."""
    company = entry.get("company", "")
    title = entry.get("title", "")
    dates = entry.get("dates", "")
    bullets: list[str] = entry.get("bullets", [])

    # Company | Title line.
    p = document.add_paragraph()
    company_run = p.add_run(f"{company}")
    company_run.bold = True
    if title:
        p.add_run(f"  –  {title}")

    # Dates on same paragraph, right-aligned via tab stop – simulated with a tab.
    if dates:
        p.add_run(f"\t{dates}")

    p.paragraph_format.space_after = Pt(2)

    for bullet in bullets:
        if bullet.strip():
            _add_bullet(document, bullet.strip())


def _add_education_entry(document: Any, entry: dict[str, Any]) -> None:
    """Render a single education block."""
    institution = entry.get("institution", "")
    degree = entry.get("degree", "")
    dates = entry.get("dates", "")
    gpa = entry.get("gpa", "")

    p = document.add_paragraph()
    run = p.add_run(institution)
    run.bold = True

    if degree:
        p.add_run(f"  –  {degree}")
    if dates:
        p.add_run(f"\t{dates}")
    p.paragraph_format.space_after = Pt(2)

    if gpa:
        gpa_p = document.add_paragraph()
        gpa_p.add_run(f"GPA: {gpa}")
        gpa_p.paragraph_format.left_indent = Pt(18)


def _add_certifications(document: Any, certifications: list[dict[str, Any]]) -> None:
    """Render certifications list."""
    for cert in certifications:
        name = cert.get("name", "")
        issuer = cert.get("issuer", "")
        date = cert.get("date", "")
        parts = [name]
        if issuer:
            parts.append(issuer)
        if date:
            parts.append(date)
        _add_bullet(document, "  |  ".join(filter(None, parts)))


def _add_skills_section(
    document: Any,
    skills: list[str] | dict[str, list[str]],
) -> None:
    """Render skills – handles both a flat list and a categorised dict."""
    if isinstance(skills, dict):
        for category, items in skills.items():
            p = document.add_paragraph()
            cat_run = p.add_run(f"{category}: ")
            cat_run.bold = True
            p.add_run(", ".join(items))
            p.paragraph_format.space_after = Pt(2)
    else:
        p = document.add_paragraph(", ".join(skills))
        p.paragraph_format.space_after = Pt(4)


def _add_languages_section(
    document: Any,
    languages: list[dict[str, str]],
) -> None:
    """Render language skills (name + proficiency)."""
    for lang in languages:
        language = lang.get("language", "")
        proficiency = lang.get("proficiency", "")
        text = language
        if proficiency:
            text += f" – {proficiency}"
        _add_bullet(document, text)


def _set_page_margins(document: Any, top: float, bottom: float, left: float, right: float) -> None:
    """Set page margins in inches for all sections."""
    from docx.shared import Inches
    for section in document.sections:
        section.top_margin = Inches(top)
        section.bottom_margin = Inches(bottom)
        section.left_margin = Inches(left)
        section.right_margin = Inches(right)


# ---------------------------------------------------------------------------
# ResumeFormatter
# ---------------------------------------------------------------------------


class ResumeFormatter:
    """Formats tailored resume data into a .docx file using location-specific templates.

    The formatter never invents content.  It only changes layout, section
    ordering, contact-block verbosity, and optional fields depending on the
    target region's conventions.

    Args:
        master_resume_path: Path to the candidate's master ``master_resume.docx``.
            The file is used as a style/theme reference.  If the file does not
            exist, a blank document is used as base.

    Example::

        formatter = ResumeFormatter(Path("resume/master_resume.docx"))
        out = formatter.format(tailored_data, "us", Path("resume/generated/acme_v1.docx"))
    """

    _TEMPLATE_COLORS: dict[str, RGBColor] = {
        "india": RGBColor(0x1A, 0x3C, 0x6E),  # Deep navy blue
        "us":    RGBColor(0x2C, 0x2C, 0x2C),  # Near-black charcoal
        "uk":    RGBColor(0x00, 0x32, 0x7A),  # Royal blue
        "eu":    RGBColor(0x00, 0x33, 0x99),  # EU flag blue
    }

    def __init__(self, master_resume_path: Path) -> None:
        self._master_resume_path = Path(master_resume_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format(
        self,
        tailored_data: dict[str, Any],
        location_format: str,
        output_path: Path,
    ) -> Path:
        """Format *tailored_data* using *location_format* and save to *output_path*.

        Args:
            tailored_data: Resume content dict produced by the tailor engine.
                Required keys: ``name``, ``contact``, ``summary``,
                ``experience``, ``education``, ``skills``, ``certifications``.
                Optional keys: ``languages``, ``nationality``, ``dob``.
            location_format: One of ``'india'``, ``'us'``, ``'uk'``, ``'eu'``.
                Use :func:`get_location_format` to resolve this from JD metadata.
            output_path: Destination ``.docx`` path.  Parent directories will
                be created if they do not exist.

        Returns:
            The resolved absolute ``output_path``.

        Raises:
            ValueError: If *location_format* is not a recognised template name.
        """
        template = location_format.lower().strip()
        if template not in _VALID_TEMPLATES:
            raise ValueError(
                f"Unknown location_format '{location_format}'. "
                f"Valid options: {sorted(_VALID_TEMPLATES)}"
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Open master resume as styling base; fall back to blank document.
        if self._master_resume_path.exists():
            document = Document(str(self._master_resume_path))
            # Clear all existing body content so we can re-render cleanly.
            self._clear_document_body(document)
        else:
            logger.warning(
                "Master resume not found at %s; creating document from scratch.",
                self._master_resume_path,
            )
            document = Document()

        dispatcher = {
            "india": self._format_india,
            "us":    self._format_us,
            "uk":    self._format_uk,
            "eu":    self._format_eu,
        }
        dispatcher[template](document, tailored_data)

        document.save(str(output_path))
        logger.info("Saved %s resume → %s", template.upper(), output_path)
        return output_path.resolve()

    # ------------------------------------------------------------------
    # Document helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_document_body(document: Any) -> None:
        """Remove all body paragraphs and tables from *document* in place."""
        body = document.element.body
        # Collect all child elements except sectPr (section properties).
        children = [child for child in body if child.tag != qn("w:sectPr")]
        for child in children:
            body.remove(child)

    # ------------------------------------------------------------------
    # Template: India
    # ------------------------------------------------------------------

    def _format_india(self, document: Any, data: dict[str, Any]) -> None:
        """Full Indian CV format.

        Layout:
            - Full contact block (phone, email, LinkedIn, full location)
            - Professional Summary
            - Skills
            - Professional Experience
            - Education
            - Certifications
            - Languages (if present)

        Characteristics:
            - 2–3 pages acceptable
            - Nationality optional but acceptable
            - Full date ranges (e.g. Jan 2020 – Mar 2023)
        """
        color = self._TEMPLATE_COLORS["india"]
        _set_page_margins(document, top=1.0, bottom=1.0, left=1.25, right=1.25)

        # ---- Name ----
        name_p = document.add_paragraph()
        name_run = name_p.add_run(data.get("name", ""))
        name_run.bold = True
        name_run.font.size = Pt(20)
        name_run.font.color.rgb = color
        name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # ---- Full contact block ----
        contact: dict[str, Any] = data.get("contact", {})
        contact_parts: list[str] = []

        if contact.get("phone"):
            contact_parts.append(f"📞 {contact['phone']}")
        if contact.get("email"):
            contact_parts.append(f"✉ {contact['email']}")
        if contact.get("linkedin"):
            contact_parts.append(f"LinkedIn: {contact['linkedin']}")
        if contact.get("location"):
            loc = contact["location"]
            if isinstance(loc, dict):
                location_str = ", ".join(
                    filter(None, [loc.get("city"), loc.get("state"), loc.get("country")])
                )
            else:
                location_str = str(loc)
            if location_str:
                contact_parts.append(location_str)

        nationality = data.get("nationality", "")
        if nationality:
            contact_parts.append(f"Nationality: {nationality}")

        contact_p = document.add_paragraph("  |  ".join(contact_parts))
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_p.paragraph_format.space_after = Pt(8)

        # ---- Professional Summary ----
        if data.get("summary"):
            _add_section_heading(document, "Professional Summary", color=color)
            document.add_paragraph(data["summary"])

        # ---- Skills ----
        if data.get("skills"):
            _add_section_heading(document, "Skills", color=color)
            _add_skills_section(document, data["skills"])

        # ---- Professional Experience ----
        experience: list[dict[str, Any]] = data.get("experience", [])
        if experience:
            _add_section_heading(document, "Professional Experience", color=color)
            for entry in experience:
                _add_experience_entry(document, entry, show_full_dates=True)

        # ---- Education ----
        education: list[dict[str, Any]] = data.get("education", [])
        if education:
            _add_section_heading(document, "Education", color=color)
            for entry in education:
                _add_education_entry(document, entry)

        # ---- Certifications ----
        certifications: list[dict[str, Any]] = data.get("certifications", [])
        if certifications:
            _add_section_heading(document, "Certifications", color=color)
            _add_certifications(document, certifications)

        # ---- Languages ----
        languages: list[dict[str, str]] = data.get("languages", [])
        if languages:
            _add_section_heading(document, "Languages", color=color)
            _add_languages_section(document, languages)

    # ------------------------------------------------------------------
    # Template: US
    # ------------------------------------------------------------------

    def _format_us(self, document: Any, data: dict[str, Any]) -> None:
        """US-style single-page targeted resume.

        Layout:
            - No photo; abbreviated contact (City, State + email + LinkedIn)
            - Professional Summary (3–4 lines max)
            - Core Competencies / Skills (horizontal, comma-separated)
            - Professional Experience (month/year date format expected)
            - Education
            - Certifications

        Characteristics:
            - 1 page target (tight margins to maximise content)
            - No nationality, no DOB, no photo
            - Month + Year dates (e.g. "Jan 2020 – Mar 2023")
            - Bullet points start with strong action verbs
        """
        color = self._TEMPLATE_COLORS["us"]
        _set_page_margins(document, top=0.75, bottom=0.75, left=0.9, right=0.9)

        # ---- Name ----
        name_p = document.add_paragraph()
        name_run = name_p.add_run(data.get("name", "").upper())
        name_run.bold = True
        name_run.font.size = Pt(16)
        name_run.font.color.rgb = color
        name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # ---- Abbreviated contact: city/state, email, LinkedIn only ----
        contact: dict[str, Any] = data.get("contact", {})
        contact_parts: list[str] = []

        if contact.get("location"):
            loc = contact["location"]
            if isinstance(loc, dict):
                # US convention: City, State only (no country, no full address)
                location_str = ", ".join(
                    filter(None, [loc.get("city"), loc.get("state")])
                )
            else:
                location_str = str(loc)
            if location_str:
                contact_parts.append(location_str)

        if contact.get("email"):
            contact_parts.append(contact["email"])
        if contact.get("linkedin"):
            contact_parts.append(contact["linkedin"])

        contact_p = document.add_paragraph("  |  ".join(contact_parts))
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_p.paragraph_format.space_after = Pt(6)

        # ---- Professional Summary ----
        if data.get("summary"):
            _add_section_heading(document, "Summary", color=color, font_size_pt=11)
            summary_p = document.add_paragraph(data["summary"])
            summary_p.paragraph_format.space_after = Pt(4)

        # ---- Core Competencies (flat list, space-efficient) ----
        if data.get("skills"):
            _add_section_heading(document, "Core Competencies", color=color, font_size_pt=11)
            skills = data["skills"]
            if isinstance(skills, dict):
                for category, items in skills.items():
                    p = document.add_paragraph()
                    p.add_run(f"{category}: ").bold = True
                    p.add_run(", ".join(items))
                    p.paragraph_format.space_after = Pt(1)
            else:
                # Flat list – single dense paragraph.
                p = document.add_paragraph("  •  ".join(skills))
                p.paragraph_format.space_after = Pt(3)

        # ---- Professional Experience ----
        experience: list[dict[str, Any]] = data.get("experience", [])
        if experience:
            _add_section_heading(document, "Experience", color=color, font_size_pt=11)
            for entry in experience:
                _add_experience_entry(document, entry, show_full_dates=True)

        # ---- Education ----
        education: list[dict[str, Any]] = data.get("education", [])
        if education:
            _add_section_heading(document, "Education", color=color, font_size_pt=11)
            for entry in education:
                _add_education_entry(document, entry)

        # ---- Certifications ----
        certifications: list[dict[str, Any]] = data.get("certifications", [])
        if certifications:
            _add_section_heading(document, "Certifications", color=color, font_size_pt=11)
            _add_certifications(document, certifications)

    # ------------------------------------------------------------------
    # Template: UK
    # ------------------------------------------------------------------

    def _format_uk(self, document: Any, data: dict[str, Any]) -> None:
        """UK-style Curriculum Vitae (CV).

        Layout:
            - Personal Statement at top (expanded summary)
            - Full contact block (phone, email, LinkedIn, location)
            - Key Skills
            - Career History (chronological, most recent first)
            - Education
            - Certifications & Professional Development
            - Additional Information (nationality, languages if present)

        Characteristics:
            - 2 pages (A4 paper / UK standard)
            - Full date ranges (e.g. January 2020 – March 2023)
            - Nationality acceptable to include
            - Moderate section verbosity
        """
        color = self._TEMPLATE_COLORS["uk"]
        _set_page_margins(document, top=1.0, bottom=1.0, left=1.18, right=1.18)

        # ---- Name ----
        name_p = document.add_paragraph()
        name_run = name_p.add_run(data.get("name", ""))
        name_run.bold = True
        name_run.font.size = Pt(18)
        name_run.font.color.rgb = color
        name_p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # ---- Full contact block ----
        contact: dict[str, Any] = data.get("contact", {})
        contact_lines: list[str] = []

        if contact.get("phone"):
            contact_lines.append(contact["phone"])
        if contact.get("email"):
            contact_lines.append(contact["email"])
        if contact.get("linkedin"):
            contact_lines.append(contact["linkedin"])
        if contact.get("location"):
            loc = contact["location"]
            if isinstance(loc, dict):
                location_str = ", ".join(
                    filter(None, [loc.get("city"), loc.get("state"), loc.get("country")])
                )
            else:
                location_str = str(loc)
            if location_str:
                contact_lines.append(location_str)

        contact_p = document.add_paragraph("  |  ".join(contact_lines))
        contact_p.paragraph_format.space_after = Pt(8)

        # ---- Personal Statement (prominent at top) ----
        if data.get("summary"):
            _add_section_heading(document, "Personal Statement", color=color)
            document.add_paragraph(data["summary"])

        # ---- Key Skills ----
        if data.get("skills"):
            _add_section_heading(document, "Key Skills", color=color)
            _add_skills_section(document, data["skills"])

        # ---- Career History ----
        experience: list[dict[str, Any]] = data.get("experience", [])
        if experience:
            _add_section_heading(document, "Career History", color=color)
            for entry in experience:
                _add_experience_entry(document, entry, show_full_dates=True)

        # ---- Education ----
        education: list[dict[str, Any]] = data.get("education", [])
        if education:
            _add_section_heading(document, "Education", color=color)
            for entry in education:
                _add_education_entry(document, entry)

        # ---- Certifications & Professional Development ----
        certifications: list[dict[str, Any]] = data.get("certifications", [])
        if certifications:
            _add_section_heading(
                document, "Certifications & Professional Development", color=color
            )
            _add_certifications(document, certifications)

        # ---- Additional Information ----
        additional_lines: list[str] = []
        nationality = data.get("nationality", "")
        if nationality:
            additional_lines.append(f"Nationality: {nationality}")

        languages: list[dict[str, str]] = data.get("languages", [])
        if languages:
            lang_strs = [
                f"{l.get('language', '')} ({l.get('proficiency', '')})"
                for l in languages
                if l.get("language")
            ]
            if lang_strs:
                additional_lines.append(f"Languages: {', '.join(lang_strs)}")

        if additional_lines:
            _add_section_heading(document, "Additional Information", color=color)
            for line in additional_lines:
                document.add_paragraph(line)

    # ------------------------------------------------------------------
    # Template: EU (Europass-inspired)
    # ------------------------------------------------------------------

    def _format_eu(self, document: Any, data: dict[str, Any]) -> None:
        """EU / Europass-inspired CV format.

        Layout:
            - Header: Name + contact (prominent, structured)
            - Professional Profile (summary)
            - Language Skills (prominent – EU values multilingualism)
            - Work Experience
            - Education & Training
            - Digital & Technical Skills
            - Certifications
            - Personal Information (nationality, DOB if candidate opts in)

        Characteristics:
            - Europass-inspired but not strictly template-bound
            - DOB optional (include only if provided in data["dob"])
            - Language skills section is prominent and detailed
            - Section labels use EU/Europass naming conventions
        """
        color = self._TEMPLATE_COLORS["eu"]
        _set_page_margins(document, top=1.0, bottom=1.0, left=1.18, right=1.18)

        # ---- Name ----
        name_p = document.add_paragraph()
        name_run = name_p.add_run(data.get("name", "").upper())
        name_run.bold = True
        name_run.font.size = Pt(18)
        name_run.font.color.rgb = color
        name_p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # ---- Structured contact block ----
        contact: dict[str, Any] = data.get("contact", {})

        def _eu_contact_row(label: str, value: str) -> None:
            if not value:
                return
            p = document.add_paragraph()
            label_run = p.add_run(f"{label}: ")
            label_run.bold = True
            label_run.font.size = Pt(10)
            val_run = p.add_run(value)
            val_run.font.size = Pt(10)
            p.paragraph_format.space_after = Pt(1)

        if contact.get("location"):
            loc = contact["location"]
            if isinstance(loc, dict):
                location_str = ", ".join(
                    filter(None, [loc.get("city"), loc.get("state"), loc.get("country")])
                )
            else:
                location_str = str(loc)
            _eu_contact_row("Address", location_str)

        _eu_contact_row("Telephone", contact.get("phone", ""))
        _eu_contact_row("Email", contact.get("email", ""))
        _eu_contact_row("LinkedIn", contact.get("linkedin", ""))

        # Nationality (optional but accepted in EU context)
        nationality = data.get("nationality", "")
        if nationality:
            _eu_contact_row("Nationality", nationality)

        # DOB (optional – only shown if candidate explicitly supplied it)
        dob = data.get("dob", "")
        if dob:
            _eu_contact_row("Date of Birth", dob)

        document.add_paragraph().paragraph_format.space_after = Pt(4)

        # ---- Professional Profile ----
        if data.get("summary"):
            _add_section_heading(document, "Professional Profile", color=color)
            document.add_paragraph(data["summary"])

        # ---- Language Skills (prominent in EU CVs) ----
        languages: list[dict[str, str]] = data.get("languages", [])
        if languages:
            _add_section_heading(document, "Language Skills", color=color)
            for lang in languages:
                language = lang.get("language", "")
                proficiency = lang.get("proficiency", "")
                p = document.add_paragraph()
                lang_run = p.add_run(f"{language}")
                lang_run.bold = True
                if proficiency:
                    p.add_run(f"  –  {proficiency}")
                p.paragraph_format.space_after = Pt(2)

        # ---- Work Experience ----
        experience: list[dict[str, Any]] = data.get("experience", [])
        if experience:
            _add_section_heading(document, "Work Experience", color=color)
            for entry in experience:
                _add_experience_entry(document, entry, show_full_dates=True)

        # ---- Education & Training ----
        education: list[dict[str, Any]] = data.get("education", [])
        if education:
            _add_section_heading(document, "Education and Training", color=color)
            for entry in education:
                _add_education_entry(document, entry)

        # ---- Digital & Technical Skills ----
        if data.get("skills"):
            _add_section_heading(document, "Digital and Technical Skills", color=color)
            _add_skills_section(document, data["skills"])

        # ---- Certifications ----
        certifications: list[dict[str, Any]] = data.get("certifications", [])
        if certifications:
            _add_section_heading(document, "Certifications", color=color)
            _add_certifications(document, certifications)


# ---------------------------------------------------------------------------
# Module self-test (run directly: python resume_formatter.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    _sample_data: dict[str, Any] = {
        "name": "Rajesh Kumar",
        "contact": {
            "phone": "+91-9876543210",
            "email": "rajesh@example.com",
            "linkedin": "linkedin.com/in/rajeshkumar",
            "location": {
                "city": "Bengaluru",
                "state": "Karnataka",
                "country": "India",
            },
        },
        "summary": (
            "Senior Data Scientist with 6+ years of experience delivering "
            "end-to-end ML solutions across NLP, computer vision, and LLM "
            "fine-tuning for large enterprises."
        ),
        "experience": [
            {
                "company": "Acme Corp",
                "title": "Senior Data Scientist",
                "dates": "Jan 2021 – Present",
                "bullets": [
                    "Built RAG pipeline reducing hallucinations by 35%.",
                    "Led team of 5 engineers to deploy real-time recommendation engine.",
                ],
            }
        ],
        "education": [
            {
                "institution": "IIT Bombay",
                "degree": "B.Tech Computer Science",
                "dates": "2014 – 2018",
            }
        ],
        "skills": {
            "Languages": ["Python", "SQL", "Bash"],
            "ML Frameworks": ["PyTorch", "TensorFlow", "scikit-learn"],
            "Cloud": ["AWS", "GCP"],
        },
        "certifications": [
            {"name": "AWS Certified ML Specialty", "issuer": "Amazon", "date": "2023"}
        ],
        "languages": [
            {"language": "English", "proficiency": "C2 – Proficient"},
            {"language": "Hindi", "proficiency": "Native"},
        ],
        "nationality": "Indian",
    }

    _root = Path(__file__).resolve().parent.parent
    _master = _root / "resume" / "master_resume.docx"
    _out_dir = _root / "resume" / "generated"

    formatter = ResumeFormatter(_master)

    for _fmt in ("india", "us", "uk", "eu"):
        _out = _out_dir / f"test_{_fmt}.docx"
        _result = formatter.format(copy.deepcopy(_sample_data), _fmt, _out)
        print(f"  [{_fmt.upper()}] → {_result}")
