import json
import re

transcript_path = r"C:\Users\gaura\.gemini\antigravity-cli\brain\928e8751-94e0-4c62-836d-ea832502f468\.system_generated\logs\transcript_full.jsonl"
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if '"step_index":5961' in line:
            data = json.loads(line)
            content = data.get("content", "")
            urls = re.findall(r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s\)\"\'<>]*)?", content)
            # deduplicate while preserving order
            seen = set()
            ordered = []
            for u in urls:
                clean_u = u.rstrip(".,;")
                if clean_u not in seen:
                    seen.add(clean_u)
                    ordered.append(clean_u)
            print(f"Total Unique URLs found: {len(ordered)}")
            for i, u in enumerate(ordered[:30], 1):
                print(f"{i:2d}. {u}")
            break
