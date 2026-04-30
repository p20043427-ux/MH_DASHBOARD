"""ui/finance/tab_monthly.py — 월간추이분석 탭 (2개월 비교 + 지역 비교)"""

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
# 탭 4 — 월간추이분석
# ════════════════════════════════════════════════════════════════════
def _tab_monthly(monthly_opd_dept: List[Dict], region_monthly: List[Dict] = None) -> None:
    monthly_opd_dept = monthly_opd_dept or []

    _gap()
    # 분리 배너
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["green"]}15,{C["teal"]}10);'
        f'border-left:4px solid {C["green"]};border-radius:0 8px 8px 0;'
        f'padding:10px 16px;margin-bottom:4px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:18px;">📅</span>'
        f'<div><div style="font-size:13px;font-weight:700;color:{C["green"]};">월간 추이 분석</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'2개월 선택 → 진료과별 방문자수 / 신환 / 신환비율 / 구환 / 신환증감 비교'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # VIEW 없음 안내 (return 제거 — 지역 비교 섹션은 별도 데이터라 계속 렌더링)
    if not monthly_opd_dept:
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;'
            f'padding:20px;text-align:center;margin-top:12px;">'
            f'<div style="font-size:32px;margin-bottom:8px;">📋</div>'
            f'<div style="font-size:14px;font-weight:700;color:#92400E;">V_MONTHLY_OPD_DEPT 데이터 없음</div>'
            f'<div style="font-size:12px;color:#B45309;margin-top:6px;">'
            f'monthly_views_new.sql 을 DBeaver(DBA 계정)에서 실행 후 앱을 재시작하세요.<br>'
            f'컬럼: 기준년월(YYYYMM) / 진료과명 / 방문자수 / 신환자수 / 구환자수 / 외래전체 / 기타건수'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        # 지역 비교 섹션은 별도 뷰(V_REGION_DEPT_MONTHLY)를 쓰므로 아래로 계속 진행

    # 가용 월 목록 (내림차순) — OPD 데이터 있을 때만
    _avail = sorted(
        {str(r.get("기준년월",""))[:6] for r in monthly_opd_dept if str(r.get("기준년월",""))[:6].isdigit()},
        reverse=True,
    ) if monthly_opd_dept else []
    if monthly_opd_dept and len(_avail) < 2:
        st.warning("비교를 위해 2개월 이상의 데이터가 필요합니다.")

    if len(_avail) >= 2:
        def _fmt_ym(ym: str) -> str:
            return f"{ym[:4]}년 {ym[4:6]}월" if len(ym) >= 6 else ym
    
        # 월 선택 컨트롤
        _ctrl1, _ctrl2, _ctrl_spacer = st.columns([2, 2, 6], gap="small")
        with _ctrl1:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 기준월</div>', unsafe_allow_html=True)
            _m1 = st.selectbox("기준월", options=_avail, index=min(1, len(_avail)-1),
                               key="mon_m1", label_visibility="collapsed",
                               format_func=_fmt_ym,
                               help="분석 기준이 되는 월")
        with _ctrl2:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 비교월</div>', unsafe_allow_html=True)
            _m2 = st.selectbox("비교월", options=_avail, index=0,
                               key="mon_m2", label_visibility="collapsed",
                               format_func=_fmt_ym,
                               help="기준월과 비교할 월 (전월 또는 동기 선택)")
    
        _m1_label = _fmt_ym(_m1)
        _m2_label = _fmt_ym(_m2)
    
        # 데이터 분리
        _d1 = {r.get("진료과명",""): r for r in monthly_opd_dept if str(r.get("기준년월",""))[:6] == _m1}
        _d2 = {r.get("진료과명",""): r for r in monthly_opd_dept if str(r.get("기준년월",""))[:6] == _m2}
    
        # 진료과 목록 (합집합, 총 방문자수 내림차순)
        _all_depts_raw = sorted(set(list(_d1.keys()) + list(_d2.keys())))
        _dept_visit    = {d: int(_d2.get(d, _d1.get(d,{})).get("방문자수",0) or 0) for d in _all_depts_raw}
        _all_depts     = [d for d in sorted(_all_depts_raw, key=lambda d:-_dept_visit[d]) if d]
    
        def _vi(r, key): return int(r.get(key, 0) or 0)
        def _pct(n, d):  return f"{round(n/d*100,1):.1f}%" if d > 0 else "─"
    
        # ── 비교 테이블 ───────────────────────────────────────────────
        st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["green"] + ';margin-top:8px;">', unsafe_allow_html=True)
        _sec_hd("📊 2개월 진료과별 외래 인원 비교", f"{_m1_label} vs {_m2_label}", C["green"])
    
        _TH = "padding:5px 8px;font-size:10.5px;font-weight:700;color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
    
        # 그룹 헤더 (1행)
        _h1 = (
            f'<th style="{_TH}text-align:left;" rowspan="2">구분</th>'
            f'<th colspan="5" style="{_TH}text-align:center;color:{C["blue"]};border-left:3px solid {C["blue"]}33;">'
            f'{_m1_label} (기준)</th>'
            f'<th colspan="5" style="{_TH}text-align:center;color:{C["indigo"]};border-left:3px solid {C["indigo"]}33;">'
            f'{_m2_label} (비교)</th>'
            f'<th style="{_TH}text-align:center;color:{C["red"]};" rowspan="2">'
            f'비고<br><span style="font-size:9px;font-weight:400;">전월대비 신환증감</span></th>'
        )
        # 서브 헤더 (2행)
        _sub_cols = [
            ("방문자수",   C["t2"],    False),
            ("신환(첫방문)",C["green"], True),
            ("신환%",      C["green"], False),
            ("외래전체",   C["blue"],  False),
            ("구환자수",   C["t3"],    False),
        ]
        _h2 = ""
        for _grp_color in [C["blue"], C["indigo"]]:
            for _idx, (_col_label, _col_c, _bold) in enumerate(_sub_cols):
                _bl = f"border-left:3px solid {_grp_color}33;" if _idx == 0 else ""
                _fw = "font-weight:800;" if _bold else ""
                _h2 += f'<th style="{_TH}text-align:right;color:{_col_c};{_bl}{_fw}">{_col_label}</th>'
    
        # 행 생성
        _rows = ""
        for _i, _dept in enumerate(_all_depts):
            _r1 = _d1.get(_dept, {}); _r2 = _d2.get(_dept, {})
            _v1  = _vi(_r1,"방문자수"); _s1 = _vi(_r1,"신환자수")
            _e1  = _vi(_r1,"외래전체"); _g1 = _vi(_r1,"구환자수")
            _v2  = _vi(_r2,"방문자수"); _s2 = _vi(_r2,"신환자수")
            _e2  = _vi(_r2,"외래전체"); _g2 = _vi(_r2,"구환자수")
    
            _diff     = _s2 - _s1
            _diff_pct = f"({round(_diff/_s1*100,1):+.1f}%)" if _s1 > 0 and _diff != 0 else ""
            _diff_str = (f"{'▲' if _diff>0 else '▼'} {abs(_diff):,}명 {_diff_pct}") if _diff != 0 else "─"
            _diff_c   = C["red"] if _diff > 0 else C["blue"] if _diff < 0 else C["t3"]
    
            _bg  = "#F8FAFC" if _i%2==0 else "#FFFFFF"
            _td  = f"padding:5px 8px;background:{_bg};border-bottom:1px solid #F1F5F9;font-size:12px;font-family:Consolas,monospace;text-align:right;"
            _tdl = _td.replace("text-align:right;","text-align:left;") + "font-family:inherit;font-weight:600;"
    
            _rows += (
                f"<tr>"
                f'<td style="{_tdl}">{_dept}</td>'
                # 기준월
                f'<td style="{_td}border-left:3px solid {C["blue"]}33;">{_v1:,}</td>'
                f'<td style="{_td}color:{C["green"]};font-weight:700;">{_s1:,}</td>'
                f'<td style="{_td}color:{C["green"]};">{_pct(_s1,_e1)}</td>'
                f'<td style="{_td}">{_e1:,}</td>'
                f'<td style="{_td}">{_g1:,}</td>'
                # 비교월
                f'<td style="{_td}border-left:3px solid {C["indigo"]}33;">{_v2:,}</td>'
                f'<td style="{_td}color:{C["indigo"]};font-weight:700;">{_s2:,}</td>'
                f'<td style="{_td}color:{C["indigo"]};">{_pct(_s2,_e2)}</td>'
                f'<td style="{_td}">{_e2:,}</td>'
                f'<td style="{_td}">{_g2:,}</td>'
                # 비고
                f'<td style="{_td}text-align:center;font-weight:700;color:{_diff_c};">{_diff_str}</td>'
                f"</tr>"
            )
    
        # 합계 행
        def _sum_all(d_dict):
            return {k: sum(int(r.get(k,0) or 0) for r in d_dict.values())
                    for k in ("방문자수","신환자수","구환자수","외래전체")}
        _t1   = _sum_all(_d1); _t2 = _sum_all(_d2)
        _tdif = _t2["신환자수"] - _t1["신환자수"]
        _tdif_pct = f"({round(_tdif/_t1['신환자수']*100,1):+.1f}%)" if _t1["신환자수"]>0 and _tdif!=0 else ""
        _tdif_str = (f"{'▲' if _tdif>0 else '▼'} {abs(_tdif):,}명 {_tdif_pct}") if _tdif!=0 else "─"
        _tdif_c   = C["red"] if _tdif>0 else C["blue"] if _tdif<0 else C["t3"]
        _tdc  = "padding:6px 8px;background:#F0FDF4;border-top:2px solid #86EFAC;font-size:12.5px;font-family:Consolas,monospace;text-align:right;font-weight:800;"
        _tdcl = _tdc.replace("text-align:right;","text-align:left;") + "color:#15803D;font-family:inherit;"
    
        _rows += (
            f"<tr>"
            f'<td style="{_tdcl}">합계</td>'
            f'<td style="{_tdc}border-left:3px solid {C["blue"]}33;">{_t1["방문자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["green"]};">{_t1["신환자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["green"]};">{_pct(_t1["신환자수"],_t1["외래전체"])}</td>'
            f'<td style="{_tdc}">{_t1["외래전체"]:,}</td>'
            f'<td style="{_tdc}">{_t1["구환자수"]:,}</td>'
            f'<td style="{_tdc}border-left:3px solid {C["indigo"]}33;">{_t2["방문자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["indigo"]};">{_t2["신환자수"]:,}</td>'
            f'<td style="{_tdc}color:{C["indigo"]};">{_pct(_t2["신환자수"],_t2["외래전체"])}</td>'
            f'<td style="{_tdc}">{_t2["외래전체"]:,}</td>'
            f'<td style="{_tdc}">{_t2["구환자수"]:,}</td>'
            f'<td style="{_tdc}color:{_tdif_c};text-align:center;">{_tdif_str}</td>'
            f"</tr>"
        )
    
        st.markdown(
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>{_h1}</tr><tr>{_h2}</tr></thead>'
            f'<tbody>{_rows}</tbody></table></div>',
            unsafe_allow_html=True,
        )
    
        # 범례
        st.markdown(
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #F1F5F9;font-size:10.5px;">'
            f'<span style="color:{C["green"]};font-weight:700;">🟢 신환(첫방문): 해당 월 처음 내원 환자</span>'
            f'<span style="color:{C["t3"]};">🔵 구환: 이전 방문 이력 있는 환자</span>'
            f'<span style="color:{C["red"]};">▲ 증가 / <span style="color:{C["blue"]};">▼ 감소</span></span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        _gap()
    
        # ── 신환 비교 차트
        if HAS_PLOTLY and (_d1 or _d2) and _all_depts:
            st.markdown('<div class="wd-card" style="border-top:3px solid ' + C["teal"] + ';">', unsafe_allow_html=True)
            _sec_hd("📊 진료과별 신환자수 월별 비교", f"{_m1_label} vs {_m2_label}", C["teal"])
            _s1_vals = [_vi(_d1.get(d,{}), "신환자수") for d in _all_depts]
            _s2_vals = [_vi(_d2.get(d,{}), "신환자수") for d in _all_depts]
            _fig_m   = go.Figure()
            _fig_m.add_trace(go.Bar(
                name=f"{_m1_label}(기준) 신환",
                x=_all_depts, y=_s1_vals,
                marker_color=C["blue_l"], marker=dict(line=dict(color=C["blue"],width=0.5)),
                hovertemplate=f"<b>%{{x}}</b><br>{_m1_label}: %{{y:,}}명<extra></extra>",
            ))
            _fig_m.add_trace(go.Bar(
                name=f"{_m2_label}(비교) 신환",
                x=_all_depts, y=_s2_vals,
                marker_color=C["indigo_l"], marker=dict(line=dict(color=C["indigo"],width=0.5)),
                hovertemplate=f"<b>%{{x}}</b><br>{_m2_label}: %{{y:,}}명<extra></extra>",
            ))
            # 증감 스캐터 오버레이
            _diff_vals = [_s2_vals[i] - _s1_vals[i] for i in range(len(_all_depts))]
            _diff_text = [f"{'▲' if v>0 else '▼' if v<0 else ''}{abs(v)}" if v!=0 else "" for v in _diff_vals]
            _diff_c2   = [C["red"] if v>0 else C["blue"] if v<0 else "rgba(0,0,0,0)" for v in _diff_vals]
            _fig_m.add_trace(go.Scatter(
                x=_all_depts, y=[max(a,b)+1 for a,b in zip(_s1_vals,_s2_vals)],
                mode="text", text=_diff_text,
                textfont=dict(size=10, color=_diff_c2),
                showlegend=False, hoverinfo="skip",
            ))
            _fig_m.update_layout(**_PLOTLY_LAYOUT, barmode="group", height=320,
                margin=dict(l=0,r=0,t=30,b=60),
                legend=dict(orientation="h",y=1.10,x=0.5,xanchor="center",font=dict(size=12),bgcolor="rgba(0,0,0,0)"),
                bargap=0.2, bargroupgap=0.05)
            _fig_m.update_xaxes(tickangle=-35, tickfont=dict(size=10))
            _fig_m.update_yaxes(title_text="신환자수(명)", title_font=dict(size=10,color=C["t3"]))
            st.plotly_chart(_fig_m, use_container_width=True, key="mon_shin_bar")
            st.markdown("</div>", unsafe_allow_html=True)
    
    # ════════════════════════════════════════════════════════════════
    # [섹션 지역] 월별 지역 비교 분석 (A vs B)
    # ════════════════════════════════════════════════════════════════
    _gap(8)
    import datetime as _dt_mn
    from collections import defaultdict as _ddmn
    _today_mn = _dt_mn.date.today()

    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 월별 지역 비교 분석 (A vs B)",
            "두 달 선택 → 지역별 환자 증감 분석 (V_REGION_DEPT_MONTHLY)", C["indigo"])

    # Oracle CHAR 공백 정규화
    _mn_src = [
        {k: (str(v).strip() if v is not None else "") for k, v in r.items()}
        for r in (region_monthly or [])
    ]
    if len(_mn_src) >= 49000:
        st.warning(f"⚠️ 지역 데이터 행 수({len(_mn_src):,})가 한계에 근접합니다.")

    _mn_today_ym = _today_mn.strftime("%Y%m")
    _mn_months = sorted(
        {r.get("기준월", "") for r in _mn_src
         if r.get("기준월", "").isdigit()
         and len(r.get("기준월", "")) == 6
         and r.get("기준월", "") <= _mn_today_ym},
    )

    if not _mn_src:
        st.warning("⚠️ **V_REGION_DEPT_MONTHLY 데이터 없음** — DBA에게 뷰 생성 요청")
    elif len(_mn_months) < 2:
        st.warning("⚠️ 비교 가능한 월 부족 (최소 2개월 필요)")
    else:
        def _mn_ym(ym: str) -> str:
            return f"{ym[:4]}년 {ym[4:6]}월" if len(ym) == 6 else ym

        _mn_n = len(_mn_months)
        _col_a, _col_b, _col_d, _ = st.columns([3, 3, 3, 3], gap="small")
        with _col_a:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 기준 월 (이전)</div>', unsafe_allow_html=True)
            _mn_a = st.selectbox("A월", options=_mn_months, index=max(0, _mn_n - 2),
                                 format_func=_mn_ym, key="mn_month_a", label_visibility="collapsed")
        with _col_b:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">📅 비교 월 (이후)</div>', unsafe_allow_html=True)
            _mn_b = st.selectbox("B월", options=_mn_months, index=_mn_n - 1,
                                 format_func=_mn_ym, key="mn_month_b", label_visibility="collapsed")
        with _col_d:
            st.markdown(f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">🏥 진료과</div>', unsafe_allow_html=True)
            _mn_dept_opts = ["전체"] + sorted({r.get("진료과명", "") for r in _mn_src if r.get("진료과명", "")})
            _mn_dept = st.selectbox("진료과", options=_mn_dept_opts, index=0,
                                    key="mn_dept", label_visibility="collapsed")

        # ── 데이터 검증 expander ──────────────────────────────────
        with st.expander("🔍 로드 데이터 검증 (DB 쿼리 결과와 비교용)", expanded=False):
            st.caption(f"총 로드 행: {len(_mn_src):,}행 · 조회 가능 월: {', '.join(_mn_months)}")
            _dbg2_dept = st.selectbox("검증 진료과", ["전체"] + sorted({r.get("진료과명","") for r in _mn_src if r.get("진료과명","")}), key="mn_dbg_dept")
            _dbg2: dict = _ddmn(lambda: _ddmn(int))
            for _r in _mn_src:
                if _dbg2_dept != "전체" and _r.get("진료과명","") != _dbg2_dept:
                    continue
                _dbg2[_r.get("기준월","")][_r.get("지역","")] += int(_r.get("환자수",0) or 0)
            _dbg2_ms = sorted(_dbg2.keys())
            if len(_dbg2_ms) >= 2:
                _dd_a, _dd_b = _dbg2_ms[-2], _dbg2_ms[-1]
                _dd_rgs = sorted(set(list(_dbg2[_dd_a].keys()) + list(_dbg2[_dd_b].keys())))
                _dh = (f'<table style="font-size:11px;border-collapse:collapse;width:100%">'
                       f'<tr><th style="border:1px solid #ddd;padding:4px;background:#F8FAFC">지역</th>'
                       f'<th style="border:1px solid #ddd;padding:4px;background:#EEF2FF">{_dd_a[:4]}년{_dd_a[4:]}월(A)</th>'
                       f'<th style="border:1px solid #ddd;padding:4px;background:#EFF6FF">{_dd_b[:4]}년{_dd_b[4:]}월(B)</th>'
                       f'<th style="border:1px solid #ddd;padding:4px;background:#FFF7ED">증감</th></tr>')
                for _rg in _dd_rgs[:50]:
                    _va2 = _dbg2[_dd_a].get(_rg, 0); _vb2 = _dbg2[_dd_b].get(_rg, 0)
                    _vd2 = _vb2 - _va2
                    _c2  = "#DC2626" if _vd2 > 0 else "#1E40AF" if _vd2 < 0 else "#64748B"
                    _dh += (f'<tr><td style="border:1px solid #ddd;padding:3px 6px">{_rg}</td>'
                            f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right">{_va2:,}</td>'
                            f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right">{_vb2:,}</td>'
                            f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right;color:{_c2};font-weight:700">{_vd2:+,}</td></tr>')
                _dh += (f'<tr><td style="border:1px solid #ddd;padding:3px 6px;font-weight:700">합계</td>'
                        f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right;font-weight:700">{sum(_dbg2[_dd_a].values()):,}</td>'
                        f'<td style="border:1px solid #ddd;padding:3px 6px;text-align:right;font-weight:700">{sum(_dbg2[_dd_b].values()):,}</td>'
                        f'<td></td></tr></table>')
                st.markdown(_dh, unsafe_allow_html=True)

        if _mn_a == _mn_b:
            st.warning("A와 B에 서로 다른 월을 선택해 주세요.")
        else:
            # ── 집계 ─────────────────────────────────────────────
            def _mn_agg(month: str, dept: str) -> dict:
                agg: dict = _ddmn(int)
                for _r in _mn_src:
                    if _r.get("기준월", "") != month:
                        continue
                    if dept != "전체" and _r.get("진료과명", "") != dept:
                        continue
                    _rg = _r.get("지역", "")
                    if _rg in ("지역미상", "", None):
                        continue
                    agg[_rg] += int(_r.get("환자수", 0) or 0)
                return dict(agg)

            _agg_a = _mn_agg(_mn_a, _mn_dept)
            _agg_b = _mn_agg(_mn_b, _mn_dept)
            _all_rgs = sorted(set(list(_agg_a.keys()) + list(_agg_b.keys())))

            _mn_rows = []
            for _rg in _all_rgs:
                _ca = _agg_a.get(_rg, 0); _cb = _agg_b.get(_rg, 0)
                _diff = _cb - _ca
                _pct6 = round(_diff / max(_ca, 1) * 100, 1)
                _mn_rows.append({"지역": _rg, "A": _ca, "B": _cb, "증감": _diff, "증감률": _pct6})
            _mn_rows.sort(key=lambda x: -x["증감"])

            _tot_a  = sum(_agg_a.values()); _tot_b = sum(_agg_b.values())
            _tot_d  = _tot_b - _tot_a
            _tot_pt = round(_tot_d / max(_tot_a, 1) * 100, 1)
            _inc_n  = sum(1 for r in _mn_rows if r["증감"] > 0)
            _dec_n  = sum(1 for r in _mn_rows if r["증감"] < 0)
            _td_c   = C["red"] if _tot_d > 0 else C["blue"] if _tot_d < 0 else C["t3"]

            # ── KPI 카드 ─────────────────────────────────────────
            _gap(4)
            _k1, _k2, _k3, _k4 = st.columns(4, gap="small")
            _kpi_card(_k1, "📅", _mn_ym(_mn_a), f"{_tot_a:,}", "명", "A 기간 환자수", C["indigo"])
            _kpi_card(_k2, "📅", _mn_ym(_mn_b), f"{_tot_b:,}", "명", "B 기간 환자수", C["blue"])
            _kpi_card(_k3, "📈" if _tot_d >= 0 else "📉", "총 증감",
                      f"{_tot_d:+,}", "명", f"증감률 {_tot_pt:+.1f}%", _td_c)
            _kpi_card(_k4, "🗺️", "증감 지역 현황",
                      f"▲{_inc_n} ▼{_dec_n}", "", f"전체 {len(_mn_rows)}개 지역", C["teal"])
            _gap(8)

            # ── TOP 5 ─────────────────────────────────────────────
            _top5_inc = [r for r in _mn_rows if r["증감"] > 0][:5]
            _top5_dec = sorted([r for r in _mn_rows if r["증감"] < 0], key=lambda x: x["증감"])[:5]

            def _rank_card_mn(col, rows, title, color, is_inc):
                with col:
                    st.markdown(
                        f'<div style="background:#fff;border:1px solid #F0F4F8;'
                        f'border-top:3px solid {color};border-radius:10px;padding:12px 14px;">'
                        f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:8px;">{title}</div>',
                        unsafe_allow_html=True,
                    )
                    if not rows:
                        st.markdown(f'<div style="font-size:12px;color:{C["t3"]};padding:8px 0;">해당 없음</div>', unsafe_allow_html=True)
                    else:
                        _mx = max(abs(r["증감"]) for r in rows) or 1
                        for _ri, _r in enumerate(rows, 1):
                            _bw  = round(abs(_r["증감"]) / _mx * 100)
                            _ico = "▲" if is_inc else "▼"
                            st.markdown(
                                f'<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #F8FAFC;">'
                                f'<span style="font-size:11px;font-weight:700;color:{C["t3"]};min-width:16px;">{_ri}</span>'
                                f'<div style="flex:1;">'
                                f'<div style="font-size:12px;font-weight:600;color:{C["t1"]};">{_r["지역"]}</div>'
                                f'<div style="height:4px;background:#F1F5F9;border-radius:2px;margin-top:3px;overflow:hidden;">'
                                f'<div style="width:{_bw}%;height:100%;background:{color};border-radius:2px;"></div></div></div>'
                                f'<div style="text-align:right;">'
                                f'<div style="font-size:13px;font-weight:800;color:{color};">{_ico}{abs(_r["증감"]):,}명</div>'
                                f'<div style="font-size:10px;color:{C["t3"]};">{_r["증감률"]:+.1f}%</div>'
                                f'</div></div>',
                                unsafe_allow_html=True,
                            )
                    st.markdown("</div>", unsafe_allow_html=True)

            _rc1, _rc2 = st.columns(2, gap="small")
            _rank_card_mn(_rc1, _top5_inc, f"📈 증가 TOP 5 ({_mn_ym(_mn_a)} → {_mn_ym(_mn_b)})", C["red"], True)
            _rank_card_mn(_rc2, _top5_dec, f"📉 감소 TOP 5 ({_mn_ym(_mn_a)} → {_mn_ym(_mn_b)})", C["blue"], False)
            _gap(8)

            # ── 부산/부산외 분리 ──────────────────────────────────
            _busan_rows = [r for r in _mn_rows if r["지역"].startswith("부산")]
            _other_rows = [r for r in _mn_rows if not r["지역"].startswith("부산")]

            def _top_bot5(rows):
                """증감 상위5 + 하위5 반환 (중복 제거, 증감 내림차순)"""
                _top = sorted(rows, key=lambda x: -x["증감"])[:5]
                _bot = sorted(rows, key=lambda x: x["증감"])[:5]
                _seen = set(); _out = []
                for _r in _top + _bot:
                    if _r["지역"] not in _seen:
                        _seen.add(_r["지역"]); _out.append(_r)
                return sorted(_out, key=lambda x: -x["증감"])

            _bs5  = _top_bot5(_busan_rows)
            _ot5  = _top_bot5(_other_rows)

            def _region_table(rows, title, border_color):
                """부산/부산외 분석표 HTML 생성"""
                _TH = "padding:5px 8px;font-size:10px;font-weight:700;color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
                _h = (
                    f'<div style="background:#fff;border:1px solid #F0F4F8;'
                    f'border-top:3px solid {border_color};border-radius:10px;padding:12px 14px;height:100%;">'
                    f'<div style="font-size:12px;font-weight:700;color:{border_color};margin-bottom:8px;">{title}</div>'
                    f'<div style="overflow-x:auto;">'
                    f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
                    f'<thead><tr>'
                    f'<th style="{_TH}text-align:left;">지역</th>'
                    f'<th style="{_TH}text-align:right;color:{C["indigo"]};">A</th>'
                    f'<th style="{_TH}text-align:right;color:{C["blue"]};">B</th>'
                    f'<th style="{_TH}text-align:right;">증감</th>'
                    f'<th style="{_TH}text-align:right;">증감률</th>'
                    f'</tr></thead><tbody>'
                )
                if not rows:
                    _h += f'<tr><td colspan="5" style="padding:12px;text-align:center;color:{C["t3"]};">데이터 없음</td></tr>'
                else:
                    # 상위5 / 구분선 / 하위5 구조
                    _inc = [r for r in rows if r["증감"] > 0]
                    _dec = [r for r in rows if r["증감"] <= 0]
                    for _grp_rows, _grp_bg in [(_inc, "#FFF1F2"), (_dec, "#EFF6FF")]:
                        if _grp_rows:
                            _grp_clr = C["red"] if _grp_bg == "#FFF1F2" else C["blue"]
                            _grp_lbl = "▲ 증가" if _grp_bg == "#FFF1F2" else "▼ 감소"
                            _h += (f'<tr><td colspan="5" style="padding:3px 8px;background:{_grp_bg}20;'
                                   f'font-size:10px;font-weight:700;color:{_grp_clr};'
                                   f'border-bottom:1px solid {_grp_bg};">{_grp_lbl}</td></tr>')
                            for _r in _grp_rows:
                                _d = _r["증감"]; _p = _r["증감률"]
                                _c = C["red"] if _d > 0 else C["blue"] if _d < 0 else C["t3"]
                                _ico = "▲" if _d > 0 else "▼" if _d < 0 else "─"
                                # 지역명에서 "부산광역시 " 접두어 제거해 표시 간결화
                                _rg_short = _r["지역"].replace("부산광역시 ", "").replace("경상남도 ", "경남 ").replace("경상북도 ", "경북 ")
                                _h += (
                                    f'<tr style="border-bottom:1px solid #F1F5F9;">'
                                    f'<td style="padding:4px 8px;font-weight:600;" title="{_r["지역"]}">{_rg_short}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;font-family:Consolas,monospace;">{_r["A"]:,}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;font-family:Consolas,monospace;">{_r["B"]:,}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;font-weight:700;color:{_c};font-family:Consolas,monospace;">{_ico}{abs(_d):,}</td>'
                                    f'<td style="padding:4px 8px;text-align:right;color:{_c};">{_p:+.1f}%</td>'
                                    f'</tr>'
                                )
                _h += "</tbody></table></div></div>"
                return _h

            st.markdown(
                f'<div style="font-size:13px;font-weight:700;color:{C["teal"]};margin-bottom:6px;">'
                f'📋 지역별 환자수 분석표 · {_mn_ym(_mn_a)} vs {_mn_ym(_mn_b)}'
                + (f'  <span style="font-size:11px;font-weight:400;color:{C["t3"]};">(진료과: {_mn_dept})</span>' if _mn_dept != "전체" else "")
                + '</div>',
                unsafe_allow_html=True,
            )
            _tbl_c1, _tbl_c2 = st.columns(2, gap="small")
            with _tbl_c1:
                st.markdown(_region_table(_bs5,  f"🏙️ 부산광역시 내 상위5·하위5", C["teal"]),   unsafe_allow_html=True)
            with _tbl_c2:
                st.markdown(_region_table(_ot5, f"🗺️ 부산 외 지역 상위5·하위5", C["orange"]), unsafe_allow_html=True)
            _gap(8)

            # ── 발산 가로 막대 차트 (부산/부산외 2열) ────────────
            if HAS_PLOTLY and _mn_rows:
                def _divbar_fig(rows, title, key):
                    if not rows:
                        return None
                    _viz = sorted(rows, key=lambda x: x["증감"])
                    _l = [r["지역"].replace("부산광역시 ", "").replace("경상남도 ", "경남 ").replace("경상북도 ", "경북 ")
                          for r in _viz]
                    _d = [r["증감"] for r in _viz]
                    _p = [r["증감률"] for r in _viz]
                    _c = [C["red"] if v > 0 else C["blue"] if v < 0 else C["t3"] for v in _d]
                    _fig = go.Figure(go.Bar(
                        x=_d, y=_l, orientation="h",
                        marker=dict(color=_c, line=dict(color="rgba(0,0,0,0)")),
                        text=[f"{v:+,}({q:+.1f}%)" for v, q in zip(_d, _p)],
                        textposition="outside", textfont=dict(size=9, color=C["t2"]),
                        hovertemplate=[
                            f"<b>{r['지역']}</b><br>A: {r['A']:,}명 → B: {r['B']:,}명<br>"
                            f"증감: {r['증감']:+,}명 ({r['증감률']:+.1f}%)<extra></extra>"
                            for r in _viz
                        ],
                        customdata=[r["지역"] for r in _viz],
                    ))
                    _fig.add_vline(x=0, line=dict(color=C["t3"], width=1.5, dash="dash"))
                    _fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#333333", size=11),
                        height=max(260, len(_l) * 26 + 60),
                        margin=dict(l=0, r=110, t=30, b=8),
                        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
                        showlegend=False, bargap=0.3,
                    )
                    _fig.update_xaxes(title_text="증감 환자수(명)", title_font=dict(size=10, color=C["t3"]),
                                      gridcolor="#F1F5F9", zeroline=False, tickfont=dict(size=10))
                    _fig.update_yaxes(tickfont=dict(size=10), gridcolor="#F1F5F9")
                    return _fig

                _bs_viz = _top_bot5(_busan_rows)
                _ot_viz = _top_bot5(_other_rows)
                _ch1, _ch2 = st.columns(2, gap="small")
                with _ch1:
                    _f1 = _divbar_fig(_bs_viz,  f"🏙️ 부산 증감 · {_mn_ym(_mn_a)}→{_mn_ym(_mn_b)}", "mn_dv_busan")
                    if _f1: st.plotly_chart(_f1, use_container_width=True, key="mn_dv_busan")
                with _ch2:
                    _f2 = _divbar_fig(_ot_viz, f"🗺️ 부산 외 증감 · {_mn_ym(_mn_a)}→{_mn_ym(_mn_b)}", "mn_dv_other")
                    if _f2: st.plotly_chart(_f2, use_container_width=True, key="mn_dv_other")
                _gap(4)

                # ── A vs B 묶음 가로 막대 ───────────────────────
                _gb2    = sorted(_mn_rows, key=lambda x: -abs(x["증감"]))[:12]
                _gb2    = sorted(_gb2, key=lambda x: x["증감"])
                if _gb2:
                    _gb2_l  = [r["지역"] for r in _gb2]
                    _gb2_a  = [r["A"] for r in _gb2]
                    _gb2_b  = [r["B"] for r in _gb2]
                    _b2c    = C["red"] if _tot_d >= 0 else C["blue"]
                    _b2cl   = C["red_l"] if _tot_d >= 0 else C["blue_l"]
                    _fig_gb2 = go.Figure()
                    _fig_gb2.add_trace(go.Bar(
                        name=f"A · {_mn_ym(_mn_a)} (기준)", y=_gb2_l, x=_gb2_a, orientation="h",
                        marker_color=C["indigo_l"], marker=dict(line=dict(color=C["indigo"], width=0.8)),
                        hovertemplate="%{y}<br>A(%{x:,}명)<extra></extra>",
                    ))
                    _fig_gb2.add_trace(go.Bar(
                        name=f"B · {_mn_ym(_mn_b)} (비교)", y=_gb2_l, x=_gb2_b, orientation="h",
                        marker_color=_b2cl, marker=dict(line=dict(color=_b2c, width=0.8)),
                        hovertemplate="%{y}<br>B(%{x:,}명)<extra></extra>",
                    ))
                    _fig_gb2.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#333333", size=11), barmode="group",
                        height=max(340, len(_gb2) * 36 + 90),
                        margin=dict(l=0, r=60, t=38, b=8),
                        title=dict(text=f"지역별 A vs B 비교 · 증감 상위 {len(_gb2)}개 ({_mn_ym(_mn_a)} vs {_mn_ym(_mn_b)})",
                                   font=dict(size=12, color=C["t2"]), x=0),
                        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center",
                                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                        bargap=0.2, bargroupgap=0.05,
                    )
                    _fig_gb2.update_xaxes(title_text="환자수(명)", title_font=dict(size=10, color=C["t3"]),
                                         gridcolor="#F1F5F9", zeroline=False, tickfont=dict(size=10))
                    _fig_gb2.update_yaxes(tickfont=dict(size=10), gridcolor="#F1F5F9")
                    st.plotly_chart(_fig_gb2, use_container_width=True, key="mn_grouped")

            # ── 자동 인사이트 ─────────────────────────────────────
            _gap(4)
            _ti = _top5_inc[0] if _top5_inc else None
            _td_item = _top5_dec[0] if _top5_dec else None
            _arr  = "▲" if _tot_d >= 0 else "▼"
            _ins_mn = [(
                "📊 전체 요약",
                f"{_mn_ym(_mn_a)} <b>{_tot_a:,}명</b> → {_mn_ym(_mn_b)} <b>{_tot_b:,}명</b> "
                f"({_arr} {abs(_tot_d):,}명, {_tot_pt:+.1f}%)<br>증가 {_inc_n}개 / 감소 {_dec_n}개 지역",
                _td_c,
            )]
            if _ti:
                _ins_mn.append(("📈 최대 증가", f"<b>{_ti['지역']}</b> {_ti['A']:,} → {_ti['B']:,}명 (▲{_ti['증감']:,}명, {_ti['증감률']:+.1f}%)", C["red"]))
            if _td_item:
                _ins_mn.append(("📉 최대 감소", f"<b>{_td_item['지역']}</b> {_td_item['A']:,} → {_td_item['B']:,}명 (▼{abs(_td_item['증감']):,}명, {_td_item['증감률']:+.1f}%)", C["blue"]))
            _rapid_mn = [r for r in _mn_rows if abs(r["증감률"]) >= 50 and r["A"] >= 5]
            if _rapid_mn:
                _ins_mn.append(("🚨 급변 지역",
                    "<br>".join(f"{'🔴' if r['증감']>0 else '🔵'} <b>{r['지역']}</b> {r['증감률']:+.1f}% ({r['A']:,} → {r['B']:,}명)" for r in _rapid_mn[:4]),
                    C["violet"]))
            _ins_cols = st.columns(2, gap="small")
            for _ii, (_it, _ib, _ic) in enumerate(_ins_mn):
                with _ins_cols[_ii % 2]:
                    st.markdown(
                        f'<div style="background:#fff;border:1px solid #F0F4F8;border-left:4px solid {_ic};'
                        f'border-radius:8px;padding:10px 14px;margin-bottom:8px;">'
                        f'<div style="font-size:11.5px;font-weight:700;color:{_ic};margin-bottom:5px;">{_it}</div>'
                        f'<div style="font-size:12px;color:{C["t2"]};line-height:1.6;">{_ib}</div></div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("</div>", unsafe_allow_html=True)
    _gap()


# ════════════════════════════════════════════════════════════════════
# AI 채팅 분석  (기존 그대로)
# ════════════════════════════════════════════════════════════════════
