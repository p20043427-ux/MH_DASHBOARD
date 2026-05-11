"""
ward_v2_app.py  ─  병동 대시보드 v2 독립 실행 진입점  (2026-05-09)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행 방법:
    streamlit run ward_v2_app.py --server.port 8506
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.ui_labels import get_hospital_name  # [2026-05-11] 병원명 동적 로딩

# ── 페이지 설정 ───────────────────────────────────────────────────────
st.set_page_config(
    page_title=f"병동 현황 v2 | {get_hospital_name()}",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 전역 폰트 CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
html, body, [data-testid], [class*="st-"],
p, div, span, a, li, button, input, label, select, textarea {
  font-family: "Pretendard", -apple-system, BlinkMacSystemFont,
               "Apple SD Gothic Neo", sans-serif !important;
  -webkit-font-smoothing: antialiased;
}
/* 상단 Streamlit 헤더 숨김 */
[data-testid="stHeader"]          { display: none !important; }
[data-testid="stToolbar"]         { display: none !important; }
[data-testid="stDecoration"]      { display: none !important; }
[data-testid="stMainBlockContainer"] { padding-top: 0.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Oracle 연결 초기화 (세션당 1회) ─────────────────────────────────
if "oracle_ok" not in st.session_state:
    _ok = False
    try:
        from db.oracle_client import test_connection
        _ok, _ = test_connection()
    except Exception:
        pass
    st.session_state["oracle_ok"] = _ok

# ── v2 렌더 ──────────────────────────────────────────────────────────
try:
    from ui.hospital_dashboard_v2 import render_ward_v2
    render_ward_v2()
except Exception as _e:
    st.error(
        f"**대시보드 로드 오류**\n\n{_e}\n\n"
        "Oracle 연결 상태를 확인하거나 관리자에게 문의하세요."
    )
    import logging
    logging.getLogger(__name__).error(f"ward_v2_app 오류: {_e}", exc_info=True)
