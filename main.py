"""
진입점: 수집 → 번역 → 분석 → 리포트 순서 실행
사용법:
    python main.py               # 전체 파이프라인 실행
    python main.py --collect     # 수집만 (번역 포함)
    python main.py --translate   # 미번역 초록 일괄 번역
    python main.py --analyze     # 분석만
    python main.py --report      # 리포트만
    python main.py --stats       # DB 통계 출력
"""

import argparse
import logging
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_collect(days: int = 7, from_date: str | None = None) -> dict:
    from collector.base import collect_all
    if from_date:
        logger.info(f"=== 수집 시작 (from {from_date}) ===")
        summary = collect_all(from_date=from_date)
    else:
        logger.info(f"=== 수집 시작 (최근 {days}일) ===")
        summary = collect_all(days=days)
    total = sum(summary.values())
    logger.info(f"=== 수집 완료: 총 {total}편 신규 저장 ===")
    return summary


def run_analyze() -> dict:
    from analyzer.trend import analyze_all
    logger.info("=== 분석 시작 ===")
    results = analyze_all()
    logger.info(f"=== 분석 완료: {len(results)}개 저널 ===")
    return results


def run_report(trend_results: dict, days: int = 7) -> str:
    from reporter.markdown import generate
    from_date = (date.today() - timedelta(days=days)).isoformat()
    to_date = date.today().isoformat()
    logger.info("=== 리포트 생성 시작 ===")
    path = generate(trend_results, from_date=from_date, to_date=to_date)
    logger.info(f"=== 리포트 생성 완료: {path} ===")
    return str(path)


def run_translate(force: bool = False, priority_keyword: str | None = None) -> int:
    from analyzer.translate import translate_all
    logger.info("=== 초록 한국어 번역 시작 ===")
    done = translate_all(force=force, priority_keyword=priority_keyword)
    logger.info(f"=== 번역 완료: {done}편 ===")
    return done


def run_stats():
    from storage.database import stats
    s = stats()
    print("\n── DB 통계 ──────────────────────")
    print(f"  전체 논문: {s['total']}편")
    print(f"  분석 완료: {s['analyzed']}편")
    print(f"  미분석:    {s['unanalyzed']}편")
    for tag, cnt in s["by_tag"].items():
        print(f"  [{tag}]:     {cnt}편")
    print("─────────────────────────────────\n")


def main():
    from storage.database import init_db
    init_db()

    parser = argparse.ArgumentParser(description="학술지 연구동향 수집 에이전트")
    parser.add_argument("--collect",   action="store_true", help="수집만 실행 (번역 포함)")
    parser.add_argument("--translate", action="store_true", help="미번역 초록 일괄 번역")
    parser.add_argument("--analyze",   action="store_true", help="분석만 실행")
    parser.add_argument("--report",    action="store_true", help="리포트만 생성")
    parser.add_argument("--stats",     action="store_true", help="DB 통계 출력")
    parser.add_argument("--days",      type=int, default=7, help="수집 기간 (일, 기본 7)")
    parser.add_argument("--from-date", type=str, default=None, dest="from_date", help="수집 시작일 YYYY-MM-DD (--days보다 우선)")
    parser.add_argument("--force",            action="store_true", help="번역 강제 재실행")
    parser.add_argument("--priority-keyword", type=str, default=None, dest="priority_keyword", help="번역 우선순위 키워드 (해당 키워드 포함 논문 먼저)")
    args = parser.parse_args()

    # 단독 실행 옵션
    if args.stats:
        run_stats()
        return

    if args.translate and not args.collect and not args.analyze:
        run_translate(force=args.force, priority_keyword=args.priority_keyword)
        return

    if args.collect and not args.analyze and not args.report:
        run_collect(days=args.days, from_date=args.from_date)
        return

    if args.analyze and not args.collect and not args.report:
        run_analyze()
        return

    if args.report and not args.collect and not args.analyze:
        run_report({}, days=args.days)
        return

    # 기본: 전체 파이프라인 (수집 → 번역 → 분석 → 리포트)
    logger.info("===== 학술지 연구동향 에이전트 시작 =====")
    collect_summary = run_collect(days=args.days)   # 번역 포함
    trend_results   = run_analyze()
    report_path     = run_report(trend_results, days=args.days)
    run_stats()
    print(f"\n리포트 저장 위치: {report_path}")
    logger.info("===== 완료 =====")


if __name__ == "__main__":
    main()
