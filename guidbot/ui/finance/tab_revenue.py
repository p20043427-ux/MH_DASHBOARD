"""ui/finance/tab_revenue.py — 수납·미수금 탭"""

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
# 탭 2 — 수납·미수금
# ════════════════════════════════════════════════════════════════════
def _tab_revenue(finance_today, finance_trend, finance_by_dept, overdue_stat):
    _tot_amt = sum(int(r.get("금액",0) or 0) for r in finance_today)
    _tot_cnt = sum(int(r.get("건수",0) or 0) for r in finance_today)
    _tot_gol = sum(int(r.get("목표금액",0) or 0) for r in finance_today)
    _gol_pct = round(_tot_amt/_tot_gol*100,1) if _tot_gol > 0 else 0.0
    _ov_amt  = sum(int(r.get("금액",0) or 0) for r in overdue_stat)

    k1,k2,k3,k4 = st.columns(4, gap="small")
    _kpi_card(k1,"💰","금일 수납 합계",_fmt_won(_tot_amt),"",f"건수 {_tot_cnt:,}건",C["blue"],goal_pct=_gol_pct)
    _kpi_card(k2,"🎯","목표 달성률",f"{_gol_pct:.1f}","%",f"목표 {_fmt_won(_tot_gol)}",
              C["green"] if _gol_pct>=100 else C["yellow"] if _gol_pct>=70 else C["red"])
    _kpi_card(k3,"🔴","미수금 합계",_fmt_won(_ov_amt),"","30일 이상 기준",C["red"])
    _kpi_card(k4,"📋","금일 건수",f"{_tot_cnt:,}","건","보험유형 합산",C["indigo"])
    _gap()

    cp, ct = st.columns([2,3], gap="small")
    with cp:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["indigo"] + ';">', unsafe_allow_html=True)
        _sec_hd("🥧 보험유형별 수납","금일 기준", C["indigo"])
        if finance_today and HAS_PLOTLY:
            _labels = [r.get("보험유형","기타") for r in finance_today]
            _values = [int(r.get("금액",0) or 0) for r in finance_today]
            _counts = [int(r.get("건수",0) or 0) for r in finance_today]
            _pcolors= [C["blue"],C["green"],C["yellow"],C["violet"],C["teal"],C["orange"],C["red"]]
            _fig = go.Figure(go.Pie(labels=_labels,values=_values,customdata=_counts,
                hovertemplate="<b>%{label}</b><br>금액:%{value:,}원<br>건수:%{customdata}건<br>%{percent}<extra></extra>",
                marker=dict(colors=_pcolors[:len(_labels)],line=dict(color="#fff",width=2)),
                hole=0.52,textinfo="label+percent",textfont=dict(size=11),insidetextorientation="radial"))
            _fig.update_layout(height=260,margin=dict(l=0,r=0,t=10,b=10),
                paper_bgcolor="rgba(0,0,0,0)",font=dict(color="#333",size=11),
                legend=dict(orientation="v",x=1.02,y=0.5,font=dict(size=11),bgcolor="rgba(0,0,0,0)"),
                annotations=[dict(text=f"<b>{_fmt_won(_tot_amt)}</b>",x=0.5,y=0.5,
                    font=dict(size=13,color=C["t1"]),showarrow=False)])
            st.plotly_chart(_fig, use_container_width=True, key="rev_pie")
            _TH3 = "padding:7px 10px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
            _t3 = (
                '<table style="width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px;">'
                f'<thead><tr><th style="{_TH3}text-align:left;">보험유형</th>'
                f'<th style="{_TH3}text-align:right;">건수</th>'
                f'<th style="{_TH3}text-align:right;">금액</th>'
                f'<th style="{_TH3}text-align:right;">달성률</th></tr></thead><tbody>'
            )
            for i, r in enumerate(finance_today):
                _typ = r.get("보험유형",""); _cnt = int(r.get("건수",0) or 0)
                _amt = int(r.get("금액",0) or 0); _gol = int(r.get("목표금액",0) or 0)
                _pct = round(_amt/_gol*100,1) if _gol>0 else 0.0
                _pc  = C["green"] if _pct>=100 else C["yellow"] if _pct>=70 else C["red"]
                _bg3 = "#F8FAFC" if i%2==0 else "#fff"
                _td3 = f"padding:7px 10px;background:{_bg3};border-bottom:1px solid #F8FAFC;"
                _t3 += (f"<tr><td style='{_td3}font-weight:700;'>{_typ}</td>"
                        f"<td style='{_td3}text-align:right;color:{C['t3']};font-family:Consolas,monospace;'>{_cnt:,}</td>"
                        f"<td style='{_td3}text-align:right;font-weight:700;font-family:Consolas,monospace;'>{_fmt_won(_amt)}</td>"
                        f"<td style='{_td3}text-align:right;font-weight:700;color:{_pc};'>{_pct:.0f}%</td></tr>")
            st.markdown(_t3 + "</tbody></table>", unsafe_allow_html=True)
        else:
            st.markdown('<div style="padding:30px;text-align:center;color:#94A3B8;">V_FINANCE_TODAY 확인</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with ct:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["blue"] + ';">', unsafe_allow_html=True)
        _sec_hd("📈 최근 30일 수납 추세","일별 수납 금액", C["blue"])
        if finance_trend and HAS_PLOTLY:
            _dates = [str(r.get("기준일",""))[:10] for r in finance_trend]
            _amts  = [int(r.get("수납금액",0) or 0)//10000 for r in finance_trend]
            _cnts  = [int(r.get("수납건수",0) or 0) for r in finance_trend]
            _fig2  = go.Figure()
            _fig2.add_trace(go.Bar(x=_dates,y=_amts,name="수납금액(만원)",
                marker_color=C["blue_l"],marker=dict(line=dict(color=C["blue"],width=0.5)),
                hovertemplate="%{x}<br>%{y:,}만원<extra></extra>",yaxis="y"))
            _fig2.add_trace(go.Scatter(x=_dates,y=_amts,name="추세",mode="lines+markers",
                line=dict(color=C["blue"],width=2.5),
                marker=dict(size=5,color=C["blue"],line=dict(color="#fff",width=1.5)),
                hoverinfo="skip",yaxis="y"))
            _fig2.add_trace(go.Bar(x=_dates,y=_cnts,name="수납건수",
                marker_color=C["indigo_l"],marker=dict(line=dict(color=C["indigo"],width=0.5)),
                hovertemplate="%{x}<br>%{y:,}건<extra></extra>",yaxis="y2",visible="legendonly"))
            _fig2.update_layout(**_PLOTLY_LAYOUT,height=250,margin=dict(l=0,r=40,t=8,b=8),
                legend=dict(orientation="h",y=1.06,x=0.5,xanchor="center",font=dict(size=11),bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified",bargap=0.25)
            _fig2.update_xaxes(tickangle=-30,nticks=15)
            _fig2.update_yaxes(tickformat=",",title_text="수납금액(만원)",title_font=dict(size=10,color=C["t3"]))
            _fig2.update_layout(yaxis2=dict(overlaying="y",side="right",showgrid=False,
                tickfont=dict(size=10,color=C["indigo"]),title=dict(text="건수",font=dict(size=10,color=C["indigo"]))))
            st.plotly_chart(_fig2, use_container_width=True, key="rev_trend")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)

    _gap()
    cd2, co = st.columns([3,2], gap="small")
    with cd2:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["teal"] + ';">', unsafe_allow_html=True)
        _sec_hd("🏆 진료과별 수납 현황 (당월)","금액 순위", C["teal"])
        if finance_by_dept and HAS_PLOTLY:
            _depts2 = [r.get("진료과명","") for r in finance_by_dept[:12]]
            _amts2  = [int(r.get("수납금액",0) or 0)//10000 for r in finance_by_dept[:12]]
            _ptc    = [int(r.get("환자수",0) or 0) for r in finance_by_dept[:12]]
            _maxA   = max(_amts2) if _amts2 else 1
            _gcol   = [f"rgba(30,64,175,{0.3+0.7*(_a/_maxA):.2f})" for _a in _amts2]
            _fig3   = go.Figure(go.Bar(x=_amts2,y=_depts2,orientation="h",
                marker=dict(color=_gcol,line=dict(color=C["blue"],width=0.5)),customdata=_ptc,
                text=[f"{_a:,}만" for _a in _amts2],textposition="outside",textfont=dict(size=11,color=C["blue"]),
                hovertemplate="<b>%{y}</b><br>%{x:,}만원<br>환자수:%{customdata}명<extra></extra>"))
            _fig3.update_layout(**_PLOTLY_LAYOUT,height=max(240,len(_depts2)*28),
                margin=dict(l=0,r=60,t=4,b=4),showlegend=False,bargap=0.3)
            _fig3.update_xaxes(ticksuffix="만")
            _fig3.update_yaxes(tickfont=dict(size=11),autorange="reversed")
            st.plotly_chart(_fig3, use_container_width=True, key="rev_dept_bar")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)

    with co:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["red"] + ';">', unsafe_allow_html=True)
        _sec_hd("🔴 미수금 현황","연령별 분류", C["red"])
        if overdue_stat:
            _totO = sum(int(r.get("금액",0) or 0) for r in overdue_stat)
            st.markdown(f'<div style="background:{C["red_l"]};border:1px solid #FECDD3;border-radius:8px;padding:10px 14px;margin-bottom:10px;">'
                        f'<div style="font-size:10px;font-weight:700;color:#991B1B;text-transform:uppercase;letter-spacing:.1em;">미수금 총액</div>'
                        f'<div style="font-size:28px;font-weight:800;color:{C["red"]};">{_fmt_won(_totO)}</div></div>', unsafe_allow_html=True)
            _OC = {"30일미만":(C["green"],C["green_l"]),"30~60일":(C["yellow"],C["yellow_l"]),
                   "60~90일":(C["orange"],C["orange_l"]),"90일이상":(C["red"],C["red_l"])}
            _maxO = max((int(r.get("금액",0) or 0) for r in overdue_stat), default=1)
            for r in overdue_stat:
                _age = r.get("연령구분",""); _amt = int(r.get("금액",0) or 0)
                _cnt = int(r.get("건수",0) or 0); _pctO = round(_amt/_maxO*100) if _maxO>0 else 0
                _oc, _obg = _OC.get(_age, (C["t3"],"#F8FAFC"))
                st.markdown(
                    f'<div class="overdue-row"><span class="overdue-label" style="color:{_oc};">{_age}</span>'
                    f'<div class="overdue-bar-wrap"><div class="overdue-bar" style="width:{_pctO}%;background:{_oc};"></div></div>'
                    f'<span class="overdue-val" style="color:{_oc};">{_fmt_won(_amt)}</span>'
                    f'<span style="font-size:10px;color:{C["t4"]};width:30px;text-align:right;">{_cnt}건</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div style="padding:30px;text-align:center;color:#94A3B8;">V_OVERDUE_STAT 확인</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 탭 3 (기존 탭2) — 주간추이분석  v2.3 전면 재설계
#
# [구성]
#   배너   : 실시간현황과 명시적 분리
#   섹션1  : 📈 7일간 추이  (외래·입원·퇴원·재원 라인)
#   섹션2  : 🗓️ 외래 히트맵 [좌 1/2] | 🗓️ 입원 히트맵 [우 1/2]
#   섹션3  : 🛏️ 진료과별 재원일수 분포 (스택 바 + DRG 경고)
#
# [삭제]
#   ⏱️ 대기시간 추세 (V_WAITTIME_TREND)
#   📈 진료과별 외래 추세 라인 + 진료과 선택기
# ════════════════════════════════════════════════════════════════════
