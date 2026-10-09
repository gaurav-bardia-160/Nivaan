import os
import glob
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
REFINED_DIR = BASE_DIR / "data" / "refined"

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
        "Ask Me Anything!!", "Search Services", "Whitelabel Error Page",
        "Enter Captcha", "This website is optimised for the latest versions"
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
        
    # Remove excessive empty lines
    text = '\n'.join(cleaned).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def run_refiner():
    if not RAW_DIR.exists():
        print(f"Error: {RAW_DIR} does not exist.")
        return

    REFINED_DIR.mkdir(parents=True, exist_ok=True)
    
    raw_files = list(RAW_DIR.glob("*.txt"))
    if not raw_files:
        print(f"No text files found in {RAW_DIR}")
        return
        
    processed_count = 0
    for path in raw_files:
        try:
            content = path.read_text(encoding="utf-8")
            
            # Extract URL if present at the top
            lines = content.split('\n')
            url = ""
            if lines and lines[0].startswith("URL: "):
                url = lines[0] + "\n\n"
                # Strip URL from content for cleaning
                content = '\n'.join(lines[1:])
            
            cleaned_content = clean_markdown(content)
            
            if len(cleaned_content.strip()) > 50:
                refined_path = REFINED_DIR / path.name
                refined_path.write_text(url + cleaned_content, encoding="utf-8")
                processed_count += 1
                
        except Exception as e:
            print(f"Failed to process {path.name}: {e}")
            
    print(f"Successfully refined {processed_count} out of {len(raw_files)} raw files.")
    print(f"Refined files saved to: {REFINED_DIR}")

if __name__ == "__main__":
    run_refiner()
