"""ui/finance/tab_analytics.py — 주간추이분석 탭"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
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
except Exception:
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

# backward-compat aliases (same names used in the original finance_dashboard.py)
_kpi_card      = kpi_card
_sec_hd        = section_header
_gap           = gap
_fmt_won       = fmt_won
_plotly_empty  = empty_state
_PALETTE       = PLOTLY_PALETTE
_PLOTLY_LAYOUT = PLOTLY_CFG

# ════════════════════════════════════════════════════════════════════
# 탭 3 — 주간추이분석
# ════════════════════════════════════════════════════════════════════
def _tab_analytics(
    opd_dept_trend: List[Dict],
    los_dist_dept:  List[Dict],
    daily_dept_stat: Optional[List[Dict]] = None,
    ipd_dept_trend:  Optional[List[Dict]] = None,
) -> None:
    from collections import defaultdict as _ddc

    daily_dept_stat = daily_dept_stat or []
    ipd_dept_trend  = ipd_dept_trend  or []
    los_dist_dept   = los_dist_dept   or []

    # ── 분리 배너
    _gap()
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["blue"]}15,{C["indigo"]}10);'
        f'border-left:4px solid {C["blue"]};border-radius:0 8px 8px 0;'
        f'padding:10px 16px;margin-bottom:4px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:18px;">📊</span>'
        f'<div><div style="font-size:13px;font-weight:700;color:{C["blue"]};">주간 통계 · 분석</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'실시간 현황 탭과 별도 집계 — 최근 7일 누적 기준 / 재원일수는 현재 재원 환자 기준'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # ════════════════════
    # [1] 📈 7일간 추이
    # ════════════════════
    _gap()
    st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["blue"] + ';">', unsafe_allow_html=True)
    _sec_hd("📈 7일간 추이", "외래·입원·퇴원·재원 일별 전체 합계", C["blue"])
    if daily_dept_stat and HAS_PLOTLY:
        _trend_day: dict = _ddc(lambda: _ddc(int))
        for _r in daily_dept_stat:
            _rd    = str(_r.get("기준일","")).replace("-","")
            _d_fmt = f"{_rd[4:6]}/{_rd[6:8]}" if len(_rd)>=8 else str(_r.get("기준일",""))[:10]
            _cat   = _r.get("구분","")
            if _cat in ("외래","입원","퇴원","재원"):
                _trend_day[_d_fmt][_cat] += int(_r.get("건수",0) or 0)
        _tr_dates = sorted(_trend_day.keys())[-7:]
        if _tr_dates:
            _tr_colors = {"외래":C["blue"],"입원":C["indigo"],"퇴원":C["t2"],"재원":C["violet"]}
            _tr_dash   = {"외래":"solid","입원":"solid","퇴원":"dot","재원":"dash"}
            _figOPD = go.Figure()
            for _tc in ("외래","입원","퇴원","재원"):
                _ty = [_trend_day[d][_tc] for d in _tr_dates]
                _figOPD.add_trace(go.Scatter(
                    x=_tr_dates, y=_ty, name=_tc, mode="lines+markers",
                    line=dict(color=_tr_colors[_tc], width=2.5, dash=_tr_dash[_tc]),
                    marker=dict(size=6, color=_tr_colors[_tc], line=dict(color="#fff",width=1.5)),
                    hovertemplate=f"%{{x}}<br>{_tc}: %{{y}}명<extra></extra>",
                ))
            _figOPD.update_layout(**_PLOTLY_LAYOUT, height=260,
                margin=dict(l=0,r=0,t=28,b=8),
                legend=dict(orientation="h",y=1.12,x=0.5,xanchor="center",
                            font=dict(size=12),bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified")
            _figOPD.update_xaxes(tickfont=dict(size=12,color="#334155"))
            _figOPD.update_yaxes(title_text="인원 (명)",title_font=dict(size=10,color=C["t3"]))
            st.plotly_chart(_figOPD, use_container_width=True, key="an_7day_trend")
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#94A3B8;">V_DAILY_DEPT_STAT 기준일 컬럼 필요</div>', unsafe_allow_html=True)
    else:
        _plotly_empty()
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    # ═══════════════════════════════════════
    # [2] 히트맵 2분할 — 외래 [1/2] | 입원 [1/2]
    # ═══════════════════════════════════════
    def _render_heatmap(data, value_col, title, sub, color, colorscale, chart_key):
        """
        진료과×날짜 히트맵 공통 렌더러.
        data      : Oracle VIEW 조회 결과 (list of dict)
        value_col : 수치 컬럼명 ("외래환자수" / "입원환자수")
        """
        st.markdown(f'<div class="wd-card" style="border-top:3px solid {color};">', unsafe_allow_html=True)
        _sec_hd(title, sub, color)
        if data and HAS_PLOTLY:
            _all_dates = sorted({str(r.get("기준일",""))[:10] for r in data if r.get("기준일")})[-7:]
            _all_depts = sorted({r.get("진료과명","") for r in data if r.get("진료과명","")})
            if _all_dates and _all_depts:
                _val_map = {
                    (r.get("진료과명",""), str(r.get("기준일",""))[:10]):
                        int(r.get(value_col, 0) or 0)
                    for r in data
                }
                _z = [[_val_map.get((dept,d),0) for d in _all_dates] for dept in _all_depts]
                _x_labels = [f"{d[5:7]}/{d[8:10]}" if len(d)>=10 else d for d in _all_dates]
                _fig_hm = go.Figure(go.Heatmap(
                    z=_z, x=_x_labels, y=_all_depts,
                    colorscale=colorscale,
                    text=[[str(v) if v>0 else "" for v in row] for row in _z],
                    texttemplate="%{text}", textfont=dict(size=9, color="#333"),
                    hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}명<extra></extra>",
                    showscale=False, xgap=2, ygap=2,
                ))
                _h = max(200, len(_all_depts)*22+60)
                _fig_hm.update_layout(**_PLOTLY_LAYOUT, height=_h, margin=dict(l=0,r=0,t=8,b=8))
                _fig_hm.update_xaxes(tickfont=dict(size=10), side="top")
                _fig_hm.update_yaxes(tickfont=dict(size=10), autorange="reversed")
                st.plotly_chart(_fig_hm, use_container_width=True, key=chart_key)
            else:
                _plotly_empty()
        else:
            _view_name = "V_OPD_DEPT_TREND" if "외래" in title else "V_IPD_DEPT_TREND"
            st.markdown(f'<div style="padding:32px;text-align:center;color:#94A3B8;font-size:13px;">데이터 없음 — {_view_name} 확인<br><span style="font-size:11px;">DDL: monthly_views_new.sql</span></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    c_opd, c_ipd = st.columns([1,1], gap="small")
    with c_opd:
        _render_heatmap(
            data=opd_dept_trend, value_col="외래환자수",
            title="🗓️ 진료과별 7일 외래 인원 히트맵", sub="외래 환자수 · 진료과 × 날짜",
            color=C["blue"],
            colorscale=[[0.0,"#EFF6FF"],[0.5,"#3B82F6"],[1.0,"#1E40AF"]],
            chart_key="an_opd_heatmap",
        )
    with c_ipd:
        _render_heatmap(
            data=ipd_dept_trend, value_col="입원환자수",
            title="🗓️ 진료과별 7일 입원 인원 히트맵", sub="입원 환자수 · 진료과 × 날짜",
            color=C["indigo"],
            colorscale=[[0.0,"#EDE9FE"],[0.5,"#7C3AED"],[1.0,"#4C1D95"]],
            chart_key="an_ipd_heatmap",
        )
    _gap()

    # ═════════════════════════════════════
    # [3] 🛏️ 진료과별 재원일수 분포 (스택 바)
    # ═════════════════════════════════════
    st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["violet"] + ';">', unsafe_allow_html=True)
    _sec_hd("🛏️ 진료과별 재원일수 분포", "현재 재원 환자 기준 · 진료과 × 재원일수 구간", C["violet"])
    if los_dist_dept and HAS_PLOTLY:
        # 구간 정렬 (구간순서 컬럼 기준)
        _bins_ordered: list = []
        _seen_bins: set = set()
        for _r in sorted(los_dist_dept, key=lambda x: int(x.get("구간순서",99))):
            _b = _r.get("재원일수구간","")
            if _b and _b not in _seen_bins:
                _bins_ordered.append(_b); _seen_bins.add(_b)

        # 진료과 정렬 (총 환자수 내림차순)
        _dept_total: dict = _ddc(int)
        for _r in los_dist_dept:
            _dept_total[_r.get("진료과명","")] += int(_r.get("환자수",0) or 0)
        _depts_los = sorted([d for d in _dept_total if d], key=lambda d: -_dept_total[d])

        _los_map = {
            (r.get("진료과명",""), r.get("재원일수구간","")): int(r.get("환자수",0) or 0)
            for r in los_dist_dept
        }
        _bin_colors = [C["green"],C["teal"],C["blue"],C["yellow"],C["red"]]
        _fig_los = go.Figure()
        for _i, _bin in enumerate(_bins_ordered):
            _y_vals = [_los_map.get((dept,_bin),0) for dept in _depts_los]
            _fig_los.add_trace(go.Bar(
                name=_bin, x=_depts_los, y=_y_vals,
                marker_color=_bin_colors[_i%len(_bin_colors)],
                marker=dict(line=dict(color="#fff",width=0.5)),
                text=[str(v) if v>0 else "" for v in _y_vals],
                textposition="inside", textfont=dict(size=9,color="#fff"),
                hovertemplate=f"<b>%{{x}}</b><br>{_bin}: %{{y}}명<extra></extra>",
            ))
        _fig_los.update_layout(**_PLOTLY_LAYOUT, barmode="stack", height=320,
            margin=dict(l=0,r=0,t=8,b=50),
            legend=dict(orientation="h",y=-0.20,x=0.5,xanchor="center",
                        font=dict(size=11),bgcolor="rgba(0,0,0,0)"))
        _fig_los.update_xaxes(tickangle=-35, tickfont=dict(size=10), gridcolor="rgba(0,0,0,0)")
        _fig_los.update_yaxes(title_text="환자 수(명)", title_font=dict(size=10,color=C["t3"]))
        st.plotly_chart(_fig_los, use_container_width=True, key="an_los_dept_bar")

        # DRG 임계 경고
        _drg_bins = {b for b in _bins_ordered if any(k in b for k in ("15","30","60"))}
        _drg_by_dept: dict = _ddc(int)
        for _r in los_dist_dept:
            if _r.get("재원일수구간","") in _drg_bins:
                _drg_by_dept[_r.get("진료과명","")] += int(_r.get("환자수",0) or 0)
        _drg_total = sum(_drg_by_dept.values())
        if _drg_total > 0:
            _top3     = sorted(_drg_by_dept.items(), key=lambda x:-x[1])[:3]
            _top3_str = "  |  ".join(f'<b style="color:{C["red"]};">{d}</b> {n}명' for d,n in _top3)
            st.markdown(
                f'<div style="background:{C["red_l"]};border:1px solid #FECDD3;border-radius:8px;'
                f'padding:9px 14px;margin-top:6px;display:flex;align-items:center;gap:10px;">'
                f'<span style="font-size:16px;">⚠️</span>'
                f'<div><span style="font-size:12px;font-weight:700;color:{C["red"]};">'
                f'DRG 임계(15일+) 총 {_drg_total:,}명 — 퇴원 계획 검토 필요</span>'
                f'<div style="font-size:11px;margin-top:2px;">{_top3_str}</div></div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="padding:32px;text-align:center;color:#94A3B8;font-size:13px;">'
            'V_LOS_DIST_DEPT 가 없습니다 — monthly_views_new.sql 실행 후 재시작하세요.</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 탭 4 (신규) — 월간추이분석
#
# [구성]
#   배너   : 월간 분석 설명
#   컨트롤 : 기준월 / 비교월 선택 (selectbox)
#   테이블 : 진료과 × [기준월: 방문자수/신환/신환%/외래전체/구환] × [비교월: 동일] × 비고(신환증감)
#   차트   : 진료과별 신환자수 그룹 바
#
# [필요 VIEW]
#   V_MONTHLY_OPD_DEPT (신규 — DDL: monthly_views_new.sql)
#   컬럼: 기준년월(YYYYMM) / 진료과명 / 방문자수 / 신환자수 / 구환자수 / 외래전체 / 기타건수
# ════════════════════════════════════════════════════════════════════
