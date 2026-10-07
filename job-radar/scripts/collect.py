"""AI 아티스트 잡 레이더 수집기 (GitHub Actions용).

순수 Python + requests + BeautifulSoup. LLM 호출·API 키 없음.
사이트 하나가 막히거나 실패해도 나머지는 계속 돌고, 실패한 사이트의 기존 데이터는 그대로 둔다.
로그인·캡차 우회, 프록시 돌려쓰기는 하지 않는다. 막히면 막힌 걸로 기록만 한다.

실행: python job-radar/scripts/collect.py
환경변수: RADAR_SOURCES=saramin,wanted (일부만), RADAR_DEBUG=1 (응답 앞부분 로그)
"""
import json
import os
import random
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules  # noqa: E402

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JOBS_FILE = DATA / "jobs.json"
STATUS_FILE = DATA / "status.json"
COMPANIES_FILE = DATA / "companies.json"  # 회사별 평균연봉 캐시
SALARY_REFRESH_DAYS = 30

STALE_DAYS = 7
MAX_DETAILS_PER_SOURCE = 30
SITE_BUDGET_SEC = int(os.environ.get("RADAR_SITE_BUDGET", "600"))  # 사이트당 최대 10분
DELAY = (1.5, 3.0)
DEBUG = os.environ.get("RADAR_DEBUG") == "1"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)


class Blocked(Exception):
    """403/429, 캡차, 봇 차단 페이지."""


class OutOfTime(Exception):
    """사이트별 시간 예산 초과. 그때까지 모은 결과는 쓴다."""


def now_kst():
    return datetime.now(KST).replace(microsecond=0)


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- HTTP

class Fetcher:
    def __init__(self, name):
        self.name = name
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.requests = 0
        self.errors = []
        self.blocked = 0
        self.deadline = time.time() + SITE_BUDGET_SEC
        self.out_of_time = False

    def get(self, url, accept=None, referer=None):
        if time.time() > self.deadline:
            self.out_of_time = True
            raise OutOfTime()
        time.sleep(random.uniform(*DELAY))
        headers = {}
        if accept:
            headers["Accept"] = accept
        if referer:
            headers["Referer"] = referer
        self.requests += 1
        try:
            r = self.s.get(url, headers=headers, timeout=15)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(8)  # 잠깐 쉬고 한 번만 다시 (일시적 끊김 대비)
            r = self.s.get(url, headers=headers, timeout=20)
        body_head = r.text[:3000].lower() if r.text else ""
        if DEBUG:
            log(f"  [{self.name}] {r.status_code} {len(r.content)}B {url}")
        if r.status_code in (401, 403, 429) or (
            r.status_code == 503 and ("cloudflare" in body_head or "captcha" in body_head)
        ):
            self.blocked += 1
            raise Blocked(f"HTTP {r.status_code}")
        if any(k in body_head for k in ("cf-challenge", "challenge-platform", "captcha", "are you a robot",
                                         "access denied", "자동입력 방지", "비정상적인 접근")):
            # 페이지 안에 captcha 글자가 들어간 정상 페이지도 있어서 짧은 페이지만 차단으로 본다
            if len(r.content) < 60000:
                self.blocked += 1
                raise Blocked("bot challenge page")
        r.raise_for_status()
        return r

    def html(self, url, **kw):
        return BeautifulSoup(self.get(url, **kw).text, "html.parser")

    def json(self, url, **kw):
        return self.get(url, accept="application/json, text/plain, */*", **kw).json()


# ---------------------------------------------------------------- 파싱 도우미

def clean(text, limit=None):
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(" ") if "<" in text else text
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def make_summary(body):
    return clean(body, 220)


def to_date(value):
    """여러 형식의 날짜 문자열 -> YYYY-MM-DD (모르면 원문/None)."""
    if not value:
        return None
    value = str(value).strip()
    m = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", value)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
        except ValueError:
            return None
        if d - now_kst() > timedelta(days=300):  # 상시채용을 1년 뒤 날짜로 넣는 사이트가 있다
            return "상시"
        return d.strftime("%Y-%m-%d")
    m = re.search(r"(?<!\d)(\d{1,2})[/.](\d{1,2})(?!\d)", value)
    if m:
        today = now_kst().date()
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            y = today.year + (1 if mo < today.month - 6 else 0)
            return f"{y:04d}-{mo:02d}-{d:02d}"
    if re.search(r"상시|채용시|수시|always|open", value, re.I):
        return "상시"
    return None


EMPLOYMENT_MAP = {
    "FULL_TIME": "정규직", "PART_TIME": "파트타임", "CONTRACTOR": "계약직", "CONTRACT": "계약직",
    "TEMPORARY": "계약직", "INTERN": "인턴", "VOLUNTEER": "기타", "PER_DIEM": "일용직", "OTHER": "기타",
    "Full-time": "정규직", "Part-time": "파트타임", "Contract": "계약직", "Internship": "인턴",
    "Temporary": "계약직", "Freelance": "프리랜서",
}


def norm_employment(v):
    if not v:
        return ""
    if isinstance(v, list):
        return ", ".join(dict.fromkeys(norm_employment(x) for x in v if x))
    v = str(v).strip()
    return EMPLOYMENT_MAP.get(v, EMPLOYMENT_MAP.get(v.upper(), v))


def jsonld_jobposting(soup):
    """상세 페이지의 schema.org JobPosting(JSON-LD)을 찾아서 dict로."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return d
                stack.extend(v for v in d.values() if isinstance(v, (list, dict)))
    return None


def location_from_ld(ld):
    locs = ld.get("jobLocation")
    if not locs:
        return ""
    if isinstance(locs, dict):
        locs = [locs]
    out = []
    for loc in locs:
        addr = (loc or {}).get("address") if isinstance(loc, dict) else None
        if isinstance(addr, dict):
            parts = [addr.get("addressRegion"), addr.get("addressLocality")]
            s = " ".join(p for p in parts if p) or addr.get("streetAddress") or ""
        else:
            s = str(addr or "")
        if s:
            out.append(clean(s))
    return ", ".join(dict.fromkeys(out))


def meta(soup, *names):
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


COMPANY_LINK = re.compile(
    r"https://www\.saramin\.co\.kr/zf_user/company-info/view[^\"'#]*csn=[^&\"'#]+"
    r"|https://www\.jobkorea\.co\.kr/(?:Recruit/Co_Read/C/[^?\"'#]+|company/\d+)"
)


def company_link(soup, base):
    """공고 페이지에서 사람인/잡코리아 기업정보 페이지 링크를 찾는다."""
    for a in soup.find_all("a", href=True):
        m = COMPANY_LINK.search(urljoin(base, a["href"]))
        if m:
            return m.group(0)
    return None


def salary_from_ld(ld):
    """JSON-LD baseSalary -> '연 3,600~4,200만원' 같은 문자열 (숫자가 있을 때만)."""
    bs = ld.get("baseSalary") if ld else None
    if not isinstance(bs, dict):
        return ""
    v = bs.get("value") if isinstance(bs.get("value"), dict) else bs
    lo, hi = v.get("minValue"), v.get("maxValue")
    if lo is None and hi is None:
        lo = v.get("value") if not isinstance(v.get("value"), dict) else None
    unit = str(v.get("unitText") or bs.get("unitText") or "YEAR").upper()

    def man(x):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return None
        if x <= 0:
            return None
        if unit == "MONTH":
            x *= 12
        elif unit == "HOUR":
            return None
        return int(round(x / 10000)) if x > 100000 else int(x)

    lo, hi = man(lo), man(hi)
    if not lo and not hi:
        return ""
    if lo and hi and lo != hi:
        return f"연 {lo:,}~{hi:,}만원"
    return f"연 {(lo or hi):,}만원"


def company_key(name):
    n = re.sub(r"\(.*?\)|㈜|주식회사|\(주\)|\(유\)|유한회사|corporation|corp\.?|inc\.?|co\.,?\s*ltd\.?|ltd\.?",
               "", name or "", flags=re.I)
    return re.sub(r"[\s·.,\-_]", "", n).lower()


SALARY_META = re.compile(r"평균\s*연봉\s*:?\s*([0-9][0-9,]{2,6})\s*만\s*원")
SALARY_VERSION = 2  # 조회 방식이 바뀌면 올려서 캐시를 다시 채운다


def saramin_csn(url):
    m = re.search(r"csn[=/]([^&/?#]+)", url or "")
    return m.group(1) if m else None


def find_saramin_csn(f, name):
    """사람인 기업 검색에서 이름이 정확히 같은 회사의 csn."""
    key = company_key(name)
    if not key:
        return None
    soup = f.html(f"https://www.saramin.co.kr/zf_user/search/company?searchType=search&searchword={quote(name)}")
    for a in soup.find_all("a", href=True):
        csn = saramin_csn(a["href"]) if "company-info" in a["href"] else None
        if not csn:
            continue
        if any(company_key(clean(x)) == key for x in (a.get("title"), a.get_text(" ")) if x):
            return csn
    return None


def saramin_salary(f, csn):
    """사람인 기업 연봉 페이지 메타 설명의 '평균연봉 : 8614만원' (국민연금 기준)."""
    r = f.get(f"https://www.saramin.co.kr/zf_user/company-info/view-inner-salary?csn={csn}")
    m = SALARY_META.search(r.text)
    if m:
        v = int(m.group(1).replace(",", ""))
        if 1000 <= v <= 30000:
            return v
    return None


JP_RATING = re.compile(r'ratingValue\\*"\s*:\s*\\*"?([0-9.]+)')
JP_COUNT = re.compile(r'ratingCount\\*"\s*:\s*\\*"?([0-9]+)')
RATING_VERSION = 1


def jobplanet_rating(f, name):
    """잡플래닛 자동완성으로 회사 id를 찾고(이름 정확히 일치), 리뷰 페이지에서 평점·리뷰 수."""
    key = company_key(name)
    data = f.json(f"https://www.jobplanet.co.kr/autocomplete/autocomplete/suggest.json?term={quote(name)}",
                  referer="https://www.jobplanet.co.kr/")
    cid = next((c.get("id") for c in (data.get("companies") or [])
                if company_key(c.get("name")) == key), None)
    if not cid:
        return {"jp_id": None}
    html = f.get(f"https://www.jobplanet.co.kr/companies/{cid}/reviews").text
    m, n = JP_RATING.search(html), JP_COUNT.search(html)
    out = {"jp_id": cid, "jp_rating": None, "jp_reviews": int(n.group(1)) if n else 0}
    if m:
        v = float(m.group(1))
        if 0 < v <= 5:
            out["jp_rating"] = round(v, 1)
    return out


def rating_pass(companies, jobs, now, budget_sec=420, max_lookups=40):
    """잡플래닛 평점 조회. companies는 읽기만 하고, 바뀐 값은 돌려준다 (연봉 조회와 동시에 돌기 때문)."""
    f = Fetcher("jobplanet-rating")
    f.deadline = time.time() + budget_sec
    now_iso = now.isoformat()
    fresh = (now - timedelta(days=SALARY_REFRESH_DAYS)).isoformat()
    names = {}
    for j in jobs:
        ck = company_key(j.get("company"))
        if ck and ck not in names:
            names[ck] = j["company"]
    todo = [(ck, n) for ck, n in names.items()
            if not ((companies.get(ck) or {}).get("jp_v") == RATING_VERSION
                    and ((companies.get(ck) or {}).get("jp_checked") or "") >= fresh)]
    updates, found = {}, 0
    for ck, name in todo[:max_lookups]:
        try:
            info = jobplanet_rating(f, name)
        except (Blocked, OutOfTime) as e:
            log(f"   평점 조회 중단: {type(e).__name__}")
            break
        except Exception as e:  # noqa: BLE001
            log(f"   평점 {name}: {type(e).__name__}")
            continue
        updates[ck] = {**info, "jp_checked": now_iso, "jp_v": RATING_VERSION}
        if info.get("jp_rating"):
            found += 1
            log(f"   ★ {name}: {info['jp_rating']} (리뷰 {info['jp_reviews']})")
    log(f"== 잡플래닛 평점: 대상 {len(todo)}곳 중 {len(updates)}곳 조회, {found}곳 확인 (요청 {f.requests})")
    return updates, {"todo": len(todo), "checked": len(updates), "found": found}


def salary_pass(companies, jobs, hints, now, budget_sec=420, max_lookups=40):
    """공고에 나온 회사들의 평균연봉을 사람인에서 채운다. 실패해도 수집 결과에는 영향 없음."""
    f = Fetcher("salary")
    f.deadline = time.time() + budget_sec
    now_iso = now.isoformat()
    fresh = (now - timedelta(days=SALARY_REFRESH_DAYS)).isoformat()
    retry_missing = (now - timedelta(days=7)).isoformat()
    names = {}
    for j in jobs:
        ck = company_key(j.get("company"))
        if ck and ck not in names:
            names[ck] = j["company"]
    todo = []
    for ck, name in names.items():
        c = companies.get(ck) or {}
        checked = c.get("checked") or ""
        if c.get("v") == SALARY_VERSION and checked >= fresh and (c.get("avg_salary") or checked >= retry_missing):
            continue
        todo.append((ck, name))
    found = done = 0
    for ck, name in todo[:max_lookups]:
        c = dict(companies.get(ck) or {})
        try:
            csn = c.get("csn") or saramin_csn(hints.get(ck)) or find_saramin_csn(f, name)
            sal = saramin_salary(f, csn) if csn else None
        except (Blocked, OutOfTime) as e:
            log(f"   연봉 조회 중단: {type(e).__name__}")
            break
        except Exception as e:  # noqa: BLE001
            log(f"   연봉 {name}: {type(e).__name__}")
            continue
        c.update({"name": name, "checked": now_iso, "v": SALARY_VERSION, "src": "사람인"})
        if csn:
            c["csn"] = csn
        c["avg_salary"] = sal
        companies[ck] = c
        done += 1
        if sal:
            found += 1
            log(f"   $ {name}: 평균 {sal:,}만원")
    log(f"== 평균연봉: 대상 {len(todo)}곳 중 {done}곳 조회, {found}곳 확인 (요청 {f.requests})")
    return {"todo": len(todo), "checked": done, "found": found}


def parse_detail_generic(soup):
    """JSON-LD 우선, 없으면 og 메타 + 본문 텍스트."""
    out = {}
    ld = jsonld_jobposting(soup)
    if ld:
        org = ld.get("hiringOrganization") or {}
        out["title"] = clean(ld.get("title"))
        out["company"] = clean(org.get("name") if isinstance(org, dict) else str(org))
        out["location"] = location_from_ld(ld)
        out["employment"] = norm_employment(ld.get("employmentType"))
        out["deadline"] = to_date(ld.get("validThrough"))
        out["industry"] = clean(ld.get("industry") if isinstance(ld.get("industry"), str) else " ".join(ld.get("industry") or []))
        out["body"] = clean(ld.get("description"))
        out["salary"] = salary_from_ld(ld)
    if not out.get("body"):
        for t in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            t.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        out["body"] = clean(main.get_text(" "), 8000)
    out.setdefault("title", clean(meta(soup, "og:title", "twitter:title")))
    if not out.get("summary"):
        out["summary"] = clean(meta(soup, "og:description", "description"))
    return out


# ---------------------------------------------------------------- 사이트별 수집기
# 각 수집기는 (fetcher, known_urls) 를 받아 list[dict] 를 돌려준다.
# dict 필드: url, title, company, location, employment, deadline, industry, body(내부용)

def _links(soup, base, pattern):
    rx = re.compile(pattern)
    found = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        m = rx.search(href)
        if m:
            key = m.group(0)
            text = clean(a.get_text(" "))
            if key not in found or (text and len(text) > len(found[key])):
                found[key] = text
    return found


def _run_terms(f, terms, fn):
    """검색어마다 fn(term) 실행. 전부 실패하면 마지막 예외를 다시 던진다."""
    results, last_exc, ok = [], None, 0
    for t in terms:
        try:
            results.extend(fn(t))
            ok += 1
        except OutOfTime:
            f.errors.append(f"시간 예산 초과: '{t}'부터 검색 생략")
            break
        except Blocked as e:
            last_exc = e
            f.errors.append(f"{t}: blocked ({e})")
            if f.blocked >= 3 and ok == 0:
                break  # 계속 두드리지 않는다
        except Exception as e:  # noqa: BLE001
            last_exc = e
            f.errors.append(f"{t}: {type(e).__name__}: {e}"[:200])
    if ok == 0 and last_exc:
        raise last_exc
    return results


def _detail_pass(f, cards, known, detail_fn):
    """카드 목록에서 상세를 채운다. 이미 아는 url은 상세 요청을 생략한다."""
    out, fetched = [], 0
    for c in cards:
        if c["url"] in known:
            prev = known[c["url"]]
            c = {**prev, **{k: v for k, v in c.items() if v}}
            c["_known"] = True
            out.append(c)
            continue
        if not rules.title_could_match(c.get("title")) or rules.EXCLUDE_META.search(c.get("company") or ""):
            out.append(c)  # 제목·회사만으로 탈락 -> 상세 요청 생략 (judge에서 제외로 집계)
            continue
        if fetched >= MAX_DETAILS_PER_SOURCE:
            continue
        fetched += 1
        try:
            d = detail_fn(c)
            c = {**c, **{k: v for k, v in d.items() if v}}
        except OutOfTime:
            f.errors.append("시간 예산 초과: 상세 일부 생략")
            fetched = MAX_DETAILS_PER_SOURCE  # 남은 새 공고는 상세 없이 건너뜀 (기존 공고는 계속 갱신)
            continue
        except Blocked:
            raise
        except Exception as e:  # noqa: BLE001
            f.errors.append(f"detail {c['url']}: {type(e).__name__}"[:200])
        out.append(c)
    return out


def _dedupe(cards):
    seen = {}
    for c in cards:
        if c["url"] not in seen:
            seen[c["url"]] = c
        else:
            for k, v in c.items():
                if v and not seen[c["url"]].get(k):
                    seen[c["url"]][k] = v
    return list(seen.values())


# --- 사람인
def src_saramin(f, known):
    def search(term):
        url = ("https://www.saramin.co.kr/zf_user/search/recruit?searchType=search&recruitSort=reg_dt"
               f"&recruitPageCount=40&searchword={quote(term)}")
        soup = f.html(url)
        cards = []
        for it in soup.select("div.item_recruit"):
            a = it.select_one("h2.job_tit a")
            if not a:
                continue
            m = re.search(r"rec_idx=(\d+)", a.get("href", ""))
            if not m:
                continue
            cond = [clean(s.get_text()) for s in it.select("div.job_condition span")]
            cards.append({
                "url": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={m.group(1)}",
                "_id": m.group(1),
                "title": clean(a.get("title") or a.get_text()),
                "company": clean((it.select_one("strong.corp_name a") or it.select_one(".corp_name") or a).get_text()),
                "_company_url": company_link(it, "https://www.saramin.co.kr"),
                "location": cond[0] if cond else "",
                "employment": cond[3] if len(cond) > 3 else "",
                "deadline": to_date(clean((it.select_one("div.job_date .date") or it.new_tag("i")).get_text())),
                "industry": clean((it.select_one("div.job_sector") or it.new_tag("i")).get_text()),
            })
        if not cards:
            log("  saramin no cards; head:", soup.get_text(" ")[:300])
        return cards

    def detail(c):
        soup = f.html(f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={c['_id']}&rec_seq=0",
                      referer=c["url"])
        body = clean(soup.get_text(" "), 8000)
        out = {"body": body}
        try:  # 메인 페이지에 JSON-LD(마감일·업종)가 있다
            main = f.html(c["url"])
            d = parse_detail_generic(main)
            out.update({k: d[k] for k in ("deadline", "industry", "employment", "salary") if d.get(k)})
            out["_company_url"] = c.get("_company_url") or company_link(main, "https://www.saramin.co.kr")
        except Blocked:
            raise
        except Exception:
            pass
        return out

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, detail)


# --- 원티드
def src_wanted(f, known):
    def walk_positions(data):
        """API 응답 형태가 바뀌어도 position 객체를 찾아낸다."""
        out, stack = [], [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                pid = d.get("id")
                title = (d.get("position") or d.get("name")) if isinstance(d.get("company"), dict) else None
                if isinstance(pid, int) and isinstance(title, str):
                    out.append(d)
                else:
                    stack.extend(v for v in d.values() if isinstance(v, (list, dict)))
        return out

    def search(term):
        q = quote(term)
        endpoints = [
            f"https://www.wanted.co.kr/api/chaos/search/v1/results?query={q}&tab=position&country=kr&limit=40&offset=0",
            f"https://www.wanted.co.kr/api/v4/search?query={q}&tab=position&country=kr&limit=40",
        ]
        last = None
        for ep in endpoints:
            try:
                data = f.json(ep, referer=f"https://www.wanted.co.kr/search?query={q}&tab=position")
            except (Blocked, OutOfTime) as e:
                if isinstance(e, OutOfTime):
                    raise
                last = e
                break  # API가 막히면 공개 검색 페이지로
            except Exception as e:  # noqa: BLE001
                last = e
                continue
            pos = walk_positions(data)
            if pos:
                return [{
                    "url": f"https://www.wanted.co.kr/wd/{p['id']}",
                    "_id": p["id"],
                    "title": clean(p.get("position") or p.get("name")),
                    "company": clean((p.get("company") or {}).get("name")),
                    "location": clean((p.get("address") or {}).get("location") or ""),
                    "deadline": to_date(p.get("due_time")) or ("상시" if "due_time" in p and not p.get("due_time") else None),
                } for p in pos]
            if DEBUG:
                log("  wanted: no positions at", ep, str(data)[:300])
        # 마지막 수단: 검색 페이지 HTML의 /wd/ 링크
        soup = f.html(f"https://www.wanted.co.kr/search?query={q}&tab=position")
        links = _links(soup, "https://www.wanted.co.kr", r"https://www\.wanted\.co\.kr/wd/\d+")
        if not links:
            log("  wanted html no links; head:", soup.get_text(" ")[:300])
        if not links and last:
            raise last
        return [{"url": u, "_id": int(u.rsplit("/", 1)[1]), "title": t} for u, t in links.items()]

    def detail(c):
        try:
            j = f.json(f"https://www.wanted.co.kr/api/v4/jobs/{c['_id']}", referer=c["url"]).get("job", {})
            det = j.get("detail") or {}
            body = " ".join(clean(det.get(k)) for k in ("intro", "main_tasks", "requirements", "preferred_points", "benefits"))
            return {
                "title": clean(j.get("position")),
                "company": clean((j.get("company") or {}).get("name")),
                "industry": clean((j.get("company") or {}).get("industry_name")),
                "location": clean((j.get("address") or {}).get("full_location") or (j.get("address") or {}).get("location")),
                "deadline": to_date(j.get("due_time")) or "상시",
                "employment": "",
                "body": body,
            }
        except Blocked:
            raise
        except Exception:
            return parse_detail_generic(f.html(c["url"]))

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, detail)


# --- 잡코리아
def src_jobkorea(f, known):
    def search(term):
        soup = f.html(f"https://www.jobkorea.co.kr/Search/?stext={quote(term)}&tabType=recruit&Page_No=1")
        links = _links(soup, "https://www.jobkorea.co.kr", r"https://www\.jobkorea\.co\.kr/Recruit/GI_Read/\d+")
        if not links:
            log("  jobkorea no links; head:", soup.get_text(" ")[:300])
        return [{"url": u, "_id": u.rsplit("/", 1)[1], "title": t} for u, t in links.items()]

    def detail(c):
        soup = f.html(c["url"])
        d = parse_detail_generic(soup)
        og = meta(soup, "og:title")
        # og:title 예: "(주)회사 채용 - 공고제목 | 잡코리아"
        m = re.match(r"\s*(.+?)\s*채용\s*-\s*(.+?)\s*(?:\|.*)?$", og or "")
        if m:
            d.setdefault("company", m.group(1))
            if not d.get("title"):
                d["title"] = m.group(2)
        try:
            ifr = f.html(f"https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno={c['_id']}", referer=c["url"])
            body = clean(ifr.get_text(" "), 8000)
            if len(body) > len(d.get("body", "")):
                d["body"] = body
        except Blocked:
            raise
        except Exception:
            pass
        return d

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, detail)


# --- 점핏 (사람인 계열)
def src_jumpit(f, known):
    def search(term):
        data = f.json(f"https://jumpit-api.saramin.co.kr/api/positions?sort=reg_dt&highlight=false&keyword={quote(term)}",
                      referer="https://jumpit.saramin.co.kr/")
        pos = (data.get("result") or {}).get("positions") or []
        return [{
            "url": f"https://jumpit.saramin.co.kr/position/{p['id']}",
            "_id": p["id"],
            "title": clean(p.get("title")),
            "company": clean(p.get("companyName")),
            "location": ", ".join(p.get("locations") or []),
            "deadline": to_date(p.get("closedAt")) or ("상시" if p.get("alwaysOpen") else None),
            "industry": " ".join(p.get("techStacks") or []),
        } for p in pos if p.get("id")]

    def detail(c):
        try:
            j = f.json(f"https://jumpit-api.saramin.co.kr/api/position/{c['_id']}", referer=c["url"]).get("result") or {}
            body = " ".join(clean(j.get(k)) for k in ("serviceInfo", "responsibility", "qualifications", "preferredRequirements", "welfares"))
            return {"body": body, "employment": "정규직" if j.get("jobCategory") is None else ""}
        except Blocked:
            raise
        except Exception:
            return parse_detail_generic(f.html(c["url"]))

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, detail)


# --- 인크루트
def src_incruit(f, known):
    def search(term):
        soup = f.html(f"https://search.incruit.com/list/search.asp?col=job&kw={quote(term, encoding='euc-kr', errors='ignore')}")
        rx = re.compile(r"https?://job\.incruit\.com/jobdb_info/jobpost\.asp\?job=\d+")
        cards = {}
        for a in soup.find_all("a", href=True):
            m = rx.search(urljoin("https://job.incruit.com", a["href"]))
            if not m:
                continue
            url = m.group(0).replace("http://", "https://")
            title = clean(a.get_text(" "))
            box = a.find_parent("li")
            cp = box.select_one(".cpname") if box else None
            c = cards.setdefault(url, {"url": url, "title": "", "company": ""})
            if len(title) > len(c["title"]):
                c["title"] = title
            if cp and not c["company"]:
                c["company"] = clean(cp.get_text(" "))
        return list(cards.values())

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, lambda c: parse_detail_generic(f.html(c["url"])))


# --- 로켓펀치
def src_rocketpunch(f, known):
    def search(term):
        soup = f.html(f"https://www.rocketpunch.com/jobs?keywords={quote(term)}")
        links = _links(soup, "https://www.rocketpunch.com", r"https://www\.rocketpunch\.com/jobs/\d+(?:/[^?#\"']*)?")
        if not links:
            log("  rocketpunch no links; head:", soup.get_text(" ")[:300])
        return [{"url": u, "title": t} for u, t in links.items()]

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, lambda c: parse_detail_generic(f.html(c["url"])))


# --- 링크드인 (로그인 없이 공개되는 게스트 검색)
def src_linkedin(f, known):
    def search(term):
        url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
               f"keywords={quote(term)}&location={quote('South Korea')}&start=0")
        soup = f.html(url)
        cards = []
        for li in soup.select("li"):
            a = li.select_one("a.base-card__full-link") or li.select_one("a[href*='/jobs/view/']")
            if not a:
                continue
            m = re.search(r"/jobs/view/(?:[^/?]*-)?(\d+)", a["href"])
            if not m:
                continue
            cards.append({
                "url": f"https://www.linkedin.com/jobs/view/{m.group(1)}",
                "_id": m.group(1),
                "title": clean((li.select_one(".base-search-card__title") or a).get_text()),
                "company": clean((li.select_one(".base-search-card__subtitle") or li.new_tag("i")).get_text()),
                "location": clean((li.select_one(".job-search-card__location") or li.new_tag("i")).get_text()),
            })
        return cards

    def detail(c):
        soup = f.html(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{c['_id']}")
        body = clean((soup.select_one(".show-more-less-html__markup") or soup).get_text(" "), 8000)
        crit = {}
        for li in soup.select("li.description__job-criteria-item"):
            k = clean((li.select_one("h3") or li).get_text())
            v = clean((li.select_one("span") or li).get_text())
            crit[k] = v
        return {
            "body": body,
            "employment": norm_employment(crit.get("Employment type") or crit.get("고용 형태")),
            "industry": crit.get("Industries") or crit.get("업계") or "",
        }

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS_EN, search))
    return _detail_pass(f, cards, known, detail)


# --- 잡플래닛 (공개 API)
def src_jobplanet(f, known):
    def search(term):
        data = f.json(f"https://www.jobplanet.co.kr/api/v3/job/postings?query={quote(term)}&page=1&page_size=30",
                      referer="https://www.jobplanet.co.kr/job/search")
        out = []
        for p in ((data.get("data") or {}).get("recruits") or []):
            if not p.get("id") or p.get("jobkorea_posting_id"):
                continue  # 잡코리아에서 옮겨온 공고는 잡코리아 쪽에서 이미 수집
            out.append({
                "url": f"https://www.jobplanet.co.kr/job/search?posting_ids%5B%5D={p['id']}",
                "_id": p["id"],
                "title": clean(p.get("title")),
                "company": clean((p.get("company") or {}).get("name")),
                "location": ", ".join(p.get("cities") or []),
                "employment": clean(p.get("job_type")),
                "deadline": to_date(p.get("end_at")) or ("상시" if not p.get("end_at") else None),
                "industry": " ".join((p.get("occupation_names") or {}).get("level2") or []),
                "body": " ".join(p.get("skills") or []) if isinstance(p.get("skills"), list) and all(isinstance(x, str) for x in p.get("skills") or []) else "",
            })
        return out

    def detail(c):
        d = f.json(f"https://www.jobplanet.co.kr/api/v1/job/postings/{c['_id']}", referer=c["url"]).get("data") or {}
        texts = []

        def walk(x):
            if isinstance(x, str):
                if len(x) > 1 and not x.startswith("http"):
                    texts.append(x)
            elif isinstance(x, dict):
                for k, v in x.items():
                    if k not in ("logo_url", "image", "company"):
                        walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(d)
        return {"body": clean(" ".join(texts), 8000), "company": clean(d.get("name"))}

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, detail)


# --- 리멤버 (경력직 채용, 공개 검색 API)
def src_remember(f, known):
    shown = {"keys": False}

    def first(d, *paths):
        for path in paths:
            v = d
            for k in path.split("."):
                v = v.get(k) if isinstance(v, dict) else None
            if v:
                return v
        return None

    def search(term):
        if time.time() > f.deadline:
            f.out_of_time = True
            raise OutOfTime()
        r = f.s.post("https://career-api.rememberapp.co.kr/job_postings/search",
                     json={"search": {"keywords": [term]}, "page": 1, "per": 30},
                     headers={"Origin": "https://career.rememberapp.co.kr", "Referer": "https://career.rememberapp.co.kr/",
                              "Accept": "application/json"}, timeout=20)
        f.requests += 1
        time.sleep(random.uniform(*DELAY))
        if r.status_code in (401, 403, 429):
            f.blocked += 1
            raise Blocked(f"HTTP {r.status_code}")
        r.raise_for_status()
        items = r.json().get("data") or []
        if items and not shown["keys"]:
            shown["keys"] = True
            log("  remember keys:", sorted(items[0].keys())[:60])
        out = []
        for p in items:
            if not p.get("id"):
                continue
            body = " ".join(clean(p.get(k)) for k in ("job_description", "qualifications", "preferred_qualifications", "benefits") if isinstance(p.get(k), str))
            addr = first(p, "addresses") or []
            loc = ""
            if isinstance(addr, list) and addr and isinstance(addr[0], dict):
                loc = " ".join(str(v) for k, v in addr[0].items() if "level" in k and v)
            lo, hi = p.get("min_salary"), p.get("max_salary")
            sal = ""
            if isinstance(lo, (int, float)) or isinstance(hi, (int, float)):
                sal = f"연 {int(lo):,}~{int(hi):,}만원" if lo and hi else f"연 {int(lo or hi):,}만원"
            out.append({
                "url": f"https://career.rememberapp.co.kr/job/posting/{p['id']}",
                "title": clean(p.get("title")),
                "company": clean(first(p, "organization.name", "company.name", "organization_name", "company_name") or ""),
                "location": clean(loc),
                "employment": clean(p.get("employment_type") or ""),
                "deadline": to_date(first(p, "ending_date", "end_date", "ends_at", "closed_at")) or None,
                "industry": clean(p.get("job_role") or ""),
                "salary": sal,
                "body": body,
            })
        return out

    return _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))


# --- 미디어잡 (방송·영상·매스컴 전문)
def src_mediajob(f, known):
    def search(term):
        soup = f.html(f"https://www.mediajob.co.kr/search/search.htm?search={quote(term)}")
        links = _links(soup, "https://www.mediajob.co.kr",
                       r"https://www\.mediajob\.co\.kr/recruit/recruit\.htm\?cmd=view&rec_idx=\d+")
        return [{"url": u, "_id": u.rsplit("=", 1)[1], "title": t} for u, t in links.items()]

    def detail(c):
        soup = f.html(c["url"])
        d = parse_detail_generic(soup)
        if "미디어잡" in (d.get("title") or ""):
            d.pop("title")  # og:title은 "회사 채용 | 미디어잡"이라 목록의 공고 제목을 쓴다
        if not d.get("company"):
            m = re.match(r"\s*(.+?)\s*채용\s*\|", meta(soup, "og:title") or "")
            if m:
                d["company"] = m.group(1)
        try:
            ifr = f.html(f"https://www.mediajob.co.kr/company/recruit_detail_iframe.htm?rec_idx={c['_id']}", referer=c["url"])
            body = clean(ifr.get_text(" "), 8000)
            if len(body) > 50:
                d["body"] = body
        except Blocked:
            raise
        except Exception:
            pass
        return d

    cards = _dedupe(_run_terms(f, rules.SEARCH_TERMS, search))
    return _detail_pass(f, cards, known, detail)


# --- 슈퍼인턴
def src_superintern(f, known):
    try:
        soup = f.html("https://www.superintern.kr/")
    except requests.exceptions.SSLError:
        raise RuntimeError("사이트 보안 인증서(SSL) 오류로 접속 불가")
    links = _links(soup, "https://www.superintern.kr", r"https://www\.superintern\.kr/[^\s\"'#?]*\d+")
    cards = [{"url": u, "title": t} for u, t in links.items()]
    return _detail_pass(f, cards, known, lambda c: parse_detail_generic(f.html(c["url"])))


SOURCES = {
    "saramin": ("사람인", src_saramin),
    "wanted": ("원티드", src_wanted),
    "jobkorea": ("잡코리아", src_jobkorea),
    "jumpit": ("점핏", src_jumpit),
    "incruit": ("인크루트", src_incruit),
    "rocketpunch": ("로켓펀치", src_rocketpunch),
    "jobplanet": ("잡플래닛", src_jobplanet),
    "remember": ("리멤버", src_remember),
    "mediajob": ("미디어잡", src_mediajob),
    "superintern": ("슈퍼인턴", src_superintern),
    "linkedin": ("LinkedIn", src_linkedin),
}

FIELDS = ["source", "url", "title", "company", "location", "employment", "summary", "tools",
          "deadline", "salary", "avg_salary", "avg_salary_src", "employees", "jp_rating", "jp_reviews", "jp_url",
          "first_seen", "last_seen"]


# ---------------------------------------------------------------- 병합

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def to_record(source, c, now_iso, prev=None):
    body = c.get("body") or ""
    text = " ".join([c.get("title") or "", body, c.get("industry") or ""])
    tools = rules.find_tools(text) or (prev or {}).get("tools") or []
    rec = {
        "source": source,
        "url": c["url"],
        "title": c.get("title") or (prev or {}).get("title") or "",
        "company": c.get("company") or (prev or {}).get("company") or "",
        "location": c.get("location") or (prev or {}).get("location") or "",
        "employment": c.get("employment") or (prev or {}).get("employment") or "",
        "summary": make_summary(body) if body else (c.get("summary") or (prev or {}).get("summary") or ""),
        "tools": tools,
        "deadline": c.get("deadline") or (prev or {}).get("deadline"),
        "salary": c.get("salary") or (prev or {}).get("salary") or "",
        "avg_salary": None,  # 마지막에 companies.json 캐시에서 채움
        "avg_salary_src": "",
        "employees": None,
        "jp_rating": None,
        "jp_reviews": None,
        "jp_url": "",
        "first_seen": (prev or {}).get("first_seen") or now_iso,
        "last_seen": now_iso,
    }
    return {k: rec[k] for k in FIELDS}


def judge(c, prev=None):
    """(포함 여부, 사유). 이미 저장된 공고는 본문 없이 제목·저장된 툴로 판단."""
    title = c.get("title") or ""
    body = c.get("body") or ""
    tools = rules.find_tools(" ".join([title, body])) or (prev or {}).get("tools") or []
    reason = rules.exclusion_reason(title, c.get("company"), c.get("industry"), body)
    if reason:
        return False, reason
    if not rules.is_relevant(title, body, tools):
        return False, "not-relevant"
    return True, None


def title_ok(j):
    """본문 없이 제목·회사명만으로 다시 거르기 (규칙 변경을 기존 공고에도 반영)."""
    title = j.get("title") or ""
    if rules.NON_ARTIST_TITLE.search(title):
        return False
    return not rules.EXCLUDE_META.search(" ".join([title, j.get("company") or ""]))


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    started = now_kst()
    now_iso = started.isoformat()
    old_jobs = load_json(JOBS_FILE, [])
    if isinstance(old_jobs, dict):
        old_jobs = old_jobs.get("jobs", [])
    old_status = load_json(STATUS_FILE, {})
    by_url = {j["url"]: j for j in old_jobs if j.get("url")}
    companies = load_json(COMPANIES_FILE, {})
    salary_hints = {}  # 회사키 -> 사람인 기업정보 링크 (사람인 공고에서 얻은 것)

    only = [s.strip() for s in os.environ.get("RADAR_SOURCES", "").split(",") if s.strip()]
    status_sites = {}
    new_by_url = {}
    ok_sources = set()
    dropped_urls = set()  # 이번에 다시 보였지만 규칙상 제외된 공고 -> 바로 삭제

    def run_site(key, label, fn):
        f = Fetcher(key)
        t0 = time.time()
        known = {u: j for u, j in by_url.items() if j.get("source") == key}
        st = {"label": label, "ok": False, "count": 0, "found": 0, "excluded": 0, "new": 0,
              "requests": 0, "error": None, "checked_at": now_iso}
        recs, dropped = {}, set()
        lines = [f"== {label} ({key})"]
        try:
            cards = fn(f, known)
            st["found"] = len(cards)
            for c in cards:
                prev = by_url.get(c["url"])
                ok, why = judge(c, prev)
                if not ok:
                    st["excluded"] += 1
                    dropped.add(c["url"])
                    if DEBUG:
                        lines.append(f"   - skip [{why}] {c.get('title')} / {c.get('company')}")
                    continue
                rec = to_record(key, c, now_iso, prev)
                if not prev:
                    st["new"] += 1
                recs[rec["url"]] = rec
                if "saramin.co.kr" in (c.get("_company_url") or ""):
                    salary_hints[company_key(rec["company"])] = c["_company_url"]
                lines.append(f"   + {rec['title']} / {rec['company']} {rec['tools']}")
            st["ok"] = True
            st["count"] = len(recs)
            st["last_success"] = now_iso
            if f.out_of_time:
                st["partial"] = True
        except Blocked as e:
            st["error"] = f"차단됨: {e}"
            st["blocked"] = True
        except Exception as e:  # noqa: BLE001
            st["error"] = f"{type(e).__name__}: {e}"[:300]
            lines.append(traceback.format_exc())
        if not st["ok"]:
            prev_st = (old_status.get("sites") or {}).get(key) or {}
            if prev_st.get("last_success"):
                st["last_success"] = prev_st["last_success"]
        st["requests"] = f.requests
        st["warnings"] = f.errors[:10]
        st["seconds"] = round(time.time() - t0, 1)
        lines.append(f"   => ok={st['ok']} count={st['count']} found={st['found']} excluded={st['excluded']} "
                     f"requests={f.requests} {st['seconds']}s err={st['error']}")
        log("\n".join(lines))
        return key, st, recs, dropped

    todo = []
    for key, (label, fn) in SOURCES.items():
        if only and key not in only:
            # 이번에 안 돈 사이트는 이전 상태 유지
            if key in (old_status.get("sites") or {}):
                status_sites[key] = old_status["sites"][key]
            continue
        todo.append((key, label, fn))
    # 사이트끼리는 동시에, 같은 사이트 안에서는 요청 간격을 지키며 순서대로
    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as ex:
        for key, st, recs, dropped in ex.map(lambda a: run_site(*a), todo):
            status_sites[key] = st
            if st["ok"]:
                ok_sources.add(key)
                new_by_url.update(recs)
                dropped_urls.update(dropped)
    status_sites = {k: status_sites[k] for k in SOURCES if k in status_sites}

    # 병합: 성공한 사이트는 새 결과 + (7일 안 지난) 미발견 공고, 실패한 사이트는 기존 그대로
    cutoff = started - timedelta(days=STALE_DAYS)
    merged = dict(new_by_url)
    for url, j in by_url.items():
        if url in merged or url in dropped_urls:
            continue
        if not title_ok(j):
            continue  # 규칙이 바뀌어 이제는 제외 대상
        if j.get("source") in ok_sources:
            try:
                last = datetime.fromisoformat(j["last_seen"])
            except Exception:
                last = started
            if last < cutoff:
                continue  # 7일 연속 안 보임 -> 제거
        merged[url] = j

    # 평균연봉(사람인)과 잡플래닛 평점은 서로 다른 사이트라 동시에 조회
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_rating = ex.submit(rating_pass, companies, list(merged.values()), started)
        salary_stat = salary_pass(companies, list(merged.values()), salary_hints, started)
        rating_updates, rating_stat = fut_rating.result()
    for ck, upd in rating_updates.items():
        companies[ck] = {**(companies.get(ck) or {}), **upd}
    for j in merged.values():
        info = companies.get(company_key(j.get("company"))) or {}
        j["jp_rating"] = info.get("jp_rating")
        j["jp_reviews"] = info.get("jp_reviews") if info.get("jp_rating") else None
        j["jp_url"] = f"https://www.jobplanet.co.kr/companies/{info['jp_id']}/reviews" if info.get("jp_id") else ""
        j["avg_salary"] = info.get("avg_salary")
        j["avg_salary_src"] = f"{info['src']} 기업정보" if info.get("avg_salary") else ""
        j["employees"] = info.get("employees")
        for k in FIELDS:
            j.setdefault(k, None if k in ("avg_salary", "employees", "jp_rating", "jp_reviews") else "")
    COMPANIES_FILE.write_text(json.dumps(companies, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    jobs = sorted(merged.values(), key=lambda j: (j.get("first_seen") or "", j.get("last_seen") or ""), reverse=True)
    for key, st in status_sites.items():
        st["total"] = sum(1 for j in jobs if j.get("source") == key)

    JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    status = {
        "updated_at": now_iso,
        "finished_at": now_kst().isoformat(),
        "total": len(jobs),
        "salary": salary_stat,
        "jobplanet_rating": rating_stat,
        "sites": status_sites,
    }
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"done: {len(jobs)} jobs, ok={sorted(ok_sources)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
