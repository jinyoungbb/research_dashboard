"""
수집기 오케스트레이터
- 저널별로 OpenAlex 우선 시도
- 결과 없으면 Semantic Scholar fallback
- DB 저장 및 중복 방지
"""

import logging
from datetime import date, timedelta

import sqlite3
from config import TARGET_JOURNALS, DB_PATH
from storage.database import save_paper
from collector import openalex, semantic

logger = logging.getLogger(__name__)


def _get_new_paper_ids(titles: list[str]) -> list[int]:
    """방금 저장된 논문 ID 목록 조회"""
    if not titles:
        return []
    con = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(titles))
    rows = con.execute(
        f"SELECT id FROM papers WHERE title IN ({placeholders})", titles
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def collect_all(days: int = 7, from_date: str | None = None) -> dict[str, int]:
    """
    모든 TARGET_JOURNALS 수집 실행.
    수집 후 신규 논문 자동 번역.

    Args:
        days: 며칠 전부터 수집할지
        from_date: 수집 시작일 직접 지정 "YYYY-MM-DD" (지정 시 days 무시)

    Returns:
        {"저널명": 신규 저장 건수} 딕셔너리
    """
    if from_date is None:
        from_date = (date.today() - timedelta(days=days)).isoformat()
    summary: dict[str, int] = {}
    new_titles: list[str] = []

    for journal in TARGET_JOURNALS:
        name = journal["name"]
        tag  = journal["tag"]
        saved = 0

        logger.info(f"수집 시작: [{tag}] {name}")

        papers = openalex.fetch(name, from_date=from_date)
        if not papers:
            logger.info(f"OpenAlex 결과 없음 → Semantic Scholar fallback: {name}")
            papers = semantic.fetch(name)

        for p in papers:
            ok = save_paper(
                title=p["title"],
                journal=name,
                journal_tag=tag,
                authors=p["authors"],
                publication_date=p["publication_date"],
                keywords=p["keywords"],
                abstract=p["abstract"],
                doi=p["doi"],
                source_api=p["source_api"],
            )
            if ok:
                saved += 1
                new_titles.append(p["title"])

        logger.info(f"완료: {name} → 신규 {saved}편 저장")
        summary[name] = saved

    total = sum(summary.values())
    logger.info(f"전체 수집 완료: 총 {total}편 신규 저장")

    # 신규 논문 자동 번역 (일일 한도 초과 시 graceful 종료)
    if new_titles:
        logger.info(f"신규 논문 {total}편 자동 번역 시작")
        try:
            from analyzer.translate import translate_new
            new_ids = _get_new_paper_ids(new_titles)
            translate_new(new_ids)
        except Exception as e:
            logger.warning(f"자동 번역 중단 (나중에 python main.py --translate 로 재실행): {e}")

    return summary
