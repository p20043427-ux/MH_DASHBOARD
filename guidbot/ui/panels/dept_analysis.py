"""
ui/panels/dept_analysis.py  —  진료과 분석 탭 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[기능]
  특정 진료과의 지역·성별·나이대·구분별 분포를 분석하는 탭.

[분석 모드]
  ① 단일월 분석 — 선택 월의 스냅샷 + 12개월 추세
  ② 비교월 분석 — 두 월의 차이 비교 (지역/성별/연령대)

[사용 Oracle VIEW]
  기존 (이미 존재):
    V_REGION_DEPT_MONTHLY  — 월별 진료과×지역 환자수
    V_MONTHLY_OPD_DEPT     — 월별 진료과 외래 지표
  신규 필요 (없으면 미연결 안내):
    V_DEPT_GENDER_MONTHLY  — 월별 진료과×성별 환자수
    V_DEPT_AGE_MONTHLY     — 월별 진료과×연령대 환자수
    V_DEPT_CATEGORY_AGE    — 월별 진료과×구분(외래/입원)×연령대

[VIEW 생성 SQL (DBA 요청용)]
  -- V_DEPT_GENDER_MONTHLY
  CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_GENDER_MONTHLY AS
  SELECT TO_CHAR(기준일,'YYYYMM') AS 기준월, 진료과명, 성별, COUNT(*) AS 환자수
  FROM JAIN_WM.PATIENT_VISIT_BASE
  GROUP BY TO_CHAR(기준일,'YYYYMM'), 진료과명, 성별;

  -- V_DEPT_AGE_MONTHLY
  CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_AGE_MONTHLY AS
  SELECT TO_CHAR(기준일,'YYYYMM') AS 기준월, 진료과명,
         FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10 AS 연령대,
         COUNT(*) AS 환자수
  FROM JAIN_WM.PATIENT_VISIT_BASE
  GROUP BY TO_CHAR(기준일,'YYYYMM'), 진료과명,
           FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10;

  -- V_DEPT_CATEGORY_AGE
  CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_CATEGORY_AGE AS
  SELECT TO_CHAR(기준일,'YYYYMM') AS 기준월, 진료과명, 구분,
         FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10 AS 연령대,
         COUNT(*) AS 환자수
  FROM JAIN_WM.PATIENT_VISIT_BASE
  GROUP BY TO_CHAR(기준일,'YYYYMM'), 진료과명, 구분,
           FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10;
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import streamlit as st

from utils.type_helpers import safe_int as _safe_int

from ui.panels._shared import (
    C, HAS_PLOTLY, go, logger,
    _kpi_card, _sec_hd, _gap, _PALETTE, _PLOTLY_LAYOUT,
    _plotly_empty,
)

# ────────────────────────────────────────────────────────────────────
# 상수
# ────────────────────────────────────────────────────────────────────
_AGE_ORDER = ["0대", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대이상"]
_AGE_COLORS = ["#818CF8", "#38BDF8", "#34D399", "#FBBF24", "#F87171",
               "#A78BFA", "#FB923C", "#60A5FA", "#F472B6"]
_GENDER_COLORS = {"남": "#3B82F6", "여": "#EC4899", "기타": "#94A3B8"}
_REGION_ACCENT = C["teal"]

_BUSAN_DISTRICTS = {
    "중구","서구","동구","영도구","부산진구","동래구",
    "남구","북구","해운대구","사하구","금정구","강서구",
    "연제구","수영구","사상구","기장군",
}

# ────────────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────────────
def _fmt_ym(ym: str) -> str:
    """'202501' → '2025년 01월'"""
    return f"{ym[:4]}년 {ym[4:6]}월" if len(ym) >= 6 else ym


# _safe_int: utils.type_helpers 에서 import (위에서 import)


def _strip_region(r: str) -> str:
    return r.replace("부산광역시 ", "").replace("경상남도 ", "경남 ").replace("경상북도 ", "경북 ")


# ────────────────────────────────────────────────────────────────────
# Oracle 조회 래퍼 (missing VIEW → 빈 리스트 반환)
# ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _query(sql: str) -> List[Dict]:
    """Oracle SELECT → dict 리스트. 실패 시 [] 반환."""
    try:
        from db.oracle_client import execute_query
        return execute_query(sql) or []
    except Exception as _e:
        logger.debug(f"[dept_analysis] 쿼리 실패 (무시): {_e}")
        return []


def _dept_region(dept: str, ym_from: str, ym_to: str) -> List[Dict]:
    sql = (
        "SELECT 기준월, 진료과명, 지역, 환자수 "
        "FROM JAIN_WM.V_REGION_DEPT_MONTHLY "
        f"WHERE 진료과명 = '{dept}' "
        f"AND 기준월 BETWEEN '{ym_from}' AND '{ym_to}' "
        "ORDER BY 기준월, 환자수 DESC"
    )
    return _query(sql)


def _dept_trend(dept: str) -> List[Dict]:
    sql = (
        "SELECT 기준년월, 외래환자수, 신환자수, 구환자수, 신환비율 "
        "FROM JAIN_WM.V_MONTHLY_OPD_DEPT "
        f"WHERE 진료과명 = '{dept}' "
        "ORDER BY 기준년월"
    )
    return _query(sql)


def _dept_gender(dept: str, ym_from: str, ym_to: str) -> Tuple[List[Dict], bool]:
    sql = (
        "SELECT 기준월, 성별, 환자수 "
        "FROM JAIN_WM.V_DEPT_GENDER_MONTHLY "
        f"WHERE 진료과명 = '{dept}' "
        f"AND 기준월 BETWEEN '{ym_from}' AND '{ym_to}' "
        "ORDER BY 기준월, 성별"
    )
    rows = _query(sql)
    has_view = bool(rows) or _view_exists("V_DEPT_GENDER_MONTHLY")
    return rows, has_view


def _dept_age(dept: str, ym_from: str, ym_to: str) -> Tuple[List[Dict], bool]:
    sql = (
        "SELECT 기준월, 연령대, 환자수 "
        "FROM JAIN_WM.V_DEPT_AGE_MONTHLY "
        f"WHERE 진료과명 = '{dept}' "
        f"AND 기준월 BETWEEN '{ym_from}' AND '{ym_to}' "
        "ORDER BY 기준월, 연령대"
    )
    rows = _query(sql)
    has_view = bool(rows) or _view_exists("V_DEPT_AGE_MONTHLY")
    return rows, has_view


def _dept_cat_age(dept: str, ym_from: str, ym_to: str) -> Tuple[List[Dict], bool]:
    sql = (
        "SELECT 기준월, 구분, 연령대, 환자수 "
        "FROM JAIN_WM.V_DEPT_CATEGORY_AGE "
        f"WHERE 진료과명 = '{dept}' "
        f"AND 기준월 BETWEEN '{ym_from}' AND '{ym_to}' "
        "ORDER BY 기준월, 구분, 연령대"
    )
    rows = _query(sql)
    has_view = bool(rows) or _view_exists("V_DEPT_CATEGORY_AGE")
    return rows, has_view


@st.cache_data(ttl=3600, show_spinner=False)
def _view_exists(view_name: str) -> bool:
    sql = (
        f"SELECT COUNT(*) AS CNT FROM ALL_VIEWS "
        f"WHERE VIEW_NAME = '{view_name}' AND OWNER = 'JAIN_WM'"
    )
    rows = _query(sql)
    return bool(rows and _safe_int(rows[0].get("CNT", 0)) > 0)


# ────────────────────────────────────────────────────────────────────
# 진료과 목록 추출
# ────────────────────────────────────────────────────────────────────
def _get_dept_list(monthly_opd_dept: List[Dict]) -> List[str]:
    """monthly_opd_dept 에서 진료과 목록 추출."""
    depts = sorted({
        str(r.get("진료과명", "")).strip()
        for r in monthly_opd_dept
        if r.get("진료과명", "")
    })
    if not depts:
        # fallback — 고정 목록
        depts = [
            "*내분비내과", "*호흡기내과", "*소화기내과", "*신장내과", "*순환기내과",
            "인공신장실", "신경과", "가정의학과", "신경외과", "*유방센터", "*위장관센터",
            "*갑상선센터", "성형외과", "정형외과", "*OBGY", "*난임센터",
            "소아청소년과", "이비인후과", "피부과", "응급의학과",
        ]
    return depts


# ────────────────────────────────────────────────────────────────────
# 공통 차트 렌더러
# ────────────────────────────────────────────────────────────────────
def _missing_view_info(view_name: str, col=None):
    """VIEW가 없을 때 안내 박스."""
    msg = (
        f'<div style="background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;'
        f'padding:10px 14px;font-size:12px;">'
        f'<b style="color:#C2410C;">🛠 Oracle VIEW 생성 필요</b>'
        f'<div style="color:#9A3412;margin-top:4px;font-family:Consolas,monospace;'
        f'font-size:11px;">JAIN_WM.{view_name}</div>'
        f'<div style="color:#7C2D12;margin-top:4px;font-size:11px;">'
        f'DBA에게 해당 뷰 생성을 요청하세요. (파일 상단 docstring 참조)</div></div>'
    )
    target = col if col else st
    target.markdown(msg, unsafe_allow_html=True)


def _chart_region_bar(region_agg: Dict[str, int], title: str,
                       chart_key: str, height: int = 280):
    """구군별 유입 가로 막대 차트."""
    if not HAS_PLOTLY or not region_agg:
        return
    sorted_r = sorted(region_agg.items(), key=lambda x: -x[1])
    labels  = [_strip_region(k) for k, _ in sorted_r]
    values  = [v for _, v in sorted_r]
    total   = sum(values)
    colors  = [C["teal"] if _is_busan(k) else C["orange"] for k, _ in sorted_r]

    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
        text=[f"{v:,}명 ({v/max(total,1)*100:.1f}%)" for v in values],
        textposition="outside",
        textfont=dict(size=9, color=C["t2"]),
        hovertemplate="<b>%{y}</b><br>%{x:,}명<extra></extra>",
    ))
    fig.update_layout(
        **_PLOTLY_LAYOUT,
        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
        height=height,
        margin=dict(l=0, r=90, t=32, b=8),
    )
    fig.update_xaxes(title_text="환자수(명)", title_font=dict(size=10, color=C["t3"]),
                     gridcolor="#F1F5F9")
    fig.update_yaxes(tickfont=dict(size=9))
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def _is_busan(region: str) -> bool:
    for d in _BUSAN_DISTRICTS:
        if d in region:
            return True
    return "부산" in region


def _chart_gender_pie(gender_agg: Dict[str, int], title: str,
                       chart_key: str, height: int = 260):
    """성별 파이 차트."""
    if not HAS_PLOTLY or not gender_agg:
        return
    labels = list(gender_agg.keys())
    values = list(gender_agg.values())
    colors = [_GENDER_COLORS.get(l, C["t3"]) for l in labels]
    total  = sum(values)

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        textinfo="label+percent",
        textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>%{value:,}명 (%{percent})<extra></extra>",
        hole=0.42,
    ))
    fig.update_layout(
        **_PLOTLY_LAYOUT,
        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
        height=height,
        margin=dict(l=0, r=0, t=32, b=8),
        showlegend=True,
        legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center",
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        annotations=[dict(
            text=f"총 {total:,}명",
            x=0.5, y=0.5, font=dict(size=12, color=C["t2"]),
            showarrow=False,
        )],
    )
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def _chart_age_bar(age_agg: Dict[str, int], title: str,
                    chart_key: str, height: int = 260):
    """나이대 막대 차트."""
    if not HAS_PLOTLY or not age_agg:
        return
    ages   = [a for a in _AGE_ORDER if a in age_agg]
    values = [age_agg[a] for a in ages]
    colors = [_AGE_COLORS[_AGE_ORDER.index(a) % len(_AGE_COLORS)] for a in ages]
    total  = sum(values)

    fig = go.Figure(go.Bar(
        x=ages, y=values,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
        text=[f"{v:,}" for v in values],
        textposition="outside",
        textfont=dict(size=10),
        hovertemplate="<b>%{x}</b><br>%{y:,}명 (%{customdata:.1f}%)<extra></extra>",
        customdata=[v / max(total, 1) * 100 for v in values],
    ))
    fig.update_layout(
        **_PLOTLY_LAYOUT,
        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
        height=height,
        margin=dict(l=0, r=0, t=32, b=8),
    )
    fig.update_xaxes(tickfont=dict(size=10))
    fig.update_yaxes(title_text="환자수(명)", title_font=dict(size=10, color=C["t3"]),
                     gridcolor="#F1F5F9")
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def _chart_cat_age_stacked(cat_age: Dict[str, Dict[str, int]], title: str,
                             chart_key: str, height: int = 260):
    """구분별 연령대 누적 막대 차트."""
    if not HAS_PLOTLY or not cat_age:
        return
    categories = list(cat_age.keys())
    cat_colors = {
        "외래": C["blue"], "입원": C["indigo"], "응급": C["orange"],
        "기타": C["t3"],
    }
    fig = go.Figure()
    for age in _AGE_ORDER:
        values = [cat_age.get(cat, {}).get(age, 0) for cat in categories]
        if sum(values) == 0:
            continue
        idx = _AGE_ORDER.index(age)
        fig.add_trace(go.Bar(
            name=age, x=categories, y=values,
            marker_color=_AGE_COLORS[idx % len(_AGE_COLORS)],
            hovertemplate=f"<b>%{{x}}</b> | {age}<br>%{{y:,}}명<extra></extra>",
        ))
    fig.update_layout(
        **_PLOTLY_LAYOUT,
        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
        barmode="stack",
        height=height,
        margin=dict(l=0, r=0, t=32, b=8),
        legend=dict(orientation="h", y=1.10, x=0.5, xanchor="center",
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(tickfont=dict(size=11))
    fig.update_yaxes(title_text="환자수(명)", title_font=dict(size=10, color=C["t3"]),
                     gridcolor="#F1F5F9")
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def _chart_trend_line(trend_rows: List[Dict], dept: str,
                       chart_key: str, height: int = 280):
    """월별 외래 추세 라인 차트."""
    if not HAS_PLOTLY or not trend_rows:
        return
    months = [str(r.get("기준년월", ""))[:6] for r in trend_rows]
    opd    = [_safe_int(r.get("외래환자수", 0)) for r in trend_rows]
    new_pt = [_safe_int(r.get("신환자수", 0)) for r in trend_rows]
    old_pt = [_safe_int(r.get("구환자수", 0)) for r in trend_rows]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months, y=opd, name="외래 전체",
        line=dict(color=C["blue"], width=2.5),
        mode="lines+markers",
        hovertemplate="<b>%{x}</b><br>외래 전체: %{y:,}명<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=new_pt, name="신환",
        line=dict(color=C["green"], width=2, dash="dot"),
        mode="lines+markers",
        hovertemplate="<b>%{x}</b><br>신환: %{y:,}명<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=old_pt, name="구환",
        line=dict(color=C["t3"], width=1.5, dash="dash"),
        mode="lines+markers",
        hovertemplate="<b>%{x}</b><br>구환: %{y:,}명<extra></extra>",
    ))
    fig.update_layout(
        **_PLOTLY_LAYOUT,
        title=dict(text=f"📈 {dept} 월별 외래 추세", font=dict(size=12, color=C["t2"]), x=0),
        height=height,
        margin=dict(l=0, r=0, t=38, b=8),
        legend=dict(orientation="h", y=1.10, x=0.5, xanchor="center",
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(tickfont=dict(size=10), tickangle=-30)
    fig.update_yaxes(title_text="환자수(명)", title_font=dict(size=10, color=C["t3"]),
                     gridcolor="#F1F5F9")
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def _chart_compare_bar(data_a: Dict[str, int], data_b: Dict[str, int],
                        label_a: str, label_b: str,
                        all_keys: List[str], title: str,
                        chart_key: str, height: int = 260,
                        horizontal: bool = False):
    """비교 묶음 막대 차트."""
    if not HAS_PLOTLY:
        return
    vals_a = [data_a.get(k, 0) for k in all_keys]
    vals_b = [data_b.get(k, 0) for k in all_keys]
    diff   = [b - a for a, b in zip(vals_a, vals_b)]
    diff_t = [f"{'▲' if d>0 else '▼' if d<0 else ''}{abs(d):,}" for d in diff]
    diff_c = [C["red"] if d > 0 else C["blue"] if d < 0 else "rgba(0,0,0,0)" for d in diff]

    fig = go.Figure()
    if horizontal:
        fig.add_trace(go.Bar(
            name=label_a, y=all_keys, x=vals_a, orientation="h",
            marker_color=C["indigo_l"], marker=dict(line=dict(color=C["indigo"], width=0.8)),
            hovertemplate=f"<b>%{{y}}</b><br>{label_a}: %{{x:,}}명<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            name=label_b, y=all_keys, x=vals_b, orientation="h",
            marker_color=C["teal_l"], marker=dict(line=dict(color=C["teal"], width=0.8)),
            hovertemplate=f"<b>%{{y}}</b><br>{label_b}: %{{x:,}}명<extra></extra>",
        ))
    else:
        fig.add_trace(go.Bar(
            name=label_a, x=all_keys, y=vals_a,
            marker_color=C["indigo_l"], marker=dict(line=dict(color=C["indigo"], width=0.8)),
            hovertemplate=f"<b>%{{x}}</b><br>{label_a}: %{{y:,}}명<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            name=label_b, x=all_keys, y=vals_b,
            marker_color=C["teal_l"], marker=dict(line=dict(color=C["teal"], width=0.8)),
            hovertemplate=f"<b>%{{x}}</b><br>{label_b}: %{{y:,}}명<extra></extra>",
        ))
        # 증감 텍스트 오버레이
        fig.add_trace(go.Scatter(
            x=all_keys,
            y=[max(a, b) + 1 for a, b in zip(vals_a, vals_b)],
            mode="text", text=diff_t,
            textfont=dict(size=9, color=diff_c),
            showlegend=False, hoverinfo="skip",
        ))

    fig.update_layout(
        **_PLOTLY_LAYOUT,
        title=dict(text=title, font=dict(size=12, color=C["t2"]), x=0),
        barmode="group",
        height=height,
        margin=dict(l=0, r=80, t=38, b=8),
        legend=dict(orientation="h", y=1.10, x=0.5, xanchor="center",
                    font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        bargap=0.2, bargroupgap=0.05,
    )
    fig.update_xaxes(tickfont=dict(size=10), tickangle=-30 if not horizontal else 0)
    fig.update_yaxes(title_text="환자수(명)" if not horizontal else "",
                     title_font=dict(size=10, color=C["t3"]),
                     gridcolor="#F1F5F9")
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


# ────────────────────────────────────────────────────────────────────
# 집계 헬퍼
# ────────────────────────────────────────────────────────────────────
def _agg_region(rows: List[Dict], ym: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for r in rows:
        if str(r.get("기준월", ""))[:6] != ym:
            continue
        rg = str(r.get("지역", ""))
        if rg in ("지역미상", "", "None"):
            continue
        result[rg] = result.get(rg, 0) + _safe_int(r.get("환자수", 0))
    return result


def _agg_gender(rows: List[Dict], ym: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for r in rows:
        if str(r.get("기준월", ""))[:6] != ym:
            continue
        g = str(r.get("성별", "기타"))
        result[g] = result.get(g, 0) + _safe_int(r.get("환자수", 0))
    return result


def _agg_age(rows: List[Dict], ym: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for r in rows:
        if str(r.get("기준월", ""))[:6] != ym:
            continue
        age_raw = _safe_int(r.get("연령대", 0))
        if age_raw >= 80:
            label = "80대이상"
        else:
            label = f"{(age_raw // 10) * 10}대"
            if label == "0대":
                label = "0대"
        result[label] = result.get(label, 0) + _safe_int(r.get("환자수", 0))
    return result


def _agg_cat_age(rows: List[Dict], ym: str) -> Dict[str, Dict[str, int]]:
    """구분 → {연령대: 환자수}"""
    result: Dict[str, Dict[str, int]] = {}
    for r in rows:
        if str(r.get("기준월", ""))[:6] != ym:
            continue
        cat = str(r.get("구분", "기타"))
        age_raw = _safe_int(r.get("연령대", 0))
        label = "80대이상" if age_raw >= 80 else f"{(age_raw // 10) * 10}대"
        if cat not in result:
            result[cat] = {}
        result[cat][label] = result[cat].get(label, 0) + _safe_int(r.get("환자수", 0))
    return result


# ────────────────────────────────────────────────────────────────────
# 지역 순위 표
# ────────────────────────────────────────────────────────────────────
def _render_region_rank(region_agg: Dict[str, int], col=None):
    sorted_r = sorted(region_agg.items(), key=lambda x: -x[1])
    busan  = [(k, v) for k, v in sorted_r if _is_busan(k)][:10]
    others = [(k, v) for k, v in sorted_r if not _is_busan(k)][:8]
    total  = sum(region_agg.values())
    medals = ["🥇", "🥈", "🥉"]

    def _row_html(rank, name, cnt):
        pct = cnt / max(total, 1) * 100
        bar = f'<div style="flex:1;height:6px;background:#F1F5F9;border-radius:3px;">' \
              f'<div style="width:{pct:.0f}%;height:100%;background:{_REGION_ACCENT};border-radius:3px;"></div></div>'
        md = medals[rank] if rank < 3 else f'<span style="font-size:10px;color:{C["t4"]};font-weight:700;">{rank+1}</span>'
        short = _strip_region(name)
        return (
            f'<div style="display:flex;align-items:center;gap:5px;padding:3px 0;">'
            f'<div style="width:22px;text-align:center;">{md}</div>'
            f'<div style="width:54px;font-size:11px;font-weight:600;color:{C["t2"]};white-space:nowrap;"'
            f' title="{name}">{short}</div>'
            f'{bar}'
            f'<div style="width:48px;font-size:11px;font-weight:700;color:{_REGION_ACCENT};'
            f'font-family:Consolas,monospace;text-align:right;">{cnt:,}</div>'
            f'<div style="width:40px;font-size:10px;color:{C["t3"]};text-align:right;">{pct:.1f}%</div>'
            f'</div>'
        )

    html = ""
    if busan:
        html += (
            f'<div style="font-size:11.5px;font-weight:700;color:{C["teal"]};'
            f'margin-bottom:4px;">🏙️ 부산 내 구군</div>'
        )
        for i, (nm, cnt) in enumerate(busan):
            html += _row_html(i, nm, cnt)

    if others:
        html += (
            f'<div style="font-size:11.5px;font-weight:700;color:{C["orange"]};'
            f'margin:10px 0 4px;">🗺️ 부산 외 지역</div>'
        )
        for i, (nm, cnt) in enumerate(others):
            html += _row_html(i, nm, cnt)

    container = col if col else st
    container.markdown(
        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;'
        f'padding:10px 14px;">{html}</div>',
        unsafe_allow_html=True,
    )


# ────────────────────────────────────────────────────────────────────
# 자동 인사이트 박스
# ────────────────────────────────────────────────────────────────────
def _insight_box(items: List[Tuple[str, str, str]]):
    """[(제목, 내용, 색상), ...] → 인사이트 카드."""
    cols = st.columns(min(len(items), 3), gap="small")
    for i, (title, body, color) in enumerate(items):
        cols[i % len(cols)].markdown(
            f'<div style="background:#FFFFFF;border:1px solid #F0F4F8;'
            f'border-left:4px solid {color};border-radius:8px;'
            f'padding:10px 14px;margin-bottom:8px;">'
            f'<div style="font-size:11.5px;font-weight:700;color:{color};'
            f'margin-bottom:5px;">{title}</div>'
            f'<div style="font-size:12px;color:{C["t2"]};line-height:1.6;">{body}</div></div>',
            unsafe_allow_html=True,
        )


# ────────────────────────────────────────────────────────────────────
# ① 단일월 분석
# ────────────────────────────────────────────────────────────────────
def _render_single(dept: str, avail_months: List[str]):
    """단일월 스냅샷 분석."""
    if not avail_months:
        st.info("조회 가능한 월 데이터가 없습니다. Oracle 연결 상태를 확인하세요.")
        return

    # ── 컨트롤
    ctrl_col, _, info_col = st.columns([3, 3, 6], gap="small")
    with ctrl_col:
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};padding-bottom:2px;">'
            f'📅 분석 월</div>',
            unsafe_allow_html=True,
        )
        sel_ym = st.selectbox(
            "분석 월", options=avail_months, index=0,
            key=f"da_single_ym_{dept}",
            label_visibility="collapsed",
            format_func=_fmt_ym,
        )

    # ── 데이터 로드
    region_rows               = _dept_region(dept, sel_ym, sel_ym)
    gender_rows, has_gender   = _dept_gender(dept, sel_ym, sel_ym)
    age_rows,    has_age      = _dept_age(dept, sel_ym, sel_ym)
    cat_rows,    has_cat_age  = _dept_cat_age(dept, sel_ym, sel_ym)
    trend_rows                = _dept_trend(dept)

    # 집계
    region_agg  = _agg_region(region_rows, sel_ym)
    gender_agg  = _agg_gender(gender_rows, sel_ym)
    age_agg     = _agg_age(age_rows, sel_ym)
    cat_age     = _agg_cat_age(cat_rows, sel_ym)

    # 추세에서 해당 월 OPD 지표
    trend_this  = next((r for r in trend_rows
                        if str(r.get("기준년월", ""))[:6] == sel_ym), {})
    total_opd   = _safe_int(trend_this.get("외래환자수", 0))
    new_pt      = _safe_int(trend_this.get("신환자수", 0))
    old_pt      = _safe_int(trend_this.get("구환자수", 0))
    new_ratio   = float(trend_this.get("신환비율", 0) or 0)
    total_region = sum(region_agg.values())
    total_gender = sum(gender_agg.values())

    _gap(6)

    # ── KPI 카드
    k1, k2, k3, k4 = st.columns(4, gap="small")
    _kpi_card(k1, "👥", "외래 환자", f"{total_opd:,}" if total_opd else "─", "명",
              f"{_fmt_ym(sel_ym)}", C["blue"])
    _kpi_card(k2, "🆕", "신환자수", f"{new_pt:,}" if new_pt else "─", "명",
              f"신환율 {new_ratio:.1f}%", C["green"])
    _kpi_card(k3, "🔄", "구환자수", f"{old_pt:,}" if old_pt else "─", "명",
              "이전 방문 이력", C["t3"])
    _kpi_card(k4, "🗺️", "지역 유입", f"{total_region:,}" if total_region else "─", "명",
              f"{len(region_agg)}개 지역", C["teal"])

    _gap(8)

    # ════ 섹션 1: 지역 분석 ════════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["teal"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("🗺️ 부산시내 구군별 유입 분석", f"{dept} · {_fmt_ym(sel_ym)}", C["teal"])

    if region_agg:
        busan_agg  = {k: v for k, v in region_agg.items() if _is_busan(k)}
        others_agg = {k: v for k, v in region_agg.items() if not _is_busan(k)}

        ch_col, rank_col = st.columns([3, 2], gap="small")
        with ch_col:
            _chart_region_bar(
                region_agg,
                f"구군별 환자수 — {_fmt_ym(sel_ym)}",
                f"da_region_bar_{dept}_{sel_ym}",
                height=max(280, len(region_agg) * 22 + 80),
            )
        with rank_col:
            _render_region_rank(region_agg)

        # 부산 내/외 비율 파이
        if busan_agg and others_agg and HAS_PLOTLY:
            pie_col1, pie_col2 = st.columns(2, gap="small")
            bs_total = sum(busan_agg.values()); ot_total = sum(others_agg.values())
            fig_pie = go.Figure(go.Pie(
                labels=["부산 내", "부산 외"],
                values=[bs_total, ot_total],
                marker=dict(colors=[C["teal"], C["orange"]],
                            line=dict(color="#FFFFFF", width=2)),
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>%{value:,}명 (%{percent})<extra></extra>",
                hole=0.4,
            ))
            fig_pie.update_layout(
                **_PLOTLY_LAYOUT,
                title=dict(text="부산 내/외 비율", font=dict(size=12, color=C["t2"]), x=0),
                height=240,
                margin=dict(l=0, r=0, t=32, b=8),
                showlegend=False,
                annotations=[dict(
                    text=f"총<br>{bs_total+ot_total:,}명",
                    x=0.5, y=0.5, font=dict(size=11, color=C["t2"]),
                    showarrow=False,
                )],
            )
            pie_col1.plotly_chart(fig_pie, use_container_width=True,
                                  key=f"da_region_pie_{dept}_{sel_ym}")

            # 부산 내 Top5
            top5_bs = sorted(busan_agg.items(), key=lambda x: -x[1])[:5]
            bs_html = f'<div style="padding:8px 0;font-size:11.5px;font-weight:700;color:{C["teal"]}">🏙️ 부산 Top 5</div>'
            for i, (nm, cnt) in enumerate(top5_bs):
                md = ["🥇","🥈","🥉","4위","5위"][i]
                bs_html += (
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:3px 0;border-bottom:1px solid #F1F5F9;">'
                    f'<span style="font-size:12px;">{md} {_strip_region(nm)}</span>'
                    f'<span style="font-size:12px;font-weight:700;color:{C["teal"]};'
                    f'font-family:Consolas,monospace;">{cnt:,}</span></div>'
                )
            pie_col2.markdown(bs_html, unsafe_allow_html=True)
    else:
        st.info("지역별 데이터가 없습니다. (V_REGION_DEPT_MONTHLY 에 해당 진료과 데이터 없음)")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap(8)

    # ════ 섹션 2: 성별 + 나이대 ═══════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["violet"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("👤 성별·나이대 분석", f"{dept} · {_fmt_ym(sel_ym)}", C["violet"])

    g_col, a_col = st.columns(2, gap="small")

    with g_col:
        if gender_agg:
            _chart_gender_pie(
                gender_agg,
                f"성별 분포",
                f"da_gender_pie_{dept}_{sel_ym}",
            )
        elif not has_gender:
            _missing_view_info("V_DEPT_GENDER_MONTHLY", g_col)
        else:
            g_col.info("해당 월 성별 데이터 없음")

    with a_col:
        if age_agg:
            _chart_age_bar(
                age_agg,
                f"연령대 분포",
                f"da_age_bar_{dept}_{sel_ym}",
            )
        elif not has_age:
            _missing_view_info("V_DEPT_AGE_MONTHLY", a_col)
        else:
            a_col.info("해당 월 연령대 데이터 없음")

    st.markdown("</div>", unsafe_allow_html=True)
    _gap(8)

    # ════ 섹션 3: 구분별 나이 분포 ══════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 구분별 나이 분포", f"외래/입원별 연령대 현황 · {dept}", C["indigo"])

    if cat_age:
        _chart_cat_age_stacked(
            cat_age,
            f"구분(외래/입원)별 연령대 분포 — {_fmt_ym(sel_ym)}",
            f"da_cat_age_{dept}_{sel_ym}",
            height=300,
        )
    elif not has_cat_age:
        _missing_view_info("V_DEPT_CATEGORY_AGE")
    else:
        st.info("해당 월 구분별 데이터 없음")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap(8)

    # ════ 섹션 4: 12개월 추세 ═══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📈 월별 외래 추세", f"{dept} — 최근 12개월", C["blue"])

    if trend_rows:
        _chart_trend_line(
            trend_rows[-12:],
            dept,
            f"da_trend_{dept}",
        )
        # 추세 인사이트
        if len(trend_rows) >= 3:
            last3 = [_safe_int(r.get("외래환자수", 0)) for r in trend_rows[-3:]]
            trend_dir = "▲ 증가 추세" if last3[-1] > last3[0] else "▼ 감소 추세"
            trend_col = C["red"] if last3[-1] > last3[0] else C["blue"]
            avg12 = sum(_safe_int(r.get("외래환자수", 0)) for r in trend_rows[-12:]) // max(len(trend_rows[-12:]), 1)
            cur_vs_avg = total_opd - avg12
            _insight_box([
                ("📊 추세 방향", f"{dept} 최근 3개월 <b>{trend_dir}</b><br>"
                 f"{last3[0]:,} → {last3[-1]:,}명", trend_col),
                ("📋 12개월 평균", f"월 평균 외래 <b>{avg12:,}명</b><br>"
                 f"이번 달 평균 대비 <b>{cur_vs_avg:+,}명</b>", C["teal"]),
            ])
    else:
        st.info("추세 데이터 없음 (V_MONTHLY_OPD_DEPT 확인)")

    st.markdown("</div>", unsafe_allow_html=True)
    _gap()


# ────────────────────────────────────────────────────────────────────
# ② 비교월 분석
# ────────────────────────────────────────────────────────────────────
def _render_compare(dept: str, avail_months: List[str]):
    """두 월을 비교하는 분석."""
    if len(avail_months) < 2:
        st.info("비교를 위해 2개월 이상의 데이터가 필요합니다.")
        return

    # ── 컨트롤
    c1, c2, _ = st.columns([2, 2, 6], gap="small")
    with c1:
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{C["blue"]};'
            f'padding-bottom:2px;">📅 기준월</div>',
            unsafe_allow_html=True,
        )
        ym_a = st.selectbox("기준월", options=avail_months,
                             index=min(1, len(avail_months)-1),
                             key=f"da_cmp_a_{dept}",
                             label_visibility="collapsed",
                             format_func=_fmt_ym)
    with c2:
        st.markdown(
            f'<div style="font-size:11px;font-weight:700;color:{C["teal"]};'
            f'padding-bottom:2px;">📅 비교월</div>',
            unsafe_allow_html=True,
        )
        ym_b = st.selectbox("비교월", options=avail_months,
                             index=0,
                             key=f"da_cmp_b_{dept}",
                             label_visibility="collapsed",
                             format_func=_fmt_ym)

    if ym_a == ym_b:
        st.warning("서로 다른 두 달을 선택해 주세요.")
        return

    label_a = _fmt_ym(ym_a)
    label_b = _fmt_ym(ym_b)
    ym_min  = min(ym_a, ym_b)
    ym_max  = max(ym_a, ym_b)

    # ── 데이터 로드
    region_rows              = _dept_region(dept, ym_min, ym_max)
    gender_rows, has_gender  = _dept_gender(dept, ym_min, ym_max)
    age_rows,    has_age     = _dept_age(dept, ym_min, ym_max)
    trend_rows               = _dept_trend(dept)

    def _trend_row(ym):
        return next((r for r in trend_rows
                     if str(r.get("기준년월",""))[:6] == ym), {})

    tr_a = _trend_row(ym_a); tr_b = _trend_row(ym_b)
    opd_a = _safe_int(tr_a.get("외래환자수", 0))
    opd_b = _safe_int(tr_b.get("외래환자수", 0))
    new_a = _safe_int(tr_a.get("신환자수", 0))
    new_b = _safe_int(tr_b.get("신환자수", 0))
    opd_diff = opd_b - opd_a
    new_diff = new_b - new_a
    diff_color = C["red"] if opd_diff > 0 else C["blue"] if opd_diff < 0 else C["t3"]

    _gap(6)

    # ── KPI 비교 카드
    k1, k2, k3, k4 = st.columns(4, gap="small")
    _kpi_card(k1, "📅", label_a, f"{opd_a:,}" if opd_a else "─", "명", "기준월 외래", C["blue"])
    _kpi_card(k2, "📅", label_b, f"{opd_b:,}" if opd_b else "─", "명", "비교월 외래", C["teal"])
    _kpi_card(k3, "📊", "외래 증감", f"{opd_diff:+,}", "명",
              f"{'▲' if opd_diff>0 else '▼'} {abs(opd_diff)/max(opd_a,1)*100:.1f}%" if opd_a else "─",
              diff_color)
    _kpi_card(k4, "🆕", "신환 증감", f"{new_diff:+,}", "명",
              f"{label_a}: {new_a:,} / {label_b}: {new_b:,}",
              C["green"] if new_diff >= 0 else C["orange"])

    _gap(8)

    # ════ 섹션 1: 지역 비교 ═══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["teal"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("🗺️ 구군별 유입 비교", f"{dept} · {label_a} vs {label_b}", C["teal"])

    reg_a = _agg_region(region_rows, ym_a)
    reg_b = _agg_region(region_rows, ym_b)
    all_rg = sorted(set(list(reg_a.keys()) + list(reg_b.keys())))

    if all_rg:
        # 증감 계산
        rg_diff = {r: reg_b.get(r, 0) - reg_a.get(r, 0) for r in all_rg}
        top_inc  = sorted([r for r in all_rg if rg_diff[r] > 0], key=lambda r: -rg_diff[r])[:5]
        top_dec  = sorted([r for r in all_rg if rg_diff[r] < 0], key=lambda r: rg_diff[r])[:5]

        # 비교 막대 차트
        _chart_compare_bar(
            reg_a, reg_b, label_a, label_b,
            [r for r in all_rg if _is_busan(r)],
            f"부산 내 구군별 비교",
            f"da_cmp_rg_busan_{dept}",
            height=max(280, sum(1 for r in all_rg if _is_busan(r)) * 36 + 90),
            horizontal=True,
        )
        # 인사이트
        ins_items = []
        if top_inc:
            ins_items.append((
                "📈 유입 증가 지역 Top5",
                "<br>".join(
                    f"🔴 <b>{_strip_region(r)}</b>  {reg_a.get(r,0):,} → {reg_b.get(r,0):,}명 ({rg_diff[r]:+,})"
                    for r in top_inc
                ),
                C["red"],
            ))
        if top_dec:
            ins_items.append((
                "📉 유입 감소 지역 Top5",
                "<br>".join(
                    f"🔵 <b>{_strip_region(r)}</b>  {reg_a.get(r,0):,} → {reg_b.get(r,0):,}명 ({rg_diff[r]:+,})"
                    for r in top_dec
                ),
                C["blue"],
            ))
        if ins_items:
            _insight_box(ins_items)
    else:
        st.info("지역 데이터 없음")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap(8)

    # ════ 섹션 2: 성별 비교 ══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["violet"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("👤 성별 비교", f"{dept} · {label_a} vs {label_b}", C["violet"])

    if gender_rows:
        gen_a = _agg_gender(gender_rows, ym_a)
        gen_b = _agg_gender(gender_rows, ym_b)
        all_gen = sorted(set(list(gen_a.keys()) + list(gen_b.keys())))
        g1, g2 = st.columns(2, gap="small")
        with g1:
            _chart_gender_pie(gen_a, f"성별 분포 — {label_a}", f"da_gen_pie_a_{dept}")
        with g2:
            _chart_gender_pie(gen_b, f"성별 분포 — {label_b}", f"da_gen_pie_b_{dept}")
        _chart_compare_bar(
            gen_a, gen_b, label_a, label_b, all_gen,
            f"성별 월별 비교",
            f"da_cmp_gen_{dept}",
            height=240,
        )
    elif not has_gender:
        _missing_view_info("V_DEPT_GENDER_MONTHLY")
    else:
        st.info("해당 기간 성별 데이터 없음")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap(8)

    # ════ 섹션 3: 연령대 비교 ═══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📊 연령대 비교", f"{dept} · {label_a} vs {label_b}", C["indigo"])

    if age_rows:
        age_a = _agg_age(age_rows, ym_a)
        age_b = _agg_age(age_rows, ym_b)
        all_ages = [a for a in _AGE_ORDER if a in age_a or a in age_b]
        _chart_compare_bar(
            age_a, age_b, label_a, label_b, all_ages,
            f"연령대별 월별 비교",
            f"da_cmp_age_{dept}",
            height=280,
        )
        # 핵심 연령대
        peak_a = max(age_a, key=age_a.get, default="─") if age_a else "─"
        peak_b = max(age_b, key=age_b.get, default="─") if age_b else "─"
        _insight_box([
            ("🎯 핵심 연령대 (기준월)",
             f"{label_a} 최다 내원 연령대: <b>{peak_a}</b> — {age_a.get(peak_a,0):,}명",
             C["blue"]),
            ("🎯 핵심 연령대 (비교월)",
             f"{label_b} 최다 내원 연령대: <b>{peak_b}</b> — {age_b.get(peak_b,0):,}명",
             C["teal"]),
        ])
    elif not has_age:
        _missing_view_info("V_DEPT_AGE_MONTHLY")
    else:
        st.info("해당 기간 연령대 데이터 없음")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap(8)

    # ════ 섹션 4: 추세 ═══════════════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📈 월별 외래 추세", f"{dept} — 전체 기간", C["blue"])
    if trend_rows:
        _chart_trend_line(trend_rows[-12:], dept, f"da_cmp_trend_{dept}")
    else:
        st.info("추세 데이터 없음 (V_MONTHLY_OPD_DEPT 확인)")
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()


# ────────────────────────────────────────────────────────────────────
# 메인 진입점
# ────────────────────────────────────────────────────────────────────
def render_dept_analysis(monthly_opd_dept: List[Dict]) -> None:
    """
    진료과 분석 탭 렌더링.

    Args:
        monthly_opd_dept: V_MONTHLY_OPD_DEPT 데이터 (기존 로드된 데이터 재사용)
    """
    # ── 진료과 선택 ────────────────────────────────────────────────
    dept_list = _get_dept_list(monthly_opd_dept)
    avail_months = sorted(
        {str(r.get("기준년월", ""))[:6]
         for r in monthly_opd_dept
         if str(r.get("기준년월", ""))[:6].isdigit()},
        reverse=True,
    )

    lbl_col, sel_col, _ = st.columns([1, 3, 6], gap="small", vertical_alignment="center")
    with lbl_col:
        st.markdown(
            f'<div style="font-size:12px;font-weight:700;color:{C["t2"]};'
            f'white-space:nowrap;">🔬 진료과 선택</div>',
            unsafe_allow_html=True,
        )
    with sel_col:
        selected_dept = st.selectbox(
            "진료과", options=dept_list,
            key="da_dept_select",
            label_visibility="collapsed",
        )

    if not selected_dept:
        st.info("분석할 진료과를 선택하세요.")
        return

    # ── 분석 모드 탭 ───────────────────────────────────────────────
    mode_single, mode_compare = st.tabs([
        "📅 단일월 분석",
        "📊 비교월 분석",
    ])

    with mode_single:
        _render_single(selected_dept, avail_months)

    with mode_compare:
        _render_compare(selected_dept, avail_months)
