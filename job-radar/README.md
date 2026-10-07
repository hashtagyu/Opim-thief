# 📡 AI 아티스트 잡 레이더 (GitHub 버전)

맥북 없이 GitHub Actions가 매일 채용 공고를 모으고, GitHub Pages가 페이지를 띄워요.

```
GitHub Actions (매일 09:00 KST)
  └─ scripts/collect.py  →  data/jobs.json, data/status.json 커밋
GitHub Pages
  └─ index.html  ←  data/jobs.json, data/insta.json, data/status.json 을 fetch
```

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `index.html` | 페이지 (검색, NEW만 보기, 사이트별 필터, 사이트별 수집 건수) |
| `data/jobs.json` | 자동 수집된 공고 (손대지 마세요) |
| `data/status.json` | 사이트별 성공/실패, 수집 건수, 마지막 갱신 시각 |
| `data/insta.json` | **손으로 관리하는** 인스타 스튜디오 목록 |
| `scripts/collect.py` | 수집기 (LLM·API 키 없음) |
| `scripts/rules.py` | 검색어, 툴 이름 사전, 포함·제외 규칙 |
| `../.github/workflows/refresh.yml` | 매일 실행 + 수동 실행 워크플로 |

## 수동 새로고침

1. 페이지의 **⟳ 지금 새로고침** 버튼을 누르거나, 저장소 → Actions → "AI 잡 레이더 새로고침"으로 가요.
2. 오른쪽의 **Run workflow** → 브랜치 `main` → **Run workflow**.
3. 2~3분 뒤(사이트가 많으면 최대 10분) 페이지를 새로고침하면 반영돼요.

일부 사이트만 돌리려면 `sources` 칸에 `saramin,wanted` 처럼 적어요. 원인을 보고 싶으면 `debug` 를 켜요.

## 인스타 목록 고치기

`data/insta.json` 의 `studios` 배열에 항목을 추가해요. 폰에서도 GitHub 웹에서 파일 → ✏️ 연필 아이콘 → 수정 → Commit changes 로 할 수 있어요.

```json
{
 "account": "instagram_id",
 "name": "스튜디오 이름",
 "hiring_now": true,
 "post_url": "채용 게시물 주소",
 "post_title": "AI 아티스트 모집",
 "post_date": "2026-10-07",
 "tools": ["Kling"],
 "summary": "한 줄 메모"
}
```

- `account` 만 있으면 인스타 프로필 링크는 자동으로 만들어져요. 아이디를 모르면 비우고 `url` 에 다른 주소를 넣어도 돼요.
- `hiring_now: true` 면 "채용중", `false` 면 "채용 이력"으로 표시돼요. 채용중인 곳이 위로 올라가요.
- 항목 사이에는 쉼표가 필요해요. 쉼표나 따옴표 하나만 빠져도 JSON이 깨지니 커밋 전에 확인하세요. 커밋하면 1~2분 뒤 페이지에 반영돼요.

## 수집 규칙

- **사이트**: 사람인, 원티드, 잡코리아, 점핏, 인크루트, 로켓펀치, LinkedIn(로그인 없는 공개 검색)
- **포함**: 제목에 "AI/생성형 + 아티스트·영상·크리에이터·콘텐츠…"가 있거나, 본문에 생성형 툴(Higgsfield, ComfyUI, Seedance, Kling, Nano Banana, Midjourney, Runway, Veo, Sora 등)이 나오고 제목이 영상·디자인·크리에이티브 직무인 공고
- **제외**: 제목·회사명·업종에 광고/대행사/커머스/뷰티/화장품/코스메틱/병원/마케팅/교육 등이 있거나, 본문에 "광고대행", "화장품 브랜드", "교육 기관" 같은 표현이 있거나, 본문에 광고·마케팅·교육 같은 단어가 3번 이상 나오는 공고 ("교육비 지원" 같은 복지 문구는 세지 않음)
- url 기준 중복 제거, `first_seen` 유지·`last_seen` 갱신, 7일 연속 안 보이면 제거
- 사이트가 막히거나 실패하면 그 사이트의 기존 공고는 그대로 두고 `status.json` 에 실패로 기록
- 요청 사이 1.5~3초 간격, 일반 브라우저 User-Agent. 로그인·캡차 우회나 프록시는 쓰지 않아요.

규칙은 `scripts/rules.py` 에서 고칠 수 있어요.

## 로컬에서 돌려보기

```bash
pip install -r job-radar/scripts/requirements.txt
python job-radar/scripts/collect.py
cd job-radar && python -m http.server 8000   # http://localhost:8000
```
