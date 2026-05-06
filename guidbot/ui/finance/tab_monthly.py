"""ui/finance/tab_monthly.py — 월간추이분석 탭 (V_MONTHLY_OPD_DEPT 기반)"""

from __future__ import annotations
import datetime as _dt_m
from typing import Dict, List, Optional
import streamlit as st

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False  # type: ignore

import sys, os as _os
_PR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../.."))
if _PR not in sys.path:
    sys.path.insert(0, _PR)

try:
    from utils.logger import get_logger as _gl
    from config.settings import settings as _s
    logger = _gl(__name__, log_dir=_s.log_dir)
    _SC = (_s.oracle_schema or "JAIN_WM").upper()
except Exception:
    _SC = "JAIN_WM"
    import logging as _l
    logger = _l.getLogger(__name__)
    if not logger.handlers:
        _fh = _l.StreamHandler()
        _fh.setFormatter(_l.Formatter(
            "[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(_fh)
        logger.setLevel(_l.DEBUG)

from ui.design import (
    C,
    PLOTLY_PALETTE,
    PLOTLY_CFG,
    kpi_card,
    section_header,
    gap,
    fmt_won,
    empty_state,
)

_kpi_card      = kpi_card
_sec_hd        = section_header
_gap           = gap
_fmt_won       = fmt_won
_plotly_empty  = empty_state
_PALETTE       = PLOTLY_PALETTE
_PLOTLY_LAYOUT = PLOTLY_CFG


# ════════════════════════════════════════════════════════════════════
# 탭 4 — 월간추이분석
# ════════════════════════════════════════════════════════════════════
def _tab_monthly(*_, **__) -> None:
    """월간추이분석 탭 — 기준월/비교월 선택 후 조회 버튼으로 쿼리 실행."""

    _SESS_D  = "mon_opd_data"
    _SESS_M1 = "mon_sel_m1"
    _SESS_M2 = "mon_sel_m2"

    # ── 배너 ─────────────────────────────────────────────────────────
    _gap()
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["green"]}15,{C["teal"]}10);'
        f'border-left:4px solid {C["green"]};border-radius:0 8px 8px 0;'
        f'padding:10px 16px;margin-bottom:8px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:18px;">📅</span>'
        f'<div><div style="font-size:13px;font-weight:700;color:{C["green"]};">월간 외래 추이 분석</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'기준월 · 비교월 선택 → 진료과별 외래환자수 / 신환 / 신환비율 비교 · V_MONTHLY_OPD_DEPT'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # ── 24개월 목록 ───────────────────────────────────────────────────
    _ym_opts: List[str] = []
    _td = _dt_m.date.today()
    for _i in range(24):
        _ab = _td.year * 12 + (_td.month - 1) - _i
        _ym_opts.append(f"{_ab // 12}{_ab % 12 + 1:02d}")

    def _fmt_ym(ym: str) -> str:
        return f"{ym[:4]}년 {ym[4:6]}월" if len(ym) >= 6 else ym

    # ── 필터 폼 (st.form → 드롭다운 변경 시 리런 없음) ─────────────────
    with st.form("mon_filter_form", border=False):
        _fc1, _fc2, _fc3, _fc4 = st.columns(
            [2.2, 2.2, 1.2, 0.8], gap="small", vertical_alignment="bottom"
        )
        with _fc1:
            _sel_m1 = st.selectbox(
                "📅 기준월",
                options=_ym_opts,
                index=min(1, len(_ym_opts) - 1),
                format_func=_fmt_ym,
                key="mon_m1",
            )
        with _fc2:
            _sel_m2 = st.selectbox(
                "📅 비교월",
                options=_ym_opts,
                index=0,
                format_func=_fmt_ym,
                key="mon_m2",
            )
        with _fc3:
            _do_load = st.form_submit_button(
                "🔍 조회", type="primary", use_container_width=True
            )
        with _fc4:
            _do_reset = st.form_submit_button("🔄", use_container_width=True, help="초기화")

    # 초기화
    if _do_reset:
        for _k in (_SESS_D, _SESS_M1, _SESS_M2):
            st.session_state.pop(_k, None)
        st.rerun()

    # ── 조회 실행 ─────────────────────────────────────────────────────
    if _do_load:
        if _sel_m1 == _sel_m2:
            st.warning("기준월과 비교월이 같습니다. 다른 달을 선택하세요.")
        else:
            with st.spinner(f"{_fmt_ym(_sel_m1)} / {_fmt_ym(_sel_m2)} 조회 중…"):
                try:
                    from db.oracle_client import execute_query as _eq
                    _rd = _eq(
                        f"SELECT * FROM {_SC}.V_MONTHLY_OPD_DEPT "
                        f"WHERE 기준년월 IN ('{_sel_m1}', '{_sel_m2}') "
                        f"ORDER BY 기준년월 DESC, 진료과명",
                        max_rows=5000,
                    ) or []
                    st.session_state[_SESS_D]  = _rd
                    st.session_state[_SESS_M1] = _sel_m1
                    st.session_state[_SESS_M2] = _sel_m2
                    st.rerun()
                except Exception as _e:
                    st.error(f"조회 오류: {_e}")
        return

    # ── 세션에서 데이터 로드 ──────────────────────────────────────────
    _data     = st.session_state.get(_SESS_D, [])
    _loaded_m1 = st.session_state.get(_SESS_M1)
    _loaded_m2 = st.session_state.get(_SESS_M2)

    if not _data or not _loaded_m1 or not _loaded_m2:
        _gap()
        st.markdown(
            f'<div style="background:linear-gradient(135deg,{C["green"]}08,{C["teal"]}05);'
            f'border:2px dashed {C["green"]}40;border-radius:16px;'
            f'padding:52px 24px;text-align:center;margin:16px 0;">'
            f'<div style="font-size:44px;margin-bottom:14px;">📅</div>'
            f'<div style="font-size:17px;font-weight:700;color:{C["green"]};margin-bottom:8px;">'
            f'월간 외래 추이 분석</div>'
            f'<div style="font-size:13px;color:{C["t2"]};line-height:1.9;margin-bottom:20px;">'
            f'<b style="color:{C["t1"]};">① 기준월</b> 과 '
            f'<b style="color:{C["t1"]};">② 비교월</b> 을 선택한 뒤 '
            f'<b style="color:{C["t1"]};">③ 🔍 조회</b> 를 클릭하세요.</div>'
            f'<div style="display:inline-flex;align-items:center;gap:8px;'
            f'background:{C["green"]}12;border-radius:8px;padding:10px 18px;">'
            f'<code style="font-size:11px;color:{C["green"]};">V_MONTHLY_OPD_DEPT</code>'
            f'<span style="font-size:12px;color:{C["t3"]};">·</span>'
            f'<span style="font-size:11px;color:{C["t3"]};">'
            f'기준년월 / 진료과명 / 외래환자수 / 신환자수 / 구환자수 / 신환비율</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        return

    _m1_label = _fmt_ym(_loaded_m1)
    _m2_label = _fmt_ym(_loaded_m2)

    # ── 조회 결과 배너 ────────────────────────────────────────────────
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["green"]}15,{C["teal"]}10);'
        f'border-left:4px solid {C["green"]};border-radius:0 8px 8px 0;'
        f'padding:8px 16px;margin:4px 0 6px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:16px;">📊</span>'
        f'<div style="font-size:12px;font-weight:700;color:{C["green"]};">'
        f'{_m1_label} (기준) vs {_m2_label} (비교)</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 헬퍼 ─────────────────────────────────────────────────────────
    def _vi(r: dict, key: str) -> int:
        return int(r.get(key, 0) or 0)

    def _vf(r: dict, key: str) -> float:
        v = r.get(key, 0)
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _pct(n: int, d: int) -> str:
        return f"{round(n / d * 100, 1):.1f}%" if d > 0 else "─"

    # ── 데이터 분리 ───────────────────────────────────────────────────
    _d1 = {
        r.get("진료과명", ""): r
        for r in _data
        if str(r.get("기준년월", ""))[:6] == _loaded_m1
    }
    _d2 = {
        r.get("진료과명", ""): r
        for r in _data
        if str(r.get("기준년월", ""))[:6] == _loaded_m2
    }
    _all_depts_raw = sorted(set(list(_d1.keys()) + list(_d2.keys())))
    _dept_visit = {
        d: _vi(_d2.get(d, _d1.get(d, {})), "외래환자수")
        for d in _all_depts_raw
    }
    _all_depts = [d for d in sorted(_all_depts_raw, key=lambda d: -_dept_visit[d]) if d]

    # ── KPI 카드 ─────────────────────────────────────────────────────
    _t1_opd = sum(_vi(r, "외래환자수") for r in _d1.values())
    _t2_opd = sum(_vi(r, "외래환자수") for r in _d2.values())
    _t1_new = sum(_vi(r, "신환자수")   for r in _d1.values())
    _t2_new = sum(_vi(r, "신환자수")   for r in _d2.values())
    _t1_old = sum(_vi(r, "구환자수")   for r in _d1.values())
    _t2_old = sum(_vi(r, "구환자수")   for r in _d2.values())
    _t1_ratio = round(_t1_new / max(_t1_opd, 1) * 100, 1)
    _t2_ratio = round(_t2_new / max(_t2_opd, 1) * 100, 1)
    _diff_opd = _t2_opd - _t1_opd

    _kc1, _kc2, _kc3, _kc4 = st.columns(4, gap="small")
    _kpi_card(_kc1, "👥", f"{_m2_label} 외래", f"{_t2_opd:,}", "명",
              f"전월 {_t1_opd:,}명", C["blue"])
    _kpi_card(_kc2, "🆕", f"{_m2_label} 신환", f"{_t2_new:,}", "명",
              f"전월 {_t1_new:,}명", C["green"])
    _kpi_card(_kc3, "📊", f"{_m2_label} 신환비율", f"{_t2_ratio}", "%",
              f"전월 {_t1_ratio}%", C["teal"])
    _kc4.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid '
        f'{C["red"] if _diff_opd >= 0 else C["blue"]};">'
        f'<div class="fn-kpi-icon">{"📈" if _diff_opd >= 0 else "📉"}</div>'
        f'<div class="fn-kpi-label">외래 증감</div>'
        f'<div style="font-size:18px;font-weight:800;color:'
        f'{C["red"] if _diff_opd >= 0 else C["blue"]};">'
        f'{"▲" if _diff_opd > 0 else "▼"}&nbsp;{abs(_diff_opd):,}'
        f'<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
        f'<div style="font-size:11px;font-weight:700;color:'
        f'{C["red"] if _diff_opd >= 0 else C["blue"]};">'
        f'{round(_diff_opd / max(_t1_opd, 1) * 100, 1):+.1f}%</div></div>',
        unsafe_allow_html=True,
    )
    _gap()

    # ── 진료과별 비교 테이블 ──────────────────────────────────────────
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["green"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📋 진료과별 외래 지표 비교", f"{_m1_label} vs {_m2_label}", C["green"])

    _TH = (
        "padding:5px 8px;font-size:10.5px;font-weight:700;color:#64748B;"
        "border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
    )
    _h1 = (
        f'<th style="{_TH}text-align:left;" rowspan="2">진료과</th>'
        f'<th colspan="4" style="{_TH}text-align:center;color:{C["blue"]};'
        f'border-left:3px solid {C["blue"]}33;">{_m1_label} (기준)</th>'
        f'<th colspan="4" style="{_TH}text-align:center;color:{C["indigo"]};'
        f'border-left:3px solid {C["indigo"]}33;">{_m2_label} (비교)</th>'
        f'<th style="{_TH}text-align:center;color:{C["red"]};" rowspan="2">'
        f'외래 증감</th>'
    )
    _sub = [("외래환자수", C["blue"]), ("신환자수", C["green"]),
            ("구환자수", C["t3"]),    ("신환비율", C["teal"])]
    _h2 = ""
    for _gc in [C["blue"], C["indigo"]]:
        for _si, (_sl, _sc2) in enumerate(_sub):
            _bl = f"border-left:3px solid {_gc}33;" if _si == 0 else ""
            _h2 += f'<th style="{_TH}text-align:right;color:{_sc2};{_bl}">{_sl}</th>'

    _rows = ""
    for _i, _dept in enumerate(_all_depts):
        _r1 = _d1.get(_dept, {}); _r2 = _d2.get(_dept, {})
        _opd1 = _vi(_r1, "외래환자수"); _new1 = _vi(_r1, "신환자수")
        _old1 = _vi(_r1, "구환자수");   _rat1 = _vf(_r1, "신환비율")
        _opd2 = _vi(_r2, "외래환자수"); _new2 = _vi(_r2, "신환자수")
        _old2 = _vi(_r2, "구환자수");   _rat2 = _vf(_r2, "신환비율")

        _diff  = _opd2 - _opd1
        _dpct  = f"({round(_diff / max(_opd1, 1) * 100, 1):+.1f}%)" if _opd1 > 0 and _diff != 0 else ""
        _dstr  = (f"{'▲' if _diff > 0 else '▼'} {abs(_diff):,} {_dpct}") if _diff != 0 else "─"
        _dc    = C["red"] if _diff > 0 else C["blue"] if _diff < 0 else C["t3"]

        _bg  = "#F8FAFC" if _i % 2 == 0 else "#FFFFFF"
        _td  = (f"padding:5px 8px;background:{_bg};border-bottom:1px solid #F1F5F9;"
                f"font-size:12px;font-family:Consolas,monospace;text-align:right;")
        _tdl = _td.replace("text-align:right;", "text-align:left;") + "font-family:inherit;font-weight:600;"

        _rows += (
            f"<tr>"
            f'<td style="{_tdl}">{_dept}</td>'
            f'<td style="{_td}border-left:3px solid {C["blue"]}33;">{_opd1:,}</td>'
            f'<td style="{_td}color:{C["green"]};font-weight:700;">{_new1:,}</td>'
            f'<td style="{_td}">{_old1:,}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_rat1:.1f}%</td>'
            f'<td style="{_td}border-left:3px solid {C["indigo"]}33;">{_opd2:,}</td>'
            f'<td style="{_td}color:{C["green"]};font-weight:700;">{_new2:,}</td>'
            f'<td style="{_td}">{_old2:,}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_rat2:.1f}%</td>'
            f'<td style="{_td}text-align:center;font-weight:700;color:{_dc};">{_dstr}</td>'
            f"</tr>"
        )

    # 합계 행
    _t1_rat_avg = round(sum(_vf(r, "신환비율") for r in _d1.values()) / max(len(_d1), 1), 1)
    _t2_rat_avg = round(sum(_vf(r, "신환비율") for r in _d2.values()) / max(len(_d2), 1), 1)
    _tdif = _t2_opd - _t1_opd
    _tdif_pct = f"({round(_tdif / max(_t1_opd, 1) * 100, 1):+.1f}%)" if _t1_opd > 0 and _tdif != 0 else ""
    _tdif_str = (f"{'▲' if _tdif > 0 else '▼'} {abs(_tdif):,} {_tdif_pct}") if _tdif != 0 else "─"
    _tdif_c   = C["red"] if _tdif > 0 else C["blue"] if _tdif < 0 else C["t3"]
    _tdc  = ("padding:6px 8px;background:#F0FDF4;border-top:2px solid #86EFAC;"
             "font-size:12.5px;font-family:Consolas,monospace;text-align:right;font-weight:800;")
    _tdcl = _tdc.replace("text-align:right;", "text-align:left;") + "color:#15803D;font-family:inherit;"

    _rows += (
        f"<tr>"
        f'<td style="{_tdcl}">합계 / 평균</td>'
        f'<td style="{_tdc}border-left:3px solid {C["blue"]}33;">{_t1_opd:,}</td>'
        f'<td style="{_tdc}color:{C["green"]};">{_t1_new:,}</td>'
        f'<td style="{_tdc}">{_t1_old:,}</td>'
        f'<td style="{_tdc}color:{C["teal"]};">{_t1_rat_avg:.1f}%</td>'
        f'<td style="{_tdc}border-left:3px solid {C["indigo"]}33;">{_t2_opd:,}</td>'
        f'<td style="{_tdc}color:{C["green"]};">{_t2_new:,}</td>'
        f'<td style="{_tdc}">{_t2_old:,}</td>'
        f'<td style="{_tdc}color:{C["teal"]};">{_t2_rat_avg:.1f}%</td>'
        f'<td style="{_tdc}text-align:center;color:{_tdif_c};">{_tdif_str}</td>'
        f"</tr>"
    )

    st.markdown(
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        f'<thead><tr>{_h1}</tr><tr>{_h2}</tr></thead>'
        f'<tbody>{_rows}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;'
        f'padding-top:6px;border-top:1px solid #F1F5F9;font-size:10.5px;">'
        f'<span style="color:{C["blue"]};font-weight:700;">외래환자수: 해당 월 전체 내원</span>'
        f'<span style="color:{C["green"]};font-weight:700;">🆕 신환: 첫 방문 환자</span>'
        f'<span style="color:{C["t3"]};">구환: 재방문 환자</span>'
        f'<span style="color:{C["teal"]};">신환비율 = 신환/외래×100</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    if not HAS_PLOTLY or not _all_depts:
        return

    # ── 차트 1: 진료과별 외래환자수 비교 막대 ────────────────────────
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 진료과별 외래환자수 비교", f"{_m1_label} vs {_m2_label}", C["blue"])

    _opd1_vals = [_vi(_d1.get(d, {}), "외래환자수") for d in _all_depts]
    _opd2_vals = [_vi(_d2.get(d, {}), "외래환자수") for d in _all_depts]
    _diff_vals = [_opd2_vals[i] - _opd1_vals[i] for i in range(len(_all_depts))]
    _diff_text = [
        f"{'▲' if v > 0 else '▼' if v < 0 else ''}{abs(v)}" if v != 0 else ""
        for v in _diff_vals
    ]
    _diff_c2 = [C["red"] if v > 0 else C["blue"] if v < 0 else "rgba(0,0,0,0)" for v in _diff_vals]

    _fig_opd = go.Figure()
    _fig_opd.add_trace(go.Bar(
        name=f"{_m1_label} 외래",
        x=_all_depts, y=_opd1_vals,
        marker_color=C.get("blue_l", "#BFDBFE"),
        marker=dict(line=dict(color=C["blue"], width=0.5)),
        hovertemplate=f"<b>%{{x}}</b><br>{_m1_label}: %{{y:,}}명<extra></extra>",
    ))
    _fig_opd.add_trace(go.Bar(
        name=f"{_m2_label} 외래",
        x=_all_depts, y=_opd2_vals,
        marker_color=C.get("indigo_l", "#C7D2FE"),
        marker=dict(line=dict(color=C["indigo"], width=0.5)),
        hovertemplate=f"<b>%{{x}}</b><br>{_m2_label}: %{{y:,}}명<extra></extra>",
    ))
    _fig_opd.add_trace(go.Scatter(
        x=_all_depts,
        y=[max(a, b) + 1 for a, b in zip(_opd1_vals, _opd2_vals)],
        mode="text", text=_diff_text,
        textfont=dict(size=10, color=_diff_c2),
        showlegend=False, hoverinfo="skip",
    ))
    _fig_opd.update_layout(
        **_PLOTLY_LAYOUT, barmode="group", height=320,
        margin=dict(l=0, r=0, t=30, b=60),
        legend=dict(orientation="h", y=1.10, x=0.5, xanchor="center",
                    font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        bargap=0.2, bargroupgap=0.05,
    )
    _fig_opd.update_xaxes(tickangle=-35, tickfont=dict(size=10))
    _fig_opd.update_yaxes(title_text="외래환자수(명)", title_font=dict(size=10, color=C["t3"]))
    st.plotly_chart(_fig_opd, use_container_width=True, key="mon_opd_bar")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    # ── 차트 2: 진료과별 신환자수 비교 막대 ──────────────────────────
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["green"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 진료과별 신환자수 비교", f"{_m1_label} vs {_m2_label}", C["green"])

    _new1_vals = [_vi(_d1.get(d, {}), "신환자수") for d in _all_depts]
    _new2_vals = [_vi(_d2.get(d, {}), "신환자수") for d in _all_depts]
    _ndiff_vals = [_new2_vals[i] - _new1_vals[i] for i in range(len(_all_depts))]
    _ndiff_text = [
        f"{'▲' if v > 0 else '▼' if v < 0 else ''}{abs(v)}" if v != 0 else ""
        for v in _ndiff_vals
    ]
    _ndiff_c = [C["red"] if v > 0 else C["blue"] if v < 0 else "rgba(0,0,0,0)" for v in _ndiff_vals]

    _fig_new = go.Figure()
    _fig_new.add_trace(go.Bar(
        name=f"{_m1_label} 신환",
        x=_all_depts, y=_new1_vals,
        marker_color=C.get("blue_l", "#BFDBFE"),
        marker=dict(line=dict(color=C["blue"], width=0.5)),
        hovertemplate=f"<b>%{{x}}</b><br>{_m1_label}: %{{y:,}}명<extra></extra>",
    ))
    _fig_new.add_trace(go.Bar(
        name=f"{_m2_label} 신환",
        x=_all_depts, y=_new2_vals,
        marker_color=C.get("indigo_l", "#C7D2FE"),
        marker=dict(line=dict(color=C["indigo"], width=0.5)),
        hovertemplate=f"<b>%{{x}}</b><br>{_m2_label}: %{{y:,}}명<extra></extra>",
    ))
    _fig_new.add_trace(go.Scatter(
        x=_all_depts,
        y=[max(a, b) + 1 for a, b in zip(_new1_vals, _new2_vals)],
        mode="text", text=_ndiff_text,
        textfont=dict(size=10, color=_ndiff_c),
        showlegend=False, hoverinfo="skip",
    ))
    _fig_new.update_layout(
        **_PLOTLY_LAYOUT, barmode="group", height=320,
        margin=dict(l=0, r=0, t=30, b=60),
        legend=dict(orientation="h", y=1.10, x=0.5, xanchor="center",
                    font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        bargap=0.2, bargroupgap=0.05,
    )
    _fig_new.update_xaxes(tickangle=-35, tickfont=dict(size=10))
    _fig_new.update_yaxes(title_text="신환자수(명)", title_font=dict(size=10, color=C["t3"]))
    st.plotly_chart(_fig_new, use_container_width=True, key="mon_new_bar")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    # ── 차트 3: 진료과별 신환비율 비교 (수평 막대) ───────────────────
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["teal"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 진료과별 신환비율 비교", f"{_m1_label} vs {_m2_label} (%)", C["teal"])

    _rat1_vals = [_vf(_d1.get(d, {}), "신환비율") for d in _all_depts]
    _rat2_vals = [_vf(_d2.get(d, {}), "신환비율") for d in _all_depts]

    _fig_rat = go.Figure()
    _fig_rat.add_trace(go.Bar(
        name=f"{_m1_label} 신환비율",
        y=_all_depts, x=_rat1_vals,
        orientation="h",
        marker_color=C.get("teal_l", "#99F6E4") if C.get("teal_l") else "#99F6E4",
        marker=dict(line=dict(color=C["teal"], width=0.5)),
        hovertemplate=f"<b>%{{y}}</b><br>{_m1_label}: %{{x:.1f}}%<extra></extra>",
    ))
    _fig_rat.add_trace(go.Bar(
        name=f"{_m2_label} 신환비율",
        y=_all_depts, x=_rat2_vals,
        orientation="h",
        marker_color=C["teal"],
        marker=dict(line=dict(color=C["teal"], width=0.5), opacity=0.8),
        hovertemplate=f"<b>%{{y}}</b><br>{_m2_label}: %{{x:.1f}}%<extra></extra>",
    ))
    _fig_rat.update_layout(
        **_PLOTLY_LAYOUT, barmode="group", height=max(280, len(_all_depts) * 28),
        margin=dict(l=0, r=40, t=30, b=20),
        legend=dict(orientation="h", y=1.06, x=0.5, xanchor="center",
                    font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        bargap=0.25,
    )
    _fig_rat.update_xaxes(
        title_text="신환비율(%)", title_font=dict(size=10, color=C["t3"]),
        ticksuffix="%",
    )
    _fig_rat.update_yaxes(tickfont=dict(size=10), autorange="reversed")
    st.plotly_chart(_fig_rat, use_container_width=True, key="mon_ratio_bar")
    st.markdown("</div>", unsafe_allow_html=True)
