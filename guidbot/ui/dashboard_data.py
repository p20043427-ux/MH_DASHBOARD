"""
ui/dashboard_data.py  ─  대시보드 공용 데이터 유틸리티
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[역할]
  finance_dashboard / hospital_dashboard 양쪽에서 중복 정의되던
  타입 변환 헬퍼와 성별 정규화 함수를 단일 모듈로 통합.

[포함 내용]
  · safe_int  — None/빈값/오류 안전한 int 변환
  · safe_float — None/빈값/오류 안전한 float 변환
  · norm_sex  — DB 성별 값 → 'F'/'M' 정규화
"""

from __future__ import annotations

from typing import Any, Dict

# ── 성별 정규화 매핑 (dict lookup O(1)) ────────────────────────────────
# DB 성별 값: '여'/'남' 한글 또는 'F'/'M' 영문 혼재 가능
_SEX_NORM: Dict[str, str] = {
    "여": "F", "F": "F", "f": "F",
    "남": "M", "M": "M", "m": "M",
}


def safe_int(val: Any, default: int = 0) -> int:
    """None/빈문자열/오류 안전한 int 변환."""
    try:
        return int(val or default)
    except (ValueError, TypeError):
        return default


def safe_float(val: Any, default: float = 0.0) -> float:
    """None/빈문자열/오류 안전한 float 변환."""
    try:
        return float(val or default)
    except (ValueError, TypeError):
        return default


def norm_sex(val: str) -> str:
    """성별 값을 'F'(여) 또는 'M'(남) 코드로 정규화. 미인식 값은 빈 문자열."""
    return _SEX_NORM.get(str(val).strip(), "")
