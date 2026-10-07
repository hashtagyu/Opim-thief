import re, time, requests, sys
from urllib.parse import quote
sys.path.insert(0, "job-radar/scripts")
import rules
from bs4 import BeautifulSoup
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
TARGET = "55151858"
for term in ["AI 영상", "AI 크리에이터", "생성형 AI 영상", "AI 콘텐츠 제작"]:
    for sort in ["reg_dt", "relation"]:
        for page in [1, 2, 3]:
            time.sleep(2)
            u = (f"https://www.saramin.co.kr/zf_user/search/recruit?searchType=search&recruitSort={sort}"
                 f"&recruitPageCount=40&recruitPage={page}&searchword={quote(term)}")
            try:
                r = s.get(u, timeout=30)
            except Exception as e:
                print(term, sort, page, "ERR", e); continue
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("div.item_recruit")
            ids = [re.search(r"rec_idx=(\d+)", (it.select_one("h2.job_tit a") or {}).get("href", "") or "") for it in items]
            ids = [m.group(1) for m in ids if m]
            total = soup.select_one(".cnt_result")
            dates = [x.get_text(strip=True) for x in soup.select("div.job_date .job_day")][-1:]
            print(f"{term} | {sort} p{page}: {len(ids)} items, target={'YES' if TARGET in ids else 'no'}, total={total.get_text(strip=True) if total else '?'} last={dates}")
time.sleep(2)
r = s.get(f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={TARGET}&rec_seq=0", timeout=30)
body = re.sub(r"\s+", " ", BeautifulSoup(r.text, "html.parser").get_text(" "))
title = "AI 영상 제작의 새로운 기준을 함께 만들 크리에이터를 찾습니다"
print("detail len", len(body))
print("tools", rules.find_tools(title + " " + body))
print("exclusion", rules.exclusion_reason(title, "(주)줄라이하우스", "", body))
print("relevant", rules.is_relevant(title, body, rules.find_tools(title + " " + body)))
for m in list(re.finditer(r".{0,30}(광고|마케팅|뷰티|커머스|병원).{0,30}", body))[:6]: print("  ctx:", m.group(0))
