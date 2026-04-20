"""
ui/dashboard_ui.py — 하위 호환 재익스포트 모듈
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  새 코드는 ui/design.py 를 직접 임포트하라.
    이 파일은 기존 import 경로 호환성 유지 목적으로만 존재한다.

[마이그레이션]
    # 구 방식 (계속 동작하지만 사용 지양)
    from ui.dashboard_ui import C_FINANCE as C, FINANCE_CSS as _CSS

    # 신 방식 (권장)
    from ui.design import C, APP_CSS as _CSS
"""

from __future__ import annotations
from typing import Optional

import streamlit as st

# ── design.py 에서 전부 가져와 재익스포트 ───────────────────────────
from ui.design import (                        # noqa: F401  (재익스포트)
    C,
    APP_CSS,
    PLOTLY_CFG,
    PLOTLY_PALETTE,
    kpi_card,
    section_header,
    gap,
    badge_html,
    empty_state,
    topbar,
    fmt_won,
)

# ── 구 이름 별칭 (기존 import 경로 유지) ────────────────────────────
C_FINANCE   = C                         # from ui.dashboard_ui import C_FINANCE
C_WARD      = C                         # from ui.dashboard_ui import C_WARD
FINANCE_CSS = APP_CSS                   # from ui.dashboard_ui import FINANCE_CSS
WARD_CSS    = APP_CSS                   # from ui.dashboard_ui import WARD_CSS

PLOTLY_LAYOUT   = PLOTLY_CFG            # from ui.dashboard_ui import PLOTLY_LAYOUT
WARD_PLOTLY_BASE = PLOTLY_CFG
WARD_AX = dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False)
WARD_PALETTE = PLOTLY_PALETTE

finance_kpi_card = kpi_card             # from ui.dashboard_ui import finance_kpi_card
empty_chart      = empty_state          # from ui.dashboard_ui import empty_chart


def ward_layout(fig, **kwargs):
    """병동 Plotly Figure 레이아웃 적용 (하위 호환)."""
    merged = {**PLOTLY_CFG, **kwargs}
    fig.update_layout(**merged)
    return fig


def ward_kpi_card(
    label: str,
    value: str,
    unit: str,
    sub: str,
    color: str,
    col_obj=None,
    delta: str = "",
    bar_pct: float = 0,
) -> None:
    """병동 KPI 카드 — fn-kpi 스타일로 통일 (하위 호환 시그니처 유지)."""
    tgt = col_obj if col_obj else st
    _delta_html = ""
    if delta:
        if "▲" in delta:
            _dc = C["green"]
        elif "▼" in delta:
            _dc = C["red"]
        else:
            _dc = C["t4"]
        _delta_html = (
            f'<span style="font-size:13px;font-weight:700;color:{_dc};">{delta}</span>'
        )
    _bar_html = (
        f'<div class="goal-bar-wrap">'
        f'<div class="goal-bar-fill" style="width:{min(100, bar_pct):.1f}%;background:{color};"></div>'
        f'</div>'
        if bar_pct > 0
        else '<div style="height:3px;margin:4px 0 3px;"></div>'
    )
    tgt.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid {color};">'
        f'<div class="fn-kpi-label">{label}</div>'
        f'<div style="display:flex;align-items:baseline;gap:3px;margin-bottom:2px;">'
        f'<span class="fn-kpi-value" style="color:{color};">{value}</span>'
        f'<span class="fn-kpi-unit">{unit}</span>'
        f'</div>'
        f'{_bar_html}'
        f'<div style="display:flex;justify-content:space-between;">'
        f'<span class="fn-kpi-sub">{sub}</span>'
        f'{_delta_html}'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def ward_section_title(title: str, badge: str = "") -> None:
    """병동 섹션 제목 (하위 호환). 새 코드는 section_header() 사용."""
    badge_html_str = (
        f'<span style="font-size:10px;background:{C["sky_l"]};color:{C["sky"]};'
        f'border:1px solid rgba(56,189,248,0.3);border-radius:3px;'
        f'padding:1px 7px;font-weight:600;margin-left:8px;">{badge}</span>'
        if badge
        else ""
    )
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
        f'text-transform:uppercase;letter-spacing:.06em;margin:18px 0 8px;">'
        f'{title}{badge_html_str}</div>',
        unsafe_allow_html=True,
    )
