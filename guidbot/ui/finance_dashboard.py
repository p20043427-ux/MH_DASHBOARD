"""
ui/finance_dashboard.py  ─  원무 현황 대시보드 v2.4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[6탭 구조]
  탭1 실시간 현황   — KPI / 일일현황 / 진료과 대기 / 키오스크 / 세부과집계표
  탭2 주간추이분석  — 7일간 추이 라인 / 외래 히트맵 / 입원 히트맵 / 진료과별 재원일수
  탭3 월간추이분석  — 2개월 비교 (방문자/신환/구환/신환비율/신환증감)
  탭4 지역별 통계   — 구군별 유입 현황 / 월별 추이 지도
  탭5 진료과 분석   — 진료과 선택 → 단일월 스냅샷 / 비교월 분석
  탭6 카드 매칭     — 카드사 xlsx ↔ 병원 Oracle 이중 매칭

[사용 Oracle VIEW — v2.4 최종]
  실시간: V_OPD_KPI / V_OPD_DEPT_STATUS / V_KIOSK_STATUS
          V_DISCHARGE_PIPELINE / V_WARD_BED_DETAIL / V_WARD_ROOM_DETAIL
          V_KIOSK_BY_DEPT / V_KIOSK_COUNTER_TREND
          V_DAILY_DEPT_STAT / V_DAY_INWEON_3
  수납:   V_FINANCE_TODAY / V_FINANCE_TREND / V_FINANCE_BY_DEPT / V_OVERDUE_STAT
  주간:   V_OPD_DEPT_TREND / V_IPD_DEPT_TREND(신규) / V_LOS_DIST_DEPT(신규)
  월간:   V_MONTHLY_OPD_DEPT
  지역:   V_REGION_DEPT_MONTHLY / V_REGION_DEPT_DAILY
  진료과: V_REGION_DEPT_MONTHLY / V_MONTHLY_OPD_DEPT
          V_DEPT_GENDER_MONTHLY(신규) / V_DEPT_AGE_MONTHLY(신규)
          V_DEPT_CATEGORY_AGE(신규)
  카드:   V_KIOSK_CARD_APPROVAL

[삭제된 VIEW]
  V_WAITTIME_TREND (대기시간 추세 탭 삭제)
  V_LOS_DIST       (진료과별 분포 V_LOS_DIST_DEPT 로 대체)
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
import streamlit as st
import json as _json_r
import uuid as _uuid_r

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

import sys, os as _os
_PR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _PR not in sys.path:
    sys.path.insert(0, _PR)

try:
    from utils.logger import get_logger as _gl
    from config.settings import settings as _s
    logger = _gl(__name__, log_dir=_s.log_dir)
except Exception:
    import logging as _l
    logger = _l.getLogger(__name__)
    if not logger.handlers:
        _fh = _l.StreamHandler()
        _fh.setFormatter(_l.Formatter(
            "[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(_fh)
        logger.setLevel(_l.DEBUG)

# ════════════════════════════════════════════════════════════════════
# 디자인 토큰 — ui/design.py 단일 소스 (2026-04-22 Phase 1 리팩토링)
#   · 기존 로컬 C 딕셔너리·_CSS·헬퍼 함수를 모두 제거하고
#     ui/design.py 의 단일 소스에서 임포트한다.
#   · 기존 호출부(_kpi_card, _sec_hd 등)는 하위 호환 별칭으로 유지.
# ════════════════════════════════════════════════════════════════════
from ui.design import (          # noqa: E402
    C,               # 색상 팔레트 — 프로젝트 전체 단일 소스
    APP_CSS,         # 마스터 CSS — fn-kpi / wd-card / badge 등 공통 클래스
    PLOTLY_PALETTE,  # Plotly 색상 시퀀스
    PLOTLY_CFG,      # Plotly 공통 레이아웃 설정
    kpi_card,        # KPI 카드 컴포넌트
    section_header,  # 섹션 헤더 (wd-sec 스타일)
    gap,             # 빈 세로 여백
    fmt_won,         # 금액 → 억/만 단위 포맷
    empty_state,     # 데이터 없음 플레이스홀더
)

# ════════════════════════════════════════════════════════════════════
# Oracle 쿼리 딕셔너리 / 공유 유틸리티 — panels/_shared.py 에서 임포트
# (2026-04-22 Phase 2 리팩토링)
#   · FQ / FQ_HIST / _fq() 를 panels/_shared.py 로 이전
#   · 이 파일은 역임포트로 하위 호환 유지
#   · 보안 원칙: VIEW 경유만 허용 / 집계값만 노출 / 카드 매칭 제외
# ════════════════════════════════════════════════════════════════════
from ui.panels._shared import (          # noqa: E402
    FQ, FQ_HIST, _fq,                   # 쿼리 딕셔너리 + Oracle 조회 래퍼
    _TODAY_STR, _dt_import,             # 날짜 유틸리티
)
try:
    from ui.panels.dept_analysis import render_dept_analysis as _render_dept_analysis
    _HAS_DEPT_ANALYSIS = True
except Exception as _e:
    _HAS_DEPT_ANALYSIS = False
    logger.warning(f"dept_analysis 로드 실패 (탭 비활성화): {_e}")
# ════════════════════════════════════════════════════════════════════
# [2026-04-22 Phase 1 리팩토링] 하위 호환 별칭
# ────────────────────────────────────────────────────────────────────
# 기존 로컬 정의(C 딕셔너리·_CSS·_kpi_card 등)를 모두 제거하고
# design.py 단일 소스로 통합. 파일 내 100+ 호출부는 아래 별칭을
# 통해 변경 없이 동작. Phase 2 에서 별칭을 제거하고 직접 호출 예정.
# ════════════════════════════════════════════════════════════════════
_kpi_card      = kpi_card        # 24곳 호출 — design.kpi_card 로 위임
_sec_hd        = section_header  # 26곳 호출 — design.section_header 로 위임
_gap           = gap             # 42곳 호출 — design.gap 로 위임
_fmt_won       = fmt_won         # 8곳 호출  — design.fmt_won 로 위임
_plotly_empty  = empty_state     # 9곳 호출  — design.empty_state 로 위임
_PALETTE       = PLOTLY_PALETTE  # 7곳 호출  — design.PLOTLY_PALETTE 로 위임
_PLOTLY_LAYOUT = PLOTLY_CFG      # 17곳 호출 — design.PLOTLY_CFG 로 위임



# ================================================================
# [v2.6 P2] Tab renderers moved to ui/finance/ package
# Each tab_*.py is 200-600 LOC. This file is now a thin router.
# ================================================================
from ui.finance import (         # noqa: E402
    _tab_realtime,
    _render_day_inweon,
    _render_finance_llm_chat,    # defined; not currently called
    _tab_revenue,                # defined; not currently wired
    _tab_analytics,
    _tab_monthly,
    _tab_region,
    _tab_card_match,
)


# ================================================================
# Main entry point
# ================================================================
def render_finance_dashboard() -> None:
    '''원무 현황 대시보드 v2.6 -- 6탭 구조 + 탭별 Lazy Loading.

    [v2.6] P2: tab renderers in ui/finance/tab_*.py
    [v2.5] Lazy loading: 1 query on first render, each tab loads its own data.
    '''
    st.markdown(APP_CSS, unsafe_allow_html=True)

    logger.info('render_finance_dashboard v2.6 start')
    oracle_ok = False
    try:
        from db.oracle_client import test_connection
        oracle_ok, _ = test_connection()
        if not oracle_ok:
            logger.warning('Oracle: connection failed -- demo mode')
    except Exception as _e:
        logger.warning(f'Oracle check exception: {_e}')

    import datetime as _dt_main
    _is_custom = st.session_state.get('fn_use_custom_date', False)
    if _is_custom:
        _sel_d = st.session_state.get('fn_sel_date', _dt_main.date.today())
        _qdate = (_sel_d.strftime('%Y%m%d')
                  if isinstance(_sel_d, _dt_main.date)
                  else str(_sel_d).replace('-', '')[:8])
    else:
        _qdate = ''
    _q = _qdate if _is_custom else ''

    # Minimum data for topbar (1 Oracle query on every rerun)
    opd_kpi = (_fq('opd_kpi') or [{}])[0]

    # Topbar
    st.markdown('<div class="fn-topbar"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([4, 3, 5], vertical_alignment='center')
    with c1:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
            f'<div style="width:3px;height:22px;background:{C["blue"]};border-radius:2px;"></div>'
            f'<div>'
            f'<div style="font-size:9px;font-weight:700;color:{C["t4"]};text-transform:uppercase;letter-spacing:.15em;">좋은문화병원</div>'
            f'<div style="font-size:17px;font-weight:800;color:{C["t1"]};letter-spacing:-.03em;">💼 원무 현황</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        b1, b2 = st.columns(2, gap='small')
        with b1:
            if st.button('🔄 새로고침', key='fn_refresh',
                         use_container_width=True, type='secondary'):
                st.cache_data.clear(); st.rerun()
        with b2:
            st.markdown(
                f'<a href="{_s.dashboard_url}" target="_blank" style="'
                'display:block;text-align:center;background:#EFF6FF;color:#1E40AF;'
                'border:1.5px solid #BFDBFE;border-radius:20px;padding:5px 0;'
                'font-size:11.5px;font-weight:600;text-decoration:none;">🔗 병동 대시보드</a>',
                unsafe_allow_html=True,
            )
    with c3:
        _dc1, _dc2 = st.columns([2, 3], gap='small')
        with _dc1:
            _oc = C['green'] if oracle_ok else C['yellow']
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:5px;padding:6px 0;">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{_oc};'
                f'flex-shrink:0;display:inline-block;"></span>'
                f'<span style="font-size:11px;font-weight:700;color:{_oc};white-space:nowrap;">'
                f'{"Oracle 연결" if oracle_ok else "Oracle 미연결"}</span></div>',
                unsafe_allow_html=True,
            )
        with _dc2:
            st.toggle('📅 날짜 지정',
                      value=st.session_state.get('fn_use_custom_date', False),
                      key='fn_use_custom_date')
            if st.session_state.get('fn_use_custom_date', False):
                st.date_input(
                    '', key='fn_sel_date', label_visibility='collapsed',
                    value=st.session_state.get('fn_sel_date', _dt_main.date.today()),
                    format='YYYY-MM-DD', max_value=_dt_main.date.today(),
                )
                _shown = st.session_state.get('fn_sel_date', _dt_main.date.today())
                st.markdown(
                    f'<div style="font-size:10px;color:{C["indigo"]};font-weight:700;text-align:right;">📅 {_shown} 기준</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="font-size:11px;color:{C["t3"]};font-family:Consolas,monospace;padding:2px 0;text-align:right;">{time.strftime("%Y-%m-%d %H:%M")}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown('<div style="height:1px;background:#F1F5F9;margin:0 0 6px;"></div>',
                unsafe_allow_html=True)

    if not oracle_ok:
        _ms = [
            'V_OPD_DEPT_STATUS', 'V_KIOSK_STATUS', 'V_DISCHARGE_PIPELINE',
            'V_FINANCE_TODAY', 'V_FINANCE_TREND', 'V_FINANCE_BY_DEPT', 'V_OVERDUE_STAT',
            'V_IPD_DEPT_TREND', 'V_LOS_DIST_DEPT', 'V_MONTHLY_OPD_DEPT',
            'V_REGION_DEPT_DAILY', 'V_REGION_DEPT_MONTHLY',
            'V_DEPT_GENDER_MONTHLY', 'V_DEPT_AGE_MONTHLY', 'V_DEPT_CATEGORY_AGE',
        ]
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:8px 14px;margin-bottom:8px;">'
            f'<b style="font-size:13px;color:#92400E;">⚠️ Oracle 미연결 -- VIEW 생성 필요</b>'
            f'<div style="font-size:11px;color:#B45309;margin-top:3px;">{" / ".join(_ms)}</div></div>',
            unsafe_allow_html=True,
        )

    # 6 tabs -- per-tab lazy loading
    t1, t_weekly, t_monthly, t_region, t_dept, t_card = st.tabs([
        '🏥 실시간 현황',
        '📈 주간추이분석',
        '📅 월간추이분석',
        '📍 지역별 통계',
        '🔬 진료과 분석',
        '💳 카드 매칭',
    ])

    with t1:
        dept_status         = _fq('opd_dept_status')
        kiosk_status        = _fq('kiosk_status')
        kiosk_by_dept       = _fq('kiosk_by_dept',       _q)
        kiosk_counter_trend = _fq('kiosk_counter_trend', _q)
        discharge_pipe      = _fq('discharge_pipeline',  _q)
        bed_detail          = _fq('ward_bed_detail',      _q)
        ward_room_detail    = _fq('ward_room_detail')
        daily_dept_stat     = _fq('daily_dept_stat',     _q)
        day_inweon          = _fq('day_inweon',           _q)
        opd_dept_trend      = _fq('opd_dept_trend',      _q)
        _tab_realtime(
            opd_kpi, dept_status, kiosk_status, discharge_pipe, bed_detail,
            kiosk_by_dept=kiosk_by_dept,
            kiosk_counter_trend=kiosk_counter_trend,
            ward_room_detail=ward_room_detail,
            opd_dept_trend=opd_dept_trend,
            daily_dept_stat=daily_dept_stat,
        )
        _gap()
        _render_day_inweon(day_inweon)

    with t_weekly:
        opd_dept_trend_w  = _fq('opd_dept_trend',  _q)
        ipd_dept_trend    = _fq('ipd_dept_trend',  _q)
        los_dist_dept     = _fq('los_dist_dept')
        daily_dept_stat_w = _fq('daily_dept_stat', _q)
        _tab_analytics(
            opd_dept_trend=opd_dept_trend_w,
            los_dist_dept=los_dist_dept,
            daily_dept_stat=daily_dept_stat_w,
            ipd_dept_trend=ipd_dept_trend,
        )

    with t_monthly:
        monthly_opd_dept = _fq('monthly_opd_dept')
        _tab_monthly(monthly_opd_dept, [])

    with t_region:
        _tab_region([], [])

    with t_dept:
        if _HAS_DEPT_ANALYSIS:
            monthly_opd_dept_d = _fq('monthly_opd_dept')
            _render_dept_analysis(monthly_opd_dept_d)
        else:
            _gap(16)
            st.markdown(
                f'<div style="background:#FFF7ED;border:1px solid #FED7AA;'
                f'border-radius:10px;padding:16px 20px;text-align:center;">'
                f'<div style="font-size:15px;font-weight:700;color:#C2410C;">🛠 진료과 분석 모듈 로드 실패</div>'
                f'<div style="font-size:12px;color:#9A3412;margin-top:6px;">ui/panels/dept_analysis.py 를 확인하세요.</div></div>',
                unsafe_allow_html=True,
            )

    with t_card:
        _tab_card_match()

    # Auto-refresh
    if st.session_state.get('fn_auto', False):
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=300_000, key='fn_autorefresh')
        except ImportError:
            st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)
