"""
ui/panels/_shared.py — 원무 대시보드 패널 공유 유틸리티 (2026-05-07 v2.1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모든 finance_panel/*.py 파일이 공통으로 사용하는 임포트·쿼리딕셔너리·헬퍼.
finance_dashboard.py 도 여기서 역임포트해 중복 정의 없이 사용한다.

[v2.1 변경 — 2026-05-07]
  · _fq() 에 @st.cache_data(ttl=1800) 추가 → DB 부하 감소
    · 30분 캐시: 분석성 데이터(월간·지역·진료과)에 적합
    · 새로고침 버튼(st.cache_data.clear()) 으로 언제든 강제 갱신 가능
    · 실시간 지표(KPI·수납·수술 등)도 캐시됨 — 부하가 심하면 수용 가능한 트레이드오프

[포함 항목]
  · Oracle 쿼리 딕셔너리 FQ / FQ_HIST
  · _fq()  — 날짜 치환 포함 Oracle 조회 래퍼 (캐시 포함)
  · logger, HAS_PLOTLY, go
  · design.py 하위 호환 별칭 (_kpi_card, _sec_hd, _gap, _fmt_won 등)
"""
from __future__ import annotations

import sys
import threading
import datetime as _dt_import
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 프로젝트 루트 sys.path 등록 ────────────────────────────────────────
_HERE = Path(__file__).resolve().parent          # ui/panels/
_ROOT = _HERE.parent.parent                      # guidbot/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    go = None          # type: ignore[assignment]
    HAS_PLOTLY = False

try:
    from utils.logger import get_logger as _gl
    from config.settings import settings as _s
    logger = _gl("finance_panels", log_dir=_s.log_dir)
except Exception:
    import logging as _l
    logger = _l.getLogger("finance_panels")
    if not logger.handlers:
        _h = _l.StreamHandler()
        _h.setFormatter(_l.Formatter(
            "[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(_h)
        logger.setLevel(_l.DEBUG)

# ── design.py 토큰 임포트 ──────────────────────────────────────────────
from ui.design import (
    C, APP_CSS, PLOTLY_PALETTE, PLOTLY_CFG,
    kpi_card, section_header, gap, fmt_won, empty_state,
)

# ── 하위 호환 별칭 (기존 panel 코드 호출부 무변경 유지) ─────────────────
_kpi_card      = kpi_card
_sec_hd        = section_header
_gap           = gap
_fmt_won       = fmt_won
_plotly_empty  = empty_state
_PALETTE       = PLOTLY_PALETTE
_PLOTLY_LAYOUT = PLOTLY_CFG

# ════════════════════════════════════════════════════════════════════
# Oracle 쿼리 딕셔너리 — v2.3 (finance_dashboard.py 에서 이전)
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
    "opd_dept_trend":  "SELECT * FROM JAIN_WM.V_OPD_DEPT_TREND ORDER BY 기준일, 외래환자수 DESC",
    "ipd_dept_trend":  "SELECT * FROM JAIN_WM.V_IPD_DEPT_TREND ORDER BY 기준일, 입원환자수 DESC",
    "los_dist_dept":   "SELECT * FROM JAIN_WM.V_LOS_DIST_DEPT ORDER BY 진료과명, 구간순서",
    # ── 월간추이분석 ────────────────────────────────────────────────
    "monthly_opd_dept": (
        "SELECT * FROM JAIN_WM.V_MONTHLY_OPD_DEPT ORDER BY 기준년월 DESC, 진료과명"
    ),
    # ── 지역별 환자 통계 ────────────────────────────────────────────
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

# ── 기간 VIEW 쿼리 (과거 날짜 조회) ────────────────────────────────────
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
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' ORDER BY 진료과명, 구분"
    ),
    "ward_bed_detail": (
        "SELECT * FROM JAIN_WM.V_WARD_BED_HIST "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' ORDER BY 병동명"
    ),
    "opd_dept_trend": (
        "SELECT * FROM JAIN_WM.V_OPD_DEPT_TREND "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "AND TO_DATE('{d}','YYYYMMDD') ORDER BY 기준일, 외래환자수 DESC"
    ),
    "ipd_dept_trend": (
        "SELECT * FROM JAIN_WM.V_IPD_DEPT_TREND_HIST "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "AND TO_DATE('{d}','YYYYMMDD') ORDER BY 기준일, 입원환자수 DESC"
    ),
    "kiosk_counter_trend": (
        "SELECT * FROM JAIN_WM.V_KIOSK_COUNTER_TREND "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "AND TO_DATE('{d}','YYYYMMDD') ORDER BY 기준일"
    ),
    "finance_trend": (
        "SELECT * FROM JAIN_WM.V_FINANCE_TREND "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' ORDER BY 기준일"
    ),
}

_TODAY_STR: str = _dt_import.date.today().strftime("%Y%m%d")


@st.cache_data(ttl=1800, show_spinner=False)
def _fq(key: str, date_str: str = "", max_rows: int = 5000) -> List[Dict[str, Any]]:
    """
    FQ / FQ_HIST 에서 쿼리 선택 후 Oracle 조회 (날짜 치환 포함).

    [캐시 정책 — 2026-05-07]
    · ttl=1800 (30분): Streamlit rerun 마다 반복 실행되던 DB 쿼리 방지
    · 특히 진료과 분석 탭의 monthly_opd_dept (전체 13개월) 반복 조회 해소
    · 강제 갱신: 대시보드의 새로고침 버튼 → st.cache_data.clear() 로 즉시 초기화
    """
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


def _fq_parallel(
    query_specs: List[Tuple[str, str, str]],
    max_workers: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    여러 _fq() 호출을 ThreadPoolExecutor 로 병렬 실행.

    직렬 10개 순차 실행(2-5초) → 병렬 실행(0.5-1초) 개선.
    각 쿼리는 @st.cache_data 캐시 히트 시 즉시 반환됨.

    Args:
        query_specs: [(result_name, fq_key, date_str), ...] 리스트
        max_workers: 최대 동시 스레드 수 (Oracle pool_max=10 초과 방지)

    Returns:
        {result_name: rows} 딕셔너리 — 실패 시 빈 리스트
    """
    # Streamlit 스크립트 컨텍스트를 워커 스레드에 전파 (cache_data 안전 실행)
    _ctx = None
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        _ctx = get_script_run_ctx()
    except Exception:
        pass

    def _worker(name: str, key: str, date_str: str) -> Tuple[str, List]:
        if _ctx is not None:
            try:
                from streamlit.runtime.scriptrunner import add_script_run_ctx
                add_script_run_ctx(threading.current_thread(), _ctx)
            except Exception:
                pass
        try:
            return name, _fq(key, date_str)
        except Exception as exc:
            logger.warning("[Finance] 병렬 쿼리 실패 (%s): %s", name, exc)
            return name, []

    results: Dict[str, List] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_worker, name, key, date_str): name
            for name, key, date_str in query_specs
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result_name, data = future.result()
                results[result_name] = data
            except Exception as exc:
                logger.warning("[Finance] 병렬 결과 수집 실패 (%s): %s", name, exc)
                results[name] = []

    return results
