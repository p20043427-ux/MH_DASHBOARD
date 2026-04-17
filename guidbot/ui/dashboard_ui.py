"""
ui/dashboard_ui.py  ─  대시보드 공용 UI 컴포넌트 라이브러리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[역할]
  finance_dashboard / hospital_dashboard 양쪽에서 중복 정의되던
  색상 팔레트·CSS·KPI카드·섹션헤더·공용헬퍼를 단일 모듈로 통합.

[포함 내용]
  색상:    C_FINANCE  — 원무 대시보드 팔레트
           C_WARD     — 병동 대시보드 팔레트
  CSS:     FINANCE_CSS — 원무 대시보드 전역 스타일
           WARD_CSS    — 병동 대시보드 전역 스타일
  Plotly:  PLOTLY_PALETTE, PLOTLY_LAYOUT   — 원무 공용
           WARD_PLOTLY_BASE, WARD_PALETTE  — 병동 공용
           WARD_AX      — 병동 공통 축 스타일
           ward_layout  — 병동 Figure 레이아웃 적용 헬퍼
  KPI:     finance_kpi_card — 원무 KPI 카드 (fn-kpi-* CSS)
           ward_kpi_card    — 병동 KPI 카드 (kpi-* CSS)
  헤더:    section_header   — 원무 섹션 헤더 (wd-sec-bar)
           ward_section_title — 병동 섹션 제목
  공용:    fmt_won, gap, empty_chart
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

# ════════════════════════════════════════════════════════════════════
# 색상 팔레트
# ════════════════════════════════════════════════════════════════════

C_FINANCE = {
    "blue":    "#1E40AF", "blue_l":   "#EFF6FF",
    "indigo":  "#4F46E5", "indigo_l": "#EEF2FF",
    "violet":  "#7C3AED", "violet_l": "#F5F3FF",
    "teal":    "#0891B2", "teal_l":   "#ECFEFF",
    "green":   "#059669", "green_l":  "#DCFCE7",
    "yellow":  "#D97706", "yellow_l": "#FEF3C7",
    "orange":  "#EA580C", "orange_l": "#FFF7ED",
    "red":     "#DC2626", "red_l":    "#FEE2E2",
    "t1": "#0F172A", "t2": "#334155", "t3": "#64748B", "t4": "#94A3B8",
}

C_WARD = {
    "bg": "#F8FAFC", "card": "#FFFFFF",
    "surface": "#F1F5F9", "surface_alt": "#E2E8F0",
    "border": "#CBD5E1", "border_light": "#E2E8F0", "divider": "#F1F5F9",
    "t1": "#0F172A", "t2": "#334155", "t3": "#64748B",
    "t4": "#94A3B8", "t5": "#CBD5E1",
    "semantic_up": "#EF4444", "semantic_dn": "#3B82F6",
    "ok": "#059669",    "ok_bg": "#D1FAE5",  "ok_bd": "#6EE7B7",  "ok_text": "#047857",
    "warn": "#F59E0B",  "warn_bg": "#FFFBEB","warn_bd": "#FCD34D","warn_text": "#92400E",
    "danger": "#DC2626","err_bg": "#FEE2E2", "err_bd": "#FCA5A5", "danger_text": "#991B1B",
    "chart1": "#1E40AF","chart2": "#2563EB", "chart3": "#3B82F6","chart4": "#059669",
    "chart5": "#0D9488","chart6": "#F59E0B", "chart7": "#EF4444","chart8": "#8B5CF6",
    "primary": "#1E40AF","primary_light": "#DBEAFE","primary_text": "#1D4ED8",
    "accent": "#7C3AED",
    "blue": "#3B82F6", "green": "#059669", "amber": "#F59E0B",
    "coral": "#DC2626", "sky": "#0EA5E9", "indigo": "#4F46E5", "purple": "#8B5CF6",
    "navy": "#1E40AF",  "navy2": "#1E3A8A", "navy3": "#1E3A8A",
    "blue_bg": "#DBEAFE","sky_bg": "#E0F2FE","amber_bg": "#FFFBEB",
    "purple_bg": "#F3E8FF","green_bg": "#D1FAE5","coral_bg": "#FEE2E2",
    "amber_bd": "#FCD34D","purple_bd": "#E9D5FF","t_heading": "#0F172A",
}

# ════════════════════════════════════════════════════════════════════
# Plotly 공통 헬퍼
# ════════════════════════════════════════════════════════════════════

# 원무 대시보드용
PLOTLY_PALETTE = [
    "#1E40AF", "#059669", "#D97706", "#DC2626", "#7C3AED",
    "#0891B2", "#DB2777", "#0284C7", "#65A30D", "#9333EA",
]
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#333333", size=11),
    xaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10), zeroline=False),
    yaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10), zeroline=False),
)

# 병동 대시보드용
WARD_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#333333", size=12),
)
WARD_PALETTE = [
    "#1E40AF", "#2563EB", "#3B82F6",
    "#0D9488", "#059669", "#F59E0B",
    "#EF4444", "#7C3AED", "#78716C",
]
WARD_AX = dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False)


def ward_layout(fig: "go.Figure", **kwargs) -> "go.Figure":  # type: ignore[name-defined]
    """병동 Plotly Figure에 공통 레이아웃을 적용. kwargs가 WARD_PLOTLY_BASE를 덮어씀."""
    merged = {**WARD_PLOTLY_BASE, **kwargs}
    fig.update_layout(**merged)
    return fig


# ════════════════════════════════════════════════════════════════════
# KPI 카드 컴포넌트
# ════════════════════════════════════════════════════════════════════

def finance_kpi_card(
    col,
    icon: str,
    label: str,
    val: str,
    unit: str,
    sub: str,
    color: str,
    goal_pct: Optional[float] = None,
) -> None:
    """원무 대시보드 KPI 카드 (fn-kpi-* CSS 클래스 사용)."""
    _bar = ""
    if goal_pct is not None:
        _p = min(max(int(goal_pct), 0), 100)
        _bc = (
            C_FINANCE["green"] if _p >= 100
            else C_FINANCE["yellow"] if _p >= 70
            else C_FINANCE["red"]
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
    """병동 대시보드 KPI 카드 (kpi-* CSS 클래스 사용)."""
    tgt = col_obj if col_obj else st
    if "▲" in delta:
        _dc_cls = "kpi-delta-up"
    elif "▼" in delta:
        _dc_cls = "kpi-delta-dn"
    else:
        _dc_cls = "kpi-delta-nt"
    _delta_html = f'<span class="{_dc_cls}">{delta}</span>' if delta else ""
    _bar_html = (
        f'<div class="kpi-bar-bg">'
        f'<div class="kpi-bar-fill" style="width:{min(100, bar_pct):.1f}%;background:{color};"></div>'
        f"</div>"
        if bar_pct > 0
        else '<div style="height:3px;margin:4px 0 3px;"></div>'
    )
    tgt.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div style="display:flex;align-items:baseline;gap:3px;margin-bottom:2px;">'
        f'<span class="kpi-value" style="color:{color};">{value}</span>'
        f'<span class="kpi-unit">{unit}</span>'
        f"</div>"
        f"{_bar_html}"
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:13px;color:#64748B;font-weight:500;">{sub}</span>'
        f'<span style="font-size:15px;font-weight:800;letter-spacing:-0.02em;line-height:1;">'
        f'{_delta_html}</span>'
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# 섹션 헤더
# ════════════════════════════════════════════════════════════════════

def section_header(title: str, sub: str = "", color: Optional[str] = None) -> None:
    """원무 대시보드 섹션 헤더 (wd-sec / wd-sec-bar CSS 클래스)."""
    _color = color or C_FINANCE["blue"]
    st.markdown(
        f'<div class="wd-sec">'
        f'<span class="wd-sec-bar" style="background:{_color};"></span>'
        f"{title}"
        f"{'<span class=wd-sec-sub>' + sub + '</span>' if sub else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )


def ward_section_title(title: str, badge: str = "") -> None:
    """병동 대시보드 섹션 제목."""
    badge_html = (
        f'<span style="font-size:10px;background:{C_WARD["sky_bg"]};color:{C_WARD["sky"]};'
        f"border:1px solid rgba(56,189,248,0.3);border-radius:3px;"
        f'padding:1px 7px;font-weight:600;margin-left:8px;">{badge}</span>'
        if badge
        else ""
    )
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;color:{C_WARD["t2"]};'
        f'text-transform:uppercase;letter-spacing:.06em;margin:18px 0 8px;">'
        f"{title}{badge_html}</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# 공용 헬퍼
# ════════════════════════════════════════════════════════════════════

def fmt_won(n: int) -> str:
    """금액을 억/만 단위로 포맷."""
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n // 10_000:,}만"
    return f"{n:,}"


def gap(px: int = 8) -> None:
    """빈 세로 여백."""
    st.markdown(f'<div style="height:{px}px"></div>', unsafe_allow_html=True)


def empty_chart() -> None:
    """데이터 없을 때 빈 플레이스홀더."""
    st.markdown(
        '<div style="padding:32px;text-align:center;color:#94A3B8;font-size:13px;">'
        '데이터 없음</div>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# CSS 문자열 (각 대시보드 main render 함수에서 1회 주입)
# ════════════════════════════════════════════════════════════════════

FINANCE_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable.css');
.main,[data-testid="stAppViewContainer"],[data-testid="stMarkdownContainer"]{
  font-family:'Pretendard Variable','Malgun Gothic',sans-serif!important;font-size:14px!important;}
[data-testid="stAppViewContainer"]>.main{padding-top:.3rem!important;padding-left:.75rem!important;padding-right:.75rem!important;}
[data-testid="stVerticalBlock"]{gap:.4rem!important;}
.element-container{margin-bottom:0!important;}
[data-testid="stMarkdownContainer"]:empty{display:none!important;}
.fn-topbar{height:3px;background:linear-gradient(90deg,#1E40AF 0%,#7C3AED 50%,#E2E8F0 100%);border-radius:2px 2px 0 0;}
.fn-kpi{background:#fff;border:1px solid #F0F4F8;border-radius:12px;padding:13px 15px;min-height:118px;
  display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 3px 10px rgba(0,0,0,.06);}
.fn-kpi:hover{box-shadow:0 6px 18px rgba(0,0,0,.10);}
.fn-kpi-icon{font-size:18px;margin-bottom:3px;}
.fn-kpi-label{font-size:10px;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.12em;}
.fn-kpi-value{font-size:30px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums;letter-spacing:-.03em;}
.fn-kpi-unit{font-size:13px;color:#64748B;font-weight:500;margin-left:2px;}
.fn-kpi-sub{font-size:11px;color:#94A3B8;margin-top:3px;}
.goal-bar-wrap{height:5px;background:#F1F5F9;border-radius:3px;margin-top:5px;overflow:hidden;}
.goal-bar-fill{height:100%;border-radius:3px;}
.wd-card{background:#fff;border:1px solid #F0F4F8;border-radius:12px;padding:14px 16px;box-shadow:0 3px 10px rgba(0,0,0,.06);}
.wd-sec{font-size:13px;font-weight:700;color:#0F172A;margin-bottom:10px;padding-bottom:8px;
  border-bottom:1px solid #F1F5F9;display:flex;align-items:center;gap:7px;}
.wd-sec-bar{width:3px;height:15px;border-radius:2px;flex-shrink:0;}
.wd-sec-sub{font-size:11px;color:#94A3B8;font-weight:400;margin-left:3px;}
.badge{border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;display:inline-block;}
.badge-blue{background:#DBEAFE;color:#1E40AF;}.badge-green{background:#DCFCE7;color:#15803D;}
.badge-yellow{background:#FEF3C7;color:#92400E;}.badge-red{background:#FEE2E2;color:#991B1B;}
.badge-purple{background:#EDE9FE;color:#5B21B6;}.badge-gray{background:#F1F5F9;color:#475569;}
.overdue-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #F8FAFC;}
.overdue-label{font-size:12px;font-weight:700;width:80px;flex-shrink:0;}
.overdue-bar-wrap{flex:1;height:8px;background:#F1F5F9;border-radius:4px;overflow:hidden;}
.overdue-bar{height:100%;border-radius:4px;}
.overdue-val{font-size:12px;font-weight:700;font-family:Consolas,monospace;width:65px;text-align:right;flex-shrink:0;}
[data-testid="stTabs"]>div:first-child{border-bottom:1.5px solid #E2E8F0!important;gap:0!important;}
[data-testid="stTabs"] button{font-size:13px!important;font-weight:600!important;padding:6px 16px!important;border-radius:0!important;color:#64748B!important;}
[data-testid="stTabs"] button[aria-selected="true"]{color:#1E40AF!important;border-bottom:2.5px solid #1E40AF!important;background:transparent!important;}
[data-testid="stSelectbox"]>div>div,[data-testid="stMultiSelect"]>div>div{
  border-radius:8px!important;border:1.5px solid #BFDBFE!important;
  background:#EFF6FF!important;font-size:13px!important;font-weight:600!important;color:#1E40AF!important;}
button[kind="secondary"]{font-size:13px!important;height:34px!important;border-radius:8px!important;}
</style>
"""

WARD_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable.css');
*, *::before, *::after { box-sizing: border-box; }
.main,
[data-testid="stAppViewContainer"],
[data-testid="stMarkdownContainer"],
[data-testid="stText"] {
  font-family: 'Pretendard Variable', 'Pretendard', 'Malgun Gothic', -apple-system, sans-serif !important;
  font-size: 14px !important;
  color: #333333;
}
[data-testid="stAppViewContainer"] > .main {
  padding-top: 0.4rem !important;
  padding-left: 0.75rem !important;
  padding-right: 0.75rem !important;
}
.kpi-card {
  background: #FFFFFF;
  border: 1px solid #E8EDF2;
  border-radius: 12px;
  padding: 14px 16px;
  height: 100%;
  min-height: 110px;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(15,23,42,0.06);
  transition: box-shadow 100ms ease;
}
.kpi-card:hover { box-shadow: 0 3px 12px rgba(15,23,42,0.09); }
.kpi-label { font-size:10.5px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.12em; margin-bottom:4px; }
.kpi-value { font-size:30px; font-weight:800; color:#0F172A; font-variant-numeric:tabular-nums; line-height:1; letter-spacing:-0.03em; }
.kpi-unit  { font-size:13px; color:#64748B; font-weight:500; margin-left:3px; }
.kpi-sub   { font-size:11.5px; color:#94A3B8; }
.kpi-delta-up { font-size:13px; font-weight:700; color:#16A34A; }
.kpi-delta-dn { font-size:13px; font-weight:700; color:#DC2626; }
.kpi-delta-nt { font-size:12px; font-weight:600; color:#94A3B8; }
.kpi-bar-bg   { height:3px; background:#F1F5F9; border-radius:2px; overflow:hidden; margin:5px 0; }
.kpi-bar-fill { height:100%; border-radius:2px; transition:width 400ms ease; }
.kpi-num {
  font-size: 15px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.kpi-badge-danger { background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; border-radius:4px; padding:1px 6px; font-size:10px; font-weight:700; }
.kpi-badge-warn   { background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; border-radius:4px; padding:1px 6px; font-size:10px; font-weight:700; }
.kpi-badge-ok     { background:#DCFCE7; color:#15803D; border:1px solid #86EFAC; border-radius:4px; padding:1px 6px; font-size:10px; font-weight:700; }
.wd-card {
  background: #FFFFFF;
  border: 1px solid #E8EDF2;
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 1px 4px rgba(15,23,42,0.06);
  height: 100%;
  transition: box-shadow 100ms ease;
  overflow: hidden;
}
.wd-card:hover { box-shadow: 0 3px 12px rgba(15,23,42,0.09); }
.wd-row-kpi [data-testid="stHorizontalBlock"] { align-items: stretch !important; }
.wd-row-kpi [data-testid="stColumn"] { display: flex !important; flex-direction: column !important; }
.wd-row-kpi [data-testid="stColumn"] > [data-testid="stVerticalBlock"] { flex: 1 !important; display: flex !important; flex-direction: column !important; }
.wd-row-kpi [data-testid="stColumn"]:last-child .wd-card { height: 100% !important; flex: 1 !important; display: flex !important; flex-direction: column !important; }
.wd-row-kpi [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"] { justify-content: space-between !important; }
.wd-row-kpi [data-testid="stColumn"]:first-child [data-testid="stHorizontalBlock"] { align-items: stretch !important; }
.wd-row-kpi [data-testid="stColumn"]:first-child [data-testid="stHorizontalBlock"] [data-testid="stColumn"] { display: flex !important; flex-direction: column !important; }
.wd-row-kpi .kpi-card { flex: 1 !important; height: auto !important; }
.wd-row-chart [data-testid="stHorizontalBlock"] { align-items: stretch !important; }
.wd-row-chart [data-testid="stColumn"] { display: flex !important; flex-direction: column !important; }
.wd-row-chart .wd-card { min-height: 260px; flex: 1 !important; }
.wd-row-free  .wd-card { height: auto; min-height: 0; }
.wd-sec {
  display: flex; align-items: center; gap: 7px;
  font-size: 12px; font-weight: 700; color: #1E293B;
  padding-bottom: 6px; margin-bottom: 8px;
  border-bottom: 1px solid #F1F5F9; line-height: 1.3;
}
.wd-sec-accent { width: 3px; height: 14px; border-radius: 2px; background: linear-gradient(180deg, #1E40AF, #60A5FA); flex-shrink: 0; }
.wd-sec-sub { font-size: 10.5px; color: #94A3B8; font-weight: 400; margin-left: 4px; }
[data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
.element-container { margin-bottom: 0 !important; }
.stPlotlyChart { margin: 0 !important; padding: 0 !important; }
iframe.stPlotlyChart { border: none !important; }
.wd-tbl { width:100%; border-collapse:collapse; font-size:12.5px; table-layout:fixed; }
.wd-th { padding:7px 10px; font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.07em; color:#64748B; background:#F8FAFC; border-bottom:1.5px solid #E2E8F0; white-space:nowrap; }
.wd-td { padding:8px 10px; border-bottom:1px solid #F8FAFC; color:#334155; vertical-align:middle; font-size:12.5px; }
.wd-td-num { font-variant-numeric:tabular-nums; font-family:'Consolas','SF Mono',monospace; font-size:12.5px; }
.badge-ok   { background:#DCFCE7; color:#15803D; border:1px solid #86EFAC; border-radius:5px; padding:2px 9px; font-size:11px; font-weight:700; }
.badge-warn { background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; border-radius:5px; padding:2px 9px; font-size:11px; font-weight:700; }
.badge-err  { background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; border-radius:5px; padding:2px 9px; font-size:11px; font-weight:700; }
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {
  font-size:11.5px !important; font-weight:600 !important; padding:0 14px !important;
  height:32px !important; line-height:32px !important; border-radius:20px !important;
  border:1.5px solid #E2E8F0 !important;
  background:linear-gradient(180deg,#FFFFFF 0%,#F8FAFC 100%) !important;
  color:#475569 !important;
  box-shadow:0 1px 3px rgba(15,23,42,0.06),0 1px 2px rgba(15,23,42,0.04) !important;
  transition:all 120ms ease !important; white-space:nowrap !important;
  overflow:hidden !important; text-overflow:ellipsis !important;
  width:100% !important; letter-spacing:0.01em !important;
}
button[kind="secondary"]:hover, [data-testid="stBaseButton-secondary"]:hover {
  background:linear-gradient(180deg,#F1F5F9 0%,#E2E8F0 100%) !important;
  border-color:#94A3B8 !important; color:#1E293B !important;
  box-shadow:0 3px 8px rgba(15,23,42,0.10) !important; transform:translateY(-1px) !important;
}
button[kind="secondary"]:active, [data-testid="stBaseButton-secondary"]:active {
  transform:translateY(0) !important; box-shadow:0 1px 2px rgba(15,23,42,0.06) !important;
}
button[kind="primary"], [data-testid="stBaseButton-primary"] {
  font-size:11.5px !important; font-weight:700 !important; padding:0 14px !important;
  height:32px !important; border-radius:20px !important; white-space:nowrap !important;
  overflow:hidden !important; text-overflow:ellipsis !important; width:100% !important;
  letter-spacing:0.01em !important; box-shadow:0 2px 6px rgba(30,64,175,0.20) !important;
  transition:all 120ms ease !important;
}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  transform:translateY(-1px) !important; box-shadow:0 4px 12px rgba(30,64,175,0.28) !important;
}
[data-testid="stSelectbox"] > div > div {
  height:34px !important; border-radius:8px !important; border:1.5px solid #BFDBFE !important;
  background:#EFF6FF !important; font-size:12px !important; font-weight:600 !important;
  color:#1E40AF !important; white-space:nowrap !important; overflow:hidden !important;
  text-overflow:ellipsis !important;
}
[data-testid="stSelectbox"] label { display:none !important; }
[data-testid="stMarkdownContainer"]:empty { display:none !important; }
[data-testid="stMarkdownContainer"] > div:empty { display:none !important; }
div[data-testid="stRadio"] { padding: 0 !important; margin: 0 !important; min-height: 0 !important; line-height: 0 !important; }
div[data-testid="stRadio"] > div[data-testid="stWidgetLabel"],
div[data-testid="stRadio"] > label:not([data-baseweb]),
div[data-testid="stRadio"] > p { display: none !important; height: 0 !important; max-height: 0 !important; min-height: 0 !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; opacity: 0 !important; pointer-events: none !important; }
div[data-testid="stRadio"] > div { display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important; gap: 2px !important; align-items: center !important; justify-content: flex-end !important; padding: 0 !important; margin: 0 !important; min-height: 0 !important; line-height: normal !important; }
div[data-testid="stRadio"] label { display: inline-flex !important; align-items: center !important; justify-content: center !important; padding: 2px 8px !important; border-radius: 14px !important; border: 1px solid #E2E8F0 !important; background: #FFFFFF !important; color: #64748B !important; font-size: 10.5px !important; font-weight: 500 !important; cursor: pointer !important; white-space: nowrap !important; margin: 0 !important; transition: background 0.1s, color 0.1s, border-color 0.1s !important; gap: 0 !important; line-height: 1.5 !important; }
div[data-testid="stRadio"] label:hover { background: #F1F5F9 !important; border-color: #93C5FD !important; color: #1E40AF !important; }
div[data-testid="stRadio"] label:has(input:checked) { background: #1E40AF !important; border-color: #1E40AF !important; color: #FFFFFF !important; font-weight: 600 !important; }
div[data-testid="stRadio"] input[type="radio"] { position: absolute !important; opacity: 0 !important; width: 0 !important; height: 0 !important; margin: 0 !important; padding: 0 !important; pointer-events: none !important; }
div[data-testid="stRadio"] label > div:first-child { display: none !important; width: 0 !important; height: 0 !important; min-width: 0 !important; min-height: 0 !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; flex-shrink: 0 !important; }
div[data-testid="stRadio"] label > div:last-child, div[data-testid="stRadio"] label > div:nth-child(2) { display: inline !important; width: auto !important; height: auto !important; overflow: visible !important; }
</style>
"""
