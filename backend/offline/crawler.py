import hashlib
import io
import json
import logging
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pdfplumber
import requests
import trafilatura
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCES_PATH = DATA_DIR / "sources.json"
RAW_DIR = DATA_DIR / "raw"
NEEDS_OCR_PATH = DATA_DIR / "needs_ocr_or_js.txt"
NEEDS_REVERIFICATION_PATH = DATA_DIR / "needs_reverification.txt"

FIXED_DELAY_SECONDS = 2
MIN_TEXT_LENGTH = 50
USER_AGENT = "Nivaan-Bot/1.0 (Educational Project)"

# Domain Whitelist - Only allow official domains
DOMAIN_WHITELIST = {
    "uidai.gov.in",
    "myaadhaar.uidai.gov.in",
    "rbi.org.in",
    "incometax.gov.in",
    "www.incometax.gov.in",
    "tinpan.proteantech.in",
    "onlineservices.proteantech.in",
    "pan.utiitsl.com",
    "www.pan.utiitsl.com",
    "www.trackpan.utiitsl.com",
    "passportindia.gov.in",
    "www.passportindia.gov.in",
    "parivahan.gov.in",
    "epfindia.gov.in",
    "www.epfindia.gov.in",
    "epfigms.gov.in",
    "sebi.gov.in",
    "digilocker.gov.in",
    "pgportal.gov.in",
    "ncdrc.nic.in",
    "voters.eci.gov.in",
    "eci.gov.in",
    "example.com",
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- ROBOTS.TXT CACHE ---
_robots_cache = {}

def can_fetch(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # 1. Whitelist Check
    if not any(domain == whitelisted or domain.endswith("." + whitelisted) for whitelisted in DOMAIN_WHITELIST):
        logger.warning(f"Domain {domain} is not in the whitelist. Skipping.")
        return False

    # 2. Robots.txt Check
    if domain not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{parsed.scheme}://{domain}/robots.txt"
        rp.set_url(robots_url)
        try:
            rp.read()
            _robots_cache[domain] = rp
        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt for {domain}: {e}. Defaulting to True.")
            _robots_cache[domain] = None

    rp = _robots_cache.get(domain)
    if rp:
        if not rp.can_fetch(USER_AGENT, url):
            logger.warning(f"robots.txt disallows fetching {url}. Skipping.")
            return False
            
    return True


# --- HTTP SESSION WITH RETRIES ---
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# --- UTILITIES ---
def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def append_to_list_file(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if url not in lines:
        lines.append(url)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def extract_pdf_text(content: bytes) -> str:
    text_fragments = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_fragments.append(page_text)
    except Exception as e:
        logger.error(f"Failed to parse PDF: {e}")
        return ""
    return "\n\n".join(text_fragments)

def extract_sources_from_payload(payload: dict | list) -> tuple[list[dict], dict]:
    """Extracts a flat list of sources regardless of the JSON structure, returning the list and the mapping."""
    sources = []
    if isinstance(payload, list):
        sources = [s for s in payload if isinstance(s, dict)]
    elif isinstance(payload, dict):
        # Look for lists in the dict
        for key, val in payload.items():
            if isinstance(val, list):
                sources.extend([s for s in val if isinstance(s, dict)])
    return sources

def get_js_rendered_text(url: str) -> str:
    try:
        with sync_playwright() as p:
            logger.info(f"Using Playwright for JS rendering: {url}")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(4000)  # Wait 4 seconds for React to render
            html = page.content()
            
            text = trafilatura.extract(html) or ""
            if len(text) < MIN_TEXT_LENGTH:
                text = page.inner_text("body")
            browser.close()
            return text
    except Exception as e:
        logger.error(f"Playwright failed for {url}: {e}")
        return ""

# --- MAIN CRAWLER ---
def run_crawler() -> None:
    if not SOURCES_PATH.exists():
        logger.error(f"{SOURCES_PATH} not found.")
        return

    try:
        payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error("sources.json is invalid JSON.")
        return

    sources = extract_sources_from_payload(payload)
    if not sources:
        logger.info("No sources found to crawl.")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = get_session()
    changes_made = False

    for source in sources:
        url = source.get("source_url")
        source_id = source.get("source_id", "unknown_id")
        
        if not url:
            continue

        if not can_fetch(url):
            continue

        logger.info(f"Fetching: {url}")
        time.sleep(FIXED_DELAY_SECONDS)

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            
            content_type = resp.headers.get("Content-Type", "").lower()
            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                text = extract_pdf_text(resp.content)
            else:
                text = trafilatura.extract(resp.text) or ""
                if len(text.strip()) < MIN_TEXT_LENGTH:
                    text = get_js_rendered_text(url)
                
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            continue

        text = text.strip()
        
        if len(text) < MIN_TEXT_LENGTH:
            logger.warning(f"Extracted text too short. Flagging {url}.")
            append_to_list_file(NEEDS_OCR_PATH, url)
            continue

        new_hash = compute_hash(text)
        old_hash = source.get("hash")
        today_str = date.today().isoformat()
        
        new_filename = f"{source_id}_{today_str}.txt"
        new_raw_path = RAW_DIR / new_filename
        relative_raw_path = f"backend/data/raw/{new_filename}"
        
        if old_hash == new_hash:
            logger.info(f"Unchanged: {url}")
            source["last_crawled"] = today_str
            changes_made = True
        else:
            logger.info(f"New or changed content found for {url}")
            new_raw_path.write_text(text, encoding="utf-8")
            
            source["raw_path"] = relative_raw_path
            source["hash"] = new_hash
            source["last_crawled"] = today_str
            
            if old_hash:
                append_to_list_file(NEEDS_REVERIFICATION_PATH, url)
                
            changes_made = True

    if changes_made:
        SOURCES_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("sources.json updated successfully.")
    else:
        logger.info("No updates needed for sources.json.")


if __name__ == "__main__":
    run_crawler()