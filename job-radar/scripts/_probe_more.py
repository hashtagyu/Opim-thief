import re, time, json, requests
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
Q = quote("AI 영상")
def get(u):
    time.sleep(1.5)
    try:
        return s.get(u, timeout=25)
    except Exception as e:
        print("===== ERR", type(e).__name__, str(e)[:150], u); return None
def show(u, pat=None, kw=("구인", "모집", "채용", "알바", "프리랜서", "의뢰", "프로젝트")):
    r = get(u)
    if r is None: return None
    soup = BeautifulSoup(r.text, "html.parser")
    print("=====", r.status_code, len(r.text), r.url, "|", (soup.title.get_text(strip=True) if soup.title else "")[:70])
    if r.status_code >= 400 or len(r.text) < 2500:
        print("  body:", re.sub(r"\s+", " ", r.text[:300]))
    seen, nav = [], []
    for a in soup.find_all("a", href=True):
        full = urljoin(r.url, a["href"]); t = a.get_text(" ", strip=True)[:50]
        if pat and re.search(pat, full) and full not in [x[0] for x in seen]:
            seen.append((full, t))
        elif any(k in t for k in kw) and len(nav) < 15 and full not in [x[0] for x in nav]:
            nav.append((full, t))
    if pat: print("  matches", len(seen), seen[:8])
    print("  nav:", nav[:15])
    for m in list(re.finditer(r"[\"'](/api/[\w/.-]+|https://[\w.-]*api[\w.-]*/[\w/.-]+)", r.text))[:8]:
        print("  api:", m.group(1))
    return r

print("##### FILMMAKERS")
show("https://www.filmmakers.co.kr/", r"filmmakers\.co\.kr/[a-zA-Z]+/\d+")
show("https://www.filmmakers.co.kr/staffRecruit", r"filmmakers\.co\.kr/staffRecruit/\d+")
show("https://www.filmmakers.co.kr/index.php?mid=staffRecruit&search_keyword=AI&search_target=title_content", r"/\d{6,}")
print("##### EDITMON")
r = show("https://editmon.com/work/employ_list.html", r"employ_view|employ_detail|idx=\d+|no=\d+")
if r is not None:
    a = BeautifulSoup(r.text, "html.parser").find("a", href=re.compile(r"employ_(view|detail)"))
    if a: print("  card:", re.sub(r"\s+", " ", str(a.find_parent(["li", "tr", "div"])))[:1200])
show("https://editmon.com/work/employ_list.html?keyword=" + quote("AI"), r"employ_(view|detail)")
print("##### ALBAMON")
show(f"https://www.albamon.com/total-search?keyword={Q}", r"albamon\.com/jobs/detail/\d+")
show(f"https://www.albamon.com/search?keyword={Q}", r"albamon\.com/jobs/detail/\d+")
print("##### ALBA CHEONGUK")
show(f"https://www.alba.co.kr/search/Search.asp?WsSrchKeyword={Q}", r"alba\.co\.kr/job/Detail|adid=\d+")
print("##### KMONG requests")
show("https://kmong.com/enterprise/requests", r"kmong\.com/enterprise/requests/\d+")
show(f"https://kmong.com/enterprise/requests?keyword={Q}", r"kmong\.com/enterprise/requests/\d+")
print("##### SUPEROOKIE")
show(f"https://www.superookie.com/jobs?keyword={Q}", r"superookie\.com/jobs/\w+")
print("##### WISHKET")
show(f"https://www.wishket.com/project/?q={Q}", r"wishket\.com/project/\d+")
print("##### JUNGLE")
show(f"https://www.jungle.co.kr/recruit?keyword={Q}", r"jungle\.co\.kr/recruit/\d+")
