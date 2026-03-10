"""
OpenAlex API 수집기 (기본 수집 경로)
- 저널명 → 소스 ID 변환 후 works 필터링 (2단계)
- abstract_inverted_index → 일반 텍스트 초록으로 변환
- 소스 ID 캐싱으로 반복 조회 방지
"""

import time
import logging
from datetime import date, timedelta

import httpx

from config import API_RETRY_MAX, API_SLEEP_SEC, OPENALEX_EMAIL

logger = logging.getLogger(__name__)

SOURCES_URL = "https://api.openalex.org/sources"
WORKS_URL   = "https://api.openalex.org/works"

# 수집 제외할 비논문 제목 패턴 (소문자 비교)
_SKIP_PATTERNS = [
    "cover image", "issue information", "editorial board",
    "table of contents", "front matter", "back matter",
    "author index", "subject index", "corrigendum", "erratum",
    "editor's comments", "editor's introduction",
]


def _is_non_paper(title: str) -> bool:
    t = title.lower().strip()
    return any(t == p or t.startswith(p) for p in _SKIP_PATTERNS)

# 소스 ID 인메모리 캐시 {저널명: source_id}
_source_id_cache: dict[str, str] = {}


def _invert_abstract(inverted: dict | None) -> str:
    """OpenAlex abstract_inverted_index → 일반 텍스트 변환"""
    if not inverted:
        return ""
    index: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        for pos in positions:
            index.append((pos, word))
    index.sort()
    return " ".join(word for _, word in index)


def _get_with_retry(url: str, params: dict) -> dict | None:
    """최대 API_RETRY_MAX회 재시도"""
    for attempt in range(1, API_RETRY_MAX + 1):
        try:
            resp = httpx.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"OpenAlex 요청 실패 ({attempt}/{API_RETRY_MAX}): {e}")
            if attempt < API_RETRY_MAX:
                time.sleep(2 ** attempt)
    return None


def _get_source_id(journal_name: str) -> str | None:
    """
    저널명으로 OpenAlex 소스 ID 조회.
    인메모리 캐싱으로 중복 조회 방지.
    """
    if journal_name in _source_id_cache:
        return _source_id_cache[journal_name]

    params = {"search": journal_name, "per_page": 5}
    if OPENALEX_EMAIL:
        params["mailto"] = OPENALEX_EMAIL

    data = _get_with_retry(SOURCES_URL, params)
    if not data:
        return None

    # 이름이 가장 유사한 소스 선택
    for source in data.get("results", []):
        if source.get("display_name", "").lower() == journal_name.lower():
            sid = source["id"].replace("https://openalex.org/", "")
            _source_id_cache[journal_name] = sid
            logger.info(f"소스 ID 확인: {journal_name} → {sid}")
            return sid

    # 완전 일치 없으면 첫 번째 결과 사용
    results = data.get("results", [])
    if results:
        sid = results[0]["id"].replace("https://openalex.org/", "")
        found_name = results[0].get("display_name", "")
        _source_id_cache[journal_name] = sid
        logger.info(f"소스 ID (근사 매칭): {journal_name} → {sid} ({found_name})")
        return sid

    logger.warning(f"소스 ID 미발견: {journal_name}")
    return None


def _parse_work(work: dict) -> dict | None:
    """OpenAlex work 항목 → 논문 딕셔너리 변환. 비논문이면 None 반환."""
    title = work.get("title") or ""
    if not title or _is_non_paper(title):
        return None
    authors = [
        a["author"]["display_name"]
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    keywords = [k["display_name"] for k in work.get("keywords", [])]
    abstract = _invert_abstract(work.get("abstract_inverted_index"))
    doi = work.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    return {
        "title": title,
        "authors": authors,
        "publication_date": work.get("publication_date", ""),
        "keywords": keywords,
        "abstract": abstract,
        "doi": doi or None,
        "source_api": "openalex",
    }


def fetch(journal_name: str, from_date: str | None = None, max_results: int = 2000) -> list[dict]:
    """
    저널명으로 논문 수집 (커서 기반 페이지네이션).

    Args:
        journal_name: 저널 표시명 (예: "MIS Quarterly")
        from_date: 수집 시작일 "YYYY-MM-DD" (기본: 7일 전)
        max_results: 최대 수집 건수

    Returns:
        논문 딕셔너리 리스트
    """
    if from_date is None:
        from_date = (date.today() - timedelta(days=7)).isoformat()

    source_id = _get_source_id(journal_name)
    if not source_id:
        logger.error(f"[OpenAlex] 소스 ID 조회 실패: {journal_name}")
        return []

    time.sleep(API_SLEEP_SEC)

    results: list[dict] = []
    cursor = "*"

    while len(results) < max_results:
        params = {
            "filter": f"primary_location.source.id:{source_id},from_publication_date:{from_date}",
            "select": "title,authorships,publication_date,keywords,abstract_inverted_index,doi",
            "per_page": 200,
            "sort": "publication_date:desc",
            "cursor": cursor,
        }
        if OPENALEX_EMAIL:
            params["mailto"] = OPENALEX_EMAIL

        data = _get_with_retry(WORKS_URL, params)
        if not data:
            logger.error(f"[OpenAlex] {journal_name} works 조회 실패 (cursor={cursor})")
            break

        page = data.get("results", [])
        if not page:
            break

        for work in page:
            parsed = _parse_work(work)
            if parsed:
                results.append(parsed)

        # 다음 커서 확인
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor
        time.sleep(API_SLEEP_SEC)

    logger.info(f"[OpenAlex] {journal_name}: {len(results)}편 수집")
    time.sleep(API_SLEEP_SEC)
    return results
