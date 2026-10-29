import requests
import urllib3
import re

urllib3.disable_warnings()
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
url = "https://www.digilocker.gov.in/main.1eaa4539a59300525183.js"
resp = s.get(url, timeout=12, verify=False)
js = resp.text
json_files = set(re.findall(r'["\']([^"\']+\.json[^"\']*)["\']', js))
print("JSON assets found:", [f for f in json_files if "asset" in f or "i18n" in f or "faq" in f])

# Search for FAQ texts in js
faq_matches = re.findall(r'(\bWhat is DigiLocker\b[^"\'}{]+)', js, re.I)
print("FAQ snippets:", faq_matches[:3])
