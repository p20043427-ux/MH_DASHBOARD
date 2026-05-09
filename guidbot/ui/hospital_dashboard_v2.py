"""
ui/hospital_dashboard_v2.py  ─  병동 대시보드 v2.0  (2026-05-09)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[v2.0 — 신규 설계]
  · 관리자 대시보드(admin_dashboard.py) 디자인 규칙 채택
  · 다크 헤더 + KPI strip + 탭 기반 콘텐츠 구조
  · 기존 hospital_dashboard.py 는 유지 (병행 운영)

[레이아웃]
  ─ 헤더(다크) : 병원명 / 날짜시각 / Oracle 상태 / 새로고침
  ─ 병동 선택  : selectbox 한 행 (헤더 아래)
  ─ KPI strip  : 병상가동률 · 재원 · 금일입원 · 금일퇴원 · 수술 (5카드)
  ─ 탭 콘텐츠  :
      ① 병동별 현황  — 전체 병동 병상 현황 테이블 + 요약 바
      ② 진료과 재원  — 도넛 차트 + 상세 테이블 (2열)
      ③ 주간 추이    — 라인 차트 + 데이터 테이블
      ④ 주상병 분포  — 7일 분포 + 금일 vs 전일 비교
      ⑤ 익일 예약    — 수용률 패널 + 예약 상세 + 빈병상 추천
      ⑥ AI 분석      — LLM 채팅 (기존 _render_ward_llm_chat 재사용)

[데이터 소스]
  · db.ward_repository._qc()  — Oracle VIEW 2분 TTL 캐시
  · services.ward_service     — 필터·집계 헬퍼
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import streamlit as st

try:
    import plotly.graph_objects as go
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

from db.ward_repository import _qc
from services.ward_service import (
    _safe_int, _safe_float,
    _filter_by_ward, _filter_dx_ward, _trend_dedup,
)
from ui.design import C, APP_CSS, ward_kpi_card as _kpi_card, gap


# ════════════════════════════════════════════════════════════════════
#  V2 전용 CSS — APP_CSS 위에 추가되는 규칙만
# ════════════════════════════════════════════════════════════════════
_V2_CSS: str = """
<style>
/* ── v2 다크 헤더 ─────────────────────────────────────────── */
.v2-hero {
  background: linear-gradient(135deg, #0F172A 0%, #1E3A5F 100%);
  padding: 22px 28px 18px;
  margin: 0 -1rem 0;
  border-bottom: 1px solid rgba(255,255,255,.08);
  position: relative; overflow: hidden;
}
.v2-hero::before {
  content: '';
  position: absolute; top: -80px; right: -80px;
  width: 340px; height: 340px;
  background: radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 65%);
  pointer-events: none;
}
.v2-hero-hosp {
  font-size: 10.5px; font-weight: 700; color: rgba(255,255,255,.45);
  text-transform: uppercase; letter-spacing: .14em; margin-bottom: 3px;
}
.v2-hero-title {
  font-size: 22px; font-weight: 800; color: #fff;
  letter-spacing: -.4px; line-height: 1.15; margin-bottom: 2px;
}
.v2-hero-sub {
  font-size: 12px; color: rgba(255,255,255,.45); font-weight: 400;
}
.v2-oracle-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-right: 5px; vertical-align: middle;
}

/* ── KPI strip (다크 배경) ──────────────────────────────────── */
.v2-kpi-strip {
  background: #0F172A;
  padding: 16px 28px 20px;
  margin: 0 -1rem 0;
  border-bottom: 2px solid #1E293B;
}

/* v2 안에서 fn-kpi: 다크 bg 위 흰 카드 — 높이 고정 */
.v2-kpi-strip .fn-kpi {
  height: 120px !important;
  min-height: 120px !important;
  padding: 12px 14px !important;
  background: rgba(255,255,255,.96) !important;
}

/* ── 탭 섹션 여백 ───────────────────────────────────────────── */
.v2-tab-body {
  padding: 20px 0 12px;
}

/* ── 수용률 패널 ───────────────────────────────────────────── */
.v2-cap-panel {
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 16px;
}
.v2-cap-title {
  font-size: 10px; font-weight: 700; color: #64748B;
  text-transform: uppercase; letter-spacing: .12em; margin-bottom: 10px;
}
.v2-cap-pct {
  font-size: 42px; font-weight: 800; line-height: 1;
  font-variant-numeric: tabular-nums; letter-spacing: -.04em;
}
.v2-cap-bar-track {
  height: 8px; background: #E2E8F0;
  border-radius: 9999px; overflow: hidden; margin: 10px 0 14px;
}
.v2-stat-lbl {
  font-size: 9px; font-weight: 700; color: #94A3B8;
  text-transform: uppercase; letter-spacing: .08em; margin-bottom: 3px;
}
.v2-stat-val {
  font-size: 22px; font-weight: 800; color: #0F172A; line-height: 1;
}
.v2-stat-unit {
  font-size: 11px; color: #64748B; font-weight: 500; margin-left: 2px;
}
.v2-divider { width: 1px; background: #E2E8F0; margin: 0 4px; }

/* ── 가동률 배지 ───────────────────────────────────────────── */
.v2-rate-ok   { color: #16A34A; }
.v2-rate-warn { color: #F59E0B; }
.v2-rate-err  { color: #EF4444; }

/* ── 요약 foot row ─────────────────────────────────────────── */
.v2-sum-row {
  display: flex; gap: 18px; align-items: center;
  background: #F8FAFC; border-top: 1.5px solid #E2E8F0;
  padding: 8px 14px; border-radius: 0 0 10px 10px;
  font-size: 12px;
}
.v2-sum-lbl { color: #64748B; font-weight: 500; }
.v2-sum-val { font-weight: 700; color: #0F172A; }
</style>
"""


# ════════════════════════════════════════════════════════════════════
#  헬퍼 함수들
# ════════════════════════════════════════════════════════════════════

def _oc_color(rate: float) -> str:
    if rate >= 90: return "#EF4444"
    if rate >= 80: return "#F59E0B"
    return "#16A34A"

def _oc_cls(rate: float) -> str:
    if rate >= 90: return "v2-rate-err"
    if rate >= 80: return "v2-rate-warn"
    return "v2-rate-ok"

def _delta(cur: int, prev: int, unit: str = "명") -> str:
    d = cur - prev
    if d > 0: return f"▲ +{d}{unit}"
    if d < 0: return f"▼ {d}{unit}"
    return "─"


def _trend_bar(val: float, max_val: float, color: str, height: int = 6) -> str:
    """인라인 프로그레스 바 HTML."""
    w = f"{min(val / max(max_val, 1) * 100, 100):.1f}"
    return (
        f'<div style="height:{height}px;background:#E2E8F0;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{w}%;height:100%;background:{color};border-radius:3px;"></div>'
        f'</div>'
    )


# ════════════════════════════════════════════════════════════════════
#  헤더 (다크 hero)
# ════════════════════════════════════════════════════════════════════

def _v2_header(oracle_ok: bool, ward: str, ward_list: List[str]) -> str:
    """다크 헤더 렌더링 → 선택된 병동 반환."""
    _ts  = time.strftime("%Y-%m-%d %H:%M")
    _dot = "#16A34A" if oracle_ok else "#F59E0B"
    _lbl = "Oracle 연결 정상" if oracle_ok else "Oracle 미연결"

    st.markdown(
        f'<div class="v2-hero">'
        f'<div class="v2-hero-hosp">좋은문화병원</div>'
        f'<div class="v2-hero-title">병동 현황 대시보드</div>'
        f'<div class="v2-hero-sub">'
        f'<span class="v2-oracle-dot" style="background:{_dot};'
        f'box-shadow:0 0 0 3px {_dot}33;"></span>{_lbl}'
        f'<span style="margin-left:14px;color:rgba(255,255,255,.35);">|</span>'
        f'<span style="margin-left:14px;">{_ts}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 병동 선택 + 새로고침 한 행
    _hc1, _hc2, _hc3 = st.columns([6, 2, 1], gap="small")
    with _hc1:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        new_ward = st.selectbox(
            "병동 선택",
            options=ward_list,
            index=ward_list.index(ward) if ward in ward_list else 0,
            key="v2_ward_sel",
            label_visibility="collapsed",
        )
    with _hc2:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    with _hc3:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        if st.button("새로고침", key="v2_refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if new_ward != st.session_state.get("v2_ward_prev"):
        st.session_state["v2_ward_prev"] = new_ward
        st.session_state["ward_selected"] = new_ward
    return new_ward


# ════════════════════════════════════════════════════════════════════
#  KPI Strip (5카드)
# ════════════════════════════════════════════════════════════════════

def _v2_kpi_strip(
    occ_rate: float, occupied: int, total_bed: int,
    admit_cnt: int, disc_cnt: int, op_total: int,
    pa: int, pd: int, ps: int, next_op: int,
) -> None:
    st.markdown('<div class="v2-kpi-strip">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5, gap="small")
    _c = _oc_color(occ_rate)

    with c1:
        _kpi_card("병상 가동률",   f"{occ_rate:.1f}", "%",
                  f"재원 {occupied} / {total_bed}병상",
                  _c, delta=_delta(occupied, ps), bar_pct=occ_rate)
    with c2:
        _kpi_card("재원 환자",     str(occupied),    "명",
                  "총 재원 중",
                  "#0F172A", delta=_delta(occupied, ps))
    with c3:
        _kpi_card("금일 입원",     str(admit_cnt),   "명",
                  f"전일 {pa}명",
                  C["blue"], delta=_delta(admit_cnt, pa))
    with c4:
        _kpi_card("금일 퇴원",     str(disc_cnt),    "명",
                  f"전일 {pd}명",
                  "#475569", delta=_delta(disc_cnt, pd))
    with c5:
        _kpi_card("금일 수술",     str(op_total),    "건",
                  f"익일 예약 {next_op}건",
                  C["purple"])
    st.markdown('</div>', unsafe_allow_html=True)
    gap(12)


# ════════════════════════════════════════════════════════════════════
#  탭 ① — 병동별 현황
# ════════════════════════════════════════════════════════════════════

def _tab_ward_detail(bed_detail_f: List[Dict], op_stat_f: List[Dict]) -> None:
    if not bed_detail_f:
        st.info("병동별 현황 데이터가 없습니다.")
        return

    # 병동별 수술 건수
    _surg: Dict[str, int] = {}
    for r in op_stat_f:
        w = r.get("병동명", "")
        _surg[w] = _surg.get(w, 0) + int(r.get("수술건수", 0) or 0)

    _TH = "padding:10px 12px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748B;background:#F8FAFC;border-bottom:1.5px solid #E2E8F0;white-space:nowrap;"
    _th = (
        f'<th style="{_TH}text-align:left;">병동</th>'
        f'<th style="{_TH}text-align:right;">총병상</th>'
        f'<th style="{_TH}text-align:right;">재원</th>'
        f'<th style="{_TH}text-align:right;">가동률</th>'
        f'<th style="{_TH}text-align:right;">입원</th>'
        f'<th style="{_TH}text-align:right;">퇴원</th>'
        f'<th style="{_TH}text-align:right;color:#7C3AED;">퇴원예정</th>'
        f'<th style="{_TH}text-align:right;color:#8B5CF6;">수술</th>'
        f'<th style="{_TH}text-align:right;">잔여</th>'
        f'<th style="{_TH}text-align:right;color:#059669;">익일가용</th>'
    )
    rows_html = ""
    _sum = dict(총=0, 재=0, 입=0, 퇴=0, 예정=0, 수=0, 잔=0, 익=0)

    for i, r in enumerate(bed_detail_f):
        bg    = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
        rate  = _safe_float(r.get("가동률"))
        tot   = _safe_int(r.get("총병상"))
        stay  = _safe_int(r.get("재원수"))
        adm   = _safe_int(r.get("금일입원"))
        disc  = _safe_int(r.get("금일퇴원"))
        ndc   = _safe_int(r.get("익일퇴원예고"))
        rest  = max(0, tot - stay)
        avail = max(0, rest + ndc)
        wname = r.get("병동명", "")
        op_cnt = _surg.get(wname, 0)
        rc    = _oc_color(rate)

        _sum["총"] += tot; _sum["재"] += stay
        _sum["입"] += adm; _sum["퇴"] += disc
        _sum["예정"] += ndc; _sum["수"] += op_cnt
        _sum["잔"] += rest; _sum["익"] += avail

        _td = f"padding:9px 12px;background:{bg};border-bottom:1px solid #F1F5F9;"
        _tdn = f"{_td}font-variant-numeric:tabular-nums;font-family:Consolas,monospace;text-align:right;"
        rows_html += (
            f"<tr>"
            f'<td style="{_td}font-weight:700;color:#0F172A;">{wname}</td>'
            f'<td style="{_tdn}">{tot}</td>'
            f'<td style="{_tdn}font-weight:600;">{stay}</td>'
            f'<td style="padding:9px 12px;background:{bg};border-bottom:1px solid #F1F5F9;">'
            f'<div style="display:flex;align-items:center;gap:7px;">'
            f'{_trend_bar(rate, 100, rc, 5)}'
            f'<span style="font-size:12.5px;font-weight:700;color:{rc};font-family:Consolas,monospace;white-space:nowrap;">{rate:.1f}%</span>'
            f'</div></td>'
            f'<td style="{_tdn}color:#1D4ED8;">{adm}</td>'
            f'<td style="{_tdn}">{disc}</td>'
            f'<td style="{_tdn}color:#7C3AED;">{ndc}</td>'
            f'<td style="{_tdn}color:#8B5CF6;">{op_cnt}</td>'
            f'<td style="{_tdn}">{rest}</td>'
            f'<td style="{_tdn}font-weight:700;color:#059669;">{avail}</td>'
            f"</tr>"
        )

    # 합계 행
    _sf = "#EFF6FF"
    _stl = f"padding:9px 12px;background:{_sf};border-top:2px solid #BFDBFE;font-weight:700;"
    _stn = f"{_stl}font-variant-numeric:tabular-nums;font-family:Consolas,monospace;text-align:right;"
    tot_rate = round(_sum["재"] / max(_sum["총"], 1) * 100, 1)
    rc_sum = _oc_color(tot_rate)
    rows_html += (
        f"<tr>"
        f'<td style="{_stl}color:#1E40AF;">합 계</td>'
        f'<td style="{_stn}">{_sum["총"]}</td>'
        f'<td style="{_stn}">{_sum["재"]}</td>'
        f'<td style="{_stl}">'
        f'<span style="font-size:12.5px;font-weight:800;color:{rc_sum};">{tot_rate:.1f}%</span>'
        f'</td>'
        f'<td style="{_stn}color:#1D4ED8;">{_sum["입"]}</td>'
        f'<td style="{_stn}">{_sum["퇴"]}</td>'
        f'<td style="{_stn}color:#7C3AED;">{_sum["예정"]}</td>'
        f'<td style="{_stn}color:#8B5CF6;">{_sum["수"]}</td>'
        f'<td style="{_stn}">{_sum["잔"]}</td>'
        f'<td style="{_stn}color:#059669;font-size:13px;">{_sum["익"]}</td>'
        f"</tr>"
    )

    st.markdown(
        f'<div class="wd-card" style="padding:0;overflow:hidden;">'
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
        f'<thead><tr>{_th}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div></div>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
#  탭 ② — 진료과 재원 구성
# ════════════════════════════════════════════════════════════════════

def _tab_dept_stay(dept_stay_f: List[Dict]) -> None:
    if not dept_stay_f:
        st.info("진료과 재원 데이터가 없습니다.")
        return

    _sorted = sorted(dept_stay_f, key=lambda r: -_safe_int(r.get("재원수", 0)))
    _total  = sum(_safe_int(r.get("재원수", 0)) for r in _sorted)

    col_chart, col_tbl = st.columns([1, 1], gap="medium")

    with col_chart:
        st.markdown('<div class="wd-card" style="padding:16px 18px;">', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11.5px;font-weight:700;color:#0F172A;'
            'margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #F1F5F9;">'
            '진료과별 재원 구성</div>',
            unsafe_allow_html=True,
        )
        if HAS_PLOTLY and _sorted:
            _labels = [r.get("진료과명", "기타") for r in _sorted[:12]]
            _vals   = [_safe_int(r.get("재원수", 0)) for r in _sorted[:12]]
            _colors = [
                "#1E40AF","#3B82F6","#60A5FA","#7C3AED","#A78BFA",
                "#EC4899","#F43F5E","#F97316","#EAB308","#059669",
                "#0891B2","#64748B",
            ]
            fig = go.Figure(go.Pie(
                labels=_labels, values=_vals,
                hole=0.55,
                marker=dict(colors=_colors[:len(_labels)], line=dict(color="#fff", width=2)),
                textinfo="percent",
                textfont=dict(size=11, color="#fff"),
                hovertemplate="%{label}<br>%{value}명 (%{percent})<extra></extra>",
            ))
            fig.add_annotation(
                text=f"<b>{_total}</b><br><span style='font-size:11px;color:#64748B;'>총 재원</span>",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=20, color="#0F172A"),
                align="center",
            )
            fig.update_layout(
                showlegend=True, margin=dict(t=10, b=10, l=10, r=10),
                height=280, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(font=dict(size=10), orientation="v",
                            x=1.02, y=0.5, bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            # fallback — 가로 바 차트 (HTML)
            for r in _sorted[:10]:
                dept  = r.get("진료과명", "")
                cnt   = _safe_int(r.get("재원수", 0))
                pct   = cnt / max(_total, 1) * 100
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
                    f'<div style="width:70px;font-size:11px;color:#475569;text-align:right;white-space:nowrap;">{dept}</div>'
                    f'<div style="flex:1;height:14px;background:#EFF6FF;border-radius:3px;overflow:hidden;">'
                    f'<div style="width:{pct:.1f}%;height:100%;background:#3B82F6;border-radius:3px;"></div>'
                    f'</div>'
                    f'<div style="width:42px;font-size:11px;font-weight:700;color:#1E40AF;text-align:right;">{cnt}명</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)

    with col_tbl:
        st.markdown('<div class="wd-card" style="padding:0;overflow:hidden;">', unsafe_allow_html=True)
        _TH = "padding:10px 14px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748B;background:#F8FAFC;border-bottom:1.5px solid #E2E8F0;"
        rows = ""
        for i, r in enumerate(_sorted):
            bg   = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
            cnt  = _safe_int(r.get("재원수", 0))
            pct  = cnt / max(_total, 1) * 100
            dept = r.get("진료과명", "—")
            rows += (
                f'<tr>'
                f'<td style="padding:8px 14px;background:{bg};border-bottom:1px solid #F1F5F9;">'
                f'<span style="font-weight:600;color:#0F172A;">{dept}</span></td>'
                f'<td style="padding:8px 14px;background:{bg};border-bottom:1px solid #F1F5F9;text-align:right;">'
                f'<span style="font-variant-numeric:tabular-nums;font-family:Consolas,monospace;font-weight:700;color:#1E40AF;">{cnt}</span>'
                f'<span style="font-size:11px;color:#94A3B8;margin-left:2px;">명</span></td>'
                f'<td style="padding:8px 14px;background:{bg};border-bottom:1px solid #F1F5F9;width:100px;">'
                f'{_trend_bar(pct, 100, "#3B82F6", 5)}'
                f'<span style="font-size:10px;color:#64748B;">{pct:.1f}%</span></td>'
                f'</tr>'
            )
        st.markdown(
            f'<div style="overflow-y:auto;max-height:320px;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
            f'<thead><tr>'
            f'<th style="{_TH}text-align:left;">진료과</th>'
            f'<th style="{_TH}text-align:right;">재원</th>'
            f'<th style="{_TH}">비율</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
#  탭 ③ — 주간 추이
# ════════════════════════════════════════════════════════════════════

def _tab_trend(trend_f: List[Dict], occ_rate: float) -> None:
    if not trend_f:
        st.info("추이 데이터가 없습니다.")
        return

    _today_str = time.strftime("%Y-%m-%d")
    _no_today  = [r for r in trend_f if str(r.get("기준일",""))[:10] != _today_str]
    _t7 = sorted(_no_today, key=lambda r: str(r.get("기준일", "")))[-7:]

    col_ch, col_tbl = st.columns([3, 2], gap="medium")

    with col_ch:
        st.markdown('<div class="wd-card" style="padding:16px 18px;">', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11.5px;font-weight:700;color:#0F172A;'
            'margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #F1F5F9;">'
            '7일 가동률 추이</div>',
            unsafe_allow_html=True,
        )
        if HAS_PLOTLY and _t7:
            _dates = [str(r.get("기준일",""))[:10][5:] for r in _t7]  # MM-DD
            _rates = [_safe_float(r.get("가동률", 0)) for r in _t7]
            _admits = [_safe_int(r.get("금일입원", 0)) for r in _t7]
            _discs  = [_safe_int(r.get("금일퇴원", 0)) for r in _t7]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=_dates, y=_rates, name="가동률(%)",
                mode="lines+markers+text",
                line=dict(color="#3B82F6", width=2.5),
                marker=dict(size=6, color="#3B82F6"),
                text=[f"{v:.1f}%" for v in _rates],
                textposition="top center",
                textfont=dict(size=10, color="#1E40AF"),
                fill="tozeroy", fillcolor="rgba(59,130,246,0.07)",
            ))
            fig.add_hline(y=occ_rate, line_dash="dot",
                          line_color="#F59E0B", line_width=1.5,
                          annotation_text=f"현재 {occ_rate:.1f}%",
                          annotation_font_size=10)
            fig.update_layout(
                margin=dict(t=10, b=30, l=0, r=0), height=220,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                xaxis=dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False,
                           tickfont=dict(size=10)),
                yaxis=dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False,
                           ticksuffix="%", tickfont=dict(size=10), range=[0, 105]),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            # 입퇴원 막대
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=_dates, y=_admits, name="입원",
                                  marker_color="#3B82F6", text=_admits,
                                  textposition="outside", textfont_size=10))
            fig2.add_trace(go.Bar(x=_dates, y=_discs, name="퇴원",
                                  marker_color="#94A3B8", text=_discs,
                                  textposition="outside", textfont_size=10))
            fig2.update_layout(
                margin=dict(t=10, b=30, l=0, r=0), height=160,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                barmode="group", bargap=0.25,
                legend=dict(orientation="h", x=0, y=1.1, font_size=10,
                            bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False,
                           tickfont=dict(size=10)),
                yaxis=dict(gridcolor="#F1F5F9", linecolor="#E2E8F0", zeroline=False,
                           tickfont=dict(size=10)),
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Plotly 미설치 — 테이블로 표시합니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_tbl:
        st.markdown('<div class="wd-card" style="padding:0;overflow:hidden;">', unsafe_allow_html=True)
        _TH = "padding:9px 12px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748B;background:#F8FAFC;border-bottom:1.5px solid #E2E8F0;white-space:nowrap;"
        rows = ""
        for i, r in enumerate(reversed(_t7)):
            bg    = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
            dt    = str(r.get("기준일",""))[:10]
            rate  = _safe_float(r.get("가동률", 0))
            adm   = _safe_int(r.get("금일입원", 0))
            disc  = _safe_int(r.get("금일퇴원", 0))
            stay  = _safe_int(r.get("재원수", 0))
            rc    = _oc_color(rate)
            _td   = f"padding:9px 12px;background:{bg};border-bottom:1px solid #F1F5F9;"
            rows += (
                f"<tr>"
                f'<td style="{_td}color:#64748B;">{dt[5:]}</td>'
                f'<td style="{_td}font-weight:700;color:{rc};font-family:Consolas,monospace;text-align:right;">{rate:.1f}%</td>'
                f'<td style="{_td}font-family:Consolas,monospace;text-align:right;color:#1D4ED8;">{adm}</td>'
                f'<td style="{_td}font-family:Consolas,monospace;text-align:right;">{disc}</td>'
                f'<td style="{_td}font-family:Consolas,monospace;text-align:right;">{stay}</td>'
                f"</tr>"
            )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
            f'<thead><tr>'
            f'<th style="{_TH}text-align:left;">날짜</th>'
            f'<th style="{_TH}text-align:right;">가동률</th>'
            f'<th style="{_TH}text-align:right;color:#1D4ED8;">입원</th>'
            f'<th style="{_TH}text-align:right;">퇴원</th>'
            f'<th style="{_TH}text-align:right;">재원</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
#  탭 ④ — 주상병 분포
# ════════════════════════════════════════════════════════════════════

def _tab_dx(dx_today_f: List[Dict], dx_trend_f: List[Dict]) -> None:
    col_l, col_r = st.columns([1, 1], gap="medium")

    # ── 좌: 7일 주상병 (도넛) ─────────────────────────────────────────
    with col_l:
        st.markdown('<div class="wd-card" style="padding:16px 18px;">', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11.5px;font-weight:700;color:#0F172A;'
            'margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #F1F5F9;">'
            '최근 7일 주상병 분포</div>',
            unsafe_allow_html=True,
        )
        # dx_trend_f 집계
        from collections import Counter as _Cnt
        _cnt7: Dict[str, int] = {}
        for r in dx_trend_f:
            _k = r.get("주상병명", r.get("상병코드", "기타"))
            _cnt7[_k] = _cnt7.get(_k, 0) + int(r.get("건수", 1) or 1)
        _top7 = sorted(_cnt7.items(), key=lambda x: -x[1])[:10]

        if HAS_PLOTLY and _top7:
            _labs = [k for k, _ in _top7]
            _vals = [v for _, v in _top7]
            _clrs = ["#1E40AF","#3B82F6","#7C3AED","#A78BFA","#EC4899",
                     "#F43F5E","#F97316","#EAB308","#059669","#0891B2"]
            fig = go.Figure(go.Pie(
                labels=_labs, values=_vals, hole=0.5,
                marker=dict(colors=_clrs[:len(_labs)], line=dict(color="#fff", width=2)),
                textinfo="percent", textfont=dict(size=10, color="#fff"),
                hovertemplate="%{label}<br>%{value}건 (%{percent})<extra></extra>",
            ))
            fig.update_layout(
                showlegend=True, margin=dict(t=10,b=10,l=0,r=10),
                height=280, paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(font=dict(size=9.5), x=1.02, y=0.5, bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        elif _top7:
            _max_v = max(v for _, v in _top7) or 1
            for k, v in _top7:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">'
                    f'<div style="flex:1;font-size:11px;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{k}</div>'
                    f'<div style="width:80px;">{_trend_bar(v, _max_v, "#3B82F6", 5)}</div>'
                    f'<div style="width:28px;font-size:11px;font-weight:700;color:#1E40AF;text-align:right;">{v}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#94A3B8;">데이터 없음</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── 우: 금일 vs 전일 비교 ─────────────────────────────────────────
    with col_r:
        st.markdown('<div class="wd-card" style="padding:16px 18px;">', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11.5px;font-weight:700;color:#0F172A;'
            'margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #F1F5F9;">'
            '금일 주상병 현황</div>',
            unsafe_allow_html=True,
        )
        if dx_today_f:
            _sorted_today = sorted(dx_today_f, key=lambda r: -_safe_int(r.get("건수", 0)))[:15]
            _max_t = max((_safe_int(r.get("건수",0)) for r in _sorted_today), default=1)
            _TH2 = "padding:8px 12px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748B;background:#F8FAFC;border-bottom:1.5px solid #E2E8F0;"
            rows2 = ""
            for i, r in enumerate(_sorted_today):
                bg   = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                nm   = r.get("주상병명", r.get("상병코드", "—"))
                cd   = r.get("상병코드", "")
                cnt  = _safe_int(r.get("건수", 0))
                _td2 = f"padding:8px 12px;background:{bg};border-bottom:1px solid #F1F5F9;"
                rows2 += (
                    f"<tr>"
                    f'<td style="{_td2}">'
                    f'<span style="font-size:12px;font-weight:600;color:#0F172A;">{nm}</span>'
                    f'{"<br><span style=font-size:10px;color:#94A3B8;>" + cd + "</span>" if cd else ""}'
                    f'</td>'
                    f'<td style="{_td2}width:110px;">'
                    f'{_trend_bar(cnt, _max_t, "#3B82F6", 4)}'
                    f'<span style="font-size:11px;font-weight:700;color:#1E40AF;">{cnt}건</span>'
                    f'</td>'
                    f"</tr>"
                )
            st.markdown(
                f'<div style="overflow-y:auto;max-height:300px;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
                f'<thead><tr>'
                f'<th style="{_TH2}text-align:left;">상병명</th>'
                f'<th style="{_TH2}">건수</th>'
                f'</tr></thead><tbody>{rows2}</tbody></table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#94A3B8;">금일 데이터 없음</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
#  탭 ⑤ — 익일 예약 & 수용 현황
# ════════════════════════════════════════════════════════════════════

def _tab_next_day(
    bed_detail_f: List[Dict],
    admit_cands: List[Dict],
    total_rest: int, total_ndc_pre: int,
    next_adm: int, next_disc: int, next_op: int,
    adm_total: int, adm_done: int,
) -> None:
    total_avail = total_rest + total_ndc_pre
    cap_pct     = round(next_adm / max(total_avail, 1) * 100)
    cap_c       = _oc_color(cap_pct)

    # ── 수용률 패널 ────────────────────────────────────────────────────
    st.markdown(
        f'<div class="v2-cap-panel">'
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;">'
        f'<div>'
        f'<div class="v2-cap-title">익일 병상 수용 현황</div>'
        f'<div class="v2-cap-pct" style="color:{cap_c};">{cap_pct}'
        f'<span style="font-size:18px;font-weight:600;color:{cap_c};margin-left:2px;">%</span></div>'
        f'<div style="font-size:11px;color:#94A3B8;margin-top:4px;">'
        f'익일 입원 {next_adm}명 / 가용 {total_avail}병상</div>'
        f'</div>'
        f'<div style="display:flex;gap:28px;margin-top:4px;">'
        f'<div style="text-align:center;">'
        f'<div class="v2-stat-lbl">가용 병상</div>'
        f'<div class="v2-stat-val">{total_avail}<span class="v2-stat-unit">병상</span></div>'
        f'</div>'
        f'<div class="v2-divider"></div>'
        f'<div style="text-align:center;">'
        f'<div class="v2-stat-lbl">잔여 병상</div>'
        f'<div class="v2-stat-val">{total_rest}<span class="v2-stat-unit">병상</span></div>'
        f'</div>'
        f'<div class="v2-divider"></div>'
        f'<div style="text-align:center;">'
        f'<div class="v2-stat-lbl">퇴원 예고</div>'
        f'<div class="v2-stat-val">{total_ndc_pre}<span class="v2-stat-unit">명</span></div>'
        f'</div>'
        f'<div class="v2-divider"></div>'
        f'<div style="text-align:center;">'
        f'<div class="v2-stat-lbl">익일 예약</div>'
        f'<div class="v2-stat-val">{next_adm}<span class="v2-stat-unit">명</span></div>'
        f'</div>'
        f'<div class="v2-divider"></div>'
        f'<div style="text-align:center;">'
        f'<div class="v2-stat-lbl">익일 퇴원</div>'
        f'<div class="v2-stat-val">{next_disc}<span class="v2-stat-unit">명</span></div>'
        f'</div>'
        f'<div class="v2-divider"></div>'
        f'<div style="text-align:center;">'
        f'<div class="v2-stat-lbl">익일 수술</div>'
        f'<div class="v2-stat-val">{next_op}<span class="v2-stat-unit">건</span></div>'
        f'</div>'
        f'</div></div>'
        f'<div class="v2-cap-bar-track">'
        f'<div style="width:{min(cap_pct,100)}%;height:100%;background:{cap_c};border-radius:9999px;"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 입원 예약 상세 + 빈병상 ────────────────────────────────────────
    col_l, col_r = st.columns([3, 2], gap="medium")

    with col_l:
        st.markdown('<div class="wd-card" style="padding:0;overflow:hidden;">', unsafe_allow_html=True)
        _TH = "padding:9px 12px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748B;background:#F8FAFC;border-bottom:1.5px solid #E2E8F0;white-space:nowrap;"
        st.markdown(
            f'<div style="padding:12px 14px 10px;border-bottom:1px solid #F1F5F9;">'
            f'<span style="font-size:11.5px;font-weight:700;color:#0F172A;">입원 예약 상세</span>'
            f'<span style="font-size:11px;color:#94A3B8;margin-left:8px;">총 {adm_total}건 · 완료 {adm_done}건</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if admit_cands:
            rows = ""
            _ST_CLR = {"AD": ("#16A34A","#DCFCE7"), "RQ": ("#F59E0B","#FEF3C7"),
                       "CN": ("#EF4444","#FEE2E2")}
            for i, r in enumerate(admit_cands[:20]):
                bg     = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
                nm     = r.get("환자명","")[:3] + "**" if len(r.get("환자명","")) > 2 else "**"
                dept   = r.get("진료과명","—")
                room   = r.get("희망병실","—")
                st_cd  = r.get("수속상태","")
                sc, sb = _ST_CLR.get(st_cd, ("#64748B","#F1F5F9"))
                st_lbl = {"AD":"수속완료","RQ":"예약","CN":"취소"}.get(st_cd, st_cd)
                dt     = str(r.get("예약일",""))[:10]
                _td    = f"padding:8px 12px;background:{bg};border-bottom:1px solid #F1F5F9;"
                rows += (
                    f"<tr>"
                    f'<td style="{_td}font-weight:600;">{nm}</td>'
                    f'<td style="{_td}color:#475569;">{dept}</td>'
                    f'<td style="{_td}color:#64748B;">{room}</td>'
                    f'<td style="{_td}">'
                    f'<span style="background:{sb};color:{sc};border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;">{st_lbl}</span>'
                    f'</td>'
                    f'<td style="{_td}color:#94A3B8;">{dt}</td>'
                    f"</tr>"
                )
            st.markdown(
                f'<div style="overflow-y:auto;max-height:280px;">'
                f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
                f'<thead><tr>'
                f'<th style="{_TH}text-align:left;">환자</th>'
                f'<th style="{_TH}">진료과</th>'
                f'<th style="{_TH}">희망병실</th>'
                f'<th style="{_TH}">상태</th>'
                f'<th style="{_TH}">예약일</th>'
                f'</tr></thead><tbody>{rows}</tbody></table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div style="padding:24px;text-align:center;color:#94A3B8;">예약 데이터 없음</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="wd-card" style="padding:16px 18px;">', unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11.5px;font-weight:700;color:#0F172A;'
            'margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #F1F5F9;">'
            '병동별 익일 가용 현황</div>',
            unsafe_allow_html=True,
        )
        if bed_detail_f:
            for r in sorted(bed_detail_f,
                            key=lambda x: -(max(0, _safe_int(x.get("총병상")) -
                                              _safe_int(x.get("재원수"))) +
                                            _safe_int(x.get("익일퇴원예고", 0)))):
                wname  = r.get("병동명","")
                tot    = _safe_int(r.get("총병상"))
                stay   = _safe_int(r.get("재원수"))
                ndc    = _safe_int(r.get("익일퇴원예고", 0))
                rest   = max(0, tot - stay)
                avail  = rest + ndc
                _fc    = _oc_color(stay / max(tot, 1) * 100)
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:space-between;'
                    f'padding:7px 0;border-bottom:1px solid #F8FAFC;">'
                    f'<div style="font-size:12px;font-weight:600;color:#0F172A;">{wname}</div>'
                    f'<div style="display:flex;align-items:center;gap:10px;">'
                    f'<div style="width:80px;">{_trend_bar(stay, tot, _fc, 4)}</div>'
                    f'<span style="font-size:11px;font-weight:700;color:#059669;'
                    f'font-family:Consolas,monospace;min-width:28px;text-align:right;">{avail}</span>'
                    f'<span style="font-size:10px;color:#94A3B8;">병상</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
#  탭 ⑥ — AI 분석 채팅
# ════════════════════════════════════════════════════════════════════

def _tab_ai(kpi_ctx: Dict, bed_detail_f: List[Dict], op_stat_f: List[Dict]) -> None:
    from ui.hospital_dashboard import _render_ward_llm_chat

    _quick_qs = [
        ("운영 요약",     "오늘 병동 전체 운영 현황을 3줄로 요약해주세요."),
        ("익일 가용",     "익일 입원 예약 대비 가용 병상 현황을 분석하고, 부족 위험이 있는 병동을 알려주세요."),
        ("입퇴원 분석",   "금일 입원과 퇴원 현황을 분석하고 전일 대비 변화를 설명해주세요."),
        ("상병 추세",     "최근 7일 주요 입원 상병 추세를 분석하고 특이사항을 알려주세요."),
        ("재원 분석",     "병동별 재원 환자 현황을 분석하고 장기 재원 위험 병동을 알려주세요."),
    ]
    _qb = st.columns(len(_quick_qs), gap="small")
    for _qi, (_ql, _qv) in enumerate(_quick_qs):
        with _qb[_qi]:
            if st.button(_ql, key=f"v2_qs_{_qi}", use_container_width=True,
                         type="secondary", help=_qv[:50]):
                st.session_state["ward_chat_quick_input"] = _qv
                st.rerun()

    gap(8)
    _render_ward_llm_chat(
        kpi=kpi_ctx, bed_occ=[],
        bed_detail=bed_detail_f, op_stat=op_stat_f,
    )


# ════════════════════════════════════════════════════════════════════
#  메인 진입점
# ════════════════════════════════════════════════════════════════════

def render_ward_v2() -> None:
    """병동 대시보드 v2.0 — 관리자 대시보드 디자인 규칙."""
    st.markdown(APP_CSS + _V2_CSS, unsafe_allow_html=True)

    _oracle_ok = st.session_state.get("oracle_ok", False)

    # ── 데이터 조회 ────────────────────────────────────────────────────
    dept_stay   = _qc("ward_dept_stay")
    bed_detail  = _qc("ward_bed_detail")
    op_stat     = _qc("ward_op_stat")
    trend       = _qc("ward_kpi_trend")
    dx_today    = _qc("ward_dx_today")
    dx_trend    = _qc("ward_dx_trend")
    yesterday   = _qc("ward_yesterday")
    admit_cands = _qc("admit_candidates")

    # ── 병동 목록 / 선택 ──────────────────────────────────────────────
    _all_wards = ["전체"] + sorted({
        r.get("병동명","") for r in bed_detail
        if r.get("병동명","") and r.get("병동명","") != "전체"
    })
    _g_ward = st.session_state.get("ward_selected", "전체")

    # ── 헤더 (병동 선택 포함) ─────────────────────────────────────────
    _g_ward = _v2_header(_oracle_ok, _g_ward, _all_wards)
    st.session_state["ward_selected"] = _g_ward

    # ── 필터 적용 ─────────────────────────────────────────────────────
    if _g_ward != "전체":
        bed_detail_f = _filter_by_ward(bed_detail, _g_ward)
        op_stat_f    = _filter_by_ward(op_stat, _g_ward)
    else:
        bed_detail_f = bed_detail
        op_stat_f    = op_stat

    dept_stay_f = dept_stay
    trend_f     = _trend_dedup(trend)
    dx_today_f  = _filter_dx_ward(dx_today, _g_ward)
    dx_trend_f  = _filter_dx_ward(dx_trend, _g_ward)

    # ── KPI 계산 ──────────────────────────────────────────────────────
    total_bed  = sum(_safe_int(r.get("총병상"))   for r in bed_detail_f)
    admit_cnt  = sum(_safe_int(r.get("금일입원"))  for r in bed_detail_f)
    occupied   = sum(_safe_int(r.get("재원수"))    for r in bed_detail_f)
    disc_cnt   = sum(_safe_int(r.get("금일퇴원"))  for r in bed_detail_f)
    occ_rate   = round(occupied / max(total_bed, 1) * 100, 1)

    _ward_surg: Dict[str, int] = {}
    for _sr in op_stat_f:
        _sw = _sr.get("병동명","")
        _ward_surg[_sw] = _ward_surg.get(_sw, 0) + int(_sr.get("수술건수", 0) or 0)
    op_total = sum(_ward_surg.values())

    _yest_f = _filter_by_ward(yesterday, _g_ward) if _g_ward != "전체" else yesterday
    pa = sum(_safe_int(r.get("금일입원"))  for r in _yest_f)
    pd = sum(_safe_int(r.get("금일퇴원"))  for r in _yest_f)
    ps = sum(_safe_int(r.get("재원수"))    for r in _yest_f)
    if not _yest_f:
        pa, pd, ps = admit_cnt, disc_cnt, occupied

    _first_bed  = bed_detail[0] if bed_detail else {}
    next_op     = int(_first_bed.get("익일수술예약", 0) or 0)
    next_adm    = int(_first_bed.get("익일입원예약", 0) or 0)
    next_disc   = int(_first_bed.get("익일퇴원예약", 0) or 0)
    total_rest  = sum(max(0, _safe_int(r.get("총병상")) - _safe_int(r.get("재원수"))) for r in bed_detail_f)
    total_ndc   = sum(_safe_int(r.get("익일퇴원예고")) for r in bed_detail_f)
    adm_total   = len(admit_cands)
    adm_done    = sum(1 for r in admit_cands if r.get("수속상태","") == "AD")

    # ── KPI strip ─────────────────────────────────────────────────────
    _v2_kpi_strip(occ_rate, occupied, total_bed,
                  admit_cnt, disc_cnt, op_total,
                  pa, pd, ps, next_op)

    # ── 탭 ────────────────────────────────────────────────────────────
    _kpi_ctx = {
        "가동률": occ_rate, "재원수": occupied, "총병상": total_bed,
        "금일입원": admit_cnt, "금일퇴원": disc_cnt, "선택병동": _g_ward,
    }

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🏢 병동별 현황",
        "🏥 진료과 재원",
        "📈 주간 추이",
        "🩺 주상병 분포",
        "📅 익일 예약",
        "🤖 AI 분석",
    ])

    with tab1:
        gap(8)
        _tab_ward_detail(bed_detail_f, op_stat_f)

    with tab2:
        gap(8)
        _tab_dept_stay(dept_stay_f)

    with tab3:
        gap(8)
        _tab_trend(trend_f, occ_rate)

    with tab4:
        gap(8)
        _tab_dx(dx_today_f, dx_trend_f)

    with tab5:
        gap(8)
        _tab_next_day(
            bed_detail_f, admit_cands,
            total_rest, total_ndc,
            next_adm, next_disc, next_op,
            adm_total, adm_done,
        )

    with tab6:
        gap(8)
        _tab_ai(_kpi_ctx, bed_detail_f, op_stat_f)
