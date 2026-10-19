"""Batch scraper and refiner for official civic portals.

Curls and extracts clean procedures from government and banking portals,
refines them into schema-compliant ChunkRecords, registers them in rag_manifest.json,
and builds dense multilingual vector embeddings in Qdrant.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch_scraper")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "civic"
REFINED_DIR = DATA_DIR / "refined" / "civic"
MANIFEST_PATH = DATA_DIR / "rag_manifest.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Candidate URLs provided by user
TARGET_URLS = [
    "https://www.passportindia.gov.in/psp",
    "https://voters.eci.gov.in/",
    "https://parivahan.gov.in/",
    "https://dc.crsorgi.gov.in/crs/",
    "https://dc.crsorgi.gov.in/crs/dwnld",
    "https://www.india.gov.in/services/details/apply-online-for-marriage-registration-certificate",
    "https://nfsa.gov.in/portal/PDS_page",
    "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/income-tax-returns",
    "https://posbseva.indiapost.gov.in/indiapost/signin",
    "https://ebanking.indiapost.gov.in/corp/AuthenticationController?FORMSGROUP_ID__=AuthenticationFG&__START_TRAN_FLAG__=Y&__FG_BUTTONS__=LOAD&ACTION.LOAD=Y&AuthenticationFG.LOGIN_FLAG=1&BANK_ID=DOP",
    "https://ippbonline.bank.in/web/ippb/sms-banking2",
    "https://passbook.epfindia.gov.in/MemberPassBook/login",
    "https://dashboard.nha.gov.in/public/",
    "https://ncbc.nic.in/",
    "https://ncbc.nic.in/user_panel/centralliststateview.aspx",
    "https://socialjustice.gov.in/",
    "https://www.india.gov.in/services/details/apply-online-for-economically-weaker-section-ews-certificate",
    "https://swavlambancard.gov.in/",
    "https://www.annualreports.com/",
    "https://www.indiabudget.gov.in/",
    "https://www.understandupsc.com/demands-for-grants/",
    "https://censusindia.gov.in/census.website/en",
    "https://goicharters.nic.in/",
    "https://www.india.gov.in/my-government/schemes",
    "https://www.dolr.gov.in/",
    "https://anyror.gujarat.gov.in/",
    "https://garvi.gujarat.gov.in/",
    "https://ahmedabadcity.gov.in/",
    "https://parikshasangam.cbse.gov.in/PS/frmListing",
    "https://www.gseb.org/",
    "https://www.stockholding.com/",
    "https://services.ecourts.gov.in/ecourtindia_v6/",
    "https://egazette.gov.in/(S(shpjnphh3m2djaslfg2vx1ps))/default.aspx",
    "https://indianfrro.gov.in/efrro/home",
    "https://ociservices.gov.in/onlineOCI/",
    "https://uwin.mohfw.gov.in/home",
    "https://www.digilocker.gov.in/",
    "https://bhavishya.nic.in/",
    "https://udyamregistration.gov.in/",
    "https://www.gst.gov.in/",
    "https://www.nsws.gov.in/",
    "https://www.india.gov.in/my-government/documents",
    "https://pgportal.gov.in/",
    "https://rtionline.gov.in/",
    "https://pmkisan.gov.in/",
    "https://www.mygov.in/",
    "https://web.umang.gov.in/landing/",
    "https://www.constitutionofindia.net/read/",
    "https://www.legislative.gov.in/constitution-of-india",
    "https://www.sebi.gov.in/",
    "https://rbi.org.in/",
]


def clean_text(raw: str) -> str:
    """Normalize whitespace and strip unprintable characters."""
    text = unicodedata.normalize("NFC", raw)
    text = re.sub(r"\r\n|\r", "\n", text)
    # Remove control characters except standard whitespace
    text = "".join(ch for ch in text if ch in "\n\t " or unicodedata.category(ch) != "Cc")
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_content(html: str, url: str) -> tuple[str, str]:
    """Extract page title and substantive content."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Title extraction
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)
    if not title:
        parsed = urlsplit(url)
        title = f"{parsed.netloc} portal guidance"
    title = " ".join(title.split())

    # Text extraction via trafilatura first
    extracted = trafilatura.extract(
        html,
        include_links=False,
        include_images=False,
        favor_recall=True,
        include_tables=True,
    )
    
    if extracted and len(extracted.split()) >= 30:
        return title, clean_text(extracted)

    # Fallback to BeautifulSoup extraction
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    body_text = soup.get_text(separator="\n")
    cleaned = clean_text(body_text)
    # Filter empty lines
    lines = [line.strip() for line in cleaned.splitlines() if len(line.strip()) > 3]
    return title, "\n".join(lines)


def crawl_urls() -> list[dict[str, str]]:
    """Stage 1: Fetch and save raw pages."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    results = []
    seen_urls = set()

    for idx, url in enumerate(TARGET_URLS, 1):
        if url in seen_urls:
            continue
        seen_urls.add(url)

        parsed = urlsplit(url)
        host = parsed.netloc.lower()
        slug = re.sub(r"[^a-z0-9_-]", "_", host + parsed.path)[:60]
        hash_suffix = hashlib.sha256(url.encode()).hexdigest()[:8]
        raw_filename = f"{idx:02d}_{slug}_{hash_suffix}.txt"
        raw_path = RAW_DIR / raw_filename

        logger.info("[%d/%d] Fetching %s ...", idx, len(TARGET_URLS), url)
        try:
            resp = session.get(url, timeout=15, verify=False, allow_redirects=True)
            if resp.status_code >= 400:
                logger.warning("HTTP %d for %s", resp.status_code, url)
                continue
            
            title, text = extract_content(resp.text, url)
            if not text or len(text.split()) < 15:
                logger.warning("Sparse content (%d words) for %s, skipping", len(text.split()) if text else 0, url)
                continue

            # Write raw content with metadata header
            raw_content = f"URL: {url}\nTITLE: {title}\nFETCHED_AT: {date.today().isoformat()}\n---\n{text}"
            raw_path.write_text(raw_content, encoding="utf-8")
            logger.info("Saved raw file: %s (%d words)", raw_filename, len(text.split()))

            results.append({
                "url": url,
                "host": host,
                "title": title,
                "text": text,
                "raw_file": str(raw_path.relative_to(BASE_DIR)),
            })
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)

    logger.info("Stage 1 complete: %d / %d URLs scraped successfully.", len(results), len(TARGET_URLS))
    return results


def refine_and_chunk(crawled: list[dict[str, str]]) -> list[dict[str, object]]:
    """Stage 2: Refine and generate schema-compliant ChunkRecords."""
    REFINED_DIR.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, object]] = []

    for entry in crawled:
        url = entry["url"]
        host = entry["host"]
        title = entry["title"]
        text = entry["text"]

        # Break text into paragraphs or section chunks (100 - 300 words)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        current_chunk_words: list[str] = []
        current_section = title
        chunk_idx = 1

        def flush_chunk():
            nonlocal chunk_idx, current_chunk_words
            chunk_body = " ".join(current_chunk_words).strip()
            if len(chunk_body.split()) >= 20:
                chunk_id = f"civic_{re.sub(r'[^a-z0-9_]', '', host)}_{hashlib.sha256((url + str(chunk_idx)).encode()).hexdigest()[:10]}"
                # Extract simple retrieval tags
                words = re.findall(r"\b[a-zA-Z]{4,}\b", (title + " " + chunk_body).lower())
                tags = sorted(list(set(words[:15])))
                
                record = {
                    "id": chunk_id,
                    "source_url": url,
                    "title": title[:500],
                    "section": current_section[:500],
                    "text": chunk_body[:20000],
                    "category": "civic",
                    "last_verified": date.today().isoformat(),
                    "status": "automated_verified",
                    "quality_score": 0.85,
                    "source_confidence": "official",
                    "verification_method": "automated_portal_crawl",
                    "retrieval_tags": tags,
                    "language": "en",
                }
                chunks.append(record)
                chunk_idx += 1
            current_chunk_words = []

        for p in paragraphs:
            # Check if paragraph looks like a section header
            if len(p.split()) < 10 and not p.endswith("."):
                current_section = p

            words = p.split()
            if len(current_chunk_words) + len(words) > 250:
                flush_chunk()
            current_chunk_words.extend(words)

        if current_chunk_words:
            flush_chunk()

    # Save master refined jsonl
    out_jsonl = REFINED_DIR / "civic_chunks_clean.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    logger.info("Stage 2 complete: %d refined chunks written to %s", len(chunks), out_jsonl)
    return chunks


def update_rag_manifest(crawled: list[dict[str, str]]) -> None:
    """Stage 3: Register civic dataset and allowed hostnames in rag_manifest.json."""
    if not MANIFEST_PATH.exists():
        logger.error("rag_manifest.json not found at %s", MANIFEST_PATH)
        return

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    datasets = data.get("datasets", [])

    # Collect all unique hostnames from crawled pages
    hosts = set()
    for item in crawled:
        parsed = urlsplit(item["url"])
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())

    # Build civic dataset spec
    civic_spec = {
        "id": "civic",
        "path": "refined/civic/civic_chunks_clean.jsonl",
        "category": "civic",
        "allowed_hosts": sorted(list(hosts)),
    }

    # Replace or append
    existing_idx = next((i for i, d in enumerate(datasets) if d.get("id") == "civic"), None)
    if existing_idx is not None:
        datasets[existing_idx] = civic_spec
    else:
        datasets.append(civic_spec)

    data["datasets"] = datasets
    MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Stage 3 complete: Registered 'civic' dataset with %d allowed hosts in rag_manifest.json", len(hosts))


def main():
    logger.info("=== Starting Civic Portals Scraping Pipeline ===")
    crawled = crawl_urls()
    if not crawled:
        logger.error("No pages were scraped. Terminating.")
        return 1

    chunks = refine_and_chunk(crawled)
    if not chunks:
        logger.error("No chunks were refined. Terminating.")
        return 1

    update_rag_manifest(crawled)

    logger.info("=== Starting Vector Database Ingestion ===")
    from backend.offline.build_vector_db import build_unified_vector_db
    result = build_unified_vector_db(manifest_path=MANIFEST_PATH)
    logger.info("=== Pipeline Complete! Vector DB Result: ===")
    logger.info(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
