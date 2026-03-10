"""
자동 스케줄러
- CRAWL_INTERVAL=weekly → 매주 월요일 09:00 실행
- CRAWL_INTERVAL=daily  → 매일 09:00 실행
- python scheduler.py 로 백그라운드 실행
"""

import logging
import time

import schedule

from config import CRAWL_INTERVAL
from main import run_collect, run_analyze, run_report
from storage.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def pipeline():
    logger.info("스케줄 실행 시작")
    try:
        init_db()
        collect_summary = run_collect()
        trend_results = run_analyze()
        run_report(trend_results)
        # 수집 후 미번역 논문 번역 (500 RPD 한도 내)
        from main import run_translate
        run_translate()
    except Exception as e:
        logger.error(f"파이프라인 실행 오류: {e}", exc_info=True)


def main():
    init_db()

    schedule.every().saturday.at("22:00").do(pipeline)
    logger.info("스케줄 등록: 매주 토요일 22:00")

    logger.info("스케줄러 대기 중... (종료: Ctrl+C)")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
