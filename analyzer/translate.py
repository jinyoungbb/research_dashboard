"""
초록·제목 한국어 번역기
- 미번역 논문 초록+제목을 Gemini Flash Lite로 일괄 번역
- 번역 결과 즉시 DB 캐싱 (재번역 금지)
- 수집 파이프라인에서 자동 호출
"""

import logging
import time

from google import genai
from google.genai import errors as genai_errors

from config import GEMINI_API_KEY, SUMMARY_MODEL
from storage.database import get_all_papers, save_abstract_ko, save_title_ko

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=GEMINI_API_KEY)

TRANSLATE_PROMPT = """\
다음 학술 논문의 제목과 초록을 한국어로 번역하세요.
- 학술 용어는 한국어(영문 병기) 형식으로 작성
- 원문의 문장 구조와 의미를 최대한 유지
- 아래 형식으로만 출력 (설명 없이):

제목: [번역된 제목]
초록: [번역된 초록]

---
제목(영문): {title}
초록(영문): {abstract}"""

TITLE_ONLY_PROMPT = """\
다음 학술 논문 제목을 한국어로 번역하세요. 번역된 제목만 출력하세요.

{title}"""


_rpd_exhausted = False  # 일일 한도 소진 플래그


def _call(prompt: str) -> str:
    """Gemini API 호출. RPM 초과 시 60초 대기 재시도. RPD 초과 시 즉시 반환."""
    global _rpd_exhausted
    if _rpd_exhausted:
        return ""
    try:
        response = _client.models.generate_content(model=SUMMARY_MODEL, contents=prompt)
        return response.text.strip()
    except genai_errors.ClientError as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            if "PerDay" in err or "perDay" in err:
                logger.error("일일 번역 한도(500 RPD) 소진 — 내일 --translate 로 재실행")
                _rpd_exhausted = True
                return ""
            logger.warning("분당 rate limit (RPM) — 60초 대기 후 재시도")
            time.sleep(60)
            return _call(prompt)
        logger.error(f"Gemini API 오류: {e}")
        return ""
    except Exception as e:
        logger.error(f"Gemini API 호출 실패: {e}")
        return ""


def _translate_pair(title: str, abstract: str) -> tuple[str, str]:
    """제목+초록 동시 번역. (title_ko, abstract_ko) 반환."""
    text = _call(TRANSLATE_PROMPT.format(title=title, abstract=abstract))
    if not text:
        return "", ""
    title_ko, abstract_ko = "", ""
    for line in text.split("\n"):
        if line.startswith("제목:"):
            title_ko = line[3:].strip()
        elif line.startswith("초록:"):
            abstract_ko = line[3:].strip()
    # 멀티라인 초록 처리
    if not abstract_ko and "초록:" in text:
        abstract_ko = text.split("초록:", 1)[1].strip()
    return title_ko, abstract_ko


def _translate_title_only(title: str) -> str:
    """제목만 번역 (초록 없는 논문용)."""
    return _call(TITLE_ONLY_PROMPT.format(title=title))


def translate_all(force: bool = False) -> int:
    """
    미번역 논문 전체 번역 (제목 + 초록).

    Args:
        force: True면 이미 번역된 논문도 재번역

    Returns:
        번역 완료 건수
    """
    papers = get_all_papers()
    targets = [
        p for p in papers
        if force or not p.get("title_ko")
    ]

    total = len(targets)
    if total == 0:
        logger.info("번역할 논문 없음 (모두 번역 완료)")
        return 0

    logger.info(f"번역 시작: 총 {total}편")
    done = 0

    for i, p in enumerate(targets, 1):
        title    = p.get("title", "")
        abstract = p.get("abstract", "")
        pid      = p["id"]

        if abstract:
            title_ko, abstract_ko = _translate_pair(title, abstract)
            if title_ko:
                save_title_ko(pid, title_ko)
            if abstract_ko:
                save_abstract_ko(pid, abstract_ko)
            if title_ko or abstract_ko:
                done += 1
        elif title:
            title_ko = _translate_title_only(title)
            if title_ko:
                save_title_ko(pid, title_ko)
                done += 1

        if i % 10 == 0 or i == total:
            logger.info(f"번역 진행: {i}/{total}편 완료")
        if _rpd_exhausted:
            logger.warning(f"일일 번역 한도 소진 — {i}/{total}편에서 중단")
            break
        time.sleep(4.0)  # 15 RPM 준수 (60초 / 15 = 4초)

    logger.info(f"번역 완료: {done}/{total}편")
    return done


def translate_new(paper_ids: list[int]) -> int:
    """
    신규 논문만 번역 (파이프라인 자동 호출용).
    """
    from storage.database import get_paper_by_id

    done = 0
    for pid in paper_ids:
        p = get_paper_by_id(pid)
        if not p or p.get("title_ko"):
            continue
        title    = p.get("title", "")
        abstract = p.get("abstract", "")

        if abstract:
            title_ko, abstract_ko = _translate_pair(title, abstract)
            if title_ko:   save_title_ko(pid, title_ko)
            if abstract_ko: save_abstract_ko(pid, abstract_ko)
            if title_ko or abstract_ko: done += 1
        elif title:
            title_ko = _translate_title_only(title)
            if title_ko:
                save_title_ko(pid, title_ko)
                done += 1

        if _rpd_exhausted:
            logger.warning("일일 번역 한도 소진 — 번역 중단")
            break
        time.sleep(4.0)  # 15 RPM 준수

    logger.info(f"신규 번역 완료: {done}편")
    return done
