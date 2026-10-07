import re, time, json, requests
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
def req(m, u, **kw):
    time.sleep(1.5)
    try:
        return s.request(m, u, timeout=25, **kw)
    except Exception as e:
        print("  ERR", type(e).__name__, str(e)[:200], u); return None

print("##### REMEMBER")
H = {"Origin": "https://career.rememberapp.co.kr", "Referer": "https://career.rememberapp.co.kr/", "Accept": "application/json", "Content-Type": "application/json"}
bodies = [
 {"search": {"keywords": ["AI 영상"]}, "page": 1, "per": 20},
 {"search": {"keyword": "AI 영상"}, "page": 1, "per": 20},
 {"keyword": "AI 영상", "page": 1, "per": 20},
 {"search": {"query": "AI 영상"}, "page": 1, "per": 20},
 {"page": 1, "per": 5},
]
for b in bodies:
    r = req("POST", "https://career-api.rememberapp.co.kr/job_postings/search", json=b, headers=H)
    if r is None: continue
    print(" body", json.dumps(b, ensure_ascii=False), "->", r.status_code, re.sub(r"\s+", " ", r.text[:700]))
r = req("GET", "https://career.rememberapp.co.kr/job/postings?search=%7B%22keywords%22%3A%5B%22AI%20%EC%98%81%EC%83%81%22%5D%7D")
if r is not None:
    for m in list(re.finditer(r"/job/posting/\d+", r.text))[:5]: print("  link", m.group(0))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if m:
        t = m.group(1); i = t.find("jobPosting"); print("  next:", t[max(0,i-100):i+800])

print("##### MEDIAJOB")
for u in ["https://www.mediajob.co.kr/search/search.htm?search=" + quote("AI 영상"),
          "https://www.mediajob.co.kr/search/search.htm?search=" + quote("AI")]:
    r = req("GET", u)
    if r is None: continue
    soup = BeautifulSoup(r.text, "html.parser")
    print("=====", r.status_code, len(r.text), u, (soup.title.get_text(strip=True) if soup.title else ""))
    links = []
    for a in soup.find_all("a", href=True):
        full = urljoin(u, a["href"])
        if "rec_idx=" in full and full not in [l[0] for l in links]:
            links.append((full, a.get_text(" ", strip=True)[:60]))
    print("  rec links", len(links), links[:8])
    if links:
        a = soup.find("a", href=re.compile("rec_idx="))
        box = a.find_parent(["li", "tr"]) or a.parent
        print("  card html:", re.sub(r"\s+", " ", str(box))[:1500])
r = req("GET", "https://www.mediajob.co.kr/recruit/recruit.htm?cmd=view&rec_idx=326314")
if r is not None:
    soup = BeautifulSoup(r.text, "html.parser")
    print("  detail", r.status_code, len(r.text), soup.title.get_text(strip=True) if soup.title else "")
    print("  og:", [(m.get("property"), (m.get("content") or "")[:120]) for m in soup.find_all("meta", property=True)][:6])
    print("  ld:", "ld+json" in r.text, " iframe:", [i.get("src") for i in soup.find_all("iframe")][:5])
    print("  text:", re.sub(r"\s+", " ", soup.get_text(" "))[:800])

print("##### JOBPLANET detail")
for u in ["https://www.jobplanet.co.kr/api/v1/job/postings/1714385", "https://www.jobplanet.co.kr/api/v3/job/postings/1714385",
          "https://www.jobplanet.co.kr/job/search?posting_ids%5B%5D=1714385"]:
    r = req("GET", u)
    if r is None: continue
    print(" ", r.status_code, len(r.text), r.headers.get("content-type"), u, re.sub(r"\s+", " ", r.text[:300]) if "json" in (r.headers.get("content-type") or "") else "")
