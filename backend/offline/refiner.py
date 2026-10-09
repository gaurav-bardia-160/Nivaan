import os
import glob
import re
import json
from pathlib import Path
from datetime import date

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
        "Enter Captcha", "This website is optimised for the latest versions",
        "Website Policy", "Terms & Conditions", "Privacy Policy",
        "Hyperlink Policy", "Copyright Policy", "Disclaimer", "Accessibility Statement",
        "Contact Us", "Sitemap", "Bhuvan Aadhaar", "Aadhaar Dashboard", "Aadhaar Data Vault",
        "Aadhaar Mitra", "Grievance Redressal", "Follow Us On"
    ]
    exact_skip_keywords = ["Home", "More", "Media", "Documents", "Help", "English", "Facebook", "Twitter", "YouTube", "Instagram", "LinkedIn", "Koo", "Login"]
    
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

def extract_tags(text: str) -> list:
    tags = []
    text_lower = text.lower()
    keywords = ["aadhaar", "update", "mobile", "fee", "download", "biometric", "authentication", "enrolment", "pan", "status", "lock", "unlock", "pvc"]
    for kw in keywords:
        if kw in text_lower:
            tags.append(kw)
    if not tags:
        tags = ["uidai_service"]
    return tags

def chunk_and_save(doc_id: str, title: str, url: str, cleaned_text: str, chunks_list: list):
    # Strip image markdowns
    cleaned_text = re.sub(r'!\[.*?\]\(.*?\)', '', cleaned_text)
    
    # Chunk by markdown headings (## or #)
    raw_pieces = re.split(r'\n(?=#+ )', cleaned_text)
    
    # 1. Merge tiny pieces
    merged_pieces = []
    current_piece = ""
    for piece in raw_pieces:
        piece = piece.strip()
        if not piece: continue
        
        if current_piece:
            current_piece += "\n\n" + piece
        else:
            current_piece = piece
            
        # If current_piece has enough words, push it
        if len(current_piece.split()) >= 150:
            merged_pieces.append(current_piece)
            current_piece = ""
            
    if current_piece:
        if merged_pieces and len(current_piece.split()) < 100:
            merged_pieces[-1] += "\n\n" + current_piece
        else:
            merged_pieces.append(current_piece)
            
    # 2. Split huge pieces
    final_chunks = []
    for piece in merged_pieces:
        words = piece.split()
        if len(words) > 500:
            # split by paragraphs
            paragraphs = piece.split('\n\n')
            temp_chunk = ""
            for p in paragraphs:
                if len((temp_chunk + " " + p).split()) > 400 and temp_chunk:
                    final_chunks.append(temp_chunk.strip())
                    temp_chunk = p
                else:
                    temp_chunk += "\n\n" + p if temp_chunk else p
            if temp_chunk:
                final_chunks.append(temp_chunk.strip())
        else:
            final_chunks.append(piece)
            
    # Now save them
    for i, chunk_text in enumerate(final_chunks):
        words = len(chunk_text.split())
        if words < 40: 
            continue # drop chunks under 40 words
            
        section = title
        lines = chunk_text.split('\n')
        if lines and lines[0].startswith('#'):
            section = lines[0].strip('# ').strip()
            
        chunk_id = f"{doc_id}_chunk_{i+1}"
        draft = {
            "id": chunk_id,
            "source_url": url,
            "title": title,
            "section": section,
            "text": chunk_text,
            "category": "aadhaar",
            "last_verified": date.today().isoformat(),
            "status": "unverified",
            "quality_score": 0.85, # automated quality score for clean chunks
            "source_confidence": "official",
            "verification_method": "automated_official_source",
            "retrieval_tags": extract_tags(chunk_text)
        }
        
        # Save individual JSON chunk
        chunk_path = REFINED_DIR / f"{chunk_id}.json"
        chunk_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        chunks_list.append(draft)

def run_refiner():
    if not RAW_DIR.exists():
        print(f"Error: {RAW_DIR} does not exist.")
        return

    REFINED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Remove old files to avoid confusion
    for old_file in REFINED_DIR.glob("*"):
        old_file.unlink()
        
    raw_files = list(RAW_DIR.glob("*.txt"))
    if not raw_files:
        print(f"No text files found in {RAW_DIR}")
        return
        
    processed_count = 0
    all_chunks = []
    
    for path in raw_files:
        try:
            content = path.read_text(encoding="utf-8")
            
            # Extract URL if present at the top
            lines = content.split('\n')
            url = ""
            if lines and lines[0].startswith("URL: "):
                url = lines[0].replace("URL: ", "").strip()
                # Strip URL from content for cleaning
                content = '\n'.join(lines[1:])
            
            cleaned_content = clean_markdown(content)
            
            if len(cleaned_content.strip()) > 50:
                doc_id = path.stem
                
                # Extract real page title instead of file-hash
                title = doc_id
                for line in cleaned_content.split('\n'):
                    if line.strip() and not line.startswith('#'):
                        title = line.strip()
                        break
                    elif line.startswith('#'):
                        title = line.strip('# ').strip()
                        break
                        
                chunk_and_save(doc_id, title, url, cleaned_content, all_chunks)
                processed_count += 1
                
        except Exception as e:
            print(f"Failed to process {path.name}: {e}")
            
    # Save combined JSONL file
    jsonl_path = REFINED_DIR / "uidai_chunks_clean.jsonl"
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            
    print(f"Successfully refined {processed_count} out of {len(raw_files)} raw files.")
    print(f"Generated {len(all_chunks)} clean JSON chunks in {REFINED_DIR}")
    print(f"Combined JSONL available at: {jsonl_path}")

if __name__ == "__main__":
    run_refiner()
