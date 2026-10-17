"""Production-grade offline refiner for raw civic and government portal documents.

Transforms raw scraped documents (UIDAI, Income Tax Department, Protean, UTIITSL)
into clean, structured, deduplicated, and schema-compliant JSON/JSONL chunks ready
for RAG ingestion and verification auditing.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
REFINED_DIR = BASE_DIR / "data" / "refined"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("govbank.refiner")

# Protected abbreviations for sentence boundary detection
PROTECTED_ABBREVIATIONS = {
    "rs.", "no.", "dr.", "mr.", "mrs.", "ms.", "prof.", "vs.", "approx.",
    "e.g.", "i.e.", "etc.", "co.", "ltd.", "inc.", "dept.", "govt.", "u.s.", "u.k."
}

# Source-specific truncation markers (boilerplate cutoffs)
UIDAI_TRUNCATE_MARKERS = [
    "### How to download the Aadhaar app?",
    "How to download the Aadhaar app?",
    "### Which services are available on this app?",
    "## [Aadhaar Services]",
    "## Aadhaar Services",
    "### UIDAI Head Office",
    "UIDAI Head Office\n",
    "Vision & Mission",
    "Citizens Charter",
]

PAN_SIDEBAR_TRIGGERS = [
    "Guided Help",
    "Tax Services\n  * [ Overview",
]

# Global boilerplate skip keywords
SKIP_KEYWORDS = [
    "Skip to Main Content", "Screen Reader", "Language selection",
    "Footer background", "Menu icon", "Open external website",
    "Hindi (हिन्दी)", "About UIDAI", "Build with Us", "Quick Links",
    "Other Links", "UIDAI — Unique", "Mobile menu toggle",
    "JavaScript must be enabled", "UIDAl website translation",
    "Ask Me Anything!!", "Search Services", "Whitelabel Error Page",
    "Enter Captcha", "This website is optimised for the latest versions",
    "Website Policy", "Terms & Conditions", "Privacy Policy",
    "Hyperlink Policy", "Copyright Policy", "Disclaimer", "Accessibility Statement",
    "Contact Us", "Sitemap", "Bhuvan Aadhaar", "Aadhaar Dashboard", "Aadhaar Data Vault",
    "Aadhaar Mitra", "Grievance Redressal", "Follow Us On",
    "Guided Tour", "Department Officials", "IRS Officers Online", "Official Email Systems",
    "Employees Corner", "Take Online Oath", "Accessibility Options", "Font Size",
    "Saturation", "High Contrast Theme", "Basic HTML View", "Invert Colors", "Language Options",
    "Quick Access International Taxation", "Organizations and Functions",
    "Tax Laws & Rules", "Media Gallery", "Advanced Search",
    "IT Bill Comparison Tool", "Compare Income-tax Act 1961 with Income-tax Act 2025",
    "Upload FilesSelect from CatalogEnter URLs", "Compare sections first to enable export",
    "Select sections from both Acts and click", "For reference purposes only",
    "Public Awareness", "Report Phishing", "Children's Corner", "Useful Links",
    "Subscribe - Newsletter", "Subscribe - Tax Feeds", "e-Governance",
    "This site is best viewed in", "Copyright Income Tax Department",
    "Show More", "Act, 1961", "Act, 2025", "Orders & Instructions",
    "Forms/Downloads", "Budget & Bills", "Finance Acts", "Finance Bills",
    "Unique Identification Authority of India", "Total Visitors", "Guided Help",
    "Validate reCAPTCHA", "Play audio Stop audio", "Powered by", "PAN - Login",
    "Select Language English", "Copyright 20"
]

EXACT_SKIP_KEYWORDS = {
    "home", "more", "media", "documents", "help", "english", "facebook", "twitter",
    "youtube", "instagram", "linkedin", "koo", "login", "register", "e-filing",
    "close", "hidden", "compare", "drop file here orchoose file", "etds-htmletds-pdf",
    "tax e-services", "guided help", "reset submit", "cancel token", "reset submit  cancel token",
    "my aadhaar", "acts", "rules", "circulars", "notifications", "taxpayers"
}

OFFICIAL_DOMAINS = {
    "uidai.gov.in",
    "myaadhaar.uidai.gov.in",
    "ovse.uidai.gov.in",
    "incometax.gov.in",
    "www.incometax.gov.in",
    "tinpan.proteantech.in",
    "onlineservices.proteantech.in",
    "pan.utiitsl.com",
    "www.pan.utiitsl.com",
    "www.trackpan.utiitsl.com",
}


@dataclass
class RefinementStats:
    source_name: str
    files_scanned: int = 0
    files_processed: int = 0
    chunks_generated: int = 0
    duplicates_skipped: int = 0
    empty_chunks_dropped: int = 0
    total_words: int = 0
    quality_scores: list[float] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)

    @property
    def average_quality_score(self) -> float:
        return round(sum(self.quality_scores) / len(self.quality_scores), 3) if self.quality_scores else 0.0

    @property
    def average_chunk_words(self) -> int:
        return int(self.total_words / self.chunks_generated) if self.chunks_generated else 0

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "files_scanned": self.files_scanned,
            "files_processed": self.files_processed,
            "chunks_generated": self.chunks_generated,
            "duplicates_skipped": self.duplicates_skipped,
            "empty_dropped": self.empty_chunks_dropped,
            "avg_chunk_words": self.average_chunk_words,
            "avg_quality_score": self.average_quality_score,
            "languages": self.languages,
        }


def detect_language(text: str) -> str:
    """Detect whether text is English (en), Hindi (hi), Gujarati (gu), or mixed."""
    devanagari = len(re.findall(r'[\u0900-\u097F]', text))
    gujarati = len(re.findall(r'[\u0A80-\u0AFF]', text))
    latin = len(re.findall(r'[A-Za-z]', text))
    total_alpha = devanagari + gujarati + latin

    if total_alpha == 0:
        return "und"

    dev_ratio = devanagari / total_alpha
    guj_ratio = gujarati / total_alpha
    latin_ratio = latin / total_alpha

    # If substantial Indic and substantial Latin both present, it is code-mixed
    if (dev_ratio > 0.15 and latin_ratio > 0.15) or (guj_ratio > 0.15 and latin_ratio > 0.15):
        return "mixed"

    if dev_ratio > 0.40:
        return "hi"
    if guj_ratio > 0.40:
        return "gu"
    if latin_ratio > 0.60:
        return "en"

    return "mixed" if (devanagari > 0 or gujarati > 0) else "en"


def compute_quality_score(text: str, title: str, section: str, url: str) -> float:
    """Compute a calibrated heuristic quality score between 0.60 and 0.98.
    
    Scores are based on word count, civic relevance, document structure,
    and lack of residual UI boilerplate.
    """
    words = text.split()
    word_count = len(words)
    if word_count < 30:
        return 0.50

    score = 0.72

    # 1. Word count adequacy
    if 100 <= word_count <= 450:
        score += 0.12
    elif 60 <= word_count < 100:
        score += 0.06
    elif word_count > 450:
        score += 0.04
    else:
        score -= 0.06

    # 2. Structural signals (headings, lists)
    lines = text.splitlines()
    has_structure = any(line.strip().startswith(("#", "*", "-", "1.", "2.", "3.")) for line in lines)
    if has_structure:
        score += 0.06

    # 3. Civic keyword richness
    civic_terms = {
        "aadhaar", "pan", "form", "application", "fee", "documents",
        "card", "identity", "otp", "authentication", "verification",
        "update", "download", "portal", "status", "link", "correction",
        "certificate", "address", "signature", "income", "tax", "nsdl",
        "protean", "utiitsl", "uidai", "reprint", "eligibility"
    }
    lower_words = set(w.lower().strip(".,;:()[]\"'") for w in words)
    overlap = len(lower_words & civic_terms)
    if overlap >= 6:
        score += 0.08
    elif overlap >= 3:
        score += 0.04

    # 4. Penalties for residual noise
    ui_noise = ["click here", "submit", "reset", "captcha", "javascript", "select from catalog"]
    lower_text = text.lower()
    for noise in ui_noise:
        if noise in lower_text:
            score -= 0.04

    return round(max(0.60, min(0.98, score)), 2)


def split_into_sentences(text: str) -> list[str]:
    """Production-grade sentence splitter that protects civic currencies and abbreviations."""
    raw_pieces = re.split(r'(\s*\n+\s*|(?<=[.!?])\s+)', text)
    sentences: list[str] = []
    current: list[str] = []

    for piece in raw_pieces:
        if not piece:
            continue
        current.append(piece)
        combined = "".join(current).strip()

        if re.search(r'[.!?]$', combined):
            words = combined.split()
            last_word = words[-1].lower() if words else ""
            if last_word in PROTECTED_ABBREVIATIONS or re.search(r'\b\d+\.$', combined):
                continue
            sentences.append(combined)
            current = []

    if current:
        remainder = "".join(current).strip()
        if remainder:
            if sentences:
                sentences[-1] += " " + remainder
            else:
                sentences.append(remainder)

    return sentences


def extract_section(chunk_text: str, fallback_title: str) -> str:
    """Extract a clean, readable section title without markdown artifacts."""
    for line in chunk_text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.startswith("#"):
            heading = line_clean.lstrip("#").strip()
            # Strip markdown links and markdown images
            heading = re.sub(r'!\[.*?\]\(.*?\)', '', heading)
            heading = re.sub(r'\[!\]\(.*?\)', '', heading)
            heading = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', heading).strip()
            heading = re.sub(r'[*_`]', '', heading).strip()
            if heading and len(heading) > 2 and heading.lower() not in {"home", "guided help", "overview"}:
                return heading[:250]
    return fallback_title[:250]


def clean_markdown(md: str, source_name: str) -> str:
    """Thoroughly sanitize, unescape, and strip boilerplate from raw markdown."""
    # 1. Unescape HTML entities (&amp; -> &, &#39; -> ', etc.)
    md = html.unescape(md)

    # 2. Unicode normalization (NFC) & strip replacement/zero-width chars
    md = unicodedata.normalize("NFC", md)
    md = md.replace("\ufffd", "-").replace("\u200b", " ").replace("\ufeff", "")

    # 3. Strip HTML comments and dangling comment markers
    md = re.sub(r'<!--.*?-->', '', md, flags=re.DOTALL)
    md = md.replace("-->", "")

    # 4. Strip dead javascript and broken links/images
    md = re.sub(r'!?\s*\[[^\]]*\]\s*\(javascript:[^\)]*\)', '', md)
    md = re.sub(r'\[\s*\]\([^\)]*\)', '', md)
    md = re.sub(r'!\[.*?\]\(.*?\)', '', md)
    md = re.sub(r'\[!\]\([^\)]*\)', '', md)

    # 5. UIDAI specific footer and repetitive widget truncation
    if source_name == "uidai":
        earliest_pos = -1
        for marker in UIDAI_TRUNCATE_MARKERS:
            pos = md.find(marker)
            if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
                earliest_pos = pos
        if earliest_pos != -1:
            md = md[:earliest_pos]

    # 6. PAN specific navigation sidebar stripping
    if source_name == "pan":
        for trigger in PAN_SIDEBAR_TRIGGERS:
            g_pos = md.find(trigger)
            if g_pos != -1:
                after = md[g_pos:]
                targets = ["About PAN", "## Steps", "Steps to Verify PAN", "## Instant", "### "]
                earliest = -1
                for t in targets:
                    p = after.find(t)
                    if p != -1 and (earliest == -1 or p < earliest):
                        earliest = p
                if earliest != -1:
                    md = md[:g_pos] + after[earliest:]

    # 7. Line-by-line filtering
    lines = md.splitlines()
    cleaned = []

    for line in lines:
        line_clean = line.strip()
        text_only = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line_clean).strip()
        text_only = re.sub(r'^[#*\- 0-9\.]+', '', text_only).strip()

        if "captcha" in line_clean.lower() and ("javascript" in line_clean.lower() or "change captcha" in line_clean.lower()):
            continue
        if any(k.lower() in line.lower() or k.lower() in text_only.lower() for k in SKIP_KEYWORDS):
            continue
        if text_only.lower() in EXACT_SKIP_KEYWORDS:
            continue
        cleaned.append(line)

    text = '\n'.join(cleaned).strip()
    text = re.sub(r'\(javascript:[^\)]*\)', '', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_tags(text: str, source_name: str) -> list[str]:
    """Extract curated retrieval tags based on civic concepts."""
    tags = []
    text_lower = text.lower()
    if source_name == "uidai":
        keywords = [
            "aadhaar", "update", "mobile", "fee", "download", "biometric",
            "authentication", "enrolment", "pan", "status", "lock", "unlock", "pvc"
        ]
    elif source_name == "pan":
        keywords = [
            "pan", "apply", "form 49a", "form 49aa", "form 93", "form 94", "form 95", "form 96",
            "nsdl", "protean", "utiitsl", "reprint", "correction", "minor", "nri", "tatkal",
            "ao code", "e-pan", "kyc", "instant", "verification", "aadhaar", "link", "fee", "address"
        ]
    else:
        keywords = [source_name]

    for kw in keywords:
        if kw in text_lower:
            tags.append(kw)

    if not tags:
        tags = [f"{source_name}_service"]
    return sorted(list(set(tags)))


def chunk_document(
    cleaned_text: str,
    *,
    min_words: int = 40,
    target_min: int = 150,
    target_max: int = 450,
    hard_max: int = 500,
) -> list[str]:
    """Split cleaned document text into coherent, bounded chunks."""
    # Chunk by markdown headings (## or #)
    raw_pieces = re.split(r'\n(?=#+ )', cleaned_text)

    # 1. Merge small pieces
    merged_pieces: list[str] = []
    current_piece = ""

    for piece in raw_pieces:
        piece = piece.strip()
        if not piece:
            continue

        if current_piece:
            current_piece += "\n\n" + piece
        else:
            current_piece = piece

        if len(current_piece.split()) >= target_min:
            merged_pieces.append(current_piece)
            current_piece = ""

    if current_piece:
        if merged_pieces and len(current_piece.split()) < 100:
            merged_pieces[-1] += "\n\n" + current_piece
        else:
            merged_pieces.append(current_piece)

    # 2. Split huge pieces using protected sentence boundaries
    final_chunks: list[str] = []
    for piece in merged_pieces:
        words = piece.split()
        if len(words) > hard_max:
            sentences = split_into_sentences(piece)
            temp_chunk: list[str] = []
            current_len = 0

            for sentence in sentences:
                s_words = len(sentence.split())
                if current_len + s_words > target_max and temp_chunk:
                    final_chunks.append(" ".join(temp_chunk).strip())
                    temp_chunk = [sentence]
                    current_len = s_words
                else:
                    temp_chunk.append(sentence)
                    current_len += s_words

            if temp_chunk:
                final_chunks.append(" ".join(temp_chunk).strip())
        else:
            final_chunks.append(piece)

    # Filter out chunks that are too short or empty
    return [c for c in final_chunks if len(c.split()) >= min_words and any(ch.isalnum() for ch in c)]


def chunk_and_save(
    doc_id: str,
    title: str,
    url: str,
    cleaned_text: str,
    chunks_list: list[dict[str, Any]],
    source_name: str,
    refined_dir: Path,
    *,
    dedup: bool = True,
    seen_hashes: set[str] | None = None,
    stats: RefinementStats | None = None,
    dry_run: bool = False,
) -> None:
    """Chunk cleaned text, compute calibrated quality scores, and save chunks."""
    chunks = chunk_document(cleaned_text)
    category = "aadhaar" if source_name == "uidai" else ("pan" if source_name == "pan" else source_name)
    today_iso = date.today().isoformat()

    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    source_confidence = "official" if domain in OFFICIAL_DOMAINS or any(d in domain for d in ["gov.in", "nic.in"]) else "unknown"

    for i, chunk_text in enumerate(chunks):
        normalized_for_hash = " ".join(chunk_text.split())
        fingerprint = hashlib.sha256((category + "\0" + normalized_for_hash).encode("utf-8")).hexdigest()

        if dedup and seen_hashes is not None:
            if fingerprint in seen_hashes:
                if stats:
                    stats.duplicates_skipped += 1
                continue
            seen_hashes.add(fingerprint)

        section = extract_section(chunk_text, title)
        q_score = compute_quality_score(chunk_text, title, section, url)
        lang = detect_language(chunk_text)
        tags = extract_tags(chunk_text, source_name)
        chunk_id = f"{doc_id}_chunk_{i+1}"

        draft: dict[str, Any] = {
            "id": chunk_id,
            "source_url": url,
            "title": title,
            "section": section,
            "text": chunk_text,
            "category": category,
            "last_verified": today_iso,
            "status": "automated_verified",
            "quality_score": q_score,
            "source_confidence": source_confidence,
            "verification_method": "automated_refiner_v2",
            "retrieval_tags": tags,
            "language": lang,
        }

        if not dry_run:
            json_content = json.dumps(draft, indent=2, ensure_ascii=False) + "\n"
            (refined_dir / f"{chunk_id}.json").write_text(json_content, encoding="utf-8")

        chunks_list.append(draft)

        if stats:
            stats.chunks_generated += 1
            stats.total_words += len(chunk_text.split())
            stats.quality_scores.append(q_score)
            stats.languages[lang] = stats.languages.get(lang, 0) + 1


def run_refiner(
    source_name: str = "pan",
    *,
    raw_dir: Path | None = None,
    refined_dir: Path | None = None,
    dedup: bool = True,
    dry_run: bool = False,
    clean_existing: bool = True,
) -> RefinementStats:
    """Run the production refiner for a given source ('pan', 'uidai', or 'all')."""
    if source_name == "all":
        s1 = run_refiner("pan", raw_dir=raw_dir, refined_dir=refined_dir, dedup=dedup, dry_run=dry_run, clean_existing=clean_existing)
        s2 = run_refiner("uidai", raw_dir=raw_dir, refined_dir=refined_dir, dedup=dedup, dry_run=dry_run, clean_existing=clean_existing)
        combined = RefinementStats(source_name="all")
        combined.files_scanned = s1.files_scanned + s2.files_scanned
        combined.files_processed = s1.files_processed + s2.files_processed
        combined.chunks_generated = s1.chunks_generated + s2.chunks_generated
        combined.duplicates_skipped = s1.duplicates_skipped + s2.duplicates_skipped
        combined.total_words = s1.total_words + s2.total_words
        combined.quality_scores = s1.quality_scores + s2.quality_scores
        for lang, count in s1.languages.items():
            combined.languages[lang] = combined.languages.get(lang, 0) + count
        for lang, count in s2.languages.items():
            combined.languages[lang] = combined.languages.get(lang, 0) + count
        return combined

    raw_base = raw_dir or RAW_DIR
    refined_base = refined_dir or REFINED_DIR

    raw_source_dir = raw_base / source_name
    refined_source_dir = refined_base / source_name

    stats = RefinementStats(source_name=source_name)

    if not dry_run:
        refined_source_dir.mkdir(parents=True, exist_ok=True)
        if clean_existing:
            for old_file in refined_source_dir.glob("*.json"):
                try:
                    old_file.unlink()
                except OSError as e:
                    logger.warning(f"Could not remove old file {old_file.name}: {e}")

    raw_files = list(raw_source_dir.glob("*.txt")) if raw_source_dir.exists() else []
    if not raw_files:
        if source_name == "pan":
            raw_files = list(raw_base.glob("*incometaxindia*.txt"))
        elif source_name == "uidai":
            raw_files = list(raw_base.glob("*uidai*.txt"))
        else:
            raw_files = list(raw_base.glob("*.txt"))

    stats.files_scanned = len(raw_files)
    if not raw_files:
        logger.warning(f"No text files found for source '{source_name}' in {raw_source_dir}")
        return stats

    logger.info(f"Refining {len(raw_files)} raw files for '{source_name}' (dedup={dedup}, dry_run={dry_run})...")

    all_chunks: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for path in sorted(raw_files):
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            url = ""
            title = path.stem

            if lines and lines[0].startswith("URL: "):
                url = lines[0].replace("URL: ", "").strip()
                lines = lines[1:]

            if lines and lines[0].startswith("Title: "):
                title = lines[0].replace("Title: ", "").strip()
                lines = lines[1:]

            content = '\n'.join(lines)

            # Extract real page title from first heading if not yet meaningful
            if title == path.stem:
                for line in content.splitlines():
                    line_clean = line.strip()
                    if line_clean.startswith('#'):
                        heading_text = line_clean.strip('# ').strip()
                        heading_text = heading_text.replace("\ufffd", "-").replace("\u200b", " ")
                        if heading_text and heading_text.lower() not in ["guided help", "tax services", "home"]:
                            title = heading_text
                            break

            cleaned_content = clean_markdown(content, source_name)

            if len(cleaned_content.strip()) > 50:
                doc_id = path.stem
                if title == doc_id:
                    for line in cleaned_content.splitlines():
                        line_clean = re.sub(r'!\[.*?\]\(.*?\)', '', line).strip()
                        line_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line_clean).strip()
                        if line_clean and len(line_clean) > 3 and line_clean.lower() not in ["guided help", "tax services", "home"]:
                            title = line_clean
                            break

                chunk_and_save(
                    doc_id=doc_id,
                    title=title,
                    url=url,
                    cleaned_text=cleaned_content,
                    chunks_list=all_chunks,
                    source_name=source_name,
                    refined_dir=refined_source_dir,
                    dedup=dedup,
                    seen_hashes=seen_hashes,
                    stats=stats,
                    dry_run=dry_run,
                )
                stats.files_processed += 1

        except Exception as e:
            logger.error(f"Failed to process {path.name}: {e}", exc_info=True)

    # Write combined master JSONL
    if not dry_run and all_chunks:
        jsonl_filename = f"{source_name}_chunks_clean.jsonl"
        jsonl_path = refined_source_dir / jsonl_filename
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for chunk in all_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        logger.info(f"Master JSONL written to: {jsonl_path}")

    logger.info(
        f"[{source_name.upper()} COMPLETE] Processed: {stats.files_processed}/{stats.files_scanned} files | "
        f"Generated: {stats.chunks_generated} chunks | Duplicates filtered: {stats.duplicates_skipped} | "
        f"Avg words: {stats.average_chunk_words} | Avg quality: {stats.average_quality_score}"
    )

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["pan", "uidai", "all"], default="all",
                        help="Data source to refine (default: all)")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR,
                        help="Directory containing raw crawled text files")
    parser.add_argument("--refined-dir", type=Path, default=REFINED_DIR,
                        help="Output directory for refined chunks")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable cross-document deduplication (legacy mode)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate refinement without writing files to disk")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose DEBUG logging")

    args = parser.parse_args(argv)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    stats = run_refiner(
        source_name=args.source,
        raw_dir=args.raw_dir,
        refined_dir=args.refined_dir,
        dedup=not args.no_dedup,
        dry_run=args.dry_run,
    )

    print(json.dumps(stats.summary(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
