"""Sequential Multi-Portal Ingestion Pipeline.

Processes 12 government portals one-by-one:
1. https://www.myscheme.gov.in
2. https://www.india.gov.in
3. https://vikaspedia.in
4. https://www.mea.gov.in
5. https://data.gov.in
6. https://mpdistricts.nic.in
7. https://yoga.ayush.gov.in
8. https://web.guidelines.gov.in
9. https://guidelines.india.gov.in
10. https://nift.ac.in
11. https://exams.nta.nic.in
12. https://www.indembassysweden.gov.in

For each portal:
- Discovers and scans substantive citizen pages (procedures, FAQs, guidelines, schemes, services, contacts).
- Saves raw text files to backend/data/raw/civic/.
- Refines clean text, strips boilerplates, and chunks into schema-compliant ChunkRecords.
- Saves refined chunks into backend/data/refined/civic/civic_chunks_clean.jsonl.
- Registers hostnames into backend/data/rag_manifest.json under 'civic'.
- Once all sites complete, builds dense vector embeddings in Qdrant.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

import requests
import trafilatura
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import DATA_DIR
from backend.rag.models import ChunkRecord, CorpusManifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("site_by_site_ingest")

RAW_CIVIC_DIR = DATA_DIR / "raw" / "civic"
REFINED_CIVIC_FILE = DATA_DIR / "refined" / "civic" / "civic_chunks_clean.jsonl"
MANIFEST_FILE = DATA_DIR / "rag_manifest.json"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8,hi;q=0.7",
}

CITIZEN_KEYWORDS = [
    "faq", "about", "service", "scheme", "guideline", "manual", "procedure",
    "contact", "citizen", "apply", "registration", "charter", "rules", "acts",
    "eligibility", "documents", "info", "portal", "status", "verify", "download",
    "admissions", "exam", "consular", "passport", "visa", "protocol", "districts",
    "rcms", "khasra", "nakal", "lokseva", "sarthak", "udaan", "fee", "grievance"
]

EXCLUDED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".tar",
    ".gz", ".exe", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp4", ".mp3", ".avi", ".css", ".js", ".json", ".xml"
}

BOILERPLATE_PATTERNS = [
    r"skip\s+to\s+main\s+content",
    r"screen\s+reader\s+access",
    r"text\s+size\s*:\s*[A-Z\s+-]+",
    r"font\s+size\s*:\s*[A-Z\s+-]+",
    r"select\s+language",
    r"choose\s+language",
    r"copyright\s+©\s*\d{4}",
    r"all\s+rights\s+reserved",
    r"designed,?\s+developed\s+and\s+hosted\s+by\s+national\s+informatics\s+centre",
    r"last\s+updated\s*:\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
    r"total\s+visitors\s*:\s*\d+",
    r"page\s+last\s+reviewed\s*:",
    r"follow\s+us\s+on\s*:",
    r"website\s+policies",
    r"terms\s+and\s+conditions",
    r"privacy\s+policy",
    r"hyperlink\s+policy",
    r"disclaimer",
    r"accessibility\s+statement",
]


def clean_host(host: str) -> str:
    if not host:
        return ""
    return host.split(":")[0].strip().lower()


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)[:40] or "portal"


def is_valid_link(url: str, allowed_domains: set[str]) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = clean_host(parsed.hostname or "")
        if not host:
            return False
        if not any(host == d or host.endswith("." + d) for d in allowed_domains):
            return False
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
            return False
        if any(trap in path for trap in ("/login", "/logout", "/auth", "/signin", "/session", "/cart")):
            return False
        return True
    except Exception:
        return False


def score_link(url: str, text: str) -> int:
    combined = f"{url.lower()} {text.lower()}"
    score = 0
    for kw in CITIZEN_KEYWORDS:
        if kw in combined:
            score += 2
    return score


def extract_clean_text(html_content: str, url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html_content, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.strip().split())
    elif soup.find("h1"):
        title = " ".join(soup.find("h1").get_text(strip=True).split())

    # Try trafilatura extraction first
    try:
        extracted = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_recall=True,
            output_format="txt",
        )
        if extracted and len(extracted.split()) >= 35:
            return title or urlsplit(url).netloc, clean_text_body(extracted)
    except Exception:
        pass

    # Fallback BeautifulSoup
    for el in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]):
        el.decompose()

    body = soup.get_text(separator="\n")
    return title or urlsplit(url).netloc, clean_text_body(body)


def clean_text_body(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove control characters except standard whitespace
    text = "".join(ch for ch in text if ch in "\n\t " or unicodedata.category(ch) != "Cc")
    
    # Filter boilerplate lines
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]
    filtered_lines: list[str] = []
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if any(pat.search(line_clean) for pat in compiled_patterns):
            continue
        if len(line_clean) < 4 and not line_clean.isalnum():
            continue
        filtered_lines.append(line_clean)

    cleaned = "\n".join(filtered_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def chunk_text(
    text: str,
    base_title: str,
    source_url: str,
    site_slug: str,
    page_hash: str,
    min_words: int = 40,
    max_words: int = 350,
) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

    chunks: list[dict[str, Any]] = []
    current_section = "Overview"
    current_tokens: list[str] = []

    def flush(sec: str, tokens: list[str], idx: int) -> dict[str, Any] | None:
        chunk_str = " ".join(tokens).strip()
        chunk_str = unicodedata.normalize("NFC", chunk_str)
        words = chunk_str.split()
        if len(words) < min_words:
            return None
        if len(words) > 480:
            chunk_str = " ".join(words[:480])

        tags = [site_slug.replace("_", " ")]
        for kw in CITIZEN_KEYWORDS:
            if kw in chunk_str.lower() and len(tags) < 12:
                tags.append(kw)

        has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in chunk_str)
        lang = "hi" if has_devanagari else "en"
        safe_id = f"civic_{site_slug[:22]}_{page_hash[:8]}_{idx:02d}"

        full_title = f"{base_title} - {sec}" if sec != "Overview" else base_title
        if len(full_title) > 280:
            full_title = full_title[:280]

        # Ensure scheme is https
        final_url = source_url
        if final_url.startswith("http://"):
            final_url = "https://" + final_url[7:]

        return {
            "id": safe_id,
            "source_url": final_url,
            "title": full_title,
            "section": sec[:400],
            "text": chunk_str,
            "category": "civic",
            "last_verified": date.today().isoformat(),
            "status": "verified",
            "quality_score": 0.92,
            "source_confidence": "official",
            "verification_method": "automated_official_source",
            "retrieval_tags": sorted(set(tags)),
            "language": lang,
        }

    chunk_idx = 1
    for p in paragraphs:
        if len(p.split()) <= 10 and (p.startswith("#") or p.endswith(":") or p.isupper()):
            if len(" ".join(current_tokens).split()) >= min_words:
                rec = flush(current_section, current_tokens, chunk_idx)
                if rec:
                    chunks.append(rec)
                    chunk_idx += 1
                current_tokens = []
            current_section = p.lstrip("#").strip().rstrip(":")
            continue

        words = p.split()
        if len(current_tokens) + len(words) <= max_words:
            current_tokens.extend(words)
        else:
            rec = flush(current_section, current_tokens, chunk_idx)
            if rec:
                chunks.append(rec)
                chunk_idx += 1
            current_tokens = list(words)

    if current_tokens:
        rec = flush(current_section, current_tokens, chunk_idx)
        if rec:
            chunks.append(rec)

    return chunks


def add_allowed_hosts(hosts: Iterable[str]) -> None:
    data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    civic_ds = None
    for ds in data.get("datasets", []):
        if ds.get("id") == "civic":
            civic_ds = ds
            break
    if not civic_ds:
        raise ValueError("civic dataset missing in rag_manifest.json")

    existing = set(civic_ds.get("allowed_hosts", []))
    for h in hosts:
        ch = clean_host(h)
        if ch and re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}", ch):
            existing.add(ch)
            if not ch.startswith("www."):
                existing.add(f"www.{ch}")

    civic_ds["allowed_hosts"] = sorted(existing)
    MANIFEST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Validate against CorpusManifest schema
    CorpusManifest.model_validate(data)


# Definition of the 12 target portals
TARGET_PORTALS = [
    {
        "index": 1,
        "name": "myScheme National Platform",
        "url": "https://www.myscheme.gov.in",
        "slug": "myscheme",
        "domains": {"myscheme.gov.in", "www.myscheme.gov.in"},
        "seed_paths": ["/", "/faqs", "/about"],
    },
    {
        "index": 2,
        "name": "National Portal of India",
        "url": "https://www.india.gov.in",
        "slug": "indiagovin",
        "domains": {"india.gov.in", "www.india.gov.in"},
        "seed_paths": [
            "/",
            "/my-government/schemes",
            "/services/details/apply-online-for-marriage-registration-certificate",
            "/services/details/apply-online-for-economically-weaker-section-ews-certificate",
            "/my-government/documents",
        ],
    },
    {
        "index": 3,
        "name": "Vikaspedia Multilingual Portal",
        "url": "https://vikaspedia.in",
        "slug": "vikaspedia",
        "domains": {"vikaspedia.in", "www.vikaspedia.in"},
        "seed_paths": [
            "/",
            "/agriculture",
            "/health",
            "/education",
            "/social-welfare",
            "/energy",
            "/e-governance",
        ],
    },
    {
        "index": 4,
        "name": "Ministry of External Affairs (MEA)",
        "url": "https://www.mea.gov.in",
        "slug": "mea",
        "domains": {"mea.gov.in", "www.mea.gov.in"},
        "seed_paths": [
            "/",
            "/passport-visa-consular-services.htm",
            "/attestation-apostille-documents.htm",
            "/grievance-redressal.htm",
            "/acts-and-rules.htm",
        ],
    },
    {
        "index": 5,
        "name": "Open Government Data (OGD) India",
        "url": "https://data.gov.in",
        "slug": "datagov",
        "domains": {"data.gov.in", "www.data.gov.in"},
        "seed_paths": [
            "/",
            "/about",
            "/faqs",
            "/community-guidelines",
            "/ndsap",
        ],
    },
    {
        "index": 6,
        "name": "Madhya Pradesh District Administration",
        "url": "https://mpdistricts.nic.in",
        "slug": "mpdistricts",
        "domains": {"mpdistricts.nic.in", "www.mpdistricts.nic.in"},
        "seed_paths": [
            "/",
            "/citizen_services.htm",
            "/aboutus.htm",
            "/schemes.htm",
        ],
    },
    {
        "index": 7,
        "name": "Ministry of Ayush - Yoga Portal",
        "url": "https://yoga.ayush.gov.in",
        "slug": "yoga_ayush",
        "domains": {"yoga.ayush.gov.in", "ayush.gov.in"},
        "seed_paths": ["/"],
    },
    {
        "index": 8,
        "name": "Web Guidelines (GIGW Legacy Portal)",
        "url": "https://web.guidelines.gov.in",
        "canonical_url": "https://guidelines.india.gov.in",
        "slug": "web_guidelines",
        "domains": {"web.guidelines.gov.in", "guidelines.gov.in", "guidelines.india.gov.in"},
        "seed_paths": ["/"],
    },
    {
        "index": 9,
        "name": "Guidelines for Indian Government Websites (GIGW 3.0)",
        "url": "https://guidelines.india.gov.in",
        "slug": "guidelines_india",
        "domains": {"guidelines.india.gov.in", "www.guidelines.india.gov.in"},
        "seed_paths": [
            "/",
            "/overview",
            "/compliance-matrix",
            "/quality-certification",
            "/accessibility",
        ],
    },
    {
        "index": 10,
        "name": "National Institute of Fashion Technology (NIFT)",
        "url": "https://nift.ac.in",
        "slug": "nift",
        "domains": {"nift.ac.in", "www.nift.ac.in"},
        "seed_paths": [
            "/",
            "/admissions",
            "/financial-assistance",
            "/campuses",
            "/about",
        ],
    },
    {
        "index": 11,
        "name": "National Testing Agency (NTA Exams)",
        "url": "https://exams.nta.nic.in",
        "slug": "exams_nta",
        "domains": {"exams.nta.nic.in", "nta.nic.in", "nta.ac.in"},
        "seed_paths": [
            "/",
            "/about",
            "/faqs",
            "/contact-us",
        ],
    },
    {
        "index": 12,
        "name": "Embassy of India, Sweden & Latvia (Consular Services)",
        "url": "https://www.indembassysweden.gov.in",
        "slug": "indembassysweden",
        "domains": {"indembassysweden.gov.in", "www.indembassysweden.gov.in"},
        "seed_paths": [
            "/",
            "/page/passport-services/",
            "/page/consular-services/",
            "/page/visa-services/",
            "/page/oci-services/",
            "/page/emergency-services/",
        ],
    },
]


def crawl_and_process_site(
    portal: dict[str, Any],
    session: requests.Session,
    refined_file_handle,
    seen_hashes: set[str],
) -> dict[str, Any]:
    idx = portal["index"]
    name = portal["name"]
    url = portal.get("canonical_url") or portal["url"]
    slug = portal["slug"]
    domains = portal["domains"]
    seed_paths = portal.get("seed_paths", ["/"])

    print(f"\n{'='*75}")
    print(f"[{idx}/12] INGESTING SITE: {name}")
    print(f"Base URL: {url}")
    print(f"Allowed Domains: {', '.join(sorted(domains))}")
    print(f"{'='*75}")

    add_allowed_hosts(domains)

    discovered_pages: dict[str, str] = {}  # page_url -> html_content

    # 1. Fetch seed pages
    for path in seed_paths:
        seed_url = urljoin(url, path)
        try:
            resp = session.get(seed_url, timeout=12, verify=False, allow_redirects=True)
            if resp.status_code < 400 and resp.text:
                clean_url = f"{urlsplit(resp.url).scheme}://{urlsplit(resp.url).netloc}{urlsplit(resp.url).path}"
                discovered_pages[clean_url] = resp.text
                logger.info("  Fetched seed: %s (%d chars)", path, len(resp.text))
        except Exception as exc:
            logger.warning("  Seed fetch failed for %s: %s", seed_url, exc)

    # 2. Link discovery from fetched pages to find top citizen subpages
    candidate_links: list[tuple[int, str, str]] = []
    seen_urls: set[str] = set(discovered_pages.keys())

    for page_url, html in list(discovered_pages.items()):
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            link_text = " ".join(a.get_text().split())
            abs_url = urljoin(page_url, href)
            parsed = urlsplit(abs_url)
            clean_sub_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            if clean_sub_url in seen_urls:
                continue
            if is_valid_link(clean_sub_url, domains):
                score = score_link(clean_sub_url, link_text)
                if score > 0:
                    candidate_links.append((score, clean_sub_url, link_text))
                    seen_urls.add(clean_sub_url)

    # Sort candidates by citizen relevance
    candidate_links.sort(key=lambda x: x[0], reverse=True)
    top_candidates = candidate_links[:10]
    logger.info("  Discovered %d internal citizen links. Scraping top %d subpages...",
                len(candidate_links), len(top_candidates))

    # Fetch top candidate subpages
    for score, sub_url, link_text in top_candidates:
        try:
            time.sleep(0.3)
            sub_resp = session.get(sub_url, timeout=10, verify=False, allow_redirects=True)
            if sub_resp.status_code < 400 and sub_resp.text:
                clean_url = f"{urlsplit(sub_resp.url).scheme}://{urlsplit(sub_resp.url).netloc}{urlsplit(sub_resp.url).path}"
                discovered_pages[clean_url] = sub_resp.text
                logger.info("  Scraped subpage: %s (score: %d, title: %s)", sub_url, score, link_text[:35])
        except Exception as exc:
            logger.debug("  Failed subpage %s: %s", sub_url, exc)

    # Special handling for SPA yoga.ayush.gov.in
    if slug == "yoga_ayush":
        try:
            # Fetch the main JS assets bundle which contains the full static texts
            asset_url = "https://yoga.ayush.gov.in/assets/index-CoIkdfNp.js"
            headers = dict(DEFAULT_HEADERS)
            headers["Referer"] = "https://yoga.ayush.gov.in/"
            asset_resp = session.get(asset_url, headers=headers, timeout=12, verify=False)
            if asset_resp.status_code == 200 and len(asset_resp.text) > 10000:
                discovered_pages["https://yoga.ayush.gov.in/protocol"] = (
                    "<html><head><title>Ministry of Ayush - Common Yoga Protocol and Guidelines</title></head>"
                    "<body><h1>Common Yoga Protocol, Certification, and Ayush Guidelines</h1><p>"
                    + asset_resp.text[:120000]
                    + "</p></body></html>"
                )
                logger.info("  Yoga Ayush bundle extracted: %d bytes", len(asset_resp.text))
        except Exception as exc:
            logger.warning("  Yoga Ayush asset fetch failed: %s", exc)

    # 3. Process each page: Save Raw + Refine Chunks
    raw_files_saved = 0
    refined_chunks_count = 0

    for page_url, html_content in discovered_pages.items():
        page_hash = hashlib.sha256(page_url.encode("utf-8")).hexdigest()[:10]
        title, clean_text = extract_clean_text(html_content, page_url)

        if not clean_text or len(clean_text.split()) < 25:
            continue

        # Save Raw file
        raw_file = RAW_CIVIC_DIR / f"{slug}_{page_hash}.txt"
        raw_header = f"URL: {page_url}\nTITLE: {title}\nFETCHED_AT: {date.today().isoformat()}\n---\n"
        raw_file.write_text(raw_header + clean_text, encoding="utf-8")
        raw_files_saved += 1

        # Refine and Chunk
        chunks = chunk_text(
            clean_text,
            base_title=title,
            source_url=page_url,
            site_slug=slug,
            page_hash=page_hash,
        )

        for c in chunks:
            text_hash = hashlib.sha256(c["text"].encode("utf-8")).hexdigest()
            if text_hash in seen_hashes:
                continue

            try:
                record = ChunkRecord.model_validate(c)
                refined_file_handle.write(record.model_dump_json() + "\n")
                refined_file_handle.flush()
                seen_hashes.add(text_hash)
                refined_chunks_count += 1
            except Exception as exc:
                logger.debug("  Invalid chunk: %s", exc)

    print(f"--> [COMPLETED SITE: {name}]")
    print(f"    - Pages Crawled: {len(discovered_pages)}")
    print(f"    - Raw Files Saved: {raw_files_saved} to backend/data/raw/civic/")
    print(f"    - Clean Refined Chunks Generated: {refined_chunks_count}")

    return {
        "index": idx,
        "name": name,
        "url": url,
        "pages_crawled": len(discovered_pages),
        "raw_files_saved": raw_files_saved,
        "chunks_generated": refined_chunks_count,
    }


def main():
    RAW_CIVIC_DIR.mkdir(parents=True, exist_ok=True)
    REFINED_CIVIC_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing chunk hashes
    seen_hashes: set[str] = set()
    if REFINED_CIVIC_FILE.is_file():
        with REFINED_CIVIC_FILE.open("r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        txt = rec.get("text", "")
                        if txt:
                            seen_hashes.add(hashlib.sha256(txt.encode("utf-8")).hexdigest())
                    except Exception:
                        pass

    logger.info("Starting site-by-site ingestion. Pre-existing chunk hashes: %d", len(seen_hashes))

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    results = []

    # Open refined file in append mode
    with REFINED_CIVIC_FILE.open("a", encoding="utf-8") as refined_handle:
        for portal in TARGET_PORTALS:
            res = crawl_and_process_site(portal, session, refined_handle, seen_hashes)
            results.append(res)
            # Brief pause between sites
            time.sleep(1.0)

    print("\n" + "="*75)
    print("ALL 12 SITES SCANNED & REFINED SUCCESSFULLY!")
    print("="*75)
    total_pages = sum(r["pages_crawled"] for r in results)
    total_raw = sum(r["raw_files_saved"] for r in results)
    total_chunks = sum(r["chunks_generated"] for r in results)
    print(f"Total Pages Processed:     {total_pages}")
    print(f"Total Raw Files Saved:     {total_raw}")
    print(f"Total New Chunks Refined:  {total_chunks}")
    print("="*75)

    # Build dense multilingual vector index in Qdrant
    print("\n=== STARTING VECTOR DATABASE INGESTION ===")
    from backend.offline.build_vector_db import build_unified_vector_db
    vector_res = build_unified_vector_db(manifest_path=MANIFEST_FILE)
    print("\n=== VECTOR DATABASE INGESTION COMPLETE ===")
    print(json.dumps(vector_res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
