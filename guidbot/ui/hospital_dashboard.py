"""
ui/hospital_dashboard.py  ─  병원 현황판 대시보드 v2.2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[v2.2 차트 선택기 통합]
  ① 진료과별 재원 구성   : 도넛(기본) / 가로막대 / 트리맵
  ② 주간 추이 7일        : 테이블(기본) / 라인 / 영역 / 막대
  ③ 병동별 당일 현황     : 테이블(기본) / 가로막대 / 히트맵
  ④ 최근 7일 주상병 분포 : 파이(기본) / 가로막대 / 트리맵
  ⑤ 금일 vs 전일 주상병  : 중첩막대(기본) / 그룹막대 / 수평막대
  - pill 버튼 UI: 각 섹션 헤더 우측에 소형 선택 버튼 표시
  - session_state 저장: 병동 전환·새로고침 후에도 선택 유지

[v2.1 성능 개선]
  ① Oracle ping 중복 제거  : render마다 test_connection() 2회 → 세션당 1회
  ② 쿼리 캐싱 도입        : _query_cached (ttl=120s) — 버튼 클릭 재조회 방지
  ③ ward_room_detail 조건부: 패널 열릴 때만 대용량 쿼리 실행
  ④ KPI 이중 계산 제거    : bed_detail 합계를 필터 적용 후 1회만 계산
  ⑤ op_stat 필터 불일치   : _ward_surg 집계를 op_stat_f(필터 후)로 수정
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [v2.2] 차트 선택기 — 외부 모듈 없이 이 파일에 직접 내장
#
# 외부 import에 의존하면 경로 문제로 선택기가 통째로 숨겨지는 문제 발생.
# chart_selector / chart_renderers 로직을 인라인으로 구현하여
# 어떤 실행 환경에서도 항상 선택기가 표시되도록 보장합니다.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 섹션별 차트 옵션 정의
# 구조: {section_key: {"options": [(value, label), ...], "default": str}}
_CHART_OPTIONS: Dict[str, Dict] = {
    # ── 진료과별 재원 구성 ─────────────────────────────────────────
    "dept_stay": {
        "options": [
            ("donut",   "🍩 도넛"),      # 기본: 중앙 총계 강조
            ("bar_h",   "📊 막대"),      # 수치 비교
            ("treemap", "🗺 트리맵"),    # 면적 비율
        ],
        "default": "donut",
    },
    # ── 주간 추이 7일 ──────────────────────────────────────────────
    "weekly_trend": {
        "options": [
            ("table", "📋 테이블"),      # 기본: 기존 HTML 표
            ("line",  "📈 라인"),        # 추세선
            ("area",  "🏔 영역"),        # 볼륨 강조
            ("bar",   "📊 막대"),        # 일별 비교
        ],
        "default": "table",
    },
    # ── 병동별 당일 현황 ───────────────────────────────────────────
    "ward_detail": {
        "options": [
            ("table",   "📋 테이블"),    # 기본: 기존 풍부한 HTML 표
            ("bar_h",   "📊 막대"),      # 가동률 비교
            ("heatmap", "🔥 히트맵"),   # 병동×지표 매트릭스
        ],
        "default": "table",
    },
    # ── 최근 7일 주상병 분포 ───────────────────────────────────────
    "dx_7day": {
        "options": [
            ("pie",     "🍩 파이"),      # 기본: 비율 파악
            ("bar_h",   "📊 막대"),      # 상병명 가독성
            ("treemap", "🗺 트리맵"),    # 빈도 강조
        ],
        "default": "pie",
    },
    # ── 금일 vs 전일 주상병 비교 ───────────────────────────────────
    "dx_compare": {
        "options": [
            ("overlay", "🔀 중첩막대"),  # 기본: 투명도 중첩
            ("grouped", "📊 그룹막대"),  # 나란히 비교
            ("bar_h",   "↔ 수평막대"),  # 상병명 공간 여유
        ],
        "default": "overlay",
    },
}

# session_state 키 접두사 (전역 병동 선택기 키와 충돌 방지)
_CT_PREFIX = "ct__"


def _get_chart_type(section_key: str) -> str:
    """
    특정 섹션의 현재 선택된 차트 타입을 session_state에서 읽어 반환합니다.
    저장된 값이 없으면 해당 섹션의 기본값을 반환합니다.
    """
    cfg = _CHART_OPTIONS.get(section_key, {})
    return st.session_state.get(_CT_PREFIX + section_key, cfg.get("default", ""))


def _chart_selector(section_key: str, title: str, subtitle: str = "") -> str:
    """
    섹션 헤더 한 줄에 제목(좌) + pill 선택기(우)를 렌더링합니다.
    반환값: 현재 선택된 chart_type 문자열

    [개선 사항 v2.3]
    - 라디오 circle 완전 제거: label > div (BaseWeb indicator) CSS 숨김 추가
    - label_visibility="hidden" 사용 → "collapsed"보다 공간 제거에 더 안정적
    - st.columns 비율 조정 → 선택기가 충분한 공간 확보
    """
    cfg = _CHART_OPTIONS.get(section_key)
    if not cfg:
        return ""

    options   = cfg["options"]
    state_key = _CT_PREFIX + section_key
    current   = st.session_state.get(state_key, cfg["default"])

    labels = [lbl for _, lbl in options]
    values = [val for val, _ in options]
    try:
        idx = values.index(current)
    except ValueError:
        idx = 0

    # 섹션 헤더: 제목(좌 60%) + 선택기(우 40%)
    col_title, col_radio = st.columns([6, 4])

    with col_title:
        sub_html = (
            f'<span style="font-size:10px;color:#94A3B8;font-weight:400;'
            f'margin-left:8px;letter-spacing:0;">{subtitle}</span>'
            if subtitle else ""
        )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;'
            f'padding:6px 0 4px;border-bottom:1px solid #F1F5F9;margin-bottom:2px;">'
            f'<span style="display:inline-block;width:3px;height:16px;'
            f'background:linear-gradient(180deg,#1E40AF,#3B82F6);'
            f'border-radius:2px;flex-shrink:0;"></span>'
            f'<span style="font-size:12.5px;font-weight:700;color:#0F172A;'
            f'letter-spacing:-0.01em;">{title}{sub_html}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with col_radio:
        # label_visibility 지원 여부를 버전별로 처리
        # "hidden": 라벨 텍스트+공간 모두 제거 (가장 깔끔)
        # "collapsed": 텍스트만 제거, 공간은 일부 남을 수 있음
        kw: dict = dict(
            label="​",          # U+200B zero-width space
            options=labels,
            index=idx,
            horizontal=True,
            key=f"radio_ct_{section_key}",
        )
        try:
            kw["label_visibility"] = "hidden"
            selected_label = st.radio(**kw)
        except TypeError:
            kw.pop("label_visibility", None)
            selected_label = st.radio(**kw)

        selected_value = values[labels.index(selected_label)]
        st.session_state[state_key] = selected_value

    return st.session_state.get(state_key, cfg["default"])

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
    "ward_dept_stay":      "SELECT * FROM JAIN_WM.V_WARD_DEPT_STAY ORDER BY 재원수 DESC",
    "ward_bed_detail":     "SELECT * FROM JAIN_WM.V_WARD_BED_DETAIL ORDER BY 병동명",
    "ward_op_stat":        "SELECT * FROM JAIN_WM.V_WARD_OP_STAT ORDER BY 수술건수 DESC",
    "ward_kpi_trend":      "SELECT * FROM JAIN_WM.V_WARD_KPI_TREND ORDER BY 기준일",
    "ward_yesterday":      "SELECT * FROM JAIN_WM.V_WARD_YESTERDAY ORDER BY 병동명",
    "ward_dx_today":       "SELECT * FROM JAIN_WM.V_WARD_DX_TODAY ORDER BY 기준일 DESC, 환자수 DESC",
    "ward_dx_trend":       "SELECT * FROM JAIN_WM.V_WARD_DX_TREND ORDER BY 기준일, 환자수 DESC",
    "admit_candidates":    "SELECT * FROM JAIN_WM.V_ADMIT_CANDIDATES ORDER BY 진료과명, 성별",
    "bed_room_status":     "SELECT * FROM JAIN_WM.V_BED_ROOM_STATUS ORDER BY 병동명, 병실번호",
    "ward_room_detail":    "SELECT * FROM JAIN_WM.V_WARD_ROOM_DETAIL ORDER BY 병동명, 병실번호",
    "finance_kpi":         "SELECT * FROM JAIN_WM.V_FINANCE_TODAY WHERE ROWNUM = 1",
    "finance_overdue":     "SELECT * FROM JAIN_WM.V_OVERDUE_STAT",
    "finance_by_insurance":"SELECT * FROM JAIN_WM.V_FINANCE_BY_INS",
    "opd_kpi":             "SELECT * FROM JAIN_WM.V_OPD_KPI WHERE ROWNUM = 1",
    "opd_by_dept":         "SELECT * FROM JAIN_WM.V_OPD_BY_DEPT ORDER BY 환자수 DESC",
    "opd_hourly":          "SELECT * FROM JAIN_WM.V_OPD_HOURLY_STAT ORDER BY 시간대",
    "opd_noshow":          "SELECT * FROM JAIN_WM.V_NOSHOW_STAT WHERE ROWNUM = 1",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 쿼리 실행 + 2분 TTL 캐시
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_QUERY_FAIL_COUNT: Dict[str, int] = {}


def _query(key: str) -> List[Dict[str, Any]]:
    try:
        from db.oracle_client import execute_query
        rows = execute_query(QUERIES[key])
        _QUERY_FAIL_COUNT.pop(key, None)
        if rows:
            return rows
        logger.warning(f"[Dashboard] 빈 결과 ({key}) → VIEW 확인: {QUERIES.get(key, '?')[:60]}")
        return []
    except Exception as e:
        _QUERY_FAIL_COUNT[key] = _QUERY_FAIL_COUNT.get(key, 0) + 1
        fail_cnt = _QUERY_FAIL_COUNT[key]
        if fail_cnt >= 3:
            logger.error(f"[Dashboard] 쿼리 {fail_cnt}회 연속 실패 ({key}): {type(e).__name__}: {e}")
        else:
            logger.warning(f"[Dashboard] 쿼리 실패 ({key}): {type(e).__name__}: {e}")
        return []


@st.cache_data(ttl=120, show_spinner=False)
def _query_cached(key: str) -> List[Dict[str, Any]]:
    """2분 TTL 캐시. 새로고침 버튼에서 st.cache_data.clear() 로 초기화."""
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
  border: 1px solid #E8EDF2;
  border-radius: 12px;
  padding: 16px 18px;
  min-height: 172px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(15,23,42,0.06);
  transition: box-shadow 120ms ease;
}
.kpi-card:hover { box-shadow: 0 4px 16px rgba(15,23,42,0.1); }
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
  border: 1px solid #E8EDF2;
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(15,23,42,0.06);
  height: 100%;
  transition: box-shadow 120ms ease;
}
.wd-card:hover {
  box-shadow: 0 4px 16px rgba(15,23,42,0.1);
}
.wd-topbar-accent {
  height: 3px;
  background: linear-gradient(90deg, #1E3A8A 0%, #2563EB 60%, #93C5FD 100%);
  border-radius: 0;
  margin-bottom: 0;
}
/* 섹션 헤더 — _chart_selector가 자체 헤더를 그리므로 wd-sec는 보조용 */
.wd-sec {
  font-size:12.5px; font-weight:700; color:#1E293B;
  margin-bottom:8px; padding-bottom:6px;
  border-bottom:1px solid #F1F5F9;
  display:flex; align-items:center; gap:7px;
  line-height:1.3;
}
.wd-sec-accent {
  width:3px; height:14px; border-radius:2px;
  background:linear-gradient(180deg,#1E40AF,#60A5FA);
  flex-shrink:0;
}
.wd-sec-sub { font-size:10.5px; color:#94A3B8; font-weight:400; margin-left:4px; letter-spacing:0; }
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

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   [v2.3] 차트 선택기 pill 버튼 — 완전 재설계
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

/* ── 라디오 위젯 래퍼 초기화 ── */
div[data-testid="stRadio"] {
  padding: 0 !important;
  margin: 0 !important;
  min-height: 0 !important;
  line-height: 0 !important;
}

/* ── 위젯 라벨(제목) 완전 제거 ──
   stWidgetLabel: Streamlit ≥ 1.10
   첫 번째 p 태그: 구버전 fallback */
div[data-testid="stRadio"] > div[data-testid="stWidgetLabel"],
div[data-testid="stRadio"] > label:not([data-baseweb]),
div[data-testid="stRadio"] > p {
  display: none !important;
  height: 0 !important;
  max-height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  opacity: 0 !important;
  pointer-events: none !important;
}

/* ── 옵션 컨테이너 — 가로 Flex ── */
div[data-testid="stRadio"] > div {
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  gap: 3px !important;
  align-items: center !important;
  padding: 0 !important;
  margin: 0 !important;
  min-height: 0 !important;
  line-height: normal !important;
}

/* ── 각 옵션 라벨 — pill 모양 ──
   label[data-baseweb="radio"]: BaseWeb radio label 정확 타겟팅 */
div[data-testid="stRadio"] label {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 3px 11px !important;
  border-radius: 20px !important;
  border: 1px solid #E2E8F0 !important;
  background: #FFFFFF !important;
  color: #64748B !important;
  font-size: 11.5px !important;
  font-weight: 500 !important;
  cursor: pointer !important;
  white-space: nowrap !important;
  margin: 0 !important;
  transition: background 0.1s, color 0.1s, border-color 0.1s !important;
  gap: 0 !important;
  line-height: 1.5 !important;
}
div[data-testid="stRadio"] label:hover {
  background: #F1F5F9 !important;
  border-color: #93C5FD !important;
  color: #1E40AF !important;
}
div[data-testid="stRadio"] label:has(input:checked) {
  background: #1E40AF !important;
  border-color: #1E40AF !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
}

/* ── radio 원형 circle 정밀 제거 ──
   Streamlit radio 구조:
     label
       input[type=radio]     ← 숨김
       div (circle/dot)      ← input + div 로 정확히 타겟 → 숨김
       div (text wrapper)    ← 이건 보여야 함!
         span (실제 텍스트)

   label > div 전체 숨김은 텍스트도 같이 사라지므로 금지.
   반드시 input 다음 형제(+) div만 숨겨야 함. */
div[data-testid="stRadio"] input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
/* circle indicator: input 바로 다음 div 형제만 숨김 */
div[data-testid="stRadio"] label > input + div,
div[data-testid="stRadio"] label > input ~ div:first-of-type {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
  min-width: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}
</style>
"""

# _PLOTLY_BASE: margin 제거 — 각 차트 함수에서 명시적으로 지정 (중복 키 오류 방지)
_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#333333", size=12),
)
_PLOTLY_DARK = _PLOTLY_BASE
_PLOTLY_LIGHT = _PLOTLY_BASE


def _layout(fig: "go.Figure", **kwargs) -> "go.Figure":
    """
    Plotly Figure에 공통 레이아웃을 적용하는 헬퍼.

    _PLOTLY_BASE를 기본으로 kwargs를 병합합니다.
    kwargs가 _PLOTLY_BASE와 동일한 키를 가질 경우 kwargs가 우선합니다.
    → margin 등 키가 두 번 전달되어 TypeError 발생하는 문제를 방지합니다.

    사용 예:
        _layout(fig, height=230, margin=dict(l=0, r=0, t=8, b=8))
    """
    merged = {**_PLOTLY_BASE, **kwargs}   # kwargs가 _PLOTLY_BASE를 덮어씀
    fig.update_layout(**merged)
    return fig

# 차트 공통 색상 팔레트 (9색, 색약 고려)
_PALETTE = [
    "#1E40AF", "#2563EB", "#3B82F6",
    "#0D9488", "#059669", "#F59E0B",
    "#EF4444", "#7C3AED", "#78716C",
]

# 공통 축 스타일
# tickfont는 포함하지 않음 → dict(**_AX, tickfont=...) 호출 시 중복 키 오류 방지
_AX = dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [v2.2] 섹션별 대안 차트 렌더러 (인라인)
#
# - "table" 타입은 각 섹션의 기존 HTML 코드 블록이 그대로 처리
# - 나머지 타입만 아래 함수가 처리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _render_dept_chart(data: List[Dict], chart_type: str) -> None:
    """
    진료과별 재원 구성 대안 차트 렌더러.
    chart_type: "donut" | "bar_h" | "treemap"
    data: ward_dept_stay 쿼리 결과
    """
    from collections import defaultdict as _ddc2
    if not data or not HAS_PLOTLY:
        st.caption("데이터 없음")
        return

    # 진료과별 합산 집계
    agg: Dict[str, int] = _ddc2(int)
    for r in data:
        agg[r.get("진료과명", "기타")] += int(r.get("재원수", 0) or 0)
    sorted_items = sorted(agg.items(), key=lambda x: -x[1])
    top8 = list(sorted_items[:8])
    etc  = sum(v for _, v in sorted_items[8:])
    if etc > 0:
        top8.append(("기타", etc))
    labels = [n for n, _ in top8]
    values = [v for _, v in top8]
    total  = max(sum(values), 1)
    colors = _PALETTE[:len(labels)]

    if chart_type == "donut":
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.52,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
            textinfo="percent", textfont=dict(size=10, color="#FFFFFF"),
            direction="clockwise", sort=True,
            hovertemplate="<b>%{label}</b><br>%{value}명 (%{percent})<extra></extra>",
        ))
        fig.update_layout(
            height=200,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=12),
            margin=dict(l=0, r=0, t=8, b=8),
            showlegend=False,
            annotations=[dict(text=f"<b>{total}</b><br>명", x=0.5, y=0.5,
                              showarrow=False, font=dict(size=14, color="#0F172A"))],
        )
        st.plotly_chart(fig, use_container_width=True, key="dept_donut")
        # 범례 테이블
        rows = ""
        for i, (nm, val) in enumerate(zip(labels, values)):
            pct = val / total * 100
            bg  = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
            clr = colors[i % len(colors)]
            rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:3px 6px;"><span style="display:inline-block;'
                f'width:8px;height:8px;border-radius:2px;background:{clr};"></span></td>'
                f'<td style="padding:3px 6px;color:#0F172A;font-size:11.5px;font-weight:500;">{nm}</td>'
                f'<td style="padding:3px 6px;text-align:right;color:#1E40AF;'
                f'font-family:Consolas,monospace;font-weight:700;font-size:11.5px;">{val}</td>'
                f'<td style="padding:3px 6px;text-align:right;color:#64748B;'
                f'font-family:Consolas,monospace;font-size:11px;">{pct:.0f}%</td></tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;margin-top:6px;border-top:1px solid #F1F5F9;">'
            f'<thead><tr style="background:#F8FAFC;">'
            f'<th style="padding:4px 6px;width:20px;"></th>'
            f'<th style="padding:4px 6px;color:#64748B;font-size:10px;text-align:left;">진료과</th>'
            f'<th style="padding:4px 6px;color:#64748B;font-size:10px;text-align:right;">재원수</th>'
            f'<th style="padding:4px 6px;color:#64748B;font-size:10px;text-align:right;">비율</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>",
            unsafe_allow_html=True,
        )

    elif chart_type == "bar_h":
        fig = go.Figure(go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
            text=[f"{v}명 ({v/total*100:.0f}%)" for v in values],
            textposition="outside", textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>%{x}명<extra></extra>",
        ))
        fig.update_layout(
            height=max(200, len(labels) * 30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=12),
            margin=dict(l=0, r=70, t=8, b=8),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, title=dict(text="재원 환자 수 (명)", font=dict(size=10))),
        )
        st.plotly_chart(fig, use_container_width=True, key="dept_bar_h")

    elif chart_type == "treemap":
        fig = go.Figure(go.Treemap(
            labels=labels, values=values, parents=[""] * len(labels),
            marker=dict(colors=colors, line=dict(width=2, color="#FFFFFF")),
            texttemplate="<b>%{label}</b><br>%{value}명<br>%{percentRoot:.0%}",
            textfont=dict(size=10),
            hovertemplate="<b>%{label}</b><br>%{value}명 (%{percentRoot:.1%})<extra></extra>",
        ))
        fig.update_layout(
            height=270,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=12),
            margin=dict(l=0, r=0, t=8, b=8),
        )
        st.plotly_chart(fig, use_container_width=True, key="dept_treemap")


def _render_trend_chart(data: List[Dict], chart_type: str, occupied: int, occ_rate: float) -> None:
    """
    주간 추이 7일 대안 차트 렌더러.
    chart_type: "table"(기존 표) | "line" | "area" | "bar"
    """
    if not data:
        st.caption("추이 데이터 없음")
        return

    dates  = [str(r.get("기준일", ""))           for r in data]
    occs   = [float(r.get("가동률", 0) or 0)     for r in data]
    admins = [int(r.get("금일입원", 0) or 0)      for r in data]
    discs  = [int(r.get("금일퇴원", 0) or 0)      for r in data]
    key_sfx = chart_type

    if chart_type == "table":
        # ── 기존 HTML 표 그대로 유지 ────────────────────────────────
        _tH2 = "padding:7px 10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        rows = ""
        for ti, row in enumerate(data):
            dt   = str(row.get("기준일", ""))
            occ  = float(row.get("가동률", 0) or 0)
            adm  = int(row.get("금일입원", 0) or 0)
            disc = int(row.get("금일퇴원", 0) or 0)
            tbg  = "#F8FAFC" if ti % 2 == 0 else "#FFFFFF"
            if occ >= 90:   oc, lbl = "#EF4444", '<span style="font-size:9px;background:#FEE2E2;color:#991B1B;border-radius:3px;padding:1px 5px;margin-left:3px;font-weight:700;">위험</span>'
            elif occ >= 80: oc, lbl = "#F59E0B", '<span style="font-size:9px;background:#FFFBEB;color:#92400E;border-radius:3px;padding:1px 5px;margin-left:3px;font-weight:700;">주의</span>'
            else:            oc, lbl = "#059669", ""
            td = f"padding:7px 10px;background:{tbg};border-bottom:1px solid #F8FAFC;font-size:13px;"
            rows += (
                f"<tr>"
                f'<td style="{td}font-weight:600;color:#334155;white-space:nowrap;">{dt}</td>'
                f'<td style="{td}text-align:right;font-weight:700;color:{oc};font-family:Consolas,monospace;">{occ:.1f}%{lbl}</td>'
                f'<td style="{td}text-align:right;color:{C["primary_text"]};font-family:Consolas,monospace;font-weight:700;">{adm}</td>'
                f'<td style="{td}text-align:right;color:#475569;font-family:Consolas,monospace;">{disc}</td>'
                f"</tr>"
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;"><thead><tr>'
            f'<th style="{_tH2}text-align:left;">날짜</th>'
            f'<th style="{_tH2}text-align:right;">가동률</th>'
            f'<th style="{_tH2}text-align:right;color:{C["primary_text"]};">입원</th>'
            f'<th style="{_tH2}text-align:right;color:#475569;">퇴원</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>"
            f'<div style="display:flex;gap:10px;padding:6px 0 0;border-top:1px solid #F1F5F9;margin-top:4px;">'
            f'<span style="font-size:10.5px;color:#059669;font-weight:600;">■ &lt;80%</span>'
            f'<span style="font-size:10.5px;color:#F59E0B;font-weight:600;">■ 80~90%</span>'
            f'<span style="font-size:10.5px;color:#EF4444;font-weight:600;">■ ≥90% 위험</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    if not HAS_PLOTLY:
        st.caption("plotly 미설치 — pip install plotly")
        return

    fig = go.Figure()

    if chart_type == "line":
        fig.add_trace(go.Scatter(x=dates, y=occs, name="가동률(%)", mode="lines+markers",
            line=dict(color="#1E40AF", width=2.5, shape="spline"),
            fill="tozeroy", fillcolor="rgba(30,64,175,0.06)",
            marker=dict(size=6, color="#1E40AF", line=dict(width=2, color="#fff")),
            yaxis="y", hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=admins, name="금일입원", mode="lines+markers",
            line=dict(color="#059669", width=1.5, dash="dot", shape="spline"),
            marker=dict(size=4, color="#059669"), yaxis="y2",
            hovertemplate="%{x}<br>입원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=discs, name="금일퇴원", mode="lines+markers",
            line=dict(color="#F59E0B", width=1.5, dash="dot", shape="spline"),
            marker=dict(size=4, color="#F59E0B"), yaxis="y2",
            hovertemplate="%{x}<br>퇴원 %{y}명<extra></extra>"))
        fig.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), showlegend=True,
            margin=dict(l=0, r=0, t=8, b=40),
            legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, title=dict(text="가동률(%)", font=dict(size=10)), ticksuffix="%", range=[0, 110]),
            yaxis2=dict(**_AX, overlaying="y", side="right", title=dict(text="인원(명)", font=dict(size=10))),
            xaxis=dict(**_AX),
        )

    elif chart_type == "area":
        fig.add_trace(go.Scatter(x=dates, y=admins, name="금일입원", mode="lines",
            fill="tozeroy", fillcolor="rgba(5,150,105,0.15)",
            line=dict(color="#059669", width=1.5),
            hovertemplate="%{x}<br>입원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=discs, name="금일퇴원", mode="lines",
            fill="tozeroy", fillcolor="rgba(245,158,11,0.15)",
            line=dict(color="#F59E0B", width=1.5),
            hovertemplate="%{x}<br>퇴원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=occs, name="가동률(%)", mode="lines+markers",
            line=dict(color="#1E40AF", width=2), marker=dict(size=5, color="#1E40AF"),
            yaxis="y2", hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        fig.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), showlegend=True,
            margin=dict(l=0, r=0, t=8, b=40),
            legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, title=dict(text="인원(명)", font=dict(size=10))),
            yaxis2=dict(**_AX, overlaying="y", side="right", ticksuffix="%", range=[0, 110],
                        title=dict(text="가동률(%)", font=dict(size=10))),
            xaxis=dict(**_AX),
        )

    elif chart_type == "bar":
        fig.add_trace(go.Bar(x=dates, y=admins, name="금일입원", marker_color="#059669",
                             hovertemplate="%{x}<br>입원 %{y}명<extra></extra>"))
        fig.add_trace(go.Bar(x=dates, y=discs, name="금일퇴원", marker_color="#F59E0B",
                             hovertemplate="%{x}<br>퇴원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=occs, name="가동률(%)", mode="lines+markers",
            line=dict(color="#1E40AF", width=2), marker=dict(size=5),
            yaxis="y2", hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        fig.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=0, t=8, b=40),
            barmode="group", showlegend=True,
            legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, title=dict(text="인원(명)", font=dict(size=10))),
            yaxis2=dict(**_AX, overlaying="y", side="right", ticksuffix="%", range=[0, 110],
                        title=dict(text="가동률(%)", font=dict(size=10))),
            xaxis=dict(**_AX),
        )

    st.plotly_chart(fig, use_container_width=True, key=f"trend_{key_sfx}")


def _render_ward_alt_chart(data: List[Dict], chart_type: str, ward_surg: Dict) -> None:
    """
    병동별 당일 현황 대안 차트 렌더러.
    chart_type: "bar_h" | "heatmap"  (table은 기존 HTML 처리)
    """
    if not data or not HAS_PLOTLY:
        st.caption("데이터 없음")
        return

    wards    = [str(r.get("병동명", ""))           for r in data]
    stays    = [int(r.get("재원수", 0) or 0)       for r in data]
    admins   = [int(r.get("금일입원", 0) or 0)     for r in data]
    discs    = [int(r.get("금일퇴원", 0) or 0)     for r in data]
    beds     = [int(r.get("총병상", 0) or 0)       for r in data]
    occs     = [float(r.get("가동률", 0) or 0)     for r in data]

    if chart_type == "bar_h":
        bar_colors = ["#EF4444" if r >= 90 else "#F59E0B" if r >= 80 else "#059669" for r in occs]
        fig = go.Figure(go.Bar(
            x=occs, y=wards, orientation="h",
            marker=dict(color=bar_colors, line=dict(color="rgba(0,0,0,0)")),
            text=[f"{r:.1f}%  ({s}명/{b}병상)" for r, s, b in zip(occs, stays, beds)],
            textposition="outside", textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>가동률 %{x:.1f}%<extra></extra>",
        ))
        for thr, lbl, clr in [(90, "위험 90%", "#EF4444"), (80, "주의 80%", "#F59E0B")]:
            fig.add_vline(x=thr, line=dict(color=clr, dash="dash", width=1.2),
                          annotation_text=lbl, annotation_font=dict(size=9, color=clr),
                          annotation_position="top")
        fig.update_layout(
            height=max(200, len(wards) * 36),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=90, t=8, b=8),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, range=[0, 115], ticksuffix="%",
                       title=dict(text="병상 가동률 (%)", font=dict(size=10))),
        )
        st.plotly_chart(fig, use_container_width=True, key="ward_bar_h")

    elif chart_type == "heatmap":
        indicators = ["재원수", "금일입원", "금일퇴원", "가동률(%)"]
        z_raw = [stays, admins, discs, occs]
        z_matrix = [list(row) for row in zip(*z_raw)]  # [병동 × 지표]
        fig = go.Figure(go.Heatmap(
            z=z_matrix, x=indicators, y=wards,
            colorscale=[[0.0, "#DBEAFE"], [0.5, "#93C5FD"], [1.0, "#1E40AF"]],
            text=[[f"{v:.1f}" if isinstance(v, float) else str(v) for v in row] for row in z_matrix],
            texttemplate="%{text}",
            textfont=dict(size=10, color="#FFFFFF"),
            hovertemplate="<b>%{y}</b><br>%{x}: %{text}<extra></extra>",
            showscale=True,
            colorbar=dict(len=0.8, thickness=12, tickfont=dict(size=9)),
        ))
        fig.update_layout(
            height=max(220, len(wards) * 34),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=60, t=30, b=8),
            xaxis=dict(side="top", tickfont=dict(size=10)),
            yaxis=dict(**_AX, autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True, key="ward_heatmap")


def _render_dx7_chart(data: List[Dict], chart_type: str) -> None:
    """
    최근 7일 주상병 분포 대안 차트 렌더러.
    chart_type: "pie" | "bar_h" | "treemap"
    """
    from collections import defaultdict as _ddx7
    if not data:
        st.info("주상병 데이터 없음")
        return

    agg: Dict[str, int] = _ddx7(int)
    for r in data:
        agg[r.get("주상병명", "기타")] += int(r.get("환자수", 0) or 0)
    sorted_items = sorted(agg.items(), key=lambda x: -x[1])
    top8  = list(sorted_items[:8])
    etc   = sum(v for _, v in sorted_items[8:])
    if etc > 0:
        top8.append(("기타", etc))
    labels = [n for n, _ in top8]
    values = [v for _, v in top8]
    total  = max(sum(values), 1)
    colors = _PALETTE[:len(labels)]

    if chart_type == "pie":
        if not HAS_PLOTLY:
            st.info("주상병 데이터 없음")
            return
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.52,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
            textinfo="percent", textfont=dict(size=10, color="#FFFFFF"),
            direction="clockwise", sort=True,
            hovertemplate="<b>%{label}</b><br>%{value}명 (%{percent})<extra></extra>",
        ))
        fig.update_layout(
            height=220, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), margin=dict(l=0, r=0, t=8, b=8), showlegend=False,
            annotations=[dict(text=f"<b>{total}</b><br>명", x=0.5, y=0.5,
                              showarrow=False, font=dict(size=14, color="#0F172A"))],
        )
        st.plotly_chart(fig, use_container_width=True, key="dx7_pie")
        # 범례 테이블
        rows = ""
        for i, (nm, cnt) in enumerate(top8):
            pct = cnt / total * 100
            bg  = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
            clr = colors[i % len(colors)]
            rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:4px 6px;text-align:center;">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{clr};"></span></td>'
                f'<td style="padding:4px 6px;color:#0F172A;font-weight:500;">{nm}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:#1E40AF;font-family:Consolas,monospace;font-weight:700;">{cnt}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:#64748B;font-family:Consolas,monospace;">{pct:.0f}%</td></tr>'
            )
        st.markdown(
            '<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:8px;border-top:1px solid #F1F5F9;">'
            '<tr style="background:#F8FAFC;">'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;width:24px;">#</th>'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:left;">주상병명</th>'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:40px;">건수</th>'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:40px;">비율</th></tr>'
            f'{rows}</table>',
            unsafe_allow_html=True,
        )

    elif chart_type == "bar_h":
        if not HAS_PLOTLY:
            st.info("주상병 데이터 없음")
            return
        fig = go.Figure(go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
            text=[f"{v}건" for v in values],
            textposition="outside", textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>%{x}건<extra></extra>",
        ))
        fig.update_layout(
            height=max(200, len(labels) * 30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=60, t=8, b=8),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, title=dict(text="입원 건수", font=dict(size=10))),
        )
        st.plotly_chart(fig, use_container_width=True, key="dx7_bar_h")

    elif chart_type == "treemap":
        if not HAS_PLOTLY:
            st.info("주상병 데이터 없음")
            return
        fig = go.Figure(go.Treemap(
            labels=labels, values=values, parents=[""] * len(labels),
            marker=dict(colors=colors, line=dict(width=2, color="#FFFFFF")),
            texttemplate="<b>%{label}</b><br>%{value}건<br>%{percentRoot:.0%}",
            textfont=dict(size=10),
            hovertemplate="<b>%{label}</b><br>%{value}건 (%{percentRoot:.1%})<extra></extra>",
        ))
        fig.update_layout(height=270, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), margin=dict(l=0, r=0, t=8, b=8))
        st.plotly_chart(fig, use_container_width=True, key="dx7_treemap")


def _render_dx_compare_chart(data: List[Dict], chart_type: str) -> None:
    """
    금일 vs 전일 주상병 비교 대안 차트 렌더러.
    chart_type: "overlay" | "grouped" | "bar_h"
    """
    from collections import defaultdict as _ddcmp
    if not data:
        st.info("주상병 분포 데이터 없음")
        return

    t_map: Dict[str, int] = _ddcmp(int)
    y_map: Dict[str, int] = _ddcmp(int)
    for r in data:
        nm  = r.get("주상병명", "기타") or "기타"
        cnt = int(r.get("환자수", 0) or 0)
        day = str(r.get("기준일", ""))
        (t_map if "오늘" in day else y_map)[nm] += cnt

    all_dx  = set(list(t_map.keys()) + list(y_map.keys()))
    sorted_dx = sorted(all_dx, key=lambda d: -(t_map.get(d, 0) + y_map.get(d, 0)))
    top_dx    = sorted_dx[:8]
    t_vals    = [t_map.get(d, 0) for d in top_dx]
    y_vals    = [y_map.get(d, 0) for d in top_dx]
    x_max     = max(max(t_vals, default=1), max(y_vals, default=1)) * 1.2
    _COL_T    = "#1D4ED8"
    _COL_Y    = "#0EA5E9"

    # 증감 주석
    def _anns_h(names, t_vs, y_vs, x_mx):
        anns = []
        for i, (nm, tv, yv) in enumerate(zip(names, t_vs, y_vs)):
            d = tv - yv
            clr = C["danger"] if d > 0 else C["ok"] if d < 0 else "#64748B"
            txt = f"▲{d:+d}" if d > 0 else f"▼{d}" if d < 0 else "─"
            anns.append(dict(x=x_mx - 0.2, y=nm, text=f"<b>{txt}</b>",
                             showarrow=False, font=dict(size=11, color=clr),
                             xref="x", yref="y", xanchor="right"))
        return anns

    if not HAS_PLOTLY:
        st.info("주상병 분포 데이터 없음")
        return

    if chart_type == "overlay":
        ranked = list(reversed(top_dx))
        rank_labels = [f"{len(top_dx) - i}위" for i in range(len(ranked))]
        tv_r  = [t_map.get(d, 0) for d in ranked]
        yv_r  = [y_map.get(d, 0) for d in ranked]
        diffs = [t - y for t, y in zip(tv_r, yv_r)]
        anns  = []
        for i, (df, tv, yv) in enumerate(zip(diffs, tv_r, yv_r)):
            clr = C["danger"] if df > 0 else C["ok"] if df < 0 else "#64748B"
            txt = f"▲{df:+d}" if df > 0 else f"▼{df}" if df < 0 else "─"
            anns.append(dict(x=x_max - 0.2, y=rank_labels[i], text=f"<b>{txt}</b>",
                             showarrow=False, font=dict(size=12, color=clr),
                             xref="x", yref="y", xanchor="right"))
        fig = go.Figure()
        fig.add_trace(go.Bar(name="전일", y=rank_labels, x=yv_r, orientation="h",
            marker_color=_COL_Y, marker=dict(opacity=0.6, line=dict(width=0)),
            text=yv_r, textposition="inside", textfont=dict(size=11, color="#FFFFFF"),
            hovertemplate="전일: %{x}명<extra></extra>"))
        fig.add_trace(go.Bar(name="금일", y=rank_labels, x=tv_r, orientation="h",
            marker_color=_COL_T, marker=dict(line=dict(width=0)),
            text=tv_r, textposition="inside", textfont=dict(size=12, color="#FFFFFF"),
            hovertemplate="금일: %{x}명<extra></extra>"))
        fig.update_layout(
            barmode="overlay", height=270,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=50, t=8, b=46),
            legend=dict(orientation="h", y=-0.16, x=0, font=dict(size=12, color="#1E293B"),
                        bgcolor="rgba(0,0,0,0)", traceorder="reversed"),
            showlegend=True, annotations=anns,
            xaxis=dict(range=[0, x_max], gridcolor="#F1F5F9",
                       tickfont=dict(size=10.5, color="#64748B"), zeroline=False,
                       title=dict(text="입원 환자 수 (명)", font=dict(size=11, color="#64748B"))),
            yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=12, color="#0F172A"), zeroline=False),
            bargap=0.3,
        )
        st.plotly_chart(fig, use_container_width=True, key="dx_overlay")
        # 하단 랭킹 테이블
        rows = ""
        for ri, (nm, tc, yc) in enumerate(zip(top_dx, t_vals, y_vals), 1):
            d  = tc - yc
            dc = C["danger"] if d > 0 else C["ok"] if d < 0 else "#94A3B8"
            dt = f"▲{d:+d}" if d > 0 else f"▼{d}" if d < 0 else "─"
            bg = "#FFFFFF" if ri % 2 == 0 else "#F8FAFC"
            rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:4px 6px;font-weight:700;color:#1E40AF;">{ri}위</td>'
                f'<td style="padding:4px 5px;color:#0F172A;font-weight:500;">{nm}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:{_COL_T};font-family:Consolas,monospace;font-weight:700;">{tc}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:{_COL_Y};font-family:Consolas,monospace;">{yc}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:{dc};font-weight:700;">{dt}</td></tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:8px;border-top:1px solid #F1F5F9;">'
            f'<tr style="background:#F8FAFC;">'
            f'<th style="padding:5px 6px;color:#64748B;font-size:10px;width:30px;">#</th>'
            f'<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:left;">주상병명</th>'
            f'<th style="padding:5px 6px;color:{_COL_T};font-size:10px;text-align:right;width:34px;">금일</th>'
            f'<th style="padding:5px 6px;color:{_COL_Y};font-size:10px;text-align:right;width:34px;">전일</th>'
            f'<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:38px;">증감</th></tr>'
            f'{rows}</table>',
            unsafe_allow_html=True,
        )

    elif chart_type == "grouped":
        fig = go.Figure()
        fig.add_trace(go.Bar(x=top_dx, y=y_vals, name="전일",
            marker=dict(color=_COL_Y, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="전일: %{y}명<extra></extra>"))
        fig.add_trace(go.Bar(x=top_dx, y=t_vals, name="금일",
            marker=dict(color=_COL_T, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="금일: %{y}명<extra></extra>"))
        fig.update_layout(
            height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            barmode="group", showlegend=True,
            legend=dict(orientation="h", y=-0.2, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(**_AX, tickangle=-30, tickfont=dict(size=9)),
            yaxis=dict(**_AX, title=dict(text="입원 환자 수 (명)", font=dict(size=10))),
            margin=dict(l=0, r=0, t=8, b=60),
        )
        st.plotly_chart(fig, use_container_width=True, key="dx_grouped")

    elif chart_type == "bar_h":
        deltas      = [t - y for t, y in zip(t_vals, y_vals)]
        delta_colors = ["#EF4444" if d > 0 else "#3B82F6" if d < 0 else "#94A3B8" for d in deltas]
        anns = [
            dict(x=max(tv, yv) + 0.5, y=dx,
                 text=f"{'▲' if d > 0 else '▼' if d < 0 else '─'}{abs(d)}",
                 showarrow=False, font=dict(size=9, color=c), xanchor="left")
            for dx, tv, yv, d, c in zip(top_dx, t_vals, y_vals, deltas, delta_colors)
        ]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=t_vals, y=top_dx, orientation="h", name="금일",
            marker=dict(color=_COL_T, opacity=0.9, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="금일: %{x}명<extra></extra>"))
        fig.add_trace(go.Bar(x=y_vals, y=top_dx, orientation="h", name="전일",
            marker=dict(color=_COL_Y, opacity=0.6, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="전일: %{x}명<extra></extra>"))
        fig.update_layout(
            height=max(200, len(top_dx) * 36),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            barmode="overlay", showlegend=True,
            legend=dict(orientation="h", y=-0.15, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, range=[0, x_max],
                       title=dict(text="입원 환자 수 (명)", font=dict(size=10))),
            annotations=anns,
            margin=dict(l=0, r=50, t=8, b=40),
        )
        st.plotly_chart(fig, use_container_width=True, key="dx_bar_h")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 병동 대시보드 렌더러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _render_ward() -> None:
    """병동 대시보드 v5.2 — 차트 선택기 통합"""
    st.markdown(_WARD_CSS, unsafe_allow_html=True)

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

    # ── 데이터 조회 (2분 TTL 캐시) ───────────────────────────────────
    dept_stay    = _query_cached("ward_dept_stay")
    bed_detail   = _query_cached("ward_bed_detail")
    op_stat      = _query_cached("ward_op_stat")
    trend        = _query_cached("ward_kpi_trend")
    dx_today     = _query_cached("ward_dx_today")
    dx_trend     = _query_cached("ward_dx_trend")
    yesterday    = _query_cached("ward_yesterday")
    admit_cands  = _query_cached("admit_candidates")
    bed_room_stat: List[Dict] = _query_cached("bed_room_status")

    _show_room_panel = st.session_state.get("show_room_panel", False)
    ward_room_detail = _query_cached("ward_room_detail") if _show_room_panel else []

    _adm_total = len(admit_cands)
    _adm_done  = sum(1 for r in admit_cands if r.get("수속상태", "") == "AD")

    _all_wards = ["전체"] + sorted({
        r.get("병동명", "") for r in bed_detail
        if r.get("병동명", "") and r.get("병동명", "") != "전체"
    })
    st.session_state["ward_name_list"] = _all_wards
    _g_ward = st.session_state.get("ward_selected", "전체")

    # ── 필터 헬퍼 ────────────────────────────────────────────────────
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

    def _filter_by_ward(data: List[Dict], ward: str, ward_col: str = "병동명") -> List[Dict]:
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
                k = (r.get("기준일", ""), r.get("주상병코드", ""), r.get("주상병명", ""))
                agg[k]["환자수"] += int(r.get("환자수", 0) or 0)
            return [
                {"기준일": k[0], "병동명": "전체", "주상병코드": k[1], "주상병명": k[2], "환자수": v["환자수"]}
                for k, v in agg.items()
            ]
        return [r for r in data if r.get("병동명", "") == ward]

    # ── 필터 적용 ─────────────────────────────────────────────────────
    if _g_ward != "전체":
        bed_detail_f = _filter_by_ward(bed_detail, _g_ward)
        op_stat_f    = _filter_by_ward(op_stat, _g_ward)
        dept_stay_f  = dept_stay  # V_WARD_DEPT_STAY는 병동명 컬럼 없음 → 전체 유지
        trend_f      = _trend_dedup(trend)
    else:
        bed_detail_f = bed_detail
        dept_stay_f  = dept_stay
        op_stat_f    = op_stat
        trend_f      = _trend_dedup(trend)

    dx_today_f = _filter_dx_ward(dx_today, _g_ward)
    dx_trend_f = _filter_dx_ward(dx_trend, _g_ward)

    # ── KPI 계산 (필터 후 1회) ────────────────────────────────────────
    total_bed  = sum(int(r.get("총병상", 0) or 0)   for r in bed_detail_f)
    admit_cnt  = sum(int(r.get("금일입원", 0) or 0)  for r in bed_detail_f)
    occupied   = sum(int(r.get("재원수", 0) or 0)    for r in bed_detail_f)
    disc_cnt   = sum(int(r.get("금일퇴원", 0) or 0)  for r in bed_detail_f)
    occ_rate   = round(occupied / max(total_bed, 1) * 100, 1)

    # ── 수술 집계 (필터 후 op_stat_f) ────────────────────────────────
    _ward_surg: dict = {}
    for _sr in op_stat_f:
        _sw = _sr.get("병동명", "")
        _ward_surg[_sw] = _ward_surg.get(_sw, 0) + int(_sr.get("수술건수", 0) or 0)

    def _ds(cur: int, prev: int, unit: str = "명") -> str:
        d = cur - prev
        return f"▲ +{d}{unit}" if d > 0 else f"▼ {d}{unit}" if d < 0 else "─"

    # ── 전일 데이터 ───────────────────────────────────────────────────
    _yest_f = _filter_by_ward(yesterday, _g_ward) if _g_ward != "전체" else yesterday
    _pa = sum(int(r.get("금일입원", 0) or 0)  for r in _yest_f)
    _pd = sum(int(r.get("금일퇴원", 0) or 0)  for r in _yest_f)
    _ps = sum(int(r.get("재원수", 0) or 0)    for r in _yest_f)
    _po = round(_ps / max(total_bed, 1) * 100, 1)
    if not _yest_f:
        _pa, _pd, _ps, _po = admit_cnt, disc_cnt, occupied, occ_rate

    # ── 익일 예약 ─────────────────────────────────────────────────────
    _first_bed  = bed_detail[0] if bed_detail else {}
    _next_op    = int(_first_bed.get("익일수술예약", 0) or 0)
    _next_adm   = int(_first_bed.get("익일입원예약", 0) or 0)
    _next_disc  = int(_first_bed.get("익일퇴원예약", 0) or 0)

    _total_rest    = sum(max(0, int(r.get("총병상", 0) or 0) - int(r.get("재원수", 0) or 0)) for r in bed_detail_f)
    _total_ndc_pre = sum(int(r.get("익일퇴원예고", 0) or 0) for r in bed_detail_f)

    # ── 가동률 색상 ───────────────────────────────────────────────────
    if occ_rate >= 90:
        _oc = "#DC2626"
    elif occ_rate >= 80:
        _oc = "#F59E0B"
    else:
        _oc = "#059669"
    _do = f"▲ +{occ_rate - _po:.1f}%" if occ_rate > _po else f"▼ {occ_rate - _po:.1f}%"

    _kpi_for_llm = {
        "가동률": occ_rate, "재원수": occupied, "총병상": total_bed,
        "금일입원": admit_cnt, "금일퇴원": disc_cnt, "선택병동": _g_ward,
    }

    # ════════════════════════════════════════════════════════════
    # 병실 현황 패널 (show_room_panel=True 일 때만)
    # ════════════════════════════════════════════════════════════
    if _show_room_panel:
        _rp_ward = st.session_state.get("ward_selected", "전체")
        _rp_data = (
            [r for r in ward_room_detail if r.get("병동명", "") == _rp_ward]
            if _rp_ward != "전체" else ward_room_detail
        )
        _STATUS_CLR = {
            "재원":    ("#1D4ED8", "#DBEAFE"),
            "퇴원예정":("#7C3AED", "#EDE9FE"),
            "빈병상":  ("#16A34A", "#DCFCE7"),
            "LOCK":    ("#DC2626", "#FEE2E2"),
        }
        _rp_stay  = sum(1 for r in _rp_data if r.get("상태") == "재원")
        _rp_dc    = sum(1 for r in _rp_data if r.get("상태") == "퇴원예정")
        _rp_avail = sum(1 for r in _rp_data if r.get("상태") == "빈병상")
        _rp_lock  = sum(1 for r in _rp_data if r.get("상태") == "LOCK")

        st.markdown('<div class="wd-card" style="margin-bottom:8px;padding:14px 16px;">', unsafe_allow_html=True)
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
            _rp_total   = len(_rp_data)
            _status_opts = [
                f"전체 ({_rp_total})", f"재원 ({_rp_stay})", f"퇴원예정 ({_rp_dc})",
                f"빈병상 ({_rp_avail})", f"LOCK ({_rp_lock})",
            ]
            _status_sel = st.radio(
                "상태 필터", _status_opts, horizontal=True,
                key="rp_status_filter", label_visibility="collapsed",
            )
            _status_key = _status_sel.split(" (")[0].strip()
        st.markdown('<div style="height:1px;background:#E2E8F0;margin:8px 0 10px;"></div>', unsafe_allow_html=True)

        _rp_data_f = (
            _rp_data if _status_key == "전체"
            else [r for r in _rp_data if r.get("상태", "") == _status_key]
        )
        _col_tbl, _col_assign = st.columns([7, 3], gap="small")

        with _col_tbl:
            if not _rp_data_f:
                st.markdown(
                    '<div style="padding:32px;text-align:center;color:#94A3B8;">'
                    '<div style="font-size:24px;margin-bottom:8px;">🏥</div>'
                    '<div style="font-size:13px;font-weight:600;">병실 데이터 없음</div>'
                    '<div style="font-size:11px;margin-top:4px;">V_WARD_ROOM_DETAIL VIEW 확인</div></div>',
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
                        _bg     = "#F0F7FF" if _gi % 2 == 0 else "#F8FAFC"
                        _status = _r.get("상태", "빈병상")
                        _sc, _sbg = _STATUS_CLR.get(_status, ("#64748B", "#F1F5F9"))
                        _lock_cm  = _r.get("LOCK코멘트", "") or ""
                        _grade    = _r.get("병실등급", "") or "─"
                        _dc_dt_v  = _r.get("퇴원예정일", "") or ""
                        if _dc_dt_v and len(str(_dc_dt_v)) >= 8:
                            _dc_str  = str(_dc_dt_v)
                            _dc_disp = f"{_dc_str[4:6]}/{_dc_str[6:8]}"
                        elif _dc_dt_v:
                            _dc_disp = str(_dc_dt_v)[:10]
                        else:
                            _dc_disp = ""
                        _room_memo = (_r.get("병실메모", "") or "").strip()
                        _fee_raw   = _r.get("병실료", 0) or 0
                        _fee_str   = f"{int(_fee_raw):,}원" if _fee_raw else "─"
                        _age_v     = _r.get("나이")
                        _sex_v     = _r.get("성별")
                        _dept_v    = _r.get("진료과")
                        _age_s     = f"{int(_age_v)}세" if _age_v else "─"
                        _sex_s     = _sex_v or "─"
                        _dept_s    = _dept_v or "─"
                        _sex_c     = "#1D4ED8" if _sex_s == "남" else "#BE185D" if _sex_s == "여" else "#94A3B8"
                        _wd_td     = _r.get("병동명", "") if _bi == 0 else ""
                        _rm_td     = _beds[0][1].get("병실번호", "")[2:4] if _bi == 0 else ""
                        _wd_fw     = "font-weight:700;color:#0F172A;" if _bi == 0 else "color:#CBD5E1;"
                        _rm_fw     = "font-weight:600;color:#334155;" if _bi == 0 else "color:#CBD5E1;"
                        _dc_date_html = (
                            f'<div style="font-size:10px;color:#7C3AED;font-weight:600;margin-top:3px;font-family:Consolas,monospace;">📅 {_dc_disp}</div>'
                            if (_status == "퇴원예정" and _dc_disp) else ""
                        )
                        _memo_c  = "#334155" if _room_memo else "#CBD5E1"
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
                            (f'<td style="padding:6px 10px;text-align:center;vertical-align:middle;">'
                             f'<span style="background:{_sbg};color:{_sc};border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;">{_status}</span>'
                             f"{_dc_date_html}</td>"),
                            f'<td style="padding:7px 10px;font-size:11px;color:#F59E0B;">{_lock_disp}</td>',
                            (f'<td style="padding:7px 10px;font-size:12px;background:{_memo_bg};color:{_memo_c};'
                             f'max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                             f"{'📝 ' + _room_memo if _room_memo else '─'}</td>"),
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
            # ── 병상 수배 조건 설정 ─────────────────────────────────
            # 병동 선택
            _asgn_wards   = ["전체"] + sorted({r.get("병동명", "") for r in ward_room_detail if r.get("병동명", "")})
            _asgn_ward_sel = st.selectbox("병동", _asgn_wards, index=_asgn_wards.index(_rp_ward) if _rp_ward in _asgn_wards else 0, key="asgn_ward_sel")

            # 인실 선택
            _asgn_room_sel = st.selectbox("인실", ["전체", "1인실", "2인실", "3인실", "4인실"], key="asgn_room_sel")

            # 성별
            _asgn_sex_sel  = st.radio("성별", ["전체", "남", "여"], horizontal=True, key="asgn_sex_sel")

            # [v2.3] 진료과 드롭다운 — ward_room_detail의 실제 영문 코드 추출
            # 연령대 필터 제거: 빈병상에는 환자 정보 없어 필터 의미 없음
            # 1인실: 진료과 무관 → 진료과 선택 시 1인실 제외 안내
            _all_dept_codes = sorted({
                (r.get("진료과", "") or "").strip()
                for r in ward_room_detail
                if r.get("진료과", "") and r.get("상태") in ("재원", "퇴원예정")
            })
            _dept_opts = ["전체"] + [d for d in _all_dept_codes if d]

            # 1인실 선택 시 진료과 필터 안내
            _is_1insl = _asgn_room_sel == "1인실"
            if _is_1insl:
                st.markdown(
                    '<div style="font-size:10.5px;color:#059669;background:#DCFCE7;'
                    'border-radius:5px;padding:4px 8px;margin-bottom:4px;">'
                    '✅ 1인실은 진료과 무관 배정 가능</div>',
                    unsafe_allow_html=True,
                )
                _asgn_dept_sel = "전체"  # 1인실은 진료과 무시
            else:
                _asgn_dept_sel = st.selectbox(
                    "진료과 (영문코드)",
                    _dept_opts,
                    key="asgn_dept_sel",
                    help="현재 재원 중인 환자의 진료과 코드 기준 (예: IM=내과, GS=외과, OS=정형외과)"
                )

            if st.button("🔍 가용 병상 검색", key="asgn_search_btn", use_container_width=True, type="primary"):
                st.session_state["asgn_result_ready"] = True
            st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.get("asgn_result_ready"):
                _sw  = st.session_state.get("asgn_ward_sel", "전체")
                _sri = st.session_state.get("asgn_room_sel", "전체")
                _sdp = ("전체" if st.session_state.get("asgn_room_sel") == "1인실"
                        else st.session_state.get("asgn_dept_sel", "전체"))
                _ssx = st.session_state.get("asgn_sex_sel", "전체")

                # 1단계: 빈병상 + 병동/인실 조건 필터
                _candidates_raw = [
                    r for r in ward_room_detail
                    if r.get("상태") == "빈병상"
                    and (_sw == "전체" or r.get("병동명", "") == _sw)
                    and (_sri == "전체" or r.get("인실구분", "") == _sri)
                ]

                # 2단계: 진료과 매칭 정렬
                # 같은 병실에 해당 진료과 환자가 이미 재원 중인 병실 우선
                # (1인실은 진료과 무관이므로 _sdp=="전체"로 바이패스됨)
                if _sdp and _sdp != "전체":
                    # 해당 진료과 재원 중인 병실번호 앞 4자리 집합
                    _dept_rooms = {
                        str(r.get("병실번호", "")).zfill(6)[:4]
                        for r in ward_room_detail
                        if (r.get("진료과", "") or "").strip().upper() == _sdp.upper()
                        and r.get("상태") in ("재원", "퇴원예정")
                    }
                    _candidates = sorted(
                        _candidates_raw,
                        key=lambda r: (
                            0 if str(r.get("병실번호", "")).zfill(6)[:4] in _dept_rooms else 1,
                            r.get("병실번호", ""),
                        )
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
                        _cbno  = str(_cr.get("병실번호", "")).zfill(6)
                        _croom = _cbno[2:4]
                        _cbed  = _cbno[4:6]
                        _cward = _cr.get("병동명", "")
                        _cinsl = _cr.get("인실구분", "")
                        _cfee  = _cr.get("병실료", 0) or 0
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
    # Row 1: KPI 2행×3열 | 주간 추이
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
            _kpi_card("병상 가동률", f"{occ_rate:.1f}", "%", f"재원 {occupied} / {total_bed}병상", _oc_color, delta=_do, bar_pct=occ_rate)
        with _r1c2:
            _kpi_card("금일 퇴원", str(disc_cnt), "명", f"전일 {_pd}명", "#475569", delta=_ds(disc_cnt, _pd))
        with _r1c3:
            _kpi_card("금일 입원", str(admit_cnt), "명", f"전일 {_pa}명", C["primary_text"], delta=_ds(admit_cnt, _pa))

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        _r2c1, _r2c2, _r2c3 = st.columns(3, gap="small")
        with _r2c1:
            _kpi_card("재원 환자", str(occupied), "명", "전일 대비", "#0F172A", delta=_ds(occupied, _ps))
        with _r2c2:
            _today_op_total = sum(_ward_surg.values())
            _kpi_card("금일 수술", str(_today_op_total), "건", f"익일 예약 {_next_op}건", "#7C3AED")
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

    # ════════════════════════════════════════════════════════════
    # [v2.2] 주간 추이 7일 — 차트 선택기 통합
    # 기본: 테이블 (기존 HTML 표) / 라인 / 영역 / 막대 선택 가능
    # ════════════════════════════════════════════════════════════
    with _col_trend:
        _oc_c_trend = "#EF4444" if occ_rate >= 90 else "#F59E0B" if occ_rate >= 80 else "#16A34A"

        st.markdown('<div class="wd-card" style="padding:14px 16px;">', unsafe_allow_html=True)

        # ── [v2.2] 섹션 헤더 + pill 선택기 ────────────────────────────
        chart_type_trend = _chart_selector("weekly_trend", "주간 추이 7일", _g_ward)

        # ── 현재 KPI 요약 (어느 타입이든 항상 표시) ─────────────────────
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;'
            f'padding-bottom:6px;border-bottom:1px solid #F1F5F9;">'
            f'<span style="font-size:12px;color:#64748B;">재원</span>'
            f'<b style="font-size:14px;color:#0F172A;font-family:Consolas,monospace;">{occupied}명</b>'
            f'<span style="font-size:12px;color:#64748B;">가동률</span>'
            f'<b style="font-size:14px;color:{_oc_c_trend};font-family:Consolas,monospace;">{occ_rate:.1f}%</b>'
            f"</div>",
            unsafe_allow_html=True,
        )

        if trend_f:
            # 전일 기준 7일치만 표시 — 금일(오늘)은 KPI 카드로 확인
            # 금일 기준일 제외: today 문자열과 일치하는 행 제거 후 마지막 7개
            _today_str = time.strftime('%Y-%m-%d')
            _trend_no_today = [
                r for r in trend_f
                if str(r.get('기준일', ''))[:10] != _today_str
            ]
            # 날짜 오름차순 정렬 후 마지막 7개 (전일 포함 7일)
            _trend_7 = sorted(_trend_no_today, key=lambda r: str(r.get('기준일', '')))[-7:]
            _render_trend_chart(_trend_7, chart_type_trend, occupied, occ_rate)
        else:
            st.markdown(
                '<div style="display:flex;align-items:center;justify-content:center;'
                'min-height:160px;color:#94A3B8;flex-direction:column;gap:8px;">'
                '<div style="font-size:28px;">📊</div>'
                '<div style="font-size:13px;font-weight:600;">추이 데이터 없음</div>'
                f'<div style="font-size:11px;color:#64748B;">'
                + ("Oracle 미연결" if not st.session_state.get("oracle_ok", False) else "V_WARD_KPI_TREND 확인")
                + "</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 2: 익일 예약 수용률 계산 + 패널
    # ════════════════════════════════════════════════════════════
    _total_avail  = _total_rest + _total_ndc_pre
    _cap_sum_c2   = "#16A34A" if _total_avail > 5 else "#F59E0B" if _total_avail > 0 else "#EF4444"
    _adm_cap_pct  = round(_next_adm / max(_total_avail, 1) * 100)
    _adm_cap_color = "#EF4444" if _adm_cap_pct >= 90 else "#F59E0B" if _adm_cap_pct >= 70 else "#16A34A"


    # ════════════════════════════════════════════════════════════
    # Row 3: 병동별 당일 현황 [4] | 진료과별 재원 구성 [2]
    # [v2.2] 두 섹션 모두 차트 선택기 통합
    # ════════════════════════════════════════════════════════════
    col_L, col_R = st.columns([4, 2], gap="small")

    # ── [v2.2] 병동별 당일 현황 ─────────────────────────────────────
    with col_L:
        st.markdown('<div class="wd-card">', unsafe_allow_html=True)

        # ── [v2.2] 섹션 헤더 + pill 선택기 ─────────────────────────────
        chart_type_ward = _chart_selector("ward_detail", "병동별 당일 현황")

        if chart_type_ward == "table":
            # ── 기존 풍부한 HTML 테이블 (퇴원예정, 수술, 잔여병상, 익일가용 포함) ──
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
                    bg    = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                    rate  = float(r.get("가동률", 0) or 0)
                    adm   = int(r.get("금일입원", 0) or 0)
                    stay  = int(r.get("재원수", 0) or 0)
                    disc  = int(r.get("금일퇴원", 0) or 0)
                    tot   = int(r.get("총병상", 0) or 0)
                    rest  = max(0, tot - stay)
                    n_disc  = int(r.get("익일퇴원예고", 0) or 0)
                    n_avail = max(0, rest + n_disc)
                    r_cls = "#DC2626" if rate >= 90 else "#F59E0B" if rate >= 80 else "#059669"
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
                _tb    = sum(int(r.get("총병상", 0) or 0) for r in bed_detail_f)
                _ta    = sum(int(r.get("금일입원", 0) or 0) for r in bed_detail_f)
                _ts    = sum(int(r.get("재원수", 0) or 0) for r in bed_detail_f)
                _td2   = sum(int(r.get("금일퇴원", 0) or 0) for r in bed_detail_f)
                _tndc  = sum(int(r.get("익일퇴원예고", 0) or 0) for r in bed_detail_f)
                _tr    = round(_ts / max(_tb, 1) * 100, 1)
                _sth   = "padding:8px 12px;background:#EFF6FF;border-top:2px solid #BFDBFE;vertical-align:middle;font-weight:700;"
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
                    f'<div style="display:flex;align-items:center;gap:0;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:5px;padding:2px 0;">'
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
                    '<div style="font-size:13px;font-weight:600;color:#64748B;">병동 현황 데이터 없음</div></div>'
                )
            st.markdown(body, unsafe_allow_html=True)

        else:
            # bar_h 또는 heatmap: 인라인 렌더러 사용
            _render_ward_alt_chart(bed_detail_f, chart_type_ward, _ward_surg)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── [v2.2] 진료과별 재원 구성 ────────────────────────────────────
    with col_R:
        st.markdown('<div class="wd-card" style="padding:12px 14px;">', unsafe_allow_html=True)

        _gw_p2 = st.session_state.get("ward_selected", "전체")

        # ── [v2.2] 섹션 헤더 + pill 선택기 ─────────────────────────────
        chart_type_dept = _chart_selector(
            "dept_stay", "진료과별 재원 구성",
            _gw_p2 if _gw_p2 != "전체" else "",
        )

        # 선택된 타입으로 렌더링 (donut/bar_h/treemap 모두 _render_dept_chart 처리)
        _render_dept_chart(dept_stay_f, chart_type_dept)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 4: 주상병 분석
    # [v2.2] 최근 7일 / 금일 vs 전일 — 차트 선택기 통합
    # ════════════════════════════════════════════════════════════
    from collections import defaultdict as _dd

    col_pie, col_bar = st.columns([1, 1], gap="small")

    # ── [v2.2] 최근 7일 입원 주상병 분포 ─────────────────────────────
    with col_pie:
        st.markdown('<div class="wd-card" style="padding:12px;">', unsafe_allow_html=True)

        chart_type_dx7 = _chart_selector("dx_7day", "최근 7일 입원 주상병 분포")
        _render_dx7_chart(dx_trend, chart_type_dx7)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── [v2.2] 금일 vs 전일 입원 주상병 분포 ─────────────────────────
    with col_bar:
        st.markdown('<div class="wd-card" style="padding:12px;">', unsafe_allow_html=True)

        chart_type_compare = _chart_selector("dx_compare", "금일 vs 전일 입원 주상병 분포")
        _render_dx_compare_chart(dx_today, chart_type_compare)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # Row 5: AI 분석 채팅
    # ════════════════════════════════════════════════════════════
    # ════════════════════════════════════════════════════════════
    # 익일 입원 예약 상세 (하단 고정 표시)
    # ════════════════════════════════════════════════════════════
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
        _age_bins = {"10대이하": 0, "20대": 0, "30대": 0, "40대": 0, "50대": 0, "60대": 0, "70대이상": 0}
        for _ac in admit_cands:
            _dn  = _ac.get("진료과명", "기타")
            _sx  = _ac.get("성별", "M")
            _age = int(_ac.get("나이", 0) or 0)
            if _sx == "M":
                _dept_m[_dn] += 1
            else:
                _dept_f[_dn] += 1
            _ab = "70대이상" if _age >= 70 else f"{(_age // 10) * 10}대" if _age >= 20 else "10대이하"
            if _ab in _age_bins:
                _age_bins[_ab] += 1
        _all_depts = sorted(set(list(_dept_m) + list(_dept_f)))
        _m_vals = [_dept_m.get(d, 0) for d in _all_depts]
        _f_vals = [_dept_f.get(d, 0) for d in _all_depts]
        import plotly.graph_objects as _go2
        _fig_adm = _go2.Figure()
        _fig_adm.add_trace(_go2.Bar(name="남성", x=_all_depts, y=_m_vals, marker_color="#3B82F6", text=_m_vals, textposition="outside", textfont=dict(size=11, color="#1E40AF")))
        _fig_adm.add_trace(_go2.Bar(name="여성", x=_all_depts, y=_f_vals, marker_color="#F472B6", text=_f_vals, textposition="outside", textfont=dict(size=11, color="#9D174D")))
        _fig_adm.update_layout(
            barmode="group", height=210, margin=dict(l=0, r=0, t=16, b=8),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=11),
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center", font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(tickfont=dict(size=11), gridcolor="rgba(0,0,0,0)"),
            yaxis=dict(gridcolor="rgba(226,232,240,0.5)", tickfont=dict(size=10), zeroline=False),
            bargap=0.25, bargroupgap=0.05,
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
                f'<div style="font-size:11px;font-weight:700;color:#64748B;margin-bottom:6px;text-transform:uppercase;letter-spacing:.07em;">연령대 분포</div>'
                f"{_age_html}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="padding:32px;text-align:center;color:#94A3B8;">'
            '<div style="font-size:28px;margin-bottom:8px;">📋</div>'
            '<div style="font-size:13px;font-weight:600;color:#64748B;">예약 환자 데이터 없음</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div style="border-top:1px solid #E2E8F0;margin:14px 0 10px;"></div>', unsafe_allow_html=True)
    _render_bed_assignment(bed_detail_f, admit_cands, _ward_surg, bed_room_stat if "bed_room_stat" in dir() else [])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── AI 채팅 카드: 구분선 강조 + 상태 표시 ─────────────────────
    _llm_avail = True
    try:
        from core.llm import get_llm_client as _gc; _gc()
    except Exception:
        _llm_avail = False
    _ai_badge = (
        '<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;'
        'background:#DCFCE7;color:#15803D;border:1px solid #86EFAC;'
        'border-radius:4px;padding:1px 7px;font-weight:600;margin-left:8px;">연결됨</span>'
        if _llm_avail else
        '<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;'
        'background:#FEE2E2;color:#991B1B;border:1px solid #FCA5A5;'
        'border-radius:4px;padding:1px 7px;font-weight:600;margin-left:8px;">미연결</span>'
    )
    st.markdown(
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;'
        f'box-shadow:0 2px 8px rgba(30,64,175,0.06);margin-top:8px;overflow:hidden;">'
        f'<div style="background:linear-gradient(135deg,#1E3A8A 0%,#1E40AF 50%,#2563EB 100%);'
        f'padding:12px 18px;display:flex;align-items:center;gap:10px;">'
        f'<div style="width:32px;height:32px;background:rgba(255,255,255,0.15);'
        f'border-radius:8px;display:flex;align-items:center;justify-content:center;'
        f'font-size:18px;flex-shrink:0;">🤖</div>'
        f'<div style="flex:1;">'
        f'<div style="font-size:14px;font-weight:700;color:#FFFFFF;letter-spacing:-0.01em;">AI 병동 분석 채팅{_ai_badge}</div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:1px;">'
        f'금일 병동 운영 데이터를 기반으로 실시간 분석 · 위험도 평가 · 운영 조언 제공</div>'
        f'</div></div>'
        f'<div style="padding:14px 16px;">',
        unsafe_allow_html=True,
    )
    _render_ward_llm_chat(kpi=_kpi_for_llm, bed_occ=[], bed_detail=bed_detail_f, op_stat=op_stat_f)
    st.markdown("</div></div>", unsafe_allow_html=True)


# ── 병상 배정 어시스트 ───────────────────────────────────────────────

def _render_bed_assignment(
    bed_detail: List[Dict],
    admit_cands: List[Dict],
    ward_surg: Dict[str, int],
    bed_room_stat: List[Dict] = None,
) -> None:
    """
    병상 배정 어시스트 v2.3 — 병실 수배 패널 스타일로 재설계

    [구성]
    좌: 조건 입력 (예약환자 선택 OR 직접 입력)
    우: 추천 결과 테이블 (병동별 가용병상, 가동률, 병실 현황 드릴다운)
    """
    # ── 헤더 ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="wd-card" style="margin-top:6px;">'
        '<div style="display:flex;align-items:center;gap:8px;padding-bottom:10px;'
        'margin-bottom:10px;border-bottom:1px solid #F1F5F9;">'
        '<span style="display:inline-block;width:3px;height:16px;background:'
        'linear-gradient(180deg,#1E40AF,#60A5FA);border-radius:2px;"></span>'
        '<span style="font-size:13px;font-weight:700;color:#0F172A;">병상 배정 어시스트</span>'
        '<span style="font-size:11px;color:#94A3B8;font-weight:400;">'
        '성별 · 연령 · 진료과 · 인실 조건으로 최적 병동 추천</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_f, col_r = st.columns([3, 7], gap="small")

    # ── 좌: 조건 입력 패널 ────────────────────────────────────────
    with col_f:
        st.markdown(
            '<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:14px;">'
            '<div style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;'
            'letter-spacing:.06em;margin-bottom:10px;">🔍 조건 설정</div>',
            unsafe_allow_html=True,
        )

        _mode = st.radio(
            "입력 방식",
            ["예약 환자", "직접 입력"],
            horizontal=True,
            key="ba_mode",
        )

        _ba_sex = _ba_age = "전체"
        _ba_dept = ""
        _ba_room = "전체"
        _pt_info = ""

        if _mode == "예약 환자":
            if admit_cands:
                _opts = ["— 환자 선택 —"] + [
                    f"{r.get('진료과명','?')} | "
                    f"{'남' if r.get('성별','M')=='M' else '여'} | "
                    f"{r.get('나이','?')}세"
                    for r in admit_cands
                ]
                _sel = st.selectbox("환자", _opts, key="ba_pt_sel", label_visibility="collapsed")
                if _sel != "— 환자 선택 —":
                    _idx = _opts.index(_sel) - 1
                    _pt  = admit_cands[_idx]
                    _ba_sex  = "남" if _pt.get("성별", "M") == "M" else "여"
                    _age_val = int(_pt.get("나이", 0) or 0)
                    _ba_age  = (
                        "70대이상" if _age_val >= 70
                        else f"{(_age_val // 10) * 10}대" if _age_val >= 20
                        else "10대이하"
                    )
                    _ba_dept = _pt.get("진료과명", "")
                    _sex_icon = "🔵" if _ba_sex == "남" else "🔴"
                    _pt_info = (
                        f'<div style="margin-top:8px;padding:8px 10px;background:#EFF6FF;'
                        f'border-radius:6px;font-size:11.5px;color:#1E40AF;line-height:1.6;">'
                        f'<b>{_ba_dept}</b> &nbsp;{_sex_icon} {_ba_sex}성 &nbsp; {_pt.get("나이","?")}세</div>'
                    )
            else:
                st.info("예약 환자 없음")
        else:
            _ba_sex  = st.radio("성별", ["전체", "남", "여"], horizontal=True, key="ba_sex_r")
            _ba_age  = st.selectbox(
                "연령대",
                ["전체","10대이하","20대","30대","40대","50대","60대","70대이상"],
                key="ba_age_sel", label_visibility="collapsed",
            )
            _ba_dept = st.text_input("진료과", key="ba_dept_inp", placeholder="예: 내과, 외과")

        _ba_room = st.selectbox(
            "희망 인실",
            ["전체", "1인실", "2인실", "3인실", "4인실 이상"],
            key="ba_room_sel",
        )

        _do_search = st.button(
            "🔍 병상 추천",
            key="ba_search",
            type="primary",
            use_container_width=True,
        )

        if _pt_info:
            st.markdown(_pt_info, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── 우: 추천 결과 ─────────────────────────────────────────────
    with col_r:
        if _do_search:
            st.session_state.update({
                "ba_result_ready": True,
                "ba_sex_v":  _ba_sex,
                "ba_age_v":  _ba_age,
                "ba_dept_v": _ba_dept,
                "ba_room_v": _ba_room,
            })

        if not st.session_state.get("ba_result_ready"):
            st.markdown(
                '<div style="display:flex;flex-direction:column;align-items:center;'
                'justify-content:center;min-height:240px;color:#CBD5E1;gap:8px;">'
                '<div style="font-size:40px;">🏥</div>'
                '<div style="font-size:13px;font-weight:600;color:#94A3B8;">좌측 조건 설정 후</div>'
                '<div style="font-size:12px;color:#CBD5E1;">🔍 병상 추천을 클릭하세요</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            _sx = st.session_state.get("ba_sex_v", "전체")
            _dp = st.session_state.get("ba_dept_v", "").strip().upper()
            _rm = st.session_state.get("ba_room_v", "전체")
            _is_1insl = (_rm == "1인실")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 병상 추천 순서도 (v2.3)
            #
            # ① 기본 조건: 가용 병상(총병상-재원) > 0
            # ② 인실 매칭: 희망 인실 있는 병동 +30점
            #    - 1인실: 진료과 매칭 스킵 (독립 병실, 무관)
            # ③ 진료과 매칭: bed_room_stat 재원 환자 진료과 코드 기준 +40점
            #    - 병동명 텍스트 비교 아님, 실제 재원 환자 코드 비교
            #    - 1인실 선택 시 이 단계 스킵
            # ④ 성별 동일 병실: 2인실 이상에서만 +20점
            #    - 1인실은 성별 무관이므로 스킵
            # ⑤ 가동률 낮은 병동: (100 - 가동률) 점수화
            # ⑥ 익일 가용 병상 수: × 2 가중치 (퇴원 예정 포함)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            # 사전 계산: 병동별 진료과 코드 집합 (bed_room_stat 기반)
            # {병동명: {진료과코드, ...}} — 재원/퇴원예정 환자만
            _ward_depts: dict = {}
            _ward_sex_rooms: dict = {}  # {병동명: {"남": [병실번호...], "여": [...]}}
            for _r in (bed_room_stat or []):
                _rw   = _r.get("병동명", "")
                _rdpt = (_r.get("진료과", "") or "").strip().upper()
                if _rdpt:
                    _ward_depts.setdefault(_rw, set()).add(_rdpt)

            # 병동별 성별 분포 (bed_room_stat에서 재원 환자 성별)
            for _r in (bed_room_stat or []):
                if _r.get("상태") not in ("재원", "퇴원예정"):
                    continue
                _rw  = _r.get("병동명", "")
                _rsx = _r.get("성별", "")
                _rno = str(_r.get("병실번호", "")).zfill(6)[:4]
                if _rsx and _rw:
                    _ward_sex_rooms.setdefault(_rw, {}).setdefault(_rsx, set()).add(_rno)

            _scored = []
            for _bd in bed_detail:
                _wn    = _bd.get("병동명", "")
                _total = int(_bd.get("총병상", 0) or 0)
                _stay  = int(_bd.get("재원수", 0) or 0)
                _avail = max(0, _total - _stay)
                _nxt   = int(_bd.get("익일가용병상", 0) or _avail)
                _rate  = float(_bd.get("가동률", 0) or 0)
                _adm   = int(_bd.get("금일입원", 0) or 0)
                _disc  = int(_bd.get("금일퇴원", 0) or 0)
                if _avail <= 0:
                    continue

                _score = 0
                _tags  = []

                # ⑤⑥ 기본 점수: 여유 + 익일 가용
                _score += (100 - _rate)        # 가동률 낮을수록 +
                _score += _nxt * 2             # 익일 가용 가중

                # ② 인실 매칭: 희망 인실이 있는 병동 가산
                if _rm != "전체":
                    _has_room_type = any(
                        r.get("인실구분", "") == _rm and r.get("상태") == "빈병상"
                        for r in (bed_room_stat or []) if r.get("병동명", "") == _wn
                    )
                    if _has_room_type:
                        _score += 30
                        _tags.append(f"{_rm} 가용")
                    else:
                        # 희망 인실 없으면 순위 대폭 하락
                        _score -= 60

                # ③ 진료과 매칭 (1인실은 스킵)
                if _dp and not _is_1insl:
                    _wn_depts = _ward_depts.get(_wn, set())
                    if _dp in _wn_depts:
                        _score += 40
                        _tags.append(f"{_dp} 재원 병동")

                # ④ 성별 동일 병실 (2인실 이상, 1인실 스킵)
                if _sx != "전체" and not _is_1insl:
                    _sex_rooms = _ward_sex_rooms.get(_wn, {})
                    if _sx in _sex_rooms and _sex_rooms[_sx]:
                        _score += 20
                        _tags.append(f"{_sx}성 병실 있음")

                _scored.append((_score, _wn, _total, _stay, _avail, _nxt, _rate, _adm, _disc, _tags))

            _scored.sort(key=lambda x: -x[0])
            _top5 = _scored[:5]

            # ── 조건 태그 ────────────────────────────────────────
            _conds = [c for c in [
                f"성별 {_sx}" if _sx != "전체" else "",
                f"진료과 {_dp}" if _dp and not _is_1insl else "",
                f"{_rm}" if _rm != "전체" else "",
                "1인실 (진료과 무관)" if _is_1insl else "",
            ] if c]
            _tag_html = "".join(
                f'<span style="background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;'
                f'border-radius:4px;padding:1px 8px;font-size:10.5px;font-weight:600;">{c}</span> '
                for c in _conds
            ) if _conds else '<span style="color:#94A3B8;font-size:11px;">조건 없음 (전체 병동)</span>'

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:10px;">'
                f'<span style="font-size:11px;font-weight:700;color:#475569;">추천 결과</span>'
                f'<span style="font-size:11px;color:#94A3B8;">· 가용 병상 순</span>'
                f'&nbsp;{_tag_html}</div>',
                unsafe_allow_html=True,
            )

            if not _top5:
                st.markdown(
                    '<div style="padding:32px;text-align:center;color:#94A3B8;">'
                    '<div style="font-size:28px;margin-bottom:8px;">⚠️</div>'
                    '<div style="font-size:13px;font-weight:600;color:#EF4444;">조건에 맞는 가용 병동 없음</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                # ── 추천 결과 테이블 (병실 수배 스타일) ──────────
                _TH = (
                    "padding:7px 10px;font-size:10.5px;font-weight:700;"
                    "text-transform:uppercase;letter-spacing:.05em;"
                    "color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
                )
                _tbl = (
                    '<div style="overflow-x:auto;">'
                    '<table style="width:100%;border-collapse:collapse;">'
                    '<thead><tr>'
                    f'<th style="{_TH}text-align:left;width:24px;"></th>'
                    f'<th style="{_TH}text-align:left;">병동명</th>'
                    f'<th style="{_TH}text-align:right;">총병상</th>'
                    f'<th style="{_TH}text-align:right;">재원</th>'
                    f'<th style="{_TH}text-align:right;color:#16A34A;">잔여</th>'
                    f'<th style="{_TH}text-align:right;color:#7C3AED;">익일가용</th>'
                    f'<th style="{_TH}text-align:right;">가동률</th>'
                    f'<th style="{_TH}text-align:right;">금일입원</th>'
                    f'<th style="{_TH}text-align:right;">금일퇴원</th>'
                    f'<th style="{_TH}text-align:right;">수술</th>'
                    f'<th style="{_TH}text-align:center;">병실</th>'
                    '</tr></thead><tbody>'
                )

                _RANK_BG = ["#EFF6FF","#F0FDF4","#FFFBEB","#F8FAFC","#F8FAFC"]
                _RANK_BD = ["#BFDBFE","#86EFAC","#FDE68A","#E2E8F0","#E2E8F0"]
                _RANK_NO = ["#1E40AF","#059669","#D97706","#94A3B8","#CBD5E1"]

                for _ri, (_sc, _wn, _total, _stay, _avail, _nxt, _rate, _adm, _disc, _tags) in enumerate(_top5):
                    _rt_c   = "#EF4444" if _rate >= 90 else "#F59E0B" if _rate >= 80 else "#059669"
                    _av_c   = "#16A34A" if _avail > 2 else "#F59E0B" if _avail > 0 else "#EF4444"
                    _nxt_c  = "#7C3AED" if _nxt > 0 else "#94A3B8"
                    _rbg    = _RANK_BG[min(_ri, 4)]
                    _rbd    = _RANK_BD[min(_ri, 4)]
                    _rno    = _RANK_NO[min(_ri, 4)]
                    _surg   = ward_surg.get(_wn, 0)
                    _tag_s  = " ".join(f"[{t}]" for t in _tags) if _tags else ""
                    _rm_key = f"show_room_{_wn.replace(' ','_')}"
                    _rm_open = st.session_state.get(_rm_key, False)
                    _btn_lbl = "▲" if _rm_open else "🏠"

                    _tbl += (
                        f'<tr style="background:{_rbg};border-left:3px solid {_rbd};">'
                        # 순위 배지
                        f'<td style="padding:8px 6px;text-align:center;">'
                        f'<span style="background:{_rno};color:#fff;border-radius:50%;'
                        f'width:20px;height:20px;display:inline-flex;align-items:center;'
                        f'justify-content:center;font-size:10px;font-weight:700;">{_ri+1}</span></td>'
                        # 병동명 + 태그
                        f'<td style="padding:8px 10px;">'
                        f'<div style="font-size:13px;font-weight:700;color:#0F172A;">{_wn}</div>'
                        f'{"<div style=" + chr(39) + "font-size:9.5px;color:#7C3AED;margin-top:1px;" + chr(39) + ">" + _tag_s + "</div>" if _tag_s else ""}'
                        f'</td>'
                        # 수치 컬럼
                        f'<td style="padding:8px 10px;text-align:right;color:#64748B;font-family:Consolas,monospace;font-size:12px;">{_total}</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:#0F172A;font-family:Consolas,monospace;font-weight:600;font-size:12px;">{_stay}</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:{_av_c};font-family:Consolas,monospace;font-weight:700;font-size:13px;">{_avail}</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:{_nxt_c};font-family:Consolas,monospace;font-weight:600;font-size:12px;">{_nxt if _nxt else "─"}</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:{_rt_c};font-family:Consolas,monospace;font-weight:700;font-size:12px;">{_rate:.0f}%</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:#1D4ED8;font-family:Consolas,monospace;font-size:12px;">{_adm}</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:#475569;font-family:Consolas,monospace;font-size:12px;">{_disc}</td>'
                        f'<td style="padding:8px 10px;text-align:right;color:{"#8B5CF6" if _surg else "#CBD5E1"};font-family:Consolas,monospace;font-size:12px;">{_surg if _surg else "─"}</td>'
                        # 병실 현황 버튼 (텍스트로만)
                        f'<td style="padding:8px 6px;text-align:center;width:36px;" id="room_btn_{_ri}"></td>'
                        f'</tr>'
                    )

                _tbl += (
                    '<tr style="background:#F8FAFC;border-top:1.5px solid #E2E8F0;">'
                    '<td colspan="11" style="padding:4px 10px;">'
                    '<div style="display:flex;gap:8px;font-size:10px;">'
                    '<span style="color:#059669;font-weight:700;">■ 잔여: 가용 병상 수</span>'
                    '<span style="color:#EF4444;font-weight:700;">■ 가동률 ≥90% 위험</span>'
                    '<span style="color:#F59E0B;font-weight:700;">■ 가동률 80~90% 주의</span>'
                    '</div></td></tr>'
                    '</tbody></table></div>'
                )
                st.markdown(_tbl, unsafe_allow_html=True)

                # ── 병실 현황 드릴다운 (병동 선택 후 펼치기) ────
                st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
                for _ri, (_sc, _wn, *_rest) in enumerate(_top5):
                    _rm_key  = f"show_room_{_wn.replace(' ','_')}"
                    _rm_open = st.session_state.get(_rm_key, False)
                    _btn_c1, _btn_c2 = st.columns([8, 2], gap="small")
                    with _btn_c1:
                        st.markdown(
                            f'<div style="font-size:12px;font-weight:600;color:#334155;'
                            f'padding:4px 0;line-height:2;">{_wn}</div>',
                            unsafe_allow_html=True,
                        )
                    with _btn_c2:
                        if st.button(
                            "▲ 접기" if _rm_open else "🏠 병실",
                            key=f"ba_room_btn_{_ri}",
                            type="secondary",
                            use_container_width=True,
                        ):
                            st.session_state[_rm_key] = not _rm_open
                            st.rerun()

                    if _rm_open:
                        _rms = [r for r in (bed_room_stat or []) if r.get("병동명", "") == _wn]
                        if _rms:
                            _STATUS_CLR = {
                                "재원":    ("#1D4ED8", "#DBEAFE"),
                                "퇴원예정":("#7C3AED", "#EDE9FE"),
                                "빈병상":  ("#16A34A", "#DCFCE7"),
                                "LOCK":    ("#DC2626", "#FEE2E2"),
                            }
                            _TH2 = (
                                "padding:5px 8px;font-size:10px;font-weight:700;"
                                "text-transform:uppercase;letter-spacing:.05em;"
                                "color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
                            )
                            _rm_tbl = (
                                f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                                f'border-radius:8px;padding:10px;margin:4px 0 8px;">'
                                f'<div style="font-size:10px;font-weight:700;color:#1E40AF;'
                                f'text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;">'
                                f'🏥 {_wn} 병실 현황</div>'
                                f'<table style="width:100%;border-collapse:collapse;">'
                                f'<thead><tr>'
                                f'<th style="{_TH2}text-align:left;">병실번호</th>'
                                f'<th style="{_TH2}text-align:center;">인실</th>'
                                f'<th style="{_TH2}text-align:right;color:#16A34A;">빈병상</th>'
                                f'<th style="{_TH2}text-align:right;color:#EF4444;">LOCK</th>'
                                f'<th style="{_TH2}text-align:center;">상태</th>'
                                f'<th style="{_TH2}text-align:left;">비고</th>'
                                f'</tr></thead><tbody>'
                            )
                            for _i, _rmr in enumerate(_rms):
                                _empty  = int(_rmr.get("빈병상수", 0) or 0)
                                _lock   = int(_rmr.get("LOCK병상수", 0) or 0)
                                _reason = _rmr.get("LOCK사유", "") or ""
                                _status = _rmr.get("상태", "")
                                _sc2, _sbg2 = _STATUS_CLR.get(_status, ("#64748B", "#F1F5F9"))
                                _ec = "#16A34A" if _empty > 0 else "#94A3B8"
                                _lc = "#EF4444" if _lock  > 0 else "#CBD5E1"
                                _bg2 = "#FFFFFF" if _i % 2 == 0 else "#F8FAFC"
                                _rm_tbl += (
                                    f'<tr style="background:{_bg2};border-bottom:1px solid #F1F5F9;">'
                                    f'<td style="padding:6px 8px;font-weight:600;color:#0F172A;font-size:12px;">'
                                    f'{_rmr.get("병실번호","")}</td>'
                                    f'<td style="padding:6px 8px;text-align:center;color:#475569;font-size:12px;">'
                                    f'{_rmr.get("인실구분","")}</td>'
                                    f'<td style="padding:6px 8px;text-align:right;font-weight:700;'
                                    f'color:{_ec};font-family:Consolas,monospace;font-size:12px;">{_empty}</td>'
                                    f'<td style="padding:6px 8px;text-align:right;font-weight:700;'
                                    f'color:{_lc};font-family:Consolas,monospace;font-size:12px;">'
                                    f'{str(_lock) if _lock else "─"}</td>'
                                    f'<td style="padding:6px 8px;text-align:center;">'
                                    f'<span style="background:{_sbg2};color:{_sc2};border-radius:4px;'
                                    f'padding:1px 7px;font-size:10.5px;font-weight:600;">'
                                    f'{_status if _status else "─"}</span></td>'
                                    f'<td style="padding:6px 8px;font-size:11px;color:#F59E0B;">'
                                    f'{"🔒 " + _reason if _reason else "─"}</td>'
                                    f'</tr>'
                                )
                            _rm_tbl += '</tbody></table></div>'
                            st.markdown(_rm_tbl, unsafe_allow_html=True)
                        else:
                            st.markdown(
                                f'<div style="padding:10px 14px;background:#FFF8F0;border-radius:6px;'
                                f'border:1px solid #FDE68A;font-size:12px;color:#92400E;margin-bottom:8px;">'
                                f'⚠️ <b>{_wn}</b> 병실 데이터 없음 — V_BED_ROOM_STATUS VIEW 확인</div>',
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
    """
    병동 현황 AI 분석 채팅 v2.3

    [개선 사항]
    - 빠른 질문 버튼: 자주 쓰는 분석 질문을 원클릭으로 입력
    - 컨텍스트 요약 배지: 현재 KPI를 채팅 상단에 표시
    - 스트리밍 응답 유지
    - PII 마스킹 유지
    """
    import re as _re

    # ── 시스템 프롬프트 구성 ─────────────────────────────────────────
    _occ   = kpi.get("가동률", 0) or 0
    _stay  = kpi.get("재원수", 0) or 0
    _beds  = kpi.get("총병상", 0) or 0
    _adm   = kpi.get("금일입원", 0) or 0
    _disc  = kpi.get("금일퇴원", 0) or 0
    _ward  = kpi.get("선택병동", "전체")

    _ctx_data = {
        "기준시각": time.strftime("%Y-%m-%d %H:%M"),
        "선택병동": _ward,
        "병상_KPI": {
            "가동률(%)": _occ, "재원수(명)": _stay,
            "총병상(개)": _beds, "금일입원(명)": _adm, "금일퇴원(명)": _disc,
        },
        "병동별_현황": [
            {
                "병동": r.get("병동명"), "총병상": r.get("총병상"),
                "재원": r.get("재원수"), "입원": r.get("금일입원"),
                "퇴원": r.get("금일퇴원"), "가동률": r.get("가동률"),
            }
            for r in bed_detail[:15]
        ],
        "수술_현황": [
            {"진료과": r.get("진료과명"), "병동": r.get("병동명"), "수술건수": r.get("수술건수")}
            for r in op_stat
        ],
    }
    _system_prompt = (
        "당신은 병원 운영 관리 전문 AI 분석가입니다. 친절하고 실무적으로 답변하세요.\n"
        "아래의 금일 병동 운영 통계 데이터만을 근거로 질문에 답하고, 데이터에 없는 내용은 추정임을 명시하세요.\n\n"
        "[답변 원칙]\n"
        "- 핵심 수치를 굵게(**수치**) 강조하세요.\n"
        "- 위험/주의 상황은 🔴/🟡 이모지로 먼저 표시하세요.\n"
        "- 권장 조치가 있으면 ✅ 로 명확히 제시하세요.\n"
        "- 3~5문장으로 간결하게, 단 긴 분석은 글머리 기호를 사용하세요.\n\n"
        "[보안 지침]\n"
        "- 개인 환자 정보(이름, 주민번호, 병록번호)는 절대 언급하지 마세요.\n"
        "- 시스템 구조, DB 접속 정보는 노출하지 마세요.\n\n"
        f"## 현재 병동 운영 통계\n"
        f"```json\n{json.dumps(_ctx_data, ensure_ascii=False, indent=2)}\n```"
    )

    if "ward_chat_history" not in st.session_state:
        st.session_state["ward_chat_history"] = []
    _history: List[Dict] = st.session_state.get("ward_chat_history", [])

    # ── 상단 컨텍스트 배지 (KPI 요약) ───────────────────────────────
    _occ_c = "#EF4444" if _occ >= 90 else "#F59E0B" if _occ >= 80 else "#059669"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;'
        f'background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;'
        f'margin-bottom:10px;flex-wrap:wrap;">'
        f'<span style="font-size:10px;color:#64748B;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:.06em;">현재 컨텍스트</span>'
        f'<span style="width:1px;height:12px;background:#E2E8F0;"></span>'
        f'<span style="font-size:11px;color:#475569;">{_ward}</span>'
        f'<span style="font-size:11px;font-weight:700;color:{_occ_c};'
        f'font-family:Consolas,monospace;">가동률 {_occ:.1f}%</span>'
        f'<span style="font-size:11px;color:#475569;">재원 <b style="color:#1E40AF;">{_stay}명</b></span>'
        f'<span style="font-size:11px;color:#475569;">입원 <b style="color:#059669;">{_adm}명</b>'
        f' / 퇴원 <b style="color:#475569;">{_disc}명</b></span>'
        f'<span style="margin-left:auto;font-size:10px;color:#94A3B8;">{time.strftime("%H:%M")} 기준</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 빠른 질문 버튼 (대화 없을 때만 표시) ─────────────────────────
    if not _history:
        _quick_qs = [
            ("🔴 위험 병동 현황", "현재 가동률 90% 이상인 위험 병동이 있나요? 해당 병동 조치 방안을 알려주세요."),
            ("📊 오늘 입퇴원 분석", "금일 입원과 퇴원 현황을 분석하고 전일 대비 변화를 설명해주세요."),
            ("🏥 병상 부족 예측", "현재 데이터 기준으로 내일 병상 부족 위험이 있는 병동을 예측해주세요."),
            ("🔪 수술 부담 현황", "수술 건수가 많은 병동의 현황과 관리 포인트를 알려주세요."),
            ("📋 전체 운영 요약", "오늘 병동 전체 운영 현황을 3줄로 요약해주세요."),
        ]
        st.markdown(
            '<div style="margin-bottom:10px;">' 
            '<div style="font-size:11px;color:#94A3B8;font-weight:600;margin-bottom:6px;'
            'text-transform:uppercase;letter-spacing:.06em;">빠른 질문</div>',
            unsafe_allow_html=True,
        )
        _qcols = st.columns(len(_quick_qs), gap="small")
        for _qi, (_ql, _qv) in enumerate(_quick_qs):
            with _qcols[_qi]:
                if st.button(
                    _ql, key=f"quick_q_{_qi}",
                    use_container_width=True, type="secondary",
                ):
                    st.session_state["ward_chat_quick_input"] = _qv
        st.markdown('</div>', unsafe_allow_html=True)

    # ── 대화 이력 표시 ────────────────────────────────────────────────
    for _msg in _history:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])

    # ── 빠른 질문 버튼 클릭 처리 ─────────────────────────────────────
    _quick_pending = st.session_state.pop("ward_chat_quick_input", None)

    # ── 입력창 ────────────────────────────────────────────────────────
    _user_input = st.chat_input(
        "병동 현황에 대해 질문하세요  예) 위험 병동은? / 퇴원 지연 진료과는?",
        key="ward_chat_input",
    ) or _quick_pending

    if _user_input:
        # PII 마스킹
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
            st.warning("⚠️ 개인식별 정보가 감지되어 마스킹 처리되었습니다.", icon="🔒")
            _user_input = _safe_input

        with st.chat_message("user"):
            st.markdown(_user_input)
        _history.append({"role": "user", "content": _user_input})

        with st.chat_message("assistant"):
            _ph   = st.empty()
            _full = ""
            try:
                from core.llm import get_llm_client
                _llm    = get_llm_client()
                _req_id = str(uuid.uuid4())[:8]
                for _tok in _llm.generate_stream(_user_input, _system_prompt, request_id=_req_id):
                    _full += _tok
                    _ph.markdown(_full + "▌")
            except Exception as _e:
                _full = (
                    f"**LLM 연결 실패**\n\n"
                    f"오류: `{_e}`\n\n"
                    f"현재 데이터 요약:\n"
                    f"- 가동률: **{_occ:.1f}%** ({'🔴 위험' if _occ>=90 else '🟡 주의' if _occ>=80 else '🟢 정상'})\n"
                    f"- 재원: **{_stay}명** / {_beds}병상\n"
                    f"- 금일 입원: **{_adm}명** / 퇴원: **{_disc}명**"
                )
                logger.warning(f"[Ward Chat LLM] {_e}")
            _ph.markdown(_full)

        _history.append({"role": "assistant", "content": _full})
        st.session_state["ward_chat_history"] = _history
        st.rerun()


# ── 원무 대시보드 ────────────────────────────────────────────────────

def _render_finance() -> None:
    kpi      = (_query_cached("finance_kpi") or [{}])[0]
    overdue  = _query_cached("finance_overdue")
    by_ins   = _query_cached("finance_by_insurance")
    outpat   = int(kpi.get("외래수납", 0) or 0)
    inpat    = int(kpi.get("입원수납", 0) or 0)
    total_s  = int(kpi.get("총수납", 0) or 0)
    total_od = sum(int(r.get("미수금액", 0) or 0) for r in overdue)
    c1, c2, c3, c4 = st.columns(4)
    _kpi_card("외래 수납", f"{outpat / 1_000_000:.1f}", "백만", "목표 65M 대비 달성률", C["blue"], c1)
    _kpi_card("입원 수납", f"{inpat / 1_000_000:.1f}", "백만", "전일 대비 변동", C["green"], c2)
    _kpi_card("미수금 잔액", f"{total_od / 1_000_000:.1f}", "백만", "30일+ 집중 관리 필요", C["coral"], c3)
    _kpi_card("총 수납", f"{total_s / 1_000_000:.1f}", "백만", "외래+입원 합계", C["sky"], c4)
    col_ins, col_od = st.columns([1, 2])
    with col_ins:
        _section_title("보험 유형별 수납")
        if by_ins and HAS_PLOTLY:
            INS_LABEL = {"C1": "건강보험", "MD": "의료급여", "CA": "자동차보험", "WC": "산재보험", "GN": "일반"}
            labels = [INS_LABEL.get(r["급종코드"], r["급종코드"]) for r in by_ins]
            values = [int(r.get("수납금액", 0) or 0) for r in by_ins]
            colors = [C["blue"], C["green"], C["amber"], C["coral"], "#666"]
            fig = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.65,
                marker=dict(colors=colors[:len(labels)], line=dict(width=0)),
                textinfo="label+percent", textfont=dict(size=10, color="rgba(255,255,255,0.8)"),
            ))
            fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key="finance_pie")
    with col_od:
        _section_title("미수금 현황")
        for r in overdue:
            amt  = int(r.get("미수금액", 0) or 0)
            days = int(r.get("최장경과일", 0) or 0)
            st_text = "위험" if days >= 30 else ("주의" if days >= 14 else "정상")
            sc  = C["coral"] if st_text == "위험" else C["amber"] if st_text == "주의" else C["green"]
            sbg = C["coral_bg"] if st_text == "위험" else C["amber_bg"] if st_text == "주의" else C["green_bg"]
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:6px 0;border-bottom:1px solid {C["border"]};font-size:12px;">'
                f'<span style="color:{C["t2"]};min-width:70px;">{r.get("진료과", "")}</span>'
                f'<span style="color:{C["t1"]};font-family:Consolas,monospace;">{amt:,}원</span>'
                f'<span style="color:#64748B;font-family:Consolas,monospace;">{days}일</span>'
                f'<span style="background:{sbg};color:{sc};padding:2px 8px;border-radius:3px;font-weight:600;font-size:11px;">{st_text}</span></div>',
                unsafe_allow_html=True,
            )


# ── 외래 대시보드 ────────────────────────────────────────────────────

def _render_opd() -> None:
    kpi     = (_query_cached("opd_kpi") or [{}])[0]
    by_dept = _query_cached("opd_by_dept")
    hourly  = _query_cached("opd_hourly")
    noshow  = (_query_cached("opd_noshow") or [{}])[0]
    total    = int(kpi.get("총내원", 0) or 0)
    new_rate = float(kpi.get("초진율", 0) or 0)
    ns_rate  = float(noshow.get("노쇼율", 0) or 0)
    c1, c2, c3, c4 = st.columns(4)
    _kpi_card("금일 외래", str(total), "명", "전일 대비 변동", C["blue"], c1)
    _kpi_card("예약 이행률", f"{100 - ns_rate:.1f}", "%", f"No-show {ns_rate}% (목표 ≤10%)", C["coral"] if ns_rate > 10 else C["green"], c2)
    _kpi_card("초진 비율", f"{new_rate}", "%", f"재진 {100 - new_rate:.1f}%", C["green"], c3)
    _kpi_card("평균 대기", "22", "분", "목표 20분 기준", C["amber"], c4)
    col_h, col_top = st.columns([6, 4])
    with col_h:
        _section_title("시간대별 내원 패턴")
        if hourly and HAS_PLOTLY:
            labels = [r["시간대"] for r in hourly if int(r.get("내원수", 0) or 0) > 0]
            values = [int(r.get("내원수", 0) or 0) for r in hourly if int(r.get("내원수", 0) or 0) > 0]
            colors = ["rgba(255,123,123,0.8)" if v >= 200 else "rgba(91,156,246,0.8)" if v >= 150 else "rgba(91,156,246,0.4)" for v in values]
            fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors, marker=dict(line=dict(width=0))))
            fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=C["t2"], size=10), xaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10)), yaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10)), showlegend=False)
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
    병원 현황판 메인 렌더러 v4.2

    [v4.2 신규]
    - 사이드바 차트 초기화 버튼 추가 (HAS_CHART_MODULES=True 일 때)

    [v4.1 개선]
    - Oracle ping: 세션당 1회 (이전: 렌더마다 2회)
    - 새로고침: oracle_ok 삭제 + st.cache_data.clear()
    """
    # ── Oracle ping — 세션당 1회 ─────────────────────────────────────
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

    _ts       = time.strftime("%Y-%m-%d %H:%M")
    _tab_names = {"ward": "병동 대시보드", "finance": "원무 대시보드", "opd": "외래 대시보드"}
    _tab_name  = _tab_names.get(tab, "병동 대시보드")
    _ss_key    = f"dash_last_refresh_{tab}"
    if _ss_key not in st.session_state:
        st.session_state[_ss_key] = _ts

    # ── 병동 목록 선제 로드 ──────────────────────────────────────────
    if tab == "ward" and "ward_name_list" not in st.session_state:
        try:
            _pre_bed   = _query_cached("ward_bed_detail")
            _pre_wards = ["전체"] + sorted({r.get("병동명", "") for r in _pre_bed if r.get("병동명", "") and r.get("병동명", "") != "전체"})
            st.session_state["ward_name_list"] = _pre_wards
        except Exception:
            st.session_state["ward_name_list"] = ["전체"]

    _o_color = "#16A34A" if oracle_ok else "#F59E0B"
    _o_label = "Oracle 연결 정상" if oracle_ok else "데모 데이터"

    # ── 탑바 ─────────────────────────────────────────────────────────
    st.markdown('<div class="wd-topbar-accent"></div>', unsafe_allow_html=True)
    _c_title, _c_btns, _c_info = st.columns([4, 3, 3], vertical_alignment="center")

    with _c_title:
        _tt_col, _wd_col = st.columns([3, 2], vertical_alignment="center")
        with _tt_col:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
                f'<div style="width:3px;height:22px;background:#1E40AF;border-radius:2px;flex-shrink:0;"></div>'
                f"<div>"
                f'<div style="font-size:9px;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.15em;line-height:1;margin-bottom:2px;">좋은문화병원</div>'
                f'<div style="font-size:17px;font-weight:800;color:#0F172A;letter-spacing:-0.03em;line-height:1.1;">{_tab_name}</div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )
        with _wd_col:
            if tab == "ward":
                _wsel_col, _rmbtn_col = st.columns([3, 2], gap="small", vertical_alignment="center")
                with _wsel_col:
                    _ward_name_list = st.session_state.get("ward_name_list", ["전체"])
                    _cur_ward       = st.session_state.get("ward_selected", "전체")
                    _sel = st.selectbox(
                        "병동 선택", options=_ward_name_list,
                        index=_ward_name_list.index(_cur_ward) if _cur_ward in _ward_name_list else 0,
                        key="global_ward_selector", label_visibility="collapsed",
                        help="선택한 병동의 데이터만 모든 차트에 반영됩니다",
                    )
                    if _sel != st.session_state.get("ward_selected"):
                        st.session_state["ward_selected"] = _sel
                        st.rerun()
                with _rmbtn_col:
                    _rm_panel_open = st.session_state.get("show_room_panel", False)
                    if st.button("▲ 접기" if _rm_panel_open else "🏥 병실현황", key="btn_room_panel", type="secondary", use_container_width=True, help="선택 병동의 병실별 상세 현황"):
                        st.session_state["show_room_panel"] = not _rm_panel_open
                        st.rerun()

    with _c_btns:
        _b1, _b2, _b3 = st.columns(3, gap="small")
        with _b1:
            if st.button("🔄 새로고침", key=f"dash_refresh_{tab}", use_container_width=True, type="secondary", help="최신 데이터 재조회 (Oracle)"):
                st.session_state.pop("oracle_ok", None)
                st.cache_data.clear()
                st.session_state[_ss_key] = time.strftime("%Y-%m-%d %H:%M")
                st.rerun()
        with _b2:
            if tab == "ward":
                pass  # 익일 예약 상세는 하단 고정 표시
        with _b3:
            if st.button("💬 채팅초기화", key=f"ward_chat_clear_hdr_{tab}", use_container_width=True, type="secondary", help="AI 채팅 대화 기록 초기화"):
                st.session_state["ward_chat_history"] = []
                st.rerun()

    with _c_info:
        _h_prev  = st.session_state.get("ward_chat_history", [])
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
                f'<div style="font-size:10px;color:#94A3B8;max-width:300px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🤖 {_preview}</div>'
                if _preview else
                f'<div style="font-size:10px;color:#CBD5E1;letter-spacing:0.02em;">🤖 AI 분석 채팅 — 하단에서 질문하세요</div>'
            )
            + f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:1px;background:#F1F5F9;margin:0 0 8px;"></div>', unsafe_allow_html=True)

    if tab == "ward":
        _render_ward()
    elif tab == "finance":
        _render_finance()
    else:
        _render_opd()