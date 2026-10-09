import glob
import os

# 1. Delete low-value pages
low_value_keywords = ['archive', 'media', 'video', 'sitemap', 'career', 'regional', 'dashboard', 'contact', 'hi/']
files = glob.glob('backend/data/raw/spider_*.txt')

deleted_count = 0
cleaned_count = 0

boilerplate = [
    "Mobile menu toggle", "JavaScript must be enabled", "UIDAl website translation",
    "Ask Me Anything!!", "Screen Reader", "Language selection", 
    "Footer background", "Menu icon", "Open external website",
    "Hindi (हिन्दी)", "English", "Search Services", "Skip to Main Content"
]

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        
    if not lines:
        continue
        
    url_line = lines[0].lower()
    
    # Check if URL matches a low-value page
    if any(k in url_line for k in low_value_keywords):
        os.remove(f)
        deleted_count += 1
        continue
        
    # Clean the boilerplate
    cleaned = []
    exact_skip_keywords = ["Home", "More", "Media", "Documents", "Help", "English"]
    
    for line in lines:
        line_clean = line.strip()
        import re
        text_only = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line_clean).strip()
        text_only = re.sub(r'^[#*\- ]+', '', text_only).strip()
        
        if any(b.lower() in line.lower() for b in boilerplate):
            continue
        if any(k.lower() == text_only.lower() for k in exact_skip_keywords):
            continue
            
        # Also skip empty lines that are just whitespace
        if not line.strip():
            # keep one empty line but not multiple
            if not cleaned or cleaned[-1].strip():
                cleaned.append(line)
        else:
            cleaned.append(line)
            
    if len(cleaned) != len(lines):
        with open(f, 'w', encoding='utf-8') as file:
            file.writelines(cleaned)
        cleaned_count += 1

print(f"Deleted {deleted_count} low-value files.")
print(f"Cleaned boilerplate from {cleaned_count} files.")
