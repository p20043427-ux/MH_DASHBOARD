"""
ui/hospital_dashboard.py  ─  병동 대시보드 렌더러 (UI 전담)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[계층 구조 — v4.0 리팩토링 이후]
  · DB 접근 / Circuit Breaker / TTL 캐시 → db/ward_repository.py
  · 비즈니스 로직 / 필터 헬퍼            → services/ward_service.py
  · UI 컴포넌트 / 스타일 / 색상          → ui/design.py
  · 차트 렌더러                           → ui/chart_renderers.py
  · 이 파일 (hospital_dashboard.py)       → 화면 렌더링만 담당

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

import os as _os
import sys

_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 병동 대시보드 사용자 로그 + 모니터링
try:
    from utils.dashboard_monitor import get_dash_monitor as _get_dash_monitor
    _DASH_MON = _get_dash_monitor()
except Exception:
    class _NullMon:
        def log_action(self, *a, **k): pass
        def log_llm_query(self, *a, **k): pass
        def log_query_fail(self, *a, **k): pass
        def log_query_time(self, *a, **k): pass
    _DASH_MON = _NullMon()

try:
    from utils.logger import get_logger as _get_logger
    from config.settings import settings as _settings
    logger = _get_logger(__name__, log_dir=_settings.log_dir)
except Exception:
    import logging as _logging
    logger = _logging.getLogger(__name__)
    if not logger.handlers:
        _fh = _logging.StreamHandler()
        _fh.setFormatter(_logging.Formatter(
            "[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(_fh)
        logger.setLevel(_logging.DEBUG)

from db.ward_repository import _qc
from services.ward_service import (
    _norm_sex, _safe_int, _safe_float,
    _filter_by_ward, _filter_dx_ward, _trend_dedup,
)
from ui.design import (
    C,
    APP_CSS as _WARD_CSS,
    ward_kpi_card as _kpi_card,
    ward_section_title as _section_title,
    PLOTLY_CFG as _PLOTLY_BASE,
    PLOTLY_PALETTE as _PALETTE,
    WARD_AX as _AX,
    ward_layout as _layout,
)
from ui.chart_selector import (
    get_chart_type as _get_chart_type,
    render_section_header_inline as _chart_selector,
)
from ui.chart_renderers import (
    _render_dept_chart,
    _render_trend_chart,
    _render_ward_alt_chart,
    _render_dx7_chart,
    _render_dx_compare_chart,
)




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [v2.2] 섹션별 대안 차트 렌더러 (인라인)
#
# - "table" 타입은 각 섹션의 기존 HTML 코드 블록이 그대로 처리
# - 나머지 타입만 아래 함수가 처리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    dept_stay    = _qc("ward_dept_stay")
    bed_detail   = _qc("ward_bed_detail")
    op_stat      = _qc("ward_op_stat")
    trend        = _qc("ward_kpi_trend")
    dx_today     = _qc("ward_dx_today")
    dx_trend     = _qc("ward_dx_trend")
    yesterday    = _qc("ward_yesterday")
    admit_cands  = _qc("admit_candidates")
    # ── V_WARD_ROOM_DETAIL: 병실현황 + 병상 수배 모두 이 VIEW 사용 ─────
    # - 성별/나이/진료과 등 환자 정보 포함
    # - 병실현황 패널, 병상 수배 성별 필터 모두 이 데이터로 처리
    # - 조건부 로드: 패널 열림 또는 병상 수배 검색 시
    _show_room_panel = st.session_state.get("show_room_panel", False)
    _need_room_detail = _show_room_panel or st.session_state.get("asgn_result_ready", False)
    ward_room_detail = _qc("ward_room_detail") if _need_room_detail else []
    bed_room_stat: List[Dict] = ward_room_detail  # 동일 데이터 — 기존 참조 호환용 alias

    _adm_total = len(admit_cands)
    _adm_done  = sum(1 for r in admit_cands if r.get("수속상태", "") == "AD")

    _all_wards = ["전체"] + sorted({
        r.get("병동명", "") for r in bed_detail
        if r.get("병동명", "") and r.get("병동명", "") != "전체"
    })
    st.session_state["ward_name_list"] = _all_wards
    _g_ward = st.session_state.get("ward_selected", "전체")

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
    total_bed  = sum(_safe_int(r.get("총병상"))   for r in bed_detail_f)
    admit_cnt  = sum(_safe_int(r.get("금일입원"))  for r in bed_detail_f)
    occupied   = sum(_safe_int(r.get("재원수"))    for r in bed_detail_f)
    disc_cnt   = sum(_safe_int(r.get("금일퇴원"))  for r in bed_detail_f)
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
    _pa = sum(_safe_int(r.get("금일입원"))  for r in _yest_f)
    _pd = sum(_safe_int(r.get("금일퇴원"))  for r in _yest_f)
    _ps = sum(_safe_int(r.get("재원수"))    for r in _yest_f)
    _po = round(_ps / max(total_bed, 1) * 100, 1)
    if not _yest_f:
        _pa, _pd, _ps, _po = admit_cnt, disc_cnt, occupied, occ_rate

    # ── 익일 예약 ─────────────────────────────────────────────────────
    _first_bed  = bed_detail[0] if bed_detail else {}
    _next_op    = int(_first_bed.get("익일수술예약", 0) or 0)
    _next_adm   = int(_first_bed.get("익일입원예약", 0) or 0)
    _next_disc  = int(_first_bed.get("익일퇴원예약", 0) or 0)

    _total_rest    = sum(max(0, _safe_int(r.get("총병상")) - _safe_int(r.get("재원수"))) for r in bed_detail_f)
    _total_ndc_pre = sum(_safe_int(r.get("익일퇴원예고")) for r in bed_detail_f)

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
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 병상 수배 조건 설정 (v2.5)
            # 기본: 직접 입력 / 예약자 불러오기는 expander로 보조
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            # ── 병동 선택 ─────────────────────────────────────
            _asgn_wards = ["전체"] + sorted({r.get("병동명", "") for r in ward_room_detail if r.get("병동명", "")})
            _asgn_ward_sel = st.selectbox(
                "병동",
                _asgn_wards,
                index=_asgn_wards.index(_rp_ward) if _rp_ward in _asgn_wards else 0,
                key="asgn_ward_sel",
            )

            # ── 인실 선택 ─────────────────────────────────────
            _asgn_room_sel = st.selectbox(
                "인실",
                ["전체", "1인실", "2인실", "3인실", "4인실"],
                key="asgn_room_sel",
            )

            # ── 성별 ──────────────────────────────────────────
            _asgn_sex_sel = st.radio(
                "성별", ["전체", "남", "여"],
                horizontal=True, key="asgn_sex_sel",
            )

            # ── 진료과 (영문코드 드롭다운) ─────────────────────
            _all_dept_codes = sorted({
                (r.get("진료과", "") or "").strip()
                for r in ward_room_detail
                if r.get("진료과", "") and r.get("상태") in ("재원", "퇴원예정")
            })
            _dept_opts_base = ["전체"] + [d for d in _all_dept_codes if d]
            _is_1insl = (_asgn_room_sel == "1인실")
            if _is_1insl:
                st.markdown(
                    '<div style="font-size:10.5px;color:#059669;background:#DCFCE7;'
                    'border-radius:5px;padding:4px 8px;margin-bottom:4px;">'
                    '✅ 1인실은 진료과 무관 배정 가능</div>',
                    unsafe_allow_html=True,
                )
                _asgn_dept_sel = "전체"
            else:
                _asgn_dept_sel = st.selectbox(
                    "진료과",
                    _dept_opts_base,
                    key="asgn_dept_sel",
                    help="재원 환자 기준 영문코드 (예: IM=내과, GS=외과, OS=정형외과)",
                )

            # ── 예약 환자에서 불러오기 (선택사항) ─────────────
            # expander로 접어두어 필수값처럼 보이지 않게 함
            _pt_badge_html = ""
            if admit_cands:
                with st.expander(f"📋 예약 환자 불러오기 ({len(admit_cands)}명)", expanded=False):
                    _pt_opts = ["— 선택 안 함 —"] + [
                        (
                            f"{r.get('진료과명','?')}"
                            f" | {'남' if r.get('성별','M')=='M' else '여'}"
                            f" | {r.get('나이','?')}세"
                        )
                        for r in admit_cands
                    ]
                    _pt_sel = st.selectbox(
                        "환자",
                        _pt_opts,
                        key="asgn_pt_sel",
                        label_visibility="collapsed",
                    )
                    if _pt_sel != "— 선택 안 함 —":
                        _pt_idx   = _pt_opts.index(_pt_sel) - 1
                        _pt_r     = admit_cands[_pt_idx]
                        _raw_dept = (_pt_r.get("진료과코드", "") or _pt_r.get("진료과명", "")).strip().upper()
                        _asgn_sex_sel  = "남" if _pt_r.get("성별", "M") == "M" else "여"
                        _asgn_dept_sel = _raw_dept if _raw_dept else "전체"
                        _age_v    = int(_pt_r.get("나이", 0) or 0)
                        _sx_icon  = "🔵" if _asgn_sex_sel == "남" else "🔴"
                        _pt_badge_html = (
                            f'<div style="margin:4px 0;padding:6px 10px;background:#EFF6FF;'
                            f'border:1px solid #BFDBFE;border-radius:6px;font-size:11.5px;'
                            f'line-height:1.7;color:#1E40AF;">'
                            f'📋 <b>{_pt_r.get("진료과명", _raw_dept)}</b>'
                            f' {_sx_icon} {_asgn_sex_sel}성 {_age_v}세 → 조건 자동 적용'
                            f'</div>'
                        )
                        st.markdown(_pt_badge_html, unsafe_allow_html=True)

            # ── 검색 버튼 ─────────────────────────────────
            if st.button("🔍 가용 병상 검색", key="asgn_search_btn", use_container_width=True, type="primary"):
                st.session_state.update({
                    "asgn_result_ready": True,
                    "asgn_dept_saved":   _asgn_dept_sel,
                    "asgn_sex_saved":    _asgn_sex_sel,
                    "asgn_room_saved":   _asgn_room_sel,
                    "asgn_ward_saved":   _asgn_ward_sel,
                })
            st.markdown("</div>", unsafe_allow_html=True)

            if st.session_state.get("asgn_result_ready"):
                # 검색 버튼 클릭 시 저장된 값 사용 (rerun 후에도 유지)
                _sw  = st.session_state.get("asgn_ward_saved", "전체")
                _sri = st.session_state.get("asgn_room_saved", "전체")
                _sdp = ("전체" if st.session_state.get("asgn_room_saved") == "1인실"
                        else st.session_state.get("asgn_dept_saved", "전체"))
                _ssx = st.session_state.get("asgn_sex_saved", "전체")

                # ── 1단계: 빈병상 + 병동/인실 기본 필터 ────────────────
                _candidates_raw = [
                    r for r in ward_room_detail
                    if r.get("상태") == "빈병상"
                    and (_sw == "전체" or r.get("병동명", "") == _sw)
                    and (_sri == "전체" or r.get("인실구분", "") == _sri)
                ]

                # ── 2단계: 성별 필터 ─────────────────────────────────────
                # 빈병상 자체에는 환자 없음 → 같은 병실 재원 환자 성별로 판단
                # 1인실은 성별 무관 (독립 병실), 2인실 이상만 적용
                # 판단: 병실번호 앞 4자리(=병실) 기준으로 반대 성별 재원 시 제외
                # 같은 병실에 아무도 없으면 → 성별 무관 허용
                if _ssx != "전체" and _sri != "1인실":
                    # _norm_sex() 모듈 레벨 함수 사용 (_SEX_NORM dict lookup O(1))
                    _opp_code = "F" if _ssx == "남" else "M"
                    _my_code  = "M" if _ssx == "남" else "F"   # 내 성별 코드

                    # 성별 필터 소스: V_WARD_ROOM_DETAIL (성별 컬럼 포함)
                    # ward_room_detail은 _need_room_detail=True 일 때 전체 병동 로드됨
                    # 검색 대상 병동(_sw)의 재원 환자만 추출
                    if _sw != "전체":
                        _sex_data_src = [
                            r for r in ward_room_detail
                            if r.get("병동명", "") == _sw
                        ]
                    else:
                        _sex_data_src = ward_room_detail

                    # 단일 순회로 blocked_rooms + same_sex_rooms 동시 수집 (O(n) → O(n/2))
                    _blocked_rooms: set[str] = set()
                    _same_sex_rooms: set[str] = set()
                    for _r in _sex_data_src:
                        if _r.get("상태") not in ("재원", "퇴원예정"):
                            continue
                        _rkey = str(_r.get("병실번호", "")).zfill(6)[:4]
                        _rsx  = _norm_sex(_r.get("성별", ""))
                        if _rsx == _opp_code:
                            _blocked_rooms.add(_rkey)
                        elif _rsx == _my_code:
                            _same_sex_rooms.add(_rkey)

                    _candidates_sex = [
                        r for r in _candidates_raw
                        if str(r.get("병실번호", "")).zfill(6)[:4] not in _blocked_rooms
                    ]
                    _candidates_sex = sorted(
                        _candidates_sex,
                        key=lambda r: (0 if str(r.get("병실번호","")).zfill(6)[:4] in _same_sex_rooms else 1,
                                       r.get("병실번호","")),
                    )
                    # 성별 필터 결과 확정 — 폴백 제거
                    # 기존: _candidates_sex가 [] (falsy)이면 _candidates_raw로 폴백
                    # → 모든 후보가 차단됐을 때 필터가 완전히 무시되는 버그
                    # 수정: 결과가 0개면 그대로 0개 유지 → '조건 맞는 병상 없음' 표시
                    _candidates_raw = _candidates_sex
                else:
                    pass  # 전체 또는 1인실: 성별 필터 없음

                # ── 3단계: 진료과 매칭 정렬 ──────────────────────────────
                # 1인실은 진료과 무관이므로 _sdp=="전체"로 바이패스됨
                if _sdp and _sdp != "전체":
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
                    _candidates = sorted(_candidates_raw, key=lambda r: r.get("병실번호", ""))
                st.markdown(
                    f'<div style="margin-top:8px;padding:10px;background:#FFFFFF;'
                    f'border:1px solid #E2E8F0;border-radius:8px;">'
                    f'<div style="font-size:11px;font-weight:700;color:#64748B;margin-bottom:6px;">가용 병상 {len(_candidates)}개</div>',
                    unsafe_allow_html=True,
                )
                if _candidates:
                    # list → join 방식: str += O(n²) 방지
                    _res_parts: list = []
                    for _cr in _candidates[:15]:
                        _cbno  = str(_cr.get("병실번호", "")).zfill(6)
                        _croom = _cbno[2:4]
                        _cbed  = _cbno[4:6]
                        _cward = _cr.get("병동명", "")
                        _cinsl = _cr.get("인실구분", "")
                        _cfee  = _cr.get("병실료", 0) or 0
                        _cfee_s = f"{int(_cfee):,}원" if _cfee else "─"
                        _res_parts.append(
                            f'<div style="display:flex;align-items:center;justify-content:space-between;'
                            f'padding:6px 8px;border-bottom:1px solid #F1F5F9;">'
                            f'<div><span style="font-size:13px;font-weight:700;color:#1E40AF;">{_cward}</span>'
                            f'<span style="font-size:12px;color:#64748B;margin-left:6px;">병실 {_croom} · 베드 {_cbed}</span>'
                            f'</div>'
                            f'<div style="display:flex;align-items:center;gap:6px;">'
                            f'<span style="font-size:11px;color:#475569;">{_cinsl}</span>'
                            f'<span style="font-size:11px;color:#94A3B8;">{_cfee_s}</span>'
                            f'<span style="background:#DCFCE7;color:#16A34A;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;">빈병상</span>'
                            f"</div></div>"
                        )
                    st.markdown("".join(_res_parts) + "</div>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div style="padding:16px;text-align:center;color:#94A3B8;font-size:12px;">'
                        "조건에 맞는 빈 병상이 없습니다</div></div>",
                        unsafe_allow_html=True,
                    )

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # ── Row 1: KPI 2행×3열 | 주간 추이 ─────────────────────────
    st.markdown('<div class="wd-row-kpi">', unsafe_allow_html=True)
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
            _kpi_card("금일 입원", str(admit_cnt), "명", f"전일 {_pa}명", C["blue"], delta=_ds(admit_cnt, _pa))

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

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
                f'<span style="font-size:28px;font-weight:800;color:{C["blue"]};font-variant-numeric:tabular-nums;line-height:1;">{_next_adm}</span>'
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

        # ── KPI 하단: 빠른질문 버튼 + AI 채팅 ──────────────────────
        # KPI 카드를 보고 판단한 뒤 바로 클릭 → 주간추이와 높이 자동 정렬
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # 빠른질문 버튼 5개 — 얇은 구분선 + 라벨
        st.markdown(
            '<div style="border-top:1px solid #E2E8F0;padding-top:8px;margin-bottom:6px;">'
            '<span style="font-size:10px;font-weight:700;color:#94A3B8;'
            'text-transform:uppercase;letter-spacing:.08em;">빠른 분석</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        _quick_qs2 = [
            ("익일 가용",     "익일 입원 예약 대비 가용 병상 현황을 분석하고, 부족 위험이 있는 병동을 알려주세요."),
            ("입퇴원 분석",   "금일 입원과 퇴원 현황을 분석하고 전일 대비 변화를 설명해주세요."),
            ("입원 상병 추세","최근 7일 주요 입원 상병 추세를 분석하고 특이사항을 알려주세요."),
            ("재원환자 분석", "병동별 재원 환자 현황을 분석하고 장기 재원 위험 병동을 알려주세요."),
            ("운영 요약",     "오늘 병동 전체 운영 현황을 3줄로 요약해주세요."),
        ]
        _qb_cols = st.columns(len(_quick_qs2), gap="small")
        for _qi2, (_ql2, _qv2) in enumerate(_quick_qs2):
            with _qb_cols[_qi2]:
                if st.button(
                    _ql2, key=f"qs_kpi_{_qi2}",
                    use_container_width=True, type="secondary",
                    help=_qv2[:40] + "...",
                ):
                    _DASH_MON.log_action("quick_btn", label=_ql2)
                    st.session_state["ward_chat_quick_input"] = _qv2
                    st.rerun()

        # AI 채팅 — KPI 컬럼 내 하단에 배치 (높이 자동 확장)
        st.markdown(
            '<div style="margin-top:8px;border:1px solid #E2E8F0;border-radius:10px;'
            'padding:12px 14px;background:#FAFBFC;flex:1;">',
            unsafe_allow_html=True,
        )
        _render_ward_llm_chat(
            kpi=_kpi_for_llm, bed_occ=[],
            bed_detail=bed_detail_f, op_stat=op_stat_f,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # [v2.2] 주간 추이 7일 — 차트 선택기 통합
    # 기본: 테이블 (기존 HTML 표) / 라인 / 영역 / 막대 선택 가능
    # ════════════════════════════════════════════════════════════
    with _col_trend:
        _oc_c_trend = "#EF4444" if occ_rate >= 90 else "#F59E0B" if occ_rate >= 80 else "#16A34A"

        st.markdown('<div class="wd-card" style="padding:14px 16px;">', unsafe_allow_html=True)

        # ── [v2.2] 섹션 헤더 + pill 선택기 ────────────────────────────
        chart_type_trend = _chart_selector("weekly_trend", "주간 추이 7일", _g_ward)

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
    st.markdown('</div>', unsafe_allow_html=True)  # /wd-row-kpi
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── Row 3: 병동별 당일 현황 + 진료과 재원 ───────────────────
    st.markdown('<div class="wd-row-chart">', unsafe_allow_html=True)
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
                    rate  = _safe_float(r.get("가동률"))
                    adm   = _safe_int(r.get("금일입원"))
                    stay  = _safe_int(r.get("재원수"))
                    disc  = _safe_int(r.get("금일퇴원"))
                    tot   = _safe_int(r.get("총병상"))
                    rest  = max(0, tot - stay)
                    n_disc  = _safe_int(r.get("익일퇴원예고"))
                    n_avail = max(0, rest + n_disc)
                    r_cls = "#DC2626" if rate >= 90 else "#F59E0B" if rate >= 80 else "#059669"
                    _td = f"padding:8px 12px;background:{bg};border-bottom:1px solid #F8FAFC;vertical-align:middle;"
                    rows_html += (
                        f"<tr>"
                        f'<td style="{_td}color:#0F172A;font-weight:600;">{r.get("병동명", "")}</td>'
                        f'<td style="{_td}text-align:right;color:#64748B;font-family:Consolas,monospace;">{tot}</td>'
                        f'<td style="{_td}text-align:right;color:{C["blue"]};font-family:Consolas,monospace;font-weight:700;">{adm}</td>'
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
                _tb    = sum(_safe_int(r.get("총병상")) for r in bed_detail_f)
                _ta    = sum(_safe_int(r.get("금일입원")) for r in bed_detail_f)
                _ts    = sum(_safe_int(r.get("재원수")) for r in bed_detail_f)
                _td2   = sum(_safe_int(r.get("금일퇴원")) for r in bed_detail_f)
                _tndc  = sum(_safe_int(r.get("익일퇴원예고")) for r in bed_detail_f)
                _tr    = round(_ts / max(_tb, 1) * 100, 1)
                _sth   = "padding:8px 12px;background:#EFF6FF;border-top:2px solid #BFDBFE;vertical-align:middle;font-weight:700;"
                rows_html += (
                    f"<tr>"
                    f'<td style="{_sth}color:#1E40AF;">합계</td>'
                    f'<td style="{_sth}text-align:right;color:#1E40AF;font-family:Consolas,monospace;">{_tb}</td>'
                    f'<td style="{_sth}text-align:right;color:{C["blue"]};font-family:Consolas,monospace;">{_ta}</td>'
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
                    f'<b style="font-size:11px;color:{C["blue"]};font-family:Consolas,monospace;">{_next_adm}명</b></span>'
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
        st.markdown('<div class="wd-card" style="padding:14px 16px;">', unsafe_allow_html=True)

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
    st.markdown('</div>', unsafe_allow_html=True)  # /wd-row-chart
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    # ── Row 4: 주상병 분석 ──────────────────────────────────────
    st.markdown('<div class="wd-row-chart">', unsafe_allow_html=True)
    # [v2.2] 최근 7일 / 금일 vs 전일 — 차트 선택기 통합
    # ════════════════════════════════════════════════════════════
    from collections import defaultdict as _dd

    col_pie, col_bar = st.columns([1, 1], gap="small")

    # ── [v2.2] 최근 7일 입원 주상병 분포 ─────────────────────────────
    with col_pie:
        st.markdown('<div class="wd-card" style="padding:14px 16px;">', unsafe_allow_html=True)

        chart_type_dx7 = _chart_selector("dx_7day", "최근 7일 입원 주상병 분포")
        _render_dx7_chart(dx_trend, chart_type_dx7)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── [v2.2] 금일 vs 전일 입원 주상병 분포 ─────────────────────────
    with col_bar:
        st.markdown('<div class="wd-card" style="padding:14px 16px;">', unsafe_allow_html=True)

        chart_type_compare = _chart_selector("dx_compare", "금일 vs 전일 입원 주상병 분포")
        _render_dx_compare_chart(dx_today, chart_type_compare)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    st.markdown('</div>', unsafe_allow_html=True)  # /wd-row-chart
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    # ── Row 5: AI 분석 채팅 ─────────────────────────────────────
    # ════════════════════════════════════════════════════════════
    # ════════════════════════════════════════════════════════════
    # 익일 입원 예약 상세 (하단 고정 표시)
    # ════════════════════════════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="margin-bottom:8px;">'
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
        # plotly.graph_objects 는 최상단 go 사용
        _fig_adm = go.Figure()
        _fig_adm.add_trace(go.Bar(name="남성", x=_all_depts, y=_m_vals, marker_color="#3B82F6", text=_m_vals, textposition="outside", textfont=dict(size=11, color="#1E40AF")))
        _fig_adm.add_trace(go.Bar(name="여성", x=_all_depts, y=_f_vals, marker_color="#F472B6", text=_f_vals, textposition="outside", textfont=dict(size=11, color="#9D174D")))
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
            st.plotly_chart(_fig_adm, width="stretch", key="ward_adm_bar")
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



    # 빠른 질문: AI 채팅 헤더 파란바로 이동됨

    # ── 대화 이력 표시 (소스 카드 포함) ─────────────────────────────
    for _hi, _msg in enumerate(_history):
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])
            if _msg["role"] == "assistant" and _msg.get("sources"):
                try:
                    from ui.components import source_section_header, source_trust_card
                    from pathlib import Path as _P
                    from config.settings import settings as _cfg_h2
                    _pdf_dirs_h = [
                        _cfg_h2.local_work_dir,
                        _cfg_h2.local_work_dir.parent / "docs" / "pdf",
                        _cfg_h2.local_work_dir.parent / "docs",
                        _cfg_h2.db_docs_dir,
                    ]
                    def _find_pdf_h(fname):
                        for _dh in _pdf_dirs_h:
                            _ph = _dh / fname
                            if _ph.exists(): return _ph
                            _ph2 = _dh / _P(fname).name
                            if _ph2.exists(): return _ph2
                        return None
                    source_section_header(len(_msg["sources"]))
                    for _s in _msg["sources"]:
                        _dp_h = (_P(_s["doc_path_str"]) if _s.get("doc_path_str")
                                 and _P(_s["doc_path_str"]).exists()
                                 else _find_pdf_h(_s["source"]))
                        # 히스토리: 세션 bytes 매칭
                        _up_ch = st.session_state.get("_uploaded_pdf_bytes", {})
                        _sk_h = _P(_s["source"]).name
                        _bh = (_up_ch.get(_s["source"]) or _up_ch.get(_sk_h))
                        source_trust_card(
                            rank=_s["rank"],
                            source=_s["source"],
                            page=_s["page"],
                            score=_s["score"],
                            article=_s.get("article", ""),
                            revision_date=_s.get("revision_date", ""),
                            chunk_text=_s["chunk_text"],
                            doc_path=_dp_h,
                            card_ns=f"wh_{_hi}",
                            pdf_bytes=_bh,
                        )
                except Exception as _pdf_e:
                    logger.debug(f"[WardChat] PDF 첨부 렌더 실패 (무시): {_pdf_e}")

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
            _t_llm_start = time.time()
            _ph   = st.empty()
            # [최적화] list+join 으로 O(n²) → O(n) 스트리밍
            _toks: list = []
            _tok_cnt = 0
            _last_render = time.time()
            # 시스템 프롬프트 크기 제한 (4000자) → LLM 비용·속도 최적화
            _safe_prompt = (_system_prompt[:4000] + "...(생략)"
                            if len(_system_prompt) > 4000 else _system_prompt)
            _full = ""
            try:
                from core.llm import get_llm_client
                _llm    = get_llm_client()
                _req_id = str(uuid.uuid4())[:8]

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 1단계: 벡터DB에서 관련 문서 검색 (규정·지침 참조)
                # 2단계: 검색 결과 + 대시보드 데이터를 함께 프롬프트에 주입
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                _rag_context = ""
                _rag_sources = []
                _pr = None
                try:
                    # ── 벡터DB: 모듈 수명 캐시 (_WARD_VDB) ──────────
                    # session_state 대신 모듈 전역 → 재로드 없음, 최속
                    import sys as _sys
                    _this_mod = _sys.modules.get(__name__, _sys.modules.get('__main__'))
                    _vdb_ver = st.session_state.get("dash_vdb_version", 0)
                    _cached_ver = getattr(_this_mod, "_WARD_VDB_VER", -1)
                    _vdb = getattr(_this_mod, "_WARD_VDB", None)

                    if _vdb is None or _vdb_ver != _cached_ver:
                        from core.vector_store import VectorStoreManager
                        from config.settings import settings as _cfg_r
                        _vsm = VectorStoreManager(
                            db_path=_cfg_r.rag_db_path,
                            model_name=_cfg_r.embedding_model,
                            cache_dir=str(_cfg_r.local_cache_path),
                        )
                        _vdb = _vsm.load()
                        setattr(_this_mod, "_WARD_VDB", _vdb)
                        setattr(_this_mod, "_WARD_VDB_VER", _vdb_ver)
                        if _vdb:
                            logger.info(f"[Ward Chat] 벡터DB 로드: {_vdb.index.ntotal}벡터")

                    if _vdb:
                        # _run_fast 직접 호출: 쿼리재작성/캐시조회 오버헤드 없음
                        from core.rag_pipeline import _run_fast
                        _pr = _run_fast(_user_input, _vdb)
                        if _pr and _pr.context.strip() and "찾을 수 없" not in _pr.context:
                            _rag_context = _pr.context[:2500]
                            _rag_sources = list(dict.fromkeys(
                                rd.document.metadata.get("source", "")
                                for rd in (_pr.ranked_docs or [])[:5]
                                if rd.document.metadata.get("source")
                            ))
                except Exception as _rag_e:
                    logger.warning(f"[Ward Chat] 벡터DB 검색 실패: {_rag_e}")

                # 최종 프롬프트: 대시보드 데이터 + RAG 문서 합산
                _combined_prompt = _safe_prompt
                if _rag_context:
                    _combined_prompt += (
                        "\n\n## 관련 규정·지침 (벡터DB 검색 결과)\n"
                        "아래 내용도 참고하여 더 정확한 답변을 제공하세요.\n\n"
                        f"{_rag_context}"
                    )
                _combined_prompt = _combined_prompt[:6000]  # 전체 토큰 상한

                for _tok in _llm.generate_stream(_user_input, _combined_prompt, request_id=_req_id):
                    _toks.append(_tok)
                    _tok_cnt += 1
                    if _tok_cnt % 8 == 0 or (time.time() - _last_render) > 0.08:
                        _ph.markdown("".join(_toks) + "▌")
                        _last_render = time.time()
                _full = "".join(_toks)

                # ── 참조 규정 카드 렌더 (main.py 동일 방식) ────────
                _elapsed_ms = int((time.time() - _t_llm_start) * 1000)
                if _pr and _pr.ranked_docs:
                    try:
                        from ui.components import source_section_header, source_trust_card
                        from config.settings import settings as _cfg_s
                        from pathlib import Path as _P
                        source_section_header(len(_pr.ranked_docs))
                        # PDF 탐색 경로 목록 (우선순위 순)
                        _pdf_search_dirs = [
                            _cfg_s.local_work_dir,
                            _cfg_s.local_work_dir.parent / "docs" / "pdf",
                            _cfg_s.local_work_dir.parent / "docs",
                            _cfg_s.db_docs_dir,
                        ]
                        def _find_pdf(fname):
                            """파일명으로 PDF 탐색 — glob 퍼지 포함."""
                            _base = _P(fname).name  # 파일명만 추출
                            for _d in _pdf_search_dirs:
                                # 정확히 일치
                                _p = _d / _base
                                if _p.exists(): return _p
                                # glob으로 유사 파일명 탐색
                                import glob as _gl
                                _hits = list(_gl.glob(str(_d / f"**/{_base}"), recursive=True))
                                if _hits: return _P(_hits[0])
                                # stem(확장자 제외)으로 탐색
                                _stem = _P(fname).stem
                                _hits2 = list(_gl.glob(str(_d / f"**/{_stem}*.pdf"), recursive=True))
                                if _hits2: return _P(_hits2[0])
                            return None

                        def _get_bytes(source):
                            """세션 캐시에서 bytes 퍼지 탐색."""
                            _uc = st.session_state.get("_uploaded_pdf_bytes", {})
                            if not _uc: return None
                            # 정확히 일치
                            _bn = _P(source).name
                            if source in _uc: return _uc[source]
                            if _bn in _uc: return _uc[_bn]
                            # 퍼지: 소문자, 공백 제거 비교
                            _norm = lambda s: s.lower().replace(" ","").replace("-","").replace("_","")
                            for _k, _v in _uc.items():
                                if _norm(_P(_k).name) == _norm(_bn):
                                    return _v
                            return None

                        _up_bytes = st.session_state.get("_uploaded_pdf_bytes", {})
                        _norm_fn = lambda s: s.lower().replace(' ','').replace('-','').replace('_','')
                        for _doc in _pr.ranked_docs:
                            _dp = _find_pdf(_doc.source)
                            # 세션 bytes 퍼지 매칭
                            _dl_fname = _P(_doc.source).name
                            _sess_bytes = None
                            for _uk, _uv in _up_bytes.items():
                                if (_uk == _doc.source or
                                    _P(_uk).name == _dl_fname or
                                    _norm_fn(_P(_uk).name) == _norm_fn(_dl_fname)):
                                    _sess_bytes = _uv; break
                            # source_trust_card에 pdf_bytes 직접 전달
                            # → 카드 내부에서 통합 렌더 (중복 버튼 없음)
                            source_trust_card(
                                rank=_doc.rank,
                                source=_doc.source,
                                page=_doc.page,
                                score=_doc.score,
                                article=_doc.article,
                                revision_date=getattr(_doc, "revision_date", ""),
                                chunk_text=_doc.document.page_content,
                                doc_path=_dp,
                                card_ns=f"wc_{_req_id[:6]}",
                                pdf_bytes=_sess_bytes,  # bytes 있으면 카드 내부 버튼
                            )
                        # 응답시간 배지
                        st.markdown(
                            f'<div style="font-size:10px;color:#94A3B8;'
                            f'text-align:right;margin-top:4px;">'
                            f'⏱ {_elapsed_ms:,}ms</div>',
                            unsafe_allow_html=True,
                        )
                    except Exception as _src_e:
                        logger.debug(f"[Ward Chat] 소스 카드 렌더 실패: {_src_e}")
                        # fallback: 텍스트로 출처 표시
                        if _rag_sources:
                            st.caption("📄 참고: " + " / ".join(_rag_sources[:3]))
                elif _rag_sources:
                    st.caption("📄 참고: " + " / ".join(_rag_sources[:3]))

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

        # ranked_docs 직렬화해서 히스토리에 저장
        _src_list = []
        if _pr and _pr.ranked_docs:
            from config.settings import settings as _cfg_h
            for _d in _pr.ranked_docs:
                _cp = _cfg_h.local_work_dir / _d.source
                _src_list.append({
                    "rank":          _d.rank,
                    "source":         _d.source,
                    "page":           _d.page,
                    "score":          _d.score,
                    "article":        _d.article,
                    "revision_date":  getattr(_d, "revision_date", ""),
                    "chunk_text":     _d.document.page_content,
                    "doc_path_str":   str(_cp) if _cp.exists() else None,
                })
        _history.append({"role": "assistant", "content": _full, "sources": _src_list})
        st.session_state["ward_chat_history"] = _history
        _llm_elapsed = int((time.time() - _t_llm_start) * 1000) if "_t_llm_start" in dir() else 0
        _DASH_MON.log_llm_query(
            question=_user_input,
            elapsed_ms=_llm_elapsed,
            success=("LLM 연결 실패" not in _full),
        )
        st.rerun()


# ── 원무 대시보드 ────────────────────────────────────────────────────

def _render_finance() -> None:
    kpi      = (_qc("finance_kpi") or [{}])[0]
    overdue  = _qc("finance_overdue")
    by_ins   = _qc("finance_by_insurance")
    outpat   = int(kpi.get("외래수납", 0) or 0)
    inpat    = int(kpi.get("입원수납", 0) or 0)
    total_s  = int(kpi.get("총수납", 0) or 0)
    total_od = sum(_safe_int(r.get("미수금액")) for r in overdue)
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
            values = [_safe_int(r.get("수납금액")) for r in by_ins]
            colors = [C["blue"], C["green"], C["amber"], C["coral"], "#666"]
            fig = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.65,
                marker=dict(colors=colors[:len(labels)], line=dict(width=0)),
                textinfo="label+percent", textfont=dict(size=10, color="rgba(255,255,255,0.8)"),
            ))
            fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
            st.plotly_chart(fig, width="stretch", key="finance_pie")
    with col_od:
        _section_title("미수금 현황")
        for r in overdue:
            amt  = _safe_int(r.get("미수금액"))
            days = _safe_int(r.get("최장경과일"))
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
    kpi     = (_qc("opd_kpi") or [{}])[0]
    by_dept = _qc("opd_by_dept")
    hourly  = _qc("opd_hourly")
    noshow  = (_qc("opd_noshow") or [{}])[0]
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
            labels = [r["시간대"] for r in hourly if _safe_int(r.get("내원수")) > 0]
            values = [_safe_int(r.get("내원수")) for r in hourly if _safe_int(r.get("내원수")) > 0]
            colors = ["rgba(255,123,123,0.8)" if v >= 200 else "rgba(91,156,246,0.8)" if v >= 150 else "rgba(91,156,246,0.4)" for v in values]
            fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors, marker=dict(line=dict(width=0))))
            fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=C["t2"], size=10), xaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10)), yaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10)), showlegend=False)
            st.plotly_chart(fig, width="stretch", key="opd_hourly_chart")
    with col_top:
        _section_title("진료과별 환자수 TOP 5")
        top5_colors = [C["blue"], C["green"], C["amber"], C["coral"], C["sky"]]
        max_cnt = max((_safe_int(r.get("환자수")) for r in by_dept[:5]), default=1)
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
    # ── Oracle 연결 체크 — 5분 캐시 + 실패 시 1분 재체크 ──────────────
    # 이전: 세션당 1회 → 연결 복구 후에도 False 고정
    # 개선: 성공 시 5분, 실패 시 1분 후 자동 재체크
    _oracle_check_key  = "oracle_ok"
    _oracle_expire_key = "oracle_ok_expire"
    _now_ts = time.time()
    _oracle_expired = _now_ts > st.session_state.get(_oracle_expire_key, 0)

    oracle_ok = False
    if _oracle_check_key not in st.session_state or _oracle_expired:
        try:
            from db.oracle_client import test_connection
            oracle_ok, _ = test_connection()
            # 성공: 5분 후 재체크 / 실패: 60초 후 재체크
            _expire = _now_ts + (300 if oracle_ok else 60)
        except Exception as _oc_e:
            oracle_ok = False
            _expire = _now_ts + 60
            logger.warning(f"Oracle 연결 확인 예외: {_oc_e}")
        st.session_state[_oracle_check_key]  = oracle_ok
        st.session_state[_oracle_expire_key] = _expire
    else:
        oracle_ok = st.session_state[_oracle_check_key]

    _ts       = time.strftime("%Y-%m-%d %H:%M")
    _tab_names = {"ward": "병동 대시보드", "finance": "원무 대시보드", "opd": "외래 대시보드"}
    _tab_name  = _tab_names.get(tab, "병동 대시보드")
    _ss_key    = f"dash_last_refresh_{tab}"
    if _ss_key not in st.session_state:
        st.session_state[_ss_key] = _ts

    # ── 병동 목록 선제 로드 ──────────────────────────────────────────
    if tab == "ward" and "ward_name_list" not in st.session_state:
        try:
            _pre_bed   = _qc("ward_bed_detail")
            _pre_wards = ["전체"] + sorted({r.get("병동명", "") for r in _pre_bed if r.get("병동명", "") and r.get("병동명", "") != "전체"})
            st.session_state["ward_name_list"] = _pre_wards
        except Exception as _wl_e:
            logger.warning(f"병동 목록 선제 로드 실패: {_wl_e}")
            st.session_state["ward_name_list"] = ["전체"]

    _o_label = "Oracle 연결 정상" if oracle_ok else "데모 데이터"

    # ── 탑바: ① 3px 그라데이션 바
    st.markdown('<div class="fn-topbar"></div>', unsafe_allow_html=True)

    # ── 탑바: ② 헤더 행 (제목 | 병동선택 | 버튼들 | 상태)
    _c_title_h, _c_ward_sel, _c_btns_bar, _c_status_h = st.columns(
        [4, 3, 3, 2], vertical_alignment="center", gap="small"
    )
    with _c_title_h:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
            f'<div style="width:3px;height:22px;background:{C["blue"]};border-radius:2px;"></div>'
            f'<div>'
            f'<div style="font-size:9px;font-weight:700;color:{C["t4"]};'
            f'text-transform:uppercase;letter-spacing:.15em;">좋은문화병원</div>'
            f'<div style="font-size:17px;font-weight:800;color:{C["t1"]};'
            f'letter-spacing:-0.03em;">{_tab_name}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with _c_ward_sel:
        if tab == "ward":
            _ward_name_list = st.session_state.get("ward_name_list", ["전체"])
            _cur_ward       = st.session_state.get("ward_selected", "전체")
            _sel = st.selectbox(
                "병동", options=_ward_name_list,
                index=_ward_name_list.index(_cur_ward) if _cur_ward in _ward_name_list else 0,
                key="global_ward_selector", label_visibility="collapsed",
                help="선택한 병동의 데이터만 모든 차트에 반영됩니다",
            )
            if _sel != st.session_state.get("ward_selected"):
                _DASH_MON.log_action("ward_filter", label=_sel)
                st.session_state["ward_selected"] = _sel
                st.rerun()
    with _c_btns_bar:
        _bx1, _bx2 = st.columns(2, gap="small")
        with _bx1:
            _rm_panel_open = st.session_state.get("show_room_panel", False)
            if st.button(
                "🏠 병실현황" if not _rm_panel_open else "▲ 닫기",
                key="btn_room_panel", type="secondary", use_container_width=True,
            ):
                st.session_state["show_room_panel"] = not _rm_panel_open
                st.rerun()
        with _bx2:
            if st.button("🔄 새로고침", key=f"dash_refresh_{tab}",
                         type="secondary", use_container_width=True):
                _DASH_MON.log_action("refresh", label=tab)
                st.session_state.pop("oracle_ok", None)
                st.session_state.pop("oracle_ok_expire", None)
                for _k in list(st.session_state.keys()):
                    if _k.startswith("_ttl_jitter_"):
                        del st.session_state[_k]
                st.cache_data.clear()
                st.session_state[_ss_key] = time.strftime("%Y-%m-%d %H:%M")
                st.rerun()
    with _c_status_h:
        _o_c = C["green"] if oracle_ok else C["yellow"]
        st.markdown(
            f'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;padding:6px 0;">'
            f'<div style="display:flex;align-items:center;gap:5px;">'
            f'<span style="width:7px;height:7px;border-radius:50%;background:{_o_c};display:inline-block;"></span>'
            f'<span style="font-size:11px;font-weight:700;color:{_o_c};">{_o_label}</span>'
            f'</div>'
            f'<span style="font-size:10px;color:{C["t4"]};font-family:Consolas,monospace;">'
            f'{st.session_state[_ss_key]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

    if tab == "ward":
        _render_ward()
    elif tab == "finance":
        _render_finance()
    else:
        _render_opd()