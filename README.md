# 학술지 논문 트렌드 대시보드

주요 학술지 논문 메타정보를 자동 수집하고 Google Gemini API로 연구동향을 분석하는 도구.

## 신규 컴퓨터 세팅 절차

### 1. 저장소 클론
```bash
git clone https://github.com/[username]/[repo].git
cd [repo]
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정
```bash
cp .env.example .env
# .env 파일을 열어 API 키 입력
```

`.env` 파일 예시:
```
GEMINI_API_KEY=AIzaSy...       # https://aistudio.google.com/app/apikey 에서 발급
OPENALEX_EMAIL=your@email.com
CRAWL_INTERVAL=weekly
```

### 4. DB 파일 복사
`data/papers.db` 파일을 Google Drive 등에서 다운로드하여 `data/` 폴더에 복사.

DB 없이 처음 시작하는 경우 직접 수집:
```bash
python main.py --collect --from-date 2024-01-01
python main.py --translate   # 번역 (500 RPD 한도, 여러 날에 걸쳐 실행)
python main.py --analyze     # 트렌드 분석
```

### 5. 대시보드 실행
```bash
streamlit run dashboard.py
```
브라우저에서 http://localhost:8501 접속.

---

## 주요 명령어

| 명령어 | 설명 |
|--------|------|
| `streamlit run dashboard.py` | 대시보드 실행 |
| `python main.py --collect` | 최근 7일 논문 수집 |
| `python main.py --collect --from-date 2024-01-01` | 특정 날짜 이후 전체 수집 |
| `python main.py --translate` | 미번역 논문 번역 |
| `python main.py --analyze` | 트렌드 분석 |
| `python main.py` | 전체 파이프라인 실행 |

---

## DB 동기화 (다른 컴퓨터로 이동 시)

**방법 A: Google Drive / OneDrive (권장)**
- `data/papers.db` 파일을 Google Drive에 업로드
- 다른 컴퓨터에서 Drive에서 다운로드 후 `data/` 폴더에 복사

**방법 B: DB 재구축**
- `python main.py --collect --from-date 2024-01-01` 로 처음부터 수집

---

## 기술 스택

- **수집**: OpenAlex, Semantic Scholar, CrossRef, PubMed, arXiv (무료 API)
- **분석**: Google Gemini API (`gemini-3.1-flash-lite-preview`, 무료 티어)
- **저장**: SQLite
- **대시보드**: Streamlit + Plotly
