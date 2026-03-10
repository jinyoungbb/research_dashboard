"""
연구동향 대시보드 (Streamlit)
실행: streamlit run dashboard.py
"""

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime

from google import genai
from google.genai import errors as genai_errors
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from config import DB_PATH, SUMMARY_MODEL, TARGET_JOURNALS
from storage.database import (
    get_all_papers,
    get_paper_by_id,
    init_db,
    save_abstract_ko,
    save_title_ko,
    stats,
)

# ── 페이지 설정 ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="학술지 연구동향 대시보드",
    page_icon="📚",
    layout="wide",
)

# 사이드바 너비 확장 (줄바꿈 방지)
st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 300px !important; max-width: 300px !important; }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
.block-container { padding-top: 2.5rem !important; }
/* 탭 균등 분할 + 글씨 크기 */
[data-testid="stTabs"] [role="tablist"] { display: flex; }
[data-testid="stTabs"] [role="tab"] {
    flex: 1;
    text-align: center;
    font-size: 1.05rem !important;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

init_db()

TAG_MAP   = {j["name"]: j["tag"] for j in TARGET_JOURNALS}
TAG_COLOR = {"CS": "#4C72B0", "LIS": "#DD8452"}
PAGES     = ["🔍 트렌드 분석", "📰 저널별 현황", "🏷️ 키워드", "📄 논문 목록"]

# ── 세션 상태 초기화 ──────────────────────────────────────────────────
for k, v in [("page", PAGES[0]), ("focus_journal", None), ("focus_paper", None)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── 데이터 로드 ───────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_papers():
    import sqlite3
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM papers ORDER BY publication_date DESC").fetchall()
    con.close()
    result = []
    for r in rows:
        d = dict(r)
        for f in ("authors", "keywords"):
            try:    d[f] = json.loads(d[f]) if d.get(f) else []
            except: d[f] = []
        result.append(d)
    return result


def refresh():
    st.cache_data.clear()
    st.rerun()


def goto_papers(journal: str | None = None, paper_id: int | None = None):
    st.session_state.page          = "📄 논문 목록"
    st.session_state.focus_journal = journal
    st.session_state.focus_paper   = paper_id
    st.rerun()


# ── 번역 (Gemini, DB 캐싱) ────────────────────────────────────────────
def _gemini():
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))


def translate_paper(paper: dict) -> tuple[str, str]:
    """
    제목+초록 번역. (title_ko, abstract_ko) 반환.
    실패 시 ("", "오류 메시지") 반환 — 예외를 밖으로 던지지 않음.
    """
    title    = paper.get("title", "")
    abstract = paper.get("abstract", "")
    pid      = paper["id"]
    prompt   = f"""다음 학술 논문의 제목과 초록을 한국어로 번역하세요.
학술 용어는 한국어(영문 병기) 형식. 아래 형식으로만 출력:

제목: [번역된 제목]
초록: [번역된 초록]

---
제목(영문): {title}
초록(영문): {abstract or '없음'}"""
    try:
        response = _gemini().models.generate_content(model=SUMMARY_MODEL, contents=prompt)
        text = response.text.strip()
        title_ko, abstract_ko = "", ""
        for line in text.split("\n"):
            if line.startswith("제목:"):
                title_ko = line[3:].strip()
            elif line.startswith("초록:"):
                abstract_ko = line[3:].strip()
        if not abstract_ko and "초록:" in text:
            abstract_ko = text.split("초록:", 1)[1].strip()
        if title_ko:    save_title_ko(pid, title_ko)
        if abstract_ko: save_abstract_ko(pid, abstract_ko)
        return title_ko, abstract_ko
    except Exception as e:
        err = str(e)
        if "PerDay" in err or "RESOURCE_EXHAUSTED" in err:
            return "", "⚠️ 일일 번역 한도(500건) 소진 — 내일 다시 시도해주세요"
        return "", f"번역 실패: {e}"


# ── 주목 논문 제목 → DB 매칭 ──────────────────────────────────────────
def _extract_notable_titles(summary: str) -> list[str]:
    """
    trend_summary에서 주목 논문 제목 추출.
    지원 포맷:
      A. > **① title** or > **title**           (DSS, CHB 포맷)
      B. ### emoji **논문 N** — *title*          (ESA 포맷)
      C. emoji 논문 N — title                    (일반 텍스트)
      D. **"title"**                             (따옴표 포함 굵은 텍스트)
    """
    titles: list[str] = []

    # 포맷 A: > **[①②③]? title** — 인용블록 + 굵은 제목 (CHB/DSS)
    for m in re.finditer(
        r'^\s*>\s*\*\*[①②③④⑤]?\s*(.{10,200}?)\*\*\s*$',
        summary, re.MULTILINE,
    ):
        t = m.group(1).strip()
        if len(t.split()) >= 3:
            titles.append(t)

    # 포맷 B: [—–] *title* or [—–] **title** — em-dash 뒤 이탤릭/굵은 제목 (ESA)
    for m in re.finditer(
        r'[—–]\s*\*{1,2}(.{10,200}?)\*{1,2}\s*$',
        summary, re.MULTILINE,
    ):
        t = m.group(1).strip()
        if len(t.split()) >= 3:
            titles.append(t)

    # 포맷 C: 이모지 + [논문 번호] + [—–] + 일반 텍스트 제목
    for m in re.finditer(
        r'[🔍📌🔬⭐✨🏥🏗️]\s*(?:논문\s*)?[\d①②③④⑤]+\s*[—–]\s*(.{10,200})',
        summary,
    ):
        t = m.group(1).strip().strip('*_').strip()
        if len(t.split()) >= 3:
            titles.append(t)

    # 포맷 D: **「title」** 또는 **"title"** — 꺽쇠/따옴표+굵은 제목 (JMIS, I&M 등)
    # 닫는 괄호 뒤에 (논문 N) 같은 부가 정보가 올 수 있음
    for m in re.finditer(r'\*\*["\u201c\u300c「](.{10,200}?)["\u201d\u300d」][^*\n]{0,30}\*\*', summary):
        titles.append(m.group(1).strip())

    # 포맷 E: 📌/🔹 ①②③ "quoted title" — 번호+따옴표 제목 (JBR 포맷)
    for m in re.finditer(r'[📌🔹]\s*[①②③④⑤]\s+"(.{10,200}?)"', summary):
        titles.append(m.group(1).strip())

    # 포맷 F: 📌/🔹 ①②③ plain title (줄 끝까지) — IJIM 포맷
    for m in re.finditer(
        r'[📌🔹]\s*[①②③④⑤]\s+(?!")(.{10,200}?)(?:\s*\(논문|\s*$)',
        summary, re.MULTILINE,
    ):
        t = m.group(1).strip().rstrip('*').strip()
        if len(t.split()) >= 4:
            titles.append(t)

    # 포맷 G: 📌 **title** ( — 굵은 단축 제목 + 괄호 저자 (JOM 포맷)
    for m in re.finditer(r'📌\s*\*\*(.{5,100}?)\*\*\s*\(', summary):
        t = m.group(1).strip()
        if len(t.split()) >= 2:
            titles.append(t)

    # 중복 제거 (순서 유지)
    seen, unique = set(), []
    for t in titles:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    return unique


def _word_overlap(a: str, b: str) -> float:
    """두 문자열의 단어 중복 비율 (Jaccard)."""
    wa = set(re.sub(r'[^\w\s]', '', a.lower()).split())
    wb = set(re.sub(r'[^\w\s]', '', b.lower()).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def find_notable_papers(summary: str, journal_papers: list[dict]) -> list[dict]:
    """trend_summary에서 주목 논문 추출 후 DB 매칭."""
    candidates = _extract_notable_titles(summary)
    matched, seen_ids = [], set()

    for cand in candidates:
        cand_l = cand.lower().strip()
        best_paper, best_score = None, 0.0

        for p in journal_papers:
            if p["id"] in seen_ids:
                continue
            title_l = p.get("title", "").lower()

            # 완전 포함 매칭 (가장 강한 신호)
            if cand_l in title_l or title_l in cand_l:
                best_paper, best_score = p, 1.0
                break

            # 단어 중복 유사도
            score = _word_overlap(cand_l, title_l)
            if score > best_score:
                best_score, best_paper = score, p

        if best_paper and best_score >= 0.35:
            matched.append((best_score, best_paper))
            seen_ids.add(best_paper["id"])

    # 스코어 내림차순 정렬 후 최대 3편
    matched.sort(key=lambda x: -x[0])
    return [p for _, p in matched[:3]]


# ══════════════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("연구동향 에이전트")
    st.divider()

    all_p = load_papers()  # 필터 목록 구성용 (DB 기준)

    if "page" not in st.session_state:
        st.session_state.page = PAGES[0]
    page = st.radio("메뉴", PAGES, index=PAGES.index(st.session_state.page),
                    label_visibility="collapsed")
    st.session_state.page = page
    st.divider()

    tag_filter     = st.multiselect("분야", ["CS", "LIS"], default=["CS", "LIS"])
    journal_filter = st.multiselect(
        "저널", sorted({p["journal"] for p in all_p if p.get("journal")}),
        default=[], placeholder="전체 저널",
    )
    keyword_search = st.text_input("키워드 검색", placeholder="예: AI, fairness")

    # 출판 날짜 필터
    st.markdown("**출판 기간**")
    dates = [p["publication_date"] for p in all_p if p.get("publication_date")]
    min_date = datetime.strptime(min(dates), "%Y-%m-%d").date() if dates else date(2024, 1, 1)
    max_date = datetime.strptime(max(dates), "%Y-%m-%d").date() if dates else date.today()
    date_from = st.date_input("시작", value=min_date, min_value=min_date, max_value=max_date)
    date_to   = st.date_input("종료", value=max_date, min_value=min_date, max_value=max_date)

    st.divider()
    if st.button("🔄 새로고침", use_container_width=True):
        refresh()

    db_stats = stats()
    all_papers_for_stats = load_papers()
    no_trans = sum(1 for p in all_papers_for_stats if not p.get("title_ko"))
    st.caption(f"총 {db_stats['total']:,}편 | 분석 {db_stats['analyzed']:,}편")
    st.caption(f"CS {db_stats['by_tag'].get('CS',0):,}편 | LIS {db_stats['by_tag'].get('LIS',0):,}편")
    if no_trans:
        st.caption(f"🇰🇷 미번역 {no_trans:,}편 (논문 목록에서 개별 번역 가능, 500건/일 한도)")


# ── 필터링 ────────────────────────────────────────────────────────────
filtered = load_papers()
if tag_filter:
    filtered = [p for p in filtered if p.get("journal_tag") in tag_filter]
if journal_filter:
    filtered = [p for p in filtered if p["journal"] in journal_filter]
if keyword_search:
    # 쉼표 또는 공백으로 구분 → AND 조건 검색
    terms = [t.strip() for t in keyword_search.replace(",", " ").split() if t.strip()]
    # 단일 검색어가 저널명과 정확히 일치하면 저널 필터로 동작
    if len(terms) == 1:
        journal_exact = [p for p in filtered if p.get("journal","").lower() == terms[0].lower()]
        if journal_exact:
            filtered = journal_exact
            terms = []
    def _match(p, term):
        t = term.lower()
        return (t in p.get("title","").lower()
                or t in (p.get("title_ko") or "").lower()
                or t in (p.get("abstract") or "").lower()
                or t in (p.get("abstract_ko") or "").lower()
                or any(t in k.lower() for k in p.get("keywords",[])))
    if terms:
        filtered = [p for p in filtered if all(_match(p, t) for t in terms)]
filtered = [
    p for p in filtered
    if p.get("publication_date","") >= str(date_from)
    and p.get("publication_date","") <= str(date_to)
]

# ── 상단 지표 ─────────────────────────────────────────────────────────
st.title("📊 학술지 연구동향 대시보드")
st.caption(f"기준일: {date.today().isoformat()}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 논문",   f"{len(filtered):,}편")
c2.metric("CS 분야",   f"{sum(1 for p in filtered if TAG_MAP.get(p['journal'])=='CS'):,}편")
c3.metric("LIS 분야",  f"{sum(1 for p in filtered if TAG_MAP.get(p['journal'])=='LIS'):,}편")
c4.metric("분석 완료", f"{sum(1 for p in filtered if p.get('is_analyzed')):,}편")

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════
# 페이지: 트렌드 분석
# ══════════════════════════════════════════════════════════════════════
if page == PAGES[0]:
    analyzed = [p for p in filtered if p.get("trend_summary")]
    if not analyzed:
        st.info("분석된 논문이 없습니다. `python main.py --analyze` 를 실행하세요.")
    else:
        by_journal: dict[str, list[dict]] = defaultdict(list)
        for p in analyzed:
            by_journal[p["journal"]].append(p)

        summaries: dict[str, str] = {}
        for j, papers in by_journal.items():
            for p in papers:
                if p.get("trend_summary") and j not in summaries:
                    summaries[j] = p["trend_summary"]

        for tag in ["CS", "LIS"]:
            tag_journals = [j for j in summaries if TAG_MAP.get(j) == tag]
            if not tag_journals:
                continue
            st.subheader(f"{'🖥️' if tag=='CS' else '📖'} {tag} 분야")

            for journal in tag_journals:
                j_papers = by_journal[journal]
                notable  = find_notable_papers(summaries[journal], j_papers)

                with st.expander(f"**{journal}** ({len(j_papers):,}편)", expanded=False):

                    # ── 본문 요약 ──────────────────────────────────
                    sum_col, nav_col = st.columns([3, 1])

                    with sum_col:
                        st.markdown(summaries[journal])

                    # ── 주목 논문 바로가기 (오른쪽 패널) ───────────
                    with nav_col:
                        if notable:
                            st.markdown("#### 🔗 주목 논문 바로가기")
                            for i, np_ in enumerate(notable, 1):
                                t   = np_.get("title", "")
                                tko = np_.get("title_ko", "")
                                doi = np_.get("doi")
                                # 제목 표시
                                st.markdown(
                                    f"**{i}.** {f'[{t}](https://doi.org/{doi})' if doi else t}"
                                )
                                if tko:
                                    st.caption(tko)
                                # 논문 목록으로 이동 버튼
                                if st.button(
                                    "📄 논문 상세 보기",
                                    key=f"nb_{np_['id']}",
                                    use_container_width=True,
                                    type="primary",
                                ):
                                    goto_papers(journal=journal, paper_id=np_["id"])
                                st.divider()
                        else:
                            st.caption("주목 논문 자동 매칭 결과 없음")

                    # ── 수록 논문 전체 목록 ────────────────────────
                    with st.expander("📄 수록 논문 전체 목록 펼치기", expanded=False):
                        for p in sorted(j_papers,
                                        key=lambda x: x.get("publication_date",""),
                                        reverse=True):
                            doi_  = p.get("doi")
                            t_    = p.get("title","")
                            tko_  = p.get("title_ko","")
                            date_ = p.get("publication_date","")
                            col_a, col_b = st.columns([5, 1])
                            with col_a:
                                link = f"[{t_}](https://doi.org/{doi_})" if doi_ else t_
                                st.markdown(f"- {link} `{date_}`")
                                if tko_:
                                    st.caption(f"  {tko_}")
                            with col_b:
                                if st.button("상세", key=f"tr_{p['id']}",
                                             use_container_width=True):
                                    goto_papers(journal=journal, paper_id=p["id"])


# ══════════════════════════════════════════════════════════════════════
# 페이지: 저널별 현황
# ══════════════════════════════════════════════════════════════════════
elif page == PAGES[1]:
    journal_counts: Counter = Counter(p["journal"] for p in filtered)

    if not journal_counts:
        st.info("수집된 논문이 없습니다.")
    else:
        journals = sorted(journal_counts, key=lambda j: journal_counts[j], reverse=True)
        colors   = [TAG_COLOR.get(TAG_MAP.get(j), "#999") for j in journals]

        fig = go.Figure(go.Bar(
            x=[journal_counts[j] for j in journals],
            y=journals, orientation="h",
            marker_color=colors,
            text=[journal_counts[j] for j in journals],
            textposition="outside",
        ))
        for tag, color in TAG_COLOR.items():
            fig.add_trace(go.Bar(x=[None], y=[None], marker_color=color,
                                 name=tag, showlegend=True))
        fig.update_layout(
            title="저널별 수집 논문 수", xaxis_title="논문 수",
            height=max(400, len(journals) * 28),
            margin=dict(l=0, r=50, t=40, b=20),
            plot_bgcolor="white", yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("저널별 상세")
        for j in journals:
            j_papers     = [p for p in filtered if p["journal"] == j]
            analyzed_cnt = sum(1 for p in j_papers if p.get("is_analyzed"))
            col_a, col_b, col_c, col_d = st.columns([1, 4, 2, 2])
            col_a.markdown(f"`{TAG_MAP.get(j,'-')}`")
            col_b.markdown(f"**{j}**")
            col_c.markdown(f"{journal_counts[j]:,}편 (분석 {analyzed_cnt:,}편)")
            if col_d.button("논문 목록 보기", key=f"jv_{j}", use_container_width=True):
                goto_papers(journal=j)


# ══════════════════════════════════════════════════════════════════════
# 페이지: 키워드
# ══════════════════════════════════════════════════════════════════════
elif page == PAGES[2]:
    col_a, col_b = st.columns([1, 3])
    with col_a:
        top_n  = st.slider("Top N", 5, 50, 20)
        tag_kw = st.radio("분야", ["전체","CS","LIS"], horizontal=True)

    kw_papers = filtered if tag_kw == "전체" else [
        p for p in filtered if TAG_MAP.get(p["journal"]) == tag_kw
    ]
    kw_counter: Counter = Counter()
    for p in kw_papers:
        for kw in p.get("keywords", []):
            if kw and len(kw) > 1:
                kw_counter[kw.lower()] += 1

    if not kw_counter:
        st.info("키워드 데이터가 없습니다.")
    else:
        top_kw = kw_counter.most_common(top_n)
        labels = [k for k, _ in top_kw]
        vals   = [v for _, v in top_kw]
        fig_kw = go.Figure(go.Bar(
            x=vals[::-1], y=labels[::-1], orientation="h",
            marker_color="#4C72B0", text=vals[::-1], textposition="outside",
        ))
        fig_kw.update_layout(
            title=f"Top {top_n} 키워드 ({tag_kw})",
            height=max(300, top_n * 22),
            margin=dict(l=0, r=50, t=40, b=20),
            plot_bgcolor="white",
        )
        with col_b:
            st.plotly_chart(fig_kw, use_container_width=True)
        st.dataframe([{"키워드": k, "빈도": v} for k, v in top_kw],
                     use_container_width=True, hide_index=True, height=400)


# ══════════════════════════════════════════════════════════════════════
# 페이지: 논문 목록
# ══════════════════════════════════════════════════════════════════════
elif page == PAGES[3]:
    focus_j = st.session_state.focus_journal
    focus_p = st.session_state.focus_paper

    display_papers = filtered
    if focus_j:
        display_papers = [p for p in filtered if p["journal"] == focus_j]
        st.info(f"필터 적용됨: **{focus_j}**")
        if st.button("✕ 필터 해제"):
            st.session_state.focus_journal = None
            st.session_state.focus_paper   = None
            st.rerun()

    # 정렬/필터 변경 시 페이지 초기화
    if "prev_filter_sig" not in st.session_state:
        st.session_state.prev_filter_sig = ""
    cur_sig = f"{tag_filter}{journal_filter}{keyword_search}{date_from}{date_to}{focus_j}"
    if cur_sig != st.session_state.prev_filter_sig:
        st.session_state.paper_page = 1
        st.session_state.prev_filter_sig = cur_sig

    col_sort, col_cnt = st.columns([3, 1])
    sort_opt = col_sort.selectbox(
        "정렬", ["출판일 (최신순)", "출판일 (오래된순)", "저널명", "수집일 (최신순)"],
        label_visibility="collapsed",
    )
    col_cnt.markdown(f"**{len(display_papers):,}편** 표시 중")

    key_map = {
        "출판일 (최신순)":  (lambda p: p.get("publication_date",""), True),
        "출판일 (오래된순)":(lambda p: p.get("publication_date",""), False),
        "저널명":           (lambda p: p.get("journal",""),          False),
        "수집일 (최신순)":  (lambda p: p.get("collected_at",""),     True),
    }
    fn, rev = key_map[sort_opt]
    display_papers = sorted(display_papers, key=fn, reverse=rev)

    # ── 페이지네이션 ──────────────────────────────────────────────
    PAGE_SIZE = 50
    total_pages = max(1, (len(display_papers) - 1) // PAGE_SIZE + 1)
    if "paper_page" not in st.session_state:
        st.session_state.paper_page = 1
    if st.session_state.paper_page > total_pages:
        st.session_state.paper_page = 1

    def _pagination_bar(key_suffix: str):
        c1, c2, c3 = st.columns([1, 3, 1])
        if c1.button("◀ 이전", key=f"prev_{key_suffix}",
                     disabled=st.session_state.paper_page <= 1):
            st.session_state.paper_page -= 1
            st.rerun()
        c2.markdown(
            f"<div style='text-align:center'>{st.session_state.paper_page} / {total_pages} 페이지</div>",
            unsafe_allow_html=True)
        if c3.button("다음 ▶", key=f"next_{key_suffix}",
                     disabled=st.session_state.paper_page >= total_pages):
            st.session_state.paper_page += 1
            st.rerun()

    _pagination_bar("top")

    start = (st.session_state.paper_page - 1) * PAGE_SIZE
    display_papers = display_papers[start: start + PAGE_SIZE]

    st.divider()

    for p in display_papers:
        pid         = p["id"]
        tag         = TAG_MAP.get(p["journal"], "")
        doi         = p.get("doi")
        title       = p.get("title", "제목 없음")
        title_ko    = p.get("title_ko", "")
        abstract    = p.get("abstract") or ""
        abstract_ko = p.get("abstract_ko") or ""
        is_focused  = focus_p and pid == focus_p
        icon        = "🖥️" if tag == "CS" else "📖"

        # ── 항상 표시: 저널 정보 + 전체 제목 ────────────────────────
        st.markdown(
            f"{icon} `{tag}` &nbsp;│&nbsp; **{p.get('journal','')}** &nbsp;│&nbsp; `{p.get('publication_date','')[:10]}`",
            unsafe_allow_html=True,
        )
        title_link = f"[{title}](https://doi.org/{doi})" if doi else title
        st.markdown(title_link)

        # ── 한국어 제목 또는 번역 버튼 ───────────────────────────
        if title_ko:
            st.caption(f"🇰🇷 {title_ko}")
        elif abstract:
            tr_col, _ = st.columns([2, 8])
            with tr_col:
                if st.button("🇰🇷 번역", key=f"tr_btn_{pid}", use_container_width=True):
                    with st.spinner("번역 중..."):
                        tk, msg = translate_paper(p)
                    if tk:
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            st.caption("_초록 없음 · 번역 불가_")

        # ── 클릭해서 열기: 저자·초록·키워드 ─────────────────────
        with st.expander("📋 저자 · 초록 · 키워드", expanded=bool(is_focused)):
            left, right = st.columns([3, 1])

            with right:
                st.markdown(f"**분야**: {tag}")
                st.markdown(f"**출판일**: {p.get('publication_date','')}")
                st.markdown(f"**수집일**: {(p.get('collected_at') or '')[:10]}")
                if doi:
                    st.markdown(f"**DOI**: [{doi}](https://doi.org/{doi})")
                keywords = p.get("keywords", [])
                if keywords:
                    st.markdown("**키워드**")
                    st.markdown(" ".join(f"`{k}`" for k in keywords[:10]))
                if p.get("is_analyzed"):
                    st.success("트렌드 분석 완료 ✅")

            with left:
                authors = p.get("authors", [])
                if authors:
                    auth_str = ", ".join(authors[:4])
                    if len(authors) > 4: auth_str += f" 외 {len(authors)-4}명"
                    st.markdown(f"**저자**: {auth_str}")

                if abstract:
                    with st.expander("📄 원문 초록 (영문)", expanded=False):
                        st.markdown(abstract)
                else:
                    st.caption("_초록 없음_")

                if abstract_ko:
                    with st.expander("🇰🇷 한국어 초록", expanded=bool(is_focused)):
                        st.markdown(abstract_ko)

        st.divider()

    _pagination_bar("bottom")
