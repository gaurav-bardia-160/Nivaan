import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
r = s.get("https://www.myscheme.gov.in", timeout=10, verify=False)
soup = BeautifulSoup(r.text, "html.parser")
scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
print("Scripts found:", scripts[:10])
