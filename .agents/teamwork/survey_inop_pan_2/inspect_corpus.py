import os
import json
from pathlib import Path

data_dir = Path("backend/data")

keywords = ["206AA", "114AAA", "03/2023", "Circular 3", "Circular 03", "234H", "inoperative", "in-operative"]

print("Searching backend/data for keywords:", keywords)

matches = []

for root, dirs, files in os.walk(data_dir):
    for f in files:
        if f.endswith((".json", ".jsonl", ".txt", ".md", ".csv")):
            p = Path(root) / f
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for kw in keywords:
                    if kw.lower() in content.lower():
                        matches.append((str(p), kw))
            except Exception as e:
                pass

print(f"Total matches found: {len(matches)}")
for p, kw in set(matches):
    print(f"File: {p} matched '{kw}'")
