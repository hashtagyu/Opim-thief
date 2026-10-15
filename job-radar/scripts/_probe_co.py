import re, time, requests
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
csns = {"블루개러지": "ZDgyeUcwaEtza2VRZm1MUTUzTXdZZz09", "143엔터": "d243YWJSRmtZS3JZeFRVbGw1dnpOZz09", "CJENM": "Wi9wdU5ZaDZXQUVIQjFNdlZRYjkwdz09"}
for name, csn in csns.items():
    time.sleep(2)
    r = s.get(f"https://www.saramin.co.kr/zf_user/company-info/view?csn={csn}", timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    links = sorted(set(a["href"] for a in soup.find_all("a", href=True) if "company-info/view-inner" in a["href"]))
    print("=====", name, "tabs:", links[:12])
    box = soup.select_one(".company_summary")
    if box: print("  summary html:", re.sub(r"\s+"," ",str(box))[:1500])
    for tab in ["view-inner-finance", "view-inner-financial", "view-inner-company-finance"]:
        time.sleep(2)
        rr = s.get(f"https://www.saramin.co.kr/zf_user/company-info/{tab}?csn={csn}", timeout=30)
        print("  ", tab, rr.status_code, len(rr.text))
        if rr.status_code == 200 and len(rr.text) > 5000:
            h = rr.text
            for m in list(re.finditer(r"매출[^<]{0,200}", h))[:5]: print("     [매출]", re.sub(r"\s+"," ",m.group(0))[:200])
            for m in list(re.finditer(r"(?i)set\w*Chart\(\{.{0,600}", h))[:4]: print("     [chart]", re.sub(r"\s+"," ",m.group(0))[:600])
            for m in list(re.finditer(r"(?i)\"(sales|revenue)\w*\"\s*:\s*.{0,300}", h))[:4]: print("     [json]", re.sub(r"\s+"," ",m.group(0))[:300])
            break
