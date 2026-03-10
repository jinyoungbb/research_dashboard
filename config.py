"""
프로젝트 전역 설정
- TARGET_JOURNALS: 모니터링 대상 저널 목록
- 환경변수 로드
- 경로 상수
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 경로 ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "papers.db"

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ── API 키 ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")  # Polite pool 진입용

# ── 모델 선택 ─────────────────────────────────────────────────────────
SUMMARY_MODEL  = "gemini-3.1-flash-lite-preview"   # 무료: 15 RPM, 500 RPD
ANALYSIS_MODEL = "gemini-3.1-flash-lite-preview"   # 심층 분석 (필요 시만)

# ── 수집 설정 ─────────────────────────────────────────────────────────
CRAWL_INTERVAL = os.getenv("CRAWL_INTERVAL", "weekly")  # daily / weekly
BATCH_SIZE = 15          # Claude API에 한 번에 보낼 초록 수
API_RETRY_MAX = 3        # API 호출 최대 재시도 횟수
API_SLEEP_SEC = 1.0      # API 호출 간격 (초)

# ── 모니터링 학술지 목록 ──────────────────────────────────────────────
TARGET_JOURNALS = [
    # ── CS 분야 (17개) ────────────────────────────────────────────────
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

    # ── LIS 분야 (9개) ────────────────────────────────────────────────
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
    {
        "name": "Quantitative Science Studies",
        "url": "https://direct.mit.edu/qss",
        "tag": "LIS",
    },
    {
        "name": "Research Evaluation",
        "url": "https://academic.oup.com/rev",
        "tag": "LIS",
    },
    {
        "name": "Journal of Informetrics",
        "url": "https://www.sciencedirect.com/journal/journal-of-informetrics",
        "tag": "LIS",
    },
    {
        "name": "Scientometrics",
        "url": "https://link.springer.com/journal/11192",
        "tag": "LIS",
    },
]
