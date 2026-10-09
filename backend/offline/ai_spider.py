import asyncio
import json
import logging
import hashlib
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
    "developer"
]

def is_junk_link(url: str, text: str) -> bool:
    target = (url + " " + text).lower()
    for junk in JUNK_KEYWORDS:
        if junk in target:
            return True
    return False

import re

def clean_markdown(md: str) -> str:
    lines = md.split('\n')
    cleaned = []
    # Common UI noises found on government sites
    skip_keywords = [
        "Skip to Main Content", "Screen Reader", "Language selection", 
        "Footer background", "Menu icon", "Open external website",
        "Hindi (हिन्दी)", "My Aadhaar", "About UIDAI",
        "Build with Us", "Quick Links", "Other Links", "UIDAI — Unique", 
        "Mobile menu toggle", "JavaScript must be enabled", "UIDAl website translation",
        "Ask Me Anything!!", "Search Services"
    ]
    exact_skip_keywords = ["Home", "More", "Media", "Documents", "Help", "English"]
    
    for line in lines:
        line_clean = line.strip()
        # Remove markdown link syntax for exact matching, e.g. [Home](...) -> Home
        text_only = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line_clean).strip()
        text_only = re.sub(r'^[#*\- ]+', '', text_only).strip() # remove bullets/headings
        
        if any(k.lower() in line.lower() for k in skip_keywords):
            continue
        if any(k.lower() == text_only.lower() for k in exact_skip_keywords):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()

import sys
import argparse

async def spider_website(start_url: str, source_name: str):
    domain = urlparse(start_url).netloc
    visited = set()
    to_visit = {start_url}

    target_dir = RAW_DIR / source_name
    target_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting spider on: {start_url}")
    logger.info(f"Saving to: {target_dir}")

    config = CrawlerRunConfig(
        magic=True,
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=50,
        exclude_external_links=True
    )

    async with AsyncWebCrawler() as crawler:
        while to_visit:
            current_url = to_visit.pop()
            if current_url in visited:
                continue
                
            visited.add(current_url)
            logger.info(f"Crawling: {current_url}")
            
            result = await crawler.arun(url=current_url, config=config)
            
            if not result.success:
                logger.error(f"Failed to crawl {current_url}: {result.error_message}")
                continue
                
            if result.markdown and len(result.markdown) > 100:
                cleaned_text = clean_markdown(result.markdown)
                if len(cleaned_text) > 100:
                    h = hashlib.md5(current_url.encode()).hexdigest()[:8]
                    filename = f"spider_{domain}_{h}.txt"
                    filepath = target_dir / filename
                    filepath.write_text(f"URL: {current_url}\n\n{cleaned_text}", encoding="utf-8")
                    logger.info(f"Saved {filename}")

            internal_links = result.links.get("internal", [])
            for link_obj in internal_links:
                href = link_obj.get("href")
                text = link_obj.get("text", "")
                
                if not href:
                    continue
                    
                full_url = urljoin(current_url, href)
                
                if full_url not in visited and full_url not in to_visit:
                    if full_url.startswith(start_url) and not is_junk_link(full_url, text):
                        to_visit.add(full_url)
                    elif not full_url.startswith(start_url):
                        logger.debug(f"Ignored out-of-scope link: {full_url}")
                    else:
                        logger.debug(f"Ignored junk link: {full_url}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    asyncio.run(spider_website(args.url, args.source))
