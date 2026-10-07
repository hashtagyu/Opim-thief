import re, time, requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
urls = [
 "https://www.jobkorea.co.kr/Recruit/Co_Read/C/35809179",
 "https://www.jobkorea.co.kr/company/35809179/Salary",
 "https://www.saramin.co.kr/zf_user/company-info/view-inner-salary?csn=ZDgyeUcwaEtza2VRZm1MUTUzTXdZZz09",
 "https://www.saramin.co.kr/zf_user/company-info/view?csn=ZDgyeUcwaEtza2VRZm1MUTUzTXdZZz09",
 "https://www.jobkorea.co.kr/Recruit/Co_Read/C/35809179",
 "https://www.jobkorea.co.kr/Recruit/Co_Read/C/33958138",
]
for u in urls:
    time.sleep(3)
    try:
        r = s.get(u, timeout=30)
    except Exception as e:
        print("=====", "ERR", type(e).__name__, u); continue
    h = r.text
    print("=====", r.status_code, len(h), u)
    for m in list(re.finditer(r"평균\s*연봉", h))[:6]:
        print("  [평균연봉]", re.sub(r"\s+", " ", h[max(0, m.start()-200):m.end()+300]))
    for m in list(re.finditer(r"[0-9][0-9,]{2,6}\s*만\s*원", h))[:8]:
        print("  [만원]", re.sub(r"\s+", " ", h[max(0, m.start()-150):m.end()+40]))
    for m in list(re.finditer(r"(?i)avg_?sal|averageSalary|avgSalary|salary\w*\"?\s*[:=]", h))[:6]:
        print("  [key]", re.sub(r"\s+", " ", h[max(0, m.start()-80):m.end()+120]))
    soup = BeautifulSoup(h, "html.parser")
    seen = set()
    for a in soup.find_all("a", href=True):
        t = a.get_text(" ", strip=True)
        if ("연봉" in t or "salary" in a["href"].lower() or "Salary" in a["href"]) and a["href"] not in seen:
            seen.add(a["href"]); print("  [link]", t[:30], urljoin(u, a["href"]))
    for sc in soup.find_all("script", src=False):
        txt = sc.string or ""
        if "연봉" in txt or "salary" in txt.lower():
            i = txt.lower().find("salary"); i = i if i >= 0 else txt.find("연봉")
            print("  [script]", re.sub(r"\s+", " ", txt[max(0, i-200):i+300]))
            break
