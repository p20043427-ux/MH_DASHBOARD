"""ui/finance/tab_region.py — 지역별 통계 탭 (Folium 단계구분도)"""

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

# backward-compat aliases (same names used in the original finance_dashboard.py)
_kpi_card      = kpi_card
_sec_hd        = section_header
_gap           = gap
_fmt_won       = fmt_won
_plotly_empty  = empty_state
_PALETTE       = PLOTLY_PALETTE
_PLOTLY_LAYOUT = PLOTLY_CFG

import json
from collections import defaultdict as _ddm

try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False  # type: ignore

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_dept_list_cached(schema: str) -> list:
    """진료과 목록 1시간 캐시 — 탭 전환/리런마다 재조회 방지."""
    try:
        from db.oracle_client import execute_query as _eq_d
        rows = _eq_d(
            f"SELECT DISTINCT 진료과명 FROM {schema}.V_REGION_DEPT_DAILY "
            f"WHERE 진료과명 IS NOT NULL ORDER BY 진료과명",
            max_rows=200,
        ) or []
        return [r["진료과명"] for r in rows if r.get("진료과명")]
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def _load_sigungu_geojson_cached() -> Optional[dict]:
    
    try:
        import requests as _req
        _r = _req.get(
            "https://raw.githubusercontent.com/southkorea/"
            "southkorea-maps/master/kostat/2013/json/skorea_municipalities_geo.json",
            timeout=10,
        )
        _r.raise_for_status()
        return _r.json()
    except Exception as _e:
        logger.warning(f"[GeoJSON] 로드 실패: {_e}")
        return None

    # ❗ 최종 fallback (로컬 파일)
    try:
        with open("data/sigungu.geojson", "r", encoding="utf-8") as f:
            logger.warning("[GeoJSON] 로컬 파일로 fallback")
            return json.load(f)
    except Exception as e:
        logger.error(f"[GeoJSON] 로컬 fallback 실패: {e}")
        return None

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _interpolate_color(t: float, stops: list) -> str:
    for i in range(len(stops) - 1):
        p0, c0 = stops[i];  p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            lt = (t - p0) / (p1 - p0) if p1 > p0 else 0
            r0,g0,b0 = _hex_to_rgb(c0);  r1,g1,b1 = _hex_to_rgb(c1)
            return f"#{int(r0+(r1-r0)*lt):02X}{int(g0+(g1-g0)*lt):02X}{int(b0+(b1-b0)*lt):02X}"
    return stops[-1][1]

# 이 파일의 내용으로 finance_dashboard.py 의 _render_folium_map 함수 전체를 교체하세요.
# (함수 시작 def _render_folium_map( 부터 마지막 st.markdown('</div>') 까지)
# ════════════════════════════════════════════════════════════════════
# 부산 / 경남 구군명 목록 — GeoJSON 코드 기반 필터 대체
# ════════════════════════════════════════════════════════════════════
_BUSAN_DISTRICTS: set = {
    "중구","서구","동구","영도구","부산진구","동래구",
    "남구","북구","해운대구","사하구","금정구","강서구",
    "연제구","수영구","사상구","기장군",
}
_GYEONGNAM_DISTRICTS: set = {
    "창원시","진주시","통영시","사천시","김해시","밀양시",
    "거제시","양산시","의령군","함안군","창녕군","고성군",
    "남해군","하동군","산청군","함양군","거창군","합천군",
}


def _render_folium_map(
    region_data: list,
    sig_cd_prefix: str,          # 사용 안 함(하위 호환 유지용)
    title: str,
    color_main: str,
    color_stops: list,
    center: list,
    zoom_start: int,
    chart_key: str,
    height: int = 440,
    district_set: set = None,    # _BUSAN_DISTRICTS 또는 _GYEONGNAM_DISTRICTS
) -> None:
    """
    Folium 단계구분도 v4 — 구군명 목록 기반 필터링.

    GeoJSON 내부 코드(3738 등 순번)가 행정코드가 아닌 경우에도
    district_set 로 원하는 구군만 정확히 추출합니다.
    """
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {color_main};">',
        unsafe_allow_html=True,
    )
    _sec_hd(title, "클릭 → 팝업(환자수·점유율) · 색상 강도 = 환자수", color_main)

    if not HAS_FOLIUM:
        st.warning("streamlit-folium 미설치: `pip install streamlit-folium folium`")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _raw_geojson = _load_sigungu_geojson_cached()
    if _raw_geojson is None:
        st.error("GeoJSON 로드 실패 — 인터넷 연결 확인")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── 속성 필드 자동 감지 (이름 컬럼)
    _p0 = (_raw_geojson.get("features") or [{}])[0].get("properties", {})
    _name_key = next(
        (k for k in ("SIG_KOR_NM", "name", "NM", "adm_nm", "sggnm") if k in _p0),
        None,
    )
    if not _name_key:
        st.error(f"GeoJSON 이름 필드 감지 실패. 속성: {list(_p0.keys())[:10]}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    def _prop_name(f: dict) -> str:
        return str(f.get("properties", {}).get(_name_key, "") or "").strip()

    # ── district_set 으로 feature 필터
    _target = district_set or _BUSAN_DISTRICTS
    _features = [f for f in _raw_geojson.get("features", [])
                 if _prop_name(f) in _target]

    if not _features:
        st.warning("GeoJSON에서 해당 구군을 찾지 못했습니다.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _geojson = {"type": "FeatureCollection", "features": _features}

    # ── DB 데이터 집계
    _registered = {_prop_name(f) for f in _features}
    _cnt: dict = _ddm(int)
    for _r in region_data:
        _rg  = str(_r.get("지역", "") or "").strip()
        _val = int(_r.get("환자수", 0) or 0)
        if not _rg:
            continue
        _gu = _rg.rsplit(" ", 1)[-1]   # "부산광역시 해운대구" → "해운대구"
        if _gu in _registered:
            _cnt[_gu] += _val

    if not _cnt:
        st.info("해당 진료과·기간의 지역 데이터 없음")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _total     = sum(_cnt.values()) or 1
    _max_v     = max(_cnt.values())
    _sorted_rg = sorted(_cnt.items(), key=lambda x: -x[1])

    # ── Folium 지도
    _m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles="CartoDB positron",
        prefer_canvas=True,
    )

    def _style_fn(feature):
        _t = _cnt.get(_prop_name(feature), 0) / _max_v if _max_v > 0 else 0
        return {
            "fillColor":   _interpolate_color(_t, color_stops),
            "color":       "white",
            "weight":      1.5,
            "fillOpacity": 0.82,
        }

    def _highlight_fn(feature):
        return {"fillColor": color_main, "color": "#334155",
                "weight": 2.5, "fillOpacity": 0.95}

    folium.GeoJson(
        _geojson,
        style_function=_style_fn,
        highlight_function=_highlight_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=[_name_key], aliases=["구군:"],
            style=(
                "background-color:white;color:#0F172A;"
                "font-family:'Malgun Gothic',sans-serif;"
                "font-size:12px;font-weight:700;padding:4px 8px;"
            ),
        ),
    ).add_to(_m)

    for _f in _features:
        _nm   = _prop_name(_f)
        _v    = _cnt.get(_nm, 0)
        _pct  = round(_v / _total * 100, 1)
        _rank = next((i+1 for i,(k,_) in enumerate(_sorted_rg) if k == _nm), "─")
        _popup_html = (
            f'<div style="font-family:Malgun Gothic,sans-serif;min-width:160px;padding:4px;">'
            f'<div style="font-size:14px;font-weight:800;color:{color_main};'
            f'border-bottom:2px solid {color_main};padding-bottom:4px;margin-bottom:8px;">📍 {_nm}</div>'
            f'<table style="width:100%;font-size:12px;">'
            f'<tr><td style="color:#64748B;padding:3px 0;">환자수</td>'
            f'<td style="font-weight:700;text-align:right;">{_v:,}명</td></tr>'
            f'<tr><td style="color:#64748B;padding:3px 0;">점유율</td>'
            f'<td style="font-weight:700;color:{color_main};text-align:right;">{_pct}%</td></tr>'
            f'<tr><td style="color:#64748B;padding:3px 0;">순위</td>'
            f'<td style="font-weight:700;text-align:right;">{_rank}위</td></tr>'
            f'</table>'
            f'<div style="margin-top:6px;height:6px;background:#F1F5F9;border-radius:3px;">'
            f'<div style="width:{_pct}%;height:100%;background:{color_main};border-radius:3px;opacity:0.8;"></div>'
            f'</div></div>'
        )
        folium.GeoJson(
            _f, style_function=_style_fn,
            popup=folium.Popup(folium.IFrame(_popup_html, width=190, height=145), max_width=200),
        ).add_to(_m)

    # 범례
    _legend_html = (
        f'<div style="position:fixed;bottom:20px;right:10px;z-index:1000;'
        f'background:white;padding:10px 14px;border-radius:8px;'
        f'border:1px solid #E2E8F0;box-shadow:0 2px 8px rgba(0,0,0,.12);">'
        f'<div style="font-size:11px;font-weight:700;color:{color_main};margin-bottom:6px;">환자수(명)</div>'
    )
    for _li in range(5):
        _t_val = _li / 4
        _lc = _interpolate_color(_t_val, color_stops)
        _legend_html += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">'
            f'<div style="width:16px;height:12px;background:{_lc};border-radius:2px;"></div>'
            f'<span style="font-size:10px;color:#334155;">{int(_max_v*_t_val):,}</span></div>'
        )
    _legend_html += "</div>"
    _m.get_root().html.add_child(folium.Element(_legend_html))

    st_folium(_m, key=chart_key, height=height, width="stretch", returned_objects=[])

    # 순위 바
    _max_bar = _sorted_rg[0][1] if _sorted_rg else 1
    _medals  = ["🥇","🥈","🥉"]
    _bar_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:5px 16px;'
        'margin-top:8px;padding-top:8px;border-top:1px solid #F1F5F9;">'
    )
    for _i, (_gn, _gc) in enumerate(_sorted_rg[:12]):
        _pct_b = round(_gc / max(_max_bar, 1) * 100)
        _share = round(_gc / _total * 100, 1)
        _md = (_medals[_i] if _i < 3
               else f'<span style="font-size:10px;color:#94A3B8;font-weight:700;">{_i+1}</span>')
        _bar_html += (
            f'<div style="display:flex;align-items:center;gap:5px;min-width:200px;flex:1 0 200px;">'
            f'<div style="width:22px;text-align:center;">{_md}</div>'
            f'<div style="width:52px;font-size:11px;font-weight:600;color:#334155;white-space:nowrap;">{_gn}</div>'
            f'<div style="flex:1;height:8px;background:#F1F5F9;border-radius:4px;overflow:hidden;">'
            f'<div style="width:{_pct_b}%;height:100%;background:{color_main};border-radius:4px;opacity:0.78;"></div></div>'
            f'<div style="width:44px;font-size:11px;font-family:Consolas;font-weight:700;'
            f'color:{color_main};text-align:right;">{_gc:,}</div>'
            f'<div style="width:36px;font-size:10px;color:#94A3B8;text-align:right;">{_share}%</div>'
            f'</div>'
        )
    _bar_html += "</div>"
    st.markdown(_bar_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _tab_region(region_data: List[Dict], region_monthly: List[Dict] = None) -> None:
    """
    지역별 환자 통계 탭 v4.
    데이터는 온디맨드 로드 (세션 캐시) — 페이지 로드 시 쿼리 미실행.
    """
    import datetime as _dt_r
    from collections import defaultdict as _ddr

    # ── rgba 헬퍼 (Plotly는 8자리 hex 미지원 → rgba() 사용) ──────────
    def _c(hex_color: str, a: float = 1.0) -> str:
        h = hex_color.lstrip("#")
        r2, g2, b2 = int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r2},{g2},{b2},{a:.2f})" if a < 1.0 else hex_color

    # ── 온디맨드 데이터 로드 (월 지정 조회) ────────────────────────────
    _SESS_D  = "reg_tab_daily"
    _SESS_M  = "reg_tab_monthly"
    _SESS_YM = "reg_tab_loaded_ym"

    # 최근 24개월 목록 (YYYYMM, 최신순)
    _ym_opts: List[str] = []
    _td2 = _dt_r.date.today()
    for _i in range(24):
        _ab = _td2.year * 12 + (_td2.month - 1) - _i
        _ym_opts.append(f"{_ab // 12}{_ab % 12 + 1:02d}")

    # ── 필터 폼 ────────────────────────────────────────────────────────
    # st.form 사용: 드롭다운 변경 시 리런 없음 → 조회 버튼 클릭 시에만 쿼리 실행
    _PERIOD_MAP = {"한달": 31, "2주일": 14, "1주일": 7}
    _cmp_opts   = ["없음"] + _ym_opts[1:]

    # 진료과 목록: @st.cache_data 1시간 캐시 — 탭 이동·리런마다 재조회 없음
    _dept_opts_row = ["── 진료과를 선택하세요 ──"] + _fetch_dept_list_cached(_SC)

    with st.form("reg_filter_form", border=False):
        _rc1, _rc2, _rc3, _rc4, _rc5, _rc6 = st.columns(
            [3.2, 1.8, 1.8, 1.8, 1.2, 0.8], gap="small", vertical_alignment="bottom"
        )
        with _rc1:
            _sel_dept = st.selectbox(
                "🏥 진료과 선택 *",
                options=_dept_opts_row, index=0,
                key="reg_dept_v3",
                help="분석할 진료과를 선택하세요 (필수)",
            )
        with _rc2:
            _sel_ym = st.selectbox(
                "📅 조회 월",
                options=_ym_opts,
                format_func=lambda x: f"{x[:4]}-{x[4:]}",
                key="reg_ym_sel",
            )
        with _rc3:
            _cmp_raw = st.selectbox(
                "📊 비교 월",
                options=_cmp_opts,
                format_func=lambda x: x if x == "없음" else f"{x[:4]}-{x[4:]}",
                key="reg_cmp_sel",
            )
        with _rc4:
            _period_label = st.selectbox(
                "⏱ 분석 기간",
                options=list(_PERIOD_MAP.keys()),
                key="reg_period_sel",
            )
        with _rc5:
            _do_load = st.form_submit_button(
                "🔍 조회", use_container_width=True, type="primary"
            )
        with _rc6:
            _do_reset = st.form_submit_button("🔄", use_container_width=True, help="초기화")

    _cmp_ym = None if _cmp_raw == "없음" else _cmp_raw
    _loaded_ym = st.session_state.get(_SESS_YM)

    # 초기화
    if _do_reset:
        for _k in (_SESS_D, _SESS_M, _SESS_YM):
            st.session_state.pop(_k, None)
        st.rerun()

    # ── 이전 달 계산 (일별 비교용)
    def _prev_ym_of(ym: str) -> str:
        _y, _m = int(ym[:4]), int(ym[4:])
        _m -= 1
        if _m == 0:
            _m, _y = 12, _y - 1
        return f"{_y}{_m:02d}"
    _prev_ym = _prev_ym_of(_sel_ym)

    # ── 조회 실행 (조회 버튼 클릭 시에만 실행) ───────────────────────────
    if _do_load:
        if _sel_dept == "── 진료과를 선택하세요 ──":
            st.warning("진료과를 먼저 선택한 뒤 조회하세요.")
        else:
            _dept_q = _sel_dept.replace("'", "''")
            with st.spinner(f"{_sel_ym[:4]}-{_sel_ym[4:]} / {_sel_dept} 조회 중…"):
                try:
                    from db.oracle_client import execute_query as _eq
                    _rd = _eq(
                        f"SELECT 기준일자, 진료과명, 지역, 환자수 "
                        f"FROM {_SC}.V_REGION_DEPT_DAILY "
                        f"WHERE (기준일자 LIKE '{_sel_ym}%' OR 기준일자 LIKE '{_prev_ym}%') "
                        f"  AND 진료과명 = '{_dept_q}' "
                        f"ORDER BY 기준일자 DESC, 환자수 DESC",
                        max_rows=50000,
                    ) or []
                    _rm = _eq(
                        f"SELECT 기준월, 진료과명, 지역, 환자수 "
                        f"FROM {_SC}.V_REGION_DEPT_MONTHLY "
                        f"WHERE 진료과명 = '{_dept_q}' "
                        f"ORDER BY 기준월 DESC, 환자수 DESC",
                        max_rows=10000,
                    ) or []
                    st.session_state[_SESS_D]  = _rd
                    st.session_state[_SESS_M]  = _rm
                    st.session_state[_SESS_YM] = _sel_ym
                    st.rerun()
                except Exception as _e:
                    st.error(f"조회 오류: {_e}")
        return

    # 로드 안된 상태 → 안내 화면 표시 후 종료
    if not _loaded_ym or _loaded_ym != _sel_ym:
        _gap()
        if _loaded_ym and _loaded_ym != _sel_ym:
            # 월이 바뀐 경우 — 재조회 안내
            st.markdown(
                f'<div style="background:#FFFBEB;border-left:4px solid #F59E0B;'
                f'border-radius:0 10px 10px 0;padding:14px 20px;margin:8px 0;">'
                f'<span style="font-size:14px;">⚠️</span>'
                f'<span style="font-weight:700;color:#92400E;margin-left:8px;">'
                f'조회 월이 변경됐습니다</span>'
                f'<div style="font-size:12px;color:#B45309;margin-top:4px;">'
                f'<b>{_sel_ym[:4]}-{_sel_ym[4:]}</b> 데이터를 보려면 위의 '
                f'🔍 조회 버튼을 클릭하세요. (현재 로드: {_loaded_ym[:4]}-{_loaded_ym[4:]})</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            # 최초 진입 — 빈 상태 안내
            st.markdown(
                f'<div style="background:linear-gradient(135deg,{C["teal"]}08,{C["green"]}05);'
                f'border:2px dashed {C["teal"]}40;border-radius:16px;'
                f'padding:52px 24px;text-align:center;margin:16px 0;">'
                f'<div style="font-size:44px;margin-bottom:14px;">📍</div>'
                f'<div style="font-size:17px;font-weight:700;color:{C["teal"]};'
                f'margin-bottom:8px;">지역별 환자 통계</div>'
                f'<div style="font-size:13px;color:{C["t2"]};line-height:1.9;'
                f'margin-bottom:20px;">'
                f'진료과별 환자 주소지 분포 · 일별 유입 추이 · 지역 비교 분석<br>'
                f'<b style="color:{C["t1"]};">① 진료과 선택</b> → '
                f'<b style="color:{C["t1"]};">② 조회 월 확인</b> → '
                f'<b style="color:{C["t1"]};">③ 🔍 조회</b> 순서로 진행하세요.</div>'
                f'<div style="display:inline-flex;align-items:center;gap:8px;'
                f'background:{C["teal"]}12;border-radius:8px;padding:10px 18px;">'
                f'<span style="font-size:12px;color:{C["t3"]};">데이터 소스 ·</span>'
                f'<code style="font-size:11px;color:{C["teal"]};">V_REGION_DEPT_DAILY</code>'
                f'<span style="font-size:12px;color:{C["t3"]};">·</span>'
                f'<code style="font-size:11px;color:{C["teal"]};">V_REGION_DEPT_MONTHLY</code>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        return

    # 세션 캐시에서 데이터 가져오기
    region_data    = st.session_state.get(_SESS_D, []) or []
    region_monthly = st.session_state.get(_SESS_M, []) or []
 
    # ── 배너 (조회된 월 표시)
    _loaded_label = f"{_loaded_ym[:4]}-{_loaded_ym[4:]}" if _loaded_ym else ""
    st.markdown(
        f'<div style="background:linear-gradient(90deg,{C["teal"]}15,{C["green"]}10);'
        f'border-left:4px solid {C["teal"]};border-radius:0 8px 8px 0;'
        f'padding:8px 16px;margin:4px 0 6px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:16px;">📍</span>'
        f'<div style="flex:1;"><div style="font-size:12px;font-weight:700;color:{C["teal"]};">'
        f'지역별 환자 통계 · {_loaded_label}</div>'
        f'<div style="font-size:11px;color:{C["t3"]};margin-top:1px;">'
        f'진료과별 환자 주소지 분포 · 일별 유입 추이 · AI 경영 인사이트</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
 
    # ── VIEW 없음 안내
    if not region_data:
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;'
            f'padding:24px;text-align:center;margin-top:12px;">'
            f'<div style="font-size:32px;margin-bottom:8px;">📋</div>'
            f'<div style="font-size:14px;font-weight:700;color:#92400E;">'
            f'V_REGION_DEPT_DAILY 데이터 없음</div>'
            f'<div style="font-size:12px;color:#B45309;margin-top:6px;line-height:1.8;">'
            f'<b>region_views_daily.sql</b> 을 DBeaver(DBA 계정)에서 실행 후 재시작<br>'
            f'컬럼: 기준일자(YYYYMMDD) / 진료과명 / 지역 / 환자수'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        return
 
    # ── 진료과 목록 구성 (총 환자수 내림차순)
    _dept_total: dict = _ddr(int)
    for _r in region_data:
        _dp  = _r.get("진료과명", "")
        _cnt = int(_r.get("환자수", 0) or 0)
        if _dp:
            _dept_total[_dp] += _cnt
    _all_depts = sorted(_dept_total.keys(), key=lambda d: -_dept_total[d])
 
    # ── 오늘 날짜
    _today = _dt_r.date.today()
 
    # ── 기간·날짜 파생값 (진료과 선택은 상단 통합 컨트롤 행)
    _n_days     = _PERIOD_MAP[_period_label]
    _date_start = f"{_sel_ym}01"
    _date_end   = f"{_sel_ym}{min(_n_days, 31):02d}"
 
    # ── 미선택 상태 → 진료과 목록 안내
    _is_dept_selected = _sel_dept != "── 진료과를 선택하세요 ──"
 
    if not _is_dept_selected:
        _gap()
        st.markdown(
            f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;'
            f'padding:16px 20px;text-align:center;margin-bottom:12px;">'
            f'<div style="font-size:14px;font-weight:700;color:{C["blue"]};margin-bottom:4px;">'
            f'👆 위에서 진료과를 선택하면 분석이 시작됩니다</div>'
            f'<div style="font-size:11px;color:{C["t3"]};">'
            f'{_sel_ym[:4]}-{_sel_ym[4:]} {_period_label} 기준 / 진료과를 선택하면 상세 분석이 시작됩니다</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
 
        # ── 진료과 환자수 순위 요약 (전체 30일 기준)
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd("🏥 진료과별 환자수 순위", "최근 30일 전체 기준 — 선택 진료과 참고용", C["blue"])
        _TH_D = (
            "padding:6px 10px;font-size:11px;font-weight:700;color:#64748B;"
            "border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        )
        _dept_table = (
            '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
            f'<thead><tr>'
            f'<th style="{_TH_D}text-align:center;width:40px;">순위</th>'
            f'<th style="{_TH_D}text-align:left;">진료과</th>'
            f'<th style="{_TH_D}text-align:right;color:{C["blue"]};">환자수(30일)</th>'
            f'<th style="{_TH_D}">비율</th>'
            f'</tr></thead><tbody>'
        )
        _total_all = sum(_dept_total.values()) or 1
        for _ri, _dp in enumerate(_all_depts[:20], 1):
            _dc = _dept_total.get(_dp, 0)
            _dp_pct = round(_dc / _total_all * 100, 1)
            _rbg    = "#F8FAFC" if _ri % 2 == 0 else "#FFFFFF"
            _td_s   = f"padding:6px 10px;background:{_rbg};border-bottom:1px solid #F1F5F9;font-size:12px;"
            _dept_table += (
                f"<tr>"
                f'<td style="{_td_s}text-align:center;font-weight:700;color:{C["t3"]};">{_ri}</td>'
                f'<td style="{_td_s}font-weight:600;color:{C["t1"]};">{_dp}</td>'
                f'<td style="{_td_s}text-align:right;font-family:Consolas;color:{C["blue"]};font-weight:700;">{_dc:,}</td>'
                f'<td style="{_td_s}"><div style="display:flex;align-items:center;gap:6px;">'
                f'<div style="flex:1;height:6px;background:#F1F5F9;border-radius:3px;overflow:hidden;">'
                f'<div style="width:{_dp_pct}%;height:100%;background:{C["blue"]};border-radius:3px;"></div>'
                f'</div><span style="font-size:10px;color:{C["t3"]};min-width:34px;">{_dp_pct}%</span>'
                f'</div></td>'
                f"</tr>"
            )
        st.markdown(_dept_table + "</tbody></table>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return  # ← 미선택 시 이후 분석 렌더링 중단
 
    # ════════════════════════════════════════════════════════════════
    # 이하: 진료과 선택 완료 상태
    # ════════════════════════════════════════════════════════════════
 
    # ── 기간 및 진료과 필터 (조회월 기준)
    _filtered_data = [
        _r for _r in region_data
        if _r.get("진료과명", "") == _sel_dept
        and _date_start <= str(_r.get("기준일자", "")) <= _date_end
    ]
 
    # ── 지역 집계 (지역미상 분리)
    _region_total: dict = _ddr(int)
    _unknown_total: int = 0
    for _r in _filtered_data:
        _rg  = _r.get("지역", "")
        _cnt = int(_r.get("환자수", 0) or 0)
        if _rg in ("지역미상", "", None):
            _unknown_total += _cnt
        else:
            _region_total[_rg] += _cnt
 
    _total_patients  = sum(_region_total.values()) + _unknown_total
    _known_total     = sum(_region_total.values())
    _unique_regions  = len(_region_total)
    _sorted_regions  = sorted(_region_total.items(), key=lambda x: -x[1])
    _top1_region     = _sorted_regions[0][0] if _sorted_regions else "─"
    _top1_cnt        = _sorted_regions[0][1] if _sorted_regions else 0
    _top1_dependency = round(_top1_cnt / max(_known_total, 1) * 100, 1)
 
    # ── KPI 4개
    _gap()
    _dep_color = C["red"] if _top1_dependency >= 60 else C["yellow"] if _top1_dependency >= 40 else C["green"]
    _kk1, _kk2, _kk3, _kk4 = st.columns(4, gap="small")
    _kpi_card(_kk1, "👥", f"총 환자수 ({_period_label})",
              f"{_total_patients:,}", "명",
              f"지역미상 {_unknown_total:,}명 포함", C["teal"])
    _kpi_card(_kk2, "📍", "유입 지역 수",
              f"{_unique_regions:,}", "개 시구", "지역미상 제외 기준", C["green"])
    _kk3.markdown(
        f'<div class="fn-kpi" style="border-top:3px solid {_dep_color};">'
        f'<div class="fn-kpi-icon">🏆</div>'
        f'<div class="fn-kpi-label">1위 지역</div>'
        f'<div style="font-size:15px;font-weight:800;color:{_dep_color};line-height:1.3;margin:2px 0;">'
        f'{_top1_region[:10] if len(_top1_region) > 10 else _top1_region}</div>'
        f'<div style="font-size:11px;color:{C["t3"]};">{_top1_cnt:,}명</div>'
        f'<div class="goal-bar-wrap"><div class="goal-bar-fill" '
        f'style="width:{_top1_dependency}%;background:{_dep_color};"></div></div>'
        f'<div style="font-size:10px;color:{_dep_color};font-weight:700;">'
        f'점유율 {_top1_dependency}% '
        f'{"⚠️ 의존도 높음" if _top1_dependency >= 60 else "주의" if _top1_dependency >= 40 else "✅ 양호"}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    _kpi_card(_kk4, "📅", "분석 기간",
              _period_label, "",
              f"{_sel_ym[:4]}-{_sel_ym[4:]}  {_date_start[6:]}일~{_date_end[6:]}일", C["indigo"])
    _gap()
 
    # ── 지역미상 경고
    if _unknown_total > 0:
        _unk_pct = round(_unknown_total / max(_total_patients, 1) * 100, 1)
        _unk_c   = C["red"] if _unk_pct >= 20 else C["yellow"]
        st.markdown(
            f'<div style="background:{_unk_c}18;border:1px solid {_unk_c}55;border-radius:8px;'
            f'padding:8px 14px;margin-bottom:8px;display:flex;align-items:center;gap:10px;">'
            f'<span>⚠️</span>'
            f'<span style="font-size:12px;font-weight:700;color:{_unk_c};">'
            f'지역미상 {_unknown_total:,}명 ({_unk_pct}%) — 우편번호 미기재 또는 POSTNO 미매핑</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
 
    # ══════════════════════════════════════
    # [섹션1] 좌: 지역 수평 바 TOP15  |  우: 일별 트렌드 라인
    # ══════════════════════════════════════
    _col_bar, _col_line = st.columns([1, 1], gap="small")
 
    with _col_bar:
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"📊 {_sel_dept} — 지역별 환자 순위 TOP15",
                f"{_period_label} 합산", C["blue"])
        if _sorted_regions and HAS_PLOTLY:
            _top15     = _sorted_regions[:15]
            _rg_lbls   = [r for r, _ in _top15]
            _rg_vals   = [v for _, v in _top15]
            _max_v     = _rg_vals[0] if _rg_vals else 1
            _bar_clrs  = [
                f"rgba(8,145,178,{0.30 + 0.70 * (v / _max_v):.2f})"
                for v in _rg_vals
            ]
            _fig_bar = go.Figure(go.Bar(
                x=_rg_vals, y=_rg_lbls,
                orientation="h",
                marker=dict(color=_bar_clrs, line=dict(color=C["teal"], width=0.5)),
                text=[f"{v:,}명 ({round(v/max(_known_total,1)*100,1)}%)" for v in _rg_vals],
                textposition="outside",
                textfont=dict(size=10, color=C["t2"]),
                hovertemplate="<b>%{y}</b><br>%{x:,}명<extra></extra>",
            ))
            _fig_bar.update_layout(
                **_PLOTLY_LAYOUT,
                height=max(300, len(_top15) * 26 + 60),
                margin=dict(l=0, r=100, t=8, b=8),
                showlegend=False, bargap=0.3,
            )
            _fig_bar.update_xaxes(showticklabels=False, showgrid=False)
            _fig_bar.update_yaxes(tickfont=dict(size=10), autorange="reversed")
            st.plotly_chart(_fig_bar, use_container_width=True, key="reg_v3_hbar")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)
 
    with _col_line:
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["green"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"📈 {_sel_dept} — 상위 5개 지역 일별 추이",
                f"{_period_label} 일별 환자수", C["green"])
        # 일별 × 지역 집계
        _day_rg_map: dict = _ddr(lambda: _ddr(int))
        for _r in _filtered_data:
            _dj  = str(_r.get("기준일자", ""))
            _rg  = _r.get("지역", "")
            _cnt = int(_r.get("환자수", 0) or 0)
            if _dj and _rg not in ("지역미상", "", None):
                _day_rg_map[_dj][_rg] += _cnt
 
        _all_days_sorted = sorted(_day_rg_map.keys())
        _top5_rg         = [r for r, _ in _sorted_regions[:5]]
 
        # 날짜 레이블: 간략하게 (MM/DD)
        def _fmt_day(d: str) -> str:
            return f"{d[4:6]}/{d[6:8]}" if len(d) == 8 else d
 
        if _top5_rg and _all_days_sorted and HAS_PLOTLY:
            _fig_line = go.Figure()
            for _li, _rg_l in enumerate(_top5_rg):
                _y_vals = [_day_rg_map.get(_dj, {}).get(_rg_l, 0) for _dj in _all_days_sorted]
                _fig_line.add_trace(go.Scatter(
                    x=[_fmt_day(_dj) for _dj in _all_days_sorted],
                    y=_y_vals, name=_rg_l,
                    mode="lines+markers",
                    line=dict(color=_PALETTE[_li % len(_PALETTE)], width=2.5),
                    marker=dict(size=6, color=_PALETTE[_li % len(_PALETTE)],
                                line=dict(color="#fff", width=1.5)),
                    hovertemplate=f"<b>{_rg_l}</b><br>%{{x}}: %{{y:,}}명<extra></extra>",
                ))
            _fig_line.update_layout(
                **_PLOTLY_LAYOUT, height=300,
                margin=dict(l=0, r=0, t=30, b=8),
                legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center",
                            font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified",
            )
            _fig_line.update_xaxes(tickfont=dict(size=10),
                                   tickangle=-30 if _n_days >= 14 else 0)
            _fig_line.update_yaxes(title_text="환자수(명)",
                                   title_font=dict(size=10, color=C["t3"]))
            st.plotly_chart(_fig_line, use_container_width=True, key="reg_v3_line")
        else:
            _plotly_empty()
        st.markdown("</div>", unsafe_allow_html=True)
 
    _gap()
 
    # ══════════════════════════════════════
    # [섹션2] 지역×날짜 히트맵 (2주일/한달일 때만 표시)
    # ══════════════════════════════════════
    _top10_rg_hm = [r for r, _ in _sorted_regions[:10]]
    if _n_days >= 14 and _top10_rg_hm and _all_days_sorted and HAS_PLOTLY:
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"🗓️ {_sel_dept} — 지역 × 날짜 히트맵",
                f"상위 10개 지역 · {_period_label}", C["indigo"])
        _hm_map2 = {
            (_rg, _dj): _day_rg_map.get(_dj, {}).get(_rg, 0)
            for _rg in _top10_rg_hm
            for _dj in _all_days_sorted
        }
        _z_hm2 = [
            [_hm_map2.get((_rg, _dj), 0) for _dj in _all_days_sorted]
            for _rg in _top10_rg_hm
        ]
        _x_lbl2 = [_fmt_day(_dj) for _dj in _all_days_sorted]
        _fig_hm3 = go.Figure(go.Heatmap(
            z=_z_hm2, x=_x_lbl2, y=_top10_rg_hm,
            colorscale=[[0.0, "#EEF2FF"], [0.5, "#6366F1"], [1.0, "#3730A3"]],
            text=[[str(v) if v > 0 else "" for v in row] for row in _z_hm2],
            texttemplate="%{text}", textfont=dict(size=9, color="#fff"),
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:,}명<extra></extra>",
            showscale=True, xgap=2, ygap=2,
            colorbar=dict(title="환자수", thickness=12, len=0.8),
        ))
        _hm3_h = max(250, len(_top10_rg_hm) * 26 + 70)
        _fig_hm3.update_layout(
            **_PLOTLY_LAYOUT, height=_hm3_h,
            margin=dict(l=0, r=60, t=8, b=8),
        )
        _fig_hm3.update_xaxes(side="top", tickfont=dict(size=9), tickangle=-45)
        _fig_hm3.update_yaxes(tickfont=dict(size=10), autorange="reversed")
        st.plotly_chart(_fig_hm3, use_container_width=True, key="reg_v3_heatmap")
        st.markdown("</div>", unsafe_allow_html=True)
        _gap()
 
    # ══════════════════════════════════════
    # [섹션3] TOP5 지역 카드 + MoM(전주/전기간) 증감
    # ══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["teal"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd(f"🏆 {_sel_dept} — 상위 지역 TOP 5",
            f"{_period_label} · 전기간 대비 증감", C["teal"])
 
    # 비교 기간 (전달 동일 기간)
    _prev_start_d = f"{_prev_ym}01"
    _prev_end_d   = f"{_prev_ym}{_date_end[6:]}"   # 전달의 동일 일자까지

    _prev_data = [
        _r for _r in region_data
        if _r.get("진료과명", "") == _sel_dept
        and _prev_start_d <= str(_r.get("기준일자", "")) <= _prev_end_d
    ]
    _prev_region: dict = _ddr(int)
    for _r in _prev_data:
        _rg = _r.get("지역", "")
        if _rg not in ("지역미상", "", None):
            _prev_region[_rg] += int(_r.get("환자수", 0) or 0)
 
    if _sorted_regions:
        _top5_cols = st.columns(5, gap="small")
        for _ti, (_rg_t, _rc_t) in enumerate(_sorted_regions[:5]):
            _prev_cnt = _prev_region.get(_rg_t, 0)
            _diff_t   = _rc_t - _prev_cnt
            _chg_t    = (
                f"{round(_diff_t / _prev_cnt * 100, 1):+.1f}%"
                if _prev_cnt > 0 else "신규"
            )
            _arrow_t  = "▲" if _diff_t > 0 else "▼" if _diff_t < 0 else "─"
            _dc_t     = C["red"] if _diff_t > 0 else C["blue"] if _diff_t < 0 else C["t3"]
            _pct_t    = round(_rc_t / max(_known_total, 1) * 100, 1)
            _bar_w_t  = round(_rc_t / max(_sorted_regions[0][1], 1) * 100)
            _medals_t = ["🥇", "🥈", "🥉", "④", "⑤"]
            _col_t    = _PALETTE[_ti % len(_PALETTE)]
 
            with _top5_cols[_ti]:
                st.markdown(
                    f'<div style="background:#fff;border:1px solid #F0F4F8;'
                    f'border-top:3px solid {_col_t};border-radius:10px;'
                    f'padding:12px 10px;text-align:center;">'
                    f'<div style="font-size:18px;">{_medals_t[_ti]}</div>'
                    f'<div style="font-size:11px;font-weight:800;color:{_col_t};'
                    f'margin:4px 0;line-height:1.3;word-break:keep-all;">{_rg_t}</div>'
                    f'<div style="font-size:20px;font-weight:800;color:{C["t1"]};">'
                    f'{_rc_t:,}<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
                    f'<div style="font-size:10px;color:{C["t3"]};margin-top:2px;">'
                    f'점유율 {_pct_t}%</div>'
                    f'<div style="height:4px;background:#F1F5F9;border-radius:2px;'
                    f'margin:6px 0;overflow:hidden;">'
                    f'<div style="width:{_bar_w_t}%;height:100%;background:{_col_t};'
                    f'border-radius:2px;"></div></div>'
                    f'<div style="font-size:11px;font-weight:700;color:{_dc_t};">'
                    f'{_arrow_t} {_chg_t}</div>'
                    f'<div style="font-size:9.5px;color:{C["t4"]};">전기간 대비</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        _plotly_empty()
 
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()
 
    # ══════════════════════════════════════
    # [섹션4] 정적 경영 인사이트 요약
    # (AI채팅 제거 — 하단 공통 채팅 사용)
    # ══════════════════════════════════════
    st.markdown(
        f'<div class="wd-card" style="border-top:3px solid {C["violet"]};">',
        unsafe_allow_html=True,
    )
    _sec_hd("📋 경영 인사이트 자동 요약",
            f"{_sel_dept} · {_period_label} 데이터 기준", C["violet"])
 
    # 의존도 진단
    _dep_level = "🔴 위험" if _top1_dependency >= 60 else "🟡 주의" if _top1_dependency >= 40 else "🟢 양호"
    _dep_msg   = (
        f"1위 지역 <b>{_top1_region}</b> 점유율 <b>{_top1_dependency}%</b> — {_dep_level}<br>"
        f"{'⚠️ 특정 지역 집중도가 높습니다. 인근 지역 홍보 강화가 필요합니다.' if _top1_dependency >= 40 else '✅ 지역 분산이 양호합니다.'}"
    )
 
    # 데이터 품질
    _unk_pct = round(_unknown_total / max(_total_patients, 1) * 100, 1)
    _unk_level = "🔴 불량" if _unk_pct >= 30 else "🟡 주의" if _unk_pct >= 10 else "🟢 양호"
    _unk_msg   = (
        f"지역미상 <b>{_unknown_total:,}명 ({_unk_pct}%)</b> — {_unk_level}<br>"
        f"{'📋 접수 시 주소 입력 강화가 필요합니다.' if _unk_pct >= 10 else '✅ 주소 데이터 품질이 양호합니다.'}"
    )
 
    # 전기간 대비 이상징후 (TOP15 지역 중 ±30% 이상)
    _anomaly_msgs = []
    for _rg_a, _cv_a in _sorted_regions[:15]:
        _pv_a = _prev_region.get(_rg_a, 0)
        if _pv_a >= 3:
            _chg_a = (_cv_a - _pv_a) / _pv_a * 100
            if abs(_chg_a) >= 30:
                _icon_a = "🔴" if _chg_a > 0 else "🔵"
                _anomaly_msgs.append(
                    f"{_icon_a} <b>{_rg_a}</b> {_chg_a:+.1f}% "
                    f"({_pv_a:,} → {_cv_a:,}명)"
                )
    _anom_msg = (
        "<br>".join(_anomaly_msgs[:3])
        if _anomaly_msgs
        else "✅ 전기간 대비 급격한 변동 지역 없음"
    )
 
    # TOP3 지역
    _top3_str = " > ".join(
        f"<b>{r}</b> {c:,}명" for r, c in _sorted_regions[:3]
    ) if _sorted_regions else "─"
 
    _ins_items = [
        ("📍 지역 의존도 진단", _dep_msg,  C["blue"]),
        ("🗂️ 데이터 품질",     _unk_msg,  C["orange"]),
        ("🚨 이상징후 탐지",   _anom_msg, C["red"] if _anomaly_msgs else C["green"]),
        ("🏆 상위 3개 지역",   _top3_str, C["teal"]),
    ]
    _ins_cols = st.columns(2, gap="small")
    for _ii2, (_ins_title, _ins_body, _ins_color) in enumerate(_ins_items):
        with _ins_cols[_ii2 % 2]:
            st.markdown(
                f'<div style="background:#fff;border:1px solid #F0F4F8;'
                f'border-left:4px solid {_ins_color};border-radius:8px;'
                f'padding:12px 14px;margin-bottom:8px;">'
                f'<div style="font-size:11.5px;font-weight:700;color:{_ins_color};margin-bottom:6px;">'
                f'{_ins_title}</div>'
                f'<div style="font-size:12px;color:{C["t2"]};line-height:1.6;">'
                f'{_ins_body}</div></div>',
                unsafe_allow_html=True,
            )
 
    st.markdown(
        f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;'
        f'padding:9px 14px;margin-top:4px;display:flex;align-items:center;gap:8px;">'
        f'<span style="font-size:14px;">🤖</span>'
        f'<span style="font-size:12px;color:{C["blue"]};font-weight:600;">'
        f'AI 심층 분석은 하단 채팅창에서 "{_sel_dept} 지역 분석해줘" 등으로 질문하세요'
        f'</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    _gap()
    
    # ══════════════════════════════════════════════
    # [섹션5] 부산/경남 지역 버블맵
    # ══════════════════════════════════════════════
    _gap(12)
    _map_c1, _map_c2 = st.columns([1, 1], gap="small")
    with _map_c1:
        _render_folium_map(
            region_data=_filtered_data,
            sig_cd_prefix="26",            # 하위호환 유지
            title="🗺️ 부산 구군별 환자 분포",
            color_main=C["blue"],
            color_stops=[(0.0,"#EFF6FF"),(0.2,"#BAE6FD"),(0.5,"#3B82F6"),(0.8,"#1D4ED8"),(1.0,"#0C2D48")],
            center=[35.12, 129.04],        # ← 부산 중심 조정
            zoom_start=11,
            chart_key=f"folium_busan_{_sel_dept}_{_n_days}",
            district_set=_BUSAN_DISTRICTS, # ← 추가
        )
    with _map_c2:
        _render_folium_map(
            region_data=_filtered_data,
            sig_cd_prefix="48",
            title="🗺️ 경상남도 시군별 환자 분포",
            color_main=C["green"],
            color_stops=[(0.0,"#F0FDF4"),(0.2,"#BBF7D0"),(0.5,"#34D399"),(0.8,"#059669"),(1.0,"#064E3B")],
            center=[35.40, 128.10],        # ← 경남 중심 조정
            zoom_start=8,                  # ← 9 → 8 (경남 전체 보이게)
            chart_key=f"folium_gyeongnam_{_sel_dept}_{_n_days}",
            district_set=_GYEONGNAM_DISTRICTS, # ← 추가
        )
    _gap()

    # ══════════════════════════════════════════════════════════════════════
    # [섹션6] 지정월 전년도 대비 지역 비교 트리맵 (V_REGION_DEPT_MONTHLY)
    # ══════════════════════════════════════════════════════════════════════
    _rm = region_monthly or []
    _rm_dept = [r for r in _rm if r.get("진료과명", "") == _sel_dept]

    # YYYYMM → {지역: 환자수}
    _mo_lookup: dict = {}
    for _r5 in _rm_dept:
        _ym5 = str(_r5.get("기준월", ""))
        _rg5 = _r5.get("지역", "")
        _cnt5 = int(_r5.get("환자수", 0) or 0)
        if not _ym5 or not _rg5 or _rg5 == "지역미상":
            continue
        if _ym5 not in _mo_lookup:
            _mo_lookup[_ym5] = {}
        _mo_lookup[_ym5][_rg5] = _mo_lookup[_ym5].get(_rg5, 0) + _cnt5

    _mo_months = sorted(_mo_lookup.keys())

    # 전년도 대비: 위에서 선택한 조회월 기준 자동 설정
    _yoy_cur = _sel_ym
    _yoy_prv = str(int(_yoy_cur) - 100)
    _yoy_available = _yoy_cur in _mo_lookup and _yoy_prv in _mo_lookup

    if _yoy_available:
        _gap()
        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(
            f"📊 {_sel_dept} — {_yoy_cur[:4]}년 {_yoy_cur[4:]}월 vs 전년 동월 지역 비교",
            "V_REGION_DEPT_MONTHLY · DISTINCT 환자수 기준 · 부산·경남 상세",
            C["indigo"],
        )

        _cur_d = _mo_lookup.get(_yoy_cur, {})
        _prv_d = _mo_lookup.get(_yoy_prv, {})
        _all_rgs_y = sorted(set(list(_cur_d.keys()) + list(_prv_d.keys())))

        def _yoy_color(pct):
            if pct is None:
                return "#CBD5E1"
            elif pct >= 15:
                return "#1D4ED8"
            elif pct >= 5:
                return "#93C5FD"
            elif pct >= -5:
                return "#E2E8F0"
            elif pct >= -15:
                return "#FCA5A5"
            else:
                return "#DC2626"

        # 시도 레벨 집계
        _sido_agg: dict = {}
        for _rg6 in _all_rgs_y:
            _sido = _rg6.split(" ")[0] if " " in _rg6 else _rg6
            if _sido not in _sido_agg:
                _sido_agg[_sido] = {"cur": 0, "prv": 0}
            _sido_agg[_sido]["cur"] += _cur_d.get(_rg6, 0)
            _sido_agg[_sido]["prv"] += _prv_d.get(_rg6, 0)

        # 전국 YoY KPI
        _tot_cur_y = sum(v["cur"] for v in _sido_agg.values())
        _tot_prv_y = sum(v["prv"] for v in _sido_agg.values())
        _tot_diff_y = _tot_cur_y - _tot_prv_y
        _tot_pct_y = round(_tot_diff_y / max(_tot_prv_y, 1) * 100, 1)
        _yoy_cur_label = f"{_yoy_cur[:4]}년 {_yoy_cur[4:]}월"
        _yoy_prv_label = f"{_yoy_prv[:4]}년 {_yoy_prv[4:]}월"

        _ky1, _ky2, _ky3 = st.columns(3, gap="small")
        _kpi_card(_ky1, "📅", _yoy_cur_label, f"{_tot_cur_y:,}", "명",
                  "기준월 전체 환자수", C["indigo"])
        _kpi_card(_ky2, "📅", _yoy_prv_label, f"{_tot_prv_y:,}", "명",
                  "전년 동월 환자수", C["t2"])
        _ky3.markdown(
            f'<div class="fn-kpi" style="border-top:3px solid '
            f'{C["red"] if _tot_diff_y >= 0 else C["blue"]};">'
            f'<div class="fn-kpi-icon">{"📈" if _tot_diff_y >= 0 else "📉"}</div>'
            f'<div class="fn-kpi-label">전년 대비</div>'
            f'<div style="font-size:18px;font-weight:800;color:'
            f'{C["red"] if _tot_diff_y >= 0 else C["blue"]};">'
            f'{"▲" if _tot_diff_y > 0 else "▼"}&nbsp;{abs(_tot_diff_y):,}'
            f'<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
            f'<div style="font-size:11px;font-weight:700;color:'
            f'{C["red"] if _tot_diff_y >= 0 else C["blue"]};">'
            f'{_tot_pct_y:+.1f}%</div></div>',
            unsafe_allow_html=True,
        )
        _gap()

        # ── 전국 시도 트리맵
        if HAS_PLOTLY and _sido_agg:
            _tm_labels = ["전국"]
            _tm_parents = [""]
            _tm_values = [_tot_cur_y]
            _tm_colors = ["#F1F5F9"]
            _tm_custom = [[None, _tot_cur_y, _tot_prv_y, "전국"]]

            _sido_labels = {
                "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
                "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
                "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
                "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
                "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
                "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
            }
            for _sido, _sv in sorted(_sido_agg.items(),
                                     key=lambda x: -x[1]["cur"]):
                _sc = _sv["cur"]
                _sp = _sv["prv"]
                _spct = round((_sc - _sp) / max(_sp, 1) * 100, 1) if _sp > 0 else None
                _lbl = _sido_labels.get(_sido, _sido)
                _tm_labels.append(_lbl)
                _tm_parents.append("전국")
                _tm_values.append(_sc)
                _tm_colors.append(_yoy_color(_spct))
                _tm_custom.append([_spct, _sc, _sp, _sido])

            _fig_tm = go.Figure(go.Treemap(
                labels=_tm_labels,
                parents=_tm_parents,
                values=_tm_values,
                marker=dict(colors=_tm_colors, line=dict(width=1.5, color="#fff")),
                texttemplate=(
                    "<b>%{label}</b><br>"
                    "<span style='font-size:11px'>%{customdata[0]:+.1f}%</span>"
                ),
                customdata=_tm_custom,
                hovertemplate=(
                    "<b>%{customdata[3]}</b><br>"
                    "전년 대비: <b>%{customdata[0]:+.1f}%</b><br>"
                    f"{_yoy_cur_label}: %{{customdata[1]:,}}명<br>"
                    f"{_yoy_prv_label}: %{{customdata[2]:,}}명"
                    "<extra></extra>"
                ),
                textfont=dict(size=13),
                pathbar=dict(visible=False),
                root_color="#F8FAFC",
            ))
            _fig_tm.update_layout(
                **_PLOTLY_LAYOUT, height=340,
                margin=dict(l=0, r=0, t=8, b=0),
            )
            st.plotly_chart(_fig_tm, use_container_width=True,
                            key=f"reg_yoy_tm_{_sel_dept}_{_yoy_cur}")

            # ── 범례
            _legend_items = [
                ("#1D4ED8", "+15%↑ 강한 증가"),
                ("#93C5FD", "+5~15%"),
                ("#E2E8F0", "±5% 보합"),
                ("#FCA5A5", "-5~-15%"),
                ("#DC2626", "-15%↓ 강한 감소"),
            ]
            _leg_html = (
                '<div style="display:flex;gap:14px;justify-content:center;'
                'padding:6px 0 10px;flex-wrap:wrap;">'
            )
            for _lc, _lt in _legend_items:
                _leg_html += (
                    f'<div style="display:flex;align-items:center;gap:5px;">'
                    f'<div style="width:14px;height:14px;border-radius:3px;'
                    f'background:{_lc};"></div>'
                    f'<span style="font-size:11px;color:{C["t2"]};">{_lt}</span>'
                    f'</div>'
                )
            st.markdown(_leg_html + "</div>", unsafe_allow_html=True)

        _gap()

        # ── 부산 구별 + 경남 시군별 상세 YoY 바 차트
        _yoy_row = []
        for _rg6 in _all_rgs_y:
            _c6 = _cur_d.get(_rg6, 0)
            _p6 = _prv_d.get(_rg6, 0)
            _pct6 = round((_c6 - _p6) / max(_p6, 1) * 100, 1) if _p6 > 0 else None
            _yoy_row.append({"지역": _rg6, "cur": _c6, "prv": _p6, "pct": _pct6})

        _busan_yoy = sorted(
            [r for r in _yoy_row if r["지역"].startswith("부산")],
            key=lambda x: -x["cur"],
        )
        _gynam_yoy = sorted(
            [r for r in _yoy_row if r["지역"].startswith("경상남도")],
            key=lambda x: -x["cur"],
        )

        def _detail_yoy_chart(rows, title, color_up, color_dn, chart_key):
            if not rows or not HAS_PLOTLY:
                return
            _lbl7 = [r["지역"].split(" ", 1)[-1] if " " in r["지역"] else r["지역"]
                     for r in rows]
            _cur7 = [r["cur"] for r in rows]
            _prv7 = [r["prv"] for r in rows]
            _pct7 = [r["pct"] for r in rows]
            _clr7 = [
                color_up if (p is not None and p >= 0) else color_dn
                for p in _pct7
            ]
            _pct_txt = [
                f"{p:+.1f}%" if p is not None else "신규" for p in _pct7
            ]

            _fig7 = go.Figure()
            _fig7.add_trace(go.Bar(
                name=_yoy_prv_label, x=_lbl7, y=_prv7,
                marker_color=_c(C["t3"], 0.53),
                hovertemplate="<b>%{x}</b><br>전년: %{y:,}명<extra></extra>",
            ))
            _fig7.add_trace(go.Bar(
                name=_yoy_cur_label, x=_lbl7, y=_cur7,
                marker_color=_clr7,
                text=_pct_txt,
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate="<b>%{x}</b><br>현년: %{y:,}명<extra></extra>",
            ))
            _fig7.update_layout(
                **_PLOTLY_LAYOUT,
                height=300,
                margin=dict(l=0, r=0, t=30, b=8),
                barmode="group",
                bargap=0.15,
                bargroupgap=0.05,
                legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center",
                            font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                title=dict(text=title, font=dict(size=13, color=C["t1"]), x=0),
            )
            _fig7.update_xaxes(tickfont=dict(size=10), tickangle=-20)
            _fig7.update_yaxes(showticklabels=False)
            st.plotly_chart(_fig7, use_container_width=True, key=chart_key)

        _dc1, _dc2 = st.columns(2, gap="small")
        with _dc1:
            st.markdown(
                f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
                unsafe_allow_html=True,
            )
            _detail_yoy_chart(
                _busan_yoy,
                f"🏙️ 부산 구별  ({_yoy_cur_label} vs {_yoy_prv_label})",
                C["blue"], _c(C["red"], 0.80),
                f"reg_yoy_busan_{_sel_dept}_{_yoy_cur}",
            )
            st.markdown("</div>", unsafe_allow_html=True)
        with _dc2:
            st.markdown(
                f'<div class="wd-card" style="border-top:3px solid {C["green"]};">',
                unsafe_allow_html=True,
            )
            _detail_yoy_chart(
                _gynam_yoy,
                f"🏞️ 경상남도 시군별  ({_yoy_cur_label} vs {_yoy_prv_label})",
                C["green"], _c(C["red"], 0.80),
                f"reg_yoy_gynam_{_sel_dept}_{_yoy_cur}",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)  # card
        _gap()

    # ══════════════════════════════════════════════════════════════════════
    # [섹션7] 월별 환자 추이 + 선택적 비교 (V_REGION_DEPT_MONTHLY 기반)
    # ══════════════════════════════════════════════════════════════════════
    if _mo_months:
        _mo_total = {ym: sum(v.values()) for ym, v in _mo_lookup.items()}

        st.markdown(
            f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
            unsafe_allow_html=True,
        )
        _sec_hd(f"📅 {_sel_dept} — 월별 환자 추이",
                f"V_REGION_DEPT_MONTHLY · {len(_mo_months)}개월 · 지역미상 제외",
                C["blue"])

        # KPI (전월 대비)
        if len(_mo_months) >= 2:
            _cm = _mo_months[-1]
            _pm = _mo_months[-2]
            _ct = _mo_total.get(_cm, 0)
            _pt = _mo_total.get(_pm, 0)
            _md = _ct - _pt
            _mp = round(_md / max(_pt, 1) * 100, 1)
            _mc = C["red"] if _md > 0 else C["blue"] if _md < 0 else C["t3"]
            _mxm = max(_mo_total, key=_mo_total.get)

            _km1, _km2, _km3, _km4 = st.columns(4, gap="small")
            _kpi_card(_km1, "📅", f"당월 ({_cm[:4]}.{_cm[4:]})", f"{_ct:,}", "명",
                      "지역미상 제외", C["blue"])
            _kpi_card(_km2, "📅", f"전월 ({_pm[:4]}.{_pm[4:]})", f"{_pt:,}", "명",
                      "지역미상 제외", C["t2"])
            _km3.markdown(
                f'<div class="fn-kpi" style="border-top:3px solid {_mc};">'
                f'<div class="fn-kpi-icon">{"📈" if _md >= 0 else "📉"}</div>'
                f'<div class="fn-kpi-label">전월 대비</div>'
                f'<div style="font-size:18px;font-weight:800;color:{_mc};">'
                f'{"▲" if _md > 0 else "▼"}&nbsp;{abs(_md):,}'
                f'<span style="font-size:11px;color:{C["t3"]};">명</span></div>'
                f'<div style="font-size:11px;color:{_mc};font-weight:700;">'
                f'{_mp:+.1f}%</div></div>',
                unsafe_allow_html=True,
            )
            _kpi_card(_km4, "🏆", "최대 월", f"{_mo_total[_mxm]:,}", "명",
                      f"{_mxm[:4]}.{_mxm[4:]}", C["teal"])
            _gap()

        # 월별 추이 바 차트
        if HAS_PLOTLY:
            _ml = [f"{ym[:4]}.{ym[4:]}" for ym in _mo_months]
            _mv = [_mo_total.get(ym, 0) for ym in _mo_months]
            _mc2 = [
                C["blue"] if ym == _mo_months[-1]
                else _c(C["indigo"], 0.67) if ym == _mo_months[-2]
                else _c(C["indigo"], 0.33)
                for ym in _mo_months
            ]
            _fig_mo = go.Figure(go.Bar(
                x=_ml, y=_mv,
                marker=dict(color=_mc2, line=dict(color="rgba(0,0,0,0)")),
                text=[f"{v:,}" for v in _mv],
                textposition="outside",
                textfont=dict(size=10, color=C["t2"]),
                hovertemplate="<b>%{x}</b><br>%{y:,}명<extra></extra>",
            ))
            _fig_mo.update_layout(
                **_PLOTLY_LAYOUT, height=260,
                margin=dict(l=0, r=0, t=30, b=8),
                showlegend=False, bargap=0.25,
            )
            _fig_mo.update_xaxes(tickfont=dict(size=10))
            _fig_mo.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)",
                                  showticklabels=False)
            st.plotly_chart(_fig_mo, use_container_width=True,
                            key=f"reg_mo_bar_{_sel_dept}")

        # 월별 요약 테이블 (최근 12개월 · 컴팩트)
        _mo_recent = list(reversed(_mo_months))[:12]
        _TH_MO = (
            "padding:5px 8px;font-size:11px;font-weight:700;color:#64748B;"
            "border-bottom:1.5px solid #E2E8F0;background:#F8FAFC;"
        )
        _mo_tbl = (
            '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>'
            f'<th style="{_TH_MO}text-align:left;width:72px;">월</th>'
            f'<th style="{_TH_MO}text-align:right;color:{C["blue"]};">환자수</th>'
            f'<th style="{_TH_MO}text-align:right;">전월대비</th>'
            f'<th style="{_TH_MO}">1위 지역</th>'
            f'<th style="{_TH_MO}text-align:right;width:48px;">점유율</th>'
            f'</tr></thead><tbody>'
        )
        for _ri8, _ym8 in enumerate(_mo_recent):
            _rbg8 = "#F8FAFC" if _ri8 % 2 == 0 else "#FFFFFF"
            _td8  = (f"padding:5px 8px;background:{_rbg8};"
                     "border-bottom:1px solid #F1F5F9;font-size:12px;")
            _tot8    = _mo_total.get(_ym8, 0)
            _prev_ym8 = _mo_recent[_ri8 + 1] if _ri8 + 1 < len(_mo_recent) else None
            _prev8    = _mo_total.get(_prev_ym8, 0) if _prev_ym8 else None
            if _prev8 is not None and _prev8 > 0:
                _diff8  = _tot8 - _prev8
                _pct8   = round(_diff8 / _prev8 * 100, 1)
                _dc8    = C["red"] if _diff8 > 0 else C["blue"] if _diff8 < 0 else C["t3"]
                _darr8  = "▲" if _diff8 > 0 else "▼" if _diff8 < 0 else "─"
                _mom8   = (f'<span style="color:{_dc8};font-weight:700;">'
                           f'{_darr8} {abs(_diff8):,} ({_pct8:+.1f}%)</span>')
            else:
                _mom8 = '<span style="color:#CBD5E1;">─</span>'
            _tops8   = sorted(_mo_lookup[_ym8].items(), key=lambda x: -x[1])
            _top1_rg8 = _tops8[0][0] if _tops8 else "─"
            _top1_pt8 = round(_tops8[0][1] / max(_tot8, 1) * 100, 1) if _tops8 else 0
            _is_cur8  = (_ym8 == _mo_months[-1])
            _ym_clr8  = C["blue"] if _is_cur8 else C["t2"]
            _ym_fw8   = "800" if _is_cur8 else "600"
            _mo_tbl += (
                f"<tr>"
                f'<td style="{_td8}font-weight:{_ym_fw8};color:{_ym_clr8};">'
                f'{_ym8[:4]}.{_ym8[4:]}</td>'
                f'<td style="{_td8}text-align:right;font-weight:700;color:{C["t1"]};">'
                f'{_tot8:,}</td>'
                f'<td style="{_td8}text-align:right;">{_mom8}</td>'
                f'<td style="{_td8}color:{C["t2"]};">{_top1_rg8}</td>'
                f'<td style="{_td8}text-align:right;color:{C["t3"]};">{_top1_pt8}%</td>'
                f"</tr>"
            )
        st.markdown(_mo_tbl + "</tbody></table>", unsafe_allow_html=True)
        if len(_mo_months) > 12:
            with st.expander(f"📋 전체 {len(_mo_months)}개월 보기"):
                _mo_all_tbl = (
                    '<table style="width:100%;border-collapse:collapse;font-size:11.5px;">'
                    f'<thead><tr>'
                    f'<th style="{_TH_MO}text-align:left;">월</th>'
                    f'<th style="{_TH_MO}text-align:right;">환자수</th>'
                    f'<th style="{_TH_MO}">1위 지역</th>'
                    f'<th style="{_TH_MO}">2위 지역</th>'
                    f'</tr></thead><tbody>'
                )
                for _ri9, _ym9 in enumerate(reversed(_mo_months)):
                    _rbg9 = "#F8FAFC" if _ri9 % 2 == 0 else "#FFFFFF"
                    _td9  = f"padding:4px 8px;background:{_rbg9};border-bottom:1px solid #F1F5F9;font-size:11.5px;"
                    _tot9 = _mo_total.get(_ym9, 0)
                    _tops9 = sorted(_mo_lookup[_ym9].items(), key=lambda x: -x[1])[:2]
                    _rg9  = [f"{r}({c:,}명)" for r, c in _tops9]
                    while len(_rg9) < 2: _rg9.append("─")
                    _mo_all_tbl += (
                        f"<tr>"
                        f'<td style="{_td9}font-weight:600;color:{C["t2"]};">{_ym9[:4]}.{_ym9[4:]}</td>'
                        f'<td style="{_td9}text-align:right;font-weight:700;">{_tot9:,}</td>'
                        f'<td style="{_td9}">{_rg9[0]}</td>'
                        f'<td style="{_td9}">{_rg9[1]}</td>'
                        f"</tr>"
                    )
                st.markdown(_mo_all_tbl + "</tbody></table>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        _gap()

    # ── 월별 지역 비교 (선택적)
    if len(_mo_months) >= 2:
        _show_cmp = st.checkbox(
            f"📊 {_sel_dept} — 월별 지역 비교 (두 달 선택 → 지역별 증감)",
            key=f"reg_mo_cmp_{_sel_dept}",
        )
        if _show_cmp:
            st.markdown(
                f'<div class="wd-card" style="border-top:3px solid {C["violet"]};">',
                unsafe_allow_html=True,
            )
            _sec_hd("📊 월별 지역 비교 분석",
                    f"{_sel_dept} · 두 달 선택", C["violet"])

            def _fmt_ym_ko(ym: str) -> str:
                return f"{ym[:4]}년 {ym[4:]}월"

            _cc1, _cc2 = st.columns(2, gap="small")
            with _cc1:
                st.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
                    f'padding-bottom:2px;">📅 A월 (기준)</div>',
                    unsafe_allow_html=True,
                )
                _cmp_a_default = (
                    _mo_months.index(_sel_ym) if _sel_ym in _mo_months
                    else max(0, len(_mo_months) - 2)
                )
                _cmp_a = st.selectbox(
                    "A월", options=_mo_months,
                    index=_cmp_a_default,
                    format_func=_fmt_ym_ko,
                    key=f"reg_cmp_a_{_sel_dept}",
                    label_visibility="collapsed",
                )
            with _cc2:
                st.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:{C["t2"]};'
                    f'padding-bottom:2px;">📅 B월 (비교)</div>',
                    unsafe_allow_html=True,
                )
                _cmp_b_default = (
                    _mo_months.index(_cmp_ym) if _cmp_ym and _cmp_ym in _mo_months
                    else (_mo_months.index(_prev_ym) if _prev_ym in _mo_months
                          else len(_mo_months) - 1)
                )
                _cmp_b = st.selectbox(
                    "B월", options=_mo_months,
                    index=_cmp_b_default,
                    format_func=_fmt_ym_ko,
                    key=f"reg_cmp_b_{_sel_dept}",
                    label_visibility="collapsed",
                )

            if _cmp_a == _cmp_b:
                st.warning("⚠️ A월과 B월이 같습니다. 서로 다른 달을 선택하세요.")
            else:
                _a_d = dict(_mo_lookup.get(_cmp_a, {}))
                _b_d = dict(_mo_lookup.get(_cmp_b, {}))
                _tot_a2 = sum(_a_d.values())
                _tot_b2 = sum(_b_d.values())
                _all_r2 = sorted(set(list(_a_d.keys()) + list(_b_d.keys())))

                _cmp_rows = []
                for _rg2 in _all_r2:
                    _ca2 = _a_d.get(_rg2, 0)
                    _cb2 = _b_d.get(_rg2, 0)
                    _diff2 = _cb2 - _ca2
                    _pct2 = round(_diff2 / max(_ca2, 1) * 100, 1) if _ca2 > 0 else None
                    _cmp_rows.append({"지역": _rg2, "A": _ca2, "B": _cb2,
                                      "증감": _diff2, "증감률": _pct2})
                _cmp_rows.sort(key=lambda x: -x["증감"])

                _inc_n2 = sum(1 for r in _cmp_rows if r["증감"] > 0)
                _dec_n2 = sum(1 for r in _cmp_rows if r["증감"] < 0)
                _diff_t2 = _tot_b2 - _tot_a2
                _diff_p2 = round(_diff_t2 / max(_tot_a2, 1) * 100, 1)

                _kc1, _kc2, _kc3, _kc4 = st.columns(4, gap="small")
                _kpi_card(_kc1, "📅", _fmt_ym_ko(_cmp_a), f"{_tot_a2:,}", "명",
                          "A월 환자수", C["indigo"])
                _kpi_card(_kc2, "📅", _fmt_ym_ko(_cmp_b), f"{_tot_b2:,}", "명",
                          "B월 환자수", C["blue"])
                _kpi_card(_kc3, "📊", "총 증감", f"{_diff_t2:+,}", "명",
                          f"{_diff_p2:+.1f}%",
                          C["red"] if _diff_t2 > 0 else C["blue"])
                _kpi_card(_kc4, "🔄", "지역 변화",
                          f"▲{_inc_n2} ▼{_dec_n2}", "",
                          f"총 {len(_cmp_rows)}개 지역", C["teal"])
                _gap()

                _cc_l2, _cc_r2 = st.columns(2, gap="small")
                _top_inc2 = [r for r in _cmp_rows if r["증감"] > 0][:10]
                _top_dec2 = sorted(
                    [r for r in _cmp_rows if r["증감"] < 0], key=lambda x: x["증감"]
                )[:10]

                with _cc_l2:
                    st.markdown(
                        f'<div class="wd-card" style="border-top:3px solid {C["red"]};">',
                        unsafe_allow_html=True,
                    )
                    _sec_hd(f"📈 증가 TOP {len(_top_inc2)}", "", C["red"])
                    if _top_inc2 and HAS_PLOTLY:
                        _fig_i = go.Figure(go.Bar(
                            x=[r["증감"] for r in _top_inc2],
                            y=[r["지역"] for r in _top_inc2],
                            orientation="h",
                            marker_color=_c(C["red"], 0.80),
                            text=[f"+{r['증감']:,}명" for r in _top_inc2],
                            textposition="outside",
                            textfont=dict(size=10, color=C["red"]),
                        ))
                        _fig_i.update_layout(
                            **_PLOTLY_LAYOUT,
                            height=max(200, len(_top_inc2) * 28 + 60),
                            margin=dict(l=0, r=90, t=8, b=8), showlegend=False,
                        )
                        _fig_i.update_xaxes(showticklabels=False, showgrid=False)
                        _fig_i.update_yaxes(tickfont=dict(size=10), autorange="reversed")
                        st.plotly_chart(_fig_i, use_container_width=True,
                                        key=f"reg_cmp_inc2_{_sel_dept}_{_cmp_a}_{_cmp_b}")
                    else:
                        st.info("증가 지역 없음")
                    st.markdown("</div>", unsafe_allow_html=True)

                with _cc_r2:
                    st.markdown(
                        f'<div class="wd-card" style="border-top:3px solid {C["blue"]};">',
                        unsafe_allow_html=True,
                    )
                    _sec_hd(f"📉 감소 TOP {len(_top_dec2)}", "", C["blue"])
                    if _top_dec2 and HAS_PLOTLY:
                        _fig_d = go.Figure(go.Bar(
                            x=[r["증감"] for r in _top_dec2],
                            y=[r["지역"] for r in _top_dec2],
                            orientation="h",
                            marker_color=_c(C["blue"], 0.80),
                            text=[f"{r['증감']:,}명" for r in _top_dec2],
                            textposition="outside",
                            textfont=dict(size=10, color=C["blue"]),
                        ))
                        _fig_d.update_layout(
                            **_PLOTLY_LAYOUT,
                            height=max(200, len(_top_dec2) * 28 + 60),
                            margin=dict(l=0, r=90, t=8, b=8), showlegend=False,
                        )
                        _fig_d.update_xaxes(showticklabels=False, showgrid=False)
                        _fig_d.update_yaxes(tickfont=dict(size=10), autorange="reversed")
                        st.plotly_chart(_fig_d, use_container_width=True,
                                        key=f"reg_cmp_dec2_{_sel_dept}_{_cmp_a}_{_cmp_b}")
                    else:
                        st.info("감소 지역 없음")
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
        _gap()

 
 
# ════════════════════════════════════════════════════════════════════
# 카드 매칭 탭  (기존 _tab_card_match 그대로 — 내용 동일)
# ════════════════════════════════════════════════════════════════════
