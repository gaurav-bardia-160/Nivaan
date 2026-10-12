import os
import glob
import re
import json
import argparse
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
REFINED_DIR = BASE_DIR / "data" / "refined"

def clean_markdown(md: str, source_name: str) -> str:
    lines = md.split('\n')
    cleaned = []
    
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
        "Aadhaar Mitra", "Grievance Redressal", "Follow Us On",
        "Guided Tour", "Department Officials", "IRS Officers Online", "Official Email Systems",
        "Employees Corner", "Take Online Oath", "Accessibility Options", "Font Size",
        "Saturation", "High Contrast Theme", "Basic HTML View", "Invert Colors", "Language Options",
        "Quick Access International Taxation", "Organizations and Functions", "Taxpayers",
        "Tax Laws & Rules", "Media Gallery", "Advanced Search",
        "IT Bill Comparison Tool", "Compare Income-tax Act 1961 with Income-tax Act 2025",
        "Upload FilesSelect from CatalogEnter URLs", "Compare sections first to enable export",
        "Select sections from both Acts and click",
        "For reference purposes only", "Public Awareness", "Report Phishing", "Children's Corner", "Useful Links",
        "Subscribe - Newsletter", "Subscribe - Tax Feeds", "e-Governance",
        "This site is best viewed in", "Copyright Income Tax Department",
        "Show More", "Act, 1961", "Act, 2025", "Acts", "Rules", "Circulars", "Notifications",
        "Orders & Instructions", "Forms/Downloads", "Budget & Bills", "Finance Acts", "Finance Bills"
    ]
    
    exact_skip_keywords = [
        "Home", "More", "Media", "Documents", "Help", "English", "Facebook", "Twitter",
        "YouTube", "Instagram", "LinkedIn", "Koo", "Login", "Register", "e-Filing",
        "Close", "Hidden", "Compare", "Drop file here orChoose File", "etds-htmletds-pdf",
        "Tax e-Services"
    ]
    
    for line in lines:
        line_clean = line.strip()
        # Remove markdown link syntax for exact matching, e.g. [Home](...) -> Home
        text_only = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line_clean).strip()
        text_only = re.sub(r'^[#*\- 0-9\.]+', '', text_only).strip()
        
        if any(k.lower() in line.lower() for k in skip_keywords):
            continue
        if any(k.lower() == text_only.lower() for k in exact_skip_keywords):
            continue
        cleaned.append(line)
        
    text = '\n'.join(cleaned).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def extract_tags(text: str, source_name: str) -> list:
    tags = []
    text_lower = text.lower()
    if source_name == "uidai":
        keywords = ["aadhaar", "update", "mobile", "fee", "download", "biometric", "authentication", "enrolment", "pan", "status", "lock", "unlock", "pvc"]
    elif source_name == "pan":
        keywords = ["pan", "apply", "form 49a", "form 49aa", "nsdl", "protean", "utiitsl", "reprint", "correction", "minor", "nri", "tatkal", "eproof", "ao code", "e-pan", "kyc", "instant", "verification", "aadhaar_link", "fee"]
    else:
        keywords = [source_name]
        
    for kw in keywords:
        if kw in text_lower:
            tags.append(kw)
            
    if not tags:
        tags = [f"{source_name}_service"]
    return sorted(list(set(tags)))

def chunk_and_save(doc_id: str, title: str, url: str, cleaned_text: str, chunks_list: list, source_name: str, refined_dir: Path, global_refined_dir: Path):
    # Strip image markdowns
    cleaned_text = re.sub(r'!\[.*?\]\(.*?\)', '', cleaned_text)
    
    # Chunk by markdown headings (## or #)
    raw_pieces = re.split(r'\n(?=#+ )', cleaned_text)
    
    # 1. Merge tiny pieces
    merged_pieces = []
    current_piece = ""
    for piece in raw_pieces:
        piece = piece.strip()
        if not piece:
            continue
        
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
            lines = piece.split('\n')
            temp_chunk = ""
            for line in lines:
                sentences = re.split(r'(?<=\.)\s+', line)
                for sentence in sentences:
                    if len((temp_chunk + " " + sentence).split()) > 400 and temp_chunk:
                        final_chunks.append(temp_chunk.strip())
                        temp_chunk = sentence
                    else:
                        temp_chunk += " " + sentence if temp_chunk else sentence
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
        for line in lines:
            line_clean = re.sub(r'!\[.*?\]\(.*?\)', '', line).strip('# ').strip()
            if line_clean:
                section = line_clean
                break
            
        chunk_id = f"{doc_id}_chunk_{i+1}"
        draft = {
            "id": chunk_id,
            "source_url": url,
            "title": title,
            "section": section,
            "text": chunk_text,
            "category": source_name,
            "last_verified": date.today().isoformat(),
            "status": "unverified",
            "quality_score": 0.85,
            "source_confidence": "official",
            "verification_method": "automated_official_source",
            "retrieval_tags": extract_tags(chunk_text, source_name)
        }
        
        # Save individual JSON chunk to both refined/{source_name}/ and refined/
        json_content = json.dumps(draft, indent=2, ensure_ascii=False) + "\n"
        (refined_dir / f"{chunk_id}.json").write_text(json_content, encoding="utf-8")
        (global_refined_dir / f"{chunk_id}.json").write_text(json_content, encoding="utf-8")
        chunks_list.append(draft)

def run_refiner(source_name: str = "pan"):
    raw_source_dir = RAW_DIR / source_name
    refined_source_dir = REFINED_DIR / source_name
    
    refined_source_dir.mkdir(parents=True, exist_ok=True)
    REFINED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Clean previous chunks for this source
    for old_file in refined_source_dir.glob("*.json"):
        old_file.unlink()
        
    # Collect raw files from raw/{source_name}/ or raw/ matching the domain
    raw_files = []
    if raw_source_dir.exists():
        raw_files = list(raw_source_dir.glob("*.txt"))
        
    if not raw_files:
        # Fallback to search in RAW_DIR directly
        if source_name == "pan":
            raw_files = list(RAW_DIR.glob("*incometaxindia*.txt"))
        elif source_name == "uidai":
            raw_files = list(RAW_DIR.glob("*uidai*.txt"))
        else:
            raw_files = list(RAW_DIR.glob("*.txt"))

    if not raw_files:
        print(f"No text files found for source '{source_name}'.")
        return
        
    processed_count = 0
    all_chunks = []
    
    for path in raw_files:
        try:
            content = path.read_text(encoding="utf-8")
            
            lines = content.split('\n')
            url = ""
            if lines and lines[0].startswith("URL: "):
                url = lines[0].replace("URL: ", "").strip()
                content = '\n'.join(lines[1:])
            
            cleaned_content = clean_markdown(content, source_name)
            
            if len(cleaned_content.strip()) > 50:
                doc_id = path.stem
                
                # Extract real page title instead of file-hash
                title = doc_id
                for line in cleaned_content.split('\n'):
                    line_clean = re.sub(r'!\[.*?\]\(.*?\)', '', line).strip()
                    if line_clean and not line_clean.startswith('#'):
                        title = line_clean
                        break
                    elif line_clean.startswith('#'):
                        title = line_clean.strip('# ').strip()
                        break
                        
                chunk_and_save(doc_id, title, url, cleaned_content, all_chunks, source_name, refined_source_dir, REFINED_DIR)
                processed_count += 1
                
        except Exception as e:
            print(f"Failed to process {path.name}: {e}")
            
    # Save combined JSONL file to both refined/{source_name}/ and refined/
    jsonl_filename = f"{source_name}_chunks_clean.jsonl"
    jsonl_path = refined_source_dir / jsonl_filename
    global_jsonl_path = REFINED_DIR / jsonl_filename
    
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            
    with open(global_jsonl_path, 'w', encoding='utf-8') as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            
    print(f"Successfully refined {processed_count} out of {len(raw_files)} raw files.")
    print(f"Generated {len(all_chunks)} clean JSON chunks.")
    print(f"Source JSONL available at: {jsonl_path}")
    print(f"Global JSONL available at: {global_jsonl_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="pan")
    args = parser.parse_args()
    run_refiner(args.source)
