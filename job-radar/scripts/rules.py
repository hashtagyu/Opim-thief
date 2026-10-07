"""포함·제외 규칙과 툴 이름 사전. LLM 없이 정규식으로만 판단한다."""
import re

# 각 사이트에 넣을 검색어 (한글·영문)
SEARCH_TERMS = [
    "AI 아티스트",
    "AI 영상",
    "AI 크리에이터",
    "생성형 AI 영상",
    "AI 콘텐츠 제작",
    "미드저니",
    "ComfyUI",
    "Midjourney",
    "AI artist",
    "AI video",
    "Higgsfield",
    "Kling",
]

# 영문 위주 사이트(LinkedIn)용 검색어
SEARCH_TERMS_EN = [
    "AI artist",
    "AI video creator",
    "generative AI video",
    "ComfyUI",
    "Midjourney",
]

# 표시 이름 -> 패턴. 한글/영문 표기 모두.
TOOLS = {
    "Higgsfield": r"higgs\s*field|힉스\s*필드",
    "ComfyUI": r"comfy\s*ui|comfyui|컴피\s*(?:ui|유아이)",
    "Seedance": r"seedance|시댄스|씨댄스",
    "Kling": r"\bkling\b|클링\s*(?:ai)?(?=\W|$)",
    "Nano Banana": r"nano\s*-?\s*banana|나노\s*바나나",
    "Midjourney": r"mid\s*journey|미드\s*저니",
    "Runway": r"\brunway\s*(?:ml|gen|act|aleph|ai)|\brunwayml\b|런웨이\s*(?:ml|ai|gen)|(?<![a-z])Runway(?![a-z])",
    "Veo": r"(?<![A-Za-z])Veo(?:\s*\d)?(?![A-Za-z])|구글\s*비오",
    "Sora": r"(?<![A-Za-z])Sora(?![A-Za-z])|오픈ai\s*소라|openai\s*소라",
    "Stable Diffusion": r"stable\s*diffusion|스테이블\s*디퓨전|\bsdxl\b",
    "Flux": r"(?<![A-Za-z])FLUX(?:\.1)?(?![A-Za-z])|(?<![A-Za-z])Flux\s*(?:\.1|1|pro|dev|kontext)",
    "Pika": r"\bpika\s*(?:labs|art|\d)?\b(?=.{0,30}(?:ai|video|영상))|피카\s*랩스",
    "Luma": r"luma\s*(?:ai|labs|dream)|dream\s*machine|루마\s*ai",
    "Hailuo": r"hailuo|하이루오|minimax|미니맥스",
    "Wan": r"(?<![A-Za-z])Wan\s*2\.\d",
    "Hedra": r"\bhedra\b",
    "Krea": r"\bkrea\b",
    "Leonardo": r"leonardo\s*(?:ai|\.ai)",
    "Firefly": r"adobe\s*firefly|\bfirefly\b|파이어플라이",
    "DALL-E": r"dall[\s·-]?e|달리\s*3",
    "Suno": r"\bsuno\b|수노\s*ai",
    "ElevenLabs": r"eleven\s*labs|일레븐\s*랩스",
    "Magnific": r"\bmagnific\b",
    "Topaz": r"topaz\s*(?:video|labs|ai)",
}
_TOOL_RE = {k: re.compile(v, re.I) for k, v in TOOLS.items()}
# 대소문자를 구분해야 하는 툴 (Veo/Sora/Runway/Flux/Wan 등 일반 단어와 겹침)
_CASE_SENSITIVE = {"Veo", "Sora", "Flux", "Wan"}
for _k in _CASE_SENSITIVE:
    _TOOL_RE[_k] = re.compile(TOOLS[_k])

# 제목에 있으면 AI 아티스트 직무로 바로 인정
ROLE_TITLE = re.compile(
    r"(?:ai|생성형|인공지능|gen\s*ai)\s*[-·/]?\s*(?:기반\s*)?"
    r"(?:아티스트|영상|크리에이터|콘텐츠|컨텐츠|디자이너|애니메이터|애니메이션|비디오|이미지|필름|감독|pd|작가|"
    r"artist|video|creator|content|filmmaker|animator|animation|designer|director|motion|visual|image|cinemat)",
    re.I,
)
# 툴이 언급된 경우 제목에 이런 크리에이티브 단어가 있으면 인정
CREATIVE_TITLE = re.compile(
    r"영상|비디오|아티스트|크리에이터|콘텐츠|컨텐츠|디자이너|디자인|모션|편집|애니메이|vfx|3d|cg|pd|감독|일러스트|"
    r"그래픽|촬영|숏폼|artist|video|creator|content|motion|editor|animat|designer|vfx|film|visual|creative|generalist",
    re.I,
)

# 제목·회사명·업종에 하나라도 있으면 제외
EXCLUDE_META = re.compile(
    r"광고|대행사|커머스|쇼핑몰|뷰티|화장품|코스메틱|병원|의원|클리닉|성형외과|(?<!생)성형|피부과|치과|한의원|"
    r"마케팅|마케터|퍼포먼스|교육|학원|강사|튜터|에듀|아카데미|상세\s*페이지|쇼핑|"
    r"advertis|ad\s*agency|commerce|beauty|cosmetic|hospital|clinic|medical|marketing|marketer|"
    r"education|edtech|academy|tutor|instructor|teacher",
    re.I,
)
# 본문: 구체적인 표현은 1번만 나와도 제외
EXCLUDE_BODY_STRONG = re.compile(
    r"광고\s*대행|종합\s*광고|광고\s*에이전시|디지털\s*광고\s*회사|이\s*커머스|커머스\s*(?:기업|회사|플랫폼|브랜드)|"
    r"쇼핑몰\s*운영|뷰티\s*(?:브랜드|기업|회사)|화장품\s*(?:브랜드|기업|회사|제조)|코스메틱|"
    r"(?:성형외과|피부과|치과|한의원|병원)\s*(?:입니다|에서|소속|전문)|마케팅\s*(?:대행|에이전시|전문\s*기업|회사)|"
    r"퍼포먼스\s*마케팅|교육\s*기관|교육\s*(?:전문\s*|콘텐츠\s*)?(?:기업|회사)|교육\s*콘텐츠|에듀테크|학원|강사\s*(?:모집|채용)|"
    r"advertising\s*agency|marketing\s*agency|e-?commerce\s*(?:company|brand|platform)|beauty\s*brand|"
    r"cosmetics?\s*(?:brand|company)|edtech|education\s*company",
    re.I,
)
# 본문: 흔한 단어는 3번 이상 나와야 제외 ("교육비 지원" 같은 복지 문구 오탐 방지)
EXCLUDE_BODY_WEAK = re.compile(r"광고|마케팅|교육|뷰티|커머스|병원|advertis|marketing|education|beauty|commerce", re.I)
WEAK_THRESHOLD = 3
# 복지 문구는 약한 단어 계산에서 빼고 센다
BENEFIT_NOISE = re.compile(r"교육\s*(?:비|지원|프로그램|기회)|사내\s*교육|직무\s*교육|도서\s*.{0,4}교육|education\s*(?:budget|stipend|support)", re.I)


def find_tools(text):
    text = text or ""
    return [name for name, rx in _TOOL_RE.items() if rx.search(text)]


def exclusion_reason(title, company, industry, body):
    meta = " ".join(x for x in (title, company, industry) if x)
    m = EXCLUDE_META.search(meta)
    if m:
        return f"meta:{m.group(0)}"
    body = body or ""
    m = EXCLUDE_BODY_STRONG.search(body)
    if m:
        return f"body:{m.group(0)}"
    cleaned = BENEFIT_NOISE.sub(" ", body)
    hits = EXCLUDE_BODY_WEAK.findall(cleaned)
    if len(hits) >= WEAK_THRESHOLD:
        return f"body-weak:{hits[0]}x{len(hits)}"
    return None


# 개발·엔지니어 직군은 제목에 "AI Artist"가 붙어 있어도 제외
NON_ARTIST_TITLE = re.compile(
    r"엔지니어|개발자|백엔드|프론트엔드|풀스택|데이터\s*사이언|engineer|developer|software|full\s*stack|backend|frontend|"
    r"devops|data\s*scien|researcher|연구원|영업|세일즈|sales|회계|인사\b",
    re.I,
)


def title_could_match(title):
    """상세를 열기 전 제목만으로 후보가 될 수 있는지 (요청 수 줄이기용)."""
    title = title or ""
    if not title:
        return True
    if NON_ARTIST_TITLE.search(title) or EXCLUDE_META.search(title):
        return False
    return bool(ROLE_TITLE.search(title) or CREATIVE_TITLE.search(title))


def is_relevant(title, body, tools):
    title = title or ""
    if NON_ARTIST_TITLE.search(title):
        return False
    if ROLE_TITLE.search(title):
        return True
    return bool(tools) and bool(CREATIVE_TITLE.search(title))
