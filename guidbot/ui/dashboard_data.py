"""
ui/dashboard_data.py  ─  대시보드 공용 데이터 유틸리티 (위임 래퍼)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[v2.0 변경]
  실제 구현이 utils/type_helpers.py 로 이동됨.
  이 파일은 하위 호환을 위한 re-export 래퍼로만 유지.

  기존 코드 변경 없이 계속 사용 가능:
    from ui.dashboard_data import safe_int, safe_float, norm_sex
"""

from utils.type_helpers import safe_int, safe_float, norm_sex

__all__ = ["safe_int", "safe_float", "norm_sex"]
