"""
ui/design.py — 좋은문화병원 대시보드 디자인 시스템 (v2.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Single source of truth for dashboard UI.

[v2.0 변경]
  · theme.py(UITheme) 를 re-export → 챗봇/대시보드 모두 이 파일 하나로 임포트 가능
  · 기존 'from ui.theme import UITheme' 를 쓰던 곳은 'from ui.design import UITheme' 로
    교체할 수 있음 (하위 호환 별칭 제공)

[임포트 방법]
    from ui.design import C, APP_CSS, PLOTLY_CFG
    from ui.design import kpi_card, section_header, gap, badge_html
    from ui.design import UITheme   # theme.py 하위 호환 별칭
"""

from __future__ import annotations
from typing import Optional
import streamlit as st

# theme.py 하위 호환 re-export (단일 임포트 포인트)
from ui.theme import UITheme

# ════════════════════════════════════════════════════════════════════
# 1. 색상 팔레트 — 단일 C 딕셔너리
# ════════════════════════════════════════════════════════════════════
# 네이밍 원칙
#   · 기능명  : blue / indigo / violet / teal / green / yellow / orange / red
#   · *_l     : 연한 배경 (light background)
#   · t1~t5   : 텍스트 계층 (t1=제목 → t5=비활성)
#   · 상태명  : ok / warn / danger (+ _l 배경, _bd 테두리)
#   · 표면    : bg / surface / border / card
#   · 관리자  : navy / navy2 / sky / sky_l

C: dict = {
    # ── 브랜드 색상 ──────────────────────────────────────────────────
    "blue":     "#1E40AF",  "blue_l":    "#EFF6FF",
    "indigo":   "#4F46E5",  "indigo_l":  "#EEF2FF",
    "violet":   "#7C3AED",  "violet_l":  "#F5F3FF",
    "teal":     "#0891B2",  "teal_l":    "#ECFEFF",

    # ── 의미 색상 ──────────────────────────────────────────────────
    "green":    "#059669",  "green_l":   "#DCFCE7",
    "yellow":   "#D97706",  "yellow_l":  "#FEF3C7",
    "orange":   "#EA580C",  "orange_l":  "#FFF7ED",
    "red":      "#DC2626",  "red_l":     "#FEE2E2",

    # ── 텍스트 계층 ────────────────────────────────────────────────
    "t1": "#0F172A",   # 제목·강조
    "t2": "#334155",   # 본문
    "t3": "#64748B",   # 보조
    "t4": "#94A3B8",   # 힌트·메타
    "t5": "#CBD5E1",   # 비활성·구분선

    # ── 표면·배경 ──────────────────────────────────────────────────
    "bg":       "#F8FAFC",   # 페이지 배경
    "surface":  "#F1F5F9",   # 섹션 배경
    "border":   "#E2E8F0",   # 테두리
    "card":     "#FFFFFF",   # 카드 배경

    # ── 상태 시스템 (병원 전용) ───────────────────────────────────
    "ok":       "#059669",  "ok_l":      "#DCFCE7",  "ok_bd":     "#86EFAC",
    "warn":     "#F59E0B",  "warn_l":    "#FFFBEB",  "warn_bd":   "#FCD34D",
    "danger":   "#DC2626",  "danger_l":  "#FEE2E2",  "danger_bd": "#FCA5A5",

    # ── 관리자 대시보드 전용 ──────────────────────────────────────
    "navy":     "#0F172A",
    "navy2":    "#1E3A8A",
    "sky":      "#0EA5E9",
    "sky_l":    "#E0F2FE",
}

# ════════════════════════════════════════════════════════════════════
# 2. Plotly 공통 설정
# ════════════════════════════════════════════════════════════════════

PLOTLY_PALETTE: list = [
    "#1E40AF", "#059669", "#D97706", "#DC2626", "#7C3AED",
    "#0891B2", "#DB2777", "#0284C7", "#65A30D", "#9333EA",
]

PLOTLY_CFG: dict = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#333333", size=11),
    xaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10), zeroline=False),
    yaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10), zeroline=False),
)

# ════════════════════════════════════════════════════════════════════
# 3. 마스터 CSS — 모든 대시보드 공유
# ════════════════════════════════════════════════════════════════════
# 설계 원칙
#   · fn-kpi-*    : KPI 카드  (모든 대시보드 공통)
#   · wd-card     : 섹션 카드 컨테이너
#   · wd-sec      : 섹션 헤더
#   · badge-*     : 상태 배지
#   · goal-bar-*  : 목표 달성률 바

APP_CSS: str = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable.css');

/* ── 전역 타이포그래피 ─────────────────────────────────────────── */
.main,
[data-testid="stAppViewContainer"],
[data-testid="stMarkdownContainer"],
[data-testid="stText"] {
  font-family: 'Pretendard Variable', 'Malgun Gothic', -apple-system, sans-serif !important;
  font-size: 14px !important;
}
[data-testid="stAppViewContainer"] > .main {
  padding-top: .3rem !important;
  padding-left: .75rem !important;
  padding-right: .75rem !important;
}
[data-testid="stVerticalBlock"]  { gap: .45rem !important; }
.element-container               { margin-bottom: 0 !important; }
[data-testid="stMarkdownContainer"]:empty { display: none !important; }

/* ── 상단 그라데이션 바 ────────────────────────────────────────── */
.fn-topbar {
  height: 3px;
  background: linear-gradient(90deg, #1E40AF 0%, #7C3AED 50%, #E2E8F0 100%);
  border-radius: 2px 2px 0 0;
}

/* ── KPI 카드 ──────────────────────────────────────────────────── */
.fn-kpi {
  background: #fff;
  border: 1px solid #F0F4F8;
  border-radius: 12px;
  padding: 13px 15px;
  min-height: 118px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 3px 10px rgba(0,0,0,.06);
  transition: box-shadow 120ms ease;
}
.fn-kpi:hover          { box-shadow: 0 6px 18px rgba(0,0,0,.10); }
.fn-kpi-icon           { font-size: 18px; margin-bottom: 3px; }
.fn-kpi-label          { font-size: 10px; font-weight: 700; color: #64748B;
                          text-transform: uppercase; letter-spacing: .12em; }
.fn-kpi-value          { font-size: 30px; font-weight: 800; line-height: 1;
                          font-variant-numeric: tabular-nums; letter-spacing: -.03em; }
.fn-kpi-unit           { font-size: 13px; color: #64748B; font-weight: 500; margin-left: 2px; }
.fn-kpi-sub            { font-size: 11px; color: #94A3B8; margin-top: 3px; }

/* ── 목표 진행률 바 ────────────────────────────────────────────── */
.goal-bar-wrap { height: 5px; background: #F1F5F9; border-radius: 3px;
                  margin-top: 5px; overflow: hidden; }
.goal-bar-fill { height: 100%; border-radius: 3px; }

/* ── 섹션 카드 ─────────────────────────────────────────────────── */
.wd-card {
  background: #FFFFFF;
  border: 1px solid #E8EDF2;
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(15,23,42,.06);
  transition: box-shadow 120ms ease;
  overflow: hidden;
}
.wd-card:hover { box-shadow: 0 3px 12px rgba(15,23,42,.09); }

/* ── 섹션 헤더 ─────────────────────────────────────────────────── */
.wd-sec {
  font-size: 13px; font-weight: 700; color: #0F172A;
  margin-bottom: 10px; padding-bottom: 8px;
  border-bottom: 1px solid #F1F5F9;
  display: flex; align-items: center; gap: 7px;
}
.wd-sec-bar  { width: 3px; height: 15px; border-radius: 2px; flex-shrink: 0; }
.wd-sec-sub  { font-size: 11px; color: #94A3B8; font-weight: 400; margin-left: 3px; }

/* ── 배지 ──────────────────────────────────────────────────────── */
.badge        { border-radius: 5px; padding: 2px 8px;
                font-size: 11px; font-weight: 700; display: inline-block; }
.badge-blue   { background: #DBEAFE; color: #1E40AF; }
.badge-indigo { background: #EEF2FF; color: #4338CA; }
.badge-green  { background: #DCFCE7; color: #15803D; }
.badge-yellow { background: #FEF3C7; color: #92400E; }
.badge-orange { background: #FFF7ED; color: #C2410C; }
.badge-red    { background: #FEE2E2; color: #991B1B; }
.badge-gray   { background: #F1F5F9; color: #475569; }
.badge-ok     { background: #DCFCE7; color: #15803D; border: 1px solid #86EFAC; }
.badge-warn   { background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; }
.badge-err    { background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }

/* ── 미수금 바 ─────────────────────────────────────────────────── */
.overdue-row       { display: flex; align-items: center; gap: 8px;
                      padding: 6px 0; border-bottom: 1px solid #F8FAFC; }
.overdue-label     { font-size: 12px; font-weight: 700; width: 80px; flex-shrink: 0; }
.overdue-bar-wrap  { flex: 1; height: 8px; background: #F1F5F9;
                      border-radius: 4px; overflow: hidden; }
.overdue-bar       { height: 100%; border-radius: 4px; }
.overdue-val       { font-size: 12px; font-weight: 700; font-family: Consolas, monospace;
                      width: 65px; text-align: right; flex-shrink: 0; }

/* ── 테이블 ────────────────────────────────────────────────────── */
.wd-tbl     { width: 100%; border-collapse: collapse;
               font-size: 12.5px; table-layout: fixed; }
.wd-th      { padding: 7px 10px; font-size: 10.5px; font-weight: 700;
               text-transform: uppercase; letter-spacing: .07em; color: #64748B;
               background: #F8FAFC; border-bottom: 1.5px solid #E2E8F0;
               white-space: nowrap; }
.wd-td      { padding: 8px 10px; border-bottom: 1px solid #F8FAFC;
               color: #334155; vertical-align: middle; font-size: 12.5px; }
.wd-td-num  { font-variant-numeric: tabular-nums;
               font-family: 'Consolas', 'SF Mono', monospace; font-size: 12.5px; }

/* ── Streamlit 탭 ──────────────────────────────────────────────── */
[data-testid="stTabs"] > div:first-child {
  border-bottom: 1.5px solid #E2E8F0 !important; gap: 0 !important;
}
[data-testid="stTabs"] button {
  font-size: 13px !important; font-weight: 600 !important;
  padding: 6px 16px !important; border-radius: 0 !important; color: #64748B !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
  color: #1E40AF !important;
  border-bottom: 2.5px solid #1E40AF !important;
  background: transparent !important;
}

/* ── Selectbox ─────────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
  border-radius: 8px !important;
  border: 1.5px solid #BFDBFE !important;
  background: #EFF6FF !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  color: #1E40AF !important;
}
[data-testid="stSelectbox"] label { display: none !important; }

/* ── 버튼 ──────────────────────────────────────────────────────── */
button[kind="secondary"],
[data-testid="stBaseButton-secondary"] {
  font-size: 11.5px !important; font-weight: 600 !important;
  padding: 0 14px !important; height: 32px !important;
  border-radius: 20px !important;
  border: 1.5px solid #E2E8F0 !important;
  background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%) !important;
  color: #475569 !important;
  box-shadow: 0 1px 3px rgba(15,23,42,.06) !important;
  transition: all 120ms ease !important;
  white-space: nowrap !important;
}
button[kind="secondary"]:hover,
[data-testid="stBaseButton-secondary"]:hover {
  background: linear-gradient(180deg, #F1F5F9 0%, #E2E8F0 100%) !important;
  border-color: #94A3B8 !important; color: #1E293B !important;
  box-shadow: 0 3px 8px rgba(15,23,42,.10) !important;
  transform: translateY(-1px) !important;
}
button[kind="primary"],
[data-testid="stBaseButton-primary"] {
  font-size: 11.5px !important; font-weight: 700 !important;
  padding: 0 14px !important; height: 32px !important;
  border-radius: 20px !important;
  box-shadow: 0 2px 6px rgba(30,64,175,.20) !important;
  transition: all 120ms ease !important;
}
button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 4px 12px rgba(30,64,175,.28) !important;
}

/* ── 라디오 버튼 (pill 형태) ───────────────────────────────────── */
div[data-testid="stRadio"] { padding: 0 !important; margin: 0 !important; }
div[data-testid="stRadio"] > div[data-testid="stWidgetLabel"],
div[data-testid="stRadio"] > label:not([data-baseweb]),
div[data-testid="stRadio"] > p {
  display: none !important; height: 0 !important;
}
div[data-testid="stRadio"] > div {
  display: flex !important; flex-direction: row !important;
  flex-wrap: nowrap !important; gap: 2px !important;
  align-items: center !important; padding: 0 !important;
}
div[data-testid="stRadio"] label {
  display: inline-flex !important; align-items: center !important;
  padding: 2px 8px !important; border-radius: 14px !important;
  border: 1px solid #E2E8F0 !important;
  background: #FFFFFF !important; color: #64748B !important;
  font-size: 10.5px !important; font-weight: 500 !important;
  cursor: pointer !important; white-space: nowrap !important;
  transition: background .1s, color .1s, border-color .1s !important;
}
div[data-testid="stRadio"] label:hover {
  background: #F1F5F9 !important;
  border-color: #93C5FD !important; color: #1E40AF !important;
}
div[data-testid="stRadio"] label:has(input:checked) {
  background: #1E40AF !important;
  border-color: #1E40AF !important;
  color: #FFFFFF !important; font-weight: 600 !important;
}
div[data-testid="stRadio"] input[type="radio"] {
  position: absolute !important; opacity: 0 !important;
  width: 0 !important; height: 0 !important;
}
div[data-testid="stRadio"] label > div:first-child {
  display: none !important; width: 0 !important;
}
.stPlotlyChart { margin: 0 !important; padding: 0 !important; }
iframe.stPlotlyChart { border: none !important; }
</style>
"""

# ════════════════════════════════════════════════════════════════════
# 4. Streamlit 컴포넌트 헬퍼
# ════════════════════════════════════════════════════════════════════

def kpi_card(
    col,
    icon: str,
    label: str,
    val: str,
    unit: str,
    sub: str,
    color: str,
    goal_pct: Optional[float] = None,
) -> None:
    """fn-kpi 스타일 KPI 카드. 모든 대시보드 공통."""
    _bar = ""
    if goal_pct is not None:
        _p = min(max(int(goal_pct), 0), 100)
        _bc = (
            C["green"] if _p >= 100
            else C["yellow"] if _p >= 70
            else C["red"]
        )
        _bar = (
            f'<div class="goal-bar-wrap">'
            f'<div class="goal-bar-fill" style="width:{_p}%;background:{_bc};"></div>'
            f'</div>'
            f'<div style="font-size:10px;color:{_bc};font-weight:700;margin-top:2px;">'
            f'목표 {_p}%</div>'
        )
    col.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid {color};">'
        f'<div class="fn-kpi-icon">{icon}</div>'
        f'<div class="fn-kpi-label">{label}</div>'
        f'<div class="fn-kpi-value" style="color:{color};">{val}'
        f'<span class="fn-kpi-unit">{unit}</span></div>'
        f'<div class="fn-kpi-sub">{sub}</div>{_bar}</div>',
        unsafe_allow_html=True,
    )


def section_header(title: str, sub: str = "", color: Optional[str] = None) -> None:
    """wd-sec 스타일 섹션 헤더. 모든 대시보드 공통."""
    _color = color or C["blue"]
    st.markdown(
        f'<div class="wd-sec">'
        f'<span class="wd-sec-bar" style="background:{_color};"></span>'
        f"{title}"
        f"{'<span class=wd-sec-sub>' + sub + '</span>' if sub else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )


def gap(px: int = 8) -> None:
    """빈 세로 여백."""
    st.markdown(f'<div style="height:{px}px"></div>', unsafe_allow_html=True)


def badge_html(text: str, kind: str = "blue") -> str:
    """배지 HTML 반환. kind: blue/indigo/green/yellow/orange/red/gray/ok/warn/err"""
    return f'<span class="badge badge-{kind}">{text}</span>'


def empty_state(msg: str = "데이터 없음") -> None:
    """데이터 없을 때 빈 플레이스홀더."""
    st.markdown(
        f'<div style="padding:32px;text-align:center;color:{C["t4"]};font-size:13px;">'
        f'{msg}</div>',
        unsafe_allow_html=True,
    )


def topbar() -> None:
    """상단 그라데이션 바."""
    st.markdown('<div class="fn-topbar"></div>', unsafe_allow_html=True)


def fmt_won(n: int) -> str:
    """금액 → 억/만 단위 포맷."""
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n // 10_000:,}만"
    return f"{n:,}"


# ════════════════════════════════════════════════════════════════════
# 병동 대시보드 전용 — chart_renderers / hospital_dashboard 공용
# ════════════════════════════════════════════════════════════════════

WARD_AX: dict = dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False)


def ward_layout(fig, **kwargs):
    """병동 Plotly Figure 레이아웃 적용."""
    fig.update_layout(**{**PLOTLY_CFG, **kwargs})
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
    """병동 KPI 카드 (fn-kpi 스타일)."""
    tgt = col_obj if col_obj else st
    _delta_html = ""
    if delta:
        _dc = C["green"] if "▲" in delta else C["red"] if "▼" in delta else C["t4"]
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
    """병동 섹션 제목."""
    badge_str = (
        f'<span style="font-size:10px;background:{C["sky_l"]};color:{C["sky"]};'
        f'border:1px solid rgba(56,189,248,0.3);border-radius:3px;'
        f'padding:1px 7px;font-weight:600;margin-left:8px;">{badge}</span>'
        if badge else ""
    )
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
        f'text-transform:uppercase;letter-spacing:.06em;margin:18px 0 8px;">'
        f'{title}{badge_str}</div>',
        unsafe_allow_html=True,
    )
