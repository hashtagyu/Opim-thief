import re, time, requests
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
for name, csn in {"블루개러지": "ZDgyeUcwaEtza2VRZm1MUTUzTXdZZz09", "CJENM": "Wi9wdU5ZaDZXQUVIQjFNdlZRYjkwdz09"}.items():
    time.sleep(2)
    h = s.get(f"https://www.saramin.co.kr/zf_user/company-info/view-inner-finance?csn={csn}", timeout=30).text
    soup = BeautifulSoup(h, "html.parser")
    print("=====", name)
    for sc in soup.find_all("script"):
        t = sc.string or ""
        if re.search(r"20[12]\d", t) and re.search(r"(?i)sales|매출|revenue|finance|chart", t) and "gtag" not in t:
            i = max(t.lower().find("sales"), t.find("매출"), t.lower().find("chart"))
            print("  [script]", re.sub(r"\s+", " ", t[max(0, i-200):i+900]))
    for tb in soup.find_all(["table", "dl"]):
        tx = re.sub(r"\s+", " ", tb.get_text(" ", strip=True))
        if "매출" in tx: print("  [table]", tx[:500])
    sec = soup.find(id=re.compile("finance|sales", re.I)) or soup.find(class_=re.compile("finance|sales", re.I))
    if sec: print("  [section]", re.sub(r"\s+", " ", sec.get_text(" ", strip=True))[:800])
    tx = re.sub(r"\s+", " ", soup.get_text(" "))
    for m in list(re.finditer(r"매출액", tx))[:8]: print("  [text]", tx[max(0, m.start()-80):m.start()+150])
