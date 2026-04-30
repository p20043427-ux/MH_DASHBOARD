"""
utils/type_helpers.py  ─  공용 타입 변환 헬퍼 (Single Source of Truth)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[통합 배경]
  이전에 동일한 safe_int / safe_float / norm_sex 함수가
  5개 파일에 중복 정의되어 있었음:
    - db/schema_extractor.py
    - services/ward_service.py  (클래스 메서드 + 모듈 래퍼)
    - ui/dashboard_data.py
    - ui/panels/dept_analysis.py

  이 파일이 유일한 구현체. 나머지 파일은 여기서 import.

[사용 방법]
  from utils.type_helpers import safe_int, safe_float, norm_sex
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
    """
    None/빈문자열/오류 안전한 int 변환.

    Examples:
        safe_int(None)        → 0
        safe_int("")          → 0
        safe_int("1234")      → 1234
        safe_int(1234.5)      → 1234
        safe_int("invalid")   → 0
        safe_int(None, -1)    → -1
    """
    try:
        return int(val or default)
    except (ValueError, TypeError):
        return default


def safe_float(val: Any, default: float = 0.0) -> float:
    """
    None/빈문자열/오류 안전한 float 변환.

    Examples:
        safe_float(None)        → 0.0
        safe_float("3.14")      → 3.14
        safe_float("invalid")   → 0.0
    """
    try:
        return float(val or default)
    except (ValueError, TypeError):
        return default


def norm_sex(val: Any) -> str:
    """
    DB 성별 값을 'F'(여) 또는 'M'(남) 코드로 정규화.

    DB 값: '여'/'남' (한글) 또는 'F'/'M' (영문) 혼재 가능.
    미인식 값은 빈 문자열 반환.

    Examples:
        norm_sex("여")  → "F"
        norm_sex("F")   → "F"
        norm_sex("남")  → "M"
        norm_sex("?")   → ""
    """
    return _SEX_NORM.get(str(val).strip(), "")
