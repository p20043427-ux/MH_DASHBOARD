"""ui/finance/tab_realtime.py — 실시간 현황 탭 + AI 채팅 + 세부과 집계표"""

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
# 탭 1 — 실시간 현황
# ════════════════════════════════════════════════════════════════════
def _tab_realtime(opd_kpi, dept_status, kiosk_status, discharge_pipe, bed_detail,
                  kiosk_by_dept=None, kiosk_counter_trend=None, ward_room_detail=None,
                  opd_dept_trend=None, daily_dept_stat=None):
    opd_dept_trend      = opd_dept_trend   or []
    daily_dept_stat     = daily_dept_stat  or []
    kiosk_by_dept       = kiosk_by_dept       or []
    kiosk_counter_trend = kiosk_counter_trend or []
    ward_room_detail    = ward_room_detail    or []

    def _ds_sum(cat):
        return sum(int(r.get("건수", 0) or 0) for r in daily_dept_stat if r.get("구분") == cat)

    _opd_total = _ds_sum("외래") or (
        sum(int(r.get("대기",0) or 0)+int(r.get("진료중",0) or 0)+int(r.get("완료",0) or 0)
            for r in dept_status))
    _adm  = _ds_sum("입원") or sum(int(r.get("금일입원",0) or 0) for r in bed_detail)
    _disc = _ds_sum("퇴원") or sum(int(r.get("금일퇴원",0) or 0) for r in bed_detail)
    _stay = _ds_sum("재원") or sum(int(r.get("재원수",   0) or 0) for r in bed_detail)
    _opd_wait = sum(int(r.get("대기",0) or 0)   for r in dept_status)
    _opd_proc = sum(int(r.get("진료중",0) or 0) for r in dept_status)
    _opd_done = sum(int(r.get("완료",0) or 0)   for r in dept_status)

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid {C["blue"]};">'
        f'<div class="fn-kpi-icon">👥</div>'
        f'<div class="fn-kpi-label">금일 외래</div>'
        f'<div class="fn-kpi-value" style="color:{C["blue"]};">{_opd_total:,}'
        f'<span class="fn-kpi-unit">명</span></div>'
        f'<div style="display:flex;gap:4px;margin-top:6px;flex-wrap:wrap;">'
        f'<span style="background:{C["yellow"]}22;color:{C["yellow"]};border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;">대기 {_opd_wait}</span>'
        f'<span style="background:{C["blue"]}22;color:{C["blue"]};border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;">보류 {_opd_proc}</span>'
        f'<span style="background:{C["green"]}22;color:{C["green"]};border-radius:4px;padding:2px 6px;font-size:10px;font-weight:700;">완료 {_opd_done}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    _kpi_card(k2, "🏥", "금일 입원",  f"{_adm:,}",  "명", "입원 처리 완료",   C["indigo"])
    _kpi_card(k3, "📤", "금일 퇴원",  f"{_disc:,}", "명", "퇴원 처리 완료",   C["t2"])
    _kpi_card(k4, "🛏️", "현재 재원",  f"{_stay:,}", "명",
              f"총병상 {sum(int(r.get('총병상',0) or 0) for r in bed_detail)}개 기준", C["violet"])
    _gap()

    if bed_detail:
        _total_bed = sum(int(r.get("총병상",0) or 0) for r in bed_detail)
        _occ_rate  = round(_stay / max(_total_bed,1)*100, 1)
        _ndc_pre   = sum(int(r.get("익일퇴원예약",0) or 0) for r in bed_detail)
        _rest      = max(0, _total_bed - _stay)
        _oc        = "#DC2626" if _occ_rate >= 90 else "#F59E0B" if _occ_rate >= 80 else "#059669"
        _ward_kpi  = [
            ("가동률",      f"{_occ_rate:.1f}", _oc,       "%",  "🏥"),
            ("총병상",      str(_total_bed),    "#64748B", "개", "🛏️"),
            ("잔여병상",    str(_rest),         "#059669", "개", "✅"),
            ("익일퇴원예정",str(_ndc_pre),      "#7C3AED", "명", "📤"),
        ]
        _wk_cols = st.columns(len(_ward_kpi), gap="small")
        for _wki, (_wl, _wv, _wc, _wu, _ico) in enumerate(_ward_kpi):
            _wk_cols[_wki].markdown(
                f'<div class="fn-kpi" style="border-top:3px solid {_wc};min-height:80px;">'
                f'<div class="fn-kpi-icon">{_ico}</div>'
                f'<div class="fn-kpi-label">{_wl}</div>'
                f'<div class="fn-kpi-value" style="color:{_wc};">{_wv}'
                f'<span class="fn-kpi-unit">{_wu}</span></div></div>',
                unsafe_allow_html=True,
            )

    if st.session_state.get("fn_show_room", False) and ward_room_detail:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:12px 14px;margin-bottom:8px;">',
            unsafe_allow_html=True,
        )
        _TH_R = "padding:6px 8px;font-size:10px;font-weight:700;text-transform:uppercase;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        _rh = (
            '<div style="overflow-x:auto;max-height:280px;overflow-y:auto;">'
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>'
            f'<th style="{_TH_R}text-align:left;">병동</th>'
            f'<th style="{_TH_R}text-align:center;">병실</th>'
            f'<th style="{_TH_R}text-align:center;">베드</th>'
            f'<th style="{_TH_R}text-align:center;">상태</th>'
            f'<th style="{_TH_R}text-align:center;">성별</th>'
            f'<th style="{_TH_R}text-align:left;">진료과</th>'
            f'<th style="{_TH_R}text-align:right;">병실료</th>'
            '</tr></thead><tbody>'
        )
        _STATUS_CLR = {"재원":("#1D4ED8","#DBEAFE"),"퇴원예정":("#7C3AED","#EDE9FE"),
                       "빈병상":("#16A34A","#DCFCE7"),"LOCK":("#DC2626","#FEE2E2")}
        for _ri, _r in enumerate(ward_room_detail[:80]):
            _bno = str(_r.get("병실번호","")).zfill(6)
            _sc, _sbg = _STATUS_CLR.get(_r.get("상태","빈병상"), ("#64748B","#F1F5F9"))
            _fee = int(_r.get("병실료", 0) or 0)
            _bg_r = "#F8FAFC" if _ri % 2 == 0 else "#FFFFFF"
            _td_r = f"padding:5px 8px;background:{_bg_r};border-bottom:1px solid #F8FAFC;"
            _rh += (
                f"<tr>"
                f'<td style="{_td_r}font-weight:600;">{_r.get("병동명","")}</td>'
                f'<td style="{_td_r}text-align:center;font-family:Consolas,monospace;">{_bno[2:4]}</td>'
                f'<td style="{_td_r}text-align:center;font-family:Consolas,monospace;color:#7C3AED;">{_bno[4:6]}</td>'
                f'<td style="{_td_r}text-align:center;">'
                f'<span style="background:{_sbg};color:{_sc};border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;">{_r.get("상태","")}</span></td>'
                f'<td style="{_td_r}text-align:center;font-weight:600;">{_r.get("성별","─")}</td>'
                f'<td style="{_td_r}">{_r.get("진료과","─")}</td>'
                f'<td style="{_td_r}text-align:right;font-family:Consolas,monospace;">{"─" if not _fee else f"{_fee:,}원"}</td>'
                f"</tr>"
            )
        st.markdown(_rh + "</tbody></table></div></div>", unsafe_allow_html=True)
    elif st.session_state.get("fn_show_room", False):
        st.info("V_WARD_ROOM_DETAIL 데이터 없음 — Oracle 연결 확인")

    _gap()

    # ── 일일현황 테이블
    st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["blue"] + ';">', unsafe_allow_html=True)
    _sec_hd("📋 일일현황", "진료과별 외래·입원·퇴원·재원 (보험구분)", C["blue"])
    _INS_CODES = ["공단", "보호", "산재", "자보", "기타"]
    _CATS      = ["외래", "입원", "퇴원", "재원"]
    _CAT_COLORS= {"외래":C["blue"],"입원":C["indigo"],"퇴원":C["t2"],"재원":C["violet"]}
    if daily_dept_stat:
        from collections import defaultdict as _ddd2
        _agg: dict = _ddd2(lambda: _ddd2(lambda: _ddd2(int)))
        for _r in daily_dept_stat:
            _dept = _r.get("진료과명",""); _cat = _r.get("구분","")
            _ins  = _r.get("보험구분","기타"); _cnt = int(_r.get("건수",0) or 0)
            if _dept and _cat: _agg[_dept][_cat][_ins] += _cnt
        _depts = sorted(_agg.keys())
        _TH_D = "padding:4px 6px;font-size:11px;font-weight:700;letter-spacing:.02em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;text-align:right;"
        _TH_L = _TH_D.replace("text-align:right;","text-align:left;")
        _colspan = len(_INS_CODES) + 1
        _gh = "".join(
            f'<th colspan="{_colspan}" style="padding:4px;font-size:11.5px;font-weight:800;'
            f'color:{_CAT_COLORS[c]};border-bottom:1px solid #E2E8F0;background:#F8FAFC;'
            f'text-align:center;border-left:2px solid {_CAT_COLORS[c]}33;">{c}</th>'
            for c in _CATS
        )
        _sh2 = "".join(
            (f'<th style="{_TH_D}border-left:2px solid {_CAT_COLORS[c]}33;">{ins}</th>'
             if i == 0 else f'<th style="{_TH_D}">{ins}</th>') +
            (f'<th style="{_TH_D}color:{_CAT_COLORS[c]};font-weight:800;">계</th>'
             if i == len(_INS_CODES)-1 else "")
            for c in _CATS for i, ins in enumerate(_INS_CODES)
        )
        _rows_d = ""
        _tot: dict = _ddd2(lambda: _ddd2(int))
        for _di, _dept in enumerate(_depts):
            _rbg = "#F8FAFC" if _di%2==0 else "#FFFFFF"
            _td_s = f"padding:4px 5px;background:{_rbg};border-bottom:1px solid #F1F5F9;font-size:12px;font-family:Consolas,monospace;text-align:right;"
            _rows_d += (f'<tr><td style="{_td_s.replace("text-align:right;","text-align:left;")}'
                        f'font-weight:700;font-family:inherit;color:#0F172A;white-space:nowrap;">{_dept}</td>')
            for _ci, _cat in enumerate(_CATS):
                _subtot = 0
                for _ii, _ins in enumerate(_INS_CODES):
                    _v = _agg[_dept][_cat][_ins]; _subtot += _v; _tot[_cat][_ins] += _v
                    _bl2 = f"border-left:2px solid {_CAT_COLORS[_cat]}33;" if _ii==0 else ""
                    _rows_d += f'<td style="{_td_s}{_bl2}">{"─" if _v==0 else _v}</td>'
                _tot[_cat]["계"] += _subtot
                _rows_d += (f'<td style="{_td_s}font-weight:700;color:{_CAT_COLORS[_cat]};">'
                            f'{"─" if _subtot==0 else _subtot}</td>')
            _rows_d += "</tr>"
        _sth_d = "padding:4px 5px;background:#EFF6FF;border-top:2px solid #BFDBFE;font-size:12px;font-family:Consolas,monospace;text-align:right;font-weight:700;"
        _rows_d += f'<tr><td style="{_sth_d.replace("text-align:right;","text-align:left;")}font-family:inherit;color:#1E40AF;">합계</td>'
        for _cat in _CATS:
            for _ii, _ins in enumerate(_INS_CODES):
                _v = _tot[_cat][_ins]
                _bl2 = f"border-left:2px solid {_CAT_COLORS[_cat]}33;" if _ii==0 else ""
                _rows_d += f'<td style="{_sth_d}{_bl2}color:{_CAT_COLORS[_cat]};">{"─" if _v==0 else _v}</td>'
            _v2 = _tot[_cat]["계"]
            _rows_d += (f'<td style="{_sth_d}color:{_CAT_COLORS[_cat]};font-size:12.5px;">{"─" if _v2==0 else _v2}</td>')
        _rows_d += "</tr>"
        st.markdown(
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
            f'<thead><tr><th style="{_TH_L}min-width:40px;">진료과</th>{_gh}</tr>'
            f'<tr><th style="{_TH_L}"></th>{_sh2}</tr>'
            f'</thead><tbody>{_rows_d}</tbody></table></div>',
            unsafe_allow_html=True,
        )

    # 파이차트
    _PALETTE_P = [
        "#1E40AF","#4F46E5","#0891B2","#059669","#D97706",
        "#DC2626","#7C3AED","#DB2777","#65A30D","#9333EA",
        "#0284C7","#16A34A","#EA580C","#0F766E","#BE185D",
    ]
    _PIE_DEFS = [
        ("외래","🥧 외래 진료과별 구성",C["blue"],   "daily_pie_opd"),
        ("입원","🥧 입원 진료과별 구성",C["indigo"], "daily_pie_adm"),
        ("재원","🥧 재원 진료과별 구성",C["violet"], "daily_pie_stay"),
    ]
    if daily_dept_stat and HAS_PLOTLY:
        from collections import defaultdict as _ddd_pie
        _pie_all: dict = _ddd_pie(lambda: _ddd_pie(int))
        for _r in daily_dept_stat:
            _cat_p = _r.get("구분",""); _dept_p = _r.get("진료과명","")
            if _cat_p and _dept_p:
                _pie_all[_cat_p][_dept_p] += int(_r.get("건수",0) or 0)
        _pie_cols = st.columns(3, gap="small")
        for _pci, (_pcat, _ptitle, _pclr, _pkey) in enumerate(_PIE_DEFS):
            _pd = _pie_all.get(_pcat, {})
            with _pie_cols[_pci]:
                st.markdown(f'<div style="background:#FFFFFF;border:1px solid #F0F4F8;border-top:3px solid {_pclr};border-radius:10px;padding:10px 12px;">', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:12px;font-weight:700;color:{_pclr};margin-bottom:4px;">{_ptitle}</div>', unsafe_allow_html=True)
                if _pd:
                    _sorted_d = sorted(_pd.items(), key=lambda x:-x[1])
                    _top10    = _sorted_d[:10]; _etc_sum = sum(v for _,v in _sorted_d[10:])
                    _pl = [k for k,_ in _top10]; _pv = [v for _,v in _top10]
                    if _etc_sum > 0: _pl.append("기타"); _pv.append(_etc_sum)
                    _ptotal = sum(_pv)
                    _figP = go.Figure(go.Pie(
                        labels=_pl, values=_pv,
                        marker=dict(colors=_PALETTE_P[:len(_pl)], line=dict(color="#fff",width=1.5)),
                        hole=0.48, textinfo="label+percent", textfont=dict(size=10),
                        insidetextorientation="radial", sort=True,
                        hovertemplate="<b>%{label}</b><br>%{value:,}명 (%{percent})<extra></extra>",
                    ))
                    _figP.update_layout(**_PLOTLY_LAYOUT, height=300,
                        margin=dict(l=0,r=0,t=4,b=4), showlegend=False,
                        annotations=[dict(text=f"<b>{_ptotal:,}</b><br><span style='font-size:10px'>명</span>",
                            x=0.5,y=0.5,font=dict(size=13,color=_pclr),showarrow=False)])
                    st.plotly_chart(_figP, use_container_width=True, key=_pkey)
                else:
                    st.markdown(f'<div style="height:200px;display:flex;align-items:center;justify-content:center;color:#94A3B8;font-size:12px;">데이터 없음</div>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()

    # 키오스크
    ck, cd = st.columns([1,1], gap="small")
    with ck:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["violet"] + ';">', unsafe_allow_html=True)
        _sec_hd("🖥️ 키오스크 진료과별 수납 건수","금일 기준", C["violet"])
        if kiosk_by_dept:
            _k_total = sum(int(r.get("수납건수",0) or 0) for r in kiosk_by_dept)
            st.markdown(f'<div style="font-size:10px;color:#64748B;margin-bottom:8px;">총 <b style="color:{C["violet"]};font-size:13px;">{_k_total:,}</b>건</div>', unsafe_allow_html=True)
            _TH_K = "padding:6px 8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
            _tk = (
                '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>'
                f'<th style="{_TH_K}text-align:left;">진료과</th>'
                f'<th style="{_TH_K}text-align:right;color:{C["violet"]};">건수</th>'
                f'<th style="{_TH_K}text-align:right;color:{C["indigo"]};">금액(만)</th>'
                f'<th style="{_TH_K}">비율</th></tr></thead><tbody>'
            )
            for _ki, _r in enumerate(kiosk_by_dept[:15]):
                _kd = _r.get("진료과명",""); _kc = int(_r.get("수납건수",0) or 0)
                _ka = int(_r.get("수납금액",0) or 0); _kp = round(_kc/max(_k_total,1)*100)
                _kbg = "#F8FAFC" if _ki%2==0 else "#FFFFFF"
                _td_k = f"padding:5px 8px;background:{_kbg};border-bottom:1px solid #F8FAFC;"
                _tk += (
                    f"<tr><td style='{_td_k}font-weight:600;'>{_kd}</td>"
                    f"<td style='{_td_k}text-align:right;color:{C['violet']};font-family:Consolas,monospace;font-weight:700;'>{_kc:,}</td>"
                    f"<td style='{_td_k}text-align:right;color:{C['indigo']};font-family:Consolas,monospace;'>{_ka//10000 if _ka else '─'}만</td>"
                    f"<td style='{_td_k}'><div style='display:flex;align-items:center;gap:4px;'>"
                    f"<div style='flex:1;height:6px;background:#F1F5F9;border-radius:3px;'>"
                    f"<div style='width:{_kp}%;height:100%;background:{C['violet']};border-radius:3px;'></div></div>"
                    f"<span style='font-size:10px;color:#64748B;'>{_kp}%</span></div></td></tr>"
                )
            st.markdown(_tk + "</tbody></table>", unsafe_allow_html=True)
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)

    with cd:
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["teal"] + ';">', unsafe_allow_html=True)
        _sec_hd("📈 7일간 키오스크 vs 창구 수납 건수","일별 추이", C["teal"])
        if kiosk_counter_trend and HAS_PLOTLY:
            def _fmt_date(d):
                s = str(d).replace('-','')[:8]
                return f"{s[4:6]}/{s[6:8]}" if len(s) >= 8 else str(d)[:10]
            _dates_k = [_fmt_date(r.get("기준일","")) for r in kiosk_counter_trend]
            _k_vals  = [int(r.get("키오스크건수",0) or 0) for r in kiosk_counter_trend]
            _c_vals  = [int(r.get("창구건수",    0) or 0) for r in kiosk_counter_trend]
            _figKC = go.Figure()
            _figKC.add_trace(go.Bar(x=_dates_k,y=_k_vals,name="키오스크",
                marker_color=C["violet"],marker=dict(line=dict(width=0)),
                text=_k_vals,textposition="outside",textfont=dict(size=11,color=C["violet"]),
                hovertemplate="%{x}<br>키오스크: %{y}건<extra></extra>"))
            _figKC.add_trace(go.Bar(x=_dates_k,y=_c_vals,name="창구",
                marker_color=C["teal"],marker=dict(line=dict(width=0)),
                text=_c_vals,textposition="outside",textfont=dict(size=11,color=C["teal"]),
                hovertemplate="%{x}<br>창구: %{y}건<extra></extra>"))
            _kc_max = max(max(_k_vals,default=0),max(_c_vals,default=0))
            _figKC.update_layout(**_PLOTLY_LAYOUT,barmode="group",height=280,
                margin=dict(l=0,r=0,t=30,b=8),
                legend=dict(orientation="h",y=1.12,x=0.5,xanchor="center",font=dict(size=12),bgcolor="rgba(0,0,0,0)"),
                bargap=0.25,bargroupgap=0.05)
            _figKC.update_xaxes(tickfont=dict(size=12,color="#334155"))
            _figKC.update_yaxes(title_text="수납 건수",title_font=dict(size=10,color=C["t3"]),
                range=[0, _kc_max*1.22])
            st.plotly_chart(_figKC, use_container_width=True, key="kiosk_counter_trend")
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#94A3B8;font-size:12px;">V_KIOSK_COUNTER_TREND 생성 후 조회 가능</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 탭 2 — 수납·미수금  (기존 _tab_revenue 그대로)
# ════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════
# AI 채팅 분석 (정의만 존재 — render_finance_dashboard 에서 미호출)
# ════════════════════════════════════════════════════════════════════
def _render_finance_llm_chat(bed_detail=None, dept_status=None, kiosk_by_dept=None,
                              daily_dept_stat=None, kiosk_counter_trend=None,
                              discharge_pipe=None, kiosk_status=None):
    import json as _json, uuid as _uuid
    bed_detail          = bed_detail          or []
    dept_status         = dept_status         or []
    kiosk_by_dept       = kiosk_by_dept       or []
    daily_dept_stat     = daily_dept_stat     or []
    kiosk_counter_trend = kiosk_counter_trend or []
    discharge_pipe      = discharge_pipe      or []

    _stay      = sum(int(r.get("재원수",   0) or 0) for r in bed_detail)
    _adm       = sum(int(r.get("금일입원", 0) or 0) for r in bed_detail)
    _disc      = sum(int(r.get("금일퇴원", 0) or 0) for r in bed_detail)
    _total_bed = sum(int(r.get("총병상",   0) or 0) for r in bed_detail)
    _rest      = max(0, _total_bed - _stay)
    _occ       = round(_stay/max(_total_bed,1)*100, 1)
    _ndc       = sum(int(r.get("익일퇴원예약", 0) or 0) for r in bed_detail)
    _wait      = sum(int(r.get("대기",   0) or 0) for r in dept_status)
    _proc      = sum(int(r.get("진료중", 0) or 0) for r in dept_status)
    _done      = sum(int(r.get("완료",   0) or 0) for r in dept_status)
    _k_tot     = sum(int(r.get("수납건수", 0) or 0) for r in kiosk_by_dept)
    _k_amt     = sum(int(r.get("수납금액", 0) or 0) for r in kiosk_by_dept)

    from collections import defaultdict as _ddd_c
    _ds_cat: dict = _ddd_c(lambda: _ddd_c(int))
    for _r in daily_dept_stat:
        _ds_cat[_r.get("구분","")][_r.get("보험구분","기타")] += int(_r.get("건수",0) or 0)
    _pipe: dict = {}
    for _r in discharge_pipe:
        _s = _r.get("단계",""); _n = int(_r.get("환자수",0) or 0)
        if _s: _pipe[_s] = _pipe.get(_s,0) + _n
    _kc_summary = [{"날짜":str(r.get("기준일",""))[:10],"키오스크":r.get("키오스크건수"),"창구":r.get("창구건수")}
                   for r in kiosk_counter_trend[-7:]]
    _ctx = {
        "기준시각": time.strftime("%Y-%m-%d %H:%M"),
        "병동_현황": {"금일입원":_adm,"금일퇴원":_disc,"재원수":_stay,"총병상":_total_bed,
                      "잔여병상":_rest,"가동률":f"{_occ}%","익일퇴원예정":_ndc,
                      "병동별":[{"병동":r.get("병동명"),"재원":r.get("재원수"),"가동률":r.get("가동률")} for r in bed_detail[:12]]},
        "외래_현황": {"대기":_wait,"진료중":_proc,"완료":_done,"합계":_wait+_proc+_done,
                      "진료과별":[{"진료과":r.get("진료과명"),"대기":r.get("대기"),"완료":r.get("완료"),"평균대기(분)":r.get("평균대기시간")}
                                  for r in sorted(dept_status,key=lambda x:-int(x.get("대기",0) or 0))[:12]]},
        "일일현황_보험구분": {cat: dict(v) for cat,v in _ds_cat.items()},
        "키오스크_수납": {"총건수":_k_tot,"총금액(만원)":_k_amt//10000,
                          "진료과별":[{"진료과":r.get("진료과명"),"건수":r.get("수납건수"),"금액(만원)":int(r.get("수납금액",0) or 0)//10000} for r in kiosk_by_dept[:10]],
                          "7일_추세":_kc_summary},
        "퇴원_파이프라인": _pipe,
    }
    _sys_prompt = (
        "당신은 병원 원무팀 업무 지원 AI입니다.\n"
        "반드시 아래 [현재 대시보드 데이터]만 근거로 답변하세요. 데이터에 없는 내용은 추측하지 마세요.\n"
        "핵심 수치는 **굵게**, 위험/주의는 🔴, 정상은 🟢, 권장 조치는 ✅ 로 표시하세요.\n"
        "개인 환자 정보(환자명, 주민번호, 카드번호 등)는 절대 언급하지 마세요.\n\n"
        f"## [현재 대시보드 데이터] — {time.strftime('%Y-%m-%d %H:%M')} 기준\n"
        f"```json\n{_json.dumps(_ctx, ensure_ascii=False, indent=2)[:6000]}\n```"
    )
    if "fn_chat_history" not in st.session_state:
        st.session_state["fn_chat_history"] = []
    _history = st.session_state["fn_chat_history"]
    st.markdown(
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:14px 16px;margin-top:4px;">',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="font-size:16px;">🤖</span>'
        '<span style="font-size:13px;font-weight:700;color:#0F172A;">AI 원무 분석 채팅</span></div>',
        unsafe_allow_html=True,
    )
    _quick = [
        ("외래 혼잡도", "현재 외래 진료과별 대기 현황을 분석하고 혼잡한 진료과 조치 방안을 알려주세요."),
        ("키오스크 현황", f"오늘 키오스크 수납 {_k_tot}건 현황을 분석하고 창구 부담 현황을 알려주세요."),
        ("입퇴원 분석",  f"금일 입원 {_adm}명·퇴원 {_disc}명·재원 {_stay}명 현황을 분석해주세요."),
        ("운영 요약",    "오늘 원무 전체 운영 현황을 3줄로 요약해주세요."),
    ]
    _qcols = st.columns(len(_quick), gap="small")
    for _qi, (_ql, _qv) in enumerate(_quick):
        with _qcols[_qi]:
            if st.button(_ql, key=f"fn_qs_{_qi}", use_container_width=True, type="secondary"):
                st.session_state["fn_chat_prefill"] = _qv; st.rerun()
    for _msg in _history:
        with st.chat_message(_msg["role"]): st.markdown(_msg["content"])
    _prefill  = st.session_state.pop("fn_chat_prefill", None)
    _user_in  = st.chat_input("원무 현황에 대해 질문하세요", key="fn_chat_input") or _prefill
    if _user_in:
        with st.chat_message("user"): st.markdown(_user_in)
        _history.append({"role":"user","content":_user_in})
        with st.chat_message("assistant"):
            _ph = st.empty(); _toks: list = []; _full = ""
            try:
                from core.llm import get_llm_client
                _llm = get_llm_client()
                _safe_p = _sys_prompt[:4000]+"...(생략)" if len(_sys_prompt)>4000 else _sys_prompt
                for _tok in _llm.generate_stream(_user_in, _safe_p, request_id=_uuid.uuid4().hex[:8]):
                    _toks.append(_tok)
                    if len(_toks)%4==0: _ph.markdown("".join(_toks)+"▌")
                _full = "".join(_toks)
            except Exception as _e:
                _full = (f"**LLM 연결 실패**\n\n`{_e}`\n\n"
                         f"현재 데이터: 재원 **{_stay}명** / 외래대기 **{_wait}명** / 키오스크수납 **{_k_tot}건**")
            _ph.markdown(_full)
        _history.append({"role":"assistant","content":_full})
        st.session_state["fn_chat_history"] = _history; st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 세부과 일일집계표  (기존 그대로)
# ════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════
# 세부과 일일집계표
# ════════════════════════════════════════════════════════════════════
def _render_day_inweon(day_inweon: list) -> None:
    _TH = ("padding:6px 8px;font-size:11px;font-weight:700;"
           "color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;")
    _group_html = (
        f'<th style="{_TH}text-align:left;" rowspan="2">진료과</th>'
        f'<th style="{_TH}text-align:right;color:{C["blue"]};" rowspan="2">외래계</th>'
        f'<th style="{_TH}text-align:right;color:{C["indigo"]};" rowspan="2">입원계</th>'
        f'<th style="{_TH}text-align:right;color:{C["t2"]};" rowspan="2">퇴원계</th>'
        f'<th style="{_TH}text-align:right;color:{C["violet"]};" rowspan="2">재원계</th>'
        f'<th colspan="5" style="{_TH}text-align:center;color:{C["teal"]};">예방접종</th>'
    )
    _sub_html = (
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">독감</th>'
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">AZ·JS·NV</th>'
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">MD</th>'
        f'<th style="{_TH}text-align:right;color:{C["teal"]};">FZ</th>'
        f'<th style="{_TH}text-align:right;color:{C["green"]};font-weight:800;">소계</th>'
    )
    _rows_html = ""
    for _i, _r in enumerate(day_inweon):
        _dept     = str(_r.get("진료과",""))
        _dept_t   = _dept.strip()
        _is_total = (_dept_t == "총합계")
        _is_group = _dept_t.startswith("*")
        _dept_disp= _dept_t.lstrip("*").strip() if _is_group else _dept_t
        if _is_total:
            _bg  = "#EFF6FF"
            _td  = f"padding:6px 8px;background:{_bg};border-top:2px solid #BFDBFE;font-weight:800;font-size:12.5px;font-family:Consolas,monospace;text-align:right;"
            _dept_td = _td.replace("text-align:right;","text-align:left;") + f"color:#1E40AF;font-family:inherit;"
        elif _is_group:
            _bg  = "#F0F4FF"
            _td  = f"padding:5px 8px;background:{_bg};border-bottom:1px solid #E2E8F0;font-size:12px;font-family:Consolas,monospace;text-align:right;font-weight:700;"
            _dept_td = _td.replace("text-align:right;","text-align:left;") + f"color:{C['blue']};font-family:inherit;padding-left:8px;"
        else:
            _bg  = "#F8FAFC" if _i%2==0 else "#FFFFFF"
            _td  = f"padding:5px 8px;background:{_bg};border-bottom:1px solid #F1F5F9;font-size:12px;font-family:Consolas,monospace;text-align:right;"
            _dept_td = _td.replace("text-align:right;","text-align:left;") + "color:#334155;font-family:inherit;padding-left:18px;"
        def _fmt(key):
            v = _r.get(key)
            if v is None: return "─"
            try:
                n = int(str(v).replace(",",""))
                return "─" if n==0 else f"{n:,}"
            except: return str(v) if str(v).strip() else "─"
        _rows_html += (
            f"<tr><td style='{_dept_td}'>{_dept_disp}</td>"
            f'<td style="{_td}color:{C["blue"]};">{_fmt("외래계")}</td>'
            f'<td style="{_td}color:{C["indigo"]};">{_fmt("입원계")}</td>'
            f'<td style="{_td}color:{C["t2"]};">{_fmt("퇴원계")}</td>'
            f'<td style="{_td}color:{C["violet"]};">{_fmt("재원계")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(독감)")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(AZ,JS,NV)")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(MD)")}</td>'
            f'<td style="{_td}color:{C["teal"]};">{_fmt("예방(FZ)")}</td>'
            f'<td style="{_td}color:{C["green"]};font-weight:{"800" if _is_total or _is_group else "600"};">'
            f'{_fmt("예방주사계")}</td></tr>'
        )
    _today = time.strftime("%Y.%m.%d")
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">'
        f'<div class="wd-sec"><span class="wd-sec-bar" style="background:{C["blue"]};"></span>'
        f'세부과 일일집계표<span class="wd-sec-sub"> {_today} 기준</span></div>',
        unsafe_allow_html=True,
    )
    if day_inweon:
        st.markdown(
            f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>{_group_html}</tr><tr>{_sub_html}</tr></thead>'
            f'<tbody>{_rows_html}</tbody></table></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #F1F5F9;">'
            f'<span style="font-size:10px;color:#64748B;">📌 * 표시: 하위 진료과 합산 그룹</span>'
            f'<span style="font-size:10px;color:{C["blue"]};">■ 외래</span>'
            f'<span style="font-size:10px;color:{C["indigo"]};">■ 입원</span>'
            f'<span style="font-size:10px;color:{C["violet"]};">■ 재원</span>'
            f'<span style="font-size:10px;color:{C["teal"]};">■ 예방접종</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div style="padding:28px;text-align:center;color:#94A3B8;font-size:13px;">V_DAY_INWEON_3 데이터 없음</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    return

    # ── 격자 Z 행렬 구성
    _max_col = max(c for c, r in grid_dict.values())
    _max_row = max(r for c, r in grid_dict.values())

    # float('nan') = 빈 셀 (투명)
    _z    = [[float("nan")] * (_max_col + 1) for _ in range(_max_row + 1)]
    _text = [[""] * (_max_col + 1) for _ in range(_max_row + 1)]

    for _nm, (_col, _row) in grid_dict.items():
        _c = _cnt.get(_nm, 0)
        _z[_row][_col]    = float(_c)
        _text[_row][_col] = f"{_nm}<br>{_c:,}명"

    # NaN 셀 → 0으로 처리하되 텍스트는 비워두기
    # (colorscale 에서 0 = 가장 연한 색 → 빈 셀처럼 보임)
    # 실제로 NaN은 투명하게 처리됨

    _max_v = max(_cnt.values()) if _cnt else 1

    _fig = go.Figure(go.Heatmap(
        z=_z,
        text=_text,
        texttemplate="%{text}",
        textfont=dict(size=9, color="#1E293B"),
        colorscale=colorscale,
        zmin=0,
        zmax=_max_v,
        showscale=True,
        hovertemplate="%{text}<extra></extra>",
        xgap=4,
        ygap=4,
        colorbar=dict(
            title=dict(text="환자수", font=dict(size=11)),
            thickness=13,
            len=0.75,
            tickformat=",",
            tickfont=dict(size=10),
        ),
    ))

    _fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=350,
        margin=dict(l=0, r=0, t=4, b=0),
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False, autorange="reversed"),
    )

    st.plotly_chart(_fig, use_container_width=True, key=chart_key)

    # ── 구군 순위 보조 바 (TOP 12)
    _sorted_cnt = sorted(_cnt.items(), key=lambda x: -x[1])
    _max_bar    = _sorted_cnt[0][1] if _sorted_cnt else 1
    _medals     = ["🥇", "🥈", "🥉"]
    _bar_html   = (
        '<div style="display:flex;flex-wrap:wrap;gap:5px 16px;'
        'margin-top:8px;padding-top:8px;border-top:1px solid #F1F5F9;">'
    )
    for _i, (_gn, _gc) in enumerate(_sorted_cnt[:12]):
        _pct_b = round(_gc / max(_max_bar, 1) * 100)
        _md = _medals[_i] if _i < 3 else (
            f'<span style="font-size:10px;color:#94A3B8;font-weight:700;">{_i+1}</span>'
        )
        _bar_html += (
            f'<div style="display:flex;align-items:center;gap:5px;'
            f'min-width:186px;flex:1 0 186px;">'
            f'<div style="width:22px;text-align:center;">{_md}</div>'
            f'<div style="width:52px;font-size:11px;font-weight:600;color:#334155;'
            f'white-space:nowrap;">{_gn}</div>'
            f'<div style="flex:1;height:8px;background:#F1F5F9;border-radius:4px;overflow:hidden;">'
            f'<div style="width:{_pct_b}%;height:100%;background:{color_main};'
            f'border-radius:4px;opacity:0.78;"></div></div>'
            f'<div style="width:44px;font-size:11px;font-family:Consolas;'
            f'font-weight:700;color:{color_main};text-align:right;">{_gc:,}</div>'
            f'</div>'
        )
    _bar_html += "</div>"
    st.markdown(_bar_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

