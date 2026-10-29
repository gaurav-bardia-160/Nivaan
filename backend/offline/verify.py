"""Human verification checklist for knowledge base entries.

Provides automated pre-checks and a structured checklist for manual review
of entries before they are marked as 'verified' in the knowledge base.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("verify")

# Staging / non-production URL indicators
_STAGING_INDICATORS = {"beta", "staging", "test", "dev", "sandbox", "preview", "canary"}


def check_entry(entry: dict[str, Any], source_text: str = "") -> dict[str, Any]:
    """Run automated verification checks on a knowledge base entry.

    Returns a dict with:
      - 'passed': bool — True if all automated checks passed
      - 'checks': list of dicts with 'name', 'passed', 'detail'
      - 'manual_checklist': list of strings the reviewer must verify by hand
    """
    checks: list[dict[str, Any]] = []
    answer_text = _build_answer_text(entry)

    # --- Automated Checks ---

    # 1. Check abbreviations against source text
    if source_text:
        abbr_check = _check_abbreviations(answer_text, source_text)
        checks.append(abbr_check)
    
    # 2. Check source URL is canonical (not staging/beta)
    source_url = ""
    source_obj = entry.get("source", {})
    if isinstance(source_obj, dict):
        source_url = source_obj.get("url", "")
    elif isinstance(source_obj, str):
        source_url = source_obj
    
    url_check = _check_source_url(source_url)
    checks.append(url_check)

    # 3. Check that entry has required fields
    field_check = _check_required_fields(entry)
    checks.append(field_check)

    # 4. Check steps are not overstated (look for "optional" or "can" in detail but "mandatory" in title)
    step_check = _check_step_consistency(entry)
    checks.append(step_check)

    # --- Manual Checklist ---
    manual_checklist = [
        "Does every abbreviation/term in the answer appear in the source text?",
        "Are all 'free', 'exempt', 'optional', or 'not required' facts from the source carried into the answer?",
        "Is every numbered step actually sequenced as mandatory in the source, not implied or optional?",
        "Is the source URL the canonical public page (not beta/staging/test)?",
        "Does the entry cover special cases (children, exemptions, different categories) separately?",
        "Are fees, timelines, and penalties accurate and up to date?",
    ]

    all_passed = all(c["passed"] for c in checks)
    return {
        "passed": all_passed,
        "checks": checks,
        "manual_checklist": manual_checklist,
    }


def _build_answer_text(entry: dict[str, Any]) -> str:
    """Concatenate all user-facing text in the entry."""
    parts = [
        entry.get("title", ""),
        entry.get("summary", ""),
    ]
    for doc in entry.get("documents_needed", []):
        parts.append(doc if isinstance(doc, str) else str(doc))
    for step in entry.get("steps", []):
        if isinstance(step, dict):
            parts.append(step.get("title", ""))
            parts.append(step.get("detail", ""))
    for warning in entry.get("warnings", []):
        if isinstance(warning, dict):
            parts.append(warning.get("title", ""))
            parts.append(warning.get("message", ""))
    return " ".join(parts)


def _check_abbreviations(answer_text: str, source_text: str) -> dict[str, Any]:
    """Check that abbreviations in the answer exist in the source text."""
    abbreviations = set(re.findall(r'\b[A-Z][a-zA-Z]{1,4}\b', answer_text))
    common = {
        "The", "You", "Your", "This", "That", "Step", "Note", "From", "With",
        "Also", "Each", "Once", "None", "True", "False", "India", "India",
        "Proof", "Visit", "Check", "Enter", "Click",
    }
    suspicious = []
    for abbr in abbreviations - common:
        if abbr not in source_text:
            suspicious.append(abbr)
    
    return {
        "name": "abbreviations_in_source",
        "passed": len(suspicious) == 0,
        "detail": f"Suspicious abbreviations not found in source: {suspicious}" if suspicious else "All abbreviations found in source text.",
    }


def _check_source_url(url: str) -> dict[str, Any]:
    """Check that the source URL is not a staging/beta endpoint."""
    if not url:
        return {
            "name": "source_url_canonical",
            "passed": False,
            "detail": "No source URL provided.",
        }
    
    url_lower = url.lower()
    for indicator in _STAGING_INDICATORS:
        if indicator in url_lower:
            return {
                "name": "source_url_canonical",
                "passed": False,
                "detail": f"URL contains '{indicator}' — may be staging/non-production: {url}",
            }
    
    return {
        "name": "source_url_canonical",
        "passed": True,
        "detail": f"Source URL looks canonical: {url}",
    }


def _check_required_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Check that essential fields are present and non-empty."""
    required = ["id", "title", "summary", "steps", "status"]
    missing = [f for f in required if not entry.get(f)]
    
    return {
        "name": "required_fields",
        "passed": len(missing) == 0,
        "detail": f"Missing required fields: {missing}" if missing else "All required fields present.",
    }


def _check_step_consistency(entry: dict[str, Any]) -> dict[str, Any]:
    """Check that optional actions are not presented as mandatory steps."""
    issues = []
    optional_words = {"can", "may", "optional", "optionally", "if you want", "if needed"}
    
    for i, step in enumerate(entry.get("steps", []), 1):
        if not isinstance(step, dict):
            continue
        detail = (step.get("detail") or "").lower()
        title = (step.get("title") or "").lower()
        
        # If the detail says "optional" or "can" but it's presented as a numbered step
        if any(w in detail for w in optional_words) and "optional" not in title:
            issues.append(f"Step {i} ('{step.get('title', '')}') has optional language in detail but is presented as a mandatory step.")
    
    return {
        "name": "step_consistency",
        "passed": len(issues) == 0,
        "detail": "; ".join(issues) if issues else "All steps appear consistent with their detail.",
    }


def verify_knowledge_base(kb_path: str | Path, source_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Run verification checks on all entries in a knowledge base file.
    
    Args:
        kb_path: Path to knowledge_base.json
        source_dir: Optional directory containing raw source text files
    
    Returns:
        List of verification results, one per entry.
    """
    kb_path = Path(kb_path)
    entries = json.loads(kb_path.read_text(encoding="utf-8-sig"))
    
    results = []
    for entry in entries:
        source_text = ""
        if source_dir:
            # Try to find matching raw source file
            source_dir_path = Path(source_dir)
            entry_id = entry.get("id", "")
            for txt_file in source_dir_path.glob(f"*{entry_id}*"):
                source_text = txt_file.read_text(encoding="utf-8", errors="ignore")
                break
        
        result = check_entry(entry, source_text)
        result["entry_id"] = entry.get("id", "unknown")
        result["entry_title"] = entry.get("title", "unknown")
        results.append(result)
    
    return results


if __name__ == "__main__":
    import sys
    
    kb_path = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    
    results = verify_knowledge_base(kb_path, raw_dir if raw_dir.exists() else None)
    
    print(f"\n{'='*60}")
    print(f"VERIFICATION REPORT — {len(results)} entries checked")
    print(f"{'='*60}\n")
    
    for r in results:
        status = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"{status}  {r['entry_id']} — {r['entry_title']}")
        for check in r["checks"]:
            mark = "  ✓" if check["passed"] else "  ✗"
            print(f"    {mark} {check['name']}: {check['detail']}")
    
    print(f"\n--- Manual Checklist (apply to each entry) ---")
    if results:
        for item in results[0]["manual_checklist"]:
            print(f"  [ ] {item}")
    
    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\n⚠  {len(failed)} entries need attention.")
        sys.exit(1)
    else:
        print(f"\n✓  All {len(results)} entries passed automated checks.")
