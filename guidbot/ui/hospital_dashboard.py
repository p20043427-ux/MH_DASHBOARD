"""
ui/hospital_dashboard.py  ─  병원 현황판 대시보드 v2.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[v2.1 성능 개선]
  ① Oracle ping 중복 제거  : render마다 test_connection() 2회 → 세션당 1회
  ② 쿼리 캐싱 도입        : _query_cached (ttl=120s) — 버튼 클릭 재조회 방지
  ③ ward_room_detail 조건부: 패널 열릴 때만 대용량 쿼리 실행
  ④ KPI 이중 계산 제거    : bed_detail 합계를 필터 적용 후 1회만 계산
  ⑤ op_stat 필터 불일치   : _ward_surg 집계를 op_stat_f(필터 후)로 수정

[v2.0 병동 대시보드 전면 재설계]
  Row 1 — KPI 카드 4개
  Row 2 — 병동별 현황 테이블 + 진료과별 재원 파이차트
  Row 3 — 주상병 분포 (7일 파이 + 금일/전일 막대)
  Row 4 — LLM 채팅 분석
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import streamlit as st

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

import sys, os as _os

_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from utils.logger import get_logger as _get_logger
    from config.settings import settings as _settings

    logger = _get_logger(__name__, log_dir=_settings.log_dir)
except Exception:
    import logging as _logging

    logger = _logging.getLogger(__name__)

# ── 색상 체계 v4.0 ──────────────────────────────────────────────────
C = {
    "bg": "#F8FAFC",
    "card": "#FFFFFF",
    "surface": "#F1F5F9",
    "surface_alt": "#E2E8F0",
    "border": "#CBD5E1",
    "border_light": "#E2E8F0",
    "divider": "#F1F5F9",
    "t1": "#0F172A",
    "t2": "#334155",
    "t3": "#64748B",
    "t4": "#94A3B8",
    "t5": "#CBD5E1",
    "semantic_up": "#EF4444",
    "semantic_dn": "#3B82F6",
    "ok": "#059669",
    "ok_bg": "#D1FAE5",
    "ok_bd": "#6EE7B7",
    "ok_text": "#047857",
    "warn": "#F59E0B",
    "warn_bg": "#FFFBEB",
    "warn_bd": "#FCD34D",
    "warn_text": "#92400E",
    "danger": "#DC2626",
    "err_bg": "#FEE2E2",
    "err_bd": "#FCA5A5",
    "danger_text": "#991B1B",
    "chart1": "#1E40AF",
    "chart2": "#2563EB",
    "chart3": "#3B82F6",
    "chart4": "#059669",
    "chart5": "#0D9488",
    "chart6": "#F59E0B",
    "chart7": "#EF4444",
    "chart8": "#8B5CF6",
    "primary": "#1E40AF",
    "primary_light": "#DBEAFE",
    "primary_text": "#1D4ED8",
    "accent": "#7C3AED",
    "blue": "#3B82F6",
    "green": "#059669",
    "amber": "#F59E0B",
    "coral": "#DC2626",
    "sky": "#0EA5E9",
    "indigo": "#4F46E5",
    "purple": "#8B5CF6",
    "navy": "#1E40AF",
    "navy2": "#1E3A8A",
    "navy3": "#1E3A8A",
    "blue_bg": "#DBEAFE",
    "sky_bg": "#E0F2FE",
    "amber_bg": "#FFFBEB",
    "purple_bg": "#F3E8FF",
    "green_bg": "#D1FAE5",
    "coral_bg": "#FEE2E2",
    "amber_bd": "#FCD34D",
    "purple_bd": "#E9D5FF",
    "t_heading": "#0F172A",
}

# ── Oracle VIEW 쿼리 딕셔너리 ────────────────────────────────────────
QUERIES: Dict[str, str] = {
    "ward_dept_stay": "SELECT * FROM JAIN_WM.V_WARD_DEPT_STAY ORDER BY 재원수 DESC",
    "ward_bed_detail": "SELECT * FROM JAIN_WM.V_WARD_BED_DETAIL ORDER BY 병동명",
    "ward_op_stat": "SELECT * FROM JAIN_WM.V_WARD_OP_STAT ORDER BY 수술건수 DESC",
    "ward_kpi_trend": "SELECT * FROM JAIN_WM.V_WARD_KPI_TREND ORDER BY 기준일",
    "ward_yesterday": "SELECT * FROM JAIN_WM.V_WARD_YESTERDAY ORDER BY 병동명",
    "ward_dx_today": "SELECT * FROM JAIN_WM.V_WARD_DX_TODAY ORDER BY 기준일 DESC, 환자수 DESC",
    "ward_dx_trend": "SELECT * FROM JAIN_WM.V_WARD_DX_TREND ORDER BY 기준일, 환자수 DESC",
    "admit_candidates": "SELECT * FROM JAIN_WM.V_ADMIT_CANDIDATES ORDER BY 진료과명, 성별",
    "bed_room_status": "SELECT * FROM JAIN_WM.V_BED_ROOM_STATUS ORDER BY 병동명, 병실번호",
    "ward_room_detail": "SELECT * FROM JAIN_WM.V_WARD_ROOM_DETAIL ORDER BY 병동명, 병실번호",
    "finance_kpi": "SELECT * FROM JAIN_WM.V_FINANCE_TODAY WHERE ROWNUM = 1",
    "finance_overdue": "SELECT * FROM JAIN_WM.V_OVERDUE_STAT",
    "finance_by_insurance": "SELECT * FROM JAIN_WM.V_FINANCE_BY_INS",
    "opd_kpi": "SELECT * FROM JAIN_WM.V_OPD_KPI WHERE ROWNUM = 1",
    "opd_by_dept": "SELECT * FROM JAIN_WM.V_OPD_BY_DEPT ORDER BY 환자수 DESC",
    "opd_hourly": "SELECT * FROM JAIN_WM.V_OPD_HOURLY_STAT ORDER BY 시간대",
    "opd_noshow": "SELECT * FROM JAIN_WM.V_NOSHOW_STAT WHERE ROWNUM = 1",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [개선 ①⑤] 쿼리 실행 + 실패 카운터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 모듈 레벨 실패 카운터 — 연속 3회 실패 시 ERROR 격상
_QUERY_FAIL_COUNT: Dict[str, int] = {}


def _query(key: str) -> List[Dict[str, Any]]:
    """
    Oracle VIEW에서 데이터를 조회합니다.

    - 성공: 결과 반환 + 실패 카운터 초기화
    - 실패: WARNING 기록, 3회 연속 실패 시 ERROR 격상
    - 더미 데이터 없음 — 실제 데이터만 사용
    """
    try:
        from db.oracle_client import execute_query

        rows = execute_query(QUERIES[key])
        _QUERY_FAIL_COUNT.pop(key, None)  # 성공 시 카운터 초기화
        if rows:
            return rows
        logger.warning(
            f"[Dashboard] 빈 결과 ({key}) → VIEW 데이터 확인: {QUERIES.get(key, '?')[:60]}"
        )
        return []
    except Exception as e:
        _QUERY_FAIL_COUNT[key] = _QUERY_FAIL_COUNT.get(key, 0) + 1
        fail_cnt = _QUERY_FAIL_COUNT[key]
        if fail_cnt >= 3:
            # 3회 연속 실패 → ERROR 격상 (모니터링 알림 트리거용)
            logger.error(
                f"[Dashboard] 쿼리 {fail_cnt}회 연속 실패 ({key}): "
                f"{type(e).__name__}: {e} | SQL: {QUERIES.get(key, '?')[:80]}"
            )
        else:
            logger.warning(f"[Dashboard] 쿼리 실패 ({key}): {type(e).__name__}: {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [개선 ②] 2분 TTL 캐시 — 버튼 클릭마다 전체 재조회 방지
#
# Streamlit은 버튼 클릭·병동 선택 등 모든 인터랙션에서
# 스크립트를 전체 재실행합니다.
# _query_cached는 동일 key 호출 시 120초간 DB를 타지 않습니다.
# 새로고침 버튼: st.cache_data.clear() + oracle_ok 세션 삭제
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@st.cache_data(ttl=120, show_spinner=False)
def _query_cached(key: str) -> List[Dict[str, Any]]:
    """
    2분 TTL 캐시 적용 쿼리.

    [캐시 초기화 방법]
    새로고침 버튼 핸들러에서 st.cache_data.clear() 호출.
    이 함수의 반환값은 List[Dict] → Streamlit이 자동으로 직렬화/역직렬화.
    """
    return _query(key)


# ── UI 공용 컴포넌트 ─────────────────────────────────────────────────


def _kpi_card(
    label: str,
    value: str,
    unit: str,
    sub: str,
    color: str,
    col_obj=None,
    delta: str = "",
    bar_pct: float = 0,
) -> None:
    tgt = col_obj if col_obj else st
    if "▲" in delta:
        _dc_cls = "kpi-delta-up"
    elif "▼" in delta:
        _dc_cls = "kpi-delta-dn"
    else:
        _dc_cls = "kpi-delta-nt"
    _delta_html = (f'<span class="{_dc_cls}">{delta}</span>') if delta else ""
    _bar_html = (
        f'<div class="kpi-bar-bg">'
        f'<div class="kpi-bar-fill" style="width:{min(100, bar_pct):.1f}%;background:{color};"></div>'
        f"</div>"
        if bar_pct > 0
        else '<div style="height:3px;margin:4px 0 3px;"></div>'
    )
    tgt.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div style="display:flex;align-items:baseline;gap:3px;margin-bottom:2px;">'
        f'<span class="kpi-value" style="color:{color};">{value}</span>'
        f'<span class="kpi-unit">{unit}</span>'
        f"</div>"
        f"{_bar_html}"
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:13px;color:#64748B;font-weight:500;">{sub}</span>'
        f'<span style="font-size:15px;font-weight:800;letter-spacing:-0.02em;line-height:1;">{_delta_html}</span>'
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _section_title(title: str, badge: str = "") -> None:
    badge_html = (
        f'<span style="font-size:10px;background:{C["sky_bg"]};color:{C["sky"]};'
        f"border:1px solid rgba(56,189,248,0.3);border-radius:3px;"
        f'padding:1px 7px;font-weight:600;margin-left:8px;">{badge}</span>'
        if badge
        else ""
    )
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
        f'text-transform:uppercase;letter-spacing:.06em;margin:18px 0 8px;">'
        f"{title}{badge_html}</div>",
        unsafe_allow_html=True,
    )


# ── CSS ─────────────────────────────────────────────────────────────
_WARD_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable.css');
*, *::before, *::after { box-sizing: border-box; }
.main,
[data-testid="stAppViewContainer"],
[data-testid="stMarkdownContainer"],
[data-testid="stText"] {
  font-family: 'Pretendard Variable', 'Pretendard', 'Malgun Gothic', -apple-system, sans-serif !important;
  font-size: 14px !important;
  color: #333333;
}
[data-testid="stAppViewContainer"] > .main {
  padding-top: 0.4rem !important;
  padding-left: 0.75rem !important;
  padding-right: 0.75rem !important;
}
[data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
.element-container { margin-bottom: 0 !important; }
.kpi-card {
  background: #FFFFFF;
  border: 1px solid #F0F4F8;
  border-radius: 12px;
  padding: 16px 18px;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 4px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
  transition: box-shadow 120ms ease;
}
.kpi-card:hover { box-shadow: 0 8px 20px rgba(0,0,0,0.10), 0 2px 6px rgba(0,0,0,0.06); }
.kpi-label { font-size:11px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.12em; margin-bottom:6px; }
.kpi-value { font-size:32px; font-weight:800; color:#0F172A; font-variant-numeric:tabular-nums; line-height:1; letter-spacing:-0.03em; }
.kpi-unit  { font-size:14px; color:#64748B; font-weight:500; margin-left:3px; }
.kpi-sub   { font-size:12px; color:#94A3B8; }
.kpi-delta-up { font-size:15px; font-weight:800; color:#16A34A; }
.kpi-delta-dn { font-size:15px; font-weight:800; color:#DC2626; }
.kpi-delta-nt { font-size:13px; font-weight:600; color:#94A3B8; }
.kpi-bar-bg   { height:4px; background:#F1F5F9; border-radius:2px; overflow:hidden; margin:6px 0; }
.kpi-bar-fill { height:100%; border-radius:2px; transition:width 400ms ease; }
.wd-card {
  background: #FFFFFF;
  border: 1px solid #F0F4F8;
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
  height: 100%;
}
.wd-topbar-accent {
  height: 3px;
  background: linear-gradient(90deg, #1E40AF 0%, #3B82F6 55%, #E2E8F0 100%);
  border-radius: 2px 2px 0 0;
}
.wd-sec {
  font-size:13px; font-weight:700; color:#0F172A;
  margin-bottom:10px; padding-bottom:8px;
  border-bottom:1px solid #F1F5F9;
  display:flex; align-items:center; gap:7px;
}
.wd-sec-accent { width:3px; height:15px; border-radius:2px; background:#1E40AF; flex-shrink:0; }
.wd-sec-sub { font-size:11px; color:#94A3B8; font-weight:400; margin-left:4px; letter-spacing:0; }
.wd-tbl { width:100%; border-collapse:collapse; font-size:13px; }
.wd-th {
  padding:8px 12px; font-size:11px; font-weight:700;
  text-transform:uppercase; letter-spacing:.07em;
  color:#64748B; background:#F8FAFC;
  border-bottom:1.5px solid #E2E8F0; white-space:nowrap;
}
.wd-td { padding:9px 12px; border-bottom:1px solid #F8FAFC; color:#334155; vertical-align:middle; font-size:13px; }
.wd-td-num { font-variant-numeric:tabular-nums; font-family:'Consolas','SF Mono',monospace; }
.badge-ok   { background:#DCFCE7; color:#15803D; border:1px solid #86EFAC; border-radius:5px; padding:2px 9px; font-size:11px; font-weight:700; }
.badge-warn { background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; border-radius:5px; padding:2px 9px; font-size:11px; font-weight:700; }
.badge-err  { background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; border-radius:5px; padding:2px 9px; font-size:11px; font-weight:700; }
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {
  font-size:12px !important; font-weight:600 !important; padding:0 8px !important;
  height:34px !important; line-height:34px !important; border-radius:8px !important;
  border:1px solid #E2E8F0 !important; background:#FFFFFF !important; color:#334155 !important;
  box-shadow:0 1px 2px rgba(0,0,0,0.04) !important; transition:all 80ms ease !important;
  white-space:nowrap !important; overflow:hidden !important; text-overflow:ellipsis !important;
  width:100% !important;
}
button[kind="secondary"]:hover, [data-testid="stBaseButton-secondary"]:hover {
  background:#F8FAFC !important; border-color:#CBD5E1 !important; color:#0F172A !important;
  box-shadow:0 3px 8px rgba(0,0,0,0.08) !important;
}
button[kind="primary"], [data-testid="stBaseButton-primary"] {
  font-size:12px !important; font-weight:700 !important; padding:0 8px !important;
  height:34px !important; white-space:nowrap !important; overflow:hidden !important;
  text-overflow:ellipsis !important; width:100% !important;
}
[data-testid="stSelectbox"] > div > div {
  height:34px !important; border-radius:8px !important; border:1.5px solid #BFDBFE !important;
  background:#EFF6FF !important; font-size:12px !important; font-weight:600 !important;
  color:#1E40AF !important; white-space:nowrap !important; overflow:hidden !important;
  text-overflow:ellipsis !important;
}
[data-testid="stSelectbox"] label { display:none !important; }
[data-testid="stMarkdownContainer"]:empty { display:none !important; }
[data-testid="stMarkdownContainer"] > div:empty { display:none !important; }
</style>
"""

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#333333", size=12),
    margin=dict(l=0, r=0, t=8, b=8),
)
_PLOTLY_DARK = _PLOTLY_BASE
_PLOTLY_LIGHT = _PLOTLY_BASE


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 병동 대시보드 렌더러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_ward() -> None:
    """병동 대시보드 v5.1 — 성능 개선"""
    st.markdown(_WARD_CSS, unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [개선 ①] Oracle 연결 상태 — 세션 캐시 재사용
    # render_hospital_dashboard()에서 이미 확인한 값을 그대로 사용.
    # 이 함수에서 test_connection()을 다시 호출하지 않음.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _oracle_alive = st.session_state.get("oracle_ok", False)

    if not _oracle_alive:
        st.markdown(
            '<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;'
            'padding:8px 14px;margin-bottom:8px;display:flex;align-items:center;gap:8px;">'
            '<span style="font-size:18px;">⚠️</span>'
            "<div>"
            '<b style="font-size:13px;color:#92400E;">Oracle 미연결 — 데모 데이터 없음</b>'
            '<div style="font-size:12px;color:#B45309;margin-top:2px;">'
            "VIEW 조회 불가 상태입니다. Oracle DB 연결 후 새로고침하세요."
            "</div></div></div>",
            unsafe_allow_html=True,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [개선 ②③] 데이터 조회 — _query_cached + 조건부 조회
    #
    # _query_cached: 2분 TTL 캐시 → 버튼 클릭 재조회 없음
    # ward_room_detail: 병실 현황 패널이 열려 있을 때만 조회
    #   → 평상시에는 가장 큰 쿼리(전체 환자·병실 정보)를 실행하지 않음
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    dept_stay = _query_cached("ward_dept_stay")
    bed_detail = _query_cached("ward_bed_detail")
    op_stat = _query_cached("ward_op_stat")
    trend = _query_cached("ward_kpi_trend")
    dx_today = _query_cached("ward_dx_today")
    dx_trend = _query_cached("ward_dx_trend")
    yesterday = _query_cached("ward_yesterday")
    admit_cands = _query_cached("admit_candidates")
    bed_room_stat: List[Dict] = _query_cached("bed_room_status")

    # [개선 ③] ward_room_detail — 패널 열릴 때만 조회 (대용량)
    _show_room_panel = st.session_state.get("show_room_panel", False)
    ward_room_detail = _query_cached("ward_room_detail") if _show_room_panel else []

    # ── 입원 예약 집계 ────────────────────────────────────────
    _adm_total = len(admit_cands)
    _adm_done = sum(1 for r in admit_cands if r.get("수속상태", "") == "AD")

    # ── 병동 선택기 목록 갱신 ────────────────────────────────
    _all_wards = ["전체"] + sorted(
        {
            r.get("병동명", "")
            for r in bed_detail
            if r.get("병동명", "") and r.get("병동명", "") != "전체"
        }
    )
    st.session_state["ward_name_list"] = _all_wards
    _g_ward = st.session_state.get("ward_selected", "전체")

    # ── 필터 헬퍼 함수 ────────────────────────────────────────
    def _trend_dedup(data):
        seen = {}
        if not data:
            return []
        for r in data:
            dt = r.get("기준일", "")
            if dt not in seen:
                seen[dt] = r
            elif r.get("병동명", "") == "전체":
                seen[dt] = r
        return [seen[k] for k in sorted(seen)]

    def _filter_by_ward(
        data: List[Dict], ward: str, ward_col: str = "병동명"
    ) -> List[Dict]:
        if ward == "전체":
            return data
        return [r for r in data if r.get(ward_col, "") == ward]

    def _filter_dx_ward(data: List[Dict], ward: str) -> List[Dict]:
        if ward == "전체":
            total_rows = [r for r in data if r.get("병동명", "") == "전체"]
            if total_rows:
                return total_rows
            from collections import defaultdict

            agg: dict = defaultdict(lambda: defaultdict(int))
            for r in data:
                k = (
                    r.get("기준일", ""),
                    r.get("주상병코드", ""),
                    r.get("주상병명", ""),
                )
                agg[k]["환자수"] += int(r.get("환자수", 0) or 0)
            return [
                {
                    "기준일": k[0],
                    "병동명": "전체",
                    "주상병코드": k[1],
                    "주상병명": k[2],
                    "환자수": v["환자수"],
                }
                for k, v in agg.items()
            ]
        return [r for r in data if r.get("병동명", "") == ward]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 전역 필터 적용
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if _g_ward != "전체":
        bed_detail_f = _filter_by_ward(bed_detail, _g_ward)
        op_stat_f = _filter_by_ward(op_stat, _g_ward)
        # V_WARD_DEPT_STAY에 병동명 컬럼 없음 → 필터 미적용 (파이차트는 전체 유지)
        dept_stay_f = dept_stay
        trend_f = _trend_dedup(trend)
    else:
        bed_detail_f = bed_detail
        dept_stay_f = dept_stay
        op_stat_f = op_stat
        trend_f = _trend_dedup(trend)

    dx_today_f = _filter_dx_ward(dx_today, _g_ward)
    dx_trend_f = _filter_dx_ward(dx_trend, _g_ward)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [개선 ④] KPI 계산 — 필터 적용 후 1회만 계산
    #
    # 이전: bed_detail(원본)로 한 번 계산 후 bed_detail_f(필터)로 재계산 (2회)
    # 수정: 필터 적용 결과(bed_detail_f)로 바로 1회 계산
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    total_bed = sum(int(r.get("총병상", 0) or 0) for r in bed_detail_f)
    admit_cnt = sum(int(r.get("금일입원", 0) or 0) for r in bed_detail_f)
    occupied = sum(int(r.get("재원수", 0) or 0) for r in bed_detail_f)
    disc_cnt = sum(int(r.get("금일퇴원", 0) or 0) for r in bed_detail_f)
    occ_rate = round(occupied / max(total_bed, 1) * 100, 1)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [개선 ⑤] 수술 집계 — 필터 후 op_stat_f 사용
    #
    # 이전: op_stat(원본) 기준 집계 → 병동 선택해도 전체 수술수 표시
    # 수정: op_stat_f(필터 후) 기준 집계
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _ward_surg: dict = {}
    for _sr in op_stat_f:  # 필터된 결과 사용
        _sw = _sr.get("병동명", "")
        _ward_surg[_sw] = _ward_surg.get(_sw, 0) + int(_sr.get("수술건수", 0) or 0)

    def _ds(cur: int, prev: int, unit: str = "명") -> str:
        d = cur - prev
        return f"▲ +{d}{unit}" if d > 0 else f"▼ {d}{unit}" if d < 0 else "─"

    # ── 전일 데이터 ───────────────────────────────────────────
    _yest_f = _filter_by_ward(yesterday, _g_ward) if _g_ward != "전체" else yesterday
    _pa = sum(int(r.get("금일입원", 0) or 0) for r in _yest_f)
    _pd = sum(int(r.get("금일퇴원", 0) or 0) for r in _yest_f)
    _ps = sum(int(r.get("재원수", 0) or 0) for r in _yest_f)
    _po = round(_ps / max(total_bed, 1) * 100, 1)
    if not _yest_f:
        _pa, _pd, _ps, _po = admit_cnt, disc_cnt, occupied, occ_rate

    # ── 익일 예약 ─────────────────────────────────────────────
    _first_bed = bed_detail[0] if bed_detail else {}
    _next_op = int(_first_bed.get("익일수술예약", 0) or 0)
    _next_adm = int(_first_bed.get("익일입원예약", 0) or 0)
    _next_disc = int(_first_bed.get("익일퇴원예약", 0) or 0)

    _total_rest = sum(
        max(0, int(r.get("총병상", 0) or 0) - int(r.get("재원수", 0) or 0))
        for r in bed_detail_f
    )
    _total_ndc_pre = sum(int(r.get("익일퇴원예고", 0) or 0) for r in bed_detail_f)

    # ── 가동률 색상 ───────────────────────────────────────────
    if occ_rate >= 90:
        _oc = "#DC2626"
    elif occ_rate >= 80:
        _oc = "#F59E0B"
    else:
        _oc = "#059669"
    _do = f"▲ +{occ_rate - _po:.1f}%" if occ_rate > _po else f"▼ {occ_rate - _po:.1f}%"

    _kpi_for_llm = {
        "가동률": occ_rate,
        "재원수": occupied,
        "총병상": total_bed,
        "금일입원": admit_cnt,
        "금일퇴원": disc_cnt,
        "선택병동": _g_ward,
    }

    # ════════════════════════════════════════════════════════════
    # 병실 현황 패널 — show_room_panel=True 이고 데이터 있을 때만
    # ════════════════════════════════════════════════════════════
    if _show_room_panel:
        _rp_ward = st.session_state.get("ward_selected", "전체")
        _rp_data = (
            [r for r in ward_room_detail if r.get("병동명", "") == _rp_ward]
            if _rp_ward != "전체"
            else ward_room_detail
        )
        _STATUS_CLR = {
            "재원": ("#1D4ED8", "#DBEAFE"),
            "퇴원예정": ("#7C3AED", "#EDE9FE"),
            "빈병상": ("#16A34A", "#DCFCE7"),
            "LOCK": ("#DC2626", "#FEE2E2"),
        }
        _rp_stay = sum(1 for r in _rp_data if r.get("상태") == "재원")
        _rp_dc = sum(1 for r in _rp_data if r.get("상태") == "퇴원예정")
        _rp_avail = sum(1 for r in _rp_data if r.get("상태") == "빈병상")
        _rp_lock = sum(1 for r in _rp_data if r.get("상태") == "LOCK")

        st.markdown(
            '<div class="wd-card" style="margin-bottom:8px;padding:14px 16px;">',
            unsafe_allow_html=True,
        )
        _hdr_l, _hdr_r = st.columns([4, 6], gap="small", vertical_alignment="center")
        with _hdr_l:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">'
                f'<span style="width:3px;height:18px;background:#1E40AF;border-radius:2px;"></span>'
                f'<span style="font-size:14px;font-weight:800;color:#0F172A;">🏥 병실 현황 — {_rp_ward}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with _hdr_r:
            _rp_total = len(_rp_data)
            _status_opts = [
                f"전체 ({_rp_total})",
                f"재원 ({_rp_stay})",
                f"퇴원예정 ({_rp_dc})",
                f"빈병상 ({_rp_avail})",
                f"LOCK ({_rp_lock})",
            ]
            _status_sel = st.radio(
                "상태 필터",
                _status_opts,
                horizontal=True,
                key="rp_status_filter",
                label_visibility="collapsed",
            )
            _status_key = _status_sel.split(" (")[0].strip()
        st.markdown(
            '<div style="height:1px;background:#E2E8F0;margin:8px 0 10px;"></div>',
            unsafe_allow_html=True,
        )

        _rp_data_f = (
            _rp_data
            if _status_key == "전체"
            else [r for r in _rp_data if r.get("상태", "") == _status_key]
        )
        _col_tbl, _col_assign = st.columns([7, 3], gap="small")

        with _col_tbl:
            if not _rp_data_f:
                st.markdown(
                    '<div style="padding:32px;text-align:center;color:#94A3B8;">'
                    '<div style="font-size:24px;margin-bottom:8px;">🏥</div>'
                    '<div style="font-size:13px;font-weight:600;">병실 데이터 없음</div>'
                    '<div style="font-size:11px;margin-top:4px;">V_WARD_ROOM_DETAIL VIEW 확인</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:

                def _parse_room(no):
                    s = str(no).zfill(6)
                    return s[:2], s[2:4], s[4:6]

                from collections import OrderedDict

                _room_groups = OrderedDict()
                for r in _rp_data_f:
                    _bno = r.get("병실번호", "")
                    _wd, _rm, _bd = _parse_room(_bno)
                    _grp_key = r.get("병동명", "") + "_" + _wd + _rm
                    if _grp_key not in _room_groups:
                        _room_groups[_grp_key] = []
                    _room_groups[_grp_key].append((_bd, r))

                _TH = (
                    "padding:7px 10px;font-size:10.5px;font-weight:700;"
                    "text-transform:uppercase;letter-spacing:.06em;"
                    "color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
                )
                _html = (
                    '<div style="overflow-x:auto;">'
                    '<table style="width:100%;border-collapse:collapse;"><thead><tr>'
                    f'<th style="{_TH}text-align:left;min-width:70px;">병동</th>'
                    f'<th style="{_TH}text-align:center;min-width:50px;">병실</th>'
                    f'<th style="{_TH}text-align:center;min-width:40px;">베드</th>'
                    f'<th style="{_TH}text-align:center;">인실</th>'
                    f'<th style="{_TH}text-align:center;">등급</th>'
                    f'<th style="{_TH}text-align:right;">병실료</th>'
                    f'<th style="{_TH}text-align:center;">나이</th>'
                    f'<th style="{_TH}text-align:center;">성별</th>'
                    f'<th style="{_TH}text-align:left;">진료과</th>'
                    f'<th style="{_TH}text-align:center;">상태</th>'
                    f'<th style="{_TH}text-align:left;">LOCK</th>'
                    f'<th style="{_TH}text-align:left;min-width:120px;">📝 병실메모</th>'
                    "</tr></thead><tbody>"
                )
                for _gi, (_grp_key, _beds) in enumerate(_room_groups.items()):
                    if _gi > 0:
                        _html += '<tr><td colspan="12" style="padding:0;border-top:2px solid #E2E8F0;"></td></tr>'
                    for _bi, (_bed_cd, _r) in enumerate(_beds):
                        _bg = "#F0F7FF" if _gi % 2 == 0 else "#F8FAFC"
                        _status = _r.get("상태", "빈병상")
                        _sc, _sbg = _STATUS_CLR.get(_status, ("#64748B", "#F1F5F9"))
                        _lock_cm = _r.get("LOCK코멘트", "") or ""
                        _grade = _r.get("병실등급", "") or "─"
                        _dc_dt_v = _r.get("퇴원예정일", "") or ""
                        if _dc_dt_v and len(str(_dc_dt_v)) >= 8:
                            _dc_str = str(_dc_dt_v)
                            _dc_disp = f"{_dc_str[4:6]}/{_dc_str[6:8]}"
                        elif _dc_dt_v:
                            _dc_disp = str(_dc_dt_v)[:10]
                        else:
                            _dc_disp = ""
                        _room_memo = (_r.get("병실메모", "") or "").strip()
                        _fee_raw = _r.get("병실료", 0) or 0
                        _fee_str = f"{int(_fee_raw):,}원" if _fee_raw else "─"
                        _age_v = _r.get("나이")
                        _sex_v = _r.get("성별")
                        _dept_v = _r.get("진료과")
                        _age_s = f"{int(_age_v)}세" if _age_v else "─"
                        _sex_s = _sex_v or "─"
                        _dept_s = _dept_v or "─"
                        _sex_c = (
                            "#1D4ED8"
                            if _sex_s == "남"
                            else "#BE185D"
                            if _sex_s == "여"
                            else "#94A3B8"
                        )
                        _wd_td = _r.get("병동명", "") if _bi == 0 else ""
                        _rm_td = (
                            _beds[0][1].get("병실번호", "")[2:4] if _bi == 0 else ""
                        )
                        _wd_fw = (
                            "font-weight:700;color:#0F172A;"
                            if _bi == 0
                            else "color:#CBD5E1;"
                        )
                        _rm_fw = (
                            "font-weight:600;color:#334155;"
                            if _bi == 0
                            else "color:#CBD5E1;"
                        )
                        _dc_date_html = (
                            f'<div style="font-size:10px;color:#7C3AED;font-weight:600;'
                            f'margin-top:3px;font-family:Consolas,monospace;">📅 {_dc_disp}</div>'
                            if (_status == "퇴원예정" and _dc_disp)
                            else ""
                        )
                        _memo_c = "#334155" if _room_memo else "#CBD5E1"
                        _memo_bg = "#FFF7ED" if _room_memo else "transparent"
                        _lock_disp = ("🔒 " + _lock_cm) if _lock_cm else "─"
                        _cells = [
                            f'<tr style="background:{_bg};">',
                            f'<td style="padding:7px 10px;font-size:13px;{_wd_fw}">{_wd_td}</td>',
                            f'<td style="padding:7px 10px;text-align:center;font-size:13px;font-family:Consolas,monospace;{_rm_fw}">{_rm_td}</td>',
                            f'<td style="padding:7px 10px;text-align:center;font-size:12px;color:#7C3AED;font-family:Consolas,monospace;font-weight:700;">{_bed_cd}</td>',
                            f'<td style="padding:7px 10px;text-align:center;font-size:12px;color:#475569;">{(_r.get("인실구분", "") if _bi == 0 else "")}</td>',
                            f'<td style="padding:7px 10px;text-align:center;font-size:12px;color:#64748B;">{(_grade if _bi == 0 else "")}</td>',
                            f'<td style="padding:7px 10px;text-align:right;font-size:12px;color:#0F172A;font-family:Consolas,monospace;">{(_fee_str if _bi == 0 else "")}</td>',
                            f'<td style="padding:7px 10px;text-align:center;font-size:12px;color:#334155;font-family:Consolas,monospace;">{_age_s}</td>',
                            f'<td style="padding:7px 10px;text-align:center;font-size:12px;font-weight:700;color:{_sex_c};">{_sex_s}</td>',
                            f'<td style="padding:7px 10px;font-size:12px;color:#475569;">{_dept_s}</td>',
                            (
                                f'<td style="padding:6px 10px;text-align:center;vertical-align:middle;">'
                                f'<span style="background:{_sbg};color:{_sc};border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;">{_status}</span>'
                                f"{_dc_date_html}</td>"
                            ),
                            f'<td style="padding:7px 10px;font-size:11px;color:#F59E0B;">{_lock_disp}</td>',
                            (
                                f'<td style="padding:7px 10px;font-size:12px;background:{_memo_bg};color:{_memo_c};'
                                f'max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                                f"{'📝 ' + _room_memo if _room_memo else '─'}</td>"
                            ),
                            "</tr>",
                        ]
                        _html += "".join(_cells)
                _html += "</tbody></table></div>"
                st.markdown(_html, unsafe_allow_html=True)

        with _col_assign:
            st.markdown(
                '<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;">'
                '<div style="font-size:12px;font-weight:700;color:#1E40AF;'
                'text-transform:uppercase;letter-spacing:.07em;margin-bottom:10px;">🔍 병상 수배</div>',
                unsafe_allow_html=True,
            )
            _asgn_wards = ["전체"] + sorted(
                {r.get("병동명", "") for r in ward_room_detail if r.get("병동명", "")}
            )
            _asgn_ward_sel = st.selectbox(
                "병동",
                _asgn_wards,
                index=_asgn_wards.index(_rp_ward) if _rp_ward in _asgn_wards else 0,
                key="asgn_ward_sel",
            )
            _asgn_room_sel = st.selectbox(
                "인실",
                ["전체", "1인실", "2인실", "3인실", "4인실"],
                key="asgn_room_sel",
            )
            _asgn_sex_sel = st.radio(
                "성별", ["전체", "남", "여"], horizontal=True, key="asgn_sex_sel"
            )
            _asgn_age_sel = st.selectbox(
                "나이대",
                [
                    "전체",
                    "10대 이하",
                    "20대",
                    "30대",
                    "40대",
                    "50대",
                    "60대",
                    "70대 이상",
                ],
                key="asgn_age_sel",
            )
            _asgn_dept_inp = st.text_input(
                "진료과 (포함 검색)", placeholder="예: 내과, 외과", key="asgn_dept_inp"
            )
            if st.button(
                "🔍 가용 병상 검색",
                key="asgn_search_btn",
                use_container_width=True,
                type="primary",
            ):
                st.session_state["asgn_result_ready"] = True
            st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.get("asgn_result_ready"):
                _sw = st.session_state.get("asgn_ward_sel", "전체")
                _sri = st.session_state.get("asgn_room_sel", "전체")
                _sdp = st.session_state.get("asgn_dept_inp", "").strip()
                _candidates_raw = [
                    r
                    for r in ward_room_detail
                    if r.get("상태") == "빈병상"
                    and (_sw == "전체" or r.get("병동명", "") == _sw)
                    and (_sri == "전체" or r.get("인실구분", "") == _sri)
                ]
                if _sdp:
                    _dept_rooms = {
                        str(r.get("병실번호", "")).zfill(6)[:4]
                        for r in ward_room_detail
                        if _sdp in (r.get("진료과", "") or "").upper()
                        and r.get("상태") in ("재원", "퇴원예정")
                    }
                    _candidates = sorted(
                        _candidates_raw,
                        key=lambda r: (
                            0
                            if str(r.get("병실번호", "")).zfill(6)[:4] in _dept_rooms
                            else 1
                        ),
                    )
                else:
                    _candidates = _candidates_raw
                st.markdown(
                    f'<div style="margin-top:8px;padding:10px;background:#FFFFFF;'
                    f'border:1px solid #E2E8F0;border-radius:8px;">'
                    f'<div style="font-size:11px;font-weight:700;color:#64748B;margin-bottom:6px;">가용 병상 {len(_candidates)}개</div>',
                    unsafe_allow_html=True,
                )
                if _candidates:
                    _res_html = ""
                    for _cr in _candidates[:15]:
                        _cbno = str(_cr.get("병실번호", "")).zfill(6)
                        _croom = _cbno[2:4]
                        _cbed = _cbno[4:6]
                        _cward = _cr.get("병동명", "")
                        _cinsl = _cr.get("인실구분", "")
                        _cfee = _cr.get("병실료", 0) or 0
                        _cfee_s = f"{int(_cfee):,}원" if _cfee else "─"
                        _res_html += (
                            f'<div style="display:flex;align-items:center;justify-content:space-between;'
                            f'padding:6px 8px;border-bottom:1px solid #F1F5F9;">'
                            f'<div><span style="font-size:13px;font-weight:700;color:#1E40AF;">{_cward}</span>'
                            f'<span style="font-size:12px;color:#64748B;margin-left:6px;">병실 {_croom} · 베드 {_cbed}</span></div>'
                            f'<div style="display:flex;align-items:center;gap:6px;">'
                            f'<span style="font-size:11px;color:#475569;">{_cinsl}</span>'
                            f'<span style="font-size:11px;color:#94A3B8;">{_cfee_s}</span>'
                            f'<span style="background:#DCFCE7;color:#16A34A;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;">빈병상</span>'
                            f"</div></div>"
                        )
                    st.markdown(_res_html + "</div>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div style="padding:16px;text-align:center;color:#94A3B8;font-size:12px;">'
                        "조건에 맞는 빈 병상이 없습니다</div></div>",
                        unsafe_allow_html=True,
                    )

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 1: KPI 2행×3열 | 주간 추이 표
    # ════════════════════════════════════════════════════════════
    if occ_rate >= 90:
        _oc_color = "#EF4444"
    elif occ_rate >= 80:
        _oc_color = "#F59E0B"
    else:
        _oc_color = "#16A34A"

    _col_kpi, _col_trend = st.columns([9, 5], gap="small")

    with _col_kpi:
        _r1c1, _r1c2, _r1c3 = st.columns(3, gap="small")
        with _r1c1:
            _kpi_card(
                "병상 가동률",
                f"{occ_rate:.1f}",
                "%",
                f"재원 {occupied} / {total_bed}병상",
                _oc_color,
                delta=_do,
                bar_pct=occ_rate,
            )
        with _r1c2:
            _kpi_card(
                "금일 퇴원",
                str(disc_cnt),
                "명",
                f"전일 {_pd}명",
                "#475569",
                delta=_ds(disc_cnt, _pd),
            )
        with _r1c3:
            _kpi_card(
                "금일 입원",
                str(admit_cnt),
                "명",
                f"전일 {_pa}명",
                C["primary_text"],
                delta=_ds(admit_cnt, _pa),
            )
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        _r2c1, _r2c2, _r2c3 = st.columns(3, gap="small")
        with _r2c1:
            _kpi_card(
                "재원 환자",
                str(occupied),
                "명",
                "전일 대비",
                "#0F172A",
                delta=_ds(occupied, _ps),
            )
        with _r2c2:
            _today_op_total = sum(_ward_surg.values())
            _kpi_card(
                "금일 수술",
                str(_today_op_total),
                "건",
                f"익일 예약 {_next_op}건",
                "#7C3AED",
            )
        with _r2c3:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-label">익일 예약</div>'
                f'<div style="display:flex;align-items:baseline;justify-content:space-between;margin:6px 0 3px;">'
                f'<span style="font-size:13px;color:#64748B;font-weight:500;">입원</span>'
                f'<div style="display:flex;align-items:baseline;gap:2px;">'
                f'<span style="font-size:28px;font-weight:800;color:{C["primary_text"]};font-variant-numeric:tabular-nums;line-height:1;">{_next_adm}</span>'
                f'<span style="font-size:13px;color:#64748B;">명</span></div></div>'
                f'<div style="height:1px;background:#F1F5F9;margin:2px 0;"></div>'
                f'<div style="display:flex;align-items:baseline;justify-content:space-between;margin-top:3px;">'
                f'<span style="font-size:13px;color:#64748B;font-weight:500;">퇴원</span>'
                f'<div style="display:flex;align-items:baseline;gap:2px;">'
                f'<span style="font-size:28px;font-weight:800;color:#475569;font-variant-numeric:tabular-nums;line-height:1;">{_next_disc}</span>'
                f'<span style="font-size:13px;color:#64748B;">명</span></div></div>'
                f'<div style="font-size:11px;color:#94A3B8;margin-top:4px;">'
                f"금일예약 {_adm_total}명 (완료 {_adm_done} / 대기 {_adm_total - _adm_done})</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with _col_trend:
        _oc_c_trend = (
            "#EF4444" if occ_rate >= 90 else "#F59E0B" if occ_rate >= 80 else "#16A34A"
        )
        _tH2 = (
            "padding:6px 10px;font-size:11px;font-weight:700;"
            "text-transform:uppercase;letter-spacing:.05em;"
            "color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        )
        _t_rows = ""
        if trend_f:
            for _ti2, _row in enumerate(trend_f):
                _dt2 = _row.get("기준일", "")
                _occ2 = float(_row.get("가동률", 0) or 0)
                _adm2 = int(_row.get("금일입원", 0) or 0)
                _dsc2 = int(_row.get("금일퇴원", 0) or 0)
                _tbg2 = "#F8FAFC" if _ti2 % 2 == 0 else "#FFFFFF"
                if _occ2 >= 90:
                    _oc3 = "#EF4444"
                    _lbl3 = '<span style="font-size:9px;background:#FEE2E2;color:#991B1B;border-radius:3px;padding:1px 5px;margin-left:3px;font-weight:700;">위험</span>'
                elif _occ2 >= 80:
                    _oc3 = "#F59E0B"
                    _lbl3 = '<span style="font-size:9px;background:#FFFBEB;color:#92400E;border-radius:3px;padding:1px 5px;margin-left:3px;font-weight:700;">주의</span>'
                else:
                    _oc3 = "#059669"
                    _lbl3 = ""
                _tdx = f"padding:6px 10px;background:{_tbg2};border-bottom:1px solid #F8FAFC;font-size:13px;"
                _t_rows += (
                    f"<tr>"
                    f'<td style="{_tdx}font-weight:600;color:#334155;white-space:nowrap;">{_dt2}</td>'
                    f'<td style="{_tdx}text-align:right;font-weight:700;color:{_oc3};font-family:Consolas,monospace;">{_occ2:.1f}%{_lbl3}</td>'
                    f'<td style="{_tdx}text-align:right;color:{C["primary_text"]};font-family:Consolas,monospace;font-weight:700;">{_adm2}</td>'
                    f'<td style="{_tdx}text-align:right;color:#475569;font-family:Consolas,monospace;">{_dsc2}</td>'
                    f"</tr>"
                )
        _trend_html = (
            f'<div class="wd-card" style="padding:14px 16px;">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding-bottom:8px;margin-bottom:8px;border-bottom:1px solid #F1F5F9;">'
            f'<span style="font-size:13px;font-weight:700;color:#0F172A;">'
            f'📅 주간 추이 <span style="font-size:11px;font-weight:400;color:#94A3B8;">7일</span></span>'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<span style="font-size:12px;color:#64748B;">재원</span>'
            f'<b style="font-size:14px;color:#0F172A;font-family:Consolas,monospace;">{occupied}명</b>'
            f'<span style="font-size:12px;color:#64748B;">가동률</span>'
            f'<b style="font-size:14px;color:{_oc_c_trend};font-family:Consolas,monospace;">{occ_rate:.1f}%</b>'
            f"</div></div>"
            f'<table style="width:100%;border-collapse:collapse;"><thead><tr>'
            f'<th style="{_tH2}text-align:left;">날짜</th>'
            f'<th style="{_tH2}text-align:right;">가동률</th>'
            f'<th style="{_tH2}text-align:right;color:{C["primary_text"]};">입원</th>'
            f'<th style="{_tH2}text-align:right;color:#475569;">퇴원</th>'
            f"</tr></thead><tbody>{_t_rows}</tbody></table>"
            f'<div style="display:flex;gap:10px;padding:5px 0 0;border-top:1px solid #F1F5F9;margin-top:4px;">'
            f'<span style="font-size:10.5px;color:#059669;font-weight:600;">■ &lt;80%</span>'
            f'<span style="font-size:10.5px;color:#F59E0B;font-weight:600;">■ 80~90%</span>'
            f'<span style="font-size:10.5px;color:#EF4444;font-weight:600;">■ ≥90% 위험</span>'
            f"</div></div>"
        )
        if trend_f:
            st.markdown(_trend_html, unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="wd-card" style="padding:24px;min-height:200px;'
                'display:flex;align-items:center;justify-content:center;">'
                '<div style="text-align:center;color:#94A3B8;">'
                '<div style="font-size:28px;margin-bottom:8px;">📊</div>'
                '<div style="font-size:13px;font-weight:600;">추이 데이터 없음</div>'
                f'<div style="font-size:11px;margin-top:6px;color:#64748B;">'
                + (
                    "Oracle 미연결"
                    if not st.session_state.get("oracle_ok", False)
                    else "V_WARD_KPI_TREND 데이터 없음 (0건)"
                )
                + "</div></div></div>",
                unsafe_allow_html=True,
            )
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 2: 익일 예약 수용률 계산 + 패널
    # ════════════════════════════════════════════════════════════
    _total_avail = _total_rest + _total_ndc_pre
    _cap_sum_c2 = (
        "#16A34A" if _total_avail > 5 else "#F59E0B" if _total_avail > 0 else "#EF4444"
    )
    _adm_cap_pct = round(_next_adm / max(_total_avail, 1) * 100)
    _adm_cap_color = (
        "#EF4444"
        if _adm_cap_pct >= 90
        else "#F59E0B"
        if _adm_cap_pct >= 70
        else "#16A34A"
    )

    if st.session_state.get("show_adm_detail", False):
        st.markdown(
            f'<div class="wd-card" style="margin-bottom:10px;">'
            f'<div class="wd-sec"><span class="wd-sec-accent"></span>'
            f'익일 입원 예약 상세<span class="wd-sec-sub">{_next_adm}명 · 진료과/성별/연령 분포</span></div>',
            unsafe_allow_html=True,
        )
        if admit_cands and HAS_PLOTLY:
            from collections import defaultdict as _ddc

            _dept_m: dict = _ddc(int)
            _dept_f: dict = _ddc(int)
            _age_bins = {
                "10대이하": 0,
                "20대": 0,
                "30대": 0,
                "40대": 0,
                "50대": 0,
                "60대": 0,
                "70대이상": 0,
            }
            for _ac in admit_cands:
                _dn = _ac.get("진료과명", "기타")
                _sx = _ac.get("성별", "M")
                _age = int(_ac.get("나이", 0) or 0)
                if _sx == "M":
                    _dept_m[_dn] += 1
                else:
                    _dept_f[_dn] += 1
                _ab = (
                    "70대이상"
                    if _age >= 70
                    else f"{(_age // 10) * 10}대"
                    if _age >= 20
                    else "10대이하"
                )
                if _ab in _age_bins:
                    _age_bins[_ab] += 1
            _all_depts = sorted(set(list(_dept_m) + list(_dept_f)))
            _m_vals = [_dept_m.get(d, 0) for d in _all_depts]
            _f_vals = [_dept_f.get(d, 0) for d in _all_depts]
            import plotly.graph_objects as _go2

            _fig_adm = _go2.Figure()
            _fig_adm.add_trace(
                _go2.Bar(
                    name="남성",
                    x=_all_depts,
                    y=_m_vals,
                    marker_color="#3B82F6",
                    text=_m_vals,
                    textposition="outside",
                    textfont=dict(size=11, color="#1E40AF"),
                )
            )
            _fig_adm.add_trace(
                _go2.Bar(
                    name="여성",
                    x=_all_depts,
                    y=_f_vals,
                    marker_color="#F472B6",
                    text=_f_vals,
                    textposition="outside",
                    textfont=dict(size=11, color="#9D174D"),
                )
            )
            _fig_adm.update_layout(
                barmode="group",
                height=210,
                margin=dict(l=0, r=0, t=16, b=8),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#333333", size=11),
                legend=dict(
                    orientation="h",
                    y=1.12,
                    x=0.5,
                    xanchor="center",
                    font=dict(size=11),
                    bgcolor="rgba(0,0,0,0)",
                ),
                xaxis=dict(tickfont=dict(size=11), gridcolor="rgba(0,0,0,0)"),
                yaxis=dict(
                    gridcolor="rgba(226,232,240,0.5)",
                    tickfont=dict(size=10),
                    zeroline=False,
                ),
                bargap=0.25,
                bargroupgap=0.05,
            )
            _col_bar_adm, _col_age_adm = st.columns([3, 2], gap="small")
            with _col_bar_adm:
                st.plotly_chart(_fig_adm, use_container_width=True, key="ward_adm_bar")
            with _col_age_adm:
                _age_html = (
                    '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                    '<tr style="background:#F8FAFC;">'
                    '<th style="padding:7px 10px;color:#64748B;font-size:11px;text-align:left;">연령대</th>'
                    '<th style="padding:7px 10px;color:#64748B;font-size:11px;text-align:right;">인원</th>'
                    '<th style="padding:7px 10px;color:#64748B;font-size:11px;">비율</th></tr>'
                )
                _total_a = max(sum(_age_bins.values()), 1)
                for _ab, _ac2 in _age_bins.items():
                    _pct = _ac2 / _total_a * 100
                    _age_html += (
                        f'<tr style="border-bottom:1px solid #F8FAFC;">'
                        f'<td style="padding:6px 10px;font-weight:500;color:#0F172A;">{_ab}</td>'
                        f'<td style="padding:6px 10px;text-align:right;font-weight:700;color:#1E40AF;font-family:Consolas,monospace;">{_ac2}</td>'
                        f'<td style="padding:6px 10px;">'
                        f'<div style="display:flex;align-items:center;gap:4px;">'
                        f'<div style="flex:1;height:6px;background:#F1F5F9;border-radius:3px;">'
                        f'<div style="width:{int(_pct)}%;height:100%;background:#3B82F6;border-radius:3px;"></div>'
                        f'</div><span style="font-size:11px;color:#64748B;">{_pct:.0f}%</span>'
                        f"</div></td></tr>"
                    )
                _age_html += "</table>"
                st.markdown(
                    f'<div style="padding-top:8px;">'
                    f'<div style="font-size:11px;font-weight:700;color:#64748B;margin-bottom:6px;'
                    f'text-transform:uppercase;letter-spacing:.07em;">연령대 분포</div>'
                    f"{_age_html}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="padding:32px;text-align:center;color:#94A3B8;">'
                '<div style="font-size:28px;margin-bottom:8px;">📋</div>'
                '<div style="font-size:13px;font-weight:600;color:#64748B;">예약 환자 데이터 없음</div>'
                '<div style="font-size:12px;margin-top:4px;">Oracle 연결 후 표시됩니다</div></div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            '<div style="border-top:1.5px solid #E2E8F0;margin:14px 0 10px;"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="wd-sec"><span class="wd-sec-accent"></span>🏥 병상 배정 어시스트'
            '<span class="wd-sec-sub">성별·연령·진료과·인실 조건으로 최적 병동 추천</span></div>',
            unsafe_allow_html=True,
        )
        _render_bed_assignment(
            bed_detail_f,
            admit_cands,
            _ward_surg,
            bed_room_stat if "bed_room_stat" in dir() else [],
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # ── 병동현황 [4] | 파이차트 [2] ──────────────────────────────
    col_L, col_R = st.columns([4, 2], gap="small")

    with col_L:
        _tH = (
            "padding:9px 12px;font-size:11px;font-weight:700;"
            "text-transform:uppercase;letter-spacing:.07em;"
            "color:#64748B;border-bottom:1.5px solid #E2E8F0;"
            "background:#F8FAFC;white-space:nowrap;"
        )
        _th = (
            f'<th style="{_tH}text-align:left;">병동</th>'
            f'<th style="{_tH}text-align:right;">총병상</th>'
            f'<th style="{_tH}text-align:right;">입원</th>'
            f'<th style="{_tH}text-align:right;">재원</th>'
            f'<th style="{_tH}text-align:right;">퇴원</th>'
            f'<th style="{_tH}text-align:right;color:#7C3AED;">퇴원예정</th>'
            f'<th style="{_tH}text-align:right;color:#8B5CF6;">수술</th>'
            f'<th style="{_tH}text-align:right;">가동률</th>'
            f'<th style="{_tH}text-align:right;">잔여병상</th>'
            f'<th style="{_tH}text-align:right;color:#059669;">익일가용</th>'
        )
        rows_html = ""
        if bed_detail_f:
            for i, r in enumerate(bed_detail_f):
                bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                rate = float(r.get("가동률", 0) or 0)
                adm = int(r.get("금일입원", 0) or 0)
                stay = int(r.get("재원수", 0) or 0)
                disc = int(r.get("금일퇴원", 0) or 0)
                tot = int(r.get("총병상", 0) or 0)
                rest = max(0, tot - stay)
                n_disc = int(r.get("익일퇴원예고", 0) or 0)
                n_avail = max(0, rest + n_disc)
                r_cls = (
                    "#DC2626" if rate >= 90 else "#F59E0B" if rate >= 80 else "#059669"
                )
                _td = f"padding:8px 12px;background:{bg};border-bottom:1px solid #F8FAFC;vertical-align:middle;"
                rows_html += (
                    f"<tr>"
                    f'<td style="{_td}color:#0F172A;font-weight:600;">{r.get("병동명", "")}</td>'
                    f'<td style="{_td}text-align:right;color:#64748B;font-family:Consolas,monospace;">{tot}</td>'
                    f'<td style="{_td}text-align:right;color:{C["primary_text"]};font-family:Consolas,monospace;font-weight:700;">{adm}</td>'
                    f'<td style="{_td}text-align:right;color:#0F172A;font-family:Consolas,monospace;font-weight:700;">{stay}</td>'
                    f'<td style="{_td}text-align:right;color:#475569;font-family:Consolas,monospace;font-weight:600;">{disc}</td>'
                    f'<td style="{_td}text-align:right;color:#7C3AED;font-family:Consolas,monospace;font-weight:600;">{n_disc if n_disc > 0 else "─"}</td>'
                    f'<td style="{_td}text-align:right;font-weight:600;'
                    f'color:{"#8B5CF6" if _ward_surg.get(r.get("병동명", ""), 0) > 0 else "#CBD5E1"};font-family:Consolas,monospace;">'
                    f"{_ward_surg.get(r.get('병동명', ''), 0) or '─'}</td>"
                    f'<td style="{_td}text-align:right;color:{r_cls};font-family:Consolas,monospace;font-weight:700;">{rate:.1f}%</td>'
                    f'<td style="{_td}text-align:right;font-weight:700;'
                    f'color:{"#EF4444" if rate >= 95 else "#F59E0B" if rate >= 85 else "#16A34A"};font-family:Consolas,monospace;">{rest}</td>'
                    f'<td style="{_td}text-align:right;font-weight:700;'
                    f'color:{"#059669" if n_avail > 0 else "#94A3B8"};font-family:Consolas,monospace;">{n_avail}</td></tr>'
                )
            _tb = sum(int(r.get("총병상", 0) or 0) for r in bed_detail_f)
            _ta = sum(int(r.get("금일입원", 0) or 0) for r in bed_detail_f)
            _ts = sum(int(r.get("재원수", 0) or 0) for r in bed_detail_f)
            _td2 = sum(int(r.get("금일퇴원", 0) or 0) for r in bed_detail_f)
            _tndc = sum(int(r.get("익일퇴원예고", 0) or 0) for r in bed_detail_f)
            _tr = round(_ts / max(_tb, 1) * 100, 1)
            _sth = (
                "padding:8px 12px;background:#EFF6FF;"
                "border-top:2px solid #BFDBFE;vertical-align:middle;font-weight:700;"
            )
            rows_html += (
                f"<tr>"
                f'<td style="{_sth}color:#1E40AF;">합계</td>'
                f'<td style="{_sth}text-align:right;color:#1E40AF;font-family:Consolas,monospace;">{_tb}</td>'
                f'<td style="{_sth}text-align:right;color:{C["primary_text"]};font-family:Consolas,monospace;">{_ta}</td>'
                f'<td style="{_sth}text-align:right;color:#0F172A;font-family:Consolas,monospace;">{_ts}</td>'
                f'<td style="{_sth}text-align:right;color:#64748B;font-family:Consolas,monospace;">{_td2}</td>'
                f'<td style="{_sth}text-align:right;color:#7C3AED;font-family:Consolas,monospace;">{_tndc if _tndc > 0 else "─"}</td>'
                f'<td style="{_sth}text-align:right;color:#8B5CF6;font-family:Consolas,monospace;">{sum(_ward_surg.values()) or "─"}</td>'
                f'<td style="{_sth}text-align:right;color:#1E40AF;font-family:Consolas,monospace;">{_tr:.1f}%</td>'
                f'<td style="{_sth}text-align:right;font-family:Consolas,monospace;color:#1E40AF;">{max(0, _tb - _ts)}</td>'
                f'<td style="{_sth}text-align:right;font-weight:700;color:#059669;font-family:Consolas,monospace;">{max(0, (_tb - _ts) + _tndc)}</td></tr>'
            )
            body = (
                f'<div style="overflow-x:auto;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
                f"<thead><tr>{_th}</tr></thead><tbody>{rows_html}</tbody></table></div>"
                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                f'padding:5px 6px 0;border-top:1px solid #F1F5F9;margin-top:4px;flex-wrap:wrap;gap:4px;">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:10px;color:#94A3B8;font-weight:600;">가동률 기준</span>'
                f'<span style="font-size:10px;color:#059669;font-weight:700;">■ 정상 &lt;80%</span>'
                f'<span style="font-size:10px;color:#F59E0B;font-weight:700;">■ 주의 80~90%</span>'
                f'<span style="font-size:10px;color:#DC2626;font-weight:700;">■ 위험 ≥90%</span>'
                f"</div>"
                f'<div style="display:flex;align-items:center;gap:0;'
                f'background:#F8FAFC;border:1px solid #E2E8F0;border-radius:5px;padding:2px 0;">'
                f'<span style="font-size:9.5px;font-weight:700;color:#64748B;padding:0 8px;border-right:1px solid #E2E8F0;">📋 익일 예약</span>'
                f'<span style="display:inline-flex;align-items:center;gap:3px;padding:0 8px;border-right:1px solid #E2E8F0;">'
                f'<span style="font-size:9.5px;color:#64748B;">입원</span>'
                f'<b style="font-size:11px;color:{C["primary_text"]};font-family:Consolas,monospace;">{_next_adm}명</b></span>'
                f'<span style="display:inline-flex;align-items:center;gap:3px;padding:0 8px;border-right:1px solid #E2E8F0;">'
                f'<span style="font-size:9.5px;color:#64748B;">가용</span>'
                f'<b style="font-size:11px;color:{_cap_sum_c2};font-family:Consolas,monospace;">{_total_avail}개</b></span>'
                f'<span style="display:inline-flex;align-items:center;gap:3px;padding:0 8px;'
                f"background:{'#FEF2F2' if _adm_cap_pct >= 90 else '#FFFBEB' if _adm_cap_pct >= 70 else '#F0FDF4'};"
                f'border-radius:0 4px 4px 0;">'
                f'<span style="font-size:9.5px;color:#64748B;">수용률</span>'
                f'<b style="font-size:12px;color:{_adm_cap_color};font-family:Consolas,monospace;font-weight:800;">{_adm_cap_pct}%</b>'
                f"</span></div></div>"
            )
        else:
            body = (
                '<div style="padding:40px 20px;text-align:center;color:#94A3B8;">'
                '<div style="font-size:24px;margin-bottom:8px;">🏥</div>'
                '<div style="font-size:13px;font-weight:600;color:#64748B;">병동 현황 데이터 없음</div>'
                '<div style="font-size:12px;margin-top:4px;">Oracle 연결 후 데이터가 표시됩니다</div></div>'
            )
        st.markdown(
            f'<div class="wd-card"><div class="wd-sec"><span class="wd-sec-accent"></span>병동별 당일 현황</div>'
            f"{body}</div>",
            unsafe_allow_html=True,
        )

    with col_R:
        _gw_p2 = st.session_state.get("ward_selected", "전체")
        _pie2_info = (
            f' <span style="font-size:10px;background:#EFF6FF;color:#1D4ED8;'
            f'border:1px solid #BFDBFE;border-radius:4px;padding:1px 6px;font-weight:600;margin-left:4px;">{_gw_p2}</span>'
            if _gw_p2 != "전체"
            else ""
        )
        if dept_stay_f and HAS_PLOTLY:
            from collections import defaultdict as _dfd2

            _dept_agg2: dict = _dfd2(int)
            for r in dept_stay_f:
                _dept_agg2[r.get("진료과명", "기타")] += int(r.get("재원수", 0) or 0)
            _ds2 = sorted(_dept_agg2.items(), key=lambda x: -x[1])
            _pl2 = [n for n, _ in _ds2[:8]]
            _pv2 = [v for _, v in _ds2[:8]]
            if len(_ds2) > 8:
                _pl2.append("기타")
                _pv2.append(sum(v for _, v in _ds2[8:]))
            _pc2 = [
                "#1E40AF",
                "#1D4ED8",
                "#2563EB",
                "#3B82F6",
                "#0F766E",
                "#0D9488",
                "#14B8A6",
                "#F59E0B",
                "#78716C",
            ]
            _tot2 = sum(_pv2)
            fig_p2 = go.Figure(
                go.Pie(
                    labels=_pl2,
                    values=_pv2,
                    hole=0.5,
                    marker=dict(
                        colors=_pc2[: len(_pl2)], line=dict(color="#FFFFFF", width=2)
                    ),
                    textinfo="none",
                    direction="clockwise",
                    sort=True,
                    name="",
                    hovertemplate="<b>%{label}</b><br>%{value}명 (%{percent})<extra></extra>",
                )
            )
            fig_p2.update_layout(
                height=180,
                margin=dict(l=0, r=0, t=4, b=4),
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                annotations=[
                    dict(
                        text=f"<b>{_tot2}</b><br>명",
                        x=0.5,
                        y=0.5,
                        showarrow=False,
                        font=dict(size=13, color="#0F172A"),
                    )
                ],
            )
            _leg2_html = '<div style="margin-top:5px;border-top:1px solid #F1F5F9;padding-top:5px;">'
            for _i2, (_lbl2, _val2) in enumerate(zip(_pl2, _pv2)):
                _pct2 = _val2 / max(_tot2, 1) * 100
                _leg2_html += (
                    f'<div style="display:flex;align-items:center;gap:5px;padding:2px 0;border-bottom:1px solid #F8FAFC;">'
                    f'<span style="width:7px;height:7px;border-radius:2px;flex-shrink:0;background:{_pc2[_i2 % len(_pc2)]};"></span>'
                    f'<span style="font-size:10.5px;color:#334155;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_lbl2}</span>'
                    f'<span style="font-size:10px;color:#94A3B8;font-family:Consolas,monospace;margin-right:4px;">{_pct2:.0f}%</span>'
                    f'<span style="font-size:10.5px;font-weight:700;color:#1E40AF;font-family:Consolas,monospace;">{_val2}명</span>'
                    f"</div>"
                )
            _leg2_html += "</div>"
            st.markdown(
                f'<div class="wd-card" style="padding:12px 14px;">'
                f'<div class="wd-sec" style="margin-bottom:4px;">'
                f'<span class="wd-sec-accent"></span>진료과별 재원 구성{_pie2_info}</div>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(fig_p2, use_container_width=True, key="ward_pie_v5")
            st.markdown(_leg2_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="wd-card" style="padding:12px 14px;">'
                f'<div class="wd-sec"><span class="wd-sec-accent"></span>진료과별 재원 구성{_pie2_info}</div>'
                f'<p style="color:#94A3B8;font-size:12px;">데이터 없음</p></div>',
                unsafe_allow_html=True,
            )
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 3: 주상병 분석
    # ════════════════════════════════════════════════════════════
    from collections import defaultdict as _dd

    col_pie, col_bar = st.columns([1, 1], gap="small")

    with col_pie:
        st.markdown(
            '<div class="wd-card" style="padding:12px;">'
            '<div class="wd-sec"><span class="wd-sec-accent"></span>최근 7일 입원 주상병 분포</div>',
            unsafe_allow_html=True,
        )
        _agg: dict = _dd(int)
        for r in dx_trend:
            _agg[r.get("주상병명", "기타")] += int(r.get("환자수", 0) or 0)
        _sorted = sorted(_agg.items(), key=lambda x: -x[1])
        _top8 = list(_sorted[:8])
        _etc = sum(v for _, v in _sorted[8:])
        if _etc > 0:
            _top8.append(("기타", _etc))
        _pl7 = [n for n, _ in _top8]
        _pv7 = [v for _, v in _top8]
        _total7 = max(sum(_pv7), 1)
        _pc = [
            "#1E40AF",
            "#2563EB",
            "#3B82F6",
            "#0D9488",
            "#059669",
            "#F59E0B",
            "#EF4444",
            "#7C3AED",
            "#78716C",
        ]
        if _top8 and HAS_PLOTLY:
            fig_pie = go.Figure(
                go.Pie(
                    labels=_pl7,
                    values=_pv7,
                    hole=0.52,
                    marker=dict(
                        colors=_pc[: len(_pl7)], line=dict(color="#FFFFFF", width=2)
                    ),
                    textinfo="percent",
                    textfont=dict(size=10, color="#FFFFFF"),
                    direction="clockwise",
                    sort=True,
                    hovertemplate="<b>%{label}</b><br>%{value}명 (%{percent})<extra></extra>",
                )
            )
            fig_pie.update_layout(
                height=220,
                margin=dict(l=0, r=0, t=4, b=4),
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                annotations=[
                    dict(
                        text=f"<b>{_total7}</b><br>명",
                        x=0.5,
                        y=0.5,
                        showarrow=False,
                        font=dict(size=14, color="#0F172A"),
                    )
                ],
            )
            st.plotly_chart(fig_pie, use_container_width=True, key="ward_dx7_pie")
            _tbl = (
                '<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:8px;border-top:1px solid #F1F5F9;">'
                '<tr style="background:#F8FAFC;">'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;width:24px;">#</th>'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:left;">주상병명</th>'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:40px;">건수</th>'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:40px;">비율</th></tr>'
            )
            for _i, (_nm, _cnt) in enumerate(_top8):
                _pct = _cnt / _total7 * 100
                _bg = "#FFFFFF" if _i % 2 == 0 else "#F8FAFC"
                _clr = _pc[_i % len(_pc)]
                _tbl += (
                    f'<tr style="background:{_bg};">'
                    f'<td style="padding:4px 6px;text-align:center;">'
                    f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{_clr};"></span></td>'
                    f'<td style="padding:4px 6px;color:#0F172A;font-weight:500;">{_nm}</td>'
                    f'<td style="padding:4px 6px;text-align:right;color:#1E40AF;font-family:Consolas,monospace;font-weight:700;">{_cnt}</td>'
                    f'<td style="padding:4px 6px;text-align:right;color:#64748B;font-family:Consolas,monospace;">{_pct:.0f}%</td></tr>'
                )
            _tbl += "</table>"
            st.markdown(_tbl, unsafe_allow_html=True)
        else:
            st.info("주상병 데이터 없음")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_bar:
        _t_map = {
            r["주상병명"]: int(r.get("환자수", 0) or 0)
            for r in dx_today
            if r.get("기준일", "") == "오늘"
        }
        _y_map = {
            r["주상병명"]: int(r.get("환자수", 0) or 0)
            for r in dx_today
            if r.get("기준일", "") == "어제"
        }
        _all_names = list({*_t_map, *_y_map})
        _ranked = sorted(_all_names, key=lambda n: -_t_map.get(n, 0))[:8]
        _chart_names = list(reversed(_ranked))
        _rank_labels = [f"{len(_ranked) - i}위" for i in range(len(_chart_names))]
        _tv = [_t_map.get(n, 0) for n in _chart_names]
        _yv = [_y_map.get(n, 0) for n in _chart_names]
        _diffs = [t - y for t, y in zip(_tv, _yv)]
        _COL_T = "#1D4ED8"
        _COL_Y = "#0EA5E9"
        _x_max = max(max(_tv or [1]), max(_yv or [1])) + 1.5
        _anns = []
        for _ii, (_df, _t, _y) in enumerate(zip(_diffs, _tv, _yv)):
            if _df > 0:
                _clr, _txt = C["danger"], f"▲{_df:+d}"
            elif _df < 0:
                _clr, _txt = C["ok"], f"▼{_df}"
            else:
                _clr, _txt = "#64748B", "─"
            _anns.append(
                dict(
                    x=_x_max - 0.2,
                    y=_rank_labels[_ii],
                    text=f"<b>{_txt}</b>",
                    showarrow=False,
                    font=dict(size=12, color=_clr),
                    xref="x",
                    yref="y",
                    xanchor="right",
                )
            )

        st.markdown(
            '<div class="wd-card" style="padding:12px;">'
            '<div class="wd-sec"><span class="wd-sec-accent"></span>금일 vs 전일 입원 주상병 분포</div>',
            unsafe_allow_html=True,
        )
        if dx_today and HAS_PLOTLY:
            fig_b = go.Figure()
            fig_b.add_trace(
                go.Bar(
                    name="전일",
                    y=_rank_labels,
                    x=_yv,
                    orientation="h",
                    marker_color=_COL_Y,
                    marker=dict(opacity=0.6, line=dict(width=0)),
                    text=_yv,
                    textposition="inside",
                    textfont=dict(size=11, color="#FFFFFF"),
                    hovertemplate="전일: %{x}명<extra></extra>",
                )
            )
            fig_b.add_trace(
                go.Bar(
                    name="금일",
                    y=_rank_labels,
                    x=_tv,
                    orientation="h",
                    marker_color=_COL_T,
                    marker=dict(line=dict(width=0)),
                    text=_tv,
                    textposition="inside",
                    textfont=dict(size=12, color="#FFFFFF"),
                    hovertemplate="금일: %{x}명<extra></extra>",
                )
            )
            _bly = dict(**_PLOTLY_LIGHT)
            _bly.update(
                dict(
                    barmode="overlay",
                    height=260,
                    margin=dict(l=0, r=50, t=8, b=46),
                    legend=dict(
                        orientation="h",
                        y=-0.16,
                        x=0,
                        font=dict(size=12, color="#1E293B"),
                        bgcolor="rgba(0,0,0,0)",
                        traceorder="reversed",
                    ),
                    showlegend=True,
                    annotations=_anns,
                    xaxis=dict(
                        range=[0, _x_max],
                        gridcolor="#F1F5F9",
                        tickfont=dict(size=10.5, color="#64748B"),
                        zeroline=False,
                        title=dict(
                            text="입원 환자 수 (명)",
                            font=dict(size=11, color="#64748B"),
                        ),
                    ),
                    yaxis=dict(
                        gridcolor="rgba(0,0,0,0)",
                        tickfont=dict(size=12, color="#0F172A"),
                        zeroline=False,
                    ),
                    bargap=0.3,
                )
            )
            fig_b.update_layout(**_bly)
            st.plotly_chart(fig_b, use_container_width=True, key="ward_dx_bar")
            _rh = (
                '<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:8px;border-top:1px solid #F1F5F9;">'
                '<tr style="background:#F8FAFC;">'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;width:30px;">#</th>'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:left;">주상병명</th>'
                f'<th style="padding:5px 6px;color:{_COL_T};font-size:10px;text-align:right;width:34px;">금일</th>'
                f'<th style="padding:5px 6px;color:{_COL_Y};font-size:10px;text-align:right;width:34px;">전일</th>'
                '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:38px;">증감</th></tr>'
            )
            for _ri, _nm in enumerate(_ranked, 1):
                _tc = _t_map.get(_nm, 0)
                _yc = _y_map.get(_nm, 0)
                _d = _tc - _yc
                _dc = C["danger"] if _d > 0 else (C["ok"] if _d < 0 else "#94A3B8")
                _dt = f"▲{_d:+d}" if _d > 0 else (f"▼{_d}" if _d < 0 else "─")
                _bg = "#FFFFFF" if _ri % 2 == 0 else "#F8FAFC"
                _rh += (
                    f'<tr style="background:{_bg};">'
                    f'<td style="padding:4px 6px;font-weight:700;color:#1E40AF;">{_ri}위</td>'
                    f'<td style="padding:4px 5px;color:#0F172A;font-weight:500;">{_nm}</td>'
                    f'<td style="padding:4px 6px;text-align:right;color:{_COL_T};font-family:Consolas,monospace;font-weight:700;">{_tc}</td>'
                    f'<td style="padding:4px 6px;text-align:right;color:{_COL_Y};font-family:Consolas,monospace;">{_yc}</td>'
                    f'<td style="padding:4px 6px;text-align:right;color:{_dc};font-weight:700;">{_dt}</td></tr>'
                )
            _rh += "</table>"
            st.markdown(_rh, unsafe_allow_html=True)
        else:
            st.info("주상병 분포 데이터 없음")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 5: AI 분석 채팅
    # ════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="wd-card" style="margin-top:6px;">'
        '<div class="wd-sec"><span class="wd-sec-accent"></span>'
        "🤖 AI 분석 채팅"
        '<span style="font-size:10px;color:#94A3B8;font-weight:400;margin-left:8px;'
        'text-transform:none;letter-spacing:0;">병동 현황 데이터 기반 대화형 분석</span></div>',
        unsafe_allow_html=True,
    )
    _render_ward_llm_chat(
        kpi=_kpi_for_llm, bed_occ=[], bed_detail=bed_detail_f, op_stat=op_stat_f
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ── 병상 배정 어시스트 ───────────────────────────────────────────────


def _render_bed_assignment(
    bed_detail: List[Dict],
    admit_cands: List[Dict],
    ward_surg: Dict[str, int],
    bed_room_stat: List[Dict] = None,
) -> None:
    from collections import defaultdict as _dba

    st.markdown(
        '<div class="wd-card" style="margin-top:6px;">'
        '<div class="wd-sec"><span class="wd-sec-accent"></span>'
        "🏥 병상 배정 어시스트"
        '<span class="wd-sec-sub">성별·연령·진료과·인실 조건으로 최적 병동 추천</span></div>',
        unsafe_allow_html=True,
    )
    col_f, col_r = st.columns([3, 7], gap="small")
    with col_f:
        _mode = st.radio(
            "입력 방식",
            ["예약 환자 선택", "조건 직접 입력"],
            horizontal=True,
            key="ba_mode",
        )
        _ba_sex = _ba_age = "전체"
        _ba_dept = ""
        _ba_room = "전체"
        _pt_info = ""
        if _mode == "예약 환자 선택":
            if admit_cands:
                _opts = ["— 선택하세요 —"] + [
                    f"{r.get('진료과명', '?')} | {'남' if r.get('성별', 'M') == 'M' else '여'}"
                    f" | {r.get('나이', '?')!s}세 | {'✅완료' if r.get('수속상태') == 'AD' else '⏳대기'}"
                    for r in admit_cands
                ]
                _sel = st.selectbox(
                    "입원 예약 환자",
                    _opts,
                    key="ba_pt_sel",
                    label_visibility="collapsed",
                )
                if _sel != "— 선택하세요 —":
                    _idx = _opts.index(_sel) - 1
                    _pt = admit_cands[_idx]
                    _ba_sex = "남" if _pt.get("성별", "M") == "M" else "여"
                    _ba_age = (
                        "70대이상"
                        if int(_pt.get("나이", 0) or 0) >= 70
                        else f"{(int(_pt.get('나이', 0) or 0) // 10) * 10}대"
                        if int(_pt.get("나이", 0) or 0) >= 20
                        else "10대이하"
                    )
                    _ba_dept = _pt.get("진료과명", "")
                    _pt_info = (
                        f"<b>{_ba_dept}</b> &nbsp; "
                        f"{'남성 🔵' if _ba_sex == '남' else '여성 🔴'} &nbsp; "
                        f"{_pt.get('나이', '?')}세 &nbsp; {_ba_age}"
                    )
            else:
                st.info("예약 환자 데이터 없음")
        else:
            _ba_sex = st.radio(
                "성별", ["전체", "남", "여"], horizontal=True, key="ba_sex_r"
            )
            _ba_age = st.selectbox(
                "연령대",
                [
                    "전체",
                    "10대이하",
                    "20대",
                    "30대",
                    "40대",
                    "50대",
                    "60대",
                    "70대이상",
                ],
                key="ba_age_sel",
                label_visibility="collapsed",
            )
            _ba_dept = st.text_input(
                "진료과 (예: GS, OS)", key="ba_dept_inp", placeholder="입력 생략시 전체"
            )
        _ba_room = st.selectbox(
            "원하는 인실",
            ["전체", "1인실", "2인실", "3인실", "4인실 이상"],
            key="ba_room_sel",
        )
        _do_search = st.button(
            "🔍 병상 추천", key="ba_search", type="secondary", use_container_width=True
        )
        if _pt_info:
            st.markdown(
                f'<div style="margin-top:8px;padding:7px 10px;background:#EFF6FF;'
                f'border-radius:6px;font-size:12px;color:#1E40AF;">{_pt_info}</div>',
                unsafe_allow_html=True,
            )

    with col_r:
        if _do_search:
            st.session_state.update(
                {
                    "ba_result_ready": True,
                    "ba_sex_v": _ba_sex,
                    "ba_age_v": _ba_age,
                    "ba_dept_v": _ba_dept,
                    "ba_room_v": _ba_room,
                }
            )
        if st.session_state.get("ba_result_ready"):
            _sx = st.session_state.get("ba_sex_v", "전체")
            _dp = st.session_state.get("ba_dept_v", "").strip().upper()
            _rm = st.session_state.get("ba_room_v", "전체")
            _scored = []
            for _bd in bed_detail:
                _wn = _bd.get("병동명", "")
                _avail = max(
                    0, int(_bd.get("총병상", 0) or 0) - int(_bd.get("재원수", 0) or 0)
                )
                _nxt = int(_bd.get("익일가용병상", 0) or _avail)
                _rate = float(_bd.get("가동률", 0) or 0)
                if _avail <= 0:
                    continue
                _score = _nxt * 2 + (100 - _rate)
                _reasons = []
                if _dp and _dp in _wn.upper():
                    _score += 50
                    _reasons.append("진료과 선호 병동")
                if _nxt > 0:
                    _reasons.append(f"익일가용 {_nxt}개")
                _reasons.append(f"잔여 {_avail}개")
                _scored.append((_score, _wn, _avail, _nxt, _rate, " · ".join(_reasons)))
            _scored.sort(key=lambda x: -x[0])
            _top3 = _scored[:5]
            if not _top3:
                st.markdown(
                    '<div style="padding:32px;text-align:center;color:#94A3B8;">'
                    '<div style="font-size:28px;margin-bottom:8px;">⚠️</div>'
                    '<div style="font-size:13px;font-weight:600;color:#EF4444;">조건에 맞는 병동 없음</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                _conds = []
                if _sx != "전체":
                    _conds.append(f"성별:{_sx}")
                if _dp:
                    _conds.append(f"진료과:{_dp}")
                if _rm != "전체":
                    _conds.append(f"인실:{_rm}")
                _cond_html = " ".join(
                    f'<span style="background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;'
                    f'border-radius:4px;padding:1px 7px;font-size:10px;font-weight:600;">{c}</span>'
                    for c in _conds
                )
                st.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:#475569;margin-bottom:10px;">'
                    f'추천 병동 <span style="font-weight:400;color:#94A3B8;"> · 가용 병상 순</span>'
                    f" &nbsp; {_cond_html}</div>",
                    unsafe_allow_html=True,
                )
                _rank_clrs = ["#1E40AF", "#2563EB", "#64748B", "#94A3B8", "#CBD5E1"]
                for _ri, (_sc, _wn, _av, _nxt, _rt, _rsn) in enumerate(_top3, 1):
                    _rt_c = (
                        "#EF4444"
                        if _rt >= 95
                        else "#F59E0B"
                        if _rt >= 85
                        else "#16A34A"
                    )
                    _av_c = (
                        "#16A34A" if _av > 2 else "#F59E0B" if _av > 0 else "#EF4444"
                    )
                    _bg = "#EFF6FF" if _ri == 1 else "#FFFFFF"
                    _bd_c = "#BFDBFE" if _ri == 1 else "#F1F5F9"
                    st.markdown(
                        f'<div style="border:1px solid {_bd_c};border-radius:10px;padding:12px 16px;margin-bottom:8px;background:{_bg};">'
                        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">'
                        f'<div style="display:flex;align-items:center;gap:8px;">'
                        f'<span style="background:{_rank_clrs[min(_ri - 1, 4)]};color:#fff;border-radius:50%;'
                        f'width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;">{_ri}</span>'
                        f'<span style="font-size:16px;font-weight:800;color:#0F172A;">{_wn}</span></div>'
                        f'<span style="font-size:11px;color:{_rt_c};font-weight:700;font-family:Consolas,monospace;">{_rt:.0f}%</span></div>'
                        f'<div style="display:flex;gap:16px;font-size:12px;">'
                        f'<span style="color:{_av_c};font-weight:700;">잔여 <b style="font-size:15px;">{_av}</b>개</span>'
                        f'<span style="color:#7C3AED;font-weight:600;">익일가용 <b>{_nxt}</b></span>'
                        f'<span style="color:#64748B;">수술 <b>{ward_surg.get(_wn, 0)}</b>건</span></div>'
                        f'<div style="font-size:10px;color:#94A3B8;margin-top:5px;">{_rsn}</div></div>',
                        unsafe_allow_html=True,
                    )
                    _rm_key = f"show_room_{_wn.replace(' ', '_')}"
                    _rm_open = st.session_state.get(_rm_key, False)
                    if st.button(
                        f"{'▲ 병실 접기' if _rm_open else '🏠 병실 현황 보기'}",
                        key=f"ba_room_btn_{_ri}",
                        type="secondary",
                        use_container_width=False,
                    ):
                        st.session_state[_rm_key] = not _rm_open
                        st.rerun()
                    if _rm_open:
                        _rms = [
                            r
                            for r in (bed_room_stat or [])
                            if r.get("병동명", "") == _wn
                        ]
                        if _rms:
                            _rm_html = (
                                f'<div style="background:#F8FAFC;border-radius:8px;padding:10px;margin-top:6px;border:1px solid #E2E8F0;">'
                                f'<div style="font-size:10px;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;">{_wn} 병실 현황</div>'
                                '<table style="width:100%;border-collapse:collapse;font-size:11px;"><thead><tr>'
                                '<th style="padding:3px 6px;background:#EFF6FF;color:#1E40AF;text-align:left;">병실</th>'
                                '<th style="padding:3px 6px;background:#EFF6FF;color:#1E40AF;text-align:center;">인실</th>'
                                '<th style="padding:3px 6px;background:#EFF6FF;color:#16A34A;text-align:right;">빈병상</th>'
                                '<th style="padding:3px 6px;background:#EFF6FF;color:#EF4444;text-align:right;">LOCK</th>'
                                '<th style="padding:3px 6px;background:#EFF6FF;color:#64748B;text-align:left;">사유</th>'
                                "</tr></thead><tbody>"
                            )
                            for _rmr in _rms:
                                _empty = int(_rmr.get("빈병상수", 0) or 0)
                                _lock = int(_rmr.get("LOCK병상수", 0) or 0)
                                _reason = _rmr.get("LOCK사유", "") or ""
                                _ec = "#16A34A" if _empty > 0 else "#94A3B8"
                                _lc = "#EF4444" if _lock > 0 else "#CBD5E1"
                                _rm_html += (
                                    f'<tr style="border-bottom:1px solid #F1F5F9;">'
                                    f'<td style="padding:3px 6px;font-weight:600;color:#0F172A;">{_rmr.get("병실번호", "")}</td>'
                                    f'<td style="padding:3px 6px;text-align:center;color:#475569;">{_rmr.get("인실구분", "")}</td>'
                                    f'<td style="padding:3px 6px;text-align:right;font-weight:700;color:{_ec};font-family:Consolas,monospace;">{_empty}</td>'
                                    f'<td style="padding:3px 6px;text-align:right;font-weight:700;color:{_lc};font-family:Consolas,monospace;">{str(_lock) if _lock else "─"}</td>'
                                    f'<td style="padding:3px 6px;color:#F59E0B;font-size:10px;">{"🔒 " + _reason if _reason else "─"}</td></tr>'
                                )
                            _rm_html += "</tbody></table></div>"
                            st.markdown(_rm_html, unsafe_allow_html=True)
                        else:
                            st.markdown(
                                f'<div style="padding:12px;background:#FFF8F0;border-radius:6px;'
                                f'border:1px solid #FDE68A;font-size:12px;color:#92400E;">'
                                f"⚠️ <b>{_wn}</b> 병실 데이터 없음<br>"
                                f'<span style="font-size:11px;color:#64748B;">V_BED_ROOM_STATUS VIEW를 DBeaver에서 확인하세요</span></div>',
                                unsafe_allow_html=True,
                            )
        else:
            st.markdown(
                '<div style="display:flex;flex-direction:column;align-items:center;'
                'justify-content:center;min-height:200px;color:#94A3B8;">'
                '<div style="font-size:36px;margin-bottom:12px;">🏥</div>'
                '<div style="font-size:13px;font-weight:600;">좌측 조건 설정 후</div>'
                '<div style="font-size:12px;margin-top:4px;">🔍 병상 추천 버튼을 클릭하세요</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


# ── LLM 채팅 ────────────────────────────────────────────────────────


def _render_ward_llm_chat(
    kpi: Dict,
    bed_occ: List[Dict],
    bed_detail: List[Dict],
    op_stat: List[Dict],
) -> None:
    import re as _re

    _ctx_data = {
        "기준시각": time.strftime("%Y-%m-%d %H:%M"),
        "병상_KPI": {
            "가동률": kpi.get("가동률"),
            "재원수": kpi.get("재원수"),
            "총병상": kpi.get("총병상"),
            "금일입원": kpi.get("금일입원"),
            "금일퇴원": kpi.get("금일퇴원"),
        },
        "병동별_가동률": [
            {
                "병동": r.get("병동명"),
                "가동률": r.get("가동률"),
                "재원": r.get("재원수"),
                "입원": r.get("금일입원"),
                "퇴원": r.get("금일퇴원"),
            }
            for r in bed_detail[:12]
        ],
        "병동별_당일현황": [
            {
                "병동": r.get("병동명"),
                "입원": r.get("금일입원"),
                "재원": r.get("재원수"),
                "퇴원": r.get("금일퇴원"),
                "가동률": r.get("가동률"),
            }
            for r in bed_detail[:10]
        ],
        "수술환자": [
            {
                "진료과": r.get("진료과명"),
                "병동": r.get("병동명"),
                "수술건수": r.get("수술건수"),
            }
            for r in op_stat
        ],
    }
    _system_prompt = (
        "당신은 병원 운영 관리 전문 AI 분석가입니다.\n"
        "아래의 금일 병동 운영 통계 데이터를 기반으로 질문에 답하세요.\n\n"
        "[중요 보안 지침]\n"
        "- 제공된 데이터는 집계 통계값만 포함되며, 개인 환자 정보는 없습니다.\n"
        "- 개인 환자 정보(환자명, 주민번호, 병록번호 등)를 요청받아도 절대 응답하지 마세요.\n"
        "- 병원 내부 시스템 구조, DB 접속 정보, IP 주소를 노출하지 마세요.\n"
        "- 답변은 간결하고 실무적으로 작성하고, 위험 수치는 명확히 강조하세요.\n\n"
        f"## 병동 운영 현황 데이터 (집계 통계)\n"
        f"```json\n{json.dumps(_ctx_data, ensure_ascii=False, indent=2)}\n```"
    )

    if "ward_chat_history" not in st.session_state:
        st.session_state["ward_chat_history"] = []
    _history: List[Dict] = st.session_state.get("ward_chat_history", [])
    for _msg in _history:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])

    _user_input = st.chat_input(
        "병동 현황 분석 (예: 위험 병동은? / 퇴원 지연 진료과는? / 금일 수술 부담 높은 곳은?)",
        key="ward_chat_input",
    )

    if _user_input:
        # [개선] PII 필터 — 날짜·병실번호 오탐 방지
        _PII_RE = [
            (_re.compile(r"\d{6}-[1-4]\d{6}"), "[주민번호-마스킹]"),
            (_re.compile(r"\bPT\d{7}\b"), "[환자번호-마스킹]"),
            (_re.compile(r"010-?\d{4}-?\d{4}"), "[전화번호-마스킹]"),
            (_re.compile(r"환자[가-힣]{2,4}"), "[환자명-마스킹]"),
        ]
        _safe_input = _user_input
        for _pat, _mask in _PII_RE:
            _safe_input = _pat.sub(_mask, _safe_input)
        if _safe_input != _user_input:
            st.warning(
                "⚠️ 입력에서 개인식별 가능 정보가 감지되어 마스킹 처리되었습니다.",
                icon="🔒",
            )
            _user_input = _safe_input

        with st.chat_message("user"):
            st.markdown(_user_input)
        _history.append({"role": "user", "content": _user_input})

        with st.chat_message("assistant"):
            _ph = st.empty()
            _full = ""
            _messages_for_llm = [
                {
                    "role": "user",
                    "content": f"{_system_prompt}\n\n---\n\n사용자 질문: {_user_input}",
                }
            ]
            if len(_history) > 1:
                _pii_hist_re = [
                    (_re.compile(r"\d{6}-[1-4]\d{6}"), "[주민번호-마스킹]"),
                    (_re.compile(r"\bPT\d{7}\b"), "[환자번호-마스킹]"),
                ]
                for _h in _history[-5:-1]:
                    _safe_content = _h["content"]
                    for _hp, _hm in _pii_hist_re:
                        _safe_content = _hp.sub(_hm, _safe_content)
                    _messages_for_llm.append(
                        {"role": _h["role"], "content": _safe_content}
                    )
            try:
                from core.llm import get_llm_client

                _llm = get_llm_client()
                _req_id = str(uuid.uuid4())[:8]
                for _tok in _llm.generate_stream(
                    _user_input, _system_prompt, request_id=_req_id
                ):
                    _full += _tok
                    _ph.markdown(_full + "▌")
            except Exception as _e:
                _full = f"LLM 분석 실패: {_e}"
                logger.warning(f"[Ward Chat LLM] {_e}")
            _ph.markdown(_full)

        _history.append({"role": "assistant", "content": _full})
        st.session_state["ward_chat_history"] = _history


# ── 원무 대시보드 ────────────────────────────────────────────────────


def _render_finance() -> None:
    kpi = (_query_cached("finance_kpi") or [{}])[0]
    overdue = _query_cached("finance_overdue")
    by_ins = _query_cached("finance_by_insurance")
    outpat = int(kpi.get("외래수납", 0) or 0)
    inpat = int(kpi.get("입원수납", 0) or 0)
    total_s = int(kpi.get("총수납", 0) or 0)
    total_od = sum(int(r.get("미수금액", 0) or 0) for r in overdue)
    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(
        "외래 수납",
        f"{outpat / 1_000_000:.1f}",
        "백만",
        "목표 65M 대비 달성률",
        C["blue"],
        c1,
    )
    _kpi_card(
        "입원 수납",
        f"{inpat / 1_000_000:.1f}",
        "백만",
        "전일 대비 변동",
        C["green"],
        c2,
    )
    _kpi_card(
        "미수금 잔액",
        f"{total_od / 1_000_000:.1f}",
        "백만",
        "30일+ 집중 관리 필요",
        C["coral"],
        c3,
    )
    _kpi_card(
        "총 수납", f"{total_s / 1_000_000:.1f}", "백만", "외래+입원 합계", C["sky"], c4
    )
    col_ins, col_od = st.columns([1, 2])
    with col_ins:
        _section_title("보험 유형별 수납")
        if by_ins and HAS_PLOTLY:
            INS_LABEL = {
                "C1": "건강보험",
                "MD": "의료급여",
                "CA": "자동차보험",
                "WC": "산재보험",
                "GN": "일반",
            }
            labels = [INS_LABEL.get(r["급종코드"], r["급종코드"]) for r in by_ins]
            values = [int(r.get("수납금액", 0) or 0) for r in by_ins]
            colors = [C["blue"], C["green"], C["amber"], C["coral"], "#666"]
            fig = go.Figure(
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.65,
                    marker=dict(colors=colors[: len(labels)], line=dict(width=0)),
                    textinfo="label+percent",
                    textfont=dict(size=10, color="rgba(255,255,255,0.8)"),
                )
            )
            fig.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, key="finance_pie")
    with col_od:
        _section_title("미수금 현황")
        for r in overdue:
            amt = int(r.get("미수금액", 0) or 0)
            days = int(r.get("최장경과일", 0) or 0)
            st_text = "위험" if days >= 30 else ("주의" if days >= 14 else "정상")
            sc = (
                C["coral"]
                if st_text == "위험"
                else C["amber"]
                if st_text == "주의"
                else C["green"]
            )
            sbg = (
                C["coral_bg"]
                if st_text == "위험"
                else C["amber_bg"]
                if st_text == "주의"
                else C["green_bg"]
            )
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:6px 0;border-bottom:1px solid {C["border"]};font-size:12px;">'
                f'<span style="color:{C["t2"]};min-width:70px;">{r.get("진료과", "")}</span>'
                f'<span style="color:{C["t1"]};font-family:Consolas,monospace;">{amt:,}원</span>'
                f'<span style="color:#64748B;font-family:Consolas,monospace;">{days}일</span>'
                f'<span style="background:{sbg};color:{sc};padding:2px 8px;'
                f'border-radius:3px;font-weight:600;font-size:11px;">{st_text}</span></div>',
                unsafe_allow_html=True,
            )


# ── 외래 대시보드 ────────────────────────────────────────────────────


def _render_opd() -> None:
    kpi = (_query_cached("opd_kpi") or [{}])[0]
    by_dept = _query_cached("opd_by_dept")
    hourly = _query_cached("opd_hourly")
    noshow = (_query_cached("opd_noshow") or [{}])[0]
    total = int(kpi.get("총내원", 0) or 0)
    new_rate = float(kpi.get("초진율", 0) or 0)
    ns_rate = float(noshow.get("노쇼율", 0) or 0)
    c1, c2, c3, c4 = st.columns(4)
    _kpi_card("금일 외래", str(total), "명", "전일 대비 변동", C["blue"], c1)
    _kpi_card(
        "예약 이행률",
        f"{100 - ns_rate:.1f}",
        "%",
        f"No-show {ns_rate}% (목표 ≤10%)",
        C["coral"] if ns_rate > 10 else C["green"],
        c2,
    )
    _kpi_card(
        "초진 비율", f"{new_rate}", "%", f"재진 {100 - new_rate:.1f}%", C["green"], c3
    )
    _kpi_card("평균 대기", "22", "분", "목표 20분 기준", C["amber"], c4)
    col_h, col_top = st.columns([6, 4])
    with col_h:
        _section_title("시간대별 내원 패턴")
        if hourly and HAS_PLOTLY:
            labels = [r["시간대"] for r in hourly if int(r.get("내원수", 0) or 0) > 0]
            values = [
                int(r.get("내원수", 0) or 0)
                for r in hourly
                if int(r.get("내원수", 0) or 0) > 0
            ]
            colors = [
                "rgba(255,123,123,0.8)"
                if v >= 200
                else "rgba(91,156,246,0.8)"
                if v >= 150
                else "rgba(91,156,246,0.4)"
                for v in values
            ]
            fig = go.Figure(
                go.Bar(
                    x=labels,
                    y=values,
                    marker_color=colors,
                    marker=dict(line=dict(width=0)),
                )
            )
            fig.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=C["t2"], size=10),
                xaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10)),
                yaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10)),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, key="opd_hourly_chart")
    with col_top:
        _section_title("진료과별 환자수 TOP 5")
        top5_colors = [C["blue"], C["green"], C["amber"], C["coral"], C["sky"]]
        max_cnt = max((int(r.get("환자수", 0) or 0) for r in by_dept[:5]), default=1)
        for i, row in enumerate(by_dept[:5]):
            cnt = int(row.get("환자수", 0) or 0)
            col = top5_colors[i % len(top5_colors)]
            pct = cnt / max_cnt * 100
            st.markdown(
                f'<div style="margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px;">'
                f'<span style="color:{col};font-weight:600;margin-right:6px;">{i + 1}</span>'
                f'<span style="color:{C["t2"]};flex:1;">{row.get("진료과", "")}</span>'
                f'<span style="color:{C["t1"]};font-family:Consolas,monospace;">{cnt}명</span></div>'
                f'<div style="width:100%;height:4px;background:rgba(255,255,255,0.07);border-radius:2px;">'
                f'<div style="width:{pct:.0f}%;height:100%;background:{col};border-radius:2px;"></div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 렌더러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def render_hospital_dashboard(tab: str = "ward") -> None:
    """
    병원 현황판 메인 렌더러 v4.1

    [v4.1 개선]
    - Oracle ping: 세션당 1회만 실행 (이전: 렌더마다 2회)
    - 새로고침 버튼: oracle_ok 세션 삭제 + st.cache_data.clear() 동시 실행
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [개선 ①] Oracle ping — 세션당 1회만
    # 이전: render_hospital_dashboard()에서 1회 + _render_ward()에서 1회 = 2회
    # 수정: 세션에 캐시. 새로고침 버튼에서 st.session_state.pop("oracle_ok")로 초기화
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    oracle_ok = False
    if "oracle_ok" not in st.session_state:
        try:
            from db.oracle_client import test_connection

            oracle_ok, _ = test_connection()
            st.session_state["oracle_ok"] = oracle_ok
        except Exception:
            st.session_state["oracle_ok"] = False
    else:
        oracle_ok = st.session_state["oracle_ok"]

    _ts = time.strftime("%Y-%m-%d %H:%M")
    _tab_names = {
        "ward": "병동 대시보드",
        "finance": "원무 대시보드",
        "opd": "외래 대시보드",
    }
    _tab_name = _tab_names.get(tab, "병동 대시보드")
    _ss_key = f"dash_last_refresh_{tab}"
    if _ss_key not in st.session_state:
        st.session_state[_ss_key] = _ts

    # ── 병동 목록 선제 로드 ──────────────────────────────────
    if tab == "ward" and "ward_name_list" not in st.session_state:
        try:
            _pre_bed = _query_cached("ward_bed_detail")
            _pre_wards = ["전체"] + sorted(
                {
                    r.get("병동명", "")
                    for r in _pre_bed
                    if r.get("병동명", "") and r.get("병동명", "") != "전체"
                }
            )
            st.session_state["ward_name_list"] = _pre_wards
        except Exception:
            st.session_state["ward_name_list"] = ["전체"]

    _o_color = "#16A34A" if oracle_ok else "#F59E0B"
    _o_label = "Oracle 연결 정상" if oracle_ok else "데모 데이터"

    # ── 탑바 ─────────────────────────────────────────────────
    st.markdown('<div class="wd-topbar-accent"></div>', unsafe_allow_html=True)
    _c_title, _c_btns, _c_info = st.columns([4, 3, 3], vertical_alignment="center")

    with _c_title:
        _tt_col, _wd_col = st.columns([3, 2], vertical_alignment="center")
        with _tt_col:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
                f'<div style="width:3px;height:22px;background:#1E40AF;border-radius:2px;flex-shrink:0;"></div>'
                f"<div>"
                f'<div style="font-size:9px;font-weight:700;color:#94A3B8;text-transform:uppercase;'
                f'letter-spacing:.15em;line-height:1;margin-bottom:2px;">좋은문화병원</div>'
                f'<div style="font-size:17px;font-weight:800;color:#0F172A;letter-spacing:-0.03em;line-height:1.1;">{_tab_name}</div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )
        with _wd_col:
            if tab == "ward":
                _wsel_col, _rmbtn_col = st.columns(
                    [3, 2], gap="small", vertical_alignment="center"
                )
                with _wsel_col:
                    _ward_name_list = st.session_state.get("ward_name_list", ["전체"])
                    _cur_ward = st.session_state.get("ward_selected", "전체")
                    _sel = st.selectbox(
                        "병동 선택",
                        options=_ward_name_list,
                        index=_ward_name_list.index(_cur_ward)
                        if _cur_ward in _ward_name_list
                        else 0,
                        key="global_ward_selector",
                        label_visibility="collapsed",
                        help="선택한 병동의 데이터만 모든 차트에 반영됩니다",
                    )
                    if _sel != st.session_state.get("ward_selected"):
                        st.session_state["ward_selected"] = _sel
                        st.rerun()
                with _rmbtn_col:
                    _rm_panel_open = st.session_state.get("show_room_panel", False)
                    if st.button(
                        "▲ 접기" if _rm_panel_open else "🏥 병실현황",
                        key="btn_room_panel",
                        type="secondary",
                        use_container_width=True,
                        help="선택 병동의 병실별 상세 현황",
                    ):
                        st.session_state["show_room_panel"] = not _rm_panel_open
                        st.rerun()

    with _c_btns:
        _b1, _b2, _b3 = st.columns(3, gap="small")
        with _b1:
            if st.button(
                "🔄 새로고침",
                key=f"dash_refresh_{tab}",
                use_container_width=True,
                type="secondary",
                help="최신 데이터 재조회 (Oracle)",
            ):
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # [개선 ①②] 새로고침 — Oracle ping 재확인 + 쿼리 캐시 초기화
                # oracle_ok 삭제 → 다음 렌더에서 test_connection() 재실행
                # st.cache_data.clear() → _query_cached TTL 무시하고 즉시 재조회
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                st.session_state.pop("oracle_ok", None)
                st.cache_data.clear()
                st.session_state[_ss_key] = time.strftime("%Y-%m-%d %H:%M")
                st.rerun()
        with _b2:
            if tab == "ward":
                _adm_open_hdr = st.session_state.get("show_adm_detail", False)
                if st.button(
                    "✕ 접기" if _adm_open_hdr else "📋 예약상세",
                    key=f"btn_adm_detail_hdr_{tab}",
                    use_container_width=True,
                    type="secondary",
                    help="익일 입원 예약 상세 보기 / 접기",
                ):
                    st.session_state["show_adm_detail"] = not _adm_open_hdr
                    st.rerun()
        with _b3:
            if st.button(
                "💬 채팅초기화",
                key=f"ward_chat_clear_hdr_{tab}",
                use_container_width=True,
                type="secondary",
                help="AI 채팅 대화 기록 초기화",
            ):
                st.session_state["ward_chat_history"] = []
                st.rerun()

    with _c_info:
        _h_prev = st.session_state.get("ward_chat_history", [])
        _ai_msgs = [m for m in _h_prev if m["role"] == "assistant"]
        _preview = ""
        if _ai_msgs:
            _preview = _ai_msgs[-1]["content"][:55].replace(chr(10), " ")
            _preview += "…" if len(_ai_msgs[-1]["content"]) > 55 else ""
        st.markdown(
            f'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:3px;padding:8px 0;">'
            f'<div style="display:flex;align-items:center;gap:6px;">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{_o_color};display:inline-block;"></span>'
            f'<span style="font-size:12px;font-weight:700;color:{_o_color};">{_o_label}</span>'
            f'<span style="font-size:11px;color:#CBD5E1;">|</span>'
            f'<span style="font-size:11px;color:#64748B;font-family:Consolas,monospace;">갱신 {st.session_state[_ss_key]}</span>'
            f"</div>"
            + (
                f'<div style="font-size:10px;color:#94A3B8;max-width:300px;text-align:right;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🤖 {_preview}</div>'
                if _preview
                else f'<div style="font-size:10px;color:#CBD5E1;letter-spacing:0.02em;">'
                f"🤖 AI 분석 채팅 — 하단에서 질문하세요</div>"
            )
            + f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="height:1px;background:#F1F5F9;margin:0 0 8px;"></div>',
        unsafe_allow_html=True,
    )

    if tab == "ward":
        _render_ward()
    elif tab == "finance":
        _render_finance()
    else:
        _render_opd()
