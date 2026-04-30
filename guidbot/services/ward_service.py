"""
services/ward_service.py  ─  병동 대시보드 비즈니스 로직 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[리팩토링 이유]
  기존 ui/hospital_dashboard.py 에 _norm_sex(), _safe_int(),
  _filter_by_ward(), _filter_dx_ward(), _trend_dedup() 등
  비즈니스 로직 함수들이 UI 코드와 섞여 있었음.
  이 파일로 분리하여 단위 테스트 및 재사용이 가능하게 한다.

[책임]
  · 데이터 정규화 (성별, 숫자 안전변환)
  · 병동 필터링 (_filter_by_ward, _filter_dx_ward)
  · 추이 데이터 중복 제거 (_trend_dedup)
  · KPI 합산 계산

[사용 방법]
  from services.ward_service import WardService
  svc = WardService()
  filtered = svc.filter_by_ward(bed_detail, "내과병동")
  sex = svc.norm_sex("여")  # → "F"
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from utils.type_helpers import safe_int as _th_safe_int
from utils.type_helpers import safe_float as _th_safe_float
from utils.type_helpers import norm_sex as _th_norm_sex


class WardService:
    """
    병동 대시보드 데이터 처리 서비스.

    DB에서 가져온 원시 데이터를 UI에 맞게 가공한다.
    DB 접근이나 UI 렌더링은 하지 않는다 (순수 비즈니스 로직).
    """

    # ──────────────────────────────────────────────────────────
    # 데이터 정규화
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def norm_sex(val: Any) -> str:
        """DB 성별 값을 'F'/'M' 으로 정규화. → utils.type_helpers 위임."""
        return _th_norm_sex(val)

    @staticmethod
    def safe_int(val: Any, default: int = 0) -> int:
        """None/빈값 안전한 int 변환. → utils.type_helpers 위임."""
        return _th_safe_int(val, default)

    @staticmethod
    def safe_float(val: Any, default: float = 0.0) -> float:
        """None/빈값 안전한 float 변환. → utils.type_helpers 위임."""
        return _th_safe_float(val, default)

    @staticmethod
    def safe_str(val: Any, default: str = "─") -> str:
        """None/빈값을 기본 문자열로 변환한다."""
        if val is None or str(val).strip() == "":
            return default
        return str(val).strip()

    # ──────────────────────────────────────────────────────────
    # 병동 필터링
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def filter_by_ward(
        data: List[Dict],
        ward: str,
        ward_col: str = "병동명",
    ) -> List[Dict]:
        """
        병동명으로 데이터를 필터링한다.

        기존 hospital_dashboard.py 의 _filter_by_ward() 를 이동.

        Args:
            data:     필터링할 딕셔너리 리스트
            ward:     선택된 병동명. "전체"면 전체 반환.
            ward_col: 병동명 컬럼 이름 (기본 "병동명")

        Returns:
            필터링된 딕셔너리 리스트
        """
        if ward == "전체":
            return data
        return [r for r in data if r.get(ward_col, "") == ward]

    @staticmethod
    def filter_dx_ward(data: List[Dict], ward: str) -> List[Dict]:
        """
        주상병 데이터를 병동으로 필터링한다.

        기존 hospital_dashboard.py 의 _filter_dx_ward() 를 이동.

        "전체" 선택 시 병동명="전체"인 집계 행을 우선 반환하고,
        없으면 모든 병동을 합산하여 반환한다.

        Args:
            data: 주상병 데이터 (기준일, 병동명, 주상병코드, 주상병명, 환자수)
            ward: 선택된 병동명

        Returns:
            필터링/집계된 딕셔너리 리스트
        """
        if ward != "전체":
            return [r for r in data if r.get("병동명", "") == ward]

        # "전체" 선택 시 — 집계 행 우선 사용
        total_rows = [r for r in data if r.get("병동명", "") == "전체"]
        if total_rows:
            return total_rows

        # 집계 행 없으면 직접 합산
        agg: dict = defaultdict(lambda: defaultdict(int))
        for r in data:
            k = (
                r.get("기준일", ""),
                r.get("주상병코드", ""),
                r.get("주상병명", ""),
            )
            try:
                agg[k]["환자수"] += int(r.get("환자수", 0) or 0)
            except (ValueError, TypeError):
                pass

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

    # ──────────────────────────────────────────────────────────
    # 데이터 가공
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def trend_dedup(data: List[Dict]) -> List[Dict]:
        """
        추이 데이터에서 날짜 중복을 제거한다.

        기존 hospital_dashboard.py 의 _trend_dedup() 를 이동.

        같은 날짜에 병동별 행과 "전체" 집계 행이 모두 있을 때,
        "전체" 행을 우선 사용하고 나머지는 제거한다.

        Args:
            data: 기준일 컬럼이 있는 딕셔너리 리스트

        Returns:
            날짜별 중복이 제거된 리스트 (날짜 오름차순 정렬)
        """
        if not data:
            return []
        seen: Dict[str, Dict] = {}
        for r in data:
            dt = r.get("기준일", "")
            if dt not in seen:
                seen[dt] = r
            elif r.get("병동명", "") == "전체":
                # "전체" 집계 행이 있으면 교체
                seen[dt] = r
        return [seen[k] for k in sorted(seen)]

    @staticmethod
    def get_ward_list(bed_detail: List[Dict]) -> List[str]:
        """
        병동 목록을 추출한다.

        기존 hospital_dashboard.py 의 인라인 코드를 메서드로 이동.

        Args:
            bed_detail: V_WARD_BED_DETAIL 쿼리 결과

        Returns:
            ["전체", "내과병동", "외과병동", ...] 형태의 리스트
        """
        ward_names = sorted({
            r.get("병동명", "")
            for r in bed_detail
            if r.get("병동명", "") and r.get("병동명", "") != "전체"
        })
        return ["전체"] + ward_names

    @staticmethod
    def calc_admit_stats(admit_candidates: List[Dict]) -> Dict[str, int]:
        """
        입원 예정 통계를 계산한다.

        Args:
            admit_candidates: V_ADMIT_CANDIDATES 쿼리 결과

        Returns:
            {"total": N, "done": N, "pending": N} 딕셔너리
        """
        total = len(admit_candidates)
        done  = sum(1 for r in admit_candidates if r.get("수속상태", "") == "AD")
        return {"total": total, "done": done, "pending": total - done}

    @staticmethod
    def filter_room_detail_by_sex(
        room_detail: List[Dict],
        sex: str,
        ward: str = "전체",
    ) -> List[Dict]:
        """
        병실 상세 데이터를 성별과 병동으로 필터링한다.

        병상 수배 기능에서 사용한다.

        Args:
            room_detail: V_WARD_ROOM_DETAIL 쿼리 결과
            sex:         "F" / "M" / "" (전체)
            ward:        병동명 필터 (기본 전체)

        Returns:
            필터링된 딕셔너리 리스트
        """
        result = room_detail
        if ward and ward != "전체":
            result = [r for r in result if r.get("병동명", "") == ward]
        if sex:
            # DB 성별 값을 정규화 후 비교
            result = [
                r for r in result
                if WardService.norm_sex(r.get("성별", "")) == sex
            ]
        return result


# 전역 싱글톤
ward_service = WardService()


# ── 하위 호환 래퍼 함수 ───────────────────────────────────────────
# hospital_dashboard.py 에서 _norm_sex(), _safe_int() 등을 직접 호출하는
# 코드가 있으면 아래 함수를 import해서 교체할 수 있음.

def _norm_sex(val: Any) -> str:
    return ward_service.norm_sex(val)

def _safe_int(val: Any, default: int = 0) -> int:
    return ward_service.safe_int(val, default)

def _safe_float(val: Any, default: float = 0.0) -> float:
    return ward_service.safe_float(val, default)

def _filter_by_ward(data: List[Dict], ward: str, ward_col: str = "병동명") -> List[Dict]:
    return ward_service.filter_by_ward(data, ward, ward_col)

def _filter_dx_ward(data: List[Dict], ward: str) -> List[Dict]:
    return ward_service.filter_dx_ward(data, ward)

def _trend_dedup(data: List[Dict]) -> List[Dict]:
    return ward_service.trend_dedup(data)