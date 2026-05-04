"""
ui/chart_renderers.py  ─  병동 대시보드 차트 렌더러
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
hospital_dashboard.py 에서 분리한 5개의 대안 차트 렌더러.
"""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from ui.dashboard_data import safe_int as _safe_int, safe_float as _safe_float
from ui.design import (
    C,
    PLOTLY_PALETTE as _PALETTE,
    WARD_AX as _AX,
    ward_layout as _layout,
)


def _render_dept_chart(data: List[Dict], chart_type: str) -> None:
    """
    진료과별 재원 구성 대안 차트 렌더러.
    chart_type: "donut" | "bar_h" | "treemap"
    data: ward_dept_stay 쿼리 결과
    """
    from collections import defaultdict as _ddc2
    if not data or not HAS_PLOTLY:
        st.caption("데이터 없음")
        return

    # 진료과별 합산 집계
    agg: Dict[str, int] = _ddc2(int)
    for r in data:
        agg[r.get("진료과명", "기타")] += _safe_int(r.get("재원수"))
    sorted_items = sorted(agg.items(), key=lambda x: -x[1])
    top8 = list(sorted_items[:8])
    etc  = sum(v for _, v in sorted_items[8:])
    if etc > 0:
        top8.append(("기타", etc))
    labels = [n for n, _ in top8]
    values = [v for _, v in top8]
    total  = max(sum(values), 1)
    colors = _PALETTE[:len(labels)]

    if chart_type == "donut":
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.52,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
            textinfo="percent", textfont=dict(size=10, color="#FFFFFF"),
            direction="clockwise", sort=True,
            hovertemplate="<b>%{label}</b><br>%{value}명 (%{percent})<extra></extra>",
        ))
        fig.update_layout(
            height=200,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=12),
            margin=dict(l=0, r=0, t=8, b=8),
            showlegend=False,
            annotations=[dict(text=f"<b>{total}</b><br>명", x=0.5, y=0.5,
                              showarrow=False, font=dict(size=14, color="#0F172A"))],
        )
        st.plotly_chart(fig, use_container_width=True, key="dept_donut")
        # 범례 테이블
        rows = ""
        for i, (nm, val) in enumerate(zip(labels, values)):
            pct = val / total * 100
            bg  = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
            clr = colors[i % len(colors)]
            rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:3px 6px;"><span style="display:inline-block;'
                f'width:8px;height:8px;border-radius:2px;background:{clr};"></span></td>'
                f'<td style="padding:3px 6px;color:#0F172A;font-size:11.5px;font-weight:500;">{nm}</td>'
                f'<td style="padding:3px 6px;text-align:right;color:#1E40AF;'
                f'font-family:Consolas,monospace;font-weight:700;font-size:11.5px;">{val}</td>'
                f'<td style="padding:3px 6px;text-align:right;color:#64748B;'
                f'font-family:Consolas,monospace;font-size:11px;">{pct:.0f}%</td></tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;margin-top:6px;border-top:1px solid #F1F5F9;">'
            f'<thead><tr style="background:#F8FAFC;">'
            f'<th style="padding:4px 6px;width:20px;"></th>'
            f'<th style="padding:4px 6px;color:#64748B;font-size:10px;text-align:left;">진료과</th>'
            f'<th style="padding:4px 6px;color:#64748B;font-size:10px;text-align:right;">재원수</th>'
            f'<th style="padding:4px 6px;color:#64748B;font-size:10px;text-align:right;">비율</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>",
            unsafe_allow_html=True,
        )

    elif chart_type == "bar_h":
        fig = go.Figure(go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
            text=[f"{v}명 ({v/total*100:.0f}%)" for v in values],
            textposition="outside", textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>%{x}명<extra></extra>",
        ))
        fig.update_layout(
            height=max(200, len(labels) * 30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=12),
            margin=dict(l=0, r=70, t=8, b=8),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, title=dict(text="재원 환자 수 (명)", font=dict(size=10))),
        )
        st.plotly_chart(fig, use_container_width=True, key="dept_bar_h")

    elif chart_type == "treemap":
        fig = go.Figure(go.Treemap(
            labels=labels, values=values, parents=[""] * len(labels),
            marker=dict(colors=colors, line=dict(width=2, color="#FFFFFF")),
            texttemplate="<b>%{label}</b><br>%{value}명<br>%{percentRoot:.0%}",
            textfont=dict(size=10),
            hovertemplate="<b>%{label}</b><br>%{value}명 (%{percentRoot:.1%})<extra></extra>",
        ))
        fig.update_layout(
            height=270,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#333333", size=12),
            margin=dict(l=0, r=0, t=8, b=8),
        )
        st.plotly_chart(fig, use_container_width=True, key="dept_treemap")


def _render_trend_chart(data: List[Dict], chart_type: str, occupied: int, occ_rate: float) -> None:
    """
    주간 추이 7일 대안 차트 렌더러.
    chart_type: "table"(기존 표) | "line" | "area" | "bar"
    """
    if not data:
        st.caption("추이 데이터 없음")
        return

    dates  = [str(r.get("기준일", ""))           for r in data]
    occs   = [_safe_float(r.get("가동률"))     for r in data]
    admins = [_safe_int(r.get("금일입원"))      for r in data]
    discs  = [_safe_int(r.get("금일퇴원"))      for r in data]
    key_sfx = chart_type

    if chart_type == "table":
        # ── 기존 HTML 표 그대로 유지 ────────────────────────────────
        _tH2 = "padding:7px 10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748B;border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        rows = ""
        for ti, row in enumerate(data):
            dt   = str(row.get("기준일", ""))
            occ  = float(row.get("가동률", 0) or 0)
            adm  = int(row.get("금일입원", 0) or 0)
            disc = int(row.get("금일퇴원", 0) or 0)
            tbg  = "#F8FAFC" if ti % 2 == 0 else "#FFFFFF"
            if occ >= 90:   oc, lbl = "#EF4444", '<span style="font-size:9px;background:#FEE2E2;color:#991B1B;border-radius:3px;padding:1px 5px;margin-left:3px;font-weight:700;">위험</span>'
            elif occ >= 80: oc, lbl = "#F59E0B", '<span style="font-size:9px;background:#FFFBEB;color:#92400E;border-radius:3px;padding:1px 5px;margin-left:3px;font-weight:700;">주의</span>'
            else:            oc, lbl = "#059669", ""
            td = f"padding:7px 10px;background:{tbg};border-bottom:1px solid #F8FAFC;font-size:13px;"
            rows += (
                f"<tr>"
                f'<td style="{td}font-weight:600;color:#334155;white-space:nowrap;">{dt}</td>'
                f'<td style="{td}text-align:right;">'
                f'<span style="font-size:16px;font-weight:800;color:{oc};font-family:Consolas,monospace;letter-spacing:-0.02em;">{occ:.1f}%</span>{lbl}</td>'
                f'<td style="{td}text-align:right;">'
                f'<span style="font-size:16px;font-weight:800;color:{C["blue"]};font-family:Consolas,monospace;">{adm}</span></td>'
                f'<td style="{td}text-align:right;">'
                f'<span style="font-size:15px;font-weight:700;color:#64748B;font-family:Consolas,monospace;">{disc}</span></td>'
                f"</tr>"
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;"><thead><tr>'
            f'<th style="{_tH2}text-align:left;">날짜</th>'
            f'<th style="{_tH2}text-align:right;">가동률</th>'
            f'<th style="{_tH2}text-align:right;color:{C["blue"]};">입원</th>'
            f'<th style="{_tH2}text-align:right;color:#475569;">퇴원</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>",
            unsafe_allow_html=True,
        )
        return

    if not HAS_PLOTLY:
        st.caption("plotly 미설치 — pip install plotly")
        return

    fig = go.Figure()

    if chart_type == "line":
        fig.add_trace(go.Scatter(x=dates, y=occs, name="가동률(%)", mode="lines+markers",
            line=dict(color="#1E40AF", width=2.5, shape="spline"),
            fill="tozeroy", fillcolor="rgba(30,64,175,0.06)",
            marker=dict(size=6, color="#1E40AF", line=dict(width=2, color="#fff")),
            yaxis="y", hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=admins, name="금일입원", mode="lines+markers",
            line=dict(color="#059669", width=1.5, dash="dot", shape="spline"),
            marker=dict(size=4, color="#059669"), yaxis="y2",
            hovertemplate="%{x}<br>입원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=discs, name="금일퇴원", mode="lines+markers",
            line=dict(color="#F59E0B", width=1.5, dash="dot", shape="spline"),
            marker=dict(size=4, color="#F59E0B"), yaxis="y2",
            hovertemplate="%{x}<br>퇴원 %{y}명<extra></extra>"))
        fig.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), showlegend=True,
            margin=dict(l=0, r=0, t=8, b=40),
            legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, title=dict(text="가동률(%)", font=dict(size=10)), ticksuffix="%", range=[0, 110]),
            yaxis2=dict(**_AX, overlaying="y", side="right", title=dict(text="인원(명)", font=dict(size=10))),
            xaxis=dict(**_AX),
        )

    elif chart_type == "area":
        fig.add_trace(go.Scatter(x=dates, y=admins, name="금일입원", mode="lines",
            fill="tozeroy", fillcolor="rgba(5,150,105,0.15)",
            line=dict(color="#059669", width=1.5),
            hovertemplate="%{x}<br>입원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=discs, name="금일퇴원", mode="lines",
            fill="tozeroy", fillcolor="rgba(245,158,11,0.15)",
            line=dict(color="#F59E0B", width=1.5),
            hovertemplate="%{x}<br>퇴원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=occs, name="가동률(%)", mode="lines+markers",
            line=dict(color="#1E40AF", width=2), marker=dict(size=5, color="#1E40AF"),
            yaxis="y2", hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        fig.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), showlegend=True,
            margin=dict(l=0, r=0, t=8, b=40),
            legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, title=dict(text="인원(명)", font=dict(size=10))),
            yaxis2=dict(**_AX, overlaying="y", side="right", ticksuffix="%", range=[0, 110],
                        title=dict(text="가동률(%)", font=dict(size=10))),
            xaxis=dict(**_AX),
        )

    elif chart_type == "bar":
        fig.add_trace(go.Bar(x=dates, y=admins, name="금일입원", marker_color="#059669",
                             hovertemplate="%{x}<br>입원 %{y}명<extra></extra>"))
        fig.add_trace(go.Bar(x=dates, y=discs, name="금일퇴원", marker_color="#F59E0B",
                             hovertemplate="%{x}<br>퇴원 %{y}명<extra></extra>"))
        fig.add_trace(go.Scatter(x=dates, y=occs, name="가동률(%)", mode="lines+markers",
            line=dict(color="#1E40AF", width=2), marker=dict(size=5),
            yaxis="y2", hovertemplate="%{x}<br>가동률 %{y:.1f}%<extra></extra>"))
        fig.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=0, t=8, b=40),
            barmode="group", showlegend=True,
            legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, title=dict(text="인원(명)", font=dict(size=10))),
            yaxis2=dict(**_AX, overlaying="y", side="right", ticksuffix="%", range=[0, 110],
                        title=dict(text="가동률(%)", font=dict(size=10))),
            xaxis=dict(**_AX),
        )

    st.plotly_chart(fig, use_container_width=True, key=f"trend_{key_sfx}")


def _render_ward_alt_chart(data: List[Dict], chart_type: str, ward_surg: Dict) -> None:
    """
    병동별 당일 현황 대안 차트 렌더러.
    chart_type: "bar_h" | "heatmap"  (table은 기존 HTML 처리)
    """
    if not data or not HAS_PLOTLY:
        st.caption("데이터 없음")
        return

    wards    = [str(r.get("병동명", ""))           for r in data]
    stays    = [_safe_int(r.get("재원수"))       for r in data]
    admins   = [_safe_int(r.get("금일입원"))     for r in data]
    discs    = [_safe_int(r.get("금일퇴원"))     for r in data]
    beds     = [_safe_int(r.get("총병상"))       for r in data]
    occs     = [_safe_float(r.get("가동률"))     for r in data]

    if chart_type == "bar_h":
        bar_colors = ["#EF4444" if r >= 90 else "#F59E0B" if r >= 80 else "#059669" for r in occs]
        fig = go.Figure(go.Bar(
            x=occs, y=wards, orientation="h",
            marker=dict(color=bar_colors, line=dict(color="rgba(0,0,0,0)")),
            text=[f"{r:.1f}%  ({s}명/{b}병상)" for r, s, b in zip(occs, stays, beds)],
            textposition="outside", textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>가동률 %{x:.1f}%<extra></extra>",
        ))
        for thr, lbl, clr in [(90, "위험 90%", "#EF4444"), (80, "주의 80%", "#F59E0B")]:
            fig.add_vline(x=thr, line=dict(color=clr, dash="dash", width=1.2),
                          annotation_text=lbl, annotation_font=dict(size=9, color=clr),
                          annotation_position="top")
        fig.update_layout(
            height=max(200, len(wards) * 36),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=90, t=8, b=8),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, range=[0, 115], ticksuffix="%",
                       title=dict(text="병상 가동률 (%)", font=dict(size=10))),
        )
        st.plotly_chart(fig, use_container_width=True, key="ward_bar_h")

    elif chart_type == "heatmap":
        indicators = ["재원수", "금일입원", "금일퇴원", "가동률(%)"]
        z_raw = [stays, admins, discs, occs]
        z_matrix = [list(row) for row in zip(*z_raw)]  # [병동 × 지표]
        fig = go.Figure(go.Heatmap(
            z=z_matrix, x=indicators, y=wards,
            colorscale=[[0.0, "#DBEAFE"], [0.5, "#93C5FD"], [1.0, "#1E40AF"]],
            text=[[f"{v:.1f}" if isinstance(v, float) else str(v) for v in row] for row in z_matrix],
            texttemplate="%{text}",
            textfont=dict(size=10, color="#FFFFFF"),
            hovertemplate="<b>%{y}</b><br>%{x}: %{text}<extra></extra>",
            showscale=True,
            colorbar=dict(len=0.8, thickness=12, tickfont=dict(size=9)),
        ))
        fig.update_layout(
            height=max(220, len(wards) * 34),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=60, t=30, b=8),
            xaxis=dict(side="top", tickfont=dict(size=10)),
            yaxis=dict(**_AX, autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True, key="ward_heatmap")


def _render_dx7_chart(data: List[Dict], chart_type: str) -> None:
    """
    최근 7일 주상병 분포 대안 차트 렌더러.
    chart_type: "pie" | "bar_h" | "treemap"
    """
    from collections import defaultdict as _ddx7
    if not data:
        st.info("주상병 데이터 없음")
        return

    agg: Dict[str, int] = _ddx7(int)
    for r in data:
        agg[r.get("주상병명", "기타")] += _safe_int(r.get("환자수"))
    sorted_items = sorted(agg.items(), key=lambda x: -x[1])
    top8  = list(sorted_items[:8])
    etc   = sum(v for _, v in sorted_items[8:])
    if etc > 0:
        top8.append(("기타", etc))
    labels = [n for n, _ in top8]
    values = [v for _, v in top8]
    total  = max(sum(values), 1)
    colors = _PALETTE[:len(labels)]

    if chart_type == "pie":
        if not HAS_PLOTLY:
            st.info("주상병 데이터 없음")
            return
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.52,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
            textinfo="percent", textfont=dict(size=10, color="#FFFFFF"),
            direction="clockwise", sort=True,
            hovertemplate="<b>%{label}</b><br>%{value}명 (%{percent})<extra></extra>",
        ))
        fig.update_layout(
            height=220, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), margin=dict(l=0, r=0, t=8, b=8), showlegend=False,
            annotations=[dict(text=f"<b>{total}</b><br>명", x=0.5, y=0.5,
                              showarrow=False, font=dict(size=14, color="#0F172A"))],
        )
        st.plotly_chart(fig, use_container_width=True, key="dx7_pie")
        # 범례 테이블
        rows = ""
        for i, (nm, cnt) in enumerate(top8):
            pct = cnt / total * 100
            bg  = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
            clr = colors[i % len(colors)]
            rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:4px 6px;text-align:center;">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{clr};"></span></td>'
                f'<td style="padding:4px 6px;color:#0F172A;font-weight:500;">{nm}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:#1E40AF;font-family:Consolas,monospace;font-weight:700;">{cnt}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:#64748B;font-family:Consolas,monospace;">{pct:.0f}%</td></tr>'
            )
        st.markdown(
            '<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:8px;border-top:1px solid #F1F5F9;">'
            '<tr style="background:#F8FAFC;">'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;width:24px;">#</th>'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:left;">주상병명</th>'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:40px;">건수</th>'
            '<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:40px;">비율</th></tr>'
            f'{rows}</table>',
            unsafe_allow_html=True,
        )

    elif chart_type == "bar_h":
        if not HAS_PLOTLY:
            st.info("주상병 데이터 없음")
            return
        fig = go.Figure(go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
            text=[f"{v}건" for v in values],
            textposition="outside", textfont=dict(size=10, color="#475569"),
            hovertemplate="<b>%{y}</b><br>%{x}건<extra></extra>",
        ))
        fig.update_layout(
            height=max(200, len(labels) * 30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=60, t=8, b=8),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, title=dict(text="입원 건수", font=dict(size=10))),
        )
        st.plotly_chart(fig, use_container_width=True, key="dx7_bar_h")

    elif chart_type == "treemap":
        if not HAS_PLOTLY:
            st.info("주상병 데이터 없음")
            return
        fig = go.Figure(go.Treemap(
            labels=labels, values=values, parents=[""] * len(labels),
            marker=dict(colors=colors, line=dict(width=2, color="#FFFFFF")),
            texttemplate="<b>%{label}</b><br>%{value}건<br>%{percentRoot:.0%}",
            textfont=dict(size=10),
            hovertemplate="<b>%{label}</b><br>%{value}건 (%{percentRoot:.1%})<extra></extra>",
        ))
        fig.update_layout(height=270, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12), margin=dict(l=0, r=0, t=8, b=8))
        st.plotly_chart(fig, use_container_width=True, key="dx7_treemap")


def _render_dx_compare_chart(data: List[Dict], chart_type: str) -> None:
    """
    금일 vs 전일 주상병 비교 대안 차트 렌더러.
    chart_type: "overlay" | "grouped" | "bar_h"
    """
    from collections import defaultdict as _ddcmp
    if not data:
        st.info("주상병 분포 데이터 없음")
        return

    t_map: Dict[str, int] = _ddcmp(int)
    y_map: Dict[str, int] = _ddcmp(int)
    for r in data:
        nm  = r.get("주상병명", "기타") or "기타"
        cnt = _safe_int(r.get("환자수"))
        day = str(r.get("기준일", ""))
        (t_map if "오늘" in day else y_map)[nm] += cnt

    all_dx  = set(list(t_map.keys()) + list(y_map.keys()))
    sorted_dx = sorted(all_dx, key=lambda d: -(t_map.get(d, 0) + y_map.get(d, 0)))
    top_dx    = sorted_dx[:8]
    t_vals    = [t_map.get(d, 0) for d in top_dx]
    y_vals    = [y_map.get(d, 0) for d in top_dx]
    x_max     = max(max(t_vals, default=1), max(y_vals, default=1)) * 1.2
    _COL_T    = "#1D4ED8"
    _COL_Y    = "#0EA5E9"

    # 증감 주석
    def _anns_h(names, t_vs, y_vs, x_mx):
        anns = []
        for i, (nm, tv, yv) in enumerate(zip(names, t_vs, y_vs)):
            d = tv - yv
            clr = C["danger"] if d > 0 else C["ok"] if d < 0 else "#64748B"
            txt = f"▲{d:+d}" if d > 0 else f"▼{d}" if d < 0 else "─"
            anns.append(dict(x=x_mx - 0.2, y=nm, text=f"<b>{txt}</b>",
                             showarrow=False, font=dict(size=11, color=clr),
                             xref="x", yref="y", xanchor="right"))
        return anns

    if not HAS_PLOTLY:
        st.info("주상병 분포 데이터 없음")
        return

    if chart_type == "overlay":
        ranked = list(reversed(top_dx))
        rank_labels = [f"{len(top_dx) - i}위" for i in range(len(ranked))]
        tv_r  = [t_map.get(d, 0) for d in ranked]
        yv_r  = [y_map.get(d, 0) for d in ranked]
        diffs = [t - y for t, y in zip(tv_r, yv_r)]
        anns  = []
        for i, (df, tv, yv) in enumerate(zip(diffs, tv_r, yv_r)):
            clr = C["danger"] if df > 0 else C["ok"] if df < 0 else "#64748B"
            txt = f"▲{df:+d}" if df > 0 else f"▼{df}" if df < 0 else "─"
            anns.append(dict(x=x_max - 0.2, y=rank_labels[i], text=f"<b>{txt}</b>",
                             showarrow=False, font=dict(size=12, color=clr),
                             xref="x", yref="y", xanchor="right"))
        fig = go.Figure()
        fig.add_trace(go.Bar(name="전일", y=rank_labels, x=yv_r, orientation="h",
            marker_color=_COL_Y, marker=dict(opacity=0.6, line=dict(width=0)),
            text=yv_r, textposition="inside", textfont=dict(size=11, color="#FFFFFF"),
            hovertemplate="전일: %{x}명<extra></extra>"))
        fig.add_trace(go.Bar(name="금일", y=rank_labels, x=tv_r, orientation="h",
            marker_color=_COL_T, marker=dict(line=dict(width=0)),
            text=tv_r, textposition="inside", textfont=dict(size=12, color="#FFFFFF"),
            hovertemplate="금일: %{x}명<extra></extra>"))
        fig.update_layout(
            barmode="overlay", height=270,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            margin=dict(l=0, r=50, t=8, b=46),
            legend=dict(orientation="h", y=-0.16, x=0, font=dict(size=12, color="#1E293B"),
                        bgcolor="rgba(0,0,0,0)", traceorder="reversed"),
            showlegend=True, annotations=anns,
            xaxis=dict(range=[0, x_max], gridcolor="#F1F5F9",
                       tickfont=dict(size=10.5, color="#64748B"), zeroline=False,
                       title=dict(text="입원 환자 수 (명)", font=dict(size=11, color="#64748B"))),
            yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=12, color="#0F172A"), zeroline=False),
            bargap=0.3,
        )
        st.plotly_chart(fig, use_container_width=True, key="dx_overlay")
        # 하단 랭킹 테이블
        rows = ""
        for ri, (nm, tc, yc) in enumerate(zip(top_dx, t_vals, y_vals), 1):
            d  = tc - yc
            dc = C["danger"] if d > 0 else C["ok"] if d < 0 else "#94A3B8"
            dt = f"▲{d:+d}" if d > 0 else f"▼{d}" if d < 0 else "─"
            bg = "#FFFFFF" if ri % 2 == 0 else "#F8FAFC"
            rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:4px 6px;font-weight:700;color:#1E40AF;">{ri}위</td>'
                f'<td style="padding:4px 5px;color:#0F172A;font-weight:500;">{nm}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:{_COL_T};font-family:Consolas,monospace;font-weight:700;">{tc}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:{_COL_Y};font-family:Consolas,monospace;">{yc}</td>'
                f'<td style="padding:4px 6px;text-align:right;color:{dc};font-weight:700;">{dt}</td></tr>'
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:8px;border-top:1px solid #F1F5F9;">'
            f'<tr style="background:#F8FAFC;">'
            f'<th style="padding:5px 6px;color:#64748B;font-size:10px;width:30px;">#</th>'
            f'<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:left;">주상병명</th>'
            f'<th style="padding:5px 6px;color:{_COL_T};font-size:10px;text-align:right;width:34px;">금일</th>'
            f'<th style="padding:5px 6px;color:{_COL_Y};font-size:10px;text-align:right;width:34px;">전일</th>'
            f'<th style="padding:5px 6px;color:#64748B;font-size:10px;text-align:right;width:38px;">증감</th></tr>'
            f'{rows}</table>',
            unsafe_allow_html=True,
        )

    elif chart_type == "grouped":
        fig = go.Figure()
        fig.add_trace(go.Bar(x=top_dx, y=y_vals, name="전일",
            marker=dict(color=_COL_Y, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="전일: %{y}명<extra></extra>"))
        fig.add_trace(go.Bar(x=top_dx, y=t_vals, name="금일",
            marker=dict(color=_COL_T, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="금일: %{y}명<extra></extra>"))
        fig.update_layout(
            height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            barmode="group", showlegend=True,
            legend=dict(orientation="h", y=-0.2, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(**_AX, tickangle=-30, tickfont=dict(size=9)),
            yaxis=dict(**_AX, title=dict(text="입원 환자 수 (명)", font=dict(size=10))),
            margin=dict(l=0, r=0, t=8, b=60),
        )
        st.plotly_chart(fig, use_container_width=True, key="dx_grouped")

    elif chart_type == "bar_h":
        deltas      = [t - y for t, y in zip(t_vals, y_vals)]
        delta_colors = ["#EF4444" if d > 0 else "#3B82F6" if d < 0 else "#94A3B8" for d in deltas]
        anns = [
            dict(x=max(tv, yv) + 0.5, y=dx,
                 text=f"{'▲' if d > 0 else '▼' if d < 0 else '─'}{abs(d)}",
                 showarrow=False, font=dict(size=9, color=c), xanchor="left")
            for dx, tv, yv, d, c in zip(top_dx, t_vals, y_vals, deltas, delta_colors)
        ]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=t_vals, y=top_dx, orientation="h", name="금일",
            marker=dict(color=_COL_T, opacity=0.9, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="금일: %{x}명<extra></extra>"))
        fig.add_trace(go.Bar(x=y_vals, y=top_dx, orientation="h", name="전일",
            marker=dict(color=_COL_Y, opacity=0.6, line=dict(color="rgba(0,0,0,0)")),
            hovertemplate="전일: %{x}명<extra></extra>"))
        fig.update_layout(
            height=max(200, len(top_dx) * 36),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#333333", size=12),
            barmode="overlay", showlegend=True,
            legend=dict(orientation="h", y=-0.15, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(**_AX, autorange="reversed"),
            xaxis=dict(**_AX, range=[0, x_max],
                       title=dict(text="입원 환자 수 (명)", font=dict(size=10))),
            annotations=anns,
            margin=dict(l=0, r=50, t=8, b=40),
        )
        st.plotly_chart(fig, use_container_width=True, key="dx_bar_h")
