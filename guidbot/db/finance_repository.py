"""
db/finance_repository.py  ─  원무 대시보드 Oracle 데이터 접근 계층
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[리팩토링 이유]
  기존 ui/finance_dashboard.py 에 FQ(실시간), FQ_HIST(과거날짜)
  딕셔너리와 _fq() 쿼리 실행 함수가 모두 들어있었음.
  이 파일로 분리하여 DB 접근 책임을 단일화한다.

[책임]
  · 실시간 쿼리 딕셔너리 (FQ) - 항상 최신 데이터
  · 과거날짜 쿼리 딕셔너리 (FQ_HIST) - {d} 포맷 파라미터
  · 날짜 분기 쿼리 실행 (_fq / FinanceRepository.get)

[사용 방법]
  # 기존 finance_dashboard.py 코드 (변경 전)
  opd_kpi = (_fq("opd_kpi") or [{}])[0]
  dept_status = _fq("opd_dept_status")

  # 변경 후
  from db.finance_repository import finance_repo
  opd_kpi = finance_repo.get_one("opd_kpi")
  dept_status = finance_repo.get("opd_dept_status")
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)

_TODAY_STR: str = datetime.date.today().strftime("%Y%m%d")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 실시간 쿼리 딕셔너리 (FQ)
# 기존 finance_dashboard.py 의 FQ = {...} 를 그대로 이동
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FQ: Dict[str, str] = {
    # ── 외래 현황 (실시간) ─────────────────────────────────────────
    "opd_kpi":          "SELECT * FROM JAIN_WM.V_OPD_KPI WHERE ROWNUM = 1",
    "opd_dept_status":  "SELECT * FROM JAIN_WM.V_OPD_DEPT_STATUS ORDER BY 대기수 DESC",
    "kiosk_status":     "SELECT * FROM JAIN_WM.V_KIOSK_STATUS ORDER BY 키오스크ID",
    "ward_room_detail": "SELECT * FROM JAIN_WM.V_WARD_ROOM_DETAIL ORDER BY 병동명, 병실번호",

    # ── 수납·미수금 (항상 오늘) ────────────────────────────────────
    "finance_today":    "SELECT * FROM JAIN_WM.V_FINANCE_TODAY ORDER BY 금액 DESC",
    "finance_trend":    "SELECT * FROM JAIN_WM.V_FINANCE_TREND ORDER BY 기준일",
    "finance_by_dept":  "SELECT * FROM JAIN_WM.V_FINANCE_BY_DEPT ORDER BY 수납금액 DESC",
    "overdue_stat":     "SELECT * FROM JAIN_WM.V_OVERDUE_STAT ORDER BY 연령구분",

    # ── 분석 (날짜 무관 — 현재 재원 기준) ──────────────────────────
    "los_dist_dept":    "SELECT * FROM JAIN_WM.V_LOS_DIST_DEPT ORDER BY 진료과명, 구간순서",
    "monthly_opd_dept": (
        "SELECT * FROM JAIN_WM.V_MONTHLY_OPD_DEPT ORDER BY 기준년월 DESC, 진료과명"
    ),
    "region_dept_daily": (
        "SELECT 기준일자, 진료과명, 지역, 환자수 "
        "FROM JAIN_WM.region_dept_daily "
        "ORDER BY 기준일자 DESC, 진료과명, 환자수 DESC"
    ),

    # ── 퇴원 파이프라인 (실시간) ───────────────────────────────────
    "discharge_pipeline": "SELECT * FROM JAIN_WM.V_DISCHARGE_PIPELINE ORDER BY 단계, 병동명",
    "ward_bed_detail":    "SELECT * FROM JAIN_WM.V_WARD_BED_DETAIL ORDER BY 병동명",

    # ── 주간 추이 (실시간 7일) ─────────────────────────────────────
    "opd_dept_trend":  "SELECT * FROM JAIN_WM.V_OPD_DEPT_TREND ORDER BY 기준일, 외래환자수 DESC",
    "ipd_dept_trend":  "SELECT * FROM JAIN_WM.V_IPD_DEPT_TREND ORDER BY 기준일, 입원환자수 DESC",
    "kiosk_counter_trend": (
        "SELECT * FROM JAIN_WM.V_KIOSK_COUNTER_TREND ORDER BY 기준일"
    ),

    # ── 진료과별 배분 ─────────────────────────────────────────────
    "kiosk_by_dept": (
        "SELECT * FROM JAIN_WM.V_KIOSK_BY_DEPT ORDER BY "
        "CASE WHEN TRIM(진료과)='*내분비내과' THEN 1 WHEN TRIM(진료과)='*호흡기내과' THEN 2 "
        "WHEN TRIM(진료과)='*소화기내과' THEN 3 WHEN TRIM(진료과)='*신장내과' THEN 4 "
        "WHEN TRIM(진료과)='*순환기내과' THEN 5 WHEN TRIM(진료과)='인공신장실' THEN 6 "
        "WHEN TRIM(진료과)='신경과' THEN 7 WHEN TRIM(진료과)='가정의학과' THEN 8 "
        "WHEN TRIM(진료과)='신경외과' THEN 9 WHEN TRIM(진료과)='*유방센터' THEN 10 "
        "WHEN TRIM(진료과)='*위장관센터' THEN 11 WHEN TRIM(진료과)='*갑상선센터' THEN 12 "
        "WHEN TRIM(진료과)='성형외과' THEN 13 WHEN TRIM(진료과)='정형외과' THEN 14 "
        "WHEN TRIM(진료과)='*OBGY' THEN 15 WHEN TRIM(진료과)='*난임센터' THEN 16 "
        "WHEN TRIM(진료과)='소아청소년과' THEN 17 WHEN TRIM(진료과)='이비인후과' THEN 18 "
        "WHEN TRIM(진료과)='피부과' THEN 19 WHEN TRIM(진료과)='응급의학과' THEN 20 "
        "WHEN TRIM(진료과)='외부의뢰' THEN 21 WHEN TRIM(진료과)='진단검사' THEN 22 "
        "ELSE 23 END ASC, REPLACE(진료과,'*'), "
        "CASE WHEN SUBSTR(진료과,1,1)='*' THEN 2 ELSE 1 END"
    ),
    "day_inweon": (
        "SELECT 진료과, 외래계, 입원계, 퇴원계, 재원계, "
        '\"예방(독감)\", \"예방(AZ,JS,NV)\", \"예방(MD)\", \"예방(FZ)\", 예방주사계 '
        "FROM JAIN_WM.V_DAY_INWEON_3 "
        "ORDER BY CASE WHEN 진료과 = '총합계' THEN 99 ELSE 1 END, 진료과"
    ),
    "daily_dept_stat": (
        "SELECT * FROM JAIN_WM.V_DAILY_DEPT_STAT ORDER BY 진료과명, 구분"
    ),
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 과거날짜 쿼리 딕셔너리 (FQ_HIST)
# {d}, {d_prev}, {d_next} 포맷 파라미터 사용
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
                   SUM("예방(독감)"),SUM("예방(AZ,JS,NV)"),SUM("예방(MD)"),
                   SUM("예방(FZ)"),SUM(예방주사계)
            FROM JAIN_WM.V_DAY_INWEON_3 GROUP BY 일자
        )
        WHERE 일자 = '{d}'
        ORDER BY
            CASE WHEN 진료과 = '총합계' THEN 19 ELSE 10 END,
            CASE
                WHEN TRIM(진료과)='*내분비내과' THEN 1
                WHEN TRIM(진료과)='*호흡기내과' THEN 2
                WHEN TRIM(진료과)='*소화기내과' THEN 3
                WHEN TRIM(진료과)='*신장내과'   THEN 4
                WHEN TRIM(진료과)='*순환기내과' THEN 5
                ELSE 23
            END ASC
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
        "AND TO_DATE('{d}','YYYYMMDD') "
        "ORDER BY 기준일, 외래환자수 DESC"
    ),
    "ipd_dept_trend": (
        "SELECT * FROM JAIN_WM.V_IPD_DEPT_TREND_HIST "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "AND TO_DATE('{d}','YYYYMMDD') "
        "ORDER BY 기준일, 입원환자수 DESC"
    ),
    "kiosk_counter_trend": (
        "SELECT * FROM JAIN_WM.V_KIOSK_COUNTER_TREND "
        "WHERE 기준일 BETWEEN TO_DATE('{d}','YYYYMMDD') - 6 "
        "AND TO_DATE('{d}','YYYYMMDD') "
        "ORDER BY 기준일"
    ),
    "finance_trend": (
        "SELECT * FROM JAIN_WM.V_FINANCE_TREND "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' "
        "ORDER BY 기준일"
    ),
    "discharge_pipeline": (
        "SELECT * FROM JAIN_WM.V_DISCHARGE_PIPELINE_HIST "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' "
        "ORDER BY 단계, 병동명"
    ),
    "kiosk_by_dept": (
        "SELECT * FROM JAIN_WM.V_KIOSK_BY_DEPT_HIST "
        "WHERE TO_CHAR(기준일,'YYYYMMDD') = '{d}' "
        "ORDER BY 진료과"
    ),
}


class FinanceRepository:
    """
    원무 대시보드 전용 Oracle 데이터 접근 객체.

    [날짜 분기 로직]
    · date_str == "" or 오늘 → FQ 실시간 쿼리 사용
    · date_str = 과거날짜 → FQ_HIST 날짜 파라미터 쿼리 사용
    · FQ_HIST에 없는 키 → FQ 오늘 데이터로 대체 (경고 로그)
    """

    def get(
        self,
        key: str,
        date_str: str = "",
        ttl: int = 120,
    ) -> List[Dict[str, Any]]:
        """
        날짜 분기 TTL 캐시 쿼리 실행.

        기존 finance_dashboard.py 의 _fq() 함수를 메서드로 이동.

        Args:
            key:      FQ / FQ_HIST 딕셔너리 키
            date_str: 조회 날짜 "YYYYMMDD" 형식. 빈 문자열 = 오늘
            ttl:      캐시 유지 시간 (초, 기본 2분)

        Returns:
            쿼리 결과 딕셔너리 리스트. 실패 시 빈 리스트.
        """
        @st.cache_data(ttl=ttl, show_spinner=False)
        def _cached(k: str, d: str) -> List[Dict[str, Any]]:
            return self._execute(k, d)

        return _cached(key, date_str)

    def get_one(
        self,
        key: str,
        date_str: str = "",
    ) -> Dict[str, Any]:
        """
        쿼리 결과의 첫 행을 딕셔너리로 반환한다.
        KPI처럼 단일 행을 반환하는 쿼리에 사용한다.

        Returns:
            첫 번째 행 딕셔너리. 결과 없으면 빈 딕셔너리.
        """
        rows = self.get(key, date_str)
        return rows[0] if rows else {}

    def _execute(self, key: str, date_str: str) -> List[Dict[str, Any]]:
        """실제 쿼리 실행 (내부 메서드)."""
        _is_past = bool(
            date_str
            and len(date_str) == 8
            and date_str != _TODAY_STR
        )

        try:
            from db.oracle_client import execute_query

            if _is_past:
                if key in FQ_HIST:
                    # 날짜 파라미터 주입
                    _d_dt = datetime.datetime.strptime(date_str, "%Y%m%d")
                    _d_prev = (_d_dt - datetime.timedelta(days=1)).strftime("%Y%m%d")
                    _d_next = (_d_dt + datetime.timedelta(days=1)).strftime("%Y%m%d")
                    sql = FQ_HIST[key].format(
                        d=date_str, d_prev=_d_prev, d_next=_d_next
                    )
                    rows = execute_query(sql)
                else:
                    # FQ_HIST 미등록 → 오늘 데이터로 대체
                    logger.warning(
                        f"[FinanceRepo] '{key}' FQ_HIST 미등록 → 오늘 데이터로 대체."
                    )
                    if key not in FQ:
                        logger.error(f"[FinanceRepo] '{key}' FQ에도 없음.")
                        return []
                    rows = execute_query(FQ[key])
            else:
                # 실시간 쿼리
                if key not in FQ:
                    logger.error(f"[FinanceRepo] 미등록 쿼리 키: {key}")
                    return []
                rows = execute_query(FQ[key])

            return rows if rows else []

        except Exception as exc:
            logger.warning(
                f"[FinanceRepo] 쿼리 실패 ({key}, date={date_str}): "
                f"{type(exc).__name__}: {exc}"
            )
            return []

    # ── 자주 쓰는 편의 메서드 ─────────────────────────────────────

    def get_opd_kpi(self, date_str: str = "") -> Dict:
        return self.get_one("opd_kpi", date_str)

    def get_dept_status(self) -> List[Dict]:
        return self.get("opd_dept_status")

    def get_kiosk_status(self) -> List[Dict]:
        return self.get("kiosk_status")

    def get_finance_today(self) -> List[Dict]:
        return self.get("finance_today")

    def get_overdue_stat(self) -> List[Dict]:
        return self.get("overdue_stat")


# 전역 싱글톤 — finance_dashboard.py 에서 import해서 사용
finance_repo = FinanceRepository()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 하위 호환 래퍼
# finance_dashboard.py 의 _fq() 호출을 최소 수정으로 교체 가능
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fq(key: str, date_str: str = "") -> List[Dict[str, Any]]:
    """finance_dashboard.py 하위 호환용 래퍼."""
    return finance_repo.get(key, date_str)