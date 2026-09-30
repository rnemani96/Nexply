"""
NEXPLY GUI - Theme & Style Constants
Beautiful dark purple/blue theme for the Job Applier application.
"""
from __future__ import annotations

# ============================================================
# COLOR PALETTE
# ============================================================

# Base backgrounds
BG_PRIMARY    = "#0D0D1A"   # Deep space navy — main window
BG_SECONDARY  = "#12122A"   # Sidebar / panels
BG_CARD       = "#1A1A35"   # Card backgrounds
BG_CARD_HOVER = "#20204A"   # Card on hover
BG_INPUT      = "#0F0F2E"   # Input fields

# Accent & brand
ACCENT_PRIMARY   = "#6C63FF"  # Electric purple — primary CTA
ACCENT_SECONDARY = "#48CFAD"  # Mint green — success / match
ACCENT_BLUE      = "#4E9FFF"  # Sky blue — info
ACCENT_PINK      = "#FF6584"  # Hot pink — alerts / danger

# Score colors
SCORE_STRONG  = "#48CFAD"   # 85+ — Strong apply
SCORE_GOOD    = "#F9CA56"   # 70-84 — Apply
SCORE_STRETCH = "#FF9A56"   # 55-69 — Stretch
SCORE_SKIP    = "#FF6584"   # <55   — Skip

# Text
TEXT_PRIMARY   = "#E8E8FF"  # Main text (slightly purple-white)
TEXT_SECONDARY = "#9090C0"  # Muted text
TEXT_DIM       = "#5A5A8A"  # Very muted
TEXT_ACCENT    = "#6C63FF"  # Accent text

# Borders
BORDER_SUBTLE = "#2A2A4A"
BORDER_ACCENT = "#6C63FF"

# Status badges
STATUS_COLORS = {
    "NEW":             ("#4E9FFF", "#0D2040"),  # blue text, dark bg
    "ANALYZED":        ("#9090C0", "#1A1A35"),
    "MATCHED":         ("#48CFAD", "#0D2820"),  # green
    "TAILORED":        ("#F9CA56", "#2A2000"),  # yellow
    "QUEUED":          ("#FF9A56", "#2A1500"),  # orange
    "APPLIED":         ("#6C63FF", "#1A1040"),  # purple
    "INTERVIEW_SCREEN":("#FF6584", "#2A0520"),  # pink
    "INTERVIEW_TECH":  ("#FF6584", "#2A0520"),
    "OFFER":           ("#48CFAD", "#0D2820"),
    "ACCEPTED":        ("#48CFAD", "#0D2820"),
    "REJECTED":        ("#FF6584", "#2A0520"),
    "GHOSTED":         ("#5A5A8A", "#1A1A35"),
    "WITHDRAWN":       ("#5A5A8A", "#1A1A35"),
}

SOURCE_COLORS = {
    "himalayas":      "#6C63FF",
    "remoteok":       "#FF6B6B",
    "jobicy":         "#48CFAD",
    "remotive":       "#4E9FFF",
    "weworkremotely": "#F9CA56",
    "aijobs":         "#FF9A56",
    "linkedin":       "#0077B5",
    "naukri":         "#FF6633",
    "wellfound":      "#16B1FF",
    "remotefirstjobs":"#9C59FF",
}

# ============================================================
# FONTS
# ============================================================
FONT_FAMILY   = "Segoe UI"
FONT_MONO     = "Consolas"

FONT_TITLE    = (FONT_FAMILY, 22, "bold")
FONT_HEADING  = (FONT_FAMILY, 14, "bold")
FONT_SUBHEAD  = (FONT_FAMILY, 12, "bold")
FONT_BODY     = (FONT_FAMILY, 12)
FONT_SMALL    = (FONT_FAMILY, 10)
FONT_TINY     = (FONT_FAMILY, 9)
FONT_MONO_SM  = (FONT_MONO, 10)

# ============================================================
# SIZES & SPACING
# ============================================================
SIDEBAR_WIDTH   = 220
CARD_PADDING    = 16
CORNER_RADIUS   = 10
BUTTON_HEIGHT   = 36
INPUT_HEIGHT    = 38

# ============================================================
# SCORE COLOR HELPER
# ============================================================

def score_color(score: float) -> str:
    if score >= 85: return SCORE_STRONG
    if score >= 70: return SCORE_GOOD
    if score >= 55: return SCORE_STRETCH
    return SCORE_SKIP

def score_label(score: float) -> str:
    if score >= 85: return "STRONG APPLY"
    if score >= 70: return "APPLY"
    if score >= 55: return "STRETCH"
    return "SKIP"

def recommendation_color(rec: str) -> str:
    return {
        "strong_apply": SCORE_STRONG,
        "apply":        SCORE_GOOD,
        "stretch":      SCORE_STRETCH,
        "skip":         SCORE_SKIP,
    }.get(rec, TEXT_SECONDARY)


# ============================================================
# ALIASES — for backwards compatibility with any view files
# ============================================================
CARD_BG  = BG_CARD          # alias
SUCCESS  = ACCENT_SECONDARY  # mint green
WARNING  = SCORE_STRETCH     # orange
DANGER   = ACCENT_PINK       # hot pink
INFO     = ACCENT_BLUE       # sky blue

FONT_LARGE  = FONT_HEADING   # (Segoe UI, 14, bold)
FONT_MEDIUM = FONT_SUBHEAD   # (Segoe UI, 12, bold)
