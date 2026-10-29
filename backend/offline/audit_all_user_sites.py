import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from backend.config import DATA_DIR
from backend.rag.loader import load_corpus

RAW_DIR = DATA_DIR / "raw"
REFINED_DIR = DATA_DIR / "refined"
MANIFEST_FILE = DATA_DIR / "rag_manifest.json"

# Read user prompt URLs
transcript_path = r"C:\Users\gaura\.gemini\antigravity-cli\brain\928e8751-94e0-4c62-836d-ea832502f468\.system_generated\logs\transcript_full.jsonl"
urls_found = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if '"step_index":5961' in line:
            data = json.loads(line)
            content = data.get("content", "")
            raw_urls = re.findall(r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s\)\"\'<>]*)?", content)
            for u in raw_urls:
                u_clean = u.rstrip(".,;)\"'>")
                if u_clean not in urls_found:
                    urls_found.append(u_clean)
            break

# Load Manifest
manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
all_manifest_hosts = set()
for ds in manifest.get("datasets", []):
    for h in ds.get("allowed_hosts", []):
        all_manifest_hosts.add(h.lower())

# Load all refined text, urls, and domain tags
refined_urls = set()
refined_hosts = set()
for jsonl_file in REFINED_DIR.rglob("*.jsonl"):
    folder_name = jsonl_file.parent.name.replace("_", ".")
    refined_hosts.add(folder_name.lower())
    with jsonl_file.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                try:
                    rec = json.loads(line)
                    u = rec.get("source_url", "")
                    if u:
                        refined_urls.add(u)
                        host = urlsplit(u).hostname or ""
                        refined_hosts.add(host.lower())
                    for tag in rec.get("retrieval_tags", []):
                        refined_hosts.add(tag.lower().replace(" ", "."))
                except:
                    pass

# Load all raw files
raw_files = list(RAW_DIR.rglob("*.txt"))
raw_contents = []
raw_hosts = set()
for rf in raw_files:
    raw_folder = rf.parent.name.replace("_", ".")
    raw_hosts.add(raw_folder.lower())
    try:
        header = rf.read_text(encoding="utf-8", errors="ignore")[:400]
        m = re.search(r"URL:\s*(https?://[^\s\n]+)", header)
        if m:
            host = urlsplit(m.group(1)).hostname or ""
            raw_hosts.add(host.lower())
        m2 = re.search(r"DOMAIN:\s*([^\s\n]+)", header)
        if m2:
            raw_hosts.add(m2.group(1).lower())
    except:
        pass

# Group by unique domain
domains_map = {}
for u in urls_found:
    parsed = urlsplit(u)
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        continue
    # Filter out external commercial sites mentioned in footnote text
    if not any(host.endswith(tld) for tld in (".gov.in", ".nic.in", ".org.in", ".ac.in", ".res.in", ".in")):
        continue
    if host not in domains_map:
        domains_map[host] = {
            "domain": host,
            "url": f"{parsed.scheme}://{host}",
            "raw_extracted": any(host in rh or rh in host for rh in raw_hosts),
            "refined_extracted": any(host in rh or rh in host for rh in refined_hosts),
            "in_manifest": any(host in mh or mh in host for mh in all_manifest_hosts),
        }

total = len(domains_map)
ready = sum(1 for d in domains_map.values() if d["refined_extracted"] and d["in_manifest"])
partial = sum(1 for d in domains_map.values() if d["raw_extracted"] and not d["refined_extracted"])
pending = total - ready - partial

print(f"Total Unique Official Portals Identified in Prompt: {total}")
print(f"  [OK] Fully Ingested & Vector-Indexed: {ready}")
print(f"  [WAIT] Raw Extracted / Partially Refined: {partial}")
print(f"  [PENDING] Remaining to Ingest: {pending}")

print("\n--- SAMPLE FULLY INGESTED PORTALS ---")
for d in list(domains_map.values()):
    if d["refined_extracted"]:
        print(f"  [OK] {d['domain']}")

print("\n--- RAW EXTRACTED / PARTIALLY REFINED ---")
for d in list(domains_map.values()):
    if d["raw_extracted"] and not d["refined_extracted"]:
        print(f"  [PARTIAL] {d['domain']}")

print("\n--- PENDING / NEXT IN QUEUE ---")
for d in list(domains_map.values()):
    if not d["raw_extracted"] and not d["refined_extracted"]:
        print(f"  [PENDING] {d['domain']}")
