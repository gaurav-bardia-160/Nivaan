import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit

urllib3.disable_warnings()
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
r = s.get("https://india.gov.in", timeout=12, verify=False)
soup = BeautifulSoup(r.text, "html.parser")
links = set()
for a in soup.find_all("a", href=True):
    href = a.get("href")
    text = " ".join(a.get_text().split())
    abs_url = urljoin("https://india.gov.in", href)
    if "india.gov.in" in abs_url and not any(abs_url.endswith(x) for x in [".pdf", ".jpg", ".png"]):
        links.add((abs_url, text))

print(f"Total internal citizen links on india.gov.in homepage: {len(links)}")
for url, text in sorted(links)[:25]:
    if text:
        print(f"  {url} -> {text[:50]}")
