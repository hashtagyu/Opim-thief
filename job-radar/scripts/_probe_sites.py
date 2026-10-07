import re, time, json, requests
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
Q = quote("AI 영상")
def get(u, **kw):
    time.sleep(1.5)
    try:
        return s.get(u, timeout=25, **kw)
    except Exception as e:
        print("  ERR", type(e).__name__, str(e)[:200], u); return None

print("##### JOBPLANET")
for p in ["q", "query", "keyword", "search", "keywords"]:
    r = get(f"https://www.jobplanet.co.kr/api/v3/job/postings?{p}={Q}&page=1&page_size=5")
    if r is None: continue
    try:
        d = r.json()["data"]; rec = d.get("recruits") or []
        print(" ", p, r.status_code, d.get("total_count"), [x.get("title") for x in rec[:3]])
    except Exception as e:
        print(" ", p, r.status_code, r.text[:200])
r = get(f"https://www.jobplanet.co.kr/api/v3/job/postings?q={Q}&page=1&page_size=1")
if r is not None:
    rec = r.json()["data"]["recruits"][0]
    print("  keys:", list(rec.keys()))
    print("  sample:", json.dumps(rec, ensure_ascii=False)[:1500])
r = get(f"https://www.jobplanet.co.kr/job/search?q={Q}")
if r is not None:
    for m in list(re.finditer(r"api/v\d/[\w/]+", r.text))[:10]: print("  apiref:", m.group(0))
    for sc in BeautifulSoup(r.text, "html.parser").find_all("script", src=True)[:30]:
        print("  script:", sc["src"][:150])

print("##### REMEMBER")
r = get("https://career.rememberapp.co.kr/job/postings")
if r is not None:
    srcs = [urljoin(r.url, sc["src"]) for sc in BeautifulSoup(r.text, "html.parser").find_all("script", src=True)]
    print("  scripts", len(srcs))
    hits = set()
    for u in srcs[:60]:
        rr = get(u)
        if rr is None: continue
        for m in re.finditer(r".{0,120}(job_postings|career-api|/search\b|jobPostings).{0,160}", rr.text):
            t = m.group(0)
            if t not in hits and ("http" in t or "/job" in t or "search" in t):
                hits.add(t)
                if len(hits) <= 25: print("  [js]", u.rsplit('/',1)[-1][:40], "::", t[:300])

print("##### MEDIAJOB")
r = get("https://www.mediajob.co.kr/")
if r is not None:
    soup = BeautifulSoup(r.text, "html.parser")
    for fm in soup.find_all("form")[:8]:
        print("  form", fm.get("action"), fm.get("method"), [(i.get("name"), i.get("type")) for i in fm.find_all(["input","select"])][:10])
    seen = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if re.search(r"\d{4,}", h) and h not in seen:
            seen.append(h)
    print("  digit links:", seen[:25])
    print("  onclick samples:", [a.get("onclick") for a in soup.find_all(attrs={"onclick": True})][:10])
r = get(f"https://www.mediajob.co.kr/search?keyword={Q}")
if r is not None: print("  search body:", re.sub(r"\s+"," ", r.text[:1500]))

print("##### SUPERINTERN")
for u in ["https://superintern.kr/", "http://www.superintern.kr/", "https://www.superintern.co.kr/", "https://superintern.co.kr/", "https://app.superintern.kr/"]:
    r = get(u)
    if r is not None:
        t = BeautifulSoup(r.text, "html.parser").title
        print("  ", r.status_code, r.url, len(r.text), t.get_text(strip=True)[:80] if t else "")
