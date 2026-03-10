"""
SQLite DB 관리
- papers 테이블 초기화
- 논문 저장 (DOI 기준 중복 방지)
- 미분석 논문 조회
- 분석 결과 저장
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config import DB_PATH


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    """DB 및 테이블 초기화 (최초 1회)"""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                doi              TEXT UNIQUE,
                title            TEXT NOT NULL,
                authors          TEXT,            -- JSON 배열
                journal          TEXT,
                journal_tag      TEXT,            -- CS / LIS
                publication_date TEXT,
                keywords         TEXT,            -- JSON 배열
                abstract         TEXT,
                abstract_ko      TEXT,            -- 한국어 번역 캐시
                source_api       TEXT,            -- 수집 출처
                collected_at     TEXT,
                is_analyzed      INTEGER DEFAULT 0,
                trend_summary    TEXT
            )
        """)
        # 기존 DB 마이그레이션: 누락 컬럼 추가
        cols = [r[1] for r in con.execute("PRAGMA table_info(papers)").fetchall()]
        if "abstract_ko" not in cols:
            con.execute("ALTER TABLE papers ADD COLUMN abstract_ko TEXT")
        if "title_ko" not in cols:
            con.execute("ALTER TABLE papers ADD COLUMN title_ko TEXT")
        con.execute("CREATE INDEX IF NOT EXISTS idx_doi ON papers(doi)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_journal ON papers(journal)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_analyzed ON papers(is_analyzed)")


def exists(doi: str | None, title: str, journal: str, pub_date: str) -> bool:
    """DOI 또는 (제목+저널+날짜) 기준 중복 체크"""
    with _conn() as con:
        if doi:
            row = con.execute(
                "SELECT 1 FROM papers WHERE doi = ?", (doi,)
            ).fetchone()
            if row:
                return True
        row = con.execute(
            "SELECT 1 FROM papers WHERE title = ? AND journal = ? AND publication_date = ?",
            (title, journal, pub_date),
        ).fetchone()
        return row is not None


def save_paper(
    title: str,
    journal: str,
    journal_tag: str,
    authors: list[str],
    publication_date: str,
    keywords: list[str],
    abstract: str,
    doi: str | None,
    source_api: str,
) -> bool:
    """
    신규 논문 저장. 중복이면 False 반환.
    """
    if exists(doi, title, journal, publication_date):
        return False

    with _conn() as con:
        con.execute(
            """
            INSERT INTO papers
                (doi, title, authors, journal, journal_tag,
                 publication_date, keywords, abstract,
                 source_api, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doi,
                title,
                json.dumps(authors, ensure_ascii=False),
                journal,
                journal_tag,
                publication_date,
                json.dumps(keywords, ensure_ascii=False),
                abstract,
                source_api,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    return True


def get_unanalyzed(journal: str | None = None) -> list[dict]:
    """
    미분석(is_analyzed=0) 논문 목록 반환.
    journal 지정 시 해당 저널만 반환.
    """
    with _conn() as con:
        if journal:
            rows = con.execute(
                "SELECT * FROM papers WHERE is_analyzed = 0 AND journal = ?",
                (journal,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM papers WHERE is_analyzed = 0"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_paper_by_id(paper_id: int) -> dict | None:
    """ID로 논문 단건 조회"""
    with _conn() as con:
        row = con.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return _row_to_dict(row) if row else None


def save_abstract_ko(paper_id: int, abstract_ko: str):
    """한국어 초록 번역 저장"""
    with _conn() as con:
        con.execute(
            "UPDATE papers SET abstract_ko = ? WHERE id = ?",
            (abstract_ko, paper_id),
        )


def save_title_ko(paper_id: int, title_ko: str):
    """한국어 제목 번역 저장"""
    with _conn() as con:
        con.execute(
            "UPDATE papers SET title_ko = ? WHERE id = ?",
            (title_ko, paper_id),
        )


def mark_analyzed(paper_id: int, summary: str):
    """분석 완료 표시 및 요약 저장"""
    with _conn() as con:
        con.execute(
            "UPDATE papers SET is_analyzed = 1, trend_summary = ? WHERE id = ?",
            (summary, paper_id),
        )


def get_papers_by_period(from_date: str, to_date: str) -> list[dict]:
    """수집일(collected_at) 기준으로 논문 조회 (리포트 생성용)"""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM papers
            WHERE collected_at >= ? AND collected_at <= ?
            ORDER BY journal, publication_date DESC
            """,
            (from_date, to_date + "T23:59:59"),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_all_papers() -> list[dict]:
    """전체 논문 조회 (리포트 생성용 fallback)"""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM papers ORDER BY journal, publication_date DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def stats() -> dict:
    """전체 통계 반환"""
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        analyzed = con.execute(
            "SELECT COUNT(*) FROM papers WHERE is_analyzed = 1"
        ).fetchone()[0]
        by_tag = con.execute(
            "SELECT journal_tag, COUNT(*) FROM papers GROUP BY journal_tag"
        ).fetchall()
    return {
        "total": total,
        "analyzed": analyzed,
        "unanalyzed": total - analyzed,
        "by_tag": {r[0]: r[1] for r in by_tag},
    }


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("authors", "keywords"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                d[field] = []
    return d
