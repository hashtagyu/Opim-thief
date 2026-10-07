import re, time, json, requests
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
Q = quote("AI 영상")
urls = [
 f"https://www.jobplanet.co.kr/job/search?q={Q}",
 f"https://www.jobplanet.co.kr/api/v3/job/postings?q={Q}&page=1&page_size=20",
 f"https://www.jobplanet.co.kr/api/v5/job/postings/search?query={Q}&page=1&page_size=20",
 f"https://career.rememberapp.co.kr/job/postings?search={Q}",
 "https://career.rememberapp.co.kr/job/postings",
 "https://www.mediajob.co.kr/",
 f"https://www.mediajob.co.kr/search?keyword={Q}",
 f"https://www.mediajob.co.kr/recruit/search?keyword={Q}",
 "https://www.superintern.kr/",
 f"https://www.superintern.kr/search?keyword={Q}",
 f"https://www.wanted.co.kr/wdlist?query={Q}",
 "https://www.wanted.co.kr/sitemap.xml",
]
JOBLIKE = re.compile(r"/(job|jobs|posting|postings|recruit|position|positions|wd|notice|hire|career)s?/[\w%-]*\d", re.I)
for u in urls:
    time.sleep(2)
    try:
        r = s.get(u, timeout=25)
    except Exception as e:
        print("=====", "ERR", type(e).__name__, u); continue
    h = r.text
    print("=====", r.status_code, len(h), r.headers.get("content-type"), u)
    soup = BeautifulSoup(h, "html.parser")
    print("  title:", (soup.title.get_text(strip=True) if soup.title else "")[:100])
    links = []
    for a in soup.find_all("a", href=True):
        full = urljoin(u, a["href"])
        if JOBLIKE.search(full) and full not in links:
            links.append(full)
    print("  joblinks:", len(links), links[:6])
    if "__NEXT_DATA__" in h:
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
        print("  NEXT_DATA len", len(m.group(1)) if m else 0, (m.group(1)[:400] if m else ""))
    apis = sorted(set(re.findall(r"https?://[\w.-]*(?:api|gateway)[\w.-]*\.[a-z]{2,}[\w/.-]*", h)))[:10]
    print("  api-ish:", apis)
    apis2 = sorted(set(re.findall(r"[\"'](/api/[\w/.-]+)", h)))[:15]
    print("  /api paths:", apis2)
    if "json" in (r.headers.get("content-type") or ""):
        print("  json:", h[:600])
    if r.status_code >= 400 or len(h) < 3000:
        print("  body:", re.sub(r"\s+", " ", h[:400]))
