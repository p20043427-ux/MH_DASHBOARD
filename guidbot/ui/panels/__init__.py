"""
ui/panels/ — 좋은문화병원 대시보드 패널 모듈 (Phase 2, 2026-04-22)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
finance_dashboard.py (3966줄) 을 기능별 패널 단위로 분리한 패키지.

[패널 목록]
  _shared.py              공통 임포트, _fq(), FQ/FQ_HIST 쿼리 딕셔너리
  finance_realtime.py     탭1 — 실시간 현황 (외래·입원·키오스크·LLM 채팅)
  finance_revenue.py      탭2 — 수납·미수금
  finance_analytics.py    탭3 — 통계·분석 (주간/월간/지역)
  finance_cardmatch.py    탭4 — 카드 매칭 이중 검증

[임포트 예시]
  from ui.panels.finance_realtime  import render as render_realtime
  from ui.panels.finance_revenue   import render as render_revenue
  from ui.panels.finance_analytics import render as render_analytics
  from ui.panels.finance_cardmatch import render as render_cardmatch
"""
