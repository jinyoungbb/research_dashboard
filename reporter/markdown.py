"""
Markdown 리포트 생성기
- 날짜 범위 내 수집 논문 + 분석 결과를 Markdown 파일로 저장
- reports/YYYY-MM-DD.md
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from config import REPORTS_DIR, TARGET_JOURNALS
from storage.database import get_papers_by_period, stats

logger = logging.getLogger(__name__)

# 저널명 → 태그 매핑
_TAG_MAP = {j["name"]: j["tag"] for j in TARGET_JOURNALS}


def generate(
    trend_results: dict[str, list[str]],
    from_date: str | None = None,
    to_date: str | None = None,
) -> Path:
    """
    리포트 생성.

    Args:
        trend_results: analyze_all() 반환값 {"저널명": ["요약1", ...]}
        from_date: 리포트 기간 시작 "YYYY-MM-DD"
        to_date:   리포트 기간 종료 "YYYY-MM-DD"

    Returns:
        생성된 리포트 파일 경로
    """
    today = date.today().isoformat()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = (date.today() - timedelta(days=7)).isoformat()

    from storage.database import get_all_papers
    papers = get_papers_by_period(from_date, to_date)
    if not papers:
        papers = get_all_papers()  # 기간 내 논문 없으면 전체 조회
    db_stats = stats()

    # 저널별 논문 그룹화
    by_journal: dict[str, list[dict]] = defaultdict(list)
    for p in papers:
        by_journal[p["journal"]].append(p)

    # DB에 저장된 트렌드 요약 병합 (--report 단독 실행 시 활용)
    for journal, journal_papers in by_journal.items():
        if journal not in trend_results:
            summaries = [
                p["trend_summary"]
                for p in journal_papers
                if p.get("trend_summary")
            ]
            # 중복 제거
            seen: set[str] = set()
            unique = []
            for s in summaries:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            if unique:
                trend_results[journal] = unique

    # 태그별 저널 그룹화
    cs_journals = [j for j in by_journal if _TAG_MAP.get(j) == "CS"]
    lis_journals = [j for j in by_journal if _TAG_MAP.get(j) == "LIS"]

    lines: list[str] = []

    # ── 헤더 ──────────────────────────────────────────────────────────
    lines += [
        f"# 연구동향 리포트 — {today}",
        "",
        "## 요약",
        f"- **수집 기간**: {from_date} ~ {to_date}",
        f"- **총 수집 논문**: {db_stats['total']}편 (이번 기간: {len(papers)}편)",
        f"- **분석 저널**: {len(by_journal)}개",
        f"- CS 분야: {db_stats['by_tag'].get('CS', 0)}편 | LIS 분야: {db_stats['by_tag'].get('LIS', 0)}편",
        "",
        "---",
        "",
    ]

    # ── CS 분야 ───────────────────────────────────────────────────────
    if cs_journals:
        lines += ["## CS 분야", ""]
        for journal in cs_journals:
            lines += _journal_section(journal, by_journal[journal], trend_results.get(journal, []))

    # ── LIS 분야 ──────────────────────────────────────────────────────
    if lis_journals:
        lines += ["## LIS 분야", ""]
        for journal in lis_journals:
            lines += _journal_section(journal, by_journal[journal], trend_results.get(journal, []))

    # ── 전체 키워드 순위 ──────────────────────────────────────────────
    lines += _keyword_section(papers)

    content = "\n".join(lines)
    report_path = REPORTS_DIR / f"{today}.md"
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"리포트 생성 완료: {report_path}")
    return report_path


def _journal_section(journal: str, papers: list[dict], summaries: list[str]) -> list[str]:
    lines = [
        f"### {journal}",
        "",
        f"**수집 논문**: {len(papers)}편",
        "",
    ]

    if summaries:
        lines += ["**트렌드 분석**", ""]
        for s in summaries:
            lines.append(s)
        lines.append("")

    if papers:
        lines += ["**논문 목록**", ""]
        for p in papers[:10]:  # 최대 10편만 표시
            doi = p.get("doi")
            title = p.get("title", "")
            authors = p.get("authors", [])
            author_str = ", ".join(authors[:2])
            if len(authors) > 2:
                author_str += " 외"
            pub_date = p.get("publication_date", "")
            if doi:
                lines.append(f"- [{title}](https://doi.org/{doi}) — {author_str} ({pub_date})")
            else:
                lines.append(f"- {title} — {author_str} ({pub_date})")
        if len(papers) > 10:
            lines.append(f"- *... 외 {len(papers) - 10}편*")
        lines.append("")

    lines.append("---")
    lines.append("")
    return lines


def _keyword_section(papers: list[dict]) -> list[str]:
    from collections import Counter

    counter: Counter = Counter()
    for p in papers:
        for kw in p.get("keywords", []):
            if kw:
                counter[kw.lower()] += 1

    if not counter:
        return []

    top = counter.most_common(20)
    lines = [
        "## 전체 키워드 Top 20",
        "",
        "| 순위 | 키워드 | 빈도 |",
        "|------|--------|------|",
    ]
    for rank, (kw, cnt) in enumerate(top, 1):
        lines.append(f"| {rank} | {kw} | {cnt} |")
    lines += ["", "---", ""]
    return lines
