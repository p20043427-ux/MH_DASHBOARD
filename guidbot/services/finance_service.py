"""
services/finance_service.py  ─  원무 대시보드 비즈니스 로직 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[리팩토링 이유]
  기존 ui/finance_dashboard.py 에서 데이터 가공, 금액 포맷팅,
  카드 결제 대사(reconciliation) 필터링 등 비즈니스 로직이
  UI 렌더링 코드와 혼재되어 있었음. 이 파일로 분리한다.

[책임]
  · 금액 포맷팅 (천원 단위, 만원 단위)
  · 수납·미수금 데이터 집계
  · 카드 결제 대사 필터링 및 상태 판단
  · 진료과 정렬 순서 관리
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# 진료과 정렬 순서 (UI에서 여러 곳에 쓰이는 CASE 로직을 상수로 관리)
DEPT_ORDER: Dict[str, int] = {
    "*내분비내과":  1,  "*호흡기내과": 2,  "*소화기내과": 3,
    "*신장내과":    4,  "*순환기내과": 5,  "인공신장실":  6,
    "신경과":       7,  "가정의학과":  8,  "신경외과":    9,
    "*유방센터":   10,  "*위장관센터":11,  "*갑상선센터":12,
    "성형외과":    13,  "정형외과":   14,  "*OBGY":      15,
    "*난임센터":   16,  "소아청소년과":17, "이비인후과":  18,
    "피부과":      19,  "응급의학과": 20,  "외부의뢰":   21,
    "진단검사":    22,
}


class FinanceService:
    """
    원무 대시보드 데이터 처리 서비스.

    수납/미수금/외래 데이터를 UI에 맞게 가공한다.
    DB 접근이나 UI 렌더링은 하지 않는다.
    """

    # ──────────────────────────────────────────────────────────
    # 포맷팅
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def fmt_amount(val: Any) -> str:
        """
        금액을 천원 단위 콤마 포맷으로 변환한다.

        None이나 변환 불가 값은 "─"로 반환.
        예: 1234567 → "1,234,567"
        """
        try:
            return f"{int(val or 0):,}"
        except (ValueError, TypeError):
            return "─"

    @staticmethod
    def fmt_man(val: Any, suffix: str = "만원") -> str:
        """
        금액을 만원 단위로 변환한다.

        예: 12345678 → "1,234만원"
        """
        try:
            man = int(val or 0) // 10000
            return f"{man:,}{suffix}"
        except (ValueError, TypeError):
            return "─"

    @staticmethod
    def fmt_delta(current: Any, previous: Any) -> Tuple[float, str]:
        """
        전일/전월 대비 증감률과 방향 문자열을 계산한다.

        Returns:
            (증감률 float, "▲" or "▼" or "─")
        """
        try:
            cur = float(current or 0)
            prv = float(previous or 0)
            if prv == 0:
                return 0.0, "─"
            rate = (cur - prv) / prv * 100
            arrow = "▲" if rate >= 0 else "▼"
            return abs(rate), arrow
        except (ValueError, TypeError):
            return 0.0, "─"

    # ──────────────────────────────────────────────────────────
    # 수납·미수금 집계
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def summarize_finance_today(finance_today: List[Dict]) -> Dict[str, Any]:
        """
        V_FINANCE_TODAY 데이터에서 주요 KPI를 추출한다.

        Args:
            finance_today: finance_repo.get("finance_today") 결과

        Returns:
            {
              "total_revenue": 총수납액 (int),
              "insurance_amount": 보험청구액,
              "self_pay": 본인부담금,
              "row_count": 건수
            }
        """
        if not finance_today:
            return {"total_revenue": 0, "insurance_amount": 0,
                    "self_pay": 0, "row_count": 0}

        def _int(val: Any) -> int:
            try:
                return int(val or 0)
            except (ValueError, TypeError):
                return 0

        total_revenue    = sum(_int(r.get("금액", 0)) for r in finance_today)
        insurance_amount = sum(_int(r.get("보험금액", 0)) for r in finance_today)
        self_pay         = sum(_int(r.get("본인부담", 0)) for r in finance_today)

        return {
            "total_revenue":    total_revenue,
            "insurance_amount": insurance_amount,
            "self_pay":         self_pay,
            "row_count":        len(finance_today),
        }

    @staticmethod
    def summarize_overdue(overdue_stat: List[Dict]) -> Dict[str, Any]:
        """
        V_OVERDUE_STAT 데이터에서 미수금 요약을 계산한다.

        Returns:
            {"total_overdue": 총미수금, "count": 건수, "max_age_group": 최고연령구분}
        """
        if not overdue_stat:
            return {"total_overdue": 0, "count": 0, "max_age_group": "─"}

        def _int(val: Any) -> int:
            try:
                return int(val or 0)
            except (ValueError, TypeError):
                return 0

        total = sum(_int(r.get("미수금액", 0)) for r in overdue_stat)
        max_row = max(
            overdue_stat,
            key=lambda r: _int(r.get("미수금액", 0)),
            default={}
        )
        return {
            "total_overdue": total,
            "count": len(overdue_stat),
            "max_age_group": max_row.get("연령구분", "─"),
        }

    # ──────────────────────────────────────────────────────────
    # 카드 결제 대사 (Reconciliation)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def classify_card_recon(row: Dict) -> str:
        """
        카드 결제 대사 행의 상태를 분류한다.

        [상태 유형]
        · "정상"      - 승인번호 + 금액 일치
        · "금액불일치" - 승인번호는 같지만 금액 차이
        · "누락"      - 한쪽에만 존재
        · "병원만"    - 병원 기록에만 있고 카드사 미확인

        Args:
            row: 카드 대사 데이터 딕셔너리

        Returns:
            상태 문자열
        """
        has_card   = bool(row.get("카드사금액"))
        has_hosp   = bool(row.get("병원금액"))
        card_amt   = row.get("카드사금액", 0)
        hosp_amt   = row.get("병원금액", 0)

        if has_card and has_hosp:
            try:
                diff = abs(int(card_amt or 0) - int(hosp_amt or 0))
                return "정상" if diff == 0 else "금액불일치"
            except (ValueError, TypeError):
                return "금액불일치"
        elif has_hosp and not has_card:
            return "병원만"
        else:
            return "누락"

    # ──────────────────────────────────────────────────────────
    # 진료과 정렬
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def sort_dept_order(data: List[Dict], dept_col: str = "진료과명") -> List[Dict]:
        """
        DEPT_ORDER 기준으로 진료과별 데이터를 정렬한다.

        Python에서 ORDER BY CASE WHEN ... END 와 동일한 정렬을 수행.
        DEPT_ORDER에 없는 진료과는 맨 뒤로.

        Args:
            data:     정렬할 딕셔너리 리스트
            dept_col: 진료과명 컬럼명

        Returns:
            정렬된 딕셔너리 리스트
        """
        def _key(row: Dict) -> Tuple[int, str]:
            dept = str(row.get(dept_col, "")).strip()
            order = DEPT_ORDER.get(dept, 99)
            return (order, dept)

        return sorted(data, key=_key)


# 전역 싱글톤
finance_service = FinanceService()