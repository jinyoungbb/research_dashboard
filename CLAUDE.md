# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 언어 지침

모든 응답, 결과값, 설명, 주석은 반드시 **한글**로 작성한다.

---

## 프로젝트 개요

주요 학술지에 투고된 논문의 메타정보(제목, 저자, 날짜, 키워드, DOI)와 초록을 자동 수집하고,
**Google Gemini API**(무료 티어)를 활용해 연구동향을 요약·분석하는 에이전트.

**핵심 원칙**: 비용 최소화 — 무료 API 우선, LLM 호출 최소화, 중복 처리 금지.

### LLM API 현황 (2026-03)
- **사용 SDK**: `google-genai` (`from google import genai`)
- **모델**: `gemini-3.1-flash-lite-preview` (무료: 15 RPM, 500 RPD)
- **API 키 환경변수**: `GEMINI_API_KEY`
- **rate limit 처리**: `google.genai.errors.ClientError` status 429 → 60초 대기 재시도
- **요청 간격**: `time.sleep(4.0)` (15 RPM 준수)
- ~~anthropic~~ 패키지 제거 완료

---

## 1단계: 목표 정의

### 수집 대상 메타정보
- 제목 (title)
- 저자 (authors)
- 게재일 (publication_date)
- 키워드 (keywords)
- 초록 (abstract)
- DOI
- 저널명 / 학회명
- URL

### 모니터링 학술지 목록

```python
TARGET_JOURNALS = [
    # ── CS 분야 (17개) ──────────────────────────────────────────────
    {
        "name": "Information Systems Research",
        "url": "https://pubsonline.informs.org/journal/isre",
        "tag": "CS",
    },
    {
        "name": "Journal of Management Information Systems",
        "url": "https://www.jmis-web.org/",
        "tag": "CS",
    },
    {
        "name": "Journal of the Association for Information Systems",
        "url": "https://aisel.aisnet.org/jais/",
        "tag": "CS",
    },
    {
        "name": "Journal of Business Research",
        "url": "https://www.sciencedirect.com/journal/journal-of-business-research",
        "tag": "CS",
    },
    {
        "name": "Production and Operations Management",
        "url": "https://journals.sagepub.com/home/paoa",
        "tag": "CS",
    },
    {
        "name": "Journal of Operations Management",
        "url": "https://www.jom-hub.com/",
        "tag": "CS",
    },
    {
        "name": "Information & Management",
        "url": "https://www.sciencedirect.com/journal/information-and-management",
        "tag": "CS",
    },
    {
        "name": "Decision Support Systems",
        "url": "https://www.sciencedirect.com/journal/decision-support-systems",
        "tag": "CS",
    },
    {
        "name": "Expert Systems with Applications",
        "url": "https://www.sciencedirect.com/journal/expert-systems-with-applications",
        "tag": "CS",
    },
    {
        "name": "IEEE Access",
        "url": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=6287639",
        "tag": "CS",
    },
    {
        "name": "Internet Research",
        "url": "https://www.emerald.com/insight/publication/issn/1066-2243",
        "tag": "CS",
    },
    {
        "name": "International Journal of Information Management",
        "url": "https://www.sciencedirect.com/journal/international-journal-of-information-management",
        "tag": "CS",
    },
    {
        "name": "Technology in Society",
        "url": "https://www.sciencedirect.com/journal/technology-in-society",
        "tag": "CS",
    },
    {
        "name": "Computers in Human Behavior",
        "url": "https://www.sciencedirect.com/journal/computers-in-human-behavior",
        "tag": "CS",
    },
    {
        "name": "Telematics and Informatics",
        "url": "https://www.sciencedirect.com/journal/telematics-and-informatics",
        "tag": "CS",
    },
    {
        "name": "ICIS Proceedings",
        "url": "https://aisel.aisnet.org/icis/",
        "tag": "CS",
    },
    {
        "name": "HICSS Proceedings",
        "url": "https://aisel.aisnet.org/hicss/",
        "tag": "CS",
    },

    # ── LIS 분야 (9개) ──────────────────────────────────────────────
    {
        "name": "MIS Quarterly",
        "url": "https://misq.umn.edu/",
        "tag": "LIS",
    },
    {
        "name": "Journal of the Association for Information Science and Technology",
        "url": "https://asistdl.onlinelibrary.wiley.com/journal/23301643",
        "tag": "LIS",
    },
    {
        "name": "Library and Information Science Research",
        "url": "https://www.sciencedirect.com/journal/library-and-information-science-research",
        "tag": "LIS",
    },
    {
        "name": "Information Processing and Management",
        "url": "https://www.sciencedirect.com/journal/information-processing-and-management",
        "tag": "LIS",
    },
    {
        "name": "Journal of Documentation",
        "url": "https://www.emerald.com/insight/publication/issn/0022-0418",
        "tag": "LIS",
    },
    {
        "name": "College and Research Libraries",
        "url": "https://crl.acrl.org/",
        "tag": "LIS",
    },
    {
        "name": "정보관리학회지",
        "url": "https://kosim.jams.or.kr/",
        "tag": "LIS",
    },
    {
        "name": "한국문헌정보학회지",
        "url": "https://journal.kci.go.kr/kslis",
        "tag": "LIS",
    },
    {
        "name": "한국비블리아학회지",
        "url": "https://journal.kci.go.kr/kbiblia",
        "tag": "LIS",
    },
]
```

### 업데이트 주기
- 기본값: 주 1회 (매주 월요일 오전 9시)
- 환경변수 `CRAWL_INTERVAL`로 조정 가능

---

## 2단계: 데이터 수집 아키텍처

### 무료 API 우선순위 (비용 0원)

| 우선순위 | API | 커버리지 | 인증 |
|---------|-----|---------|------|
| 1 | **OpenAlex** | 거의 모든 저널, 가장 범용 | 불필요 (이메일 권장) |
| 2 | **Semantic Scholar** | CS/AI/바이오 강점 | 무료 API키 |
| 3 | **CrossRef** | DOI 기반 전체 | 불필요 |
| 4 | **PubMed/Entrez** | 의학·생명과학 전용 | 무료 |
| 5 | **arXiv API** | 프리프린트 전용 | 불필요 |

### 수집 모듈 구현 원칙
- OpenAlex API를 기본 수집 경로로 사용
- OpenAlex로 커버 안 되는 저널만 차순위 API 추가
- RSS 피드, Selenium 스크래핑은 **마지막 수단**으로만 사용
- 각 API 호출 사이에 `time.sleep(1)` 삽입 (rate limit 준수)

### API 호출 예시 구조
```python
# OpenAlex 저널별 최신 논문 조회
GET https://api.openalex.org/works
    ?filter=primary_location.source.display_name:{저널명},
            from_publication_date:{시작일}
    &select=title,authorships,publication_date,keywords,abstract_inverted_index,doi
    &per_page=50
    &mailto=your@email.com  # Polite pool 진입 (속도 향상)
```

---

## 3단계: 기술 스택

### 디렉토리 구조
```
claude_2603/
├── CLAUDE.md
├── main.py              # 진입점: 수집 → 저장 → 분석 → 리포트 순서 실행
├── config.py            # TARGET_JOURNALS, API 키, 경로 설정
├── collector/
│   ├── openalex.py      # OpenAlex API 수집기
│   ├── semantic.py      # Semantic Scholar 수집기
│   ├── pubmed.py        # PubMed 수집기 (의학 분야)
│   └── arxiv.py         # arXiv 수집기 (프리프린트)
├── storage/
│   └── database.py      # SQLite CRUD, 중복 체크
├── analyzer/
│   └── trend.py         # Claude API 배치 요약, 트렌드 분석
├── reporter/
│   └── markdown.py      # Markdown 리포트 생성기
├── scheduler.py         # 자동 실행 스케줄러
├── data/
│   └── papers.db        # SQLite DB (git ignore)
└── reports/             # 생성된 리포트 저장 (날짜별)
    └── 2026-03-07.md
```

### 핵심 의존성
```
httpx              # HTTP 요청
google-genai       # Google Gemini API (신규 SDK, from google import genai)
schedule           # 스케줄러
python-dotenv      # 환경변수 관리
streamlit          # 대시보드 UI
plotly             # 차트
```

### SQLite 스키마
```sql
CREATE TABLE papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doi             TEXT UNIQUE,          -- 중복 방지 기준
    title           TEXT NOT NULL,
    authors         TEXT,                 -- JSON 배열 문자열
    journal         TEXT,
    publication_date TEXT,
    keywords        TEXT,                 -- JSON 배열 문자열
    abstract        TEXT,
    source_api      TEXT,                 -- 수집 출처 API
    collected_at    TEXT,                 -- 수집 일시
    is_analyzed     INTEGER DEFAULT 0,    -- LLM 분석 완료 여부 (0/1)
    trend_summary   TEXT                  -- Claude 분석 결과 캐시
);
```

---

## 4단계: 에이전트 구현 상세

### 수집 흐름
```
main.py 실행
  → config에서 TARGET_JOURNALS 로드
  → 각 저널별 API 호출 (우선순위 순)
  → DOI 기준 중복 체크 후 신규 논문만 DB 저장
  → is_analyzed=0 논문 목록 추출
  → analyzer에 전달
```

### 중복 방지 규칙
- DOI가 있으면 DOI로 중복 체크
- DOI가 없으면 `title + journal + publication_date` 조합으로 체크
- 이미 DB에 있는 논문은 **수집 단계에서 스킵**

### 에러 처리
- API 호출 실패 시 최대 3회 재시도 (exponential backoff)
- 재시도 실패 시 해당 저널 스킵, 로그 기록 후 계속 진행
- 절대 전체 프로세스를 중단하지 않음

---

## 5단계: 비용 절감 전략

### Gemini API 호출 최소화 규칙

1. **배치 처리 필수**
   - 논문 초록을 개별 전송 금지
   - `BATCH_SIZE`(기본 15)개 초록을 하나의 프롬프트로 묶어 전송

2. **캐싱 필수**
   - `is_analyzed=1`인 논문은 재분석 금지
   - `trend_summary` 컬럼에 결과 저장 후 재사용

3. **모델 및 rate limit**
   ```python
   SUMMARY_MODEL = "gemini-3.1-flash-lite-preview"  # 무료: 15 RPM, 500 RPD
   # 요청 간격: time.sleep(4.0)
   # 429 오류 시 60초 대기 후 재시도
   ```

4. **번역 일일 한도**: 500 RPD → 대량 번역 시 여러 날에 걸쳐 실행
   - `python main.py --translate` 로 미번역분 이어서 처리

5. **주간 배치 처리**
   - 주 1회 수집 → 번역 → 분석 순서 실행

### 배치 분석 프롬프트 구조
```python
TREND_PROMPT = """
다음은 {journal}에 최근 게재된 {n}편의 논문 초록입니다.

{abstracts}  # "1. [제목]\n초록: ...\n\n2. ..." 형식

위 논문들을 분석하여 다음을 한글로 답하세요:
1. 이번 주 주요 연구 트렌드 (3줄 이내)
2. 자주 등장한 키워드 Top 5
3. 주목할 만한 논문 2~3편 (제목 + 한 줄 요약)
"""
```

---

## 6단계: 출력 형태

### Markdown 리포트 구조 (`reports/YYYY-MM-DD.md`)
```markdown
# 연구동향 리포트 — YYYY-MM-DD

## 요약
- 수집 기간: YYYY-MM-DD ~ YYYY-MM-DD
- 총 수집 논문: N편
- 분석 저널: N개

## 저널별 트렌드
### [저널명]
**주요 트렌드**
...

**Top 키워드**
| 키워드 | 빈도 |
|--------|------|

**주목 논문**
- [제목](DOI 링크) — 저자 — 한 줄 요약

---
```

### Streamlit 대시보드 (`dashboard.py`)
- `streamlit run dashboard.py` 로 실행 (기본 포트 8501)
- DB에서 직접 읽어 시각화 (30초 캐시)
- **논문 목록 UI** (2026-03 기준):
  - 영문 제목 전체 + 한국어 번역 **항상 표시** (클릭 불필요)
  - 저자·초록·키워드는 "📋 저자 · 초록 · 키워드" expander로 접기/펼치기
  - 저널 정보(`tag`, `journal`, `publication_date`) 제목 위에 표시
- 페이지: 트렌드 분석 / 저널별 현황 / 키워드 / 논문 목록

---

## 환경변수 (.env)

```
GEMINI_API_KEY=AIzaSy...        # Google AI Studio 발급 (필수)
SEMANTIC_SCHOLAR_API_KEY=       # 선택사항
NCBI_API_KEY=                   # PubMed, 선택사항
OPENALEX_EMAIL=your@email.com   # Polite pool 진입용
CRAWL_INTERVAL=weekly           # daily / weekly
```

> Gemini API 키 발급: https://aistudio.google.com/app/apikey

---

## 개발 순서 (권장)

1. `config.py` + `storage/database.py` 구현 (DB 스키마 확정)
2. `collector/openalex.py` 구현 및 테스트
3. 나머지 수집기 추가 (필요한 저널 커버리지 따라)
4. `analyzer/trend.py` 구현 (배치 처리 + 캐싱)
5. `reporter/markdown.py` 구현
6. `scheduler.py` 연결
7. (선택) `dashboard.py` Streamlit UI 추가

---

## 주요 명령어

```bash
# 대시보드 실행
streamlit run dashboard.py

# 수집 (기본 7일)
python main.py --collect

# 특정 날짜 이후 전체 수집
python main.py --collect --from-date 2024-01-01

# 미번역 논문 번역 (500 RPD 한도 내)
python main.py --translate

# 트렌드 분석
python main.py --analyze

# 전체 파이프라인
python main.py
```

## OpenAlex 수집기 주요 설정
- 페이지네이션: cursor 기반 (`cursor=*` → `meta.next_cursor`)
- 기본 max_results: 2000편/저널
- per_page: 200 (최대값)

---

## 금지 사항

- 논문 1건씩 Gemini API 호출 금지 (배치 필수)
- 이미 분석된 논문 재분석 금지
- Selenium/스크래핑을 API 대신 1순위로 사용 금지
- `.env` 파일 git 커밋 금지
- `google-generativeai` (구 deprecated SDK) 사용 금지 → `google-genai` 사용
