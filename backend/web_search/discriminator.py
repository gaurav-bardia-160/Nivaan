from __future__ import annotations
import logging
import re
import httpx
import json

from backend.modules.llm import GeminiLLMClient
from backend.web_search.fetcher import is_navigation_or_boilerplate_text

logger = logging.getLogger(__name__)

DISCRIMINATOR_FAILURE_PHRASE = "Live search failed to extract the procedural text from the official portal."


def discriminate_content(query: str, scraped_text: str) -> str:
    """Validate scraped portal text and extract only query-relevant procedural content."""
    if is_navigation_or_boilerplate_text(scraped_text):
        logger.warning("Discriminator: Heuristic caught boilerplate/table noise.")
        return DISCRIMINATOR_FAILURE_PHRASE

    truncated_text = scraped_text[:4500]
    gemini = GeminiLLMClient()

    if gemini.available():
        system = (
            "You are a strict Data Discriminator for an Indian Civic AI. "
            "Evaluate whether the scraped government webpage contains concrete, actionable procedural steps, "
            "statutory rules, or form instructions that directly answer the User Query. "
            "If the text is mostly navigation menus, Terms & Conditions, privacy policies, login screens, "
            "or unrelated portal text, return JSON: {\"approved\": false, \"extracted_text\": \"\"}. "
            "If relevant procedural content is present, return JSON: "
            "{\"approved\": true, \"extracted_text\": \"<clean verbatim procedural steps and rules only>\"}."
        )
        prompt = f"User Query: {query}\n\nScraped Official Page Text:\n{truncated_text}"
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-preview-02-05:generateContent?key={gemini.api_key}"
            payload = {
                "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 900, "responseMimeType": "application/json"},
            }
            resp = httpx.post(url, json=payload, timeout=15.0)
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed = json.loads(raw)
            if not parsed.get("approved"):
                logger.warning("Discriminator (Gemini): Rejected irrelevant/boilerplate page.")
                return DISCRIMINATOR_FAILURE_PHRASE
            extracted = str(parsed.get("extracted_text", "")).strip()
            if len(extracted) >= 60:
                return extracted
            return DISCRIMINATOR_FAILURE_PHRASE
        except Exception as exc:
            logger.warning("Discriminator Gemini call failed (%s), falling back to lexical check.", exc)

    # Deterministic fallback when Gemini API key is missing
    query_terms = set(re.findall(r"\b[a-z0-9]{3,}\b", query.lower())) - {"how", "what", "where", "when", "portal"}
    text_terms = set(re.findall(r"\b[a-z0-9]{3,}\b", truncated_text.lower()))
    if len(query_terms & text_terms) < 2:
        return DISCRIMINATOR_FAILURE_PHRASE

    return truncated_text


__all__ = [
    "is_navigation_or_boilerplate_text",
    "DISCRIMINATOR_FAILURE_PHRASE",
    "discriminate_content",
]
