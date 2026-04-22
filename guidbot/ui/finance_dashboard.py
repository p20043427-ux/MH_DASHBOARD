"""
ui/finance_dashboard.py  ─  원무 현황 대시보드 v2.3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[4탭 구조]
  탭1 실시간 현황   — KPI / 일일현황 / 진료과 대기 / 키오스크 / 세부과집계표
  탭2 주간추이분석  — 7일간 추이 라인 / 외래 히트맵 / 입원 히트맵 / 진료과별 재원일수
  탭3 월간추이분석  — 2개월 비교 (방문자/신환/구환/신환비율/신환증감)
  탭4 카드 매칭     — 카드사 xlsx ↔ 병원 Oracle 이중 매칭

[사용 Oracle VIEW — v2.3 최종]
  실시간: V_OPD_KPI / V_OPD_DEPT_STATUS / V_KIOSK_STATUS
          V_DISCHARGE_PIPELINE / V_WARD_BED_DETAIL / V_WARD_ROOM_DETAIL
          V_KIOSK_BY_DEPT / V_KIOSK_COUNTER_TREND
          V_DAILY_DEPT_STAT / V_DAY_INWEON_3
  수납:   V_FINANCE_TODAY / V_FINANCE_TREND / V_FINANCE_BY_DEPT / V_OVERDUE_STAT
  주간:   V_OPD_DEPT_TREND / V_IPD_DEPT_TREND(신규) / V_LOS_DIST_DEPT(신규)
  월간:   V_MONTHLY_OPD_DEPT(신규)
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
# Oracle 쿼리 딕셔너리 — v2.3
# [보안 원칙]
#   · VIEW 경유만 허용 (RAG_READONLY 원본 테이블 접근 금지)
#   · 각 VIEW는 집계/통계 컬럼만 노출 (환자명·주민번호·전화번호 제외)
#   · LLM 컨텍스트: 집계값만 전달, 카드 매칭 데이터 제외
# ════════════════════════════════════════════════════════════════════
FQ: Dict[str, str] = {
    # ── 실시간 현황 ────────────────────────────────────────────────
    "opd_kpi":            "SELECT * FROM JAIN_WM.V_OPD_KPI WHERE ROWNUM = 1",
    "opd_dept_status":    "SELECT * FROM JAIN_WM.V_OPD_DEPT_STATUS ORDER BY 대기 DESC",
    "kiosk_status":       "SELECT * FROM JAIN_WM.V_KIOSK_STATUS ORDER BY 키오스크ID",
    "kiosk_by_dept":      "SELECT * FROM JAIN_WM.V_KIOSK_BY_DEPT ORDER BY 수납건수 DESC",
    "kiosk_counter_trend":"SELECT * FROM JAIN_WM.V_KIOSK_COUNTER_TREND ORDER BY 기준일",
    "ward_room_detail":   "SELECT * FROM JAIN_WM.V_WARD_ROOM_DETAIL ORDER BY 병동명, 병실번호",
    "daily_dept_stat":    "SELECT * FROM JAIN_WM.V_DAILY_DEPT_STAT ORDER BY 진료과명, 구분",
    "day_inweon": """
        SELECT 진료과, 외래계, 입원계, 퇴원계, 재원계,
               "예방(독감)", "예방(AZ,JS,NV)", "예방(MD)", "예방(FZ)", 예방주사계
        FROM (
            SELECT 일자, 진료과, 외래계, 입원계, 퇴원계, 재원계,
                   "예방(독감)", "예방(AZ,JS,NV)", "예방(MD)", "예방(FZ)", 예방주사계
            FROM JAIN_WM.V_DAY_INWEON_3
            UNION ALL
            SELECT 일자, '총합계',SUM(외래계),SUM(입원계),SUM(퇴원계),SUM(재원계),
                   SUM("예방(독감)"),SUM("예방(AZ,JS,NV)"),SUM("예방(MD)"),SUM("예방(FZ)"),SUM(예방주사계)
            FROM JAIN_WM.V_DAY_INWEON_3 GROUP BY 일자
        )
        WHERE 일자 = TO_CHAR(SYSDATE, 'YYYYMMDD')
        ORDER BY
            CASE WHEN 진료과 = '총합계' THEN 19 ELSE 10 END,
            CASE
                WHEN TRIM(진료과)='*내분비내과' THEN 1 WHEN TRIM(진료과)='*호흡기내과' THEN 2
                WHEN TRIM(진료과)='*소화기내과' THEN 3 WHEN TRIM(진료과)='*신장내과' THEN 4
                WHEN TRIM(진료과)='*순환기내과' THEN 5 WHEN TRIM(진료과)='인공신장실' THEN 6
                WHEN TRIM(진료과)='신경과' THEN 7   WHEN TRIM(진료과)='가정의학과' THEN 8
                WHEN TRIM(진료과)='신경외과' THEN 9  WHEN TRIM(진료과)='*유방센터' THEN 10
                WHEN TRIM(진료과)='*위장관센터' THEN 11 WHEN TRIM(진료과)='*갑상선센터' THEN 12
                WHEN TRIM(진료과)='성형외과' THEN 13 WHEN TRIM(진료과)='정형외과' THEN 14
                WHEN TRIM(진료과)='*OBGY' THEN 15  WHEN TRIM(진료과)='*난임센터' THEN 16
                WHEN TRIM(진료과)='소아청소년과' THEN 17 WHEN TRIM(진료과)='이비인후과' THEN 18
                WHEN TRIM(진료과)='피부과' THEN 19 WHEN TRIM(진료과)='응급의학과' THEN 20
                WHEN TRIM(진료과)='외부의뢰' THEN 21 WHEN TRIM(진료과)='진단검사' THEN 22
                ELSE 23
            END ASC,
            REPLACE(진료과,'*'),
            CASE WHEN SUBSTR(진료과,1,1)='*' THEN 2 ELSE 1 END
    """,
    "discharge_pipeline": "SELECT * FROM JAIN_WM.V_DISCHARGE_PIPELINE ORDER BY 단계, 병동명",
    "ward_bed_detail":    "SELECT * FROM JAIN_WM.V_WARD_BED_DETAIL ORDER BY 병동명",

    # ── 수납·미수금 ────────────────────────────────────────────────
    "finance_today":   "SELECT * FROM JAIN_WM.V_FINANCE_TODAY ORDER BY 금액 DESC",
    "finance_trend":   "SELECT * FROM JAIN_WM.V_FINANCE_TREND ORDER BY 기준일",
    "finance_by_dept": "SELECT * FROM JAIN_WM.V_FINANCE_BY_DEPT ORDER BY 수납금액 DESC",
    "overdue_stat":    "SELECT * FROM JAIN_WM.V_OVERDUE_STAT ORDER BY 연령구분",

    # ── 주간추이분석 ────────────────────────────────────────────────
    # V_OPD_DEPT_TREND: 진료과별 7일 외래 인원 (기준일 / 진료과명 / 외래환자수)
    "opd_dept_trend":  "SELECT * FROM JAIN_WM.V_OPD_DEPT_TREND ORDER BY 기준일, 외래환자수 DESC",
    # V_IPD_DEPT_TREND: 진료과별 7일 입원 인원 (신규 — DDL: monthly_views_new.sql)
    "ipd_dept_trend":  "SELECT * FROM JAIN_WM.V_IPD_DEPT_TREND ORDER BY 기준일, 입원환자수 DESC",
    # V_LOS_DIST_DEPT: 진료과별 재원일수 분포 (신규 — DDL: monthly_views_new.sql)
    "los_dist_dept":   "SELECT * FROM JAIN_WM.V_LOS_DIST_DEPT ORDER BY 진료과명, 구간순서",

    # ── 월간추이분석 ────────────────────────────────────────────────
    # V_MONTHLY_OPD_DEPT: 진료과별 월별 외래 인원 현황 (신규 — DDL: monthly_views_new.sql)
    # 컬럼: 기준년월(YYYYMM) / 진료과명 / 방문자수 / 신환자수 / 구환자수 / 외래전체 / 기타건수
    "monthly_opd_dept": (
        "SELECT * FROM JAIN_WM.V_MONTHLY_OPD_DEPT "
        "ORDER BY 기준년월 DESC, 진료과명"
    ),
    # ── 지역별 환자 통계 ────────────────────────────────────────────
    # V_REGION_DEPT_DAILY   : 일별 트렌드/히트맵용 (30일 고정)
    # V_REGION_DEPT_MONTHLY : 월별 비교 분석용 (최근 12개월, 컬럼: 기준월 YYYYMM)
    # [보안] 지역(시구 수준)만 노출 — 상세주소/우편번호 미노출
    "region_dept_daily": (
        "SELECT 기준일자, 진료과명, 지역, 환자수 "
        "FROM JAIN_WM.V_REGION_DEPT_DAILY "
        "ORDER BY 기준일자 DESC, 진료과명, 환자수 DESC"
    ),
    "region_dept_monthly": (
        "SELECT 기준월, 진료과명, 지역, 환자수 "
        "FROM JAIN_WM.V_REGION_DEPT_MONTHLY "
        "ORDER BY 기준월 DESC, 진료과명, 환자수 DESC"
    ),
}

# ── 기간 VIEW 쿼리 (과거 날짜 조회) ─────────────────────────────────
FQ_HIST: Dict[str, str] = {
    "day_inweon": """
        SELECT 진료과, 외래계, 입원계, 퇴원계, 재원계,
               "예방(독감)", "예방(AZ,JS,NV)", "예방(MD)", "예방(FZ)", 예방주사계
        FROM (
            SELECT 일자, 진료과, 외래계, 입원계, 퇴원계, 재원계,
                   "예방(독감)", "예방(AZ,JS,NV)", "예방(MD)", "예방(FZ)", 예방주사계
            FROM JAIN_WM.V_DAY_INWEON_3
            UNION ALL
            SELECT 일자, '총합계',SUM(외래계),SUM(입원계),SUM(퇴원계),SUM(재원계),
                   SUM("예방(독감)"),SUM("예방(AZ,JS,NV)"),SUM("예방(MD)"),SUM("예방(FZ)"),SUM(예방주사계)
            FROM JAIN_WM.V_DAY_INWEON_3 GROUP BY 일자
        )
        WHERE 일자 = '{d}'
        ORDER BY
            CASE WHEN 진료과 = '총합계' THEN 19 ELSE 10 END,
            CASE
                WHEN TRIM(진료과)='*내분비내과' THEN 1 WHEN TRIM(진료과)='*호흡기내과' THEN 2
                WHEN TRIM(진료과)='*소화기내과' THEN 3 WHEN TRIM(진료과)='*신장내과' THEN 4
                WHEN TRIM(진료과)='*순환기내과' THEN 5 WHEN TRIM(진료과)='인공신장실' THEN 6
                WHEN TRIM(진료과)='신경과' THEN 7   WHEN TRIM(진료과)='가정의학과' THEN 8
                WHEN TRIM(진료과)='신경외과' THEN 9  WHEN TRIM(진료과)='*유방센터' THEN 10
                WHEN TRIM(진료과)='*위장관센터' THEN 11 WHEN TRIM(진료과)='*갑상선센터' THEN 12
                WHEN TRIM(진료과)='성형외과' THEN 13 WHEN TRIM(진료과)='정형외과' THEN 14
                WHEN TRIM(진료과)='*OBGY' THEN 15  WHEN TRIM(진료과)='*난임센터' THEN 16
                WHEN TRIM(진료과)='소아청소년과' THEN 17 WHEN TRIM(진료과)='이비인후과' THEN 18
                WHEN TRIM(진료과)='피부과' THEN 19 WHEN TRIM(진료과)='응급의학과' THEN 20
                WHEN TRIM(진료과)='외부의뢰' THEN 21 WHEN TRIM(진료과)='진단검사' THEN 22
                ELSE 23
            END ASC,
            REPLACE(진료과,'*'),
            CASE WHEN SUBSTR(진료과,1,1)='*' THEN 2 ELSE 1 END
    """,
    "daily_dept_stat": (
        "SELECT * FROM JAIN_WM.V_DAILY_DEPT_STAT_HIST "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' "
        "ORDER BY 진료과명, 구분"
    ),
    "ward_bed_detail": (
        "SELECT * FROM JAIN_WM.V_WARD_BED_HIST "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' "
        "ORDER BY 병동명"
    ),
    "opd_dept_trend": (
        "SELECT * FROM JAIN_WM.V_OPD_DEPT_TREND "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "                  AND TO_DATE('{d}','YYYYMMDD') "
        "ORDER BY 기준일, 외래환자수 DESC"
    ),
    "ipd_dept_trend": (
        "SELECT * FROM JAIN_WM.V_IPD_DEPT_TREND_HIST "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "                  AND TO_DATE('{d}','YYYYMMDD') "
        "ORDER BY 기준일, 입원환자수 DESC"
    ),
    "kiosk_counter_trend": (
        "SELECT * FROM JAIN_WM.V_KIOSK_COUNTER_TREND "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "                  AND TO_DATE('{d}','YYYYMMDD') "
        "ORDER BY 기준일"
    ),
    "finance_trend": (
        "SELECT * FROM JAIN_WM.V_FINANCE_TREND "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' "
        "ORDER BY 기준일"
    ),
    # V_REGION_DEPT_MONTHLY: 월별 집계 뷰 — DBA가 region_views_monthly.sql 실행 후 활성화
    # "region_dept_monthly": (
    #     "SELECT 기준년월, 진료과명, 지역, 환자수 "
    #     "FROM JAIN_WM.V_REGION_DEPT_MONTHLY "
    #     "ORDER BY 기준년월 DESC, 진료과명, 환자수 DESC"
    # ),
}

import datetime as _dt_import
_TODAY_STR: str = _dt_import.date.today().strftime("%Y%m%d")


def _fq(key: str, date_str: str = "", max_rows: int = 5000) -> List[Dict[str, Any]]:
    """FQ / FQ_HIST 에서 쿼리 선택 후 Oracle 조회 (v2.1)."""
    import re as _re2
    try:
        from db.oracle_client import execute_query
        _is_past = bool(date_str and len(date_str) == 8 and date_str != _TODAY_STR)
        if _is_past:
            if key in FQ_HIST:
                _d      = date_str
                _d_prev = (_dt_import.datetime.strptime(date_str, "%Y%m%d")
                           - _dt_import.timedelta(days=1)).strftime("%Y%m%d")
                _d_next = (_dt_import.datetime.strptime(date_str, "%Y%m%d")
                           + _dt_import.timedelta(days=1)).strftime("%Y%m%d")
                _sql = FQ_HIST[key].format(d=_d, d_prev=_d_prev, d_next=_d_next)
            else:
                logger.warning(f"[Finance] '{key}' FQ_HIST 미등록 → 오늘 데이터로 대체.")
                _sql = FQ[key]
        else:
            _sql = FQ[key]
            if date_str and len(date_str) == 8:
                _d      = date_str
                _d_prev = (_dt_import.datetime.strptime(date_str, "%Y%m%d")
                           - _dt_import.timedelta(days=1)).strftime("%Y%m%d")
                _d_next = (_dt_import.datetime.strptime(date_str, "%Y%m%d")
                           + _dt_import.timedelta(days=1)).strftime("%Y%m%d")
                _sql = _re2.sub(r"TO_CHAR\(SYSDATE-1,\s*'YYYYMMDD'\)", f"'{_d_prev}'", _sql)
                _sql = _re2.sub(r"TO_CHAR\(SYSDATE,\s*'YYYYMMDD'\)",   f"'{_d}'",      _sql)
                _sql = _re2.sub(r"TO_CHAR\(SYSDATE\s*\+\s*1,\s*'YYYYMMDD'\)", f"'{_d_next}'", _sql)
                _sql = _re2.sub(r"(?<!')SYSDATE(?!\s*[+-]|\s*,)",
                                f"TO_DATE('{_d}','YYYYMMDD')", _sql)
        return execute_query(_sql, max_rows=max_rows) or []
    except Exception as e:
        logger.warning(f"[Finance] {key}: {e}")
        return []


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


# ════════════════════════════════════════════════════════════════════
# 탭 1 — 실시간 현황  (기존 코드 그대로 유지)
# ════════════════════════════════════════════════════════════════════
def _tab_realtime(opd_kpi, dept_status, kiosk_status, discharge_pipe, bed_detail,
                  kiosk_by_dept=None, kiosk_counter_trend=None, ward_room_detail=None,
                  opd_dept_trend=None, daily_dept_stat=None):
    opd_dept_trend      = opd_dept_trend   or []
    daily_dept_stat     = daily_dept_stat  or []
    kiosk_by_dept       = kiosk_by_dept       or []
    kiosk_counter_trend = kiosk_counter_trend or []
    ward_room_detail    = ward_room_detail    or []

    def _ds_sum(cat):
        return sum(int(r.get("건수", 0) or 0) for r in daily_dept_stat if r.get("구분") == cat)

    _opd_total = _ds_sum("외래") or (
        sum(int(r.get("대기",0) or 0)+int(r.get("진료중",0) or 0)+int(r.get("완료",0) or 0)
            for r in dept_status))
    _adm  = _ds_sum("입원") or sum(int(r.get("금일입원",0) or 0) for r in bed_detail)
    _disc = _ds_sum("퇴원") or sum(int(r.get("금일퇴원",0) or 0) for r in bed_detail)
    _stay = _ds_sum("재원") or sum(int(r.get("재원수",   0) or 0) for r in bed_detail)
    _opd_wait = sum(int(r.get("대기",0) or 0)   for r in dept_status)
    _opd_proc = sum(int(r.get("진료중",0) or 0) for r in dept_status)
    _opd_done = sum(int(r.get("완료",0) or 0)   for r in dept_status)

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid {C["blue"]};">'
        f'<div class="fn-kpi-icon">👥</div>'
        f'<div class="fn-kpi-label">금일 외래</div>'
        f'<div class="fn-kpi-value" style="color:{C["blue"]};">{_opd_total:,}'
        f'<span class="fn-kpi-unit">명</span></div>'
        f'<div style="display:flex;gap:4px;margin-top:6px;flex-wrap:wrap;">'
        f'<span style="background:{C["yellow"]}22;color:{C["yellow"]};border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;">대기 {_opd_wait}</span>'
        f'<span style="background:{C["blue"]}22;color:{C["blue"]};border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;">보류 {_opd_proc}</span>'
        f'<span style="background:{C["green"]}22;color:{C["green"]};border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;">완료 {_opd_done}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    _kpi_card(k2, "🏥", "금일 입원",  f"{_adm:,}",  "명", "입원 처리 완료",   C["indigo"])
    _kpi_card(k3, "📤", "금일 퇴원",  f"{_disc:,}", "명", "퇴원 처리 완료",   C["t2"])
    _kpi_card(k4, "🛏️", "현재 재원",  f"{_stay:,}", "명",
              f"총병상 {sum(int(r.get('총병상',0) or 0) for r in bed_detail)}개 기준", C["violet"])
    _gap()

    if bed_detail:
        _total_bed = sum(int(r.get("총병상",0) or 0) for r in bed_detail)
        _occ_rate  = round(_stay / max(_total_bed,1)*100, 1)
        _ndc_pre   = sum(int(r.get("익일퇴원예약",0) or 0) for r in bed_detail)
        _rest      = max(0, _total_bed - _stay)
        _oc        = "#DC2626" if _occ_rate >= 90 else "#F59E0B" if _occ_rate >= 80 else "#059669"
        _ward_kpi  = [
            ("가동률",      f"{_occ_rate:.1f}", _oc,       "%",  "🏥"),
            ("총병상",      str(_total_bed),    "#64748B", "개", "🛏️"),
            ("잔여병상",    str(_rest),         "#059669", "개", "✅"),
            ("익일퇴원예정",str(_ndc_pre),      "#7C3AED", "명", "📤"),
        ]
        _wk_cols = st.columns(len(_ward_kpi), gap="small")
        for _wki, (_wl, _wv, _wc, _wu, _ico) in enumerate(_ward_kpi):
            _wk_cols[_wki].markdown(
                f'<div class="fn-kpi" style="border-top:3px solid {_wc};min-height:80px;">'
                f'<div class="fn-kpi-icon">{_ico}</div>'
                f'<div class="fn-kpi-label">{_wl}</div>'
                f'<div class="fn-kpi-value" style="color:{_wc};">{_wv}'
                f'<span class="fn-kpi-unit">{_wu}</span></div></div>',
                unsafe_allow_html=True,
            )

    if st.session_state.get("fn_show_room", False) and ward_room_detail:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:12px 14px;margin-bottom:8px;">',
            unsafe_allow_html=True,
        )
        _TH_R = "padding:6px 8px;font-size:10px;font-weight:700;text-transform:uppercase;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        _rh = (
            '<div style="overflow-x:auto;max-height:280px;overflow-y:auto;">'
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>'
            f'<th style="{_TH_R}text-align:left;">병동</th>'
            f'<th style="{_TH_R}text-align:center;">병실</th>'
            f'<th style="{_TH_R}text-align:center;">베드</th>'
            f'<th style="{_TH_R}text-align:center;">상태</th>'
            f'<th style="{_TH_R}text-align:center;">성별</th>'
            f'<th style="{_TH_R}text-align:left;">진료과</th>'
            f'<th style="{_TH_R}text-align:right;">병실료</th>'
            '</tr></thead><tbody>'
        )
        _STATUS_CLR = {"재원":("#1D4ED8","#DBEAFE"),"퇴원예정":("#7C3AED","#EDE9FE"),
                       "빈병상":("#16A34A","#DCFCE7"),"LOCK":("#DC2626","#FEE2E2")}
        for _ri, _r in enumerate(ward_room_detail[:80]):
            _bno = str(_r.get("병실번호","")).zfill(6)
            _sc, _sbg = _STATUS_CLR.get(_r.get("상태","빈병상"), ("#64748B","#F1F5F9"))
            _fee = int(_r.get("병실료", 0) or 0)
            _bg_r = "#F8FAFC" if _ri % 2 == 0 else "#FFFFFF"
            _td_r = f"padding:5px 8px;background:{_bg_r};border-bottom:1px solid #F8FAFC;"
            _rh += (
                f"<tr>"
                f'<td style="{_td_r}font-weight:600;">{_r.get("병동명","")}</td>'
                f'<td style="{_td_r}text-align:center;font-family:Consolas,monospace;">{_bno[2:4]}</td>'
                f'<td style="{_td_r}text-align:center;font-family:Consolas,monospace;color:#7C3AED;">{_bno[4:6]}</td>'
                f'<td style="{_td_r}text-align:center;">'
                f'<span style="background:{_sbg};color:{_sc};border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;">{_r.get("상태","")}</span></td>'
                f'<td style="{_td_r}text-align:center;font-weight:600;">{_r.get("성별","─")}</td>'
                f'<td style="{_td_r}">{_r.get("진료과","─")}</td>'
                f'<td style="{_td_r}text-align:right;font-family:Consolas,monospace;">{"─" if not _fee else f"{_fee:,}원"}</td>'
                f"</tr>"
            )
        st.markdown(_rh + "</tbody></table></div></div>", unsafe_allow_html=True)
    elif st.session_state.get("fn_show_room", False):
        st.info("V_WARD_ROOM_DETAIL 데이터 없음 — Oracle 연결 확인")

    _gap()

    # ── 일일현황 테이블
    st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["blue"] + ';">', unsafe_allow_html=True)
    _sec_hd("📋 일일현황", "진료과별 외래·입원·퇴원·재원 (보험구분)", C["blue"])
    _INS_CODES = ["공단", "보호", "산재", "자보", "기타"]
    _CATS      = ["외래", "입원", "퇴원", "재원"]
    _CAT_COLORS= {"외래":C["blue"],"입원":C["indigo"],"퇴원":C["t2"],"재원":C["violet"]}
    if daily_dept_stat:
        from collections import defaultdict as _ddd2
        _agg: dict = _ddd2(lambda: _ddd2(lambda: _ddd2(int)))
        for _r in daily_dept_stat:
            _dept = _r.get("진료과명",""); _cat = _r.get("구분","")
            _ins  = _r.get("보험구분","기타"); _cnt = int(_r.get("건수",0) or 0)
            if _dept and _cat: _agg[_dept][_cat][_ins] += _cnt
        _depts = sorted(_agg.keys())
        _TH_D = "padding:4px 6px;font-size:11px;font-weight:700;letter-spacing:.02em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;text-align:right;"
        _TH_L = _TH_D.replace("text-align:right;","text-align:left;")
        _colspan = len(_INS_CODES) + 1
        _gh = "".join(
            f'<th colspan="{_colspan}" style="padding:4px;font-size:11.5px;font-weight:800;'
            f'color:{_CAT_COLORS[c]};border-bottom:1px solid #E2E8F0;background:#F8FAFC;'
            f'text-align:center;border-left:2px solid {_CAT_COLORS[c]}33;">{c}</th>'
            for c in _CATS
        )
        _sh2 = "".join(
            (f'<th style="{_TH_D}border-left:2px solid {_CAT_COLORS[c]}33;">{ins}</th>'
             if i == 0 else f'<th style="{_TH_D}">{ins}</th>') +
            (f'<th style="{_TH_D}color:{_CAT_COLORS[c]};font-weight:800;">계</th>'
             if i == len(_INS_CODES)-1 else "")
            for c in _CATS for i, ins in enumerate(_INS_CODES)
        )
        _rows_d = ""
        _tot: dict = _ddd2(lambda: _ddd2(int))
        for _di, _dept in enumerate(_depts):
            _rbg = "#F8FAFC" if _di%2==0 else "#FFFFFF"
            _td_s = f"padding:4px 5px;background:{_rbg};border-bottom:1px solid #F1F5F9;font-size:12px;font-family:Consolas,monospace;text-align:right;"
            _rows_d += (f'<tr><td style="{_td_s.replace("text-align:right;","text-align:left;")}'
                        f'font-weight:700;font-family:inherit;color:#0F172A;white-space:nowrap;">{_dept}</td>')
            for _ci, _cat in enumerate(_CATS):
                _subtot = 0
                for _ii, _ins in enumerate(_INS_CODES):
                    _v = _agg[_dept][_cat][_ins]; _subtot += _v; _tot[_cat][_ins] += _v
                    _bl2 = f"border-left:2px solid {_CAT_COLORS[_cat]}33;" if _ii==0 else ""
                    _rows_d += f'<td style="{_td_s}{_bl2}">{"─" if _v==0 else _v}</td>'
                _tot[_cat]["계"] += _subtot
                _rows_d += (f'<td style="{_td_s}font-weight:700;color:{_CAT_COLORS[_cat]};">'
                            f'{"─" if _subtot==0 else _subtot}</td>')
            _rows_d += "</tr>"
        _sth_d = "padding:4px 5px;background:#EFF6FF;border-top:2px solid #BFDBFE;font-size:12px;font-family:Consolas,monospace;text-align:right;font-weight:700;"
        _rows_d += f'<tr><td style="{_sth_d.replace("text-align:right;","text-align:left;")}font-family:inherit;color:#1E40AF;">합계</td>'
        for _cat in _CATS:
            for _ii, _ins in enumerate(_INS_CODES):
                _v = _tot[_cat][_ins]
                _bl2 = f"border-left:2px solid {_CAT_COLORS[_cat]}33;" if _ii==0 else ""
                _rows_d += f'<td style="{_sth_d}{_bl2}color:{_CAT_COLORS[_cat]};">{"─" if _v==0 else _v}</td>'
            _v2 = _tot[_cat]["계"]
            _rows_d += (f'<td style="{_sth_d}color:{_CAT_COLORS[_cat]};font-size:12.5px;">{"─" if _v2==0 else _v2}</td>')
        _rows_d += "</tr>"
        st.markdown(
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
            f'<thead><tr><th style="{_TH_L}min-width:40px;">진료과</th>{_gh}</tr>'
            f'<tr><th style="{_TH_L}"></th>{_sh2}</tr>'
            f'</thead><tbody>{_rows_d}</tbody></table></div>',
            unsafe_allow_html=True,
        )

    # 파이차트
    _PALETTE_P = [
        "#1E40AF","#4F46E5","#0891B2","#059669","#D97706",
        "#DC2626","#7C3AED","#DB2777","#65A30D","#9333EA",
        "#0284C7","#16A34A","#EA580C","#0F766E","#BE185D",
    ]
    _PIE_DEFS = [
        ("외래","🥧 외래 진료과별 구성",C["blue"],   "daily_pie_opd"),
        ("입원","🥧 입원 진료과별 구성",C["indigo"], "daily_pie_adm"),
        ("재원","🥧 재원 진료과별 구성",C["violet"], "daily_pie_stay"),
    ]
    if daily_dept_stat and HAS_PLOTLY:
        from collections import defaultdict as _ddd_pie
        _pie_all: dict = _ddd_pie(lambda: _ddd_pie(int))
        for _r in daily_dept_stat:
            _cat_p = _r.get("구분",""); _dept_p = _r.get("진료과명","")
            if _cat_p and _dept_p:
                _pie_all[_cat_p][_dept_p] += int(_r.get("건수",0) or 0)
        _pie_cols = st.columns(3, gap="small")
        for _pci, (_pcat, _ptitle, _pclr, _pkey) in enumerate(_PIE_DEFS):
            _pd = _pie_all.get(_pcat, {})
            with _pie_cols[_pci]:
                st.markdown(f'<div style="background:#FFFFFF;border:1px solid #F0F4F8;border-top:3px solid {_pclr};border-radius:10px;padding:10px 12px;">', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:12px;font-weight:700;color:{_pclr};margin-bottom:4px;">{_ptitle}</div>', unsafe_allow_html=True)
                if _pd:
                    _sorted_d = sorted(_pd.items(), key=lambda x:-x[1])
                    _top10    = _sorted_d[:10]; _etc_sum = sum(v for _,v in _sorted_d[10:])
                    _pl = [k for k,_ in _top10]; _pv = [v for _,v in _top10]
                    if _etc_sum > 0: _pl.append("기타"); _pv.append(_etc_sum)
                    _ptotal = sum(_pv)
                    _figP = go.Figure(go.Pie(
                        labels=_pl, values=_pv,
                        marker=dict(colors=_PALETTE_P[:len(_pl)], line=dict(color="#fff",width=1.5)),
                        hole=0.48, textinfo="label+percent", textfont=dict(size=10),
                        insidetextorientation="radial", sort=True,
                        hovertemplate="<b>%{label}</b><br>%{value:,}명 (%{percent})<extra></extra>",
                    ))
                    _figP.update_layout(**_PLOTLY_LAYOUT, height=300,
                        margin=dict(l=0,r=0,t=4,b=4), showlegend=False,
                        annotations=[dict(text=f"<b>{_ptotal:,}</b><br><span style='font-size:10px'>명</span>",
                            x=0.5,y=0.5,font=dict(size=13,color=_pclr),showarrow=False)])
                    st.plotly_chart(_figP, use_container_width=True, key=_pkey)
                else:
                    st.markdown(f'<div style="height:200px;display:flex;align-items:center;justify-content:center;color:#94A3B8;font-size:12px;">데이터 없음</div>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    # 키오스크
    ck, cd = st.columns([1,1], gap="small")
    with ck:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["violet"] + ';">', unsafe_allow_html=True)
        _sec_hd("🖥️ 키오스크 진료과별 수납 건수","금일 기준", C["violet"])
        if kiosk_by_dept:
            _k_total = sum(int(r.get("수납건수",0) or 0) for r in kiosk_by_dept)
            st.markdown(f'<div style="font-size:10px;color:#64748B;margin-bottom:8px;">총 <b style="color:{C["violet"]};font-size:13px;">{_k_total:,}</b>건</div>', unsafe_allow_html=True)
            _TH_K = "padding:6px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
            _tk = (
                '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>'
                f'<th style="{_TH_K}text-align:left;">진료과</th>'
                f'<th style="{_TH_K}text-align:right;color:{C["violet"]};">건수</th>'
                f'<th style="{_TH_K}text-align:right;color:{C["indigo"]};">금액(만)</th>'
                f'<th style="{_TH_K}">비율</th></tr></thead><tbody>'
            )
            for _ki, _r in enumerate(kiosk_by_dept[:15]):
                _kd = _r.get("진료과명",""); _kc = int(_r.get("수납건수",0) or 0)
                _ka = int(_r.get("수납금액",0) or 0); _kp = round(_kc/max(_k_total,1)*100)
                _kbg = "#F8FAFC" if _ki%2==0 else "#FFFFFF"
                _td_k = f"padding:5px 8px;background:{_kbg};border-bottom:1px solid #F8FAFC;"
                _tk += (
                    f"<tr><td style='{_td_k}font-weight:600;'>{_kd}</td>"
                    f"<td style='{_td_k}text-align:right;color:{C['violet']};font-family:Consolas,monospace;font-weight:700;'>{_kc:,}</td>"
                    f"<td style='{_td_k}text-align:right;color:{C['indigo']};font-family:Consolas,monospace;'>{_ka//10000 if _ka else '─'}만</td>"
                    f"<td style='{_td_k}'><div style='display:flex;align-items:center;gap:4px;'>"
                    f"<div style='flex:1;height:6px;background:#F1F5F9;border-radius:3px;'>"
                    f"<div style='width:{_kp}%;height:100%;background:{C['violet']};border-radius:3px;'></div></div>"
                    f"<span style='font-size:10px;color:#64748B;'>{_kp}%</span></div></td></tr>"
                )
            st.markdown(_tk + "</tbody></table>", unsafe_allow_html=True)
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)

    with cd:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["teal"] + ';">', unsafe_allow_html=True)
        _sec_hd("📈 7일간 키오스크 vs 창구 수납 건수","일별 추이", C["teal"])
        if kiosk_counter_trend and HAS_PLOTLY:
            def _fmt_date(d):
                s = str(d).replace('-','')[:8]
                return f"{s[4:6]}/{s[6:8]}" if len(s) >= 8 else str(d)[:10]
            _dates_k = [_fmt_date(r.get("기준일","")) for r in kiosk_counter_trend]
            _k_vals  = [int(r.get("키오스크건수",0) or 0) for r in kiosk_counter_trend]
            _c_vals  = [int(r.get("창구건수",    0) or 0) for r in kiosk_counter_trend]
            _figKC = go.Figure()
            _figKC.add_trace(go.Bar(x=_dates_k,y=_k_vals,name="키오스크",
                marker_color=C["violet"],marker=dict(line=dict(width=0)),
                text=_k_vals,textposition="outside",textfont=dict(size=11,color=C["violet"]),
                hovertemplate="%{x}<br>키오스크: %{y}건<extra></extra>"))
            _figKC.add_trace(go.Bar(x=_dates_k,y=_c_vals,name="창구",
                marker_color=C["teal"],marker=dict(line=dict(width=0)),
                text=_c_vals,textposition="outside",textfont=dict(size=11,color=C["teal"]),
                hovertemplate="%{x}<br>창구: %{y}건<extra></extra>"))
            _kc_max = max(max(_k_vals,default=0),max(_c_vals,default=0))
            _figKC.update_layout(**_PLOTLY_LAYOUT,barmode="group",height=280,
                margin=dict(l=0,r=0,t=30,b=8),
                legend=dict(orientation="h",y=1.12,x=0.5,xanchor="center",font=dict(size=12),bgcolor="rgba(0,0,0,0)"),
                bargap=0.25,bargroupgap=0.05)
            _figKC.update_xaxes(tickfont=dict(size=12,color="#334155"))
            _figKC.update_yaxes(title_text="수납 건수",title_font=dict(size=10,color=C["t3"]),
                range=[0, _kc_max*1.22])
            st.plotly_chart(_figKC, use_container_width=True, key="kiosk_counter_trend")
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#94A3B8;font-size:12px;">V_KIOSK_COUNTER_TREND 생성 후 조회 가능</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 탭 2 — 수납·미수금  (기존 _tab_revenue 그대로)
# ════════════════════════════════════════════════════════════════════
def _tab_revenue(finance_today, finance_trend, finance_by_dept, overdue_stat):
    _tot_amt = sum(int(r.get("금액",0) or 0) for r in finance_today)
    _tot_cnt = sum(int(r.get("건수",0) or 0) for r in finance_today)
    _tot_gol = sum(int(r.get("목표금액",0) or 0) for r in finance_today)
    _gol_pct = round(_tot_amt/_tot_gol*100,1) if _tot_gol > 0 else 0.0
    _ov_amt  = sum(int(r.get("금액",0) or 0) for r in overdue_stat)

    k1,k2,k3,k4 = st.columns(4, gap="small")
    _kpi_card(k1,"💰","금일 수납 합계",_fmt_won(_tot_amt),"",f"건수 {_tot_cnt:,}건",C["blue"],goal_pct=_gol_pct)
    _kpi_card(k2,"🎯","목표 달성률",f"{_gol_pct:.1f}","%",f"목표 {_fmt_won(_tot_gol)}",
              C["green"] if _gol_pct>=100 else C["yellow"] if _gol_pct>=70 else C["red"])
    _kpi_card(k3,"🔴","미수금 합계",_fmt_won(_ov_amt),"","30일 이상 기준",C["red"])
    _kpi_card(k4,"📋","금일 건수",f"{_tot_cnt:,}","건","보험유형 합산",C["indigo"])
    _gap()

    cp, ct = st.columns([2,3], gap="small")
    with cp:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["indigo"] + ';">', unsafe_allow_html=True)
        _sec_hd("🥧 보험유형별 수납","금일 기준", C["indigo"])
        if finance_today and HAS_PLOTLY:
            _labels = [r.get("보험유형","기타") for r in finance_today]
            _values = [int(r.get("금액",0) or 0) for r in finance_today]
            _counts = [int(r.get("건수",0) or 0) for r in finance_today]
            _pcolors= [C["blue"],C["green"],C["yellow"],C["violet"],C["teal"],C["orange"],C["red"]]
            _fig = go.Figure(go.Pie(labels=_labels,values=_values,customdata=_counts,
                hovertemplate="<b>%{label}</b><br>금액:%{value:,}원<br>건수:%{customdata}건<br>%{percent}<extra></extra>",
                marker=dict(colors=_pcolors[:len(_labels)],line=dict(color="#fff",width=2)),
                hole=0.52,textinfo="label+percent",textfont=dict(size=11),insidetextorientation="radial"))
            _fig.update_layout(height=260,margin=dict(l=0,r=0,t=10,b=10),
                paper_bgcolor="rgba(0,0,0,0)",font=dict(color="#333",size=11),
                legend=dict(orientation="v",x=1.02,y=0.5,font=dict(size=11),bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(text=f"<b>{_fmt_won(_tot_amt)}</b>",x=0.5,y=0.5,
                    font=dict(size=13,color=C["t1"]),showarrow=False)])
            st.plotly_chart(_fig, use_container_width=True, key="rev_pie")
            _TH3 = "padding:7px 10px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
            _t3 = (
                '<table style="width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px;">'
                f'<thead><tr><th style="{_TH3}text-align:left;">보험유형</th>'
                f'<th style="{_TH3}text-align:right;">건수</th>'
                f'<th style="{_TH3}text-align:right;">금액</th>'
                f'<th style="{_TH3}text-align:right;">달성률</th></tr></thead><tbody>'
            )
            for i, r in enumerate(finance_today):
                _typ = r.get("보험유형",""); _cnt = int(r.get("건수",0) or 0)
                _amt = int(r.get("금액",0) or 0); _gol = int(r.get("목표금액",0) or 0)
                _pct = round(_amt/_gol*100,1) if _gol>0 else 0.0
                _pc  = C["green"] if _pct>=100 else C["yellow"] if _pct>=70 else C["red"]
                _bg3 = "#F8FAFC" if i%2==0 else "#fff"
                _td3 = f"padding:7px 10px;background:{_bg3};border-bottom:1px solid #F8FAFC;"
                _t3 += (f"<tr><td style='{_td3}font-weight:700;'>{_typ}</td>"
                        f"<td style='{_td3}text-align:right;color:{C['t3']};font-family:Consolas,monospace;'>{_cnt:,}</td>"
                        f"<td style='{_td3}text-align:right;font-weight:700;font-family:Consolas,monospace;'>{_fmt_won(_amt)}</td>"
                        f"<td style='{_td3}text-align:right;font-weight:700;color:{_pc};'>{_pct:.0f}%</td></tr>")
            st.markdown(_t3 + "</tbody></table>", unsafe_allow_html=True)
        else:
            st.markdown('<div style="padding:30px;text-align:center;color:#94A3B8;">V_FINANCE_TODAY 확인</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with ct:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["blue"] + ';">', unsafe_allow_html=True)
        _sec_hd("📈 최근 30일 수납 추세","일별 수납 금액", C["blue"])
        if finance_trend and HAS_PLOTLY:
            _dates = [str(r.get("기준일",""))[:10] for r in finance_trend]
            _amts  = [int(r.get("수납금액",0) or 0)//10000 for r in finance_trend]
            _cnts  = [int(r.get("수납건수",0) or 0) for r in finance_trend]
            _fig2  = go.Figure()
            _fig2.add_trace(go.Bar(x=_dates,y=_amts,name="수납금액(만원)",
                marker_color=C["blue_l"],marker=dict(line=dict(color=C["blue"],width=0.5)),
                hovertemplate="%{x}<br>%{y:,}만원<extra></extra>",yaxis="y"))
            _fig2.add_trace(go.Scatter(x=_dates,y=_amts,name="추세",mode="lines+markers",
                line=dict(color=C["blue"],width=2.5),
                marker=dict(size=5,color=C["blue"],line=dict(color="#fff",width=1.5)),
                hoverinfo="skip",yaxis="y"))
            _fig2.add_trace(go.Bar(x=_dates,y=_cnts,name="수납건수",
                marker_color=C["indigo_l"],marker=dict(line=dict(color=C["indigo"],width=0.5)),
                hovertemplate="%{x}<br>%{y:,}건<extra></extra>",yaxis="y2",visible="legendonly"))
            _fig2.update_layout(**_PLOTLY_LAYOUT,height=250,margin=dict(l=0,r=40,t=8,b=8),
                legend=dict(orientation="h",y=1.06,x=0.5,xanchor="center",font=dict(size=11),bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified",bargap=0.25)
            _fig2.update_xaxes(tickangle=-30,nticks=15)
            _fig2.update_yaxes(tickformat=",",title_text="수납금액(만원)",title_font=dict(size=10,color=C["t3"]))
            _fig2.update_layout(yaxis2=dict(overlaying="y",side="right",showgrid=False,
                tickfont=dict(size=10,color=C["indigo"]),title=dict(text="건수",font=dict(size=10,color=C["indigo"]))))
            st.plotly_chart(_fig2, use_container_width=True, key="rev_trend")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)

    _gap()
    cd2, co = st.columns([3,2], gap="small")
    with cd2:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["teal"] + ';">', unsafe_allow_html=True)
        _sec_hd("🏆 진료과별 수납 현황 (당월)","금액 순위", C["teal"])
        if finance_by_dept and HAS_PLOTLY:
            _depts2 = [r.get("진료과명","") for r in finance_by_dept[:12]]
            _amts2  = [int(r.get("수납금액",0) or 0)//10000 for r in finance_by_dept[:12]]
            _ptc    = [int(r.get("환자수",0) or 0) for r in finance_by_dept[:12]]
            _maxA   = max(_amts2) if _amts2 else 1
            _gcol   = [f"rgba(30,64,175,{0.3+0.7*(_a/_maxA):.2f})" for _a in _amts2]
            _fig3   = go.Figure(go.Bar(x=_amts2,y=_depts2,orientation="h",
                marker=dict(color=_gcol,line=dict(color=C["blue"],width=0.5)),customdata=_ptc,
                text=[f"{_a:,}만" for _a in _amts2],textposition="outside",textfont=dict(size=11,color=C["blue"]),
                hovertemplate="<b>%{y}</b><br>%{x:,}만원<br>환자수:%{customdata}명<extra></extra>"))
            _fig3.update_layout(**_PLOTLY_LAYOUT,height=max(240,len(_depts2)*28),
                margin=dict(l=0,r=60,t=4,b=4),showlegend=False,bargap=0.3)
            _fig3.update_xaxes(ticksuffix="만")
            _fig3.update_yaxes(tickfont=dict(size=11),autorange="reversed")
            st.plotly_chart(_fig3, use_container_width=True, key="rev_dept_bar")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)

    with co:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["red"] + ';">', unsafe_allow_html=True)
        _sec_hd("🔴 미수금 현황","연령별 분류", C["red"])
        if overdue_stat:
            _totO = sum(int(r.get("금액",0) or 0) for r in overdue_stat)
            st.markdown(f'<div style="background:{C["red_l"]};border:1px solid #FECDD3;border-radius:8px;padding:10px 14px;margin-bottom:10px;">'
                        f'<div style="font-size:10px;font-weight:700;color:#991B1B;text-transform:uppercase;letter-spacing:.1em;">미수금 총액</div>'
                        f'<div style="font-size:28px;font-weight:800;color:{C["red"]};">{_fmt_won(_totO)}</div></div>', unsafe_allow_html=True)
            _OC = {"30일미만":(C["green"],C["green_l"]),"30~60일":(C["yellow"],C["yellow_l"]),
                   "60~90일":(C["orange"],C["orange_l"]),"90일이상":(C["red"],C["red_l"])}
            _maxO = max((int(r.get("금액",0) or 0) for r in overdue_stat), default=1)
            for r in overdue_stat:
                _age = r.get("연령구분",""); _amt = int(r.get("금액",0) or 0)
                _cnt = int(r.get("건수",0) or 0); _pctO = round(_amt/_maxO*100) if _maxO>0 else 0
                _oc, _obg = _OC.get(_age, (C["t3"],"#F8FAFC"))
                st.markdown(
                    f'<div class="overdue-row"><span class="overdue-label" style="color:{_oc};">{_age}</span>'
                    f'<div class="overdue-bar-wrap"><div class="overdue-bar" style="width:{_pctO}%;background:{_oc};"></div></div>'
                    f'<span class="overdue-val" style="color:{_oc};">{_fmt_won(_amt)}</span>'
                    f'<span style="font-size:10px;color:{C["t4"]};width:30px;text-align:right;">{_cnt}건</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div style="padding:30px;text-align:center;color:#94A3B8;">V_OVERDUE_STAT 확인</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 탭 3 (기존 탭2) — 주간추이분석  v2.3 전면 재설계
#
# [구성]
#   배너   : 실시간현황과 명시적 분리
#   섹션1  : 📈 7일간 추이  (외래·입원·퇴원·재원 라인)
#   섹션2  : 🗓️ 외래 히트맵 [좌 1/2] | 🗓️ 입원 히트맵 [우 1/2]
#   섹션3  : 🛏️ 진료과별 재원일수 분포 (스택 바 + DRG 경고)
#
# [삭제]
#   ⏱️ 대기시간 추세 (V_WAITTIME_TREND)
#   📈 진료과별 외래 추세 라인 + 진료과 선택기
# ════════════════════════════════════════════════════════════════════
def _tab_analytics(
    opd_dept_trend: List[Dict],
    los_dist_dept:  List[Dict],
    daily_dept_stat: Optional[List[Dict]] = None,
    ipd_dept_trend:  Optional[List[Dict]] = None,
) -> None:
    from collections import defaultdict as _ddc

    daily_dept_stat = daily_dept_stat or []
    ipd_dept_trend  = ipd_dept_trend  or []
    los_dist_dept   = los_dist_dept   or []

    # ── 분리 배너
    _gap()
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["blue"]}15,{C["indigo"]}10);'
        f'border-left:4px solid {C["blue"]};border-radius:0 8px 8px 0;'
        f'padding:10px 16px;margin-bottom:4px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:18px;">📊</span>'
        f'<div><div style="font-size:13px;font-weight:700;color:{C["blue"]};">주간 통계 · 분석</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'실시간 현황 탭과 별도 집계 — 최근 7일 누적 기준 / 재원일수는 현재 재원 환자 기준'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # ════════════════════
    # [1] 📈 7일간 추이
    # ════════════════════
    _gap()
    st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["blue"] + ';">', unsafe_allow_html=True)
    _sec_hd("📈 7일간 추이", "외래·입원·퇴원·재원 일별 전체 합계", C["blue"])
    if daily_dept_stat and HAS_PLOTLY:
        _trend_day: dict = _ddc(lambda: _ddc(int))
        for _r in daily_dept_stat:
            _rd    = str(_r.get("기준일","")).replace("-","")
            _d_fmt = f"{_rd[4:6]}/{_rd[6:8]}" if len(_rd)>=8 else str(_r.get("기준일",""))[:10]
            _cat   = _r.get("구분","")
            if _cat in ("외래","입원","퇴원","재원"):
                _trend_day[_d_fmt][_cat] += int(_r.get("건수",0) or 0)
        _tr_dates = sorted(_trend_day.keys())[-7:]
        if _tr_dates:
            _tr_colors = {"외래":C["blue"],"입원":C["indigo"],"퇴원":C["t2"],"재원":C["violet"]}
            _tr_dash   = {"외래":"solid","입원":"solid","퇴원":"dot","재원":"dash"}
            _figOPD = go.Figure()
            for _tc in ("외래","입원","퇴원","재원"):
                _ty = [_trend_day[d][_tc] for d in _tr_dates]
                _figOPD.add_trace(go.Scatter(
                    x=_tr_dates, y=_ty, name=_tc, mode="lines+markers",
                    line=dict(color=_tr_colors[_tc], width=2.5, dash=_tr_dash[_tc]),
                    marker=dict(size=6, color=_tr_colors[_tc], line=dict(color="#fff",width=1.5)),
                    hovertemplate=f"%{{x}}<br>{_tc}: %{{y}}명<extra></extra>",
                ))
            _figOPD.update_layout(**_PLOTLY_LAYOUT, height=260,
                margin=dict(l=0,r=0,t=28,b=8),
                legend=dict(orientation="h",y=1.12,x=0.5,xanchor="center",
                            font=dict(size=12),bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified")
            _figOPD.update_xaxes(tickfont=dict(size=12,color="#334155"))
            _figOPD.update_yaxes(title_text="인원 (명)",title_font=dict(size=10,color=C["t3"]))
            st.plotly_chart(_figOPD, use_container_width=True, key="an_7day_trend")
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#94A3B8;">V_DAILY_DEPT_STAT 기준일 컬럼 필요</div>', unsafe_allow_html=True)
    else:
        _plotly_empty()
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    # ═══════════════════════════════════════
    # [2] 히트맵 2분할 — 외래 [1/2] | 입원 [1/2]
    # ═══════════════════════════════════════
    def _render_heatmap(data, value_col, title, sub, color, colorscale, chart_key):
        """
        진료과×날짜 히트맵 공통 렌더러.
        data      : Oracle VIEW 조회 결과 (list of dict)
        value_col : 수치 컬럼명 ("외래환자수" / "입원환자수")
        """
        st.markdown(f'<div class="wd-card" style="border-top:3px solid {color};">', unsafe_allow_html=True)
        _sec_hd(title, sub, color)
        if data and HAS_PLOTLY:
            _all_dates = sorted({str(r.get("기준일",""))[:10] for r in data if r.get("기준일")})[-7:]
            _all_depts = sorted({r.get("진료과명","") for r in data if r.get("진료과명","")})
            if _all_dates and _all_depts:
                _val_map = {
                    (r.get("진료과명",""), str(r.get("기준일",""))[:10]):
                        int(r.get(value_col, 0) or 0)
                    for r in data
                }
                _z = [[_val_map.get((dept,d),0) for d in _all_dates] for dept in _all_depts]
                _x_labels = [f"{d[5:7]}/{d[8:10]}" if len(d)>=10 else d for d in _all_dates]
                _fig_hm = go.Figure(go.Heatmap(
                    z=_z, x=_x_labels, y=_all_depts,
                    colorscale=colorscale,
                    text=[[str(v) if v>0 else "" for v in row] for row in _z],
                    texttemplate="%{text}", textfont=dict(size=9, color="#333"),
                    hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}명<extra></extra>",
                    showscale=False, xgap=2, ygap=2,
                ))
                _h = max(200, len(_all_depts)*22+60)
                _fig_hm.update_layout(**_PLOTLY_LAYOUT, height=_h, margin=dict(l=0,r=0,t=8,b=8))
                _fig_hm.update_xaxes(tickfont=dict(size=10), side="top")
                _fig_hm.update_yaxes(tickfont=dict(size=10), autorange="reversed")
                st.plotly_chart(_fig_hm, use_container_width=True, key=chart_key)
            else:
                _plotly_empty()
        else:
            _view_name = "V_OPD_DEPT_TREND" if "외래" in title else "V_IPD_DEPT_TREND"
            st.markdown(f'<div style="padding:32px;text-align:center;color:#94A3B8;font-size:13px;">데이터 없음 — {_view_name} 확인<br><span style="font-size:11px;">DDL: monthly_views_new.sql</span></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    c_opd, c_ipd = st.columns([1,1], gap="small")
    with c_opd:
        _render_heatmap(
            data=opd_dept_trend, value_col="외래환자수",
            title="🗓️ 진료과별 7일 외래 인원 히트맵", sub="외래 환자수 · 진료과 × 날짜",
            color=C["blue"],
            colorscale=[[0.0,"#EFF6FF"],[0.5,"#3B82F6"],[1.0,"#1E40AF"]],
            chart_key="an_opd_heatmap",
        )
    with c_ipd:
        _render_heatmap(
            data=ipd_dept_trend, value_col="입원환자수",
            title="🗓️ 진료과별 7일 입원 인원 히트맵", sub="입원 환자수 · 진료과 × 날짜",
            color=C["indigo"],
            colorscale=[[0.0,"#EDE9FE"],[0.5,"#7C3AED"],[1.0,"#4C1D95"]],
            chart_key="an_ipd_heatmap",
        )
    _gap()

    # ═════════════════════════════════════
    # [3] 🛏️ 진료과별 재원일수 분포 (스택 바)
    # ═════════════════════════════════════
    st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["violet"] + ';">', unsafe_allow_html=True)
    _sec_hd("🛏️ 진료과별 재원일수 분포", "현재 재원 환자 기준 · 진료과 × 재원일수 구간", C["violet"])
    if los_dist_dept and HAS_PLOTLY:
        # 구간 정렬 (구간순서 컬럼 기준)
        _bins_ordered: list = []
        _seen_bins: set = set()
        for _r in sorted(los_dist_dept, key=lambda x: int(x.get("구간순서",99))):
            _b = _r.get("재원일수구간","")
            if _b and _b not in _seen_bins:
                _bins_ordered.append(_b); _seen_bins.add(_b)

        # 진료과 정렬 (총 환자수 내림차순)
        _dept_total: dict = _ddc(int)
        for _r in los_dist_dept:
            _dept_total[_r.get("진료과명","")] += int(_r.get("환자수",0) or 0)
        _depts_los = sorted([d for d in _dept_total if d], key=lambda d: -_dept_total[d])

        _los_map = {
            (r.get("진료과명",""), r.get("재원일수구간","")): int(r.get("환자수",0) or 0)
            for r in los_dist_dept
        }
        _bin_colors = [C["green"],C["teal"],C["blue"],C["yellow"],C["red"]]
        _fig_los = go.Figure()
        for _i, _bin in enumerate(_bins_ordered):
            _y_vals = [_los_map.get((dept,_bin),0) for dept in _depts_los]
            _fig_los.add_trace(go.Bar(
                name=_bin, x=_depts_los, y=_y_vals,
                marker_color=_bin_colors[_i%len(_bin_colors)],
                marker=dict(line=dict(color="#fff",width=0.5)),
                text=[str(v) if v>0 else "" for v in _y_vals],
                textposition="inside", textfont=dict(size=9,color="#fff"),
                hovertemplate=f"<b>%{{x}}</b><br>{_bin}: %{{y}}명<extra></extra>",
            ))
        _fig_los.update_layout(**_PLOTLY_LAYOUT, barmode="stack", height=320,
            margin=dict(l=0,r=0,t=8,b=50),
            legend=dict(orientation="h",y=-0.20,x=0.5,xanchor="center",
                        font=dict(size=11),bgcolor="rgba(0,0,0,0)"))
        _fig_los.update_xaxes(tickangle=-35, tickfont=dict(size=10), gridcolor="rgba(0,0,0,0)")
        _fig_los.update_yaxes(title_text="환자 수(명)", title_font=dict(size=10,color=C["t3"]))
        st.plotly_chart(_fig_los, use_container_width=True, key="an_los_dept_bar")

        # DRG 임계 경고
        _drg_bins = {b for b in _bins_ordered if any(k in b for k in ("15","30","60"))}
        _drg_by_dept: dict = _ddc(int)
        for _r in los_dist_dept:
            if _r.get("재원일수구간","") in _drg_bins:
                _drg_by_dept[_r.get("진료과명","")] += int(_r.get("환자수",0) or 0)
        _drg_total = sum(_drg_by_dept.values())
        if _drg_total > 0:
            _top3     = sorted(_drg_by_dept.items(), key=lambda x:-x[1])[:3]
            _top3_str = "  |  ".join(f'<b style="color:{C["red"]};">{d}</b> {n}명' for d,n in _top3)
            st.markdown(
                f'<div style="background:{C["red_l"]};border:1px solid #FECDD3;border-radius:8px;'
                f'padding:9px 14px;margin-top:6px;display:flex;align-items:center;gap:10px;">'
                f'<span style="font-size:16px;">⚠️</span>'
                f'<div><span style="font-size:12px;font-weight:700;color:{C["red"]};">'
                f'DRG 임계(15일+) 총 {_drg_total:,}명 — 퇴원 계획 검토 필요</span>'
                f'<div style="font-size:11px;margin-top:2px;">{_top3_str}</div></div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="padding:32px;text-align:center;color:#94A3B8;font-size:13px;">'
            'V_LOS_DIST_DEPT 가 없습니다 — monthly_views_new.sql 실행 후 재시작하세요.</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 탭 4 (신규) — 월간추이분석
#
# [구성]
#   배너   : 월간 분석 설명
#   컨트롤 : 기준월 / 비교월 선택 (selectbox)
#   테이블 : 진료과 × [기준월: 방문자수/신환/신환%/외래전체/구환] × [비교월: 동일] × 비고(신환증감)
#   차트   : 진료과별 신환자수 그룹 바
#
# [필요 VIEW]
#   V_MONTHLY_OPD_DEPT (신규 — DDL: monthly_views_new.sql)
#   컬럼: 기준년월(YYYYMM) / 진료과명 / 방문자수 / 신환자수 / 구환자수 / 외래전체 / 기타건수
# ════════════════════════════════════════════════════════════════════
def _tab_monthly(monthly_opd_dept: List[Dict], region_monthly: List[Dict] = None) -> None:
    monthly_opd_dept = monthly_opd_dept or []

    _gap()
    # 분리 배너
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["green"]}15,{C["teal"]}10);'
        f'border-left:4px solid {C["green"]};border-radius:0 8px 8px 0;'
        f'padding:10px 16px;margin-bottom:4px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:18px;">📅</span>'
        f'<div><div style="font-size:13px;font-weight:700;color:{C["green"]};">월간 추이 분석</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'2개월 선택 → 진료과별 방문자수 / 신환 / 신환비율 / 구환 / 신환증감 비교'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # VIEW 없음 안내 (return 제거 — 지역 비교 섹션은 별도 데이터라 계속 렌더링)
    if not monthly_opd_dept:
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;'
            f'padding:20px;text-align:center;margin-top:12px;">'
            f'<div style="font-size:32px;margin-bottom:8px;">📋</div>'
            f'<div style="font-size:14px;font-weight:700;color:#92400E;">V_MONTHLY_OPD_DEPT 데이터 없음</div>'
            f'<div style="font-size:12px;color:#B45309;margin-top:6px;">'
            f'monthly_views_new.sql 을 DBeaver(DBA 계정)에서 실행 후 앱을 재시작하세요.<br>'
            f'컬럼: 기준년월(YYYYMM) / 진료과명 / 방문자수 / 신환자수 / 구환자수 / 외래전체 / 기타건수'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        # 지역 비교 섹션은 별도 뷰(V_REGION_DEPT_MONTHLY)를 쓰므로 아래로 계속 진행

    # 가용 월 목록 (내림차순) — OPD 데이터 있을 때만
    _avail = sorted(
        {str(r.get("기준년월",""))[:6] for r in monthly_opd_dept if str(r.get("기준년월",""))[:6].isdigit()},
        reverse=True,
    ) if monthly_opd_dept else []
    if monthly_opd_dept and len(_avail) < 2:
        st.warning("비교를 위해 2개월 이상의 데이터가 필요합니다.")

    if len(_avail) >= 2:
        def _fmt_ym(ym: str) -> str:
            return f"{ym[:4]}년 {ym[4:6]}월" if len(ym) >= 6 else ym
    
        # 월 선택 컨트롤
        _ctrl1, _ctrl2, _ctrl_spacer = st.columns([2, 2, 6], gap="small")
        with _ctrl1:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 기준월</div>', unsafe_allow_html=True)
            _m1 = st.selectbox("기준월", options=_avail, index=min(1, len(_avail)-1),
                               key="mon_m1", label_visibility="collapsed",
                               format_func=_fmt_ym,
                               help="분석 기준이 되는 월")
        with _ctrl2:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 비교월</div>', unsafe_allow_html=True)
            _m2 = st.selectbox("비교월", options=_avail, index=0,
                               key="mon_m2", label_visibility="collapsed",
                               format_func=_fmt_ym,
                               help="기준월과 비교할 월 (전월 또는 동기 선택)")
    
        _m1_label = _fmt_ym(_m1)
        _m2_label = _fmt_ym(_m2)
    
        # 데이터 분리
        _d1 = {r.get("진료과명",""): r for r in monthly_opd_dept if str(r.get("기준년월",""))[:6] == _m1}
        _d2 = {r.get("진료과명",""): r for r in monthly_opd_dept if str(r.get("기준년월",""))[:6] == _m2}
    
        # 진료과 목록 (합집합, 총 방문자수 내림차순)
        _all_depts_raw = sorted(set(list(_d1.keys()) + list(_d2.keys())))
        _dept_visit    = {d: int(_d2.get(d, _d1.get(d,{})).get("방문자수",0) or 0) for d in _all_depts_raw}
        _all_depts     = [d for d in sorted(_all_depts_raw, key=lambda d:-_dept_visit[d]) if d]
    
        def _vi(r, key): return int(r.get(key, 0) or 0)
        def _pct(n, d):  return f"{round(n/d*100,1):.1f}%" if d > 0 else "─"
    
        # ── 비교 테이블 ───────────────────────────────────────────────
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["green"] + ';margin-top:8px;">', unsafe_allow_html=True)
        _sec_hd("📊 2개월 진료과별 외래 인원 비교", f"{_m1_label} vs {_m2_label}", C["green"])
    
        _TH = "padding:5px 8px;font-size:10.5px;font-weight:700;color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
    
        # 그룹 헤더 (1행)
        _h1 = (
            f'<th style="{_TH}text-align:left;" rowspan="2">구분</th>'
            f'<th colspan="5" style="{_TH}text-align:center;color:{C["blue"]};border-left:3px solid {C["blue"]}33;">'
            f'{_m1_label} (기준)</th>'
            f'<th colspan="5" style="{_TH}text-align:center;color:{C["indigo"]};border-left:3px solid {C["indigo"]}33;">'
            f'{_m2_label} (비교)</th>'
            f'<th style="{_TH}text-align:center;color:{C["red"]};" rowspan="2">'
            f'비고<br><span style="font-size:9px;font-weight:400;">전월대비 신환증감</span></th>'
        )
        # 서브 헤더 (2행)
        _sub_cols = [
            ("방문자수",   C["t2"],    False),
            ("신환(첫방문)",C["green"], True),
            ("신환%",      C["green"], False),
            ("외래전체",   C["blue"],  False),
            ("구환자수",   C["t3"],    False),
        ]
        _h2 = ""
        for _grp_color in [C["blue"], C["indigo"]]:
            for _idx, (_col_label, _col_c, _bold) in enumerate(_sub_cols):
                _bl = f"border-left:3px solid {_grp_color}33;" if _idx == 0 else ""
                _fw = "font-weight:800;" if _bold else ""
                _h2 += f'<th style="{_TH}text-align:right;color:{_col_c};{_bl}{_fw}">{_col_label}</th>'
    
        # 행 생성
        _rows = ""
        for _i, _dept in enumerate(_all_depts):
            _r1 = _d1.get(_dept, {}); _r2 = _d2.get(_dept, {})
            _v1  = _vi(_r1,"방문자수"); _s1 = _vi(_r1,"신환자수")
            _e1  = _vi(_r1,"외래전체"); _g1 = _vi(_r1,"구환자수")
            _v2  = _vi(_r2,"방문자수"); _s2 = _vi(_r2,"신환자수")
            _e2  = _vi(_r2,"외래전체"); _g2 = _vi(_r2,"구환자수")
    
            _diff     = _s2 - _s1
            _diff_pct = f"({round(_diff/_s1*100,1):+.1f}%)" if _s1 > 0 and _diff != 0 else ""
            _diff_str = (f"{'▲' if _diff>0 else '▼'} {abs(_diff):,}명 {_diff_pct}") if _diff != 0 else "─"
            _diff_c   = C["red"] if _diff > 0 else C["blue"] if _diff < 0 else C["t3"]
    
            _bg  = "#F8FAFC" if _i%2==0 else "#FFFFFF"
            _td  = f"padding:5px 8px;background:{_bg};border-bottom:1px solid #F1F5F9;font-size:12px;font-family:Consolas,monospace;text-align:right;"
            _tdl = _td.replace("text-align:right;","text-align:left;") + "font-family:inherit;font-weight:600;"
    
            _rows += (
                f"<tr>"
                f'<td style="{_tdl}">{_dept}</td>'
                # 기준월
                f'<td style="{_td}border-left:3px solid {C["blue"]}33;">{_v1:,}</td>'
                f'<td style="{_td}color:{C["green"]};font-weight:700;">{_s1:,}</td>'
                f'<td style="{_td}color:{C["green"]};">{_pct(_s1,_e1)}</td>'
                f'<td style="{_td}">{_e1:,}</td>'
                f'<td style="{_td}">{_g1:,}</td>'
                # 비교월
                f'<td style="{_td}border-left:3px solid {C["indigo"]}33;">{_v2:,}</td>'
                f'<td style="{_td}color:{C["indigo"]};font-weight:700;">{_s2:,}</td>'
                f'<td style="{_td}color:{C["indigo"]};">{_pct(_s2,_e2)}</td>'
                f'<td style="{_td}">{_e2:,}</td>'
                f'<td style="{_td}">{_g2:,}</td>'
                # 비고
                f'<td style="{_td}text-align:center;font-weight:700;color:{_diff_c};">{_diff_str}</td>'
                f"</tr>"
            )
    
        # 합계 행
        def _sum_all(d_dict):
            return {k: sum(int(r.get(k,0) or 0) for r in d_dict.values())
                    for k in ("방문자수","신환자수","구환자수","외래전체")}
        _t1   = _sum_all(_d1); _t2 = _sum_all(_d2)
        _tdif = _t2["신환자수"] - _t1["신환자수"]
        _tdif_pct = f"({round(_tdif/_t1['신환자수']*100,1):+.1f}%)" if _t1["신환자수"]>0 and _tdif!=0 else ""
        _tdif_str = (f"{'▲' if _tdif>0 else '▼'} {abs(_tdif):,}명 {_tdif_pct}") if _tdif!=0 else "─"
        _tdif_c   = C["red"] if _tdif>0 else C["blue"] if _tdif<0 else C["t3"]
        _tdc  = "padding:6px 8px;background:#F0FDF4;border-top:2px solid #86EFAC;font-size:12.5px;font-family:Consolas,monospace;text-align:right;font-weight:800;"
        _tdcl = _tdc.replace("text-align:right;","text-align:left;") + "color:#15803D;font-family:inherit;"
    
        _rows += (
            f"<tr>"
            f'<td style="{_tdcl}">합계</td>'
            f'<td style="{_tdc}border-left:3px solid {C["blue"]}33;">{_t1["방문자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["green"]};">{_t1["신환자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["green"]};">{_pct(_t1["신환자수"],_t1["외래전체"])}</td>'
            f'<td style="{_tdc}">{_t1["외래전체"]:,}</td>'
            f'<td style="{_tdc}">{_t1["구환자수"]:,}</td>'
            f'<td style="{_tdc}border-left:3px solid {C["indigo"]}33;">{_t2["방문자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["indigo"]};">{_t2["신환자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["indigo"]};">{_pct(_t2["신환자수"],_t2["외래전체"])}</td>'
            f'<td style="{_tdc}">{_t2["외래전체"]:,}</td>'
            f'<td style="{_tdc}">{_t2["구환자수"]:,}</td>'
            f'<td style="{_tdc}color:{_tdif_c};text-align:center;">{_tdif_str}</td>'
            f"</tr>"
        )
    
        st.markdown(
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>{_h1}</tr><tr>{_h2}</tr></thead>'
            f'<tbody>{_rows}</tbody></table></div>',
            unsafe_allow_html=True,
        )
    
        # 범례
        st.markdown(
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #F1F5F9;font-size:10.5px;">'
            f'<span style="color:{C["green"]};font-weight:700;">🟢 신환(첫방문): 해당 월 처음 내원 환자</span>'
            f'<span style="color:{C["t3"]};">🔵 구환: 이전 방문 이력 있는 환자</span>'
            f'<span style="color:{C["red"]};">▲ 증가 / <span style="color:{C["blue"]};">▼ 감소</span></span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        _gap()
    
        # ── 신환 비교 차트
        if HAS_PLOTLY and (_d1 or _d2) and _all_depts:
            st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["teal"] + ';">', unsafe_allow_html=True)
            _sec_hd("📊 진료과별 신환자수 월별 비교", f"{_m1_label} vs {_m2_label}", C["teal"])
            _s1_vals = [_vi(_d1.get(d,{}), "신환자수") for d in _all_depts]
            _s2_vals = [_vi(_d2.get(d,{}), "신환자수") for d in _all_depts]
            _fig_m   = go.Figure()
            _fig_m.add_trace(go.Bar(
                name=f"{_m1_label}(기준) 신환",
                x=_all_depts, y=_s1_vals,
                marker_color=C["blue_l"], marker=dict(line=dict(color=C["blue"],width=0.5)),
                hovertemplate=f"<b>%{{x}}</b><br>{_m1_label}: %{{y:,}}명<extra></extra>",
            ))
            _fig_m.add_trace(go.Bar(
                name=f"{_m2_label}(비교) 신환",
                x=_all_depts, y=_s2_vals,
                marker_color=C["indigo_l"], marker=dict(line=dict(color=C["indigo"],width=0.5)),
                hovertemplate=f"<b>%{{x}}</b><br>{_m2_label}: %{{y:,}}명<extra></extra>",
            ))
            # 증감 스캐터 오버레이
            _diff_vals = [_s2_vals[i] - _s1_vals[i] for i in range(len(_all_depts))]
            _diff_text = [f"{'▲' if v>0 else '▼' if v<0 else ''}{abs(v)}" if v!=0 else "" for v in _diff_vals]
            _diff_c2   = [C["red"] if v>0 else C["blue"] if v<0 else "rgba(0,0,0,0)" for v in _diff_vals]
            _fig_m.add_trace(go.Scatter(
                x=_all_depts, y=[max(a,b)+1 for a,b in zip(_s1_vals,_s2_vals)],
                mode="text", text=_diff_text,
                textfont=dict(size=10, color=_diff_c2),
                showlegend=False, hoverinfo="skip",
            ))
            _fig_m.update_layout(**_PLOTLY_LAYOUT, barmode="group", height=320,
                margin=dict(l=0,r=0,t=30,b=60),
                legend=dict(orientation="h",y=1.10,x=0.5,xanchor="center",font=dict(size=12),bgcolor="rgba(0,0,0,0)"),
                bargap=0.2, bargroupgap=0.05)
            _fig_m.update_xaxes(tickangle=-35, tickfont=dict(size=10))
            _fig_m.update_yaxes(title_text="신환자수(명)", title_font=dict(size=10,color=C["t3"]))
            st.plotly_chart(_fig_m, use_container_width=True, key="mon_shin_bar")
            st.markdown("</div>", unsafe_allow_html=True)
    
    # ════════════════════════════════════════════════════════════════
    # [섹션 지역] 월별 지역 비교 분석 (A vs B)
    # ════════════════════════════════════════════════════════════════
    _gap(8)
    import datetime as _dt_mn
    from collections import defaultdict as _ddmn
    _today_mn = _dt_mn.date.today()

    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 월별 지역 비교 분석 (A vs B)",
            "두 달 선택 → 지역별 환자 증감 분석 (V_REGION_DEPT_MONTHLY)", C["indigo"])

    # Oracle CHAR 공백 정규화
    _mn_src = [
        {k: (str(v).strip() if v is not None else "") for k, v in r.items()}
        for r in (region_monthly or [])
    ]
    if len(_mn_src) >= 49000:
        st.warning(f"⚠️ 지역 데이터 행 수({len(_mn_src):,})가 한계에 근접합니다.")

    _mn_today_ym = _today_mn.strftime("%Y%m")
    _mn_months = sorted(
        {r.get("기준월", "") for r in _mn_src
         if r.get("기준월", "").isdigit()
         and len(r.get("기준월", "")) == 6
         and r.get("기준월", "") <= _mn_today_ym},
    )

    if not _mn_src:
        st.warning("⚠️ **V_REGION_DEPT_MONTHLY 데이터 없음** — DBA에게 뷰 생성 요청")
    elif len(_mn_months) < 2:
        st.warning("⚠️ 비교 가능한 월 부족 (최소 2개월 필요)")
    else:
        def _mn_ym(ym: str) -> str:
            return f"{ym[:4]}년 {ym[4:6]}월" if len(ym) == 6 else ym

        _mn_n = len(_mn_months)
        _col_a, _col_b, _col_d, _ = st.columns([3, 3, 3, 3], gap="small")
        with _col_a:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 기준 월 (이전)</div>', unsafe_allow_html=True)
            _mn_a = st.selectbox("A월", options=_mn_months, index=max(0, _mn_n - 2),
                                 format_func=_mn_ym, key="mn_month_a", label_visibility="collapsed")
        with _col_b:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 비교 월 (이후)</div>', unsafe_allow_html=True)
            _mn_b = st.selectbox("B월", options=_mn_months, index=_mn_n - 1,
                                 format_func=_mn_ym, key="mn_month_b", label_visibility="collapsed")
        with _col_d:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">🏥 진료과</div>', unsafe_allow_html=True)
            _mn_dept_opts = ["전체"] + sorted({r.get("진료과명", "") for r in _mn_src if r.get("진료과명", "")})
            _mn_dept = st.selectbox("진료과", options=_mn_dept_opts, index=0,
                                    key="mn_dept", label_visibility="collapsed")

        # ── 데이터 검증 expander ──────────────────────────────────
        with st.expander("🔍 로드 데이터 검증 (DB 쿼리 결과와 비교용)", expanded=False):
            st.caption(f"총 로드 행: {len(_mn_src):,}행 · 조회 가능 월: {', '.join(_mn_months)}")
            _dbg2_dept = st.selectbox("검증 진료과", ["전체"] + sorted({r.get("진료과명","") for r in _mn_src if r.get("진료과명","")}), key="mn_dbg_dept")
            _dbg2: dict = _ddmn(lambda: _ddmn(int))
            for _r in _mn_src:
                if _dbg2_dept != "전체" and _r.get("진료과명","") != _dbg2_dept:
                    continue
                _dbg2[_r.get("기준월","")][_r.get("지역","")] += int(_r.get("환자수",0) or 0)
            _dbg2_ms = sorted(_dbg2.keys())
            if len(_dbg2_ms) >= 2:
                _dd_a, _dd_b = _dbg2_ms[-2], _dbg2_ms[-1]
                _dd_rgs = sorted(set(list(_dbg2[_dd_a].keys()) + list(_dbg2[_dd_b].keys())))
                _dh = (f'<table style="font-size:11px;border-collapse:collapse;width:100%">'
                       f'<tr><th style="border:1px solid #ddd;padding:4px;background:#F8FAFC">지역</th>'
                       f'<th style="border:1px solid #ddd;padding:4px;background:#EEF2FF">{_dd_a[:4]}년{_dd_a[4:]}월(A)</th>'
                       f'<th style="border:1px solid #ddd;padding:4px;background:#EFF6FF">{_dd_b[:4]}년{_dd_b[4:]}월(B)</th>'
                       f'<th style="border:1px solid #ddd;padding:4px;background:#FFF7ED">증감</th></tr>')
                for _rg in _dd_rgs[:50]:
                    _va2 = _dbg2[_dd_a].get(_rg, 0); _vb2 = _dbg2[_dd_b].get(_rg, 0)
                    _vd2 = _vb2 - _va2
                    _c2  = "#DC2626" if _vd2 > 0 else "#1E40AF" if _vd2 < 0 else "#64748B"
                    _dh += (f'<tr><td style="border:1px solid #ddd;padding:3px 6px">{_rg}</td>'
                            f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right">{_va2:,}</td>'
                            f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right">{_vb2:,}</td>'
                            f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right;color:{_c2};font-weight:700">{_vd2:+,}</td></tr>')
                _dh += (f'<tr><td style="border:1px solid #ddd;padding:3px 6px;font-weight:700">합계</td>'
                        f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right;font-weight:700">{sum(_dbg2[_dd_a].values()):,}</td>'
                        f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right;font-weight:700">{sum(_dbg2[_dd_b].values()):,}</td>'
                        f'<td></td></tr></table>')
                st.markdown(_dh, unsafe_allow_html=True)

        if _mn_a == _mn_b:
            st.warning("A와 B에 서로 다른 월을 선택해 주세요.")
        else:
            # ── 집계 ─────────────────────────────────────────────
            def _mn_agg(month: str, dept: str) -> dict:
                agg: dict = _ddmn(int)
                for _r in _mn_src:
                    if _r.get("기준월", "") != month:
                        continue
                    if dept != "전체" and _r.get("진료과명", "") != dept:
                        continue
                    _rg = _r.get("지역", "")
                    if _rg in ("지역미상", "", None):
                        continue
                    agg[_rg] += int(_r.get("환자수", 0) or 0)
                return dict(agg)

            _agg_a = _mn_agg(_mn_a, _mn_dept)
            _agg_b = _mn_agg(_mn_b, _mn_dept)
            _all_rgs = sorted(set(list(_agg_a.keys()) + list(_agg_b.keys())))

            _mn_rows = []
            for _rg in _all_rgs:
                _ca = _agg_a.get(_rg, 0); _cb = _agg_b.get(_rg, 0)
                _diff = _cb - _ca
                _pct6 = round(_diff / max(_ca, 1) * 100, 1)
                _mn_rows.append({"지역": _rg, "A": _ca, "B": _cb, "증감": _diff, "증감률": _pct6})
            _mn_rows.sort(key=lambda x: -x["증감"])

            _tot_a  = sum(_agg_a.values()); _tot_b = sum(_agg_b.values())
            _tot_d  = _tot_b - _tot_a
            _tot_pt = round(_tot_d / max(_tot_a, 1) * 100, 1)
            _inc_n  = sum(1 for r in _mn_rows if r["증감"] > 0)
            _dec_n  = sum(1 for r in _mn_rows if r["증감"] < 0)
            _td_c   = C["red"] if _tot_d > 0 else C["blue"] if _tot_d < 0 else C["t3"]

            # ── KPI 카드 ─────────────────────────────────────────
            _gap(4)
            _k1, _k2, _k3, _k4 = st.columns(4, gap="small")
            _kpi_card(_k1, "📅", _mn_ym(_mn_a), f"{_tot_a:,}", "명", "A 기간 환자수", C["indigo"])
            _kpi_card(_k2, "📅", _mn_ym(_mn_b), f"{_tot_b:,}", "명", "B 기간 환자수", C["blue"])
            _kpi_card(_k3, "📈" if _tot_d >= 0 else "📉", "총 증감",
                      f"{_tot_d:+,}", "명", f"증감률 {_tot_pt:+.1f}%", _td_c)
            _kpi_card(_k4, "🗺️", "증감 지역 현황",
                      f"▲{_inc_n} ▼{_dec_n}", "", f"전체 {len(_mn_rows)}개 지역", C["teal"])
            _gap(8)

            # ── TOP 5 ─────────────────────────────────────────────
            _top5_inc = [r for r in _mn_rows if r["증감"] > 0][:5]
            _top5_dec = sorted([r for r in _mn_rows if r["증감"] < 0], key=lambda x: x["증감"])[:5]

            def _rank_card_mn(col, rows, title, color, is_inc):
                with col:
                    st.markdown(
                        f'<div style="background:#fff;border:1px solid #F0F4F8;'
                        f'border-top:3px solid {color};border-radius:10px;padding:12px 14px;">'
                        f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:8px;">{title}</div>',
                        unsafe_allow_html=True,
                    )
                    if not rows:
                        st.markdown(f'<div style="font-size:12px;color:{C["t3"]};padding:8px 0;">해당 없음</div>', unsafe_allow_html=True)
                    else:
                        _mx = max(abs(r["증감"]) for r in rows) or 1
                        for _ri, _r in enumerate(rows, 1):
                            _bw  = round(abs(_r["증감"]) / _mx * 100)
                            _ico = "▲" if is_inc else "▼"
                            st.markdown(
                                f'<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #F8FAFC;">'
                                f'<span style="font-size:11px;font-weight:700;color:{C["t3"]};min-width:16px;">{_ri}</span>'
                                f'<div style="flex:1;">'
                                f'<div style="font-size:12px;font-weight:600;color:{C["t1"]};">{_r["지역"]}</div>'
                                f'<div style="height:4px;background:#F1F5F9;border-radius:2px;margin-top:3px;overflow:hidden;">'
                                f'<div style="width:{_bw}%;height:100%;background:{color};border-radius:2px;"></div></div></div>'
                                f'<div style="text-align:right;">'
                                f'<div style="font-size:13px;font-weight:800;color:{color};">{_ico}{abs(_r["증감"]):,}명</div>'
                                f'<div style="font-size:10px;color:{C["t3"]};">{_r["증감률"]:+.1f}%</div>'
                                f'</div></div>',
                                unsafe_allow_html=True,
                            )
                    st.markdown("</div>", unsafe_allow_html=True)

            _rc1, _rc2 = st.columns(2, gap="small")
            _rank_card_mn(_rc1, _top5_inc, f"📈 증가 TOP 5 ({_mn_ym(_mn_a)} → {_mn_ym(_mn_b)})", C["red"], True)
            _rank_card_mn(_rc2, _top5_dec, f"📉 감소 TOP 5 ({_mn_ym(_mn_a)} → {_mn_ym(_mn_b)})", C["blue"], False)
            _gap(8)

            # ── 부산/부산외 분리 ──────────────────────────────────
            _busan_rows = [r for r in _mn_rows if r["지역"].startswith("부산")]
            _other_rows = [r for r in _mn_rows if not r["지역"].startswith("부산")]

            def _top_bot5(rows):
                """증감 상위5 + 하위5 반환 (중복 제거, 증감 내림차순)"""
                _top = sorted(rows, key=lambda x: -x["증감"])[:5]
                _bot = sorted(rows, key=lambda x: x["증감"])[:5]
                _seen = set(); _out = []
                for _r in _top + _bot:
                    if _r["지역"] not in _seen:
                        _seen.add(_r["지역"]); _out.append(_r)
                return sorted(_out, key=lambda x: -x["증감"])

            _bs5  = _top_bot5(_busan_rows)
            _ot5  = _top_bot5(_other_rows)

            def _region_table(rows, title, border_color):
                """부산/부산외 분석표 HTML 생성"""
                _TH = "padding:5px 8px;font-size:10px;font-weight:700;color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
                _h = (
                    f'<div style="background:#fff;border:1px solid #F0F4F8;'
                    f'border-top:3px solid {border_color};border-radius:10px;padding:12px 14px;height:100%;">'
                    f'<div style="font-size:12px;font-weight:700;color:{border_color};margin-bottom:8px;">{title}</div>'
                    f'<div style="overflow-x:auto;">'
                    f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
                    f'<thead><tr>'
                    f'<th style="{_TH}text-align:left;">지역</th>'
                    f'<th style="{_TH}text-align:right;color:{C["indigo"]};">A</th>'
                    f'<th style="{_TH}text-align:right;color:{C["blue"]};">B</th>'
                    f'<th style="{_TH}text-align:right;">증감</th>'
                    f'<th style="{_TH}text-align:right;">증감률</th>'
                    f'</tr></thead><tbody>'
                )
                if not rows:
                    _h += f'<tr><td colspan="5" style="padding:12px;text-align:center;color:{C["t3"]};">데이터 없음</td></tr>'
                else:
                    # 상위5 / 구분선 / 하위5 구조
                    _inc = [r for r in rows if r["증감"] > 0]
                    _dec = [r for r in rows if r["증감"] <= 0]
                    for _grp_rows, _grp_bg in [(_inc, "#FFF1F2"), (_dec, "#EFF6FF")]:
                        if _grp_rows:
                            _grp_clr = C["red"] if _grp_bg == "#FFF1F2" else C["blue"]
                            _grp_lbl = "▲ 증가" if _grp_bg == "#FFF1F2" else "▼ 감소"
                            _h += (f'<tr><td colspan="5" style="padding:3px 8px;background:{_grp_bg}20;'
                                   f'font-size:10px;font-weight:700;color:{_grp_clr};'
                                   f'border-bottom:1px solid {_grp_bg};">{_grp_lbl}</td></tr>')
                            for _r in _grp_rows:
                                _d = _r["증감"]; _p = _r["증감률"]
                                _c = C["red"] if _d > 0 else C["blue"] if _d < 0 else C["t3"]
                                _ico = "▲" if _d > 0 else "▼" if _d < 0 else "─"
                                # 지역명에서 "부산광역시 " 접두어 제거해 표시 간결화
                                _rg_short = _r["지역"].replace("부산광역시 ", "").replace("경상남도 ", "경남 ").replace("경상북도 ", "경북 ")
                                _h += (
                                    f'<tr style="border-bottom:1px solid #F1F5F9;">'
                                    f'<td style="padding:4px 8px;font-weight:600;" title="{_r["지역"]}">{_rg_short}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;font-family:Consolas,monospace;">{_r["A"]:,}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;font-family:Consolas,monospace;">{_r["B"]:,}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;font-weight:700;color:{_c};font-family:Consolas,monospace;">{_ico}{abs(_d):,}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;color:{_c};">{_p:+.1f}%</td>'
                                    f'</tr>'
                                )
                _h += "</tbody></table></div></div>"
                return _h

            st.markdown(
                f'<div style="font-size:13px;font-weight:700;color:{C["teal"]};margin-bottom:6px;">'
                f'📋 지역별 환자수 분석표 · {_mn_ym(_mn_a)} vs {_mn_ym(_mn_b)}'
                + (f'  <span style="font-size:11px;font-weight:400;color:{C["t3"]};">(진료과: {_mn_dept})</span>' if _mn_dept != "전체" else "")
                + '</div>',
                unsafe_allow_html=True,
            )
            _tbl_c1, _tbl_c2 = st.columns(2, gap="small")
            with _tbl_c1:
                st.markdown(_region_table(_bs5,  f"🏙️ 부산광역시 내 상위5·하위5", C["teal"]),   unsafe_allow_html=True)
            with _tbl_c2:
                st.markdown(_region_table(_ot5, f"🗺️ 부산 외 지역 상위5·하위5", C["orange"]), unsafe_allow_html=True)
            _gap(8)

            # ── 발산 가로 막대 차트 (부산/부산외 2열) ────────────
            if HAS_PLOTLY and _mn_rows:
                def _divbar_fig(rows, title, key):
                    if not rows:
                        return None
                    _viz = sorted(rows, key=lambda x: x["증감"])
                    _l = [r["지역"].replace("부산광역시 ", "").replace("경상남도 ", "경남 ").replace("경상북도 ", "경북 ")
                          for r in _viz]
                    _d = [r["증감"] for r in _viz]
                    _p = [r["증감률"] for r in _viz]
                    _c = [C["red"] if v > 0 else C["blue"] if v < 0 else C["t3"] for v in _d]
                    _fig = go.Figure(go.Bar(
                        x=_d, y=_l, orientation="h",
                        marker=dict(color=_c, line=dict(color="rgba(0,0,0,0)")),
                        text=[f"{v:+,}({q:+.1f}%)" for v, q in zip(_d, _p)],
                        textposition="outside", textfont=dict(size=9, color=C["t2"]),
                        hovertemplate=[
                            f"<b>{r['지역']}</b><br>A: {r['A']:,}명 → B: {r['B']:,}명<br>"
                            f"증감: {r['증감']:+,}명 ({r['증감률']:+.1f}%)<extra></extra>"
                            for r in _viz
                        ],
                        customdata=[r["지역"] for r in _viz],
                    ))
                    _fig.add_vline(x=0, line=dict(color=C["t3"], width=1.5, dash="dash"))
                    _fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#333333", size=11),
                        height=max(260, len(_l) * 26 + 60),
                        margin=dict(l=0, r=110, t=30, b=8),
                        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
                        showlegend=False, bargap=0.3,
                    )
                    _fig.update_xaxes(title_text="증감 환자수(명)", title_font=dict(size=10, color=C["t3"]),
                                      gridcolor="#F1F5F9", zeroline=False, tickfont=dict(size=10))
                    _fig.update_yaxes(tickfont=dict(size=10), gridcolor="#F1F5F9")
                    return _fig

                _bs_viz = _top_bot5(_busan_rows)
                _ot_viz = _top_bot5(_other_rows)
                _ch1, _ch2 = st.columns(2, gap="small")
                with _ch1:
                    _f1 = _divbar_fig(_bs_viz,  f"🏙️ 부산 증감 · {_mn_ym(_mn_a)}→{_mn_ym(_mn_b)}", "mn_dv_busan")
                    if _f1: st.plotly_chart(_f1, use_container_width=True, key="mn_dv_busan")
                with _ch2:
                    _f2 = _divbar_fig(_ot_viz, f"🗺️ 부산 외 증감 · {_mn_ym(_mn_a)}→{_mn_ym(_mn_b)}", "mn_dv_other")
                    if _f2: st.plotly_chart(_f2, use_container_width=True, key="mn_dv_other")
                _gap(4)

                # ── A vs B 묶음 가로 막대 ───────────────────────
                _gb2    = sorted(_mn_rows, key=lambda x: -abs(x["증감"]))[:12]
                _gb2    = sorted(_gb2, key=lambda x: x["증감"])
                if _gb2:
                    _gb2_l  = [r["지역"] for r in _gb2]
                    _gb2_a  = [r["A"] for r in _gb2]
                    _gb2_b  = [r["B"] for r in _gb2]
                    _b2c    = C["red"] if _tot_d >= 0 else C["blue"]
                    _b2cl   = C["red_l"] if _tot_d >= 0 else C["blue_l"]
                    _fig_gb2 = go.Figure()
                    _fig_gb2.add_trace(go.Bar(
                        name=f"A · {_mn_ym(_mn_a)} (기준)", y=_gb2_l, x=_gb2_a, orientation="h",
                        marker_color=C["indigo_l"], marker=dict(line=dict(color=C["indigo"], width=0.8)),
                        hovertemplate="%{y}<br>A(%{x:,}명)<extra></extra>",
                    ))
                    _fig_gb2.add_trace(go.Bar(
                        name=f"B · {_mn_ym(_mn_b)} (비교)", y=_gb2_l, x=_gb2_b, orientation="h",
                        marker_color=_b2cl, marker=dict(line=dict(color=_b2c, width=0.8)),
                        hovertemplate="%{y}<br>B(%{x:,}명)<extra></extra>",
                    ))
                    _fig_gb2.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#333333", size=11), barmode="group",
                        height=max(340, len(_gb2) * 36 + 90),
                        margin=dict(l=0, r=60, t=38, b=8),
                        title=dict(text=f"지역별 A vs B 비교 · 증감 상위 {len(_gb2)}개 ({_mn_ym(_mn_a)} vs {_mn_ym(_mn_b)})",
                                   font=dict(size=12, color=C["t2"]), x=0),
                        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center",
                                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                        bargap=0.2, bargroupgap=0.05,
                    )
                    _fig_gb2.update_xaxes(title_text="환자수(명)", title_font=dict(size=10, color=C["t3"]),
                                         gridcolor="#F1F5F9", zeroline=False, tickfont=dict(size=10))
                    _fig_gb2.update_yaxes(tickfont=dict(size=10), gridcolor="#F1F5F9")
                    st.plotly_chart(_fig_gb2, use_container_width=True, key="mn_grouped")

            # ── 자동 인사이트 ─────────────────────────────────────
            _gap(4)
            _ti = _top5_inc[0] if _top5_inc else None
            _td_item = _top5_dec[0] if _top5_dec else None
            _arr  = "▲" if _tot_d >= 0 else "▼"
            _ins_mn = [(
                "📊 전체 요약",
                f"{_mn_ym(_mn_a)} <b>{_tot_a:,}명</b> → {_mn_ym(_mn_b)} <b>{_tot_b:,}명</b> "
                f"({_arr} {abs(_tot_d):,}명, {_tot_pt:+.1f}%)<br>증가 {_inc_n}개 / 감소 {_dec_n}개 지역",
                _td_c,
            )]
            if _ti:
                _ins_mn.append(("📈 최대 증가", f"<b>{_ti['지역']}</b> {_ti['A']:,} → {_ti['B']:,}명 (▲{_ti['증감']:,}명, {_ti['증감률']:+.1f}%)", C["red"]))
            if _td_item:
                _ins_mn.append(("📉 최대 감소", f"<b>{_td_item['지역']}</b> {_td_item['A']:,} → {_td_item['B']:,}명 (▼{abs(_td_item['증감']):,}명, {_td_item['증감률']:+.1f}%)", C["blue"]))
            _rapid_mn = [r for r in _mn_rows if abs(r["증감률"]) >= 50 and r["A"] >= 5]
            if _rapid_mn:
                _ins_mn.append(("🚨 급변 지역",
                    "<br>".join(f"{'🔴' if r['증감']>0 else '🔵'} <b>{r['지역']}</b> {r['증감률']:+.1f}% ({r['A']:,} → {r['B']:,}명)" for r in _rapid_mn[:4]),
                    C["violet"]))
            _ins_cols = st.columns(2, gap="small")
            for _ii, (_it, _ib, _ic) in enumerate(_ins_mn):
                with _ins_cols[_ii % 2]:
                    st.markdown(
                        f'<div style="background:#fff;border:1px solid #F0F4F8;border-left:4px solid {_ic};'
                        f'border-radius:8px;padding:10px 14px;margin-bottom:8px;">'
                        f'<div style="font-size:11.5px;font-weight:700;color:{_ic};margin-bottom:5px;">{_it}</div>'
                        f'<div style="font-size:12px;color:{C["t2"]};line-height:1.6;">{_ib}</div></div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("</div>", unsafe_allow_html=True)
    _gap()


# ════════════════════════════════════════════════════════════════════
# AI 채팅 분석  (기존 그대로)
# ════════════════════════════════════════════════════════════════════
def _render_finance_llm_chat(bed_detail=None, dept_status=None, kiosk_by_dept=None,
                              daily_dept_stat=None, kiosk_counter_trend=None,
                              discharge_pipe=None, kiosk_status=None):
    import json as _json, uuid as _uuid
    bed_detail          = bed_detail          or []
    dept_status         = dept_status         or []
    kiosk_by_dept       = kiosk_by_dept       or []
    daily_dept_stat     = daily_dept_stat     or []
    kiosk_counter_trend = kiosk_counter_trend or []
    discharge_pipe      = discharge_pipe      or []

    _stay      = sum(int(r.get("재원수",   0) or 0) for r in bed_detail)
    _adm       = sum(int(r.get("금일입원", 0) or 0) for r in bed_detail)
    _disc      = sum(int(r.get("금일퇴원", 0) or 0) for r in bed_detail)
    _total_bed = sum(int(r.get("총병상",   0) or 0) for r in bed_detail)
    _rest      = max(0, _total_bed - _stay)
    _occ       = round(_stay/max(_total_bed,1)*100, 1)
    _ndc       = sum(int(r.get("익일퇴원예약", 0) or 0) for r in bed_detail)
    _wait      = sum(int(r.get("대기",   0) or 0) for r in dept_status)
    _proc      = sum(int(r.get("진료중", 0) or 0) for r in dept_status)
    _done      = sum(int(r.get("완료",   0) or 0) for r in dept_status)
    _k_tot     = sum(int(r.get("수납건수", 0) or 0) for r in kiosk_by_dept)
    _k_amt     = sum(int(r.get("수납금액", 0) or 0) for r in kiosk_by_dept)

    from collections import defaultdict as _ddd_c
    _ds_cat: dict = _ddd_c(lambda: _ddd_c(int))
    for _r in daily_dept_stat:
        _ds_cat[_r.get("구분","")][_r.get("보험구분","기타")] += int(_r.get("건수",0) or 0)
    _pipe: dict = {}
    for _r in discharge_pipe:
        _s = _r.get("단계",""); _n = int(_r.get("환자수",0) or 0)
        if _s: _pipe[_s] = _pipe.get(_s,0) + _n
    _kc_summary = [{"날짜":str(r.get("기준일",""))[:10],"키오스크":r.get("키오스크건수"),"창구":r.get("창구건수")}
                   for r in kiosk_counter_trend[-7:]]
    _ctx = {
        "기준시각": time.strftime("%Y-%m-%d %H:%M"),
        "병동_현황": {"금일입원":_adm,"금일퇴원":_disc,"재원수":_stay,"총병상":_total_bed,
                      "잔여병상":_rest,"가동률":f"{_occ}%","익일퇴원예정":_ndc,
                      "병동별":[{"병동":r.get("병동명"),"재원":r.get("재원수"),"가동률":r.get("가동률")} for r in bed_detail[:12]]},
        "외래_현황": {"대기":_wait,"진료중":_proc,"완료":_done,"합계":_wait+_proc+_done,
                      "진료과별":[{"진료과":r.get("진료과명"),"대기":r.get("대기"),"완료":r.get("완료"),"평균대기(분)":r.get("평균대기시간")}
                                  for r in sorted(dept_status,key=lambda x:-int(x.get("대기",0) or 0))[:12]]},
        "일일현황_보험구분": {cat: dict(v) for cat,v in _ds_cat.items()},
        "키오스크_수납": {"총건수":_k_tot,"총금액(만원)":_k_amt//10000,
                          "진료과별":[{"진료과":r.get("진료과명"),"건수":r.get("수납건수"),"금액(만원)":int(r.get("수납금액",0) or 0)//10000} for r in kiosk_by_dept[:10]],
                          "7일_추세":_kc_summary},
        "퇴원_파이프라인": _pipe,
    }
    _sys_prompt = (
        "당신은 병원 원무팀 업무 지원 AI입니다.\n"
        "반드시 아래 [현재 대시보드 데이터]만 근거로 답변하세요. 데이터에 없는 내용은 추측하지 마세요.\n"
        "핵심 수치는 **굵게**, 위험/주의는 🔴, 정상은 🟢, 권장 조치는 ✅ 로 표시하세요.\n"
        "개인 환자 정보(환자명, 주민번호, 카드번호 등)는 절대 언급하지 마세요.\n\n"
        f"## [현재 대시보드 데이터] — {time.strftime('%Y-%m-%d %H:%M')} 기준\n"
        f"```json\n{_json.dumps(_ctx, ensure_ascii=False, indent=2)[:6000]}\n```"
    )
    if "fn_chat_history" not in st.session_state:
        st.session_state["fn_chat_history"] = []
    _history = st.session_state["fn_chat_history"]
    st.markdown(
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:14px 16px;margin-top:4px;">',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="font-size:16px;">🤖</span>'
        '<span style="font-size:13px;font-weight:700;color:#0F172A;">AI 원무 분석 채팅</span></div>',
        unsafe_allow_html=True,
    )
    _quick = [
        ("외래 혼잡도", "현재 외래 진료과별 대기 현황을 분석하고 혼잡한 진료과 조치 방안을 알려주세요."),
        ("키오스크 현황", f"오늘 키오스크 수납 {_k_tot}건 현황을 분석하고 창구 부담 현황을 알려주세요."),
        ("입퇴원 분석",  f"금일 입원 {_adm}명·퇴원 {_disc}명·재원 {_stay}명 현황을 분석해주세요."),
        ("운영 요약",    "오늘 원무 전체 운영 현황을 3줄로 요약해주세요."),
    ]
    _qcols = st.columns(len(_quick), gap="small")
    for _qi, (_ql, _qv) in enumerate(_quick):
        with _qcols[_qi]:
            if st.button(_ql, key=f"fn_qs_{_qi}", use_container_width=True, type="secondary"):
                st.session_state["fn_chat_prefill"] = _qv; st.rerun()
    for _msg in _history:
        with st.chat_message(_msg["role"]): st.markdown(_msg["content"])
    _prefill  = st.session_state.pop("fn_chat_prefill", None)
    _user_in  = st.chat_input("원무 현황에 대해 질문하세요", key="fn_chat_input") or _prefill
    if _user_in:
        with st.chat_message("user"): st.markdown(_user_in)
        _history.append({"role":"user","content":_user_in})
        with st.chat_message("assistant"):
            _ph = st.empty(); _toks: list = []; _full = ""
            try:
                from core.llm import get_llm_client
                _llm = get_llm_client()
                _safe_p = _sys_prompt[:4000]+"...(생략)" if len(_sys_prompt)>4000 else _sys_prompt
                for _tok in _llm.generate_stream(_user_in, _safe_p, request_id=_uuid.uuid4().hex[:8]):
                    _toks.append(_tok)
                    if len(_toks)%4==0: _ph.markdown("".join(_toks)+"▌")
                _full = "".join(_toks)
            except Exception as _e:
                _full = (f"**LLM 연결 실패**\n\n`{_e}`\n\n"
                         f"현재 데이터: 재원 **{_stay}명** / 외래대기 **{_wait}명** / 키오스크수납 **{_k_tot}건**")
            _ph.markdown(_full)
        _history.append({"role":"assistant","content":_full})
        st.session_state["fn_chat_history"] = _history; st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 세부과 일일집계표  (기존 그대로)
# ════════════════════════════════════════════════════════════════════
def _render_day_inweon(day_inweon: list) -> None:
    _TH = ("padding:6px 8px;font-size:11px;font-weight:700;"
           "color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;")
    _group_html = (
        f'<th style="{_TH}text-align:left;" rowspan="2">진료과</th>'
        f'<th style="{_TH}text-align:right;color:{C["blue"]};" rowspan="2">외래계</th>'
        f'<th style="{_TH}text-align:right;color:{C["indigo"]};" rowspan="2">입원계</th>'
        f'<th style="{_TH}text-align:right;color:{C["t2"]};" rowspan="2">퇴원계</th>'
        f'<th style="{_TH}text-align:right;color:{C["violet"]};" rowspan="2">재원계</th>'
        f'<th colspan="5" style="{_TH}text-align:center;color:{C["teal"]};">예방접종</th>'
    )
    _sub_html = (
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">독감</th>'
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">AZ·JS·NV</th>'
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">MD</th>'
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">FZ</th>'
        f'<th style="{_TH}text-align:right;color:{C["green"]};font-weight:800;">소계</th>'
    )
    _rows_html = ""
    for _i, _r in enumerate(day_inweon):
        _dept     = str(_r.get("진료과",""))
        _dept_t   = _dept.strip()
        _is_total = (_dept_t == "총합계")
        _is_group = _dept_t.startswith("*")
        _dept_disp= _dept_t.lstrip("*").strip() if _is_group else _dept_t
        if _is_total:
            _bg  = "#EFF6FF"
            _td  = f"padding:6px 8px;background:{_bg};border-top:2px solid #BFDBFE;font-weight:800;font-size:12.5px;font-family:Consolas,monospace;text-align:right;"
            _dept_td = _td.replace("text-align:right;","text-align:left;") + f"color:#1E40AF;font-family:inherit;"
        elif _is_group:
            _bg  = "#F0F4FF"
            _td  = f"padding:5px 8px;background:{_bg};border-bottom:1px solid #E2E8F0;font-size:12px;font-family:Consolas,monospace;text-align:right;font-weight:700;"
            _dept_td = _td.replace("text-align:right;","text-align:left;") + f"color:{C['blue']};font-family:inherit;padding-left:8px;"
        else:
            _bg  = "#F8FAFC" if _i%2==0 else "#FFFFFF"
            _td  = f"padding:5px 8px;background:{_bg};border-bottom:1px solid #F1F5F9;font-size:12px;font-family:Consolas,monospace;text-align:right;"
            _dept_td = _td.replace("text-align:right;","text-align:left;") + "color:#334155;font-family:inherit;padding-left:18px;"
        def _fmt(key):
            v = _r.get(key)
            if v is None: return "─"
            try:
                n = int(str(v).replace(",",""))
                return "─" if n==0 else f"{n:,}"
            except: return str(v) if str(v).strip() else "─"
        _rows_html += (
            f"<tr><td style='{_dept_td}'>{_dept_disp}</td>"
            f'<td style="{_td}color:{C["blue"]};">{_fmt("외래계")}</td>'
            f'<td style="{_td}color:{C["indigo"]};">{_fmt("입원계")}</td>'
            f'<td style="{_td}color:{C["t2"]};">{_fmt("퇴원계")}</td>'
            f'<td style="{_td}color:{C["violet"]};">{_fmt("재원계")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(독감)")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(AZ,JS,NV)")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(MD)")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(FZ)")}</td>'
            f'<td style="{_td}color:{C["green"]};font-weight:{"800" if _is_total or _is_group else "600"};">'
            f'{_fmt("예방주사계")}</td></tr>'
        )
    _today = time.strftime("%Y.%m.%d")
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">'
        f'<div class="wd-sec"><span class="wd-sec-bar" style="background:{C["blue"]};"></span>'
        f'세부과 일일집계표<span class="wd-sec-sub"> {_today} 기준</span></div>',
        unsafe_allow_html=True,
    )
    if day_inweon:
        st.markdown(
            f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>{_group_html}</tr><tr>{_sub_html}</tr></thead>'
            f'<tbody>{_rows_html}</tbody></table></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #F1F5F9;">'
            f'<span style="font-size:10px;color:#64748B;">📌 * 표시: 하위 진료과 합산 그룹</span>'
            f'<span style="font-size:10px;color:{C["blue"]};">■ 외래</span>'
            f'<span style="font-size:10px;color:{C["indigo"]};">■ 입원</span>'
            f'<span style="font-size:10px;color:{C["violet"]};">■ 재원</span>'
            f'<span style="font-size:10px;color:{C["teal"]};">■ 예방접종</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div style="padding:28px;text-align:center;color:#94A3B8;font-size:13px;">V_DAY_INWEON_3 데이터 없음</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    return

    # ── 격자 Z 행렬 구성
    _max_col = max(c for c, r in grid_dict.values())
    _max_row = max(r for c, r in grid_dict.values())

    # float('nan') = 빈 셀 (투명)
    _z    = [[float("nan")] * (_max_col + 1) for _ in range(_max_row + 1)]
    _text = [[""] * (_max_col + 1) for _ in range(_max_row + 1)]

    for _nm, (_col, _row) in grid_dict.items():
        _c = _cnt.get(_nm, 0)
        _z[_row][_col]    = float(_c)
        _text[_row][_col] = f"{_nm}<br>{_c:,}명"

    # NaN 셀 → 0으로 처리하되 텍스트는 비워두기
    # (colorscale 에서 0 = 가장 연한 색 → 빈 셀처럼 보임)
    # 실제로 NaN은 투명하게 처리됨

    _max_v = max(_cnt.values()) if _cnt else 1

    _fig = go.Figure(go.Heatmap(
        z=_z,
        text=_text,
        texttemplate="%{text}",
        textfont=dict(size=9, color="#1E293B"),
        colorscale=colorscale,
        zmin=0,
        zmax=_max_v,
        showscale=True,
        hovertemplate="%{text}<extra></extra>",
        xgap=4,
        ygap=4,
        colorbar=dict(
            title=dict(text="환자수", font=dict(size=11)),
            thickness=13,
            len=0.75,
            tickformat=",",
            tickfont=dict(size=10),
        ),
    ))

    _fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=350,
        margin=dict(l=0, r=0, t=4, b=0),
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False, autorange="reversed"),
    )

    st.plotly_chart(_fig, use_container_width=True, key=chart_key)

    # ── 구군 순위 보조 바 (TOP 12)
    _sorted_cnt = sorted(_cnt.items(), key=lambda x: -x[1])
    _max_bar    = _sorted_cnt[0][1] if _sorted_cnt else 1
    _medals     = ["🥇", "🥈", "🥉"]
    _bar_html   = (
        '<div style="display:flex;flex-wrap:wrap;gap:5px 16px;'
        'margin-top:8px;padding-top:8px;border-top:1px solid #F1F5F9;">'
    )
    for _i, (_gn, _gc) in enumerate(_sorted_cnt[:12]):
        _pct_b = round(_gc / max(_max_bar, 1) * 100)
        _md = _medals[_i] if _i < 3 else (
            f'<span style="font-size:10px;color:#94A3B8;font-weight:700;">{_i+1}</span>'
        )
        _bar_html += (
            f'<div style="display:flex;align-items:center;gap:5px;'
            f'min-width:186px;flex:1 0 186px;">'
            f'<div style="width:22px;text-align:center;">{_md}</div>'
            f'<div style="width:52px;font-size:11px;font-weight:600;color:#334155;'
            f'white-space:nowrap;">{_gn}</div>'
            f'<div style="flex:1;height:8px;background:#F1F5F9;border-radius:4px;overflow:hidden;">'
            f'<div style="width:{_pct_b}%;height:100%;background:{color_main};'
            f'border-radius:4px;opacity:0.78;"></div></div>'
            f'<div style="width:44px;font-size:11px;font-family:Consolas;'
            f'font-weight:700;color:{color_main};text-align:right;">{_gc:,}</div>'
            f'</div>'
        )
    _bar_html += "</div>"
    st.markdown(_bar_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
# 지역 지도 시각화 — folium 버전 (외부 인터넷 연결 필요)
# pip install streamlit-folium folium
# ════════════════════════════════════════════════════════════════════
from collections import defaultdict as _ddm   # ← _render_folium_map 에서 사용

try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False


@st.cache_data(ttl=86400, show_spinner=False)
def _load_sigungu_geojson_cached() -> Optional[dict]:
    
    try:
        import requests as _req
        _r = _req.get(
            "https://raw.githubusercontent.com/southkorea/"
            "southkorea-maps/master/kostat/2013/json/skorea_municipalities_geo.json",
            timeout=10,
        )
        _r.raise_for_status()
        return _r.json()
    except Exception as _e:
        logger.warning(f"[GeoJSON] 로드 실패: {_e}")
        return None

    # ❗ 최종 fallback (로컬 파일)
    try:
        with open("data/sigungu.geojson", "r", encoding="utf-8") as f:
            logger.warning("[GeoJSON] 로컬 파일로 fallback")
            return json.load(f)
    except Exception as e:
        logger.error(f"[GeoJSON] 로컬 fallback 실패: {e}")
        return None

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _interpolate_color(t: float, stops: list) -> str:
    for i in range(len(stops) - 1):
        p0, c0 = stops[i];  p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            lt = (t - p0) / (p1 - p0) if p1 > p0 else 0
            r0,g0,b0 = _hex_to_rgb(c0);  r1,g1,b1 = _hex_to_rgb(c1)
            return f"#{int(r0+(r1-r0)*lt):02X}{int(g0+(g1-g0)*lt):02X}{int(b0+(b1-b0)*lt):02X}"
    return stops[-1][1]

# 이 파일의 내용으로 finance_dashboard.py 의 _render_folium_map 함수 전체를 교체하세요.
# (함수 시작 def _render_folium_map( 부터 마지막 st.markdown('</div>') 까지)
# ════════════════════════════════════════════════════════════════════
# 부산 / 경남 구군명 목록 — GeoJSON 코드 기반 필터 대체
# ════════════════════════════════════════════════════════════════════
_BUSAN_DISTRICTS: set = {
    "중구","서구","동구","영도구","부산진구","동래구",
    "남구","북구","해운대구","사하구","금정구","강서구",
    "연제구","수영구","사상구","기장군",
}
_GYEONGNAM_DISTRICTS: set = {
    "창원시","진주시","통영시","사천시","김해시","밀양시",
    "거제시","양산시","의령군","함안군","창녕군","고성군",
    "남해군","하동군","산청군","함양군","거창군","합천군",
}


def _render_folium_map(
    region_data: list,
    sig_cd_prefix: str,          # 사용 안 함(하위 호환 유지용)
    title: str,
    color_main: str,
    color_stops: list,
    center: list,
    zoom_start: int,
    chart_key: str,
    height: int = 440,
    district_set: set = None,    # _BUSAN_DISTRICTS 또는 _GYEONGNAM_DISTRICTS
) -> None:
    """
    Folium 단계구분도 v4 — 구군명 목록 기반 필터링.

    GeoJSON 내부 코드(3738 등 순번)가 행정코드가 아닌 경우에도
    district_set 로 원하는 구군만 정확히 추출합니다.
    """
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {color_main};">',
        unsafe_allow_html=True,
    )
    _sec_hd(title, "클릭 → 팝업(환자수·점유율) · 색상 강도 = 환자수", color_main)

    if not HAS_FOLIUM:
        st.warning("streamlit-folium 미설치: `pip install streamlit-folium folium`")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _raw_geojson = _load_sigungu_geojson_cached()
    if _raw_geojson is None:
        st.error("GeoJSON 로드 실패 — 인터넷 연결 확인")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── 속성 필드 자동 감지 (이름 컬럼)
    _p0 = (_raw_geojson.get("features") or [{}])[0].get("properties", {})
    _name_key = next(
        (k for k in ("SIG_KOR_NM", "name", "NM", "adm_nm", "sggnm") if k in _p0),
        None,
    )
    if not _name_key:
        st.error(f"GeoJSON 이름 필드 감지 실패. 속성: {list(_p0.keys())[:10]}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    def _prop_name(f: dict) -> str:
        return str(f.get("properties", {}).get(_name_key, "") or "").strip()

    # ── district_set 으로 feature 필터
    _target = district_set or _BUSAN_DISTRICTS
    _features = [f for f in _raw_geojson.get("features", [])
                 if _prop_name(f) in _target]

    if not _features:
        st.warning("GeoJSON에서 해당 구군을 찾지 못했습니다.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _geojson = {"type": "FeatureCollection", "features": _features}

    # ── DB 데이터 집계
    _registered = {_prop_name(f) for f in _features}
    _cnt: dict = _ddm(int)
    for _r in region_data:
        _rg  = str(_r.get("지역", "") or "").strip()
        _val = int(_r.get("환자수", 0) or 0)
        if not _rg:
            continue
        _gu = _rg.rsplit(" ", 1)[-1]   # "부산광역시 해운대구" → "해운대구"
        if _gu in _registered:
            _cnt[_gu] += _val

    if not _cnt:
        st.info("해당 진료과·기간의 지역 데이터 없음")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _total     = sum(_cnt.values()) or 1
    _max_v     = max(_cnt.values())
    _sorted_rg = sorted(_cnt.items(), key=lambda x: -x[1])

    # ── Folium 지도
    _m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles="CartoDB positron",
        prefer_canvas=True,
    )

    def _style_fn(feature):
        _t = _cnt.get(_prop_name(feature), 0) / _max_v if _max_v > 0 else 0
        return {
            "fillColor":   _interpolate_color(_t, color_stops),
            "color":       "white",
            "weight":      1.5,
            "fillOpacity": 0.82,
        }

    def _highlight_fn(feature):
        return {"fillColor": color_main, "color": "#334155",
                "weight": 2.5, "fillOpacity": 0.95}

    folium.GeoJson(
        _geojson,
        style_function=_style_fn,
        highlight_function=_highlight_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=[_name_key], aliases=["구군:"],
            style=(
                "background-color:white;color:#0F172A;"
                "font-family:'Malgun Gothic',sans-serif;"
                "font-size:12px;font-weight:700;padding:4px 8px;"
            ),
        ),
    ).add_to(_m)

    for _f in _features:
        _nm   = _prop_name(_f)
        _v    = _cnt.get(_nm, 0)
        _pct  = round(_v / _total * 100, 1)
        _rank = next((i+1 for i,(k,_) in enumerate(_sorted_rg) if k == _nm), "─")
        _popup_html = (
            f'<div style="font-family:Malgun Gothic,sans-serif;min-width:160px;padding:4px;">'
            f'<div style="font-size:14px;font-weight:800;color:{color_main};'
            f'border-bottom:2px solid {color_main};padding-bottom:4px;margin-bottom:8px;">📍 {_nm}</div>'
            f'<table style="width:100%;font-size:12px;">'
            f'<tr><td style="color:#64748B;padding:3px 0;">환자수</td>'
            f'<td style="font-weight:700;text-align:right;">{_v:,}명</td></tr>'
            f'<tr><td style="color:#64748B;padding:3px 0;">점유율</td>'
            f'<td style="font-weight:700;color:{color_main};text-align:right;">{_pct}%</td></tr>'
            f'<tr><td style="color:#64748B;padding:3px 0;">순위</td>'
            f'<td style="font-weight:700;text-align:right;">{_rank}위</td></tr>'
            f'</table>'
            f'<div style="margin-top:6px;height:6px;background:#F1F5F9;border-radius:3px;">'
            f'<div style="width:{_pct}%;height:100%;background:{color_main};border-radius:3px;opacity:0.8;"></div>'
            f'</div></div>'
        )
        folium.GeoJson(
            _f, style_function=_style_fn,
            popup=folium.Popup(folium.IFrame(_popup_html, width=190, height=145), max_width=200),
        ).add_to(_m)

    # 범례
    _legend_html = (
        f'<div style="position:fixed;bottom:20px;right:10px;z-index:1000;'
        f'background:white;padding:10px 14px;border-radius:8px;'
        f'border:1px solid #E2E8F0;box-shadow:0 2px 8px rgba(0,0,0,.12);">'
        f'<div style="font-size:11px;font-weight:700;color:{color_main};margin-bottom:6px;">환자수(명)</div>'
    )
    for _li in range(5):
        _t_val = _li / 4
        _lc = _interpolate_color(_t_val, color_stops)
        _legend_html += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">'
            f'<div style="width:16px;height:12px;background:{_lc};border-radius:2px;"></div>'
            f'<span style="font-size:10px;color:#334155;">{int(_max_v*_t_val):,}</span></div>'
        )
    _legend_html += "</div>"
    _m.get_root().html.add_child(folium.Element(_legend_html))

    st_folium(_m, key=chart_key, height=height, width="stretch", returned_objects=[])

    # 순위 바
    _max_bar = _sorted_rg[0][1] if _sorted_rg else 1
    _medals  = ["🥇","🥈","🥉"]
    _bar_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:5px 16px;'
        'margin-top:8px;padding-top:8px;border-top:1px solid #F1F5F9;">'
    )
    for _i, (_gn, _gc) in enumerate(_sorted_rg[:12]):
        _pct_b = round(_gc / max(_max_bar, 1) * 100)
        _share = round(_gc / _total * 100, 1)
        _md = (_medals[_i] if _i < 3
               else f'<span style="font-size:10px;color:#94A3B8;font-weight:700;">{_i+1}</span>')
        _bar_html += (
            f'<div style="display:flex;align-items:center;gap:5px;min-width:200px;flex:1 0 200px;">'
            f'<div style="width:22px;text-align:center;">{_md}</div>'
            f'<div style="width:52px;font-size:11px;font-weight:600;color:#334155;white-space:nowrap;">{_gn}</div>'
            f'<div style="flex:1;height:8px;background:#F1F5F9;border-radius:4px;overflow:hidden;">'
            f'<div style="width:{_pct_b}%;height:100%;background:{color_main};border-radius:4px;opacity:0.78;"></div></div>'
            f'<div style="width:44px;font-size:11px;font-family:Consolas;font-weight:700;'
            f'color:{color_main};text-align:right;">{_gc:,}</div>'
            f'<div style="width:36px;font-size:10px;color:#94A3B8;text-align:right;">{_share}%</div>'
            f'</div>'
        )
    _bar_html += "</div>"
    st.markdown(_bar_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _tab_region(region_data: List[Dict], region_monthly: List[Dict] = None) -> None:
    """
    지역별 환자 통계 탭 v4.
    데이터는 온디맨드 로드 (세션 캐시) — 페이지 로드 시 쿼리 미실행.
    """
    import datetime as _dt_r
    from collections import defaultdict as _ddr

    # ── rgba 헬퍼 (Plotly는 8자리 hex 미지원 → rgba() 사용) ──────────
    def _c(hex_color: str, a: float = 1.0) -> str:
        h = hex_color.lstrip("#")
        r2, g2, b2 = int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r2},{g2},{b2},{a:.2f})" if a < 1.0 else hex_color

    # ── 온디맨드 데이터 로드 (월 지정 조회) ────────────────────────────
    _SESS_D  = "reg_tab_daily"
    _SESS_M  = "reg_tab_monthly"
    _SESS_YM = "reg_tab_loaded_ym"

    # 최근 24개월 목록 (YYYYMM, 최신순)
    _ym_opts: List[str] = []
    _td2 = _dt_r.date.today()
    for _i in range(24):
        _ab = _td2.year * 12 + (_td2.month - 1) - _i
        _ym_opts.append(f"{_ab // 12}{_ab % 12 + 1:02d}")

    # ── 통합 컨트롤 행 (조회월 · 비교월 · 분석기간) ────────────────────
    _PERIOD_MAP = {"한달": 31, "2주일": 14, "1주일": 7}
    _cmp_opts   = ["없음"] + _ym_opts[1:]

    _rc1, _rc2, _rc3, _rc4, _rc5, _rc_sp = st.columns([2, 2, 2, 1, 0.8, 2], gap="small")
    with _rc1:
        st.markdown(
            f'<div style="font-size:10px;color:{C["t3"]};padding-bottom:2px;">📅 조회 월</div>',
            unsafe_allow_html=True,
        )
        _sel_ym = st.selectbox(
            "조회 월", options=_ym_opts,
            format_func=lambda x: f"{x[:4]}-{x[4:]}",
            key="reg_ym_sel", label_visibility="collapsed",
        )
    with _rc2:
        st.markdown(
            f'<div style="font-size:10px;color:{C["t3"]};padding-bottom:2px;">'
            f'📊 비교 월 <span style="opacity:.6;">(선택)</span></div>',
            unsafe_allow_html=True,
        )
        _cmp_raw = st.selectbox(
            "비교 월", options=_cmp_opts,
            format_func=lambda x: x if x == "없음" else f"{x[:4]}-{x[4:]}",
            key="reg_cmp_sel", label_visibility="collapsed",
        )
        _cmp_ym = None if _cmp_raw == "없음" else _cmp_raw
    with _rc3:
        st.markdown(
            f'<div style="font-size:10px;color:{C["t3"]};padding-bottom:2px;">⏱ 분석 기간</div>',
            unsafe_allow_html=True,
        )
        _period_label = st.selectbox(
            "분석 기간", options=list(_PERIOD_MAP.keys()),
            key="reg_period_sel", label_visibility="collapsed",
        )
    with _rc4:
        st.markdown('<div style="height:22px;"></div>', unsafe_allow_html=True)
        _do_load = st.button("🔍 조회", key="reg_load_btn", use_container_width=True)
    _loaded_ym = st.session_state.get(_SESS_YM)
    with _rc5:
        st.markdown('<div style="height:22px;"></div>', unsafe_allow_html=True)
        if _loaded_ym and st.button("🔄", key="reg_refresh_btn", help="다시 조회"):
            for _k in (_SESS_D, _SESS_M, _SESS_YM):
                st.session_state.pop(_k, None)
            st.rerun()

    # ── 이전 달 계산 (일별 비교용)
    def _prev_ym_of(ym: str) -> str:
        _y, _m = int(ym[:4]), int(ym[4:])
        _m -= 1
        if _m == 0:
            _m, _y = 12, _y - 1
        return f"{_y}{_m:02d}"
    _prev_ym = _prev_ym_of(_sel_ym)

    # ── 조회 실행 ─────────────────────────────────────────────────────
    if _do_load:
        with st.spinner(f"{_sel_ym[:4]}-{_sel_ym[4:]} 데이터 조회 중…"):
            try:
                from db.oracle_client import execute_query as _eq
                _rd = _eq(
                    "SELECT 기준일자, 진료과명, 지역, 환자수 "
                    "FROM JAIN_WM.V_REGION_DEPT_DAILY "
                    f"WHERE 기준일자 LIKE '{_sel_ym}%' "
                    f"   OR 기준일자 LIKE '{_prev_ym}%' "
                    "ORDER BY 기준일자 DESC, 진료과명, 환자수 DESC",
                    max_rows=100000,
                ) or []
                _rm = _eq(
                    "SELECT 기준월, 진료과명, 지역, 환자수 "
                    "FROM JAIN_WM.V_REGION_DEPT_MONTHLY "
                    "ORDER BY 기준월 DESC, 진료과명, 환자수 DESC",
                    max_rows=100000,
                ) or []
                st.session_state[_SESS_D]  = _rd
                st.session_state[_SESS_M]  = _rm
                st.session_state[_SESS_YM] = _sel_ym
                st.rerun()
            except Exception as _e:
                st.error(f"조회 오류: {_e}")
        return

    # 로드 안된 상태 → 안내 후 종료
    if not _loaded_ym or _loaded_ym != _sel_ym:
        if _loaded_ym and _loaded_ym != _sel_ym:
            st.caption(
                f"⚠️ 월이 변경됐습니다 — 🔍 조회를 눌러 "
                f"{_sel_ym[:4]}-{_sel_ym[4:]} 데이터를 불러오세요."
            )
        return

    # 세션 캐시에서 데이터 가져오기
    region_data    = st.session_state.get(_SESS_D, []) or []
    region_monthly = st.session_state.get(_SESS_M, []) or []
 
    # ── 배너 (조회된 월 표시)
    _loaded_label = f"{_loaded_ym[:4]}-{_loaded_ym[4:]}" if _loaded_ym else ""
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["teal"]}15,{C["green"]}10);'
        f'border-left:4px solid {C["teal"]};border-radius:0 8px 8px 0;'
        f'padding:8px 16px;margin:4px 0 6px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:16px;">📍</span>'
        f'<div style="flex:1;"><div style="font-size:12px;font-weight:700;color:{C["teal"]};">'
        f'지역별 환자 통계 · {_loaded_label}</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'진료과별 환자 주소지 분포 · 일별 유입 추이 · AI 경영 인사이트</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
 
    # ── VIEW 없음 안내
    if not region_data:
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;'
            f'padding:24px;text-align:center;margin-top:12px;">'
            f'<div style="font-size:32px;margin-bottom:8px;">📋</div>'
            f'<div style="font-size:14px;font-weight:700;color:#92400E;">'
            f'V_REGION_DEPT_DAILY 데이터 없음</div>'
            f'<div style="font-size:12px;color:#B45309;margin-top:6px;line-height:1.8;">'
            f'<b>region_views_daily.sql</b> 을 DBeaver(DBA 계정)에서 실행 후 재시작<br>'
            f'컬럼: 기준일자(YYYYMMDD) / 진료과명 / 지역 / 환자수'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        return
 
    # ── 진료과 목록 구성 (총 환자수 내림차순)
    _dept_total: dict = _ddr(int)
    for _r in region_data:
        _dp  = _r.get("진료과명", "")
        _cnt = int(_r.get("환자수", 0) or 0)
        if _dp:
            _dept_total[_dp] += _cnt
    _all_depts = sorted(_dept_total.keys(), key=lambda d: -_dept_total[d])
 
    # ── 오늘 날짜
    _today = _dt_r.date.today()
 
    # ──────────────────────────────────────────────
    # 진료과 선택 (기간·비교월은 상단 통합 컨트롤 사용)
    # ──────────────────────────────────────────────
    _n_days     = _PERIOD_MAP[_period_label]
    _date_start = f"{_sel_ym}01"
    _date_end   = f"{_sel_ym}{min(_n_days, 31):02d}"

    _c1, _c_sp = st.columns([3, 9], gap="small")
    with _c1:
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">'
            f'🏥 진료과 선택 <span style="color:{C["red"]};">*</span></div>',
            unsafe_allow_html=True,
        )
        _dept_options = ["── 진료과를 선택하세요 ──"] + _all_depts
        _sel_dept = st.selectbox(
            "진료과", options=_dept_options, index=0,
            key="reg_dept_v3", label_visibility="collapsed",
            help="분석할 진료과를 선택하세요",
        )
 
    # ── 미선택 상태 → 진료과 목록 안내
    _is_dept_selected = _sel_dept != "── 진료과를 선택하세요 ──"
 
    if not _is_dept_selected:
        _gap()
        st.markdown(
            f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;'
            f'padding:16px 20px;text-align:center;margin-bottom:12px;">'
            f'<div style="font-size:14px;font-weight:700;color:{C["blue"]};margin-bottom:4px;">'
            f'👆 위에서 진료과를 선택하면 분석이 시작됩니다</div>'
            f'<div style="font-size:11px;color:{C["t3"]};">'
            f'{_sel_ym[:4]}-{_sel_ym[4:]} {_period_label} 기준 / 진료과를 선택하면 상세 분석이 시작됩니다</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
 
        # ── 진료과 환자수 순위 요약 (전체 30일 기준)
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd("🏥 진료과별 환자수 순위", "최근 30일 전체 기준 — 선택 진료과 참고용", C["blue"])
        _TH_D = (
            "padding:6px 10px;font-size:11px;font-weight:700;color:#64748B;"
            "border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        )
        _dept_table = (
            '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
            f'<thead><tr>'
            f'<th style="{_TH_D}text-align:center;width:40px;">순위</th>'
            f'<th style="{_TH_D}text-align:left;">진료과</th>'
            f'<th style="{_TH_D}text-align:right;color:{C["blue"]};">환자수(30일)</th>'
            f'<th style="{_TH_D}">비율</th>'
            f'</tr></thead><tbody>'
        )
        _total_all = sum(_dept_total.values()) or 1
        for _ri, _dp in enumerate(_all_depts[:20], 1):
            _dc = _dept_total.get(_dp, 0)
            _dp_pct = round(_dc / _total_all * 100, 1)
            _rbg    = "#F8FAFC" if _ri % 2 == 0 else "#FFFFFF"
            _td_s   = f"padding:6px 10px;background:{_rbg};border-bottom:1px solid #F1F5F9;font-size:12px;"
            _dept_table += (
                f"<tr>"
                f'<td style="{_td_s}text-align:center;font-weight:700;color:{C["t3"]};">{_ri}</td>'
                f'<td style="{_td_s}font-weight:600;color:{C["t1"]};">{_dp}</td>'
                f'<td style="{_td_s}text-align:right;font-family:Consolas;color:{C["blue"]};font-weight:700;">{_dc:,}</td>'
                f'<td style="{_td_s}"><div style="display:flex;align-items:center;gap:6px;">'
                f'<div style="flex:1;height:6px;background:#F1F5F9;border-radius:3px;overflow:hidden;">'
                f'<div style="width:{_dp_pct}%;height:100%;background:{C["blue"]};border-radius:3px;"></div>'
                f'</div><span style="font-size:10px;color:{C["t3"]};min-width:34px;">{_dp_pct}%</span>'
                f'</div></td>'
                f"</tr>"
            )
        st.markdown(_dept_table + "</tbody></table>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return  # ← 미선택 시 이후 분석 렌더링 중단
 
    # ════════════════════════════════════════════════════════════════
    # 이하: 진료과 선택 완료 상태
    # ════════════════════════════════════════════════════════════════
 
    # ── 기간 및 진료과 필터 (조회월 기준)
    _filtered_data = [
        _r for _r in region_data
        if _r.get("진료과명", "") == _sel_dept
        and _date_start <= str(_r.get("기준일자", "")) <= _date_end
    ]
 
    # ── 지역 집계 (지역미상 분리)
    _region_total: dict = _ddr(int)
    _unknown_total: int = 0
    for _r in _filtered_data:
        _rg  = _r.get("지역", "")
        _cnt = int(_r.get("환자수", 0) or 0)
        if _rg in ("지역미상", "", None):
            _unknown_total += _cnt
        else:
            _region_total[_rg] += _cnt
 
    _total_patients  = sum(_region_total.values()) + _unknown_total
    _known_total     = sum(_region_total.values())
    _unique_regions  = len(_region_total)
    _sorted_regions  = sorted(_region_total.items(), key=lambda x: -x[1])
    _top1_region     = _sorted_regions[0][0] if _sorted_regions else "─"
    _top1_cnt        = _sorted_regions[0][1] if _sorted_regions else 0
    _top1_dependency = round(_top1_cnt / max(_known_total, 1) * 100, 1)
 
    # ── KPI 4개
    _gap()
    _dep_color = C["red"] if _top1_dependency >= 60 else C["yellow"] if _top1_dependency >= 40 else C["green"]
    _kk1, _kk2, _kk3, _kk4 = st.columns(4, gap="small")
    _kpi_card(_kk1, "👥", f"총 환자수 ({_period_label})",
              f"{_total_patients:,}", "명",
              f"지역미상 {_unknown_total:,}명 포함", C["teal"])
    _kpi_card(_kk2, "📍", "유입 지역 수",
              f"{_unique_regions:,}", "개 시구", "지역미상 제외 기준", C["green"])
    _kk3.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid {_dep_color};">'
        f'<div class="fn-kpi-icon">🏆</div>'
        f'<div class="fn-kpi-label">1위 지역</div>'
        f'<div style="font-size:15px;font-weight:800;color:{_dep_color};line-height:1.3;margin:2px 0;">'
        f'{_top1_region[:10] if len(_top1_region) > 10 else _top1_region}</div>'
        f'<div style="font-size:11px;color:{C["t3"]};">{_top1_cnt:,}명</div>'
        f'<div class="goal-bar-wrap"><div class="goal-bar-fill" '
        f'style="width:{_top1_dependency}%;background:{_dep_color};"></div></div>'
        f'<div style="font-size:10px;color:{_dep_color};font-weight:700;">'
        f'점유율 {_top1_dependency}% '
        f'{"⚠️ 의존도 높음" if _top1_dependency >= 60 else "주의" if _top1_dependency >= 40 else "✅ 양호"}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    _kpi_card(_kk4, "📅", "분석 기간",
              _period_label, "",
              f"{_sel_ym[:4]}-{_sel_ym[4:]}  {_date_start[6:]}일~{_date_end[6:]}일", C["indigo"])
    _gap()
 
    # ── 지역미상 경고
    if _unknown_total > 0:
        _unk_pct = round(_unknown_total / max(_total_patients, 1) * 100, 1)
        _unk_c   = C["red"] if _unk_pct >= 20 else C["yellow"]
        st.markdown(
            f'<div style="background:{_unk_c}18;border:1px solid {_unk_c}55;border-radius:8px;'
            f'padding:8px 14px;margin-bottom:8px;display:flex;align-items:center;gap:10px;">'
            f'<span>⚠️</span>'
            f'<span style="font-size:12px;font-weight:700;color:{_unk_c};">'
            f'지역미상 {_unknown_total:,}명 ({_unk_pct}%) — 우편번호 미기재 또는 POSTNO 미매핑</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
 
    # ══════════════════════════════════════
    # [섹션1] 좌: 지역 수평 바 TOP15  |  우: 일별 트렌드 라인
    # ══════════════════════════════════════
    _col_bar, _col_line = st.columns([1, 1], gap="small")
 
    with _col_bar:
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"📊 {_sel_dept} — 지역별 환자 순위 TOP15",
                f"{_period_label} 합산", C["blue"])
        if _sorted_regions and HAS_PLOTLY:
            _top15     = _sorted_regions[:15]
            _rg_lbls   = [r for r, _ in _top15]
            _rg_vals   = [v for _, v in _top15]
            _max_v     = _rg_vals[0] if _rg_vals else 1
            _bar_clrs  = [
                f"rgba(8,145,178,{0.30 + 0.70 * (v / _max_v):.2f})"
                for v in _rg_vals
            ]
            _fig_bar = go.Figure(go.Bar(
                x=_rg_vals, y=_rg_lbls,
                orientation="h",
                marker=dict(color=_bar_clrs, line=dict(color=C["teal"], width=0.5)),
                text=[f"{v:,}명 ({round(v/max(_known_total,1)*100,1)}%)" for v in _rg_vals],
                textposition="outside",
                textfont=dict(size=10, color=C["t2"]),
                hovertemplate="<b>%{y}</b><br>%{x:,}명<extra></extra>",
            ))
            _fig_bar.update_layout(
                **_PLOTLY_LAYOUT,
                height=max(300, len(_top15) * 26 + 60),
                margin=dict(l=0, r=100, t=8, b=8),
                showlegend=False, bargap=0.3,
            )
            _fig_bar.update_xaxes(showticklabels=False, showgrid=False)
            _fig_bar.update_yaxes(tickfont=dict(size=10), autorange="reversed")
            st.plotly_chart(_fig_bar, use_container_width=True, key="reg_v3_hbar")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)
 
    with _col_line:
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["green"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"📈 {_sel_dept} — 상위 5개 지역 일별 추이",
                f"{_period_label} 일별 환자수", C["green"])
        # 일별 × 지역 집계
        _day_rg_map: dict = _ddr(lambda: _ddr(int))
        for _r in _filtered_data:
            _dj  = str(_r.get("기준일자", ""))
            _rg  = _r.get("지역", "")
            _cnt = int(_r.get("환자수", 0) or 0)
            if _dj and _rg not in ("지역미상", "", None):
                _day_rg_map[_dj][_rg] += _cnt
 
        _all_days_sorted = sorted(_day_rg_map.keys())
        _top5_rg         = [r for r, _ in _sorted_regions[:5]]
 
        # 날짜 레이블: 간략하게 (MM/DD)
        def _fmt_day(d: str) -> str:
            return f"{d[4:6]}/{d[6:8]}" if len(d) == 8 else d
 
        if _top5_rg and _all_days_sorted and HAS_PLOTLY:
            _fig_line = go.Figure()
            for _li, _rg_l in enumerate(_top5_rg):
                _y_vals = [_day_rg_map.get(_dj, {}).get(_rg_l, 0) for _dj in _all_days_sorted]
                _fig_line.add_trace(go.Scatter(
                    x=[_fmt_day(_dj) for _dj in _all_days_sorted],
                    y=_y_vals, name=_rg_l,
                    mode="lines+markers",
                    line=dict(color=_PALETTE[_li % len(_PALETTE)], width=2.5),
                    marker=dict(size=6, color=_PALETTE[_li % len(_PALETTE)],
                                line=dict(color="#fff", width=1.5)),
                    hovertemplate=f"<b>{_rg_l}</b><br>%{{x}}: %{{y:,}}명<extra></extra>",
                ))
            _fig_line.update_layout(
                **_PLOTLY_LAYOUT, height=300,
                margin=dict(l=0, r=0, t=30, b=8),
                legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center",
                            font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified",
            )
            _fig_line.update_xaxes(tickfont=dict(size=10),
                                   tickangle=-30 if _n_days >= 14 else 0)
            _fig_line.update_yaxes(title_text="환자수(명)",
                                   title_font=dict(size=10, color=C["t3"]))
            st.plotly_chart(_fig_line, use_container_width=True, key="reg_v3_line")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)
 
    _gap()
 
    # ══════════════════════════════════════
    # [섹션2] 지역×날짜 히트맵 (2주일/한달일 때만 표시)
    # ══════════════════════════════════════
    _top10_rg_hm = [r for r, _ in _sorted_regions[:10]]
    if _n_days >= 14 and _top10_rg_hm and _all_days_sorted and HAS_PLOTLY:
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"🗓️ {_sel_dept} — 지역 × 날짜 히트맵",
                f"상위 10개 지역 · {_period_label}", C["indigo"])
        _hm_map2 = {
            (_rg, _dj): _day_rg_map.get(_dj, {}).get(_rg, 0)
            for _rg in _top10_rg_hm
            for _dj in _all_days_sorted
        }
        _z_hm2 = [
            [_hm_map2.get((_rg, _dj), 0) for _dj in _all_days_sorted]
            for _rg in _top10_rg_hm
        ]
        _x_lbl2 = [_fmt_day(_dj) for _dj in _all_days_sorted]
        _fig_hm3 = go.Figure(go.Heatmap(
            z=_z_hm2, x=_x_lbl2, y=_top10_rg_hm,
            colorscale=[[0.0, "#EEF2FF"], [0.5, "#6366F1"], [1.0, "#3730A3"]],
            text=[[str(v) if v > 0 else "" for v in row] for row in _z_hm2],
            texttemplate="%{text}", textfont=dict(size=9, color="#fff"),
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}명<extra></extra>",
            showscale=True, xgap=2, ygap=2,
            colorbar=dict(title="환자수", thickness=12, len=0.8),
        ))
        _hm3_h = max(250, len(_top10_rg_hm) * 26 + 70)
        _fig_hm3.update_layout(
            **_PLOTLY_LAYOUT, height=_hm3_h,
            margin=dict(l=0, r=60, t=8, b=8),
        )
        _fig_hm3.update_xaxes(side="top", tickfont=dict(size=9), tickangle=-45)
        _fig_hm3.update_yaxes(tickfont=dict(size=10), autorange="reversed")
        st.plotly_chart(_fig_hm3, use_container_width=True, key="reg_v3_heatmap")
        st.markdown("</div>", unsafe_allow_html=True)
        _gap()
 
    # ══════════════════════════════════════
    # [섹션3] TOP5 지역 카드 + MoM(전주/전기간) 증감
    # ══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["teal"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd(f"🏆 {_sel_dept} — 상위 지역 TOP 5",
            f"{_period_label} · 전기간 대비 증감", C["teal"])
 
    # 비교 기간 (전달 동일 기간)
    _prev_start_d = f"{_prev_ym}01"
    _prev_end_d   = f"{_prev_ym}{_date_end[6:]}"   # 전달의 동일 일자까지

    _prev_data = [
        _r for _r in region_data
        if _r.get("진료과명", "") == _sel_dept
        and _prev_start_d <= str(_r.get("기준일자", "")) <= _prev_end_d
    ]
    _prev_region: dict = _ddr(int)
    for _r in _prev_data:
        _rg = _r.get("지역", "")
        if _rg not in ("지역미상", "", None):
            _prev_region[_rg] += int(_r.get("환자수", 0) or 0)
 
    if _sorted_regions:
        _top5_cols = st.columns(5, gap="small")
        for _ti, (_rg_t, _rc_t) in enumerate(_sorted_regions[:5]):
            _prev_cnt = _prev_region.get(_rg_t, 0)
            _diff_t   = _rc_t - _prev_cnt
            _chg_t    = (
                f"{round(_diff_t / _prev_cnt * 100, 1):+.1f}%"
                if _prev_cnt > 0 else "신규"
            )
            _arrow_t  = "▲" if _diff_t > 0 else "▼" if _diff_t < 0 else "─"
            _dc_t     = C["red"] if _diff_t > 0 else C["blue"] if _diff_t < 0 else C["t3"]
            _pct_t    = round(_rc_t / max(_known_total, 1) * 100, 1)
            _bar_w_t  = round(_rc_t / max(_sorted_regions[0][1], 1) * 100)
            _medals_t = ["🥇", "🥈", "🥉", "④", "⑤"]
            _col_t    = _PALETTE[_ti % len(_PALETTE)]
 
            with _top5_cols[_ti]:
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #F0F4F8;'
                    f'border-top:3px solid {_col_t};border-radius:10px;'
                    f'padding:12px 10px;text-align:center;">'
                    f'<div style="font-size:18px;">{_medals_t[_ti]}</div>'
                    f'<div style="font-size:11px;font-weight:800;color:{_col_t};'
                    f'margin:4px 0;line-height:1.3;word-break:keep-all;">{_rg_t}</div>'
                    f'<div style="font-size:20px;font-weight:800;color:{C["t1"]};">'
                    f'{_rc_t:,}<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
                    f'<div style="font-size:10px;color:{C["t3"]};margin-top:2px;">'
                    f'점유율 {_pct_t}%</div>'
                    f'<div style="height:4px;background:#F1F5F9;border-radius:2px;'
                    f'margin:6px 0;overflow:hidden;">'
                    f'<div style="width:{_bar_w_t}%;height:100%;background:{_col_t};'
                    f'border-radius:2px;"></div></div>'
                    f'<div style="font-size:11px;font-weight:700;color:{_dc_t};">'
                    f'{_arrow_t} {_chg_t}</div>'
                    f'<div style="font-size:9.5px;color:{C["t4"]};">전기간 대비</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        _plotly_empty()
 
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()
 
    # ══════════════════════════════════════
    # [섹션4] 정적 경영 인사이트 요약
    # (AI채팅 제거 — 하단 공통 채팅 사용)
    # ══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["violet"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📋 경영 인사이트 자동 요약",
            f"{_sel_dept} · {_period_label} 데이터 기준", C["violet"])
 
    # 의존도 진단
    _dep_level = "🔴 위험" if _top1_dependency >= 60 else "🟡 주의" if _top1_dependency >= 40 else "🟢 양호"
    _dep_msg   = (
        f"1위 지역 <b>{_top1_region}</b> 점유율 <b>{_top1_dependency}%</b> — {_dep_level}<br>"
        f"{'⚠️ 특정 지역 집중도가 높습니다. 인근 지역 홍보 강화가 필요합니다.' if _top1_dependency >= 40 else '✅ 지역 분산이 양호합니다.'}"
    )
 
    # 데이터 품질
    _unk_pct = round(_unknown_total / max(_total_patients, 1) * 100, 1)
    _unk_level = "🔴 불량" if _unk_pct >= 30 else "🟡 주의" if _unk_pct >= 10 else "🟢 양호"
    _unk_msg   = (
        f"지역미상 <b>{_unknown_total:,}명 ({_unk_pct}%)</b> — {_unk_level}<br>"
        f"{'📋 접수 시 주소 입력 강화가 필요합니다.' if _unk_pct >= 10 else '✅ 주소 데이터 품질이 양호합니다.'}"
    )
 
    # 전기간 대비 이상징후 (TOP15 지역 중 ±30% 이상)
    _anomaly_msgs = []
    for _rg_a, _cv_a in _sorted_regions[:15]:
        _pv_a = _prev_region.get(_rg_a, 0)
        if _pv_a >= 3:
            _chg_a = (_cv_a - _pv_a) / _pv_a * 100
            if abs(_chg_a) >= 30:
                _icon_a = "🔴" if _chg_a > 0 else "🔵"
                _anomaly_msgs.append(
                    f"{_icon_a} <b>{_rg_a}</b> {_chg_a:+.1f}% "
                    f"({_pv_a:,} → {_cv_a:,}명)"
                )
    _anom_msg = (
        "<br>".join(_anomaly_msgs[:3])
        if _anomaly_msgs
        else "✅ 전기간 대비 급격한 변동 지역 없음"
    )
 
    # TOP3 지역
    _top3_str = " > ".join(
        f"<b>{r}</b> {c:,}명" for r, c in _sorted_regions[:3]
    ) if _sorted_regions else "─"
 
    _ins_items = [
        ("📍 지역 의존도 진단", _dep_msg,  C["blue"]),
        ("🗂️ 데이터 품질",     _unk_msg,  C["orange"]),
        ("🚨 이상징후 탐지",   _anom_msg, C["red"] if _anomaly_msgs else C["green"]),
        ("🏆 상위 3개 지역",   _top3_str, C["teal"]),
    ]
    _ins_cols = st.columns(2, gap="small")
    for _ii2, (_ins_title, _ins_body, _ins_color) in enumerate(_ins_items):
        with _ins_cols[_ii2 % 2]:
            st.markdown(
                f'<div style="background:#fff;border:1px solid #F0F4F8;'
                f'border-left:4px solid {_ins_color};border-radius:8px;'
                f'padding:12px 14px;margin-bottom:8px;">'
                f'<div style="font-size:11.5px;font-weight:700;color:{_ins_color};margin-bottom:6px;">'
                f'{_ins_title}</div>'
                f'<div style="font-size:12px;color:{C["t2"]};line-height:1.6;">'
                f'{_ins_body}</div></div>',
                unsafe_allow_html=True,
            )
 
    st.markdown(
        f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;'
        f'padding:9px 14px;margin-top:4px;display:flex;align-items:center;gap:8px;">'
        f'<span style="font-size:14px;">🤖</span>'
        f'<span style="font-size:12px;color:{C["blue"]};font-weight:600;">'
        f'AI 심층 분석은 하단 채팅창에서 "{_sel_dept} 지역 분석해줘" 등으로 질문하세요'
        f'</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()
    
    # ══════════════════════════════════════════════
    # [섹션5] 부산/경남 지역 버블맵
    # ══════════════════════════════════════════════
    _gap(12)
    _map_c1, _map_c2 = st.columns([1, 1], gap="small")
    with _map_c1:
        _render_folium_map(
            region_data=_filtered_data,
            sig_cd_prefix="26",            # 하위호환 유지
            title="🗺️ 부산 구군별 환자 분포",
            color_main=C["blue"],
            color_stops=[(0.0,"#EFF6FF"),(0.2,"#BAE6FD"),(0.5,"#3B82F6"),(0.8,"#1D4ED8"),(1.0,"#0C2D48")],
            center=[35.12, 129.04],        # ← 부산 중심 조정
            zoom_start=11,
            chart_key=f"folium_busan_{_sel_dept}_{_n_days}",
            district_set=_BUSAN_DISTRICTS, # ← 추가
        )
    with _map_c2:
        _render_folium_map(
            region_data=_filtered_data,
            sig_cd_prefix="48",
            title="🗺️ 경상남도 시군별 환자 분포",
            color_main=C["green"],
            color_stops=[(0.0,"#F0FDF4"),(0.2,"#BBF7D0"),(0.5,"#34D399"),(0.8,"#059669"),(1.0,"#064E3B")],
            center=[35.40, 128.10],        # ← 경남 중심 조정
            zoom_start=8,                  # ← 9 → 8 (경남 전체 보이게)
            chart_key=f"folium_gyeongnam_{_sel_dept}_{_n_days}",
            district_set=_GYEONGNAM_DISTRICTS, # ← 추가
        )
    _gap()

    # ══════════════════════════════════════════════════════════════════════
    # [섹션6] 지정월 전년도 대비 지역 비교 트리맵 (V_REGION_DEPT_MONTHLY)
    # ══════════════════════════════════════════════════════════════════════
    _rm = region_monthly or []
    _rm_dept = [r for r in _rm if r.get("진료과명", "") == _sel_dept]

    # YYYYMM → {지역: 환자수}
    _mo_lookup: dict = {}
    for _r5 in _rm_dept:
        _ym5 = str(_r5.get("기준월", ""))
        _rg5 = _r5.get("지역", "")
        _cnt5 = int(_r5.get("환자수", 0) or 0)
        if not _ym5 or not _rg5 or _rg5 == "지역미상":
            continue
        if _ym5 not in _mo_lookup:
            _mo_lookup[_ym5] = {}
        _mo_lookup[_ym5][_rg5] = _mo_lookup[_ym5].get(_rg5, 0) + _cnt5

    _mo_months = sorted(_mo_lookup.keys())

    # 전년도 대비 가능한 달 (현재 월과 -100 모두 있는 달)
    _today_ym_cap = _dt_r.date.today().strftime("%Y%m")
    _yoy_pairs = [
        (ym, str(int(ym) - 100))
        for ym in _mo_months
        if str(int(ym) - 100) in _mo_lookup
        and ym <= _today_ym_cap
    ]

    if _yoy_pairs:
        _gap()
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(
            f"📊 {_sel_dept} — 지정월 전년도 대비 지역 비교",
            "V_REGION_DEPT_MONTHLY · DISTINCT 환자수 기준 · 부산·경남 상세",
            C["indigo"],
        )

        # 월 선택
        _yoy_opts = [p[0] for p in _yoy_pairs]
        _yoy_cur = st.selectbox(
            "비교 기준월",
            options=_yoy_opts,
            index=len(_yoy_opts) - 1,
            format_func=lambda ym: (
                f"{ym[:4]}년 {ym[4:]}월  ←→  "
                f"{int(ym[:4])-1}년 {ym[4:]}월 (전년 동월)"
            ),
            key=f"reg_yoy_mo_{_sel_dept}",
            label_visibility="collapsed",
        )
        _yoy_prv = str(int(_yoy_cur) - 100)

        _cur_d = _mo_lookup.get(_yoy_cur, {})
        _prv_d = _mo_lookup.get(_yoy_prv, {})
        _all_rgs_y = sorted(set(list(_cur_d.keys()) + list(_prv_d.keys())))

        def _yoy_color(pct):
            if pct is None:
                return "#CBD5E1"
            elif pct >= 15:
                return "#1D4ED8"
            elif pct >= 5:
                return "#93C5FD"
            elif pct >= -5:
                return "#E2E8F0"
            elif pct >= -15:
                return "#FCA5A5"
            else:
                return "#DC2626"

        # 시도 레벨 집계
        _sido_agg: dict = {}
        for _rg6 in _all_rgs_y:
            _sido = _rg6.split(" ")[0] if " " in _rg6 else _rg6
            if _sido not in _sido_agg:
                _sido_agg[_sido] = {"cur": 0, "prv": 0}
            _sido_agg[_sido]["cur"] += _cur_d.get(_rg6, 0)
            _sido_agg[_sido]["prv"] += _prv_d.get(_rg6, 0)

        # 전국 YoY KPI
        _tot_cur_y = sum(v["cur"] for v in _sido_agg.values())
        _tot_prv_y = sum(v["prv"] for v in _sido_agg.values())
        _tot_diff_y = _tot_cur_y - _tot_prv_y
        _tot_pct_y = round(_tot_diff_y / max(_tot_prv_y, 1) * 100, 1)
        _yoy_cur_label = f"{_yoy_cur[:4]}년 {_yoy_cur[4:]}월"
        _yoy_prv_label = f"{_yoy_prv[:4]}년 {_yoy_prv[4:]}월"

        _ky1, _ky2, _ky3 = st.columns(3, gap="small")
        _kpi_card(_ky1, "📅", _yoy_cur_label, f"{_tot_cur_y:,}", "명",
                  "기준월 전체 환자수", C["indigo"])
        _kpi_card(_ky2, "📅", _yoy_prv_label, f"{_tot_prv_y:,}", "명",
                  "전년 동월 환자수", C["t2"])
        _ky3.markdown(
            f'<div class="fn-kpi" style="border-top:3px solid '
            f'{C["red"] if _tot_diff_y >= 0 else C["blue"]};">'
            f'<div class="fn-kpi-icon">{"📈" if _tot_diff_y >= 0 else "📉"}</div>'
            f'<div class="fn-kpi-label">전년 대비</div>'
            f'<div style="font-size:18px;font-weight:800;color:'
            f'{C["red"] if _tot_diff_y >= 0 else C["blue"]};">'
            f'{"▲" if _tot_diff_y > 0 else "▼"}&nbsp;{abs(_tot_diff_y):,}'
            f'<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
            f'<div style="font-size:11px;font-weight:700;color:'
            f'{C["red"] if _tot_diff_y >= 0 else C["blue"]};">'
            f'{_tot_pct_y:+.1f}%</div></div>',
            unsafe_allow_html=True,
        )
        _gap()

        # ── 전국 시도 트리맵
        if HAS_PLOTLY and _sido_agg:
            _tm_labels = ["전국"]
            _tm_parents = [""]
            _tm_values = [_tot_cur_y]
            _tm_colors = ["#F1F5F9"]
            _tm_custom = [[None, _tot_cur_y, _tot_prv_y, "전국"]]

            _sido_labels = {
                "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
                "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
                "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
                "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
                "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
                "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
            }
            for _sido, _sv in sorted(_sido_agg.items(),
                                     key=lambda x: -x[1]["cur"]):
                _sc = _sv["cur"]
                _sp = _sv["prv"]
                _spct = round((_sc - _sp) / max(_sp, 1) * 100, 1) if _sp > 0 else None
                _lbl = _sido_labels.get(_sido, _sido)
                _tm_labels.append(_lbl)
                _tm_parents.append("전국")
                _tm_values.append(_sc)
                _tm_colors.append(_yoy_color(_spct))
                _tm_custom.append([_spct, _sc, _sp, _sido])

            _fig_tm = go.Figure(go.Treemap(
                labels=_tm_labels,
                parents=_tm_parents,
                values=_tm_values,
                marker=dict(colors=_tm_colors, line=dict(width=1.5, color="#fff")),
                texttemplate=(
                    "<b>%{label}</b><br>"
                    "<span style='font-size:11px'>%{customdata[0]:+.1f}%</span>"
                ),
                customdata=_tm_custom,
                hovertemplate=(
                    "<b>%{customdata[3]}</b><br>"
                    "전년 대비: <b>%{customdata[0]:+.1f}%</b><br>"
                    f"{_yoy_cur_label}: %{{customdata[1]:,}}명<br>"
                    f"{_yoy_prv_label}: %{{customdata[2]:,}}명"
                    "<extra></extra>"
                ),
                textfont=dict(size=13),
                pathbar=dict(visible=False),
                root_color="#F8FAFC",
            ))
            _fig_tm.update_layout(
                **_PLOTLY_LAYOUT, height=340,
                margin=dict(l=0, r=0, t=8, b=0),
            )
            st.plotly_chart(_fig_tm, use_container_width=True,
                            key=f"reg_yoy_tm_{_sel_dept}_{_yoy_cur}")

            # ── 범례
            _legend_items = [
                ("#1D4ED8", "+15%↑ 강한 증가"),
                ("#93C5FD", "+5~15%"),
                ("#E2E8F0", "±5% 보합"),
                ("#FCA5A5", "-5~-15%"),
                ("#DC2626", "-15%↓ 강한 감소"),
            ]
            _leg_html = (
                '<div style="display:flex;gap:14px;justify-content:center;'
                'padding:6px 0 10px;flex-wrap:wrap;">'
            )
            for _lc, _lt in _legend_items:
                _leg_html += (
                    f'<div style="display:flex;align-items:center;gap:5px;">'
                    f'<div style="width:14px;height:14px;border-radius:3px;'
                    f'background:{_lc};"></div>'
                    f'<span style="font-size:11px;color:{C["t2"]};">{_lt}</span>'
                    f'</div>'
                )
            st.markdown(_leg_html + "</div>", unsafe_allow_html=True)

        _gap()

        # ── 부산 구별 + 경남 시군별 상세 YoY 바 차트
        _yoy_row = []
        for _rg6 in _all_rgs_y:
            _c6 = _cur_d.get(_rg6, 0)
            _p6 = _prv_d.get(_rg6, 0)
            _pct6 = round((_c6 - _p6) / max(_p6, 1) * 100, 1) if _p6 > 0 else None
            _yoy_row.append({"지역": _rg6, "cur": _c6, "prv": _p6, "pct": _pct6})

        _busan_yoy = sorted(
            [r for r in _yoy_row if r["지역"].startswith("부산")],
            key=lambda x: -x["cur"],
        )
        _gynam_yoy = sorted(
            [r for r in _yoy_row if r["지역"].startswith("경상남도")],
            key=lambda x: -x["cur"],
        )

        def _detail_yoy_chart(rows, title, color_up, color_dn, chart_key):
            if not rows or not HAS_PLOTLY:
                return
            _lbl7 = [r["지역"].split(" ", 1)[-1] if " " in r["지역"] else r["지역"]
                     for r in rows]
            _cur7 = [r["cur"] for r in rows]
            _prv7 = [r["prv"] for r in rows]
            _pct7 = [r["pct"] for r in rows]
            _clr7 = [
                color_up if (p is not None and p >= 0) else color_dn
                for p in _pct7
            ]
            _pct_txt = [
                f"{p:+.1f}%" if p is not None else "신규" for p in _pct7
            ]

            _fig7 = go.Figure()
            _fig7.add_trace(go.Bar(
                name=_yoy_prv_label, x=_lbl7, y=_prv7,
                marker_color=_c(C["t3"], 0.53),
                hovertemplate="<b>%{x}</b><br>전년: %{y:,}명<extra></extra>",
            ))
            _fig7.add_trace(go.Bar(
                name=_yoy_cur_label, x=_lbl7, y=_cur7,
                marker_color=_clr7,
                text=_pct_txt,
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate="<b>%{x}</b><br>현년: %{y:,}명<extra></extra>",
            ))
            _fig7.update_layout(
                **_PLOTLY_LAYOUT,
                height=300,
                margin=dict(l=0, r=0, t=30, b=8),
                barmode="group",
                bargap=0.15,
                bargroupgap=0.05,
                legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center",
                            font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                title=dict(text=title, font=dict(size=13, color=C["t1"]), x=0),
            )
            _fig7.update_xaxes(tickfont=dict(size=10), tickangle=-20)
            _fig7.update_yaxes(showticklabels=False)
            st.plotly_chart(_fig7, use_container_width=True, key=chart_key)

        _dc1, _dc2 = st.columns(2, gap="small")
        with _dc1:
            st.markdown(
                f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
                unsafe_allow_html=True,
            )
            _detail_yoy_chart(
                _busan_yoy,
                f"🏙️ 부산 구별  ({_yoy_cur_label} vs {_yoy_prv_label})",
                C["blue"], _c(C["red"], 0.80),
                f"reg_yoy_busan_{_sel_dept}_{_yoy_cur}",
            )
            st.markdown("</div>", unsafe_allow_html=True)
        with _dc2:
            st.markdown(
                f'<div class="wd-card" style="border-top:3px solid {C["green"]};">',
                unsafe_allow_html=True,
            )
            _detail_yoy_chart(
                _gynam_yoy,
                f"🏞️ 경상남도 시군별  ({_yoy_cur_label} vs {_yoy_prv_label})",
                C["green"], _c(C["red"], 0.80),
                f"reg_yoy_gynam_{_sel_dept}_{_yoy_cur}",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)  # card
        _gap()

    # ══════════════════════════════════════════════════════════════════════
    # [섹션7] 월별 환자 추이 + 선택적 비교 (V_REGION_DEPT_MONTHLY 기반)
    # ══════════════════════════════════════════════════════════════════════
    if _mo_months:
        _mo_total = {ym: sum(v.values()) for ym, v in _mo_lookup.items()}

        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"📅 {_sel_dept} — 월별 환자 추이",
                f"V_REGION_DEPT_MONTHLY · {len(_mo_months)}개월 · 지역미상 제외",
                C["blue"])

        # KPI (전월 대비)
        if len(_mo_months) >= 2:
            _cm = _mo_months[-1]
            _pm = _mo_months[-2]
            _ct = _mo_total.get(_cm, 0)
            _pt = _mo_total.get(_pm, 0)
            _md = _ct - _pt
            _mp = round(_md / max(_pt, 1) * 100, 1)
            _mc = C["red"] if _md > 0 else C["blue"] if _md < 0 else C["t3"]
            _mxm = max(_mo_total, key=_mo_total.get)

            _km1, _km2, _km3, _km4 = st.columns(4, gap="small")
            _kpi_card(_km1, "📅", f"당월 ({_cm[:4]}.{_cm[4:]})", f"{_ct:,}", "명",
                      "지역미상 제외", C["blue"])
            _kpi_card(_km2, "📅", f"전월 ({_pm[:4]}.{_pm[4:]})", f"{_pt:,}", "명",
                      "지역미상 제외", C["t2"])
            _km3.markdown(
                f'<div class="fn-kpi" style="border-top:3px solid {_mc};">'
                f'<div class="fn-kpi-icon">{"📈" if _md >= 0 else "📉"}</div>'
                f'<div class="fn-kpi-label">전월 대비</div>'
                f'<div style="font-size:18px;font-weight:800;color:{_mc};">'
                f'{"▲" if _md > 0 else "▼"}&nbsp;{abs(_md):,}'
                f'<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
                f'<div style="font-size:11px;color:{_mc};font-weight:700;">'
                f'{_mp:+.1f}%</div></div>',
                unsafe_allow_html=True,
            )
            _kpi_card(_km4, "🏆", "최대 월", f"{_mo_total[_mxm]:,}", "명",
                      f"{_mxm[:4]}.{_mxm[4:]}", C["teal"])
            _gap()

        # 월별 추이 바 차트
        if HAS_PLOTLY:
            _ml = [f"{ym[:4]}.{ym[4:]}" for ym in _mo_months]
            _mv = [_mo_total.get(ym, 0) for ym in _mo_months]
            _mc2 = [
                C["blue"] if ym == _mo_months[-1]
                else _c(C["indigo"], 0.67) if ym == _mo_months[-2]
                else _c(C["indigo"], 0.33)
                for ym in _mo_months
            ]
            _fig_mo = go.Figure(go.Bar(
                x=_ml, y=_mv,
                marker=dict(color=_mc2, line=dict(color="rgba(0,0,0,0)")),
                text=[f"{v:,}" for v in _mv],
                textposition="outside",
                textfont=dict(size=10, color=C["t2"]),
                hovertemplate="<b>%{x}</b><br>%{y:,}명<extra></extra>",
            ))
            _fig_mo.update_layout(
                **_PLOTLY_LAYOUT, height=260,
                margin=dict(l=0, r=0, t=30, b=8),
                showlegend=False, bargap=0.25,
            )
            _fig_mo.update_xaxes(tickfont=dict(size=10))
            _fig_mo.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)",
                                  showticklabels=False)
            st.plotly_chart(_fig_mo, use_container_width=True,
                            key=f"reg_mo_bar_{_sel_dept}")

        # 월별 요약 테이블 (최근 12개월 · 컴팩트)
        _mo_recent = list(reversed(_mo_months))[:12]
        _TH_MO = (
            "padding:5px 8px;font-size:11px;font-weight:700;color:#64748B;"
            "border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        )
        _mo_tbl = (
            '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>'
            f'<th style="{_TH_MO}text-align:left;width:72px;">월</th>'
            f'<th style="{_TH_MO}text-align:right;color:{C["blue"]};">환자수</th>'
            f'<th style="{_TH_MO}text-align:right;">전월대비</th>'
            f'<th style="{_TH_MO}">1위 지역</th>'
            f'<th style="{_TH_MO}text-align:right;width:48px;">점유율</th>'
            f'</tr></thead><tbody>'
        )
        for _ri8, _ym8 in enumerate(_mo_recent):
            _rbg8 = "#F8FAFC" if _ri8 % 2 == 0 else "#FFFFFF"
            _td8  = (f"padding:5px 8px;background:{_rbg8};"
                     "border-bottom:1px solid #F1F5F9;font-size:12px;")
            _tot8    = _mo_total.get(_ym8, 0)
            _prev_ym8 = _mo_recent[_ri8 + 1] if _ri8 + 1 < len(_mo_recent) else None
            _prev8    = _mo_total.get(_prev_ym8, 0) if _prev_ym8 else None
            if _prev8 is not None and _prev8 > 0:
                _diff8  = _tot8 - _prev8
                _pct8   = round(_diff8 / _prev8 * 100, 1)
                _dc8    = C["red"] if _diff8 > 0 else C["blue"] if _diff8 < 0 else C["t3"]
                _darr8  = "▲" if _diff8 > 0 else "▼" if _diff8 < 0 else "─"
                _mom8   = (f'<span style="color:{_dc8};font-weight:700;">'
                           f'{_darr8} {abs(_diff8):,} ({_pct8:+.1f}%)</span>')
            else:
                _mom8 = '<span style="color:#CBD5E1;">─</span>'
            _tops8   = sorted(_mo_lookup[_ym8].items(), key=lambda x: -x[1])
            _top1_rg8 = _tops8[0][0] if _tops8 else "─"
            _top1_pt8 = round(_tops8[0][1] / max(_tot8, 1) * 100, 1) if _tops8 else 0
            _is_cur8  = (_ym8 == _mo_months[-1])
            _ym_clr8  = C["blue"] if _is_cur8 else C["t2"]
            _ym_fw8   = "800" if _is_cur8 else "600"
            _mo_tbl += (
                f"<tr>"
                f'<td style="{_td8}font-weight:{_ym_fw8};color:{_ym_clr8};">'
                f'{_ym8[:4]}.{_ym8[4:]}</td>'
                f'<td style="{_td8}text-align:right;font-weight:700;color:{C["t1"]};">'
                f'{_tot8:,}</td>'
                f'<td style="{_td8}text-align:right;">{_mom8}</td>'
                f'<td style="{_td8}color:{C["t2"]};">{_top1_rg8}</td>'
                f'<td style="{_td8}text-align:right;color:{C["t3"]};">{_top1_pt8}%</td>'
                f"</tr>"
            )
        st.markdown(_mo_tbl + "</tbody></table>", unsafe_allow_html=True)
        if len(_mo_months) > 12:
            with st.expander(f"📋 전체 {len(_mo_months)}개월 보기"):
                _mo_all_tbl = (
                    '<table style="width:100%;border-collapse:collapse;font-size:11.5px;">'
                    f'<thead><tr>'
                    f'<th style="{_TH_MO}text-align:left;">월</th>'
                    f'<th style="{_TH_MO}text-align:right;">환자수</th>'
                    f'<th style="{_TH_MO}">1위 지역</th>'
                    f'<th style="{_TH_MO}">2위 지역</th>'
                    f'</tr></thead><tbody>'
                )
                for _ri9, _ym9 in enumerate(reversed(_mo_months)):
                    _rbg9 = "#F8FAFC" if _ri9 % 2 == 0 else "#FFFFFF"
                    _td9  = f"padding:4px 8px;background:{_rbg9};border-bottom:1px solid #F1F5F9;font-size:11.5px;"
                    _tot9 = _mo_total.get(_ym9, 0)
                    _tops9 = sorted(_mo_lookup[_ym9].items(), key=lambda x: -x[1])[:2]
                    _rg9  = [f"{r}({c:,}명)" for r, c in _tops9]
                    while len(_rg9) < 2: _rg9.append("─")
                    _mo_all_tbl += (
                        f"<tr>"
                        f'<td style="{_td9}font-weight:600;color:{C["t2"]};">{_ym9[:4]}.{_ym9[4:]}</td>'
                        f'<td style="{_td9}text-align:right;font-weight:700;">{_tot9:,}</td>'
                        f'<td style="{_td9}">{_rg9[0]}</td>'
                        f'<td style="{_td9}">{_rg9[1]}</td>'
                        f"</tr>"
                    )
                st.markdown(_mo_all_tbl + "</tbody></table>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        _gap()

    # ── 월별 지역 비교 (선택적)
    if len(_mo_months) >= 2:
        _show_cmp = st.checkbox(
            f"📊 {_sel_dept} — 월별 지역 비교 (두 달 선택 → 지역별 증감)",
            key=f"reg_mo_cmp_{_sel_dept}",
        )
        if _show_cmp:
            st.markdown(
                f'<div class="wd-card" style="border-top:3px solid {C["violet"]};">',
                unsafe_allow_html=True,
            )
            _sec_hd("📊 월별 지역 비교 분석",
                    f"{_sel_dept} · 두 달 선택", C["violet"])

            def _fmt_ym_ko(ym: str) -> str:
                return f"{ym[:4]}년 {ym[4:]}월"

            _cc1, _cc2 = st.columns(2, gap="small")
            with _cc1:
                st.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
                    f'padding-bottom:2px;">📅 A월 (기준)</div>',
                    unsafe_allow_html=True,
                )
                _cmp_a_default = (
                    _mo_months.index(_sel_ym) if _sel_ym in _mo_months
                    else max(0, len(_mo_months) - 2)
                )
                _cmp_a = st.selectbox(
                    "A월", options=_mo_months,
                    index=_cmp_a_default,
                    format_func=_fmt_ym_ko,
                    key=f"reg_cmp_a_{_sel_dept}",
                    label_visibility="collapsed",
                )
            with _cc2:
                st.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
                    f'padding-bottom:2px;">📅 B월 (비교)</div>',
                    unsafe_allow_html=True,
                )
                _cmp_b_default = (
                    _mo_months.index(_cmp_ym) if _cmp_ym and _cmp_ym in _mo_months
                    else (_mo_months.index(_prev_ym) if _prev_ym in _mo_months
                          else len(_mo_months) - 1)
                )
                _cmp_b = st.selectbox(
                    "B월", options=_mo_months,
                    index=_cmp_b_default,
                    format_func=_fmt_ym_ko,
                    key=f"reg_cmp_b_{_sel_dept}",
                    label_visibility="collapsed",
                )

            if _cmp_a == _cmp_b:
                st.warning("⚠️ A월과 B월이 같습니다. 서로 다른 달을 선택하세요.")
            else:
                _a_d = dict(_mo_lookup.get(_cmp_a, {}))
                _b_d = dict(_mo_lookup.get(_cmp_b, {}))
                _tot_a2 = sum(_a_d.values())
                _tot_b2 = sum(_b_d.values())
                _all_r2 = sorted(set(list(_a_d.keys()) + list(_b_d.keys())))

                _cmp_rows = []
                for _rg2 in _all_r2:
                    _ca2 = _a_d.get(_rg2, 0)
                    _cb2 = _b_d.get(_rg2, 0)
                    _diff2 = _cb2 - _ca2
                    _pct2 = round(_diff2 / max(_ca2, 1) * 100, 1) if _ca2 > 0 else None
                    _cmp_rows.append({"지역": _rg2, "A": _ca2, "B": _cb2,
                                      "증감": _diff2, "증감률": _pct2})
                _cmp_rows.sort(key=lambda x: -x["증감"])

                _inc_n2 = sum(1 for r in _cmp_rows if r["증감"] > 0)
                _dec_n2 = sum(1 for r in _cmp_rows if r["증감"] < 0)
                _diff_t2 = _tot_b2 - _tot_a2
                _diff_p2 = round(_diff_t2 / max(_tot_a2, 1) * 100, 1)

                _kc1, _kc2, _kc3, _kc4 = st.columns(4, gap="small")
                _kpi_card(_kc1, "📅", _fmt_ym_ko(_cmp_a), f"{_tot_a2:,}", "명",
                          "A월 환자수", C["indigo"])
                _kpi_card(_kc2, "📅", _fmt_ym_ko(_cmp_b), f"{_tot_b2:,}", "명",
                          "B월 환자수", C["blue"])
                _kpi_card(_kc3, "📊", "총 증감", f"{_diff_t2:+,}", "명",
                          f"{_diff_p2:+.1f}%",
                          C["red"] if _diff_t2 > 0 else C["blue"])
                _kpi_card(_kc4, "🔄", "지역 변화",
                          f"▲{_inc_n2} ▼{_dec_n2}", "",
                          f"총 {len(_cmp_rows)}개 지역", C["teal"])
                _gap()

                _cc_l2, _cc_r2 = st.columns(2, gap="small")
                _top_inc2 = [r for r in _cmp_rows if r["증감"] > 0][:10]
                _top_dec2 = sorted(
                    [r for r in _cmp_rows if r["증감"] < 0], key=lambda x: x["증감"]
                )[:10]

                with _cc_l2:
                    st.markdown(
                        f'<div class="wd-card" style="border-top:3px solid {C["red"]};">',
                        unsafe_allow_html=True,
                    )
                    _sec_hd(f"📈 증가 TOP {len(_top_inc2)}", "", C["red"])
                    if _top_inc2 and HAS_PLOTLY:
                        _fig_i = go.Figure(go.Bar(
                            x=[r["증감"] for r in _top_inc2],
                            y=[r["지역"] for r in _top_inc2],
                            orientation="h",
                            marker_color=_c(C["red"], 0.80),
                            text=[f"+{r['증감']:,}명" for r in _top_inc2],
                            textposition="outside",
                            textfont=dict(size=10, color=C["red"]),
                        ))
                        _fig_i.update_layout(
                            **_PLOTLY_LAYOUT,
                            height=max(200, len(_top_inc2) * 28 + 60),
                            margin=dict(l=0, r=90, t=8, b=8), showlegend=False,
                        )
                        _fig_i.update_xaxes(showticklabels=False, showgrid=False)
                        _fig_i.update_yaxes(tickfont=dict(size=10), autorange="reversed")
                        st.plotly_chart(_fig_i, use_container_width=True,
                                        key=f"reg_cmp_inc2_{_sel_dept}_{_cmp_a}_{_cmp_b}")
                    else:
                        st.info("증가 지역 없음")
                    st.markdown("</div>", unsafe_allow_html=True)

                with _cc_r2:
                    st.markdown(
                        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
                        unsafe_allow_html=True,
                    )
                    _sec_hd(f"📉 감소 TOP {len(_top_dec2)}", "", C["blue"])
                    if _top_dec2 and HAS_PLOTLY:
                        _fig_d = go.Figure(go.Bar(
                            x=[r["증감"] for r in _top_dec2],
                            y=[r["지역"] for r in _top_dec2],
                            orientation="h",
                            marker_color=_c(C["blue"], 0.80),
                            text=[f"{r['증감']:,}명" for r in _top_dec2],
                            textposition="outside",
                            textfont=dict(size=10, color=C["blue"]),
                        ))
                        _fig_d.update_layout(
                            **_PLOTLY_LAYOUT,
                            height=max(200, len(_top_dec2) * 28 + 60),
                            margin=dict(l=0, r=90, t=8, b=8), showlegend=False,
                        )
                        _fig_d.update_xaxes(showticklabels=False, showgrid=False)
                        _fig_d.update_yaxes(tickfont=dict(size=10), autorange="reversed")
                        st.plotly_chart(_fig_d, use_container_width=True,
                                        key=f"reg_cmp_dec2_{_sel_dept}_{_cmp_a}_{_cmp_b}")
                    else:
                        st.info("감소 지역 없음")
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
        _gap()

    # ══════════════════════════════════════
    # [AI] 경영 컨설팅 채팅
    # ══════════════════════════════════════
    # [LLM 컨텍스트 설계]
    #   · 집계값(지역명·환자수)만 전달 — 환자명/주민번호/카드번호 미포함
    #   · 시스템 프롬프트: 병원 경영 분석 전문 컨설턴트 역할
    #   · 10가지 필수 분석 항목 명시 (요구사항 반영)
    # ──────────────────────────────────────────────────────────────
    _gap()
    st.markdown(
        f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:12px;'
        f'padding:14px 16px;border-top:3px solid {C["violet"]};">',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
        f'<span style="font-size:16px;">🤖</span>'
        f'<span style="font-size:13px;font-weight:700;color:{C["t1"]};">'
        f'AI 경영 컨설팅 분석</span>'
        f'<span style="background:{C["violet_l"]};color:{C["violet"]};border-radius:5px;'
        f'padding:2px 8px;font-size:10.5px;font-weight:700;">병원 경영 분석 전문</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
 
    
    # 월별 TOP3 지역 추이 (LLM 입력용)
    _trend_ctx: dict = _ddr(lambda: _ddr(int))
    for _r in _filtered_data:
        # 기준일자(YYYYMMDD)를 기준년월(YYYYMM)로 변환
        _dj = str(_r.get("기준일자", ""))
        _ym8 = _dj[:6] if len(_dj) >= 6 else ""
        _rg8 = _r.get("지역", "")
        if _ym8 and _rg8 and _rg8 != "지역미상":
            _trend_ctx[_ym8][_rg8] += int(_r.get("환자수", 0) or 0)
 
    _trend_summary = {
        _ym8: [{"지역": r, "환자수": c}
               for r, c in sorted(_rgs.items(), key=lambda x: -x[1])[:3]]
        for _ym8, _rgs in sorted(_trend_ctx.items())
    }
    
    # 월별 분석 메타데이터
    _target_months = list(sorted(_trend_ctx.keys()))
    _n_months = len(_target_months)
    _unique_depts = 1  # 현재는 선택된 단일 진료과만 분석

    # 이상징후 탐지 (MoM 증감)
    _anomalies: list = []
    _sorted_months_ctx = sorted(_trend_ctx.keys())
    if len(_sorted_months_ctx) >= 2:
        _prev_ym = _sorted_months_ctx[-2]
        _curr_ym = _sorted_months_ctx[-1]
        _prev_rgs = _trend_ctx.get(_prev_ym, {})
        _curr_rgs = _trend_ctx.get(_curr_ym, {})
        _all_rgs_ctx = set(list(_prev_rgs.keys()) + list(_curr_rgs.keys()))
        for _rg_an in _all_rgs_ctx:
            _pv_an = _prev_rgs.get(_rg_an, 0)
            _cv_an = _curr_rgs.get(_rg_an, 0)
            if _pv_an > 10:  # 소수 샘플 필터
                _chg = round((_cv_an - _pv_an) / _pv_an * 100, 1)
                if abs(_chg) >= 30:  # 30% 이상 변동만 포함
                    _anomalies.append({
                        "지역": _rg_an,
                        "전월": _pv_an,
                        "당월": _cv_an,
                        "변동률": f"{_chg:+.1f}%",
                    })
        _anomalies = sorted(_anomalies, key=lambda x: abs(float(x["변동률"].replace("%",""))), reverse=True)[:5]
    
    # 진료과별 TOP5지역 컨텍스트 (현재는 단일 진료과)
    _dept_region_ctx = {
        _sel_dept: [{"지역": r, "환자수": c} for r, c in _sorted_regions[:5]]
    } if _sorted_regions else {}
 
    _ai_ctx = {
        "분석_진료과": _sel_dept,
        "분석_기간": f"최근 {_n_months}개월 ({', '.join(sorted(_target_months))})" if _target_months else "데이터 없음",
        "총_환자수": _total_patients,
        "유입_지역수": _unique_regions,
        "집계_진료과수": _unique_depts,
        "1위_지역": {"지역": _top1_region, "환자수": _top1_cnt},
        "진료과별_TOP5지역": _dept_region_ctx,
        "월별_상위3지역_추이": _trend_summary,
        "이상징후_탐지(MoM±30%이상)": _anomalies,
    }
 
    # ── 시스템 프롬프트 (병원 경영 분석 전문)
    _sys_consulting = (
        "당신은 대학병원 경영 전략 컨설턴트입니다.\n"
        "아래 [지역별 환자 통계 데이터]를 분석하여 "
        "병원 경영 의사결정에 활용 가능한 컨설팅 보고서를 작성하세요.\n\n"
        "## 필수 분석 항목 (모두 포함)\n"
        "1. **지역 유입 패턴** — 증가/감소 지역 식별 및 원인 추론\n"
        "2. **지역 의존도 분석** — 특정 지역 편중 리스크 평가 (지역 집중도 HHI 개념 활용)\n"
        "3. **병원 영향권 변화** — 진료권 확대/축소 및 상권 변화 해석\n"
        "4. **이상징후 탐지** — 급증·급감(±30% 이상) 지역 경고 및 대응 방안\n"
        "5. **신규 환자 유입 지역** — 신규 유입 강화 가능 지역 탐지\n"
        "6. **진료과별 지역 비교** — 진료과별 환자 유입 패턴 차이 해석\n"
        "7. **지역 점유율 변화** — 월별 지역 점유율 추이 분석\n"
        "8. **경쟁 환경 추론** — 타 의료기관 영향 가능성\n"
        "9. **마케팅 전략** — 지역별 홍보·마케팅 투자 우선순위 제안\n"
        "10. **경영 개선 전략** — 진료권 확대를 위한 구체적 실행 계획\n\n"
        "## 출력 형식\n"
        "- 컨설팅 보고서 수준 (실제 병원 운영 관점)\n"
        "- 단순 데이터 나열 금지 — 해석·전략 중심\n"
        "- ⚠️ 위험/주의, ✅ 기회/강점, 📋 조치사항, 🔴 이상징후 이모지 활용\n"
        "- 핵심 수치는 **굵게** 표시\n"
        "- 개인 환자 정보(환자명, 주민번호, 연락처 등) 언급 절대 금지\n\n"
        f"## [지역별 환자 통계 데이터]\n"
        f"```json\n{_json_r.dumps(_ai_ctx, ensure_ascii=False, indent=2)[:6000]}\n```"
    )
 
    # ── 빠른 분석 버튼 4개
    _quick_r = [
        (
            "🔍 종합 분석",
            "위 데이터를 기반으로 지역 유입 패턴, 의존도 리스크, 영향권 변화, "
            "이상징후, 마케팅 전략을 포함한 종합 경영 컨설팅 보고서를 작성해주세요.",
        ),
        (
            "📍 지역 의존도",
            f"{'전체' if _sel_dept == '전체' else _sel_dept} 데이터에서 특정 지역 의존도(편중도)를 "
            "분석하고, 의존도 리스크와 지역 다변화 전략을 제시해주세요.",
        ),
        (
            "🚨 이상징후 탐지",
            "월별 데이터에서 환자수 급증·급감(30% 이상) 이상징후를 탐지하고, "
            "원인 가설 3가지와 각 대응 방안을 제시해주세요.",
        ),
        (
            "🎯 진료권 확대 전략",
            "환자 유입 데이터를 기반으로 진료권 확대 가능 지역을 선정하고, "
            "지역별 마케팅 전략과 구체적 실행 계획을 컨설팅 보고서로 작성해주세요.",
        ),
    ]
    _qr_cols = st.columns(len(_quick_r), gap="small")
    for _qi2, (_ql2, _qv2) in enumerate(_quick_r):
        with _qr_cols[_qi2]:
            if st.button(_ql2, key=f"reg_qs_{_qi2}", use_container_width=True, type="secondary"):
                st.session_state["reg_chat_prefill"] = _qv2
                st.rerun()
 
    # ── 채팅 히스토리 초기화 버튼
    if st.session_state.get("reg_chat_history"):
        if st.button("🗑️ 대화 초기화", key="reg_chat_clear", type="secondary"):
            st.session_state["reg_chat_history"] = []
            st.rerun()
 
    # ── 채팅 히스토리 렌더링
    if "reg_chat_history" not in st.session_state:
        st.session_state["reg_chat_history"] = []
    _reg_history = st.session_state["reg_chat_history"]
 
    for _msg in _reg_history:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])
 
    # ── 입력 처리 (prefill 또는 직접 입력)
    _reg_prefill = st.session_state.pop("reg_chat_prefill", None)
    _reg_input   = (
        st.chat_input("지역별 경영 분석을 질문하세요", key="reg_chat_input")
        or _reg_prefill
    )
 
    if _reg_input:
        with st.chat_message("user"):
            st.markdown(_reg_input)
        _reg_history.append({"role": "user", "content": _reg_input})
 
        with st.chat_message("assistant"):
            _ph2 = st.empty()
            _toks2: list = []
            _full2 = ""
            try:
                from core.llm import get_llm_client
                _llm2 = get_llm_client()
                # 시스템 프롬프트 6000자 초과 시 안전 절단
                _safe_sys = (
                    _sys_consulting[:5500] + "\n...(생략)"
                    if len(_sys_consulting) > 5500
                    else _sys_consulting
                )
                for _tok2 in _llm2.generate_stream(
                    _reg_input,
                    _safe_sys,
                    request_id=_uuid_r.uuid4().hex[:8],
                ):
                    _toks2.append(_tok2)
                    if len(_toks2) % 4 == 0:
                        _ph2.markdown("".join(_toks2) + "▌")
                _full2 = "".join(_toks2)
            except Exception as _e2:
                # LLM 실패 시 데이터 요약만 제공 (폴백)
                _top3_str = " / ".join(
                    f"{r['지역']} {r['환자수']:,}명"
                    for r in list(_dept_region_ctx.values())[0][:3]
                    if _dept_region_ctx
                ) or "데이터 없음"
                _full2 = (
                    f"**⚠️ LLM 연결 실패** `{_e2}`\n\n"
                    f"**현재 데이터 요약** (AI 분석 불가 시 참고)\n"
                    f"- 분석 과: **{_sel_dept}**\n"
                    f"- 총 환자: **{_total_patients:,}명** (최근 {_n_months}개월)\n"
                    f"- 1위 지역: **{_top1_region}** ({_top1_cnt:,}명)\n"
                    f"- 유입 지역수: **{_unique_regions}개** 시구\n"
                    f"- 상위 지역: {_top3_str}\n\n"
                    f"*LLM 서버 연결 후 재질문하시면 컨설팅 보고서를 제공합니다.*"
                )
            _ph2.markdown(_full2)
 
        _reg_history.append({"role": "assistant", "content": _full2})
        st.session_state["reg_chat_history"] = _reg_history
        st.rerun()
 
    st.markdown("</div>", unsafe_allow_html=True)  # AI 채팅 카드 닫기
 
 

# ════════════════════════════════════════════════════════════════════
# 카드 매칭 탭  (기존 _tab_card_match 그대로 — 내용 동일)
# ════════════════════════════════════════════════════════════════════
def _tab_card_match() -> None:
    import io, datetime as _dt_cm

    st.markdown(f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};padding:16px;">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="wd-sec"><span class="wd-sec-bar" style="background:{C["indigo"]};"></span>'
        f'💳 카드사 승인내역 ↔ 병원 결제 매칭'
        f'<span class="wd-sec-sub"> 정방향(카드사→병원) / 역방향(병원→카드사) 이중 검증</span></div>',
        unsafe_allow_html=True,
    )
    col_lbl, col_dt, col_dir, col_btn = st.columns([1,2,3,1], gap="small")
    with col_lbl:
        st.markdown(f'<div style="font-size:12px;font-weight:700;color:{C["t2"]};padding:8px 0 0 4px;">📅 입금일자</div>', unsafe_allow_html=True)
    with col_dt:
        _cm_date    = st.date_input("입금일자", value=st.session_state.get("cm_date",_dt_cm.date.today()),
                                    key="cm_date", label_visibility="collapsed", format="YYYY-MM-DD",
                                    max_value=_dt_cm.date.today(),
                                    help="병원 DB 조회 기준 날짜 (±2일 허용)")
        _cm_date_str = _cm_date.strftime("%Y%m%d")
    with col_dir:
        _direction  = st.radio("매칭 방향",
            options=["① 정방향 — 카드사 xlsx → 병원 DB 매칭","② 역방향 — 병원 DB → 카드사 xlsx 매칭"],
            key="cm_direction", label_visibility="collapsed", horizontal=True)
        _is_forward = "정방향" in _direction
    with col_btn:
        _do_match = st.button("🔍 매칭 실행", key="btn_card_match", type="primary", use_container_width=True)

    col_up, col_info = st.columns([4,6], gap="small")
    with col_up:
        uploaded = st.file_uploader("카드사 승인내역 xlsx", type=["xlsx","xls"], key="card_match_file",
                                    help="필수 컬럼: 승인일시, 승인번호, 승인금액")
    with col_info:
        st.markdown(
            f'<div style="background:#F0F4FF;border:1px solid #BFDBFE;border-radius:8px;padding:8px 14px;margin-top:4px;font-size:11.5px;color:{C["t2"]};">'
            f'<b>① 정방향</b>: 카드사 파일 기준 → 병원 DB 누락건 탐지<br>'
            f'<b>② 역방향</b>: 병원 DB 기준 → 카드사 파일 미확인건 탐지<br>'
            f'<span style="color:{C["t3"]};font-size:10.5px;">🔒 승인번호·카드번호는 AI 채팅 미전송</span></div>',
            unsafe_allow_html=True,
        )

    _d_from = (_dt_cm.datetime.strptime(_cm_date_str,"%Y%m%d")-_dt_cm.timedelta(days=2)).strftime("%Y%m%d")
    _d_to   = (_dt_cm.datetime.strptime(_cm_date_str,"%Y%m%d")+_dt_cm.timedelta(days=2)).strftime("%Y%m%d")
    _hosp_rows: List[Dict[str, Any]] = []; _db_ok = False; _db_err = ""
    try:
        from db.oracle_client import execute_query
        _sql_view = f"""
            SELECT 승인일시 AS 거래일자, REGEXP_REPLACE(승인번호,'[^0-9]','') AS 승인번호,
                   승인금액, NVL(카드사명,'') AS 카드사명, NVL(단말기ID,'') AS 단말기ID, NVL(설치위치,'') AS 설치위치
            FROM JAIN_WM.V_KIOSK_CARD_APPROVAL
            WHERE 승인일시 BETWEEN '{_d_from}' AND '{_d_to}'
            ORDER BY 승인일시
        """
        _rows_view = execute_query(_sql_view)
        if _rows_view is not None: _hosp_rows = _rows_view; _db_ok = True
    except Exception as _e1:
        _db_err = str(_e1); logger.error(f"[CardMatch] V_KIOSK_CARD_APPROVAL: {_e1}")

    if _db_ok:
        _db_badge = (f'<span style="background:{C["green"]}1A;color:{C["green"]};border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;">✅ DB 연결 ({len(_hosp_rows):,}건)</span>')
    else:
        _db_badge = (f'<span style="background:{C["red"]}1A;color:{C["red"]};border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;">❌ VIEW 조회 실패</span>'
                     f'<span style="font-size:10.5px;color:{C["t3"]};margin-left:6px;">DBeaver(관리자)에서 V_KIOSK_CARD_APPROVAL 생성 후 GRANT SELECT TO RAG_READONLY 실행</span>')
    st.markdown(f'<div style="margin:6px 0 8px;display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:11px;color:{C["t3"]};">병원 DB 현황:</span>{_db_badge}'
                f'<span style="font-size:10.5px;color:{C["t3"]};">{_cm_date_str} ±2일 / 총 {len(_hosp_rows):,}건</span></div>', unsafe_allow_html=True)

    _df_card = None
    if uploaded:
        try:
            import pandas as pd
            _bytes = uploaded.read()
            _df_raw = pd.read_excel(io.BytesIO(_bytes), dtype=str)
            _df_raw.columns = [str(c).strip() for c in _df_raw.columns]
            _missing = {"승인일시","승인번호","승인금액"} - set(_df_raw.columns)
            if _missing:
                st.error(f"❌ 필수 컬럼 없음: {', '.join(_missing)}")
            else:
                _df_card = _df_raw[_df_raw["거래결과"].str.contains("정상",na=False)].copy() if "거래결과" in _df_raw.columns else _df_raw.copy()
                _df_card["_apv_no"]   = _df_card["승인번호"].astype(str).str.strip().str.replace(r"\D","",regex=True)
                _df_card["_apv_amt"]  = pd.to_numeric(_df_card["승인금액"].astype(str).str.replace(r"[,￦₩\s]","",regex=True).str.replace(r"[^\d\-]","",regex=True),errors="coerce").fillna(0).astype(int)
                _df_card["_apv_date"] = pd.to_datetime(_df_card["승인일시"].astype(str).str[:10].str.replace(r"[/\-]","",regex=True),format="%Y%m%d",errors="coerce").dt.strftime("%Y%m%d")
                _df_card = _df_card[_df_card["_apv_amt"]>0].reset_index(drop=True)
                if "카드번호" in _df_card.columns:
                    _df_card["카드번호_표시"] = _df_card["카드번호"].astype(str).apply(
                        lambda v: v[:4]+"-****-****-"+v[-4:] if len(v.replace("-","").replace("*",""))>=8 else "****-****-****-****")
                with st.expander(f"📄 카드사 파일 — {len(_df_card):,}건 (정상승인)", expanded=False):
                    _prev_cols = [c for c in ["승인일시","승인번호","승인금액","카드사","카드번호_표시","거래결과","단말기ID","설치위치"] if c in _df_card.columns]
                    st.dataframe(_df_card[_prev_cols].rename(columns={"카드번호_표시":"카드번호(마스킹)"}).head(50), use_container_width=True, height=200)
        except Exception as _pe:
            st.error(f"❌ 파일 파싱 오류: {_pe}"); _df_card = None

    if not _is_forward and _hosp_rows:
        import pandas as pd
        with st.expander(f"🏥 병원 DB 조회 결과 — {len(_hosp_rows):,}건", expanded=True):
            st.dataframe(pd.DataFrame(_hosp_rows), use_container_width=True, height=260)

    if not _do_match and "card_match_result" not in st.session_state:
        if not uploaded:
            st.markdown(f'<div style="padding:30px;text-align:center;color:{C["t4"]};font-size:13px;">카드사 xlsx를 업로드하고 [매칭 실행] 버튼을 클릭하세요.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True); return

    if _do_match:
        import pandas as pd
        if not _db_ok and not _hosp_rows:
            st.error("❌ 병원 DB 연결 실패"); st.markdown("</div>", unsafe_allow_html=True); return
        if _df_card is None:
            st.warning("⚠️ 카드사 파일을 먼저 업로드하세요."); st.markdown("</div>", unsafe_allow_html=True); return
        _hosp_dict = {str(_hr.get("승인번호","") or "").strip().replace(" ",""): _hr for _hr in _hosp_rows if str(_hr.get("승인번호","") or "").strip()}
        _card_dict = {}
        for _, _crow in _df_card.iterrows():
            _cno = str(_crow.get("_apv_no","")).strip()
            if _cno: _card_dict[_cno] = _crow.to_dict()
        _results = []; _card_matched = set()
        if _is_forward:
            for _, _crow in _df_card.iterrows():
                _cno = str(_crow["_apv_no"]).strip(); _camt = int(_crow["_apv_amt"])
                _hrow = _hosp_dict.get(_cno)
                if _hrow:
                    _hamt = int(_hrow.get("승인금액",0) or 0)
                    _status = "정상" if _camt==_hamt else "금액불일치"; _card_matched.add(_cno)
                else:
                    _status = "누락"; _hrow = {}
                _results.append({"상태":_status,"거래일자":str(_crow.get("_apv_date",""))[:8],"승인번호":_cno,
                    "카드사금액":_camt,"병원금액":int(_hrow.get("승인금액",0) or 0),
                    "차이":_camt-int(_hrow.get("승인금액",0) or 0),
                    "카드사":str(_crow.get("카드사","")) if "카드사" in _df_card.columns else "",
                    "단말기ID":str(_crow.get("단말기ID","") or _hrow.get("단말기ID","")),
                    "설치위치":str(_crow.get("설치위치","") or _hrow.get("설치위치","")),"출처":"카드사→병원"})
            for _hno, _hr in _hosp_dict.items():
                if _hno not in _card_matched:
                    _results.append({"상태":"병원만","거래일자":str(_hr.get("거래일자",""))[:8],"승인번호":_hno,
                        "카드사금액":0,"병원금액":int(_hr.get("승인금액",0) or 0),
                        "차이":-int(_hr.get("승인금액",0) or 0),"카드사":str(_hr.get("카드사명","")),"단말기ID":str(_hr.get("단말기ID","")),"설치위치":str(_hr.get("설치위치","")),"출처":"병원만"})
        else:
            for _hno, _hr in _hosp_dict.items():
                _hamt = int(_hr.get("승인금액",0) or 0); _crow = _card_dict.get(_hno)
                if _crow: _camt = int(_crow.get("_apv_amt",0) or 0); _status = "정상" if _hamt==_camt else "금액불일치"; _card_matched.add(_hno)
                else:      _status = "병원만"; _crow = {}; _camt = 0
                _results.append({"상태":_status,"거래일자":str(_hr.get("거래일자",""))[:8],"승인번호":_hno,
                    "병원금액":_hamt,"카드사금액":_camt,"차이":_hamt-_camt,
                    "카드사":str(_hr.get("카드사명","")),"단말기ID":str(_hr.get("단말기ID","")),"설치위치":str(_hr.get("설치위치","")),"출처":"병원→카드사"})
            for _cno, _crow in _card_dict.items():
                if _cno not in _card_matched:
                    _camt = int(_crow.get("_apv_amt",0) or 0)
                    _results.append({"상태":"누락","거래일자":str(_crow.get("_apv_date",""))[:8],"승인번호":_cno,
                        "병원금액":0,"카드사금액":_camt,"차이":_camt,
                        "카드사":str(_crow.get("카드사","")) if "카드사" in _df_card.columns else "",
                        "단말기ID":str(_crow.get("단말기ID","")),"설치위치":str(_crow.get("설치위치","")),"출처":"카드사만"})
        st.session_state["card_match_result"] = _results
        st.session_state["card_match_dir"]    = "정방향" if _is_forward else "역방향"
        st.session_state["card_match_date"]   = _cm_date_str

    _results   = st.session_state.get("card_match_result",[])
    _match_dir = st.session_state.get("card_match_dir","정방향")
    if not _results: st.markdown("</div>", unsafe_allow_html=True); return

    _cnt_ok   = sum(1 for r in _results if r["상태"]=="정상")
    _cnt_miss = sum(1 for r in _results if r["상태"]=="누락")
    _cnt_amt  = sum(1 for r in _results if r["상태"]=="금액불일치")
    _cnt_hosp = sum(1 for r in _results if r["상태"]=="병원만")
    _total    = len(_results)
    _match_rate = round(_cnt_ok/max(_cnt_ok+_cnt_miss+_cnt_amt,1)*100,1)
    _gap()
    kc1,kc2,kc3,kc4,kc5 = st.columns(5, gap="small")
    def _cm_kpi(col,icon,label,val,color,sub=""):
        col.markdown(f'<div class="fn-kpi" style="border-top:3px solid {color};min-height:90px;">'
                     f'<div class="fn-kpi-icon">{icon}</div><div class="fn-kpi-label" style="font-size:9px;">{label}</div>'
                     f'<div class="fn-kpi-value" style="color:{color};font-size:26px;">{val}</div>'
                     f'<div class="fn-kpi-sub">{sub}</div></div>', unsafe_allow_html=True)
    _cm_kpi(kc1,"✅","정상 매칭",  f"{_cnt_ok:,}건",   C["green"],  f"매칭률 {_match_rate}%")
    _cm_kpi(kc2,"🔴","누락",       f"{_cnt_miss:,}건", C["red"],    "즉시 확인 필요")
    _cm_kpi(kc3,"🟡","금액불일치", f"{_cnt_amt:,}건",  C["yellow"], "금액 다름")
    _cm_kpi(kc4,"🟠","병원만",     f"{_cnt_hosp:,}건", C["orange"], "카드사 재확인")
    _cm_kpi(kc5,"📋",f"전체({_match_dir})",f"{_total:,}건",C["t2"],f"{_cm_date_str} 기준")
    _gap()
    _flt_c, _dl_c = st.columns([7,3], gap="small")
    with _flt_c:
        _flt_status = st.multiselect("상태 필터",options=["정상","누락","금액불일치","병원만"],
                                     default=["누락","금액불일치","병원만"],key="cm_flt_status",label_visibility="collapsed")
    with _dl_c:
        import pandas as _pd_dl
        _dl_csv = _pd_dl.DataFrame(_results).to_csv(index=False,encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("⬇️ 전체 결과 CSV",data=_dl_csv,
            file_name=f"카드매칭_{_match_dir}_{_cm_date_str}.csv",mime="text/csv",key="btn_cm_dl",use_container_width=True)

    _filtered = [r for r in _results if r["상태"] in (_flt_status or ["정상","누락","금액불일치","병원만"])]
    _STATUS_STYLE = {
        "정상":("#DCFCE7","#15803D","#059669","✅ 정상"),
        "누락":("#FEE2E2","#991B1B","#DC2626","🔴 누락"),
        "금액불일치":("#FEF3C7","#92400E","#D97706","🟡 금액차이"),
        "병원만":("#FFF7ED","#9A3412","#EA580C","🟠 병원만"),
    }
    _TH2 = "padding:7px 10px;font-size:10.5px;font-weight:700;color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
    _tbl = (
        '<div style="overflow-x:auto;max-height:500px;overflow-y:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
        '<thead style="position:sticky;top:0;z-index:2;"><tr>'
        f'<th style="{_TH2}text-align:center;width:90px;">상태</th>'
        f'<th style="{_TH2}text-align:center;width:80px;">거래일자</th>'
        f'<th style="{_TH2}text-align:left;width:95px;">승인번호</th>'
        f'<th style="{_TH2}text-align:right;width:90px;">카드사금액</th>'
        f'<th style="{_TH2}text-align:right;width:90px;">병원금액</th>'
        f'<th style="{_TH2}text-align:right;width:80px;">차이</th>'
        f'<th style="{_TH2}text-align:left;">카드사</th>'
        f'<th style="{_TH2}text-align:left;">단말기</th>'
        f'<th style="{_TH2}text-align:left;">설치위치</th>'
        '</tr></thead><tbody>'
    )
    _fmta = lambda v: f"{v:,}" if v else "─"
    _fmtd = lambda v: (f'<span style="color:#DC2626;font-weight:700;">▲{v:,}</span>' if v>0
                       else f'<span style="color:#2563EB;font-weight:700;">▼{abs(v):,}</span>' if v<0 else "─")
    for _i, _r in enumerate(_filtered[:500]):
        _st = _r["상태"]
        _bg, _tx, _ac, _badge = _STATUS_STYLE.get(_st, ("#F8FAFC","#334155","#334155",_st))
        _rbg = _bg if _st!="정상" else ("#F8FAFC" if _i%2==0 else "#FFFFFF")
        _td2 = f"padding:6px 10px;background:{_rbg};border-bottom:1px solid #F0F4F8;"
        _tbl += (
            f"<tr><td style='{_td2}text-align:center;'>"
            f'<span style="background:{_bg};color:{_ac};border-radius:5px;padding:2px 7px;font-size:10.5px;font-weight:700;">{_badge}</span></td>'
            f'<td style="{_td2}text-align:center;font-family:Consolas,monospace;color:{C["t3"]};font-size:11.5px;">{_r["거래일자"]}</td>'
            f'<td style="{_td2}font-family:Consolas,monospace;font-weight:600;color:{C["t1"]};font-size:11.5px;">{_r["승인번호"]}</td>'
            f'<td style="{_td2}text-align:right;font-family:Consolas,monospace;color:{C["blue"]};">{_fmta(_r["카드사금액"])}</td>'
            f'<td style="{_td2}text-align:right;font-family:Consolas,monospace;color:{C["indigo"]};">{_fmta(_r["병원금액"])}</td>'
            f'<td style="{_td2}text-align:right;">{_fmtd(_r["차이"])}</td>'
            f'<td style="{_td2}color:{C["t2"]};">{_r.get("카드사","") or "─"}</td>'
            f'<td style="{_td2}color:{C["t3"]};font-size:11.5px;">{_r.get("단말기ID","") or "─"}</td>'
            f'<td style="{_td2}color:{C["t2"]};">{_r.get("설치위치","") or "─"}</td></tr>'
        )
    if len(_filtered)>500:
        _tbl += f'<tr><td colspan="9" style="padding:8px;text-align:center;color:{C["t3"]};font-size:11px;">... 이하 {len(_filtered)-500:,}건 생략 — CSV 다운로드 이용</td></tr>'
    if not _filtered:
        _tbl += f'<tr><td colspan="9" style="padding:30px;text-align:center;color:{C["t4"]};">필터 조건에 맞는 데이터 없음</td></tr>'
    st.markdown(_tbl+"</tbody></table></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #F1F5F9;font-size:10.5px;">'
        f'<span style="color:{C["green"]};font-weight:700;">✅ 정상: 승인번호+금액 일치</span>'
        f'<span style="color:{C["red"]};font-weight:700;">🔴 누락: 한쪽에만 존재</span>'
        f'<span style="color:{C["yellow"]};font-weight:700;">🟡 금액불일치</span>'
        f'<span style="color:{C["orange"]};font-weight:700;">🟠 병원만: 카드사 재확인</span>'
        f'<span style="color:{C["t3"]};">🔒 승인번호·카드번호 → AI 채팅 미전송</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 메인 진입점 — render_finance_dashboard  v2.3
# ════════════════════════════════════════════════════════════════════
def render_finance_dashboard() -> None:
    """원무 현황 대시보드 v2.3 — 4탭 구조."""
    st.markdown(APP_CSS, unsafe_allow_html=True)  # 2026-04-22: _CSS → APP_CSS (design.py 단일화)

    logger.info("render_finance_dashboard 시작")
    oracle_ok = False
    try:
        from db.oracle_client import test_connection
        oracle_ok, _ = test_connection()
        if not oracle_ok:
            logger.warning("Oracle 연결 확인: 실패 — 데모 모드로 전환")
    except Exception as _e:
        logger.warning(f"Oracle 연결 확인 예외: {_e}")

    import datetime as _dt_main
    _is_custom = st.session_state.get("fn_use_custom_date", False)
    if _is_custom:
        _sel_d = st.session_state.get("fn_sel_date", _dt_main.date.today())
        _qdate = _sel_d.strftime("%Y%m%d") if isinstance(_sel_d, _dt_main.date) else str(_sel_d).replace("-","")[:8]
    else:
        _qdate = ""

    # ── 실시간 데이터 (날짜 무관)
    opd_kpi      = (_fq("opd_kpi") or [{}])[0]
    dept_status  = _fq("opd_dept_status")
    kiosk_status = _fq("kiosk_status")
    # ── 날짜 적용 데이터
    _q = _qdate if _is_custom else ""
    kiosk_by_dept       = _fq("kiosk_by_dept",       _q)
    kiosk_counter_trend = _fq("kiosk_counter_trend", _q)
    discharge_pipe      = _fq("discharge_pipeline",  _q)
    opd_dept_trend      = _fq("opd_dept_trend",      _q)
    ipd_dept_trend      = _fq("ipd_dept_trend",      _q)   # 신규
    bed_detail          = _fq("ward_bed_detail",      _q)
    ward_room_detail    = _fq("ward_room_detail")
    daily_dept_stat     = _fq("daily_dept_stat",     _q)
    day_inweon          = _fq("day_inweon",           _q)
    # ── 수납 (항상 오늘)
    finance_today    = _fq("finance_today")
    finance_trend    = _fq("finance_trend")
    finance_by_dept  = _fq("finance_by_dept")
    overdue_stat     = _fq("overdue_stat")
    # ── 주간/월간 분석
    los_dist_dept    = _fq("los_dist_dept")            # 신규 — 날짜 무관(현재 재원)
    monthly_opd_dept = _fq("monthly_opd_dept")         # 신규 — 최근 12개월
    region_dept_data    = []   # 지역별 탭 온디맨드 로드 (_tab_region 내부 처리)
    region_monthly_data = []   # 지역별 탭 온디맨드 로드 (_tab_region 내부 처리)

    # ── 탑바
    st.markdown('<div class="fn-topbar"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([4, 3, 5], vertical_alignment="center")
    with c1:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
            f'<div style="width:3px;height:22px;background:{C["blue"]};border-radius:2px;"></div>'
            f'<div><div style="font-size:9px;font-weight:700;color:{C["t4"]};text-transform:uppercase;letter-spacing:.15em;">좋은문화병원</div>'
            f'<div style="font-size:17px;font-weight:800;color:{C["t1"]};letter-spacing:-.03em;">💼 원무 현황</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        b1, b2 = st.columns(2, gap="small")
        with b1:
            if st.button("🔄 새로고침", key="fn_refresh", use_container_width=True, type="secondary"):
                st.cache_data.clear(); st.rerun()
        with b2:
            st.markdown(
                '<a href="http://192.1.1.231:8501" target="_blank" style="'
                'display:block;text-align:center;background:#EFF6FF;color:#1E40AF;'
                'border:1.5px solid #BFDBFE;border-radius:20px;padding:5px 0;'
                'font-size:11.5px;font-weight:600;text-decoration:none;">🔗 병동 대시보드</a>',
                unsafe_allow_html=True,
            )
    with c3:
        _dc1, _dc2 = st.columns([2, 3], gap="small")
        with _dc1:
            _oc = C["green"] if oracle_ok else C["yellow"]
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:5px;padding:6px 0;">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{_oc};flex-shrink:0;display:inline-block;"></span>'
                f'<span style="font-size:11px;font-weight:700;color:{_oc};white-space:nowrap;">{"Oracle 연결" if oracle_ok else "Oracle 미연결"}</span></div>',
                unsafe_allow_html=True,
            )
        with _dc2:
            _use_custom = st.toggle("📅 날짜 지정", value=st.session_state.get("fn_use_custom_date",False), key="fn_use_custom_date")
            if st.session_state.get("fn_use_custom_date", False):
                st.date_input("", value=st.session_state.get("fn_sel_date",_dt_main.date.today()),
                              key="fn_sel_date", label_visibility="collapsed", format="YYYY-MM-DD", max_value=_dt_main.date.today())
                _shown = st.session_state.get("fn_sel_date",_dt_main.date.today())
                st.markdown(f'<div style="font-size:10px;color:{C["indigo"]};font-weight:700;text-align:right;">📅 {_shown} 기준</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="font-size:11px;color:{C["t3"]};font-family:Consolas,monospace;padding:2px 0;text-align:right;">{time.strftime("%Y-%m-%d %H:%M")}</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:1px;background:#F1F5F9;margin:0 0 6px;"></div>', unsafe_allow_html=True)

    if not oracle_ok:
        _ms = [
            "V_OPD_DEPT_STATUS","V_KIOSK_STATUS","V_DISCHARGE_PIPELINE",
            "V_FINANCE_TODAY","V_FINANCE_TREND","V_FINANCE_BY_DEPT","V_OVERDUE_STAT",
            "V_IPD_DEPT_TREND(신규)","V_LOS_DIST_DEPT(신규)","V_MONTHLY_OPD_DEPT(신규)",
             "V_region_dept_daily(지역분석·신규)"
        ]
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:8px 14px;margin-bottom:8px;">'
            f'<b style="font-size:13px;color:#92400E;">⚠️ Oracle 미연결 — 아래 VIEW 생성 필요</b>'
            f'<div style="font-size:11px;color:#B45309;margin-top:3px;">{" / ".join(_ms)}</div></div>',
            unsafe_allow_html=True,
        )

    # ════════════════════════════════════════════════════════════════
    # 5탭 구조
    # ════════════════════════════════════════════════════════════════
    t1, t_weekly, t_monthly, t_region, t_card = st.tabs([
        "🏥 실시간 현황",
        "📈 주간추이분석",
        "📅 월간추이분석",
        "📍 지역별 통계",    # ← 신규
        "💳 카드 매칭",
    ])

    with t1:
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
        _tab_analytics(
            opd_dept_trend=opd_dept_trend,
            los_dist_dept=los_dist_dept,
            daily_dept_stat=daily_dept_stat,
            ipd_dept_trend=ipd_dept_trend,
        )

    with t_monthly:
        _tab_monthly(monthly_opd_dept, region_monthly_data)

    with t_region:
        _tab_region(region_dept_data, region_monthly_data)

    with t_card:
        _tab_card_match()

    # ── AI 채팅 (하단 공통 — 카드 매칭 데이터 제외)
    _gap()
    _render_finance_llm_chat(
        bed_detail=bed_detail,
        dept_status=dept_status,
        kiosk_by_dept=kiosk_by_dept,
        daily_dept_stat=daily_dept_stat,
        kiosk_counter_trend=kiosk_counter_trend,
        discharge_pipe=discharge_pipe,
    )

    # ── 자동 갱신
    if st.session_state.get("fn_auto", False):
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=300_000, key="fn_autorefresh")
        except ImportError:
            st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)