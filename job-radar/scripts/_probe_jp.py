import re, time, json, requests
from urllib.parse import quote
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Accept": "application/json, text/plain, */*"})
for name in ["포자랩스", "디지털아이디어"]:
    q = quote(name)
    for u in [f"https://www.jobplanet.co.kr/api/v3/companies/search?query={q}",
              f"https://www.jobplanet.co.kr/api/v1/companies/search?query={q}",
              f"https://www.jobplanet.co.kr/api/v3/search/companies?query={q}",
              f"https://www.jobplanet.co.kr/api/v1/search/autocomplete?query={q}",
              f"https://www.jobplanet.co.kr/api/v3/search/autocomplete?query={q}",
              f"https://www.jobplanet.co.kr/api/v5/search/autocomplete?term={q}",
              f"https://www.jobplanet.co.kr/autocomplete/autocomplete/suggest.json?term={q}",
              f"https://www.jobplanet.co.kr/search/companies?query={q}",
              f"https://www.jobplanet.co.kr/search?query={q}"]:
        time.sleep(1.5)
        try:
            r = s.get(u, timeout=20)
        except Exception as e:
            print("ERR", u, e); continue
        ct = r.headers.get("content-type", "")
        t = r.text
        print("==", r.status_code, len(t), ct[:30], u)
        if "json" in ct:
            print("   ", re.sub(r"\s+", " ", t[:700]))
        else:
            for m in list(re.finditer(r"/companies/(\d+)[^\"']{0,60}", t))[:4]:
                print("    link", m.group(0)[:100])
            for m in list(re.finditer(r"(rate_total|grade|평점|review_avg|star)[^<]{0,80}", t))[:4]:
                print("    grade?", m.group(0)[:120])
time.sleep(1.5)
r = s.get("https://www.jobplanet.co.kr/companies/117/reviews", timeout=20)
print("== company page", r.status_code, len(r.text))
for m in list(re.finditer(r'(ratingValue|rate_point|grade)[^<]{0,120}', r.text))[:6]:
    print("   ", m.group(0)[:160])
