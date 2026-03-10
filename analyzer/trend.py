"""
Gemini API 트렌드 분석기
- 미분석 논문 초록을 BATCH_SIZE 단위로 묶어 한 번에 전송
- 분석 결과를 DB에 캐싱 (재분석 금지)
- 저널별 트렌드 요약 반환
"""

import logging
import time
from collections import defaultdict

from google import genai
from google.genai import errors as genai_errors

from config import BATCH_SIZE, GEMINI_API_KEY, SUMMARY_MODEL
from storage.database import get_unanalyzed, mark_analyzed

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=GEMINI_API_KEY)

TREND_PROMPT = """\
다음은 [{journal}]에 최근 게재된 {n}편의 논문 목록입니다.

{abstracts}

위 논문들을 분석하여 **한글**로 답하세요:

1. **주요 연구 트렌드** (3줄 이내 요약)
2. **자주 등장한 키워드 Top 5** (표 형식)
3. **주목할 논문 2~3편** (제목 + 한 줄 요약)
"""


def _build_abstracts_text(papers: list[dict]) -> str:
    lines = []
    for i, p in enumerate(papers, 1):
        title = p.get("title", "")
        abstract = p.get("abstract", "") or "초록 없음"
        authors = ", ".join(p.get("authors", [])[:3])
        if len(p.get("authors", [])) > 3:
            authors += " 외"
        lines.append(f"{i}. **{title}**\n   저자: {authors}\n   초록: {abstract[:400]}")
    return "\n\n".join(lines)


_rpd_exhausted = False  # 일일 한도 소진 플래그


def _call_gemini(journal: str, papers: list[dict]) -> str:
    """Gemini API 호출 (배치). Rate limit 시 60초 대기 후 재시도."""
    global _rpd_exhausted
    if _rpd_exhausted:
        return ""
    abstracts_text = _build_abstracts_text(papers)
    prompt = TREND_PROMPT.format(
        journal=journal,
        n=len(papers),
        abstracts=abstracts_text,
    )
    try:
        response = _client.models.generate_content(model=SUMMARY_MODEL, contents=prompt)
        return response.text
    except genai_errors.ClientError as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            if "PerDay" in err or "perDay" in err:
                logger.error(f"일일 분석 한도(500 RPD) 소진 ({journal}) — 내일 --analyze 로 재실행")
                _rpd_exhausted = True
                return ""
            logger.warning(f"분당 rate limit ({journal}) — 60초 대기 후 재시도")
            time.sleep(60)
            return _call_gemini(journal, papers)
        logger.error(f"Gemini API 오류 ({journal}): {e}")
        return ""
    except Exception as e:
        logger.error(f"Gemini API 호출 실패 ({journal}): {e}")
        return ""


def analyze_all() -> dict[str, list[str]]:
    """
    전체 미분석 논문 분석.
    저널별로 BATCH_SIZE 단위 배치 처리.

    Returns:
        {"저널명": ["배치1 요약", "배치2 요약", ...]}
    """
    unanalyzed = get_unanalyzed()
    if not unanalyzed:
        logger.info("분석할 논문 없음 (모두 분석 완료)")
        return {}

    # 저널별 그룹화
    by_journal: dict[str, list[dict]] = defaultdict(list)
    for p in unanalyzed:
        by_journal[p["journal"]].append(p)

    results: dict[str, list[str]] = {}

    for journal, papers in by_journal.items():
        journal_summaries = []
        # BATCH_SIZE 단위로 나누어 처리
        for i in range(0, len(papers), BATCH_SIZE):
            batch = papers[i : i + BATCH_SIZE]
            logger.info(f"분석 중: {journal} ({i+1}~{i+len(batch)}편)")
            summary = _call_gemini(journal, batch)
            if summary:
                journal_summaries.append(summary)
                # 배치 내 각 논문에 요약 저장
                for p in batch:
                    mark_analyzed(p["id"], summary)
            else:
                logger.warning(f"분석 실패: {journal} 배치 {i//BATCH_SIZE + 1}")
            if _rpd_exhausted:
                logger.warning("일일 분석 한도 소진 — 분석 중단")
                break
            time.sleep(4.0)  # 15 RPM 준수

        if journal_summaries:
            results[journal] = journal_summaries
            logger.info(f"분석 완료: {journal} ({len(papers)}편)")

    return results


def analyze_journal(journal: str) -> list[str]:
    """특정 저널만 분석"""
    papers = get_unanalyzed(journal=journal)
    if not papers:
        return []

    summaries = []
    for i in range(0, len(papers), BATCH_SIZE):
        batch = papers[i : i + BATCH_SIZE]
        summary = _call_gemini(journal, batch)
        if summary:
            summaries.append(summary)
            for p in batch:
                mark_analyzed(p["id"], summary)
        if _rpd_exhausted:
            logger.warning("일일 분석 한도 소진 — 분석 중단")
            break
        time.sleep(4.0)  # 15 RPM 준수
    return summaries
