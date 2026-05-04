"""
db/ward_repository.py  ─  병동 대시보드 Oracle 데이터 접근 계층
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[리팩토링 이유]
  기존에 ui/hospital_dashboard.py 안에 QUERIES 딕셔너리, _query(),
  _qc() 함수가 모두 있어 "UI가 DB를 직접 호출"하는 구조였음.
  이 파일로 분리하여 계층 분리 원칙을 지킨다.

[책임]
  · Oracle VIEW SQL 딕셔너리 관리 (QUERIES)
  · Circuit Breaker 패턴으로 장애 격리 (_query)
  · 2분 TTL 캐시 래퍼 (_qc / get_*)

[사용 방법]
  # 기존 hospital_dashboard.py 코드 (변경 전)
  dept_stay = _qc("ward_dept_stay")

  # 변경 후 (이 모듈 import)
  from db.ward_repository import ward_repo
  dept_stay = ward_repo.get("ward_dept_stay")
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, List

import streamlit as st

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Oracle VIEW 쿼리 딕셔너리
# 기존 hospital_dashboard.py 의 QUERIES 딕셔너리를 그대로 이동
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUERIES: Dict[str, str] = {
    # ── 병동 현황 ──────────────────────────────────────────────────
    "ward_dept_stay":       "SELECT * FROM JAIN_WM.V_WARD_DEPT_STAY ORDER BY 재원수 DESC",
    "ward_bed_detail":      "SELECT * FROM JAIN_WM.V_WARD_BED_DETAIL ORDER BY 병동명",
    "ward_op_stat":         "SELECT * FROM JAIN_WM.V_WARD_OP_STAT ORDER BY 수술건수 DESC",
    "ward_kpi_trend":       "SELECT * FROM JAIN_WM.V_WARD_KPI_TREND ORDER BY 기준일",
    "ward_yesterday":       "SELECT * FROM JAIN_WM.V_WARD_YESTERDAY ORDER BY 병동명",
    "ward_dx_today":        "SELECT * FROM JAIN_WM.V_WARD_DX_TODAY ORDER BY 기준일 DESC, 환자수 DESC",
    "ward_dx_trend":        "SELECT * FROM JAIN_WM.V_WARD_DX_TREND ORDER BY 기준일, 환자수 DESC",
    "admit_candidates":     "SELECT * FROM JAIN_WM.V_ADMIT_CANDIDATES ORDER BY 진료과명, 성별",
    "ward_room_detail":     "SELECT * FROM JAIN_WM.V_WARD_ROOM_DETAIL ORDER BY 병동명, 병실번호",
    # ── 재무 KPI (병동 탭에서도 사용) ─────────────────────────────
    "finance_kpi":          "SELECT * FROM JAIN_WM.V_FINANCE_TODAY WHERE ROWNUM = 1",
    "finance_overdue":      "SELECT * FROM JAIN_WM.V_OVERDUE_STAT",
    "finance_by_insurance": "SELECT * FROM JAIN_WM.V_FINANCE_BY_INS",
    # ── 외래 현황 ──────────────────────────────────────────────────
    "opd_kpi":              "SELECT * FROM JAIN_WM.V_OPD_KPI WHERE ROWNUM = 1",
    "opd_by_dept":          "SELECT * FROM JAIN_WM.V_OPD_BY_DEPT ORDER BY 환자수 DESC",
    "opd_hourly":           "SELECT * FROM JAIN_WM.V_OPD_HOURLY_STAT ORDER BY 시간대",
    "opd_noshow":           "SELECT * FROM JAIN_WM.V_NOSHOW_STAT WHERE ROWNUM = 1",
    # ── 간호 (nursing_dashboard.py 공유) ──────────────────────────
    "nursing_high_risk":    "SELECT * FROM JAIN_WM.V_WARD_HIGH_RISK ORDER BY 합계 DESC",
    "nursing_incident":     "SELECT * FROM JAIN_WM.V_WARD_INCIDENT ORDER BY 발생일시 DESC",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Circuit Breaker 상태 (Thread-safe)
# 기존 hospital_dashboard.py 의 _QUERY_FAIL_COUNT 등을 그대로 이동
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_FAIL_COUNT:   Dict[str, int]   = {}   # 연속 실패 카운터
_CIRCUIT_OFF:  Dict[str, float] = {}   # 차단 해제 시각
_FAIL_LOCK     = threading.Lock()
_CIRCUIT_TIMEOUT = 30.0                # 30초 후 자동 복구 시도


class WardRepository:
    """
    병동 대시보드 전용 Oracle 데이터 접근 객체.

    [Circuit Breaker 동작]
    · 3회 연속 실패 → 30초 차단 (빈 리스트 즉시 반환)
    · 30초 후 자동 Half-Open → 재시도
    · 성공 시 카운터 초기화

    [TTL 캐시]
    · Streamlit @st.cache_data(ttl=120) 로 2분 캐싱
    · 사용자가 새로고침 버튼 클릭 시 st.cache_data.clear() 호출
    """

    def query(self, key: str) -> List[Dict[str, Any]]:
        """
        Circuit Breaker 보호 하에 Oracle 쿼리를 실행한다.

        기존 hospital_dashboard.py 의 _query() 함수를 메서드로 이동.

        Args:
            key: QUERIES 딕셔너리 키

        Returns:
            쿼리 결과 딕셔너리 리스트. 실패/차단 시 빈 리스트.
        """
        if key not in QUERIES:
            logger.error(f"[WardRepo] 미등록 쿼리 키: {key}")
            return []

        # Circuit Breaker: 차단 중 확인
        _now = time.time()
        _off_until = _CIRCUIT_OFF.get(key, 0)
        if _now < _off_until:
            _rem = int(_off_until - _now)
            if _rem % 10 == 0:
                logger.debug(f"[Circuit OPEN] {key} — {_rem}초 후 재시도")
            return []

        _t0 = time.perf_counter()
        try:
            from db.oracle_client import execute_query
            rows = execute_query(QUERIES[key])
            elapsed_ms = int((time.perf_counter() - _t0) * 1000)

            # 성공: 카운터 초기화
            with _FAIL_LOCK:
                _FAIL_COUNT.pop(key, None)
                _CIRCUIT_OFF.pop(key, None)

            if elapsed_ms > 500:
                logger.warning(f"[SLOW] {key}: {elapsed_ms}ms")
            else:
                logger.debug(f"[WardRepo] {key}: {elapsed_ms}ms, {len(rows or [])}행")

            return rows if rows else []

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - _t0) * 1000)
            with _FAIL_LOCK:
                _FAIL_COUNT[key] = _FAIL_COUNT.get(key, 0) + 1
                fail_cnt = _FAIL_COUNT[key]
                if fail_cnt >= 3:
                    _CIRCUIT_OFF[key] = time.time() + _CIRCUIT_TIMEOUT
                    logger.error(
                        f"[Circuit OPEN] {key}: {fail_cnt}회 실패 "
                        f"→ {_CIRCUIT_TIMEOUT:.0f}초 차단. {type(exc).__name__}: {exc}"
                    )
                else:
                    logger.warning(
                        f"[Query FAIL] {key} ({fail_cnt}/3): {type(exc).__name__}: {exc}"
                    )
            return []

    def get(self, key: str, ttl: int = 120) -> List[Dict[str, Any]]:
        """
        TTL 캐시가 적용된 쿼리 실행.

        기존 hospital_dashboard.py 의 _qc() 함수를 메서드로 이동.
        Streamlit @st.cache_data(ttl=120) 를 내부적으로 사용한다.

        Args:
            key: QUERIES 딕셔너리 키
            ttl: 캐시 유지 시간 (초, 기본 2분)

        Returns:
            쿼리 결과 (캐시 히트 시 캐시에서 반환)
        """
        # TTL 캐시 함수를 동적 생성 (key별로 캐시 분리)
        @st.cache_data(ttl=ttl, show_spinner=False)
        def _cached(k: str) -> List[Dict[str, Any]]:
            return self.query(k)

        return _cached(key)

    # ── 자주 쓰는 데이터 편의 메서드 ──────────────────────────────

    def get_ward_dept_stay(self)   -> List[Dict]: return self.get("ward_dept_stay")
    def get_ward_bed_detail(self)  -> List[Dict]: return self.get("ward_bed_detail")
    def get_ward_kpi_trend(self)   -> List[Dict]: return self.get("ward_kpi_trend")
    def get_ward_dx_today(self)    -> List[Dict]: return self.get("ward_dx_today")
    def get_ward_dx_trend(self)    -> List[Dict]: return self.get("ward_dx_trend")
    def get_ward_yesterday(self)   -> List[Dict]: return self.get("ward_yesterday")
    def get_admit_candidates(self) -> List[Dict]: return self.get("admit_candidates")
    def get_ward_room_detail(self) -> List[Dict]: return self.get("ward_room_detail")
    def get_ward_op_stat(self)     -> List[Dict]: return self.get("ward_op_stat")
    def get_opd_kpi(self)          -> Dict:
        rows = self.get("opd_kpi")
        return rows[0] if rows else {}

    def circuit_status(self) -> Dict[str, str]:
        """모든 쿼리의 Circuit Breaker 상태를 반환한다 (모니터링용)."""
        now = time.time()
        return {
            key: (
                f"차단중 ({int(_CIRCUIT_OFF[key] - now)}초 남음)"
                if now < _CIRCUIT_OFF.get(key, 0)
                else f"정상 (실패 {_FAIL_COUNT.get(key, 0)}회)"
            )
            for key in QUERIES
        }


# 전역 싱글톤 — hospital_dashboard.py 에서 import해서 사용
ward_repo = WardRepository()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 쿼리별 TTL 정책 (hospital_dashboard.py 에서 이동)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_TTL_MAP: Dict[str, int] = {
    "ward_bed_detail":       30,   # KPI 핵심 — 가동률/재원수
    "ward_op_stat":          30,   # 수술 현황
    "ward_yesterday":        30,   # 전일 비교
    "ward_dept_stay":        60,   # 진료과별 재원
    "admit_candidates":      60,   # 익일 예약
    "ward_room_detail":      60,   # 병실 상태
    "ward_kpi_trend":       300,   # 7일 추이
    "ward_dx_today":        300,   # 주상병
    "ward_dx_trend":        300,   # 주상병 추이
    "finance_kpi":          120,
    "finance_overdue":      120,
    "finance_by_insurance": 120,
    "opd_kpi":              120,
    "opd_by_dept":          120,
    "opd_hourly":           120,
    "opd_noshow":           120,
}
_DEFAULT_TTL = 120


@st.cache_data(show_spinner=False)
def _query_cached_ttl(key: str, _bucket: int) -> List[Dict[str, Any]]:
    """키별 TTL 버킷 캐시. _bucket = int((time - jitter) / ttl) 로 분산."""
    return ward_repo.query(key)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 하위 호환 래퍼 함수 — hospital_dashboard.py 에서 import 사용
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _query(key: str) -> List[Dict[str, Any]]:
    """Circuit Breaker 보호 쿼리 실행."""
    return ward_repo.query(key)


def _qc(key: str) -> List[Dict[str, Any]]:
    """
    키별 TTL 캐시 래퍼 — Thundering Herd 방지 포함.

    세션별 jitter(0 ~ ttl×10%)를 session_state에 저장하여
    캐시 만료 시점을 분산시킨다 (20명 동시 접속 대응).
    """
    ttl = _TTL_MAP.get(key, _DEFAULT_TTL)
    _jitter_key = f"_ttl_jitter_{key}"
    if _jitter_key not in st.session_state:
        st.session_state[_jitter_key] = random.uniform(0, ttl * 0.10)
    bucket = int((time.time() - st.session_state[_jitter_key]) / ttl)
    return _query_cached_ttl(key, bucket)