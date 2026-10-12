import asyncio
import json
import logging
import hashlib
import re
import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse, urljoin
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Junk keywords in URLs or link text to ignore
JUNK_KEYWORDS = [
    "terms", "conditions", "privacy", "policy", "login", "register", 
    "captcha", "contact", "sitemap", "disclaimer",
    "archive", "media", "video", "career", "regional", "dashboard", "/hi",
    "developer", "update_language", "languageid=hi_in", "screen-reader",
    "report-phishing", "childrens-corner", "feedback", "locators",
    "tax-helpline", "website-analytics", "website-policies", "accessibility",
    "website-certifications"
]

def is_junk_link(url: str, text: str) -> bool:
    target = (url + " " + text).lower()
    for junk in JUNK_KEYWORDS:
        if junk in target:
            return True
    return False

def clean_raw_markdown(md: str, url: str) -> str:
    """Pre-cleaning before saving raw text to avoid saving massive repetitive navigation menus."""
    lines = md.split('\n')
    
    # For incometaxindia.gov.in, extract main content starting from main headings
    if "incometaxindia.gov.in" in url:
        content_lines = []
        capturing = False
        for line in lines:
            # Main content starts at the service heading
            if re.match(r'^#\s+.*', line) and not capturing:
                if "IT Bill" not in line and "TDS" not in line:
                    capturing = True
            # Cut off footer widgets like IT Bill Comparison Tool or Public Awareness
            if capturing and any(marker in line for marker in ["IT Bill Comparison Tool", "Public Awareness", "Last reviewed and updated on:"]):
                break
            if capturing:
                content_lines.append(line)
                
        if content_lines:
            return '\n'.join(content_lines).strip()
            
    return md.strip()

async def spider_website(start_url: str, source_name: str = "pan"):
    domain = urlparse(start_url).netloc
    visited = set()
    to_visit = {start_url}

    # Dedicated source dir inside raw
    source_raw_dir = RAW_DIR / source_name
    source_raw_dir.mkdir(parents=True, exist_ok=True)

    # Seed related PAN pages if targeting income tax PAN service
    if "incometaxindia.gov.in" in domain and "pan" in start_url.lower():
        pan_seed_urls = [
            "https://www.incometaxindia.gov.in/tax-services/apply-for-pan",
            "https://www.incometaxindia.gov.in/tax-services/instant-e-pan",
            "https://www.incometaxindia.gov.in/tax-services/online-pan-verification",
            "https://www.incometaxindia.gov.in/tax-services/status-of-pan-protean",
            "https://www.incometaxindia.gov.in/tax-services/status-of-pan-utitsl",
            "https://www.incometaxindia.gov.in/tax-services/link-aadhaar",
            "https://www.incometaxindia.gov.in/tax-services/tan-pan-consolidated-file",
            "https://www.incometaxindia.gov.in/pan-verification",
            "https://www.incometaxindia.gov.in/pan",
            "https://www.incometaxindia.gov.in/pan-as-per-income-tax-act-1961-"
        ]
        for s_url in pan_seed_urls:
            to_visit.add(s_url)

    logger.info(f"Starting spider on: {start_url} (queue size: {len(to_visit)})")

    config = CrawlerRunConfig(
        magic=True,
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=30,
        exclude_external_links=False
    )

    async with AsyncWebCrawler() as crawler:
        while to_visit:
            current_url = to_visit.pop()
            if current_url in visited:
                continue
                
            visited.add(current_url)
            logger.info(f"Crawling ({len(visited)}/{len(visited) + len(to_visit)}): {current_url}")
            
            result = await crawler.arun(url=current_url, config=config)
            
            if not result.success:
                logger.error(f"Failed to crawl {current_url}: {result.error_message}")
                continue
                
            # 1. Save valid raw content
            if result.markdown and len(result.markdown) > 50:
                raw_text = clean_raw_markdown(result.markdown, current_url)
                if len(raw_text) > 50:
                    h = hashlib.md5(current_url.encode()).hexdigest()[:8]
                    filename = f"spider_{domain}_{h}.txt"
                    
                    file_content = f"URL: {current_url}\n\n{raw_text}"
                    
                    # Save directly to raw/
                    (RAW_DIR / filename).write_text(file_content, encoding="utf-8")
                    # Also save to raw/{source_name}/
                    (source_raw_dir / filename).write_text(file_content, encoding="utf-8")
                    logger.info(f"Saved {filename} ({len(raw_text.split())} words)")

            # 2. Extract internal links
            internal_links = result.links.get("internal", [])
            for link_obj in internal_links:
                href = link_obj.get("href")
                text = link_obj.get("text", "")
                
                if not href:
                    continue
                    
                full_url = urljoin(current_url, href)
                
                if full_url not in visited and full_url not in to_visit:
                    parsed_full = urlparse(full_url)
                    if parsed_full.netloc == domain and not is_junk_link(full_url, text):
                        # Filter to relevant PAN links on incometaxindia
                        if "incometaxindia.gov.in" in domain:
                            u_lower = full_url.lower()
                            t_lower = text.lower()
                            if any(k in u_lower for k in ["apply-for-pan", "instant-e-pan", "online-pan", "status-of-pan", "link-aadhaar", "tan-pan", "pan-verification", "/pan"]):
                                to_visit.add(full_url)
                        else:
                            to_visit.add(full_url)

    logger.info(f"Spider completed! Crawled {len(visited)} pages. Saved to {RAW_DIR} and {source_raw_dir}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://www.incometaxindia.gov.in/tax-services/apply-for-pan")
    parser.add_argument("--source", default="pan")
    args = parser.parse_args()
    asyncio.run(spider_website(args.url, args.source))
