"""
ui/finance/__init__.py ─ 원무 현황 대시보드 탭 패키지 (P2 God File 분리)
[2026-05-07] tab_chat.py 추가 — 탭별 AI 분석 채팅 컴포넌트

각 탭은 독립 모듈에 정의됩니다.
finance_dashboard.py 는 render_finance_dashboard() 만 갖는 얇은 라우터.

모듈 구조:
    tab_realtime    — 탭1 실시간 현황 + AI 채팅 + 세부과 집계표
    tab_revenue     — 탭2 수납·미수금
    tab_analytics   — 탭3 주간추이분석
    tab_monthly     — 탭4 월간추이분석
    tab_region      — 탭5 지역별 통계 (Folium)
    tab_card_match  — 탭6 카드 매칭
    tab_chat        — 공통 AI 분석 채팅 위젯 (각 탭 하단)
"""

from ui.finance.tab_realtime   import _tab_realtime, _render_day_inweon, _render_finance_llm_chat
from ui.finance.tab_revenue    import _tab_revenue
from ui.finance.tab_analytics  import _tab_analytics
from ui.finance.tab_monthly    import _tab_monthly
from ui.finance.tab_region     import _tab_region
from ui.finance.tab_card_match import _tab_card_match
from ui.finance.tab_chat import (
    render_tab_chat,
    build_ctx_realtime,
    build_ctx_weekly,
    build_ctx_monthly,
    build_ctx_dept,
)

__all__ = [
    "_tab_realtime",
    "_render_day_inweon",
    "_render_finance_llm_chat",
    "_tab_revenue",
    "_tab_analytics",
    "_tab_monthly",
    "_tab_region",
    "_tab_card_match",
    "render_tab_chat",
    "build_ctx_realtime",
    "build_ctx_weekly",
    "build_ctx_monthly",
    "build_ctx_dept",
]
