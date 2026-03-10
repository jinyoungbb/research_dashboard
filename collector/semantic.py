"""
Semantic Scholar API 수집기 (보조 경로)
- OpenAlex 커버 안 되는 저널 보완용
- 저널명 기반 논문 검색
"""

import time
import logging

import httpx

from config import API_RETRY_MAX, API_SLEEP_SEC, SEMANTIC_SCHOLAR_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,year,publicationDate,abstract,externalIds,venue,fieldsOfStudy"


def _headers() -> dict:
    if SEMANTIC_SCHOLAR_API_KEY:
        return {"x-api-key": SEMANTIC_SCHOLAR_API_KEY}
    return {}


def _get_with_retry(params: dict) -> dict | None:
    for attempt in range(1, API_RETRY_MAX + 1):
        try:
            resp = httpx.get(BASE_URL, params=params, headers=_headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Semantic Scholar 요청 실패 ({attempt}/{API_RETRY_MAX}): {e}")
            if attempt < API_RETRY_MAX:
                time.sleep(2 ** attempt)
    return None


def fetch(journal_name: str, from_year: int | None = None, max_results: int = 50) -> list[dict]:
    """
    저널명으로 논문 수집.

    Args:
        journal_name: 저널 표시명
        from_year: 수집 시작 연도 (기본: 현재 연도)
        max_results: 최대 수집 건수
    """
    import datetime
    if from_year is None:
        from_year = datetime.date.today().year

    params = {
        "query": journal_name,
        "fields": FIELDS,
        "limit": min(max_results, 100),
        "publicationDateOrYear": f"{from_year}-",
    }

    data = _get_with_retry(params)
    if not data:
        logger.error(f"[SemanticScholar] {journal_name} 수집 실패")
        return []

    results = []
    for paper in data.get("data", []):
        title = paper.get("title") or ""
        if not title:
            continue

        # 저널명 필터 (venue가 일치하는 것만)
        venue = paper.get("venue") or ""
        if journal_name.lower() not in venue.lower():
            continue

        authors = [a.get("name", "") for a in paper.get("authors", [])]
        doi = (paper.get("externalIds") or {}).get("DOI")
        pub_date = paper.get("publicationDate") or str(paper.get("year", ""))

        results.append(
            {
                "title": title,
                "authors": authors,
                "publication_date": pub_date,
                "keywords": [],
                "abstract": paper.get("abstract") or "",
                "doi": doi or None,
                "source_api": "semantic_scholar",
            }
        )

    logger.info(f"[SemanticScholar] {journal_name}: {len(results)}편 수집")
    time.sleep(API_SLEEP_SEC)
    return results
