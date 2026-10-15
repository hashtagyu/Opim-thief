import re, time, json, requests
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
csns = {"블루개러지": "ZDgyeUcwaEtza2VRZm1MUTUzTXdZZz09", "143엔터": "d243YWJSRmtZS3JZeFRVbGw1dnpOZz09", "거상코리아": "czNaYUJtU1pYUVBEM3lZc3dFUnlnZz09"}
# 대기업 하나: 사람인 기업검색으로 csn 얻기
time.sleep(2)
r = s.get("https://www.saramin.co.kr/zf_user/search/company?searchType=search&searchword=" + requests.utils.quote("CJ ENM"), timeout=30)
m = re.search(r"company-info/view[^\"']*csn=([^&\"']+)", r.text)
if m: csns["CJ ENM?"] = m.group(1)
for name, csn in csns.items():
    time.sleep(2)
    r = s.get(f"https://www.saramin.co.kr/zf_user/company-info/view?csn={csn}", timeout=30)
    h = r.text; soup = BeautifulSoup(h, "html.parser")
    print("=====", name, r.status_code, len(h))
    for sc in soup.find_all("script", type="application/ld+json"):
        t = sc.string or ""
        if "Organization" in t: print("  LD:", re.sub(r"\s+"," ",t)[:700])
    summ = soup.select(".company_summary .company_summary_item, .company_summary li, dl.company_summary")
    print("  summary items:", [re.sub(r"\s+"," ",x.get_text(" ",strip=True))[:60] for x in summ][:12])
    txt = re.sub(r"\s+", " ", soup.get_text(" "))
    for kw in ["기업형태", "기업규모", "매출액", "사원수", "업력"]:
        i = txt.find(kw)
        if i >= 0: print(f"  [{kw}]", txt[max(0,i-20):i+80])
    for m in list(re.finditer(r"(?i)(sales|revenue|매출)[\w\"']{0,20}\s*[:=]\s*[\[{][^;]{0,400}", h))[:4]:
        print("  [js]", re.sub(r"\s+"," ",m.group(0))[:400])
    for m in list(re.finditer(r"set\w*Chart\(\{[^;]{0,300}", h))[:4]:
        print("  [chart]", re.sub(r"\s+"," ",m.group(0))[:300])
