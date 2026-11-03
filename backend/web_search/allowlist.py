"""Civic domain allowlist for web search — strictly limits queries to official Indian government domains.

No open-internet scraping is permitted. All URLs fetched must belong to the allowlist.
"""
from __future__ import annotations

from urllib.parse import urlparse

from backend.modules.domain_router import Domain

# Official Indian government domain allowlist — only these TLDs/domains are permitted
CIVIC_ALLOWLIST_DOMAINS: tuple[str, ...] = (
    "gov.in",
    "nic.in",
    "rbi.org.in",
    "npci.org.in",
    "uidai.gov.in",
    "incometax.gov.in",
    "parivahan.gov.in",
    "epfindia.gov.in",
    "passport.gov.in",
    "india.gov.in",
    "mca.gov.in",
    "sebi.gov.in",
    "irdai.gov.in",
    "cbse.gov.in",
    "digilocker.gov.in",
    "nha.gov.in",
    "abdm.gov.in",
    "pmkisan.gov.in",
    "eci.gov.in",
    "nvsp.in",
    "onlineservices.uidai.gov.in",
    "serviceonline.gov.in",
    "umang.gov.in",
    "nsdl.co.in",
    "ihmcl.co.in",
    "cbse.nic.in",
)

# Domain-specific additional site constraints for better precision
_DOMAIN_SITE_HINTS: dict[Domain, tuple[str, ...]] = {
    Domain.TAXATION: ("incometax.gov.in", "cbdt.gov.in"),
    Domain.BANKING: ("rbi.org.in", "npci.org.in"),
    Domain.TRANSPORT: ("parivahan.gov.in", "nhai.gov.in", "ihmcl.co.in", "vahan.parivahan.gov.in"),
    Domain.IDENTITY: ("uidai.gov.in", "digilocker.gov.in", "passport.gov.in", "eci.gov.in"),
    Domain.EDUCATION: ("cbse.gov.in", "cbse.nic.in", "digilocker.gov.in", "nta.ac.in"),
    Domain.AGRICULTURE: ("pmkisan.gov.in", "agri.gov.in", "farmer.gov.in"),
    Domain.LEGAL_CONSUMER: ("edaakhil.nic.in", "nalsa.gov.in", "consumerhelpline.gov.in"),
}

# Site constraint query fragment (appended to DuckDuckGo search)
_ALLOWLIST_SITE_QUERY = " ".join(f"site:{d}" for d in CIVIC_ALLOWLIST_DOMAINS[:10])


import re

def build_allowlist_query(user_query: str, domain: Domain) -> str:
    """Build a search query with targeted official domain constraints."""
    clean_query = user_query.strip()
    clean_query = re.sub(r"[?!.,'\"]+", " ", clean_query)
    clean_query = " ".join(clean_query.split())
    lowered = clean_query.lower()

    # Prioritize specific official service portals if explicitly mentioned in query
    if "digilocker" in lowered:
        site_constraint = "site:digilocker.gov.in"
    elif "fastag" in lowered or "ihmcl" in lowered:
        site_constraint = "site:ihmcl.co.in"
    elif any(t in lowered for t in ("parivahan", "vahan", "sarathi", "chassis", "challan")):
        site_constraint = "site:parivahan.gov.in"
    elif "cbse" in lowered:
        site_constraint = "site:cbse.gov.in"
    elif "pm kisan" in lowered or "pmkisan" in lowered:
        site_constraint = "site:pmkisan.gov.in"
    elif any(t in lowered for t in ("epfo", "epf", "uan", "provident")):
        site_constraint = "site:epfindia.gov.in"
    elif any(t in lowered for t in ("income tax", "itr", "form 16", "cbdt")):
        site_constraint = "site:incometax.gov.in"
    elif "passport" in lowered:
        site_constraint = "site:passportindia.gov.in"
    elif any(t in lowered for t in ("aadhaar", "uidai")):
        site_constraint = "site:uidai.gov.in"
    else:
        domain_hints = _DOMAIN_SITE_HINTS.get(domain, ())
        if domain_hints:
            primary = domain_hints[0]
            site_constraint = f"site:{primary}"
        else:
            site_constraint = "site:gov.in"

    return f"{clean_query} {site_constraint}"


def is_allowlisted_url(url: str) -> bool:
    """Returns True iff the URL's hostname belongs to a civic government domain in the allowlist.

    Strict: rejects any URL not ending with an allowlisted domain suffix.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or parsed.path).lower().split(":")[0]  # strip port
        if not host:
            return False
        return any(host == d or host.endswith(f".{d}") for d in CIVIC_ALLOWLIST_DOMAINS)
    except Exception:
        return False


__all__ = [
    "CIVIC_ALLOWLIST_DOMAINS",
    "build_allowlist_query",
    "is_allowlisted_url",
]
