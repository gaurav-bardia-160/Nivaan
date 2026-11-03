"""ETL Phase 2 — Refine: LLM discriminator to filter and clean raw HTML.

Reads raw HTML files from ETL_RAW_DIR, uses the local Qwen LLM to:
  1. Classify: is this statutory/official civic content, or marketing/noise?
  2. If approved: strip boilerplate, extract clean text, generate JSON metadata
  3. Save refined output to ETL_REFINED_DIR/{hash}.json
  4. Reject non-statutory content (log reason, delete raw file)

Usage (offline only):
    py -m backend.etl.refine

Never import or call this from the live request pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Comment

# Ensure package is importable when run as __main__
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import ETL_RAW_DIR, ETL_REFINED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("etl.refine")

_OLLAMA_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
_OLLAMA_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:3b").strip() or "qwen2.5:3b"
_LLM_TIMEOUT = 120.0

_VALID_DOMAINS = frozenset({
    "transport", "tax", "identity", "banking",
    "agriculture", "legal_consumer", "general_civic", "epf",
})

_DISCRIMINATOR_SYSTEM = """\
You are a document classifier for Nivaan, an Indian civic AI assistant.
Your task: Read the following Indian government web page text and classify it.

Answer ONLY with valid JSON (no markdown fences, no extra text):
{
  "is_statutory": true or false,
  "reason": "one sentence explaining your decision",
  "domain": one of ["transport", "tax", "identity", "banking", "agriculture", "legal_consumer", "epf", "general_civic"],
  "clean_text": "the most relevant civic procedure text, stripped of headers/footers/menus, max 3000 chars",
  "metadata": {
    "source_url": "the URL of this page",
    "error_code": null or "e.g. 139(9)",
    "scheme_name": null or "e.g. PM Kisan Samman Nidhi"
  }
}

CLASSIFICATION RULES:
- is_statutory: true — Official procedure, form, eligibility, fee schedule, grievance mechanism from a .gov.in or .nic.in page.
- is_statutory: false — Marketing, news, opinion, commercial service, generic home page, 404 error, or irrelevant content.
- domain: Pick the single most relevant civic domain.
- clean_text: Extract ONLY the actionable civic information. Remove navigation, cookies, repeated headers, footers.
"""


def _extract_text_from_html(html_bytes: bytes, encoding: str = "utf-8") -> str:
    """Strip HTML to plaintext for the LLM discriminator."""
    try:
        html = html_bytes.decode(encoding, errors="replace")
    except Exception:
        html = html_bytes.decode("utf-8", errors="replace")

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return ""

    # Remove comments and noisy tags
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    for tag_name in ("script", "style", "nav", "header", "footer", "aside", "form", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 20]
    return "\n".join(lines)[:5000]


def _call_discriminator(text: str, source_url: str) -> dict | None:
    """Call Ollama LLM discriminator and return parsed JSON or None."""
    prompt = (
        f"Source URL: {source_url}\n\n"
        f"Web Page Text:\n{text[:4500]}\n\n"
        "Classify this page and return JSON only."
    )
    payload = {
        "model": _OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": _DISCRIMINATOR_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.0,
            "num_predict": 800,
            "num_ctx": 4096,
            "num_thread": min(os.cpu_count() or 4, 4),
        },
    }
    try:
        resp = httpx.post(
            f"{_OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=_LLM_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Discriminator returned invalid JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Discriminator LLM call failed: %s", exc)
        return None


def refine_all() -> tuple[int, int]:
    """Refine all raw HTML files. Returns (approved_count, rejected_count)."""
    ETL_REFINED_DIR.mkdir(parents=True, exist_ok=True)

    raw_html_files = sorted(ETL_RAW_DIR.glob("*.html"))
    if not raw_html_files:
        logger.info("No raw HTML files to refine.")
        return 0, 0

    approved = 0
    rejected = 0

    for html_path in raw_html_files:
        url_hash = html_path.stem
        meta_path = ETL_RAW_DIR / f"{url_hash}.json"
        refined_path = ETL_REFINED_DIR / f"{url_hash}.json"

        if refined_path.exists():
            logger.debug("Refined file already exists: %s — skipping", url_hash)
            continue

        # Load metadata sidecar
        source_url = ""
        domain_hint = "general_civic"
        fetched_at = ""
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                source_url = meta.get("url", "")
                domain_hint = meta.get("domain", "general_civic")
                fetched_at = meta.get("fetched_at", "")
            except Exception:
                pass

        logger.info("Refining: %s (%.60s)", url_hash, source_url)

        # Extract text from HTML
        html_bytes = html_path.read_bytes()
        page_text = _extract_text_from_html(html_bytes)

        if len(page_text) < 200:
            logger.info("Page text too short (%d chars) — rejecting: %s", len(page_text), url_hash)
            html_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            rejected += 1
            continue

        # Call LLM discriminator
        result = _call_discriminator(page_text, source_url)

        if result is None:
            logger.warning("Discriminator failed for %s — keeping raw file for retry", url_hash)
            continue

        is_statutory = bool(result.get("is_statutory", False))
        reason = str(result.get("reason", ""))
        detected_domain = str(result.get("domain", domain_hint))
        clean_text = str(result.get("clean_text", page_text[:3000]))
        metadata = result.get("metadata", {})

        if not is_statutory:
            logger.info("REJECTED (%s): %s — reason: %s", url_hash, source_url[:60], reason)
            html_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            rejected += 1
            continue

        # Normalize domain
        if detected_domain not in _VALID_DOMAINS:
            detected_domain = domain_hint if domain_hint in _VALID_DOMAINS else "general_civic"

        # Save refined output
        refined = {
            "url_hash": url_hash,
            "source_url": source_url or metadata.get("source_url", ""),
            "domain": detected_domain,
            "clean_text": clean_text,
            "metadata": {
                "error_code": metadata.get("error_code"),
                "scheme_name": metadata.get("scheme_name"),
                "fetched_at": fetched_at,
                "discriminator_reason": reason,
            },
        }
        refined_path.write_text(
            json.dumps(refined, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("APPROVED (%s): domain=%s url=%.60s", url_hash, detected_domain, source_url)
        approved += 1

    logger.info("Refine complete. Approved: %d, Rejected: %d", approved, rejected)
    return approved, rejected


if __name__ == "__main__":
    approved, rejected = refine_all()
    logger.info("Total: approved=%d rejected=%d", approved, rejected)
    sys.exit(0)
