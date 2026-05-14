"""
ui/admin_tab_rag_tuning.py  ─  RAG 튜닝 & 검증 탭 (v1.0)  2026-05-14
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[존재 이유]
  챗봇이 원하는 답을 못 찾을 때 관리자가 원인을 진단·튜닝하는 화면.

[3개 서브 탭]
  🧪 쿼리 테스트
    - 질문 직접 입력 → RAGPipeline.run_with_mode() 실행 (LLM 없이)
    - 쿼리 변환 단계 시각화 (원문 → 정규화 → 확장 쿼리)
    - 검색된 문서 테이블 (순위·파일·페이지·CE점수·내용 미리보기)
    - 타이밍 breakdown (검색/리랭킹/전체)

  📊 질의 이력
    - search_evaluation.json 분석
    - 모드별 KPI (총 질의·평균 응답시간·평균 만족도·Precision)
    - 실패 질의 필터 (만족도 ≤ 2 또는 검색결과 0건)
    - 드릴다운: 질의별 검색 문서·LLM 답변 확인

  📖 용어 사전
    - 현재 TERM_MAP / EXPAND_MAP 표 (core/query_rewriter.py 로드)
    - 사용자 정의 추가 사전 (config/custom_terms.json) 편집
    - 추가 사전 포맷: {"구어체": "문서어"} / {"키워드": ["확장1","확장2"]}
    - 저장 시 query_rewriter 에 런타임 반영 (재시작 불필요)

[연동 파일]
  core/rag_pipeline.py   — RAGPipeline.run_with_mode()
  core/query_rewriter.py — TERM_MAP, EXPAND_MAP, QueryRewriter
  core/evaluator.py      — EvaluationLogger, EvaluationRecord
  config/custom_terms.json (없으면 자동 생성)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from ui.design import C, section_header, gap
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)

# ── 사용자 정의 사전 경로 ─────────────────────────────────────────────
_CUSTOM_TERMS_PATH: Path = _ROOT / "config" / "custom_terms.json"

# ── HTML 렌더 헬퍼 ────────────────────────────────────────────────────
def _html(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
#  CSS (탭 전용 추가 스타일)
# ════════════════════════════════════════════════════════════════════
_TAB_CSS = """
<style>
/* ── 쿼리 변환 단계 카드 ── */
.rt-step-card {
  background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px;
  padding:12px 16px; margin-bottom:10px;
}
.rt-step-label {
  font-size:11px; font-weight:700; letter-spacing:.06em;
  color:#64748B; text-transform:uppercase; margin-bottom:6px;
}
.rt-step-value {
  font-family:"IBM Plex Mono",monospace; font-size:13px;
  color:#0F172A; font-weight:600; word-break:break-word;
}
.rt-step-rule {
  font-size:11px; color:#94A3B8; margin-top:4px;
}
/* ── 적용 규칙 배지 ── */
.rt-rule-badge {
  display:inline-block; background:#EFF6FF; color:#1D4ED8;
  border:1px solid #BFDBFE; border-radius:20px;
  padding:1px 8px; font-size:10px; font-weight:700;
  margin-right:4px; margin-bottom:2px;
}
/* ── 검색 결과 문서 테이블 ── */
.rt-doc-tbl { width:100%; border-collapse:collapse; font-size:12.5px; }
.rt-doc-th {
  background:#F8FAFC; color:#475569; font-size:11px; font-weight:700;
  letter-spacing:.04em; padding:8px 10px; text-align:left;
  border-bottom:2px solid #E2E8F0; white-space:nowrap;
}
.rt-doc-td {
  padding:8px 10px; border-bottom:1px solid #F1F5F9;
  vertical-align:top; color:#1E293B;
}
.rt-doc-row:hover td { background:#F8FAFC; }
.rt-rank-badge {
  display:inline-block; width:22px; height:22px; line-height:22px;
  text-align:center; border-radius:50%;
  background:#1E40AF; color:#fff; font-size:11px; font-weight:700;
}
.rt-score-bar-wrap { height:6px; background:#F1F5F9; border-radius:3px; margin-top:3px; }
.rt-score-bar      { height:6px; border-radius:3px; background:#22C55E; }
.rt-score-lo       { background:#F59E0B; }
.rt-score-vlo      { background:#EF4444; }
.rt-preview {
  font-size:11.5px; color:#475569; line-height:1.55;
  display:-webkit-box; -webkit-line-clamp:3;
  -webkit-box-orient:vertical; overflow:hidden;
}
/* ── 타이밍 배지 ── */
.rt-timing-strip {
  display:flex; gap:8px; flex-wrap:wrap;
  background:#F8FAFC; border:1px solid #E2E8F0;
  border-radius:8px; padding:10px 14px; margin-top:10px;
}
.rt-timing-item { font-size:12px; color:#475569; }
.rt-timing-val  { font-family:monospace; font-weight:700; color:#0F172A; }
/* ── 이력 필터 배지 ── */
.rt-sat-badge {
  display:inline-block; border-radius:20px; padding:2px 8px;
  font-size:10px; font-weight:700; border:1px solid transparent;
}
.rt-sat-ok  { background:#DCFCE7; color:#166534; border-color:#BBF7D0; }
.rt-sat-mid { background:#FEF3C7; color:#92400E; border-color:#FDE68A; }
.rt-sat-bad { background:#FEE2E2; color:#991B1B; border-color:#FECACA; }
.rt-sat-na  { background:#F1F5F9; color:#64748B; border-color:#E2E8F0; }
/* ── 용어 사전 테이블 ── */
.rt-dict-tbl { width:100%; border-collapse:collapse; font-size:13px; }
.rt-dict-th {
  background:#F8FAFC; color:#475569; font-size:11px; font-weight:700;
  letter-spacing:.04em; padding:8px 12px; text-align:left;
  border-bottom:2px solid #E2E8F0;
}
.rt-dict-td { padding:8px 12px; border-bottom:1px solid #F1F5F9; }
.rt-dict-row:hover td { background:#F8FAFC; }
.rt-dict-src { font-family:monospace; color:#1E40AF; font-weight:600; }
.rt-dict-dst { color:#0F172A; }
.rt-custom-badge {
  display:inline-block; background:#FFF7ED; color:#C2410C;
  border:1px solid #FDBA74; border-radius:20px;
  padding:1px 7px; font-size:10px; font-weight:700;
}
</style>
"""


# ════════════════════════════════════════════════════════════════════
#  유틸리티 함수
# ════════════════════════════════════════════════════════════════════

def _load_vector_db():
    """VectorStoreManager 통해 FAISS DB 로드 (에러 시 None 반환).

    [2026-05-14] VectorStoreManager.__init__ 인수 3개 명시:
      db_path    → settings.rag_db_path
      model_name → settings.embedding_model
      cache_dir  → settings.local_cache_path
    """
    try:
        from core.vector_store import VectorStoreManager
        mgr = VectorStoreManager(
            db_path=settings.rag_db_path,
            model_name=settings.embedding_model,
            cache_dir=str(settings.local_cache_path),
        )
        return mgr.load()
    except Exception as exc:
        logger.warning(f"벡터DB 로드 실패: {exc}")
        return None


def _load_eval_records() -> List[Dict]:
    """search_evaluation.json 로드 → 최근 500건."""
    path = Path(settings.log_dir) / "search_evaluation.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[-500:]
        return []
    except Exception:
        return []


def _load_custom_terms() -> Dict[str, Any]:
    """config/custom_terms.json 로드."""
    if not _CUSTOM_TERMS_PATH.exists():
        return {"term_map": {}, "expand_map": {}}
    try:
        return json.loads(_CUSTOM_TERMS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"term_map": {}, "expand_map": {}}


def _save_custom_terms(data: Dict[str, Any]) -> bool:
    """config/custom_terms.json 저장 + QueryRewriter 런타임 반영."""
    try:
        _CUSTOM_TERMS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 런타임 반영: query_rewriter 모듈의 TERM_MAP / EXPAND_MAP 패치
        try:
            import core.query_rewriter as _qr
            for k, v in data.get("term_map", {}).items():
                _qr.TERM_MAP[k] = v
            for k, v in data.get("expand_map", {}).items():
                if isinstance(v, list):
                    _qr.EXPAND_MAP[k] = v
                else:
                    _qr.EXPAND_MAP[k] = [v]
        except Exception as e:
            logger.warning(f"QueryRewriter 런타임 반영 실패(재시작 시 반영): {e}")
        return True
    except Exception as exc:
        logger.error(f"custom_terms.json 저장 실패: {exc}")
        return False


def _score_bar_html(score: float) -> str:
    """CE 점수 0~1 → 컬러 바 HTML."""
    pct  = min(max(score * 100, 0), 100)
    cls  = "rt-score-vlo" if score < 0.1 else ("rt-score-lo" if score < 0.3 else "")
    return (
        f'<div class="rt-score-bar-wrap">'
        f'<div class="rt-score-bar {cls}" style="width:{pct:.0f}%;"></div>'
        f'</div>'
    )


def _sat_badge(sat: Optional[int]) -> str:
    """만족도 배지 HTML."""
    if sat is None:
        return '<span class="rt-sat-badge rt-sat-na">미응답</span>'
    if sat >= 4:
        return f'<span class="rt-sat-badge rt-sat-ok">{"⭐" * sat}</span>'
    if sat == 3:
        return f'<span class="rt-sat-badge rt-sat-mid">{"⭐" * sat}</span>'
    return f'<span class="rt-sat-badge rt-sat-bad">{"⭐" * sat}</span>'


# ════════════════════════════════════════════════════════════════════
#  서브 탭 1 — 쿼리 테스트
# ════════════════════════════════════════════════════════════════════

def _subtab_query_test() -> None:
    """질문을 직접 입력해 RAG 검색 단계를 단계별로 확인한다."""
    import html as _he

    gap(8)
    _html(
        '<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;'
        'padding:10px 14px;font-size:12.5px;color:#1D4ED8;margin-bottom:14px;">'
        '💡 챗봇에서 원하는 답을 못 찾았을 때, 같은 질문을 여기에 입력하면 '
        '검색 단계를 낱낱이 확인할 수 있습니다. <strong>LLM 호출은 하지 않습니다.</strong>'
        '</div>'
    )

    # ── 입력 영역 ───────────────────────────────────────────
    c1, c2, c3 = st.columns([5, 2, 2], gap="small")
    with c1:
        query = st.text_input(
            "질문 입력",
            placeholder="예: 연차 어떻게 써요? / 당직 수당 기준이 뭐야?",
            key="rtt_query",
        )
    with c2:
        mode = st.selectbox(
            "검색 모드",
            ["balanced", "fast", "deep"],
            key="rtt_mode",
            help="fast=빠른검색(CE없음) / balanced=표준(권장) / deep=심층(Multi-Query+CE)",
        )
    with c3:
        gap(24)
        run_btn = st.button("🔍 검색 테스트 실행", key="rtt_run", type="primary",
                            use_container_width=True, disabled=not query.strip())

    if not run_btn or not query.strip():
        if not query.strip():
            _html('<p style="color:#94A3B8;font-size:13px;padding:12px 0;">'
                  '위 입력란에 질문을 입력하고 버튼을 클릭하세요.</p>')
        return

    # ── 1단계: 쿼리 정규화 (QueryRewriter) ────────────────
    _html('<hr style="border:none;border-top:1px solid #F1F5F9;margin:16px 0 12px;">')
    _html('<div style="font-size:13px;font-weight:700;color:#0F172A;margin-bottom:10px;">'
          '① 쿼리 변환 (QueryRewriter)</div>')

    try:
        from core.query_rewriter import get_query_rewriter
        rw     = get_query_rewriter()
        t0     = time.time()
        rr     = rw.rewrite(query.strip())
        rw_ms  = (time.time() - t0) * 1000

        # 적용 규칙 배지
        rules_html = " ".join(
            f'<span class="rt-rule-badge">{_he.escape(r)}</span>'
            for r in (rr.rewrites_applied or [])
        ) or '<span style="color:#94A3B8;font-size:12px;">없음 (원문 그대로)</span>'

        rw_cards = [
            ("원본 질문",    query.strip(),       ""),
            ("정규화 쿼리",  rr.rewritten,         f'<div class="rt-step-rule">적용 규칙: {rules_html}</div>'),
            ("확장 쿼리",    rr.expanded,          f'<div class="rt-step-rule">BM25+FAISS 검색에 사용되는 최종 쿼리</div>'),
        ]
        cols = st.columns(3, gap="small")
        for (lbl, val, note), col in zip(rw_cards, cols):
            with col:
                _html(
                    f'<div class="rt-step-card">'
                    f'<div class="rt-step-label">{lbl}</div>'
                    f'<div class="rt-step-value">{_he.escape(val or "—")}</div>'
                    f'{note}'
                    f'</div>'
                )
    except Exception as exc:
        st.warning(f"QueryRewriter 오류: {exc}")
        rr = None

    # ── 2단계: 벡터DB 검색 (RAGPipeline) ─────────────────
    _html('<div style="font-size:13px;font-weight:700;color:#0F172A;'
          'margin:16px 0 10px;">② 벡터DB 검색 결과</div>')

    vdb = _load_vector_db()
    if vdb is None:
        st.error("벡터DB를 로드할 수 없습니다. 벡터DB 관리 탭에서 인덱스를 먼저 구축하세요.")
        return

    try:
        from core.rag_pipeline import RAGPipeline
        pipeline = RAGPipeline(vdb)
        t0  = time.time()
        res = pipeline.run_with_mode(query.strip(), mode=mode, use_cache=False)
        total_ms = (time.time() - t0) * 1000
    except Exception as exc:
        st.error(f"RAG 파이프라인 오류: {exc}")
        logger.error(f"RAG 튜닝 테스트 오류: {exc}", exc_info=True)
        return

    docs = res.ranked_docs

    # ── 결과 요약 KPI ───────────────────────────────────
    gap(4)
    s1, s2, s3, s4 = st.columns(4, gap="small")
    kpi_data = [
        (s1, "검색된 문서", str(len(docs)), "건",     C["blue"]   if docs else C["danger"]),
        (s2, "평균 CE 점수", f"{res.avg_score:.3f}", "",  C["ok"] if res.avg_score >= 0.3 else C["warn"]),
        (s3, "검색 시간",   f"{res.t_search_ms:.0f}", "ms", C["indigo"]),
        (s4, "리랭킹 시간", f"{res.t_rerank_ms:.0f}", "ms", C["indigo"]),
    ]
    for col, lbl, val, unit, color in kpi_data:
        with col:
            _html(
                f'<div class="fn-kpi" style="border-top:3px solid {color};">'
                f'<div class="fn-kpi-label">{lbl}</div>'
                f'<div class="fn-kpi-value" style="color:{color};">{val}'
                f'<span class="fn-kpi-unit">{unit}</span></div>'
                f'</div>'
            )

    gap(12)

    if not docs:
        _html(
            '<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;'
            'padding:16px 18px;">'
            '<div style="font-weight:700;color:#991B1B;margin-bottom:8px;">🔴 검색 결과 없음</div>'
            '<div style="font-size:13px;color:#7F1D1D;line-height:1.7;">'
            '<b>가능한 원인:</b><br>'
            '① 이 주제 관련 문서가 벡터DB에 없음 → <b>문서 관리 탭</b>에서 PDF 추가<br>'
            '② 구어체 ↔ 문서어 매핑 누락 → <b>용어 사전 탭</b>에서 TERM_MAP 추가<br>'
            '③ 벡터DB가 최신 문서를 반영하지 않음 → <b>벡터DB 관리 탭</b>에서 재구축'
            '</div>'
            '</div>'
        )
        return

    # ── 문서 테이블 ──────────────────────────────────────
    rows = []
    for d in docs:
        score   = float(d.score)
        preview = (d.document.page_content or "")[:200].replace("\n", " ")
        source  = _he.escape(d.source or "—")
        page    = _he.escape(str(d.page) if d.page else "—")
        article = _he.escape(d.article or "—")
        rows.append(
            f'<tr class="rt-doc-row">'
            f'<td class="rt-doc-td" style="text-align:center;">'
            f'  <span class="rt-rank-badge">{d.rank}</span>'
            f'</td>'
            f'<td class="rt-doc-td" style="font-size:12px;color:#3B82F6;">{source}</td>'
            f'<td class="rt-doc-td" style="font-family:monospace;font-size:12px;">{page}</td>'
            f'<td class="rt-doc-td" style="font-size:12px;">{article}</td>'
            f'<td class="rt-doc-td">'
            f'  <span style="font-family:monospace;font-weight:700;">{score:.4f}</span>'
            f'  {_score_bar_html(score)}'
            f'</td>'
            f'<td class="rt-doc-td"><div class="rt-preview">{_he.escape(preview)}</div></td>'
            f'</tr>'
        )
    head = (
        '<thead><tr>'
        '<th class="rt-doc-th" style="width:5%;">순위</th>'
        '<th class="rt-doc-th" style="width:18%;">파일</th>'
        '<th class="rt-doc-th" style="width:7%;">페이지</th>'
        '<th class="rt-doc-th" style="width:10%;">조항</th>'
        '<th class="rt-doc-th" style="width:12%;">CE 점수</th>'
        '<th class="rt-doc-th">내용 미리보기</th>'
        '</tr></thead>'
    )
    _html(
        f'<div style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;">'
        f'<table class="rt-doc-tbl">{head}<tbody>{"".join(rows)}</tbody></table>'
        f'</div>'
    )

    # ── 타이밍 상세 ──────────────────────────────────────
    gap(10)
    _html(
        f'<div class="rt-timing-strip">'
        f'<span class="rt-timing-item">🏷 파이프라인: '
        f'<span class="rt-timing-val">{_he.escape(res.pipeline_label)}</span></span>'
        f'&nbsp;│&nbsp;'
        f'<span class="rt-timing-item">🔍 검색: '
        f'<span class="rt-timing-val">{res.t_search_ms:.0f}ms</span></span>'
        f'&nbsp;│&nbsp;'
        f'<span class="rt-timing-item">⚖ 리랭킹: '
        f'<span class="rt-timing-val">{res.t_rerank_ms:.0f}ms</span></span>'
        f'&nbsp;│&nbsp;'
        f'<span class="rt-timing-item">⏱ 합계: '
        f'<span class="rt-timing-val">{total_ms:.0f}ms</span></span>'
        f'</div>'
    )

    # ── 진단 힌트 ─────────────────────────────────────────
    gap(14)
    if res.avg_score < 0.1:
        st.warning(
            "⚠️ CE 평균 점수가 매우 낮습니다 (< 0.10). "
            "검색된 문서가 질문과 관련이 없을 가능성이 높습니다. "
            "**용어 사전**에서 구어체→문서어 매핑을 추가하거나, "
            "**문서 관리**에서 관련 PDF를 추가하세요."
        )
    elif res.avg_score < 0.3:
        st.info(
            "ℹ️ CE 평균 점수가 낮습니다 (0.10 ~ 0.30). "
            "검색 모드를 **deep**으로 변경하거나 "
            "**용어 사전**에서 관련 매핑을 보강해 보세요."
        )


# ════════════════════════════════════════════════════════════════════
#  서브 탭 2 — 질의 이력
# ════════════════════════════════════════════════════════════════════

def _subtab_history() -> None:
    """search_evaluation.json 분석 — 실패 질의 탐색."""
    import html as _he

    records = _load_eval_records()
    if not records:
        st.info("질의 이력이 없습니다. 챗봇을 사용하면 자동으로 기록됩니다.")
        return

    total    = len(records)
    sat_vals = [r["satisfaction"] for r in records if r.get("satisfaction")]
    avg_sat  = sum(sat_vals) / len(sat_vals) if sat_vals else 0
    avg_lat  = sum(r.get("latency_ms", 0) for r in records) / total
    no_doc   = sum(1 for r in records if not r.get("retrieved_docs"))

    # ── KPI 카드 ─────────────────────────────────────────
    gap(4)
    k1, k2, k3, k4 = st.columns(4, gap="small")
    for col, label, val, unit, color in [
        (k1, "총 질의 수",    str(total),          "건", C["blue"]),
        (k2, "평균 만족도",   f"{avg_sat:.1f}",    "/5", C["ok"] if avg_sat >= 3.5 else C["warn"]),
        (k3, "평균 응답시간", f"{avg_lat:.0f}",    "ms", C["indigo"]),
        (k4, "검색 실패",     str(no_doc),         "건", C["danger"] if no_doc > 0 else C["ok"]),
    ]:
        with col:
            _html(
                f'<div class="fn-kpi" style="border-top:3px solid {color};">'
                f'<div class="fn-kpi-label">{label}</div>'
                f'<div class="fn-kpi-value" style="color:{color};">{val}'
                f'<span class="fn-kpi-unit">{unit}</span></div>'
                f'</div>'
            )

    gap(14)

    # ── 필터 ─────────────────────────────────────────────
    f1, f2, f3 = st.columns([2, 2, 3], gap="small")
    with f1:
        filter_mode = st.selectbox(
            "보기 필터",
            ["전체", "실패만 (만족도 ≤ 2)", "검색결과 없음", "만족도 미응답"],
            key="rth_filter",
        )
    with f2:
        filter_search_mode = st.selectbox(
            "검색 모드", ["전체", "fast", "balanced", "deep"],
            key="rth_mode",
        )
    with f3:
        kw = st.text_input(
            "질문 키워드", placeholder="질문 내용으로 검색...",
            key="rth_kw", label_visibility="collapsed",
        )

    # 필터 적용
    filtered = records[:]
    if filter_mode == "실패만 (만족도 ≤ 2)":
        filtered = [r for r in filtered if r.get("satisfaction") and r["satisfaction"] <= 2]
    elif filter_mode == "검색결과 없음":
        filtered = [r for r in filtered if not r.get("retrieved_docs")]
    elif filter_mode == "만족도 미응답":
        filtered = [r for r in filtered if r.get("satisfaction") is None]
    if filter_search_mode != "전체":
        filtered = [r for r in filtered if r.get("search_mode") == filter_search_mode]
    if kw.strip():
        kw_lo = kw.strip().lower()
        filtered = [r for r in filtered if kw_lo in r.get("question", "").lower()]

    # 최신순 정렬
    filtered = list(reversed(filtered))

    st.caption(f"필터 결과: {len(filtered):,}건 / 전체 {total:,}건")
    gap(6)

    # ── 이력 테이블 + 드릴다운 ───────────────────────────
    if not filtered:
        st.info("해당 조건의 질의 이력이 없습니다.")
        return

    for i, rec in enumerate(filtered[:100]):  # 최대 100건 표시
        sat   = rec.get("satisfaction")
        docs  = rec.get("retrieved_docs", [])
        lat   = rec.get("latency_ms", 0)
        q_txt = rec.get("question", "—")
        ts    = rec.get("timestamp", "")[:16].replace("T", " ")
        mode_val = rec.get("search_mode", "—")

        col_q, col_m, col_d, col_s, col_t = st.columns([5, 1, 1, 1, 1], gap="small")
        with col_q:
            st.markdown(f"**{_he.escape(q_txt[:80])}**")
            st.caption(f"{ts}  ·  검색어: {rec.get('search_query','—')[:40]}")
        with col_m:
            st.caption(mode_val)
        with col_d:
            doc_cnt = len(docs)
            color = "#EF4444" if doc_cnt == 0 else "#22C55E"
            st.markdown(
                f'<span style="color:{color};font-weight:700;">{doc_cnt}건</span>',
                unsafe_allow_html=True,
            )
        with col_s:
            _html(_sat_badge(sat))
        with col_t:
            st.caption(f"{lat:.0f}ms")

        # 드릴다운 expander
        with st.expander("상세 보기", expanded=False):
            if docs:
                rows = []
                for d in docs:
                    score = d.get("score", 0)
                    rows.append(
                        f'<tr class="rt-doc-row">'
                        f'<td class="rt-doc-td" style="font-size:11px;color:#94A3B8;">{d.get("rank","—")}</td>'
                        f'<td class="rt-doc-td" style="font-size:12px;color:#3B82F6;">'
                        f'{_he.escape(d.get("source","—"))}</td>'
                        f'<td class="rt-doc-td" style="font-family:monospace;font-size:11px;">'
                        f'p.{_he.escape(str(d.get("page","—")))}</td>'
                        f'<td class="rt-doc-td">'
                        f'  <span style="font-family:monospace;font-weight:700;">{score:.4f}</span>'
                        f'  {_score_bar_html(score)}'
                        f'</td>'
                        f'</tr>'
                    )
                head = (
                    '<thead><tr>'
                    '<th class="rt-doc-th">순위</th><th class="rt-doc-th">파일</th>'
                    '<th class="rt-doc-th">페이지</th><th class="rt-doc-th">CE 점수</th>'
                    '</tr></thead>'
                )
                _html(f'<table class="rt-doc-tbl">{head}<tbody>{"".join(rows)}</tbody></table>')
            else:
                _html('<p style="color:#EF4444;font-size:13px;">검색된 문서 없음</p>')

            # LLM 답변
            resp = rec.get("llm_response", "")
            if resp:
                st.markdown("**LLM 답변 요약:**")
                st.markdown(
                    f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                    f'border-radius:8px;padding:12px 14px;font-size:12.5px;color:#1E293B;">'
                    f'{_he.escape(resp[:500])}{"…" if len(resp) > 500 else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        _html('<div style="border-top:1px solid #F1F5F9;margin:6px 0;"></div>')


# ════════════════════════════════════════════════════════════════════
#  서브 탭 3 — 용어 사전
# ════════════════════════════════════════════════════════════════════

def _subtab_term_dict() -> None:
    """TERM_MAP / EXPAND_MAP 조회 + 사용자 정의 추가 사전 관리."""
    import html as _he

    _html(
        '<div style="background:#FFF7ED;border:1px solid #FDBA74;border-radius:8px;'
        'padding:10px 14px;font-size:12.5px;color:#C2410C;margin-bottom:14px;">'
        '📌 <b>용어 사전이란?</b> 챗봇 사용자가 "연차 어떻게 써요?" 처럼 구어체로 물으면 '
        '자동으로 "연차휴가 신청"으로 변환해 검색 정확도를 높입니다. '
        '원하는 답을 못 찾는다면 아래 <b>사용자 정의 사전</b>에 매핑을 추가하세요.'
        '</div>'
    )

    # ── 현재 TERM_MAP 표시 ───────────────────────────────
    try:
        from core.query_rewriter import TERM_MAP, EXPAND_MAP
    except Exception as exc:
        st.error(f"용어 사전 로드 실패: {exc}")
        return

    custom = _load_custom_terms()
    custom_keys_term   = set(custom.get("term_map", {}).keys())
    custom_keys_expand = set(custom.get("expand_map", {}).keys())

    st.subheader("구어체 → 문서어 사전 (TERM_MAP)")
    st.caption(f"현재 {len(TERM_MAP)}개 항목 등록됨")

    with st.expander("전체 목록 보기", expanded=False):
        rows = []
        for src, dst in sorted(TERM_MAP.items()):
            is_custom = src in custom_keys_term
            badge     = '<span class="rt-custom-badge">사용자 추가</span>' if is_custom else ""
            rows.append(
                f'<tr class="rt-dict-row">'
                f'<td class="rt-dict-td rt-dict-src">{_he.escape(src)}</td>'
                f'<td class="rt-dict-td" style="color:#94A3B8;">→</td>'
                f'<td class="rt-dict-td rt-dict-dst">{_he.escape(dst)}</td>'
                f'<td class="rt-dict-td">{badge}</td>'
                f'</tr>'
            )
        head = (
            '<thead><tr>'
            '<th class="rt-dict-th">구어체 (입력)</th>'
            '<th class="rt-dict-th"></th>'
            '<th class="rt-dict-th">문서어 (변환)</th>'
            '<th class="rt-dict-th">출처</th>'
            '</tr></thead>'
        )
        _html(
            f'<div style="max-height:360px;overflow-y:auto;border:1px solid #E2E8F0;'
            f'border-radius:8px;">'
            f'<table class="rt-dict-tbl">{head}<tbody>{"".join(rows)}</tbody></table>'
            f'</div>'
        )

    gap(10)

    # ── EXPAND_MAP 표시 ──────────────────────────────────
    st.subheader("키워드 확장 사전 (EXPAND_MAP)")
    st.caption(f"현재 {len(EXPAND_MAP)}개 항목 — 검색 시 관련 용어를 추가로 쿼리에 포함")

    with st.expander("전체 목록 보기", expanded=False):
        rows = []
        for src, exps in sorted(EXPAND_MAP.items()):
            is_custom = src in custom_keys_expand
            badge     = '<span class="rt-custom-badge">사용자 추가</span>' if is_custom else ""
            exp_str   = ", ".join(exps)
            rows.append(
                f'<tr class="rt-dict-row">'
                f'<td class="rt-dict-td rt-dict-src">{_he.escape(src)}</td>'
                f'<td class="rt-dict-td rt-dict-dst">{_he.escape(exp_str)}</td>'
                f'<td class="rt-dict-td">{badge}</td>'
                f'</tr>'
            )
        head = (
            '<thead><tr>'
            '<th class="rt-dict-th">키워드</th>'
            '<th class="rt-dict-th">확장 용어</th>'
            '<th class="rt-dict-th">출처</th>'
            '</tr></thead>'
        )
        _html(
            f'<div style="max-height:280px;overflow-y:auto;border:1px solid #E2E8F0;'
            f'border-radius:8px;">'
            f'<table class="rt-dict-tbl">{head}<tbody>{"".join(rows)}</tbody></table>'
            f'</div>'
        )

    gap(18)

    # ── 사용자 정의 사전 편집 ────────────────────────────
    st.subheader("✏️ 사용자 정의 사전 추가")

    d1, d2 = st.columns(2, gap="medium")

    with d1:
        st.markdown("**구어체 → 문서어 추가**")
        st.caption("입력한 구어체를 검색 시 문서어로 자동 변환합니다.")
        new_src  = st.text_input("구어체 (예: 월급날)", key="rtd_src")
        new_dst  = st.text_input("문서어 (예: 급여 지급일)",  key="rtd_dst")
        if st.button("➕ 추가 (TERM_MAP)", key="rtd_add_term", disabled=not new_src.strip()):
            data = _load_custom_terms()
            data.setdefault("term_map", {})[new_src.strip()] = new_dst.strip()
            if _save_custom_terms(data):
                st.success(f'"{new_src}" → "{new_dst}" 추가 완료 (즉시 적용)')
                st.rerun()
            else:
                st.error("저장 실패")

    with d2:
        st.markdown("**키워드 확장 추가**")
        st.caption("검색 시 이 키워드와 함께 확장 용어도 쿼리에 포함됩니다.")
        new_kw   = st.text_input("키워드 (예: 감염관리)",    key="rtd_kw")
        new_exps = st.text_input("확장 용어 (쉼표 구분, 예: 감염예방,격리지침)", key="rtd_exps")
        if st.button("➕ 추가 (EXPAND_MAP)", key="rtd_add_expand", disabled=not new_kw.strip()):
            exp_list = [e.strip() for e in new_exps.split(",") if e.strip()]
            if not exp_list:
                st.warning("확장 용어를 1개 이상 입력하세요.")
            else:
                data = _load_custom_terms()
                data.setdefault("expand_map", {})[new_kw.strip()] = exp_list
                if _save_custom_terms(data):
                    st.success(f'"{new_kw}" 확장 추가 완료 (즉시 적용)')
                    st.rerun()
                else:
                    st.error("저장 실패")

    gap(14)

    # 현재 사용자 정의 사전 목록 + 삭제
    cdata = _load_custom_terms()
    c_terms  = cdata.get("term_map", {})
    c_expand = cdata.get("expand_map", {})

    if c_terms or c_expand:
        st.markdown("**현재 사용자 정의 항목**")
        all_custom = (
            [(k, v, "term") for k, v in c_terms.items()] +
            [(k, ", ".join(v), "expand") for k, v in c_expand.items()]
        )
        for idx, (src, dst, kind) in enumerate(all_custom):
            cr, del_col = st.columns([8, 1], gap="small")
            with cr:
                kind_badge = (
                    '<span style="background:#DBEAFE;color:#1E40AF;font-size:10px;'
                    'padding:1px 6px;border-radius:20px;font-weight:700;">TERM</span>'
                    if kind == "term" else
                    '<span style="background:#FCE7F3;color:#9D174D;font-size:10px;'
                    'padding:1px 6px;border-radius:20px;font-weight:700;">EXPAND</span>'
                )
                _html(
                    f'{kind_badge}&nbsp;&nbsp;'
                    f'<code style="font-size:12px;">{_he.escape(src)}</code>'
                    f'&nbsp;→&nbsp;'
                    f'<span style="color:#475569;font-size:12px;">{_he.escape(str(dst))}</span>'
                )
            with del_col:
                if st.button("🗑", key=f"rtd_del_{idx}_{kind}", help=f'"{src}" 삭제'):
                    data = _load_custom_terms()
                    if kind == "term":
                        data.get("term_map", {}).pop(src, None)
                    else:
                        data.get("expand_map", {}).pop(src, None)
                    if _save_custom_terms(data):
                        st.rerun()
    else:
        st.caption("사용자 정의 항목이 없습니다. 위 폼에서 추가하세요.")


# ════════════════════════════════════════════════════════════════════
#  메인 탭 함수 (admin_dashboard.py 에서 호출)
# ════════════════════════════════════════════════════════════════════

def _tab_rag_tuning() -> None:
    """
    RAG 튜닝 & 검증 탭 진입점.

    admin_dashboard.py 에서:
        from ui.admin_tab_rag_tuning import _tab_rag_tuning
        with t_rag: _tab_rag_tuning()
    """
    from ui.design import topbar
    topbar()
    section_header(
        "RAG 튜닝",
        "쿼리 테스트 · 질의 이력 분석 · 용어 사전 관리",
    )

    _html(_TAB_CSS)

    t1, t2, t3 = st.tabs([
        "🧪  쿼리 테스트",
        "📊  질의 이력",
        "📖  용어 사전",
    ])
    with t1: _subtab_query_test()
    with t2: _subtab_history()
    with t3: _subtab_term_dict()
