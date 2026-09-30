"""
RAJESH AI - Job Location Filter
Smart filter that enforces the rule:

  "If a job is from a foreign country (not India / not Remote / not Worldwide)
   it must offer visa sponsorship — otherwise discard it."

Home-country jobs and remote/worldwide jobs are always kept.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# HOME-COUNTRY SIGNALS  (always keep — no visa needed)
# ============================================================

# Location strings that indicate the job is within India
INDIA_SIGNALS = [
    "india", "hyderabad", "bangalore", "bengaluru", "mumbai", "delhi",
    "new delhi", "pune", "chennai", "kolkata", "noida", "gurgaon",
    "gurugram", "ahmedabad", "jaipur", "kochi", "cochin", "indore",
    "bhubaneswar", "chandigarh", "surat", "lucknow", "nagpur", "vizag",
    "visakhapatnam", "coimbatore", "vadodara",
]

# Remote/Worldwide signals — job is accessible from India without relocation
REMOTE_SIGNALS = [
    "remote", "worldwide", "anywhere", "globally", "work from anywhere",
    "work from home", "wfh", "distributed", "fully remote", "100% remote",
    "all locations", "location independent", "no location", "global",
    "international remote",
]

# ============================================================
# FOREIGN COUNTRY SIGNALS  (require visa sponsorship)
# ============================================================

# Countries that are clearly NOT India
FOREIGN_COUNTRY_PATTERNS = [
    # North America
    r"\busa\b", r"\bu\.s\.a\b", r"\bunited states\b", r"\bcanada\b",
    r"\bnew york\b", r"\bsan francisco\b", r"\bseattle\b", r"\baustin\b",
    r"\bboston\b", r"\bchicago\b", r"\blos angeles\b", r"\bla\b",
    r"\btoronto\b", r"\bvancouver\b", r"\bmontreal\b",

    # Europe
    r"\buk\b", r"\bunited kingdom\b", r"\bgreat britain\b",
    r"\blondon\b", r"\bmanchester\b", r"\bbirmingham\b", r"\bedinburgh\b",
    r"\bgermany\b", r"\bberlin\b", r"\bmunich\b", r"\bfrankfurt\b",
    r"\bhamburg\b", r"\bnetherlands\b", r"\bamsterdam\b",
    r"\bfrance\b", r"\bparis\b", r"\bspain\b", r"\bmadrid\b",
    r"\bbarcelona\b", r"\bsweden\b", r"\bstockholm\b",
    r"\bdenmark\b", r"\bcopenhagen\b", r"\bnorway\b", r"\boslo\b",
    r"\bfinland\b", r"\bhelsinki\b", r"\bireland\b", r"\bdublin\b",
    r"\bswitzerland\b", r"\bzurich\b", r"\bausria\b", r"\bvienna\b",
    r"\bpoland\b", r"\bwarsaw\b", r"\bczech\b", r"\bprague\b",
    r"\bportugal\b", r"\blisbon\b", r"\bbelgium\b", r"\bbrussels\b",
    r"\bitaly\b", r"\brome\b", r"\bmilan\b", r"\bestonia\b",
    r"\blatvia\b", r"\blithuania\b",

    # Asia-Pacific (non-India)
    r"\bsingapore\b", r"\baustralia\b", r"\bsydney\b", r"\bmelbourne\b",
    r"\bnew zealand\b", r"\bauckland\b", r"\bjapan\b", r"\btokyo\b",
    r"\bsouth korea\b", r"\bseoul\b", r"\btaiwan\b", r"\bhong kong\b",
    r"\bchina\b", r"\bbeijing\b", r"\bshanghai\b", r"\bshenzhen\b",
    r"\bmalaysia\b", r"\bkuala lumpur\b", r"\bindonesia\b",
    r"\bjakarta\b", r"\bthailand\b", r"\bbangkok\b", r"\bvietnam\b",

    # Middle East
    r"\buae\b", r"\bdubai\b", r"\babu dhabi\b", r"\bsaudi\b",
    r"\bqatar\b", r"\bkuwait\b", r"\bbahrain\b", r"\boman\b",
    r"\bisrael\b", r"\btel aviv\b",

    # Africa
    r"\bsouth africa\b", r"\bjohannesburg\b", r"\bcape town\b",
    r"\bnairobi\b", r"\bnigeria\b", r"\blagos\b",

    # Latin America
    r"\bbrazil\b", r"\bsao paulo\b", r"\bmexico\b",
    r"\bargentina\b", r"\bbogota\b",
]

_FOREIGN_RE = re.compile(
    "|".join(FOREIGN_COUNTRY_PATTERNS),
    re.IGNORECASE,
)


# ============================================================
# FILTER DECISION
# ============================================================

@dataclass
class FilterDecision:
    keep: bool
    reason: str          # Human-readable explanation
    is_remote: bool
    is_home_country: bool
    is_foreign: bool
    visa_sponsoring: bool
    detected_country: str   # e.g. "UK", "Singapore", or ""


def decide(
    title: str,
    location: str,
    remote_type: str,
    description: str,
    source: str = "",
    home_country: str = "India",
) -> FilterDecision:
    """
    Decide whether to keep or discard a job.

    Rules (in order):
    1. Remote / Worldwide  → always KEEP
    2. Home country        → always KEEP
    3. Foreign country with visa sponsorship → KEEP
    4. Foreign country without visa sponsorship → DISCARD
    5. Unknown location    → KEEP (assume remote / no restriction)
    """
    loc_lower  = (location or "").lower().strip()
    desc_lower = (description or "").lower()
    rt_lower   = (remote_type or "").lower()

    # ----------------------------------------------------------
    # 1. Remote / Worldwide signal
    # ----------------------------------------------------------
    is_remote = (
        not loc_lower                                 # empty location = assume remote
        or any(sig in rt_lower for sig in REMOTE_SIGNALS)
        or any(sig in loc_lower for sig in REMOTE_SIGNALS)
        or source in ("remoteok", "remotive", "weworkremotely", "aijobs", "remotefirstjobs")
    )

    if is_remote:
        return FilterDecision(
            keep=True,
            reason="Remote / Worldwide — open to all locations",
            is_remote=True,
            is_home_country=False,
            is_foreign=False,
            visa_sponsoring=False,
            detected_country="",
        )

    # ----------------------------------------------------------
    # 2. Home country (India) signal
    # ----------------------------------------------------------
    home_lower = home_country.lower()
    # Build signal list: always includes generic india signals + custom home country
    home_signals = INDIA_SIGNALS if home_lower == "india" else [home_lower]

    is_home = any(sig in loc_lower for sig in home_signals)

    if is_home:
        return FilterDecision(
            keep=True,
            reason=f"Home country ({home_country}) — no visa needed",
            is_remote=False,
            is_home_country=True,
            is_foreign=False,
            visa_sponsoring=False,
            detected_country=home_country,
        )

    # ----------------------------------------------------------
    # 3. Detect foreign country
    # ----------------------------------------------------------
    foreign_match = _FOREIGN_RE.search(loc_lower)
    if not foreign_match:
        # No clear foreign signal — could be city-only or generic.
        # Check description for country context
        foreign_match = _FOREIGN_RE.search(desc_lower[:500])

    is_foreign = foreign_match is not None
    detected_country = foreign_match.group(0).title() if foreign_match else ""

    if not is_foreign:
        # Unknown location — keep it (benefit of doubt: could be remote-friendly)
        return FilterDecision(
            keep=True,
            reason="Location unclear — keeping (assumed accessible)",
            is_remote=False,
            is_home_country=False,
            is_foreign=False,
            visa_sponsoring=False,
            detected_country="",
        )

    # ----------------------------------------------------------
    # 4. Foreign job — check for visa sponsorship
    # ----------------------------------------------------------
    from agent.sources.visa_jobs_source import check_visa_sponsorship, is_visa_job
    sponsors, visa_label = is_visa_job(title, description)

    if sponsors:
        return FilterDecision(
            keep=True,
            reason=f"Foreign ({detected_country}) + Visa sponsored: {visa_label}",
            is_remote=False,
            is_home_country=False,
            is_foreign=True,
            visa_sponsoring=True,
            detected_country=detected_country,
        )

    # ----------------------------------------------------------
    # 5. Foreign, no sponsorship — DISCARD
    # ----------------------------------------------------------
    return FilterDecision(
        keep=False,
        reason=f"Foreign ({detected_country}) — no visa sponsorship mentioned",
        is_remote=False,
        is_home_country=False,
        is_foreign=True,
        visa_sponsoring=False,
        detected_country=detected_country,
    )


def should_keep(
    title: str,
    location: str,
    remote_type: str,
    description: str,
    source: str = "",
    home_country: str = "India",
    enabled: bool = True,
) -> tuple[bool, str]:
    """
    Simple boolean wrapper.
    Returns (keep: bool, reason: str).
    If `enabled=False` skips filtering entirely (keep everything).
    """
    if not enabled:
        return True, "Filter disabled"
    d = decide(title, location, remote_type, description, source, home_country)
    return d.keep, d.reason
