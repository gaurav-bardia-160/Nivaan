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
    "dfpd.gov.in",
    "nfsa.gov.in",
    "financialservices.gov.in",
    "jansamarth.in",
    "pfrda.org.in",
    "dicgc.org.in",
)

# Domain-specific additional site constraints for better precision
_DOMAIN_SITE_HINTS: dict[Domain, tuple[str, ...]] = {
    Domain.TAXATION: ("incometax.gov.in", "cbdt.gov.in"),
    Domain.BANKING: ("rbi.org.in", "npci.org.in", "financialservices.gov.in", "jansamarth.in", "dicgc.org.in"),
    Domain.TRANSPORT: ("parivahan.gov.in", "nhai.gov.in", "ihmcl.co.in", "vahan.parivahan.gov.in"),
    Domain.IDENTITY: ("uidai.gov.in", "digilocker.gov.in", "passport.gov.in", "eci.gov.in"),
    Domain.EDUCATION: ("cbse.gov.in", "cbse.nic.in", "digilocker.gov.in", "nta.ac.in"),
    Domain.AGRICULTURE: ("pmkisan.gov.in", "agri.gov.in", "farmer.gov.in"),
    Domain.LEGAL_CONSUMER: ("edaakhil.nic.in", "nalsa.gov.in", "consumerhelpline.gov.in"),
}

# Site constraint query fragment (appended to DuckDuckGo search)
_ALLOWLIST_SITE_QUERY = " ".join(f"site:{d}" for d in CIVIC_ALLOWLIST_DOMAINS[:10])


import re


def extract_search_keywords(user_query: str) -> str:
    """Extract high-signal civic search terms from conversational citizen questions."""
    clean_query = user_query.strip()
    # Split into clauses to isolate the problem/question clause from conversational preamble
    clauses = re.split(r"[.?!;]|\b(?:but|however|although)\b", clean_query, flags=re.I)
    target_clause = clean_query
    for c in reversed(clauses):
        c_clean = c.strip()
        if len(c_clean) > 10 and any(term in c_clean.lower() for term in (
            "how", "what", "where", "fix", "correct", "update", "apply", "change",
            "error", "mismatch", "failed", "download", "status", "refund", "card", "portal", "rc"
        )):
            target_clause = c_clean
            break

    # Strip conversational filler phrases
    filler_patterns = (
        r"\b(?:can you please|could you please|please tell me|tell me|i want to know|how do i|how can i|how to|what is the procedure to|what is the process to|let me know)\b",
        r"\b(?:permanently|kindly|urgently|help me with|facing an issue with|there is an error with|showing error|error on|problem with)\b",
        r"\b(?:so it shows in my app|in my app|on portal|on website|in portal|so that)\b",
    )
    simplified = target_clause
    for pat in filler_patterns:
        simplified = re.sub(pat, " ", simplified, flags=re.I)

    words = re.findall(r"\b[A-Za-z0-9_-]+\b", simplified)
    stop_words = {
        "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "and", "but", "or", "so", "if", "then", "this", "that",
        "these", "those", "my", "your", "his", "her", "its", "our", "their", "me", "him", "us", "them",
        "it", "i", "you", "we", "they", "after", "before", "while", "during", "seeing", "let", "go"
    }
    meaningful = [w for w in words if w.lower() not in stop_words]

    # Ensure critical civic domain acronyms/keywords from the full prompt are always preserved
    lowered_full = clean_query.lower()
    for entity in ("parivahan", "vahan", "sarathi", "rc", "chassis", "fastag", "ihmcl", "aadhaar", "pan", "epfo", "cbse", "passport"):
        if entity in lowered_full and not any(w.lower() == entity for w in meaningful):
            meaningful.append(entity)

    if len(meaningful) >= 2:
        return " ".join(meaningful[:8])
    return re.sub(r"[?!.,'\"]+", " ", clean_query).strip()[:80]


def preferred_domains_for_query(user_query: str, domain: Domain) -> tuple[str, ...]:
    """Return the narrow official host set that should satisfy a citizen query."""
    lowered = user_query.lower()
    rules: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("one nation one ration", "onorc", "mera ration", "ration portability"), ("nfsa.gov.in", "dfpd.gov.in")),
        (("mudra", "pmmy"), ("financialservices.gov.in", "jansamarth.in", "mudra.org.in")),
        (("ombudsman", "reserve bank complaint", "rbi complaint", "cms complaint"), ("rbi.org.in", "cms.rbi.org.in")),
        (("udgam", "unclaimed deposit"), ("rbi.org.in", "udgam.rbi.org.in")),
        (("deposit insurance", "dicgc"), ("dicgc.org.in",)),
        (("atal pension", "apy", "national pension", "nps"), ("pfrda.org.in", "npstrust.org.in")),
        (("ujjwala", "pmuy"), ("pmuy.gov.in",)),
        (("e-shram", "eshram"), ("eshram.gov.in",)),
    )
    for terms, hosts in rules:
        if any(term in lowered for term in terms):
            return hosts
    return _DOMAIN_SITE_HINTS.get(domain, ())


def build_allowlist_query(user_query: str, domain: Domain) -> str:
    """Build a search query with targeted official domain constraints."""
    clean_query = extract_search_keywords(user_query)
    clean_query = re.sub(r"[?!.,'\"]+", " ", clean_query)
    clean_query = " ".join(clean_query.split())
    lowered = user_query.lower()

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
        domain_hints = preferred_domains_for_query(user_query, domain)
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
        if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
            return False
        if parsed.port not in (None, 443):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        return any(host == d or host.endswith(f".{d}") for d in CIVIC_ALLOWLIST_DOMAINS)
    except Exception:
        return False


__all__ = [
    "CIVIC_ALLOWLIST_DOMAINS",
    "build_allowlist_query",
    "preferred_domains_for_query",
    "is_allowlisted_url",
]
