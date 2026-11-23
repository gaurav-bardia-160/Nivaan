"""Civic domain allowlist for web search — strictly limits queries to official Indian government domains.

No open-internet scraping is permitted. All URLs fetched must belong to the allowlist.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from typing import TYPE_CHECKING

from backend.modules.domain_router import Domain

# Sovereign Indian government TLD suffixes
CIVIC_TLD_SUFFIXES: tuple[str, ...] = (
    "gov.in",
    "nic.in",
)

# Non-TLD official/statutory/PSU bodies — curated manually, expand deliberately only with named official citations.
NON_TLD_OFFICIAL_DOMAINS: tuple[str, ...] = (
    # Finance / banking regulators & statutory bodies (previously approved)
    "rbi.org.in",
    "npci.org.in",
    "pfrda.org.in",
    "dicgc.org.in",
    "nsdl.co.in",
    "ihmcl.co.in",
    "jansamarth.in",
    "nvsp.in",
    # Railways / transport PSUs & autonomous bodies (Ministry of Railways verified)
    "irctc.co.in",
    "rvnl.org",
    "ircon.org",
    "cris.org.in",
)

# Single source of truth for allowlisted domains
CIVIC_ALLOWLIST_DOMAINS: tuple[str, ...] = CIVIC_TLD_SUFFIXES + NON_TLD_OFFICIAL_DOMAINS

# Universal query suffix OR'd across all allowlisted domains (constant, always-identical across all queries)
_UNIVERSAL_SITE_SUFFIX = "(" + " OR ".join(f"site:{d}" for d in CIVIC_ALLOWLIST_DOMAINS) + ")"


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


# Targeted domain site map for strict single-site constraint
DOMAIN_SITE_MAP = {
    Domain.TAX: "site:incometax.gov.in",
    Domain.TAXATION: "site:incometax.gov.in",
    Domain.BANKING: "site:rbi.org.in",
    Domain.TRANSPORT: "site:parivahan.gov.in",
    Domain.PASSPORT: "site:passportindia.gov.in",
    Domain.PENSION: "site:epfindia.gov.in",
    Domain.CORPORATE: "site:mca.gov.in",
    Domain.GENERAL_CIVIC: "site:gov.in",
}


def get_site_constraint(domain: Domain | str | None) -> str:
    """Returns a single, strict site constraint for DDGS."""
    if isinstance(domain, str):
        try:
            domain = Domain(domain)
        except ValueError:
            pass
    return DOMAIN_SITE_MAP.get(domain, "site:gov.in")


def build_allowlist_query(user_query: str, domain: Domain | None = None) -> str:
    """Build a search query with the targeted official civic domain constraint."""
    clean_query = extract_search_keywords(user_query)
    clean_query = re.sub(r"[?!.,'\"]+", " ", clean_query)
    clean_query = " ".join(clean_query.split())
    site_constraint = get_site_constraint(domain) if domain else _UNIVERSAL_SITE_SUFFIX
    return f"{clean_query} {site_constraint}".strip()


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
    "CIVIC_TLD_SUFFIXES",
    "NON_TLD_OFFICIAL_DOMAINS",
    "CIVIC_ALLOWLIST_DOMAINS",
    "DOMAIN_SITE_MAP",
    "get_site_constraint",
    "build_allowlist_query",
    "is_allowlisted_url",
]
