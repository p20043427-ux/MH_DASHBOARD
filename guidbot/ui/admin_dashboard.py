"""
ui/admin_dashboard.py  ─  좋은문화병원 관리자 대시보드 v3.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
디자인: Deep Blue Hospital System
  · 폰트 인라인 주입 제거 (CSS 클래스로만 제어 → 이중따옴표 충돌 완전 차단)
  · 주 색상: Navy #0f172a / Deep Blue #2563eb
  · 진행률 표시: CPU·메모리·디스크 Progress Bar
  · 서비스 카드: 포트 배지 + 채워진 CTA 버튼
  · Glassmorphism: hero/카드 overlay
"""

from __future__ import annotations

import platform
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from utils.logger import get_logger
from ui.design import C

logger = get_logger(__name__, log_dir=settings.log_dir)

# ── 관리자 전용 토큰 (design.py C 기반 + glassmorphism 전용값) ──────────
_C = {
    "navy":   C["navy"],       # #0F172A
    "blue":   "#2563EB",       # 관리자 강조 (design C["blue"] 보다 밝음)
    "blue2":  "#1D4ED8",
    "blue3":  "#60A5FA",
    "light":  "#F0F6FF",
    "white":  "#FFFFFF",
    "ds1":    "#1E293B",
    "ds2":    C["t2"],         # #334155
    "ok":     C["ok"],         # #059669
    "warn":   C["warn"],       # #F59E0B
    "err":    C["red"],        # #DC2626
    "t1":     C["t1"],         # #0F172A
    "t2":     "#475569",
    "t3":     C["t4"],         # #94A3B8
    "wt1":    "rgba(255,255,255,0.92)",
    "wt2":    "rgba(255,255,255,0.60)",
    "wt3":    "rgba(255,255,255,0.35)",
    "bdr_d":  "rgba(255,255,255,0.08)",
    "bdr_l":  "rgba(15,23,42,0.10)",
    "sh":     "0 4px 24px rgba(15,23,42,0.12),0 1px 6px rgba(15,23,42,0.06)",
    "sh2":    "0 8px 32px rgba(15,23,42,0.18)",
}


# ══════════════════════════════════════════════════════════════════════
#  CSS  ─  인라인 style 속성에 font-family를 절대 쓰지 않는다
#           모든 폰트 제어는 이 <style> 블록의 클래스에서만 수행
# ══════════════════════════════════════════════════════════════════════
def get_admin_css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');

/* ── 전역 폰트 강제 (클래스 기반) ─── */
.adm-root,
.adm-root *,
.adm-root p,
.adm-root span,
.adm-root div,
.adm-root h1,.adm-root h2,.adm-root h3,
.adm-root a,
.adm-root button,
.adm-root input,
.adm-root label,
.adm-root td,.adm-root th {{
  font-family: "Helvetica Neue","Noto Sans KR",Helvetica,Arial,sans-serif !important;
  -webkit-font-smoothing: antialiased;
}}

/* ── Streamlit 레이아웃 ─── */
header[data-testid="stHeader"] {{ display:none !important; }}
.main .block-container {{
  padding: 0 !important;
  max-width: 100% !important;
  background: transparent !important;
}}

/* ── 탭 ─── */
[data-testid="stTabs"] > div:first-child {{
  background: {_C["white"]} !important;
  border-bottom: 1px solid {_C["bdr_l"]} !important;
  padding: 0 48px !important;
  position: sticky !important;
  top: 0 !important;
  z-index: 100 !important;
  box-shadow: 0 1px 0 rgba(15,23,42,0.07) !important;
}}
[data-testid="stTabs"] [data-testid="stTab"] p,
[data-testid="stTabs"] [data-testid="stTab"] {{
  font-family: "Helvetica Neue","Noto Sans KR",Helvetica,Arial,sans-serif !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  letter-spacing: -0.1px !important;
  color: {_C["t2"]} !important;
  padding: 14px 0 !important;
  margin-right: 28px !important;
  border-bottom: 2px solid transparent !important;
}}
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] p,
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {{
  font-weight: 700 !important;
  color: {_C["navy"]} !important;
  border-bottom-color: {_C["blue"]} !important;
}}

/* ── Streamlit metric ─── */
[data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] label {{
  font-family: "Helvetica Neue","Noto Sans KR",Helvetica,Arial,sans-serif !important;
  font-size: 11px !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  font-weight: 700 !important;
  color: {_C["t3"]} !important;
}}
[data-testid="stMetricValue"] div {{
  font-family: "Helvetica Neue","Noto Sans KR",Helvetica,Arial,sans-serif !important;
  font-size: 1.7rem !important;
  font-weight: 700 !important;
  color: {_C["navy"]} !important;
  letter-spacing: -0.4px !important;
}}

/* ── 스크롤바 ─── */
::-webkit-scrollbar {{ width:5px; height:5px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:rgba(15,23,42,0.18); border-radius:9999px; }}

/* ════════════ 섹션 ════════════ */
.sec-hero {{
  background: {_C["navy"]};
  padding: 56px 48px 52px;
  position: relative;
  overflow: hidden;
}}
/* 히어로 배경 글로우 */
.sec-hero::before {{
  content: '';
  position: absolute;
  top: -60px; right: -60px;
  width: 360px; height: 360px;
  background: radial-gradient(circle, rgba(37,99,235,0.25) 0%, transparent 70%);
  pointer-events: none;
}}
.sec-kpi  {{ background:{_C["navy"]}; padding:0 48px 52px; }}
.sec-light {{ background:{_C["light"]}; padding:52px 48px 48px; }}
.sec-white {{ background:{_C["white"]}; padding:48px 48px 44px; }}

/* ── 타이포 ─── */
.t-hero-title {{
  font-size: 3rem;
  font-weight: 700;
  line-height: 1.10;
  letter-spacing: -0.5px;
  color: {_C["white"]};
  margin: 0 0 10px;
}}
.t-hero-sub {{
  font-size: 1rem;
  font-weight: 400;
  color: {_C["wt2"]};
  letter-spacing: -0.2px;
}}
.t-sec-title {{
  font-size: 1.75rem;
  font-weight: 700;
  color: {_C["navy"]};
  letter-spacing: -0.4px;
  margin: 0 0 6px;
}}
.t-sec-sub {{
  font-size: 0.9375rem;
  font-weight: 400;
  color: {_C["t2"]};
  letter-spacing: -0.1px;
  margin: 0 0 28px;
}}

/* ── KPI 카드 ─── */
.kpi-card {{
  background: {_C["ds1"]};
  border: 1px solid {_C["bdr_d"]};
  border-radius: 14px;
  padding: 20px 20px 18px;
  box-shadow: {_C["sh2"]};
  /* glass overlay */
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}}
.kpi-label {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: rgba(148,163,184,0.80);
  margin-bottom: 12px;
}}
.kpi-val {{
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1;
  color: {_C["white"]};
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}}
.kpi-foot {{
  font-size: 11.5px;
  color: rgba(148,163,184,0.65);
  letter-spacing: -0.1px;
  margin-bottom: 10px;
}}
/* Progress bar */
.pb-track {{
  height: 4px;
  background: rgba(255,255,255,0.10);
  border-radius: 9999px;
  overflow: hidden;
}}
.pb-fill {{
  height: 4px;
  border-radius: 9999px;
  transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}}

/* 상태 점 */
.dot {{
  display: inline-block;
  width: 9px; height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.dok  {{ background:{_C["ok"]};   box-shadow:0 0 0 3px rgba(16,185,129,0.20); }}
.dwrn {{ background:{_C["warn"]}; box-shadow:0 0 0 3px rgba(245,158,11,0.20); }}
.derr {{ background:{_C["err"]};  box-shadow:0 0 0 3px rgba(239,68,68,0.20); }}

/* ── 서비스 카드 ─── */
.svc-card {{
  background: {_C["white"]};
  border: 1px solid {_C["bdr_l"]};
  border-radius: 14px;
  padding: 22px 20px 20px;
  box-shadow: {_C["sh"]};
  position: relative;
  transition: box-shadow 180ms ease, transform 180ms ease;
}}
.svc-card:hover {{
  box-shadow: {_C["sh2"]};
  transform: translateY(-2px);
}}
.svc-badge {{
  position: absolute;
  top: 16px; right: 16px;
  background: rgba(37,99,235,0.10);
  color: {_C["blue"]};
  border: 1px solid rgba(37,99,235,0.20);
  border-radius: 9999px;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
}}
.svc-icon {{
  font-size: 24px;
  margin-bottom: 10px;
}}
.svc-name {{
  font-size: 1rem;
  font-weight: 700;
  color: {_C["navy"]};
  letter-spacing: -0.3px;
  margin-bottom: 6px;
}}
.svc-desc {{
  font-size: 13px;
  color: {_C["t2"]};
  line-height: 1.55;
  letter-spacing: -0.1px;
  margin-bottom: 16px;
  min-height: 38px;
}}
.svc-btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: {_C["blue"]};
  color: {_C["white"]};
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.1px;
  transition: background 150ms ease;
}}
.svc-btn:hover {{ background:{_C["blue2"]}; color:{_C["white"]}; }}
.svc-btn-arrow {{ font-size:12px; }}

/* ── 정보 카드 ─── */
.info-card {{
  background: {_C["white"]};
  border: 1px solid {_C["bdr_l"]};
  border-radius: 14px;
  padding: 22px 22px 18px;
  box-shadow: {_C["sh"]};
}}
.info-card-title {{
  font-size: 14px;
  font-weight: 700;
  color: {_C["navy"]};
  letter-spacing: -0.2px;
  padding-bottom: 12px;
  margin-bottom: 4px;
  border-bottom: 1px solid rgba(15,23,42,0.07);
}}
.info-row {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 9px 0;
  border-bottom: 1px solid rgba(15,23,42,0.05);
  font-size: 13.5px;
  gap: 12px;
}}
.info-row:last-child {{ border-bottom:none; }}
.info-lbl {{ color:{_C["t2"]}; font-weight:400; flex-shrink:0; }}
.info-val {{
  color:{_C["t1"]}; font-weight:600;
  text-align:right; word-break:break-all;
  max-width:62%;
}}

/* ── 로그 박스 ─── */
.log-wrap {{
  background: {_C["ds1"]};
  border: 1px solid {_C["bdr_d"]};
  border-radius: 12px;
  padding: 16px 18px;
  font-family: "IBM Plex Mono","Consolas","Courier New",monospace !important;
  font-size: 12px;
  line-height: 1.75;
  max-height: 540px;
  overflow-y: auto;
  overflow-x: auto;
}}
.log-wrap pre {{ margin:0; white-space:pre-wrap; word-break:break-all; }}
.le  {{ color:#fc8181; }}
.lw  {{ color:#fcd34d; }}
.li  {{ color:#6ee7b7; }}
.ld  {{ color:rgba(148,163,184,0.55); }}

/* ── 데이터 테이블 ─── */
.dt {{
  width:100%; border-collapse:collapse; font-size:13.5px;
}}
.dt thead tr {{
  background:rgba(15,23,42,0.04);
  border-bottom:1px solid rgba(15,23,42,0.10);
}}
.dt th {{
  text-align:left; padding:10px 14px;
  font-size:10px; font-weight:700;
  letter-spacing:0.08em; text-transform:uppercase;
  color:{_C["t3"]};
}}
.dt td {{
  padding:10px 14px;
  border-bottom:1px solid rgba(15,23,42,0.055);
  color:{_C["t1"]};
}}
.dt tr:last-child td {{ border-bottom:none; }}

/* ── 배지 ─── */
.badge {{
  display:inline-block; padding:2px 10px;
  border-radius:9999px; font-size:12px; font-weight:700;
}}
.b-ok   {{ background:rgba(16,185,129,0.12);  color:#065f46; }}
.b-warn {{ background:rgba(245,158,11,0.12);  color:#92400e; }}
.b-err  {{ background:rgba(239,68,68,0.12);   color:#991b1b; }}
.b-info {{ background:rgba(37,99,235,0.10);   color:{_C["blue"]}; }}

/* ── 경고 배너 ─── */
.warn-banner {{
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.25);
  border-radius: 10px;
  padding: 12px 16px;
  font-size: 13.5px;
  color: #92400e;
  margin-bottom: 16px;
}}
</style>
<div class="adm-root" style="display:none;"></div>
"""


# ── 폰트 클래스를 st.markdown 래퍼에 심는 헬퍼 ──────────────────────
def _html(content: str) -> None:
    """adm-root 클래스 wrapper 안에 렌더해서 폰트 클래스 상속."""
    st.markdown(f'<div class="adm-root">{content}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
#  헬퍼 — 시스템 정보
# ══════════════════════════════════════════════════════════════════════

def _sys_stats() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "cpu_pct": None, "mem_pct": None,
        "mem_used_gb": None, "mem_total_gb": None,
        "disk_pct": None, "disk_free_gb": None,
        "proc_mb": None, "psutil": False,
    }
    try:
        import psutil
        out["psutil"] = True
        out["cpu_pct"]     = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        out["mem_pct"]     = vm.percent
        out["mem_used_gb"] = round(vm.used  / 1024**3, 1)
        out["mem_total_gb"]= round(vm.total / 1024**3, 1)
        du = psutil.disk_usage(str(_ROOT))
        out["disk_pct"]    = du.percent
        out["disk_free_gb"]= round(du.free  / 1024**3, 1)
        out["proc_mb"]     = round(psutil.Process().memory_info().rss / 1024**2, 1)
    except ImportError:
        pass
    return out


def _oracle_status() -> Tuple[bool, str]:
    try:
        from db.oracle_client import test_connection
        ok, msg = test_connection()
        return ok, (msg or "")
    except Exception as e:
        return False, str(e)


def _vector_store_stats() -> Dict[str, Any]:
    vs = _ROOT / "vector_store"
    result: Dict[str, Any] = {}
    for fname in ["index.faiss", "index.pkl"]:
        p = vs / fname
        result[fname] = {
            "exists": p.exists(),
            "mb":     round(p.stat().st_size / 1024**2, 2) if p.exists() else None,
            "mtime":  datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                      if p.exists() else "—",
        }
    for sub in ["doc_db", "query_db", "schema_db"]:
        fi = vs / sub / "index.faiss"
        result[sub] = {
            "exists": fi.exists(),
            "mb":     round(fi.stat().st_size / 1024**2, 2) if fi.exists() else None,
        }
    return result


def _doc_registry_stats() -> Dict[str, Any]:
    reg = _ROOT / "doc_registry.json"
    empty: Dict[str, Any] = {"total": 0, "unindexed": 0, "by_category": {}, "size_kb": 0}
    if not reg.exists():
        return empty
    try:
        import json
        data = json.loads(reg.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return empty
        by_cat: Dict[str, int] = {}
        for d in data:
            c = d.get("category", "기타")
            by_cat[c] = by_cat.get(c, 0) + 1
        return {
            "total":      len(data),
            "unindexed":  sum(1 for d in data if not d.get("indexed", True)),
            "by_category": by_cat,
            "size_kb":    round(reg.stat().st_size / 1024, 1),
        }
    except Exception:
        return empty


def _log_dir() -> Path:
    return Path(settings.log_dir)


def _list_log_modules() -> List[str]:
    ld = _log_dir()
    if not ld.exists():
        return []
    names: set = set()
    for f in ld.iterdir():
        if ".log" in f.name:
            stem = f.name
            if ".log." in stem:
                stem = stem[:stem.index(".log.")]
            elif stem.endswith(".log"):
                stem = stem[:-4]
            if stem:
                names.add(stem)
    return sorted(names)


def _available_log_dates(module: str) -> List[str]:
    ld = _log_dir()
    prefix = f"{module}.log."
    return sorted(
        [f.name[len(prefix):] for f in ld.iterdir() if f.name.startswith(prefix)],
        reverse=True,
    )


def _read_log(module: str, date: Optional[str] = None) -> Optional[str]:
    ld = _log_dir()
    p = ld / (f"{module}.log.{date}" if date else f"{module}.log")
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _colorize(line: str) -> str:
    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lo = line.upper()
    if " ERROR " in lo or lo.lstrip().startswith("ERROR"):
        return f'<span class="le">{esc}</span>'
    if " WARNING " in lo or " WARN " in lo or lo.lstrip().startswith("WARNING"):
        return f'<span class="lw">{esc}</span>'
    if " INFO " in lo or lo.lstrip().startswith("INFO"):
        return f'<span class="li">{esc}</span>'
    return f'<span class="ld">{esc}</span>'


# ── KPI 카드 빌더 ──────────────────────────────────────────────────────

def _pb(pct: Optional[float], color: str = "#2563eb") -> str:
    """진행률 바 HTML."""
    w = f"{min(pct, 100):.1f}" if pct is not None else "0"
    return (
        f'<div class="pb-track">'
        f'<div class="pb-fill" style="width:{w}%;background:{color};"></div>'
        f'</div>'
    )


def _pct_color(val: Optional[float], warn: float = 70, err: float = 85) -> str:
    if val is None:
        return _C["warn"]
    if val >= err:
        return _C["err"]
    if val >= warn:
        return _C["warn"]
    return _C["ok"]


def _dot_cls(val: Optional[float], warn: float = 70, err: float = 85) -> str:
    if val is None:
        return "dot dwrn"
    if val >= err:
        return "dot derr"
    if val >= warn:
        return "dot dwrn"
    return "dot dok"


def _kpi_card(label: str, val_html: str, foot: str, pct: Optional[float] = None) -> str:
    bar = _pb(pct, _pct_color(pct)) if pct is not None else ""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-val">{val_html}</div>'
        f'<div class="kpi-foot">{foot}</div>'
        f'{bar}'
        f'</div>'
    )


# ══════════════════════════════════════════════════════════════════════
#  탭 1 — 운영 현황
# ══════════════════════════════════════════════════════════════════════

def _tab_ops() -> None:
    sys_s = _sys_stats()
    oracle_ok, oracle_msg = _oracle_status()

    # ── Hero ───────────────────────────────────────────────────────
    _html(
        f'<div class="sec-hero">'
        f'<div class="t-hero-title">운영 현황</div>'
        f'<div class="t-hero-sub">'
        f'좋은문화병원 AI 시스템&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'{datetime.now().strftime("%Y년 %m월 %d일  %H:%M")}'
        f'</div>'
        f'</div>'
    )

    # ── KPI 카드 행 ────────────────────────────────────────────────
    cpu  = sys_s["cpu_pct"]
    mem  = sys_s["mem_pct"]
    disk = sys_s["disk_pct"]
    pmb  = sys_s["proc_mb"]
    has_ps = sys_s["psutil"]

    o_dot = "dot dok" if oracle_ok else "dot derr"
    o_lbl = "정상" if oracle_ok else "오류"
    o_foot = oracle_msg[:44] if oracle_msg else "연결 정보 없음"

    def _pct_str(v: Optional[float]) -> str:
        return f"{v:.0f}%" if v is not None else "—"

    def _pct_foot_hint(has: bool, foot: str) -> str:
        return foot if has else "모니터링 라이브러리 없음"

    kpis = [
        _kpi_card(
            "Oracle DB",
            f'<span class="{o_dot}"></span>{o_lbl}',
            o_foot,
        ),
        _kpi_card(
            "CPU 사용률",
            f'<span class="{_dot_cls(cpu, 60, 80)}"></span>{_pct_str(cpu)}',
            _pct_foot_hint(has_ps, "현재 프로세서 부하"),
            cpu,
        ),
        _kpi_card(
            "메모리",
            f'<span class="{_dot_cls(mem)}"></span>{_pct_str(mem)}',
            _pct_foot_hint(
                has_ps,
                f'{sys_s["mem_used_gb"]} / {sys_s["mem_total_gb"]} GB'
                if sys_s["mem_total_gb"] else "",
            ),
            mem,
        ),
        _kpi_card(
            "디스크",
            f'<span class="{_dot_cls(disk, 75, 90)}"></span>{_pct_str(disk)}',
            _pct_foot_hint(
                has_ps,
                f'여유 {sys_s["disk_free_gb"]} GB' if sys_s["disk_free_gb"] else "",
            ),
            disk,
        ),
        _kpi_card(
            "앱 메모리",
            f'{f"{pmb:.0f} MB" if pmb else "—"}',
            _pct_foot_hint(has_ps, "admin_app 프로세스"),
        ),
    ]

    cols = st.columns(len(kpis), gap="small")
    for col, card_html in zip(cols, kpis):
        with col:
            _html(f'<div class="sec-kpi" style="padding:0;">{card_html}</div>')

    # 여백
    st.markdown('<div style="background:#0f172a;height:40px;"></div>', unsafe_allow_html=True)

    # ── 서비스 현황 (라이트) ───────────────────────────────────────
    _html(
        '<div class="sec-light">'
        '<div class="t-sec-title">서비스 현황</div>'
        '<div class="t-sec-sub">실행 중인 애플리케이션 포트 및 접속 주소</div>'
        '</div>'
    )

    _ip = "192.1.1.231"
    svcs = [
        ("8501", "🏥", "병동 대시보드",   "입퇴원 현황 · 병동 KPI · 환자 흐름 분석"),
        ("8502", "💬", "AI 챗봇",          "규정·지침 RAG 검색 · Gemini LLM 연동"),
        ("8503", "💼", "원무 대시보드",    "수납·미수금 · 외래 통계 · 지역 분석"),
        ("8504", "⚙️", "관리자 대시보드",  "로그 · 벡터DB · 문서 관리  ★ 현재"),
    ]
    sc = st.columns(4, gap="small")
    for col, (port, icon, name, desc) in zip(sc, svcs):
        with col:
            _html(
                f'<div class="svc-card">'
                f'<div class="svc-badge">PORT {port}</div>'
                f'<div class="svc-icon">{icon}</div>'
                f'<div class="svc-name">{name}</div>'
                f'<div class="svc-desc">{desc}</div>'
                f'<a class="svc-btn" href="http://{_ip}:{port}/" target="_blank">'
                f'접속하기<span class="svc-btn-arrow">→</span>'
                f'</a>'
                f'</div>'
            )

    # ── 시스템 상세 (흰색) ─────────────────────────────────────────
    _html(
        '<div class="sec-white">'
        '<div class="t-sec-title">시스템 상세</div>'
        '<div class="t-sec-sub">Oracle DB 연결 상태 · 서버 환경 정보</div>'
        '</div>'
    )

    d1, d2 = st.columns(2, gap="medium")
    oc = _C["ok"] if oracle_ok else _C["err"]
    with d1:
        rows_v = [
            ("상태",      f'<span style="color:{oc};font-weight:700;">{"✓ 정상" if oracle_ok else "✗ 오류"}</span>'),
            ("메시지",    (oracle_msg or "—")[:55]),
            ("스키마",    "JAIN_WM"),
            ("접속 모드", "Thin Mode (python-oracledb)"),
        ]
        body = "".join(
            f'<div class="info-row">'
            f'<span class="info-lbl">{k}</span>'
            f'<span class="info-val">{v}</span>'
            f'</div>'
            for k, v in rows_v
        )
        _html(f'<div class="info-card"><div class="info-card-title">Oracle DB 연결</div>{body}</div>')

    with d2:
        uptime = "—"
        try:
            import psutil
            up = timedelta(seconds=time.time() - psutil.boot_time())
            uptime = f"{up.days}일 {up.seconds // 3600}시간"
        except ImportError:
            uptime = "psutil 미설치"
        rows_v2 = [
            ("Python",    platform.python_version()),
            ("OS",        (platform.system() + " " + platform.release())[:46]),
            ("서버 업타임", uptime),
            ("현재 시각",  datetime.now().strftime("%Y-%m-%d  %H:%M:%S")),
        ]
        body2 = "".join(
            f'<div class="info-row">'
            f'<span class="info-lbl">{k}</span>'
            f'<span class="info-val">{v}</span>'
            f'</div>'
            for k, v in rows_v2
        )
        _html(f'<div class="info-card"><div class="info-card-title">서버 환경</div>{body2}</div>')


# ══════════════════════════════════════════════════════════════════════
#  탭 2 — 로그 뷰어
# ══════════════════════════════════════════════════════════════════════

def _tab_logs() -> None:
    _html(
        '<div class="sec-light" style="padding-bottom:0;">'
        '<div class="t-sec-title">로그 뷰어</div>'
        '<div class="t-sec-sub">모듈별 로그 파일 탐색 · 키워드 검색 · 다운로드</div>'
        '</div>'
    )
    _html('<div class="sec-white" style="padding-top:24px;">')

    modules = _list_log_modules()
    if not modules:
        st.info("로그 디렉토리에 파일이 없습니다.")
        _html("</div>")
        return

    c1, c2, c3 = st.columns([2, 2, 3], gap="small")
    with c1:
        sel_mod  = st.selectbox("모듈", modules, key="adm_log_mod")
    with c2:
        dates    = ["(최신)"] + _available_log_dates(sel_mod)
        sel_date = st.selectbox("날짜", dates, key="adm_log_date")
    with c3:
        kw = st.text_input("키워드 검색", placeholder="ERROR / WARNING / 텍스트...", key="adm_log_kw")

    date_arg = None if sel_date == "(최신)" else sel_date
    raw = _read_log(sel_mod, date_arg)

    if raw is None:
        st.warning(f"파일 없음: {sel_mod}.log{'.' + date_arg if date_arg else ''}")
        _html("</div>")
        return

    lines  = raw.splitlines()
    total  = len(lines)
    if kw.strip():
        lines = [l for l in lines if kw.strip().lower() in l.lower()]

    err_n  = sum(1 for l in lines if " ERROR "   in l.upper())
    warn_n = sum(1 for l in lines if " WARNING " in l.upper() or " WARN " in l.upper())

    m1, m2, m3, m4 = st.columns(4, gap="small")
    m1.metric("전체 라인",  f"{total:,}")
    m2.metric("필터 결과",  f"{len(lines):,}")
    m3.metric("ERROR",      f"{err_n}")
    m4.metric("WARNING",    f"{warn_n}")

    show = lines[-500:] if len(lines) > 500 else lines
    if len(lines) > 500:
        st.caption(f"최근 500줄 표시 (전체 {len(lines):,}줄)")

    colored = "\n".join(_colorize(l) for l in show)
    _html(f'<div class="log-wrap adm-root"><pre>{colored}</pre></div>')

    st.markdown("<br>", unsafe_allow_html=True)
    dl_c, cl_c = st.columns([2, 4], gap="small")
    with dl_c:
        st.download_button(
            "로그 다운로드",
            data=raw.encode("utf-8"),
            file_name=f"{sel_mod}_{date_arg or 'latest'}.log",
            mime="text/plain",
            key="adm_log_dl",
        )
    with cl_c:
        if st.button("30일 이상 로그 파일 정리", key="adm_log_clean"):
            ld, cutoff, removed = _log_dir(), datetime.now() - timedelta(days=30), 0
            for f in ld.iterdir():
                if ".log." in f.name:
                    try:
                        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                            f.unlink(); removed += 1
                    except Exception:
                        pass
            st.success(f"{removed}개 파일 삭제 완료")
            logger.info(f"관리자: 오래된 로그 {removed}개 정리")

    _html("</div>")


# ══════════════════════════════════════════════════════════════════════
#  탭 3 — 벡터DB 관리
# ══════════════════════════════════════════════════════════════════════

def _tab_vectordb() -> None:
    _html(
        '<div class="sec-light" style="padding-bottom:0;">'
        '<div class="t-sec-title">벡터DB 관리</div>'
        '<div class="t-sec-sub">FAISS 인덱스 통계 · 문서 레지스트리 · 재구축 · 백업</div>'
        '</div>'
    )
    _html('<div class="sec-white" style="padding-top:24px;">')

    vs  = _vector_store_stats()
    reg = _doc_registry_stats()
    fi  = vs.get("index.faiss", {})

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.metric("메인 인덱스", "존재" if fi.get("exists") else "없음")
    k2.metric("인덱스 크기", f'{fi.get("mb", "—")} MB')
    k3.metric("등록 문서",   f'{reg["total"]}건')
    k4.metric(
        "인덱스 대기",
        f'{reg["unindexed"]}건',
        delta="재구축 필요" if reg["unindexed"] > 0 else None,
        delta_color="inverse",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    ic1, ic2 = st.columns(2, gap="medium")

    with ic1:
        pi = vs.get("index.pkl", {})
        rows = [
            ("index.faiss", f'{fi.get("mb","—")} MB' if fi.get("exists") else "없음"),
            ("index.pkl",   f'{pi.get("mb","—")} MB' if pi.get("exists") else "없음"),
            ("마지막 수정", fi.get("mtime", "—")),
            ("저장 위치",   str(_ROOT / "vector_store")[:50]),
        ]
        body = "".join(
            f'<div class="info-row">'
            f'<span class="info-lbl">{k}</span>'
            f'<span class="info-val">{v}</span>'
            f'</div>'
            for k, v in rows
        )
        _html(f'<div class="info-card"><div class="info-card-title">메인 벡터 인덱스</div>{body}</div>')

    with ic2:
        by_cat = reg.get("by_category", {})
        cat_str = " · ".join(f"{k} {v}건" for k, v in list(by_cat.items())[:3]) or "—"
        rows2 = [
            ("총 등록 문서",   f'{reg["total"]}건'),
            ("인덱스 대기",    f'{reg["unindexed"]}건'),
            ("카테고리",       cat_str),
            ("레지스트리 크기", f'{reg.get("size_kb","—")} KB'),
        ]
        body2 = "".join(
            f'<div class="info-row">'
            f'<span class="info-lbl">{k}</span>'
            f'<span class="info-val">{v}</span>'
            f'</div>'
            for k, v in rows2
        )
        _html(f'<div class="info-card"><div class="info-card-title">문서 레지스트리</div>{body2}</div>')

    st.markdown("<br>", unsafe_allow_html=True)
    sub_rows = ""
    for key, label in [("doc_db","규정집"), ("query_db","쿼리 예제"), ("schema_db","테이블 명세")]:
        s     = vs.get(key, {})
        size  = f'{s.get("mb","—")} MB' if s.get("exists") else "없음"
        badge = '<span class="badge b-ok">정상</span>' if s.get("exists") else '<span class="badge b-warn">미생성</span>'
        sub_rows += (
            f'<tr><td><b>{key}</b></td>'
            f'<td style="color:{_C["t2"]};">{label}</td>'
            f'<td>{size}</td><td>{badge}</td></tr>'
        )
    _html(
        f'<table class="dt"><thead><tr>'
        f'<th>인덱스</th><th>용도</th><th>크기</th><th>상태</th>'
        f'</tr></thead><tbody>{sub_rows}</tbody></table>'
    )

    st.markdown("<br>", unsafe_allow_html=True)
    _html(
        '<div class="warn-banner">'
        '⚠️ 인덱스 재구축은 수 분이 소요될 수 있습니다. 재구축 중 챗봇 응답이 느려질 수 있습니다.'
        '</div>'
    )

    b1, b2, b3 = st.columns(3, gap="small")
    with b1:
        if st.button("메인 인덱스 재구축", key="adm_rb_main", use_container_width=True):
            with st.spinner("재구축 중..."):
                try:
                    from db.knowledge_db_builder import rebuild_vector_store
                    rebuild_vector_store()
                    st.success("메인 인덱스 재구축 완료")
                    logger.info("관리자: 메인 벡터 인덱스 재구축")
                except Exception as e:
                    st.error(f"오류: {e}")
    with b2:
        if st.button("스키마 인덱스 재구축", key="adm_rb_schema", use_container_width=True):
            with st.spinner("재구축 중..."):
                try:
                    from db.schema_vector_store import rebuild_schema_index
                    rebuild_schema_index()
                    st.success("스키마 인덱스 재구축 완료")
                    logger.info("관리자: 스키마 인덱스 재구축")
                except Exception as e:
                    st.error(f"오류: {e}")
    with b3:
        if st.button("백업 생성", key="adm_backup", use_container_width=True):
            with st.spinner("백업 생성 중..."):
                try:
                    import shutil
                    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dst = _ROOT / "vector_store_backup" / ts
                    shutil.copytree(str(_ROOT / "vector_store"), str(dst))
                    st.success(f"백업 완료: vector_store_backup/{ts}")
                    logger.info(f"관리자: 벡터 스토어 백업 → {ts}")
                except Exception as e:
                    st.error(f"백업 오류: {e}")

    bk_dir = _ROOT / "vector_store_backup"
    if bk_dir.exists():
        bks = sorted([d for d in bk_dir.iterdir() if d.is_dir()], reverse=True)
        if bks:
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander(f"백업 목록  ({len(bks)}개)", expanded=False):
                bk_rows = ""
                for b in bks[:8]:
                    mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d  %H:%M")
                    mb = sum(f.stat().st_size for f in b.rglob("*") if f.is_file()) / 1024**2
                    bk_rows += (
                        f'<tr><td>{b.name}</td>'
                        f'<td style="color:{_C["t2"]};">{mtime}</td>'
                        f'<td style="color:{_C["t2"]};">{mb:.1f} MB</td></tr>'
                    )
                _html(
                    f'<table class="dt"><thead><tr><th>백업명</th><th>생성일시</th><th>크기</th></tr></thead>'
                    f'<tbody>{bk_rows}</tbody></table>'
                )

    _html("</div>")


# ══════════════════════════════════════════════════════════════════════
#  탭 4 — 문서 관리
# ══════════════════════════════════════════════════════════════════════

def _tab_docs() -> None:
    _html(
        '<div class="sec-light" style="padding-bottom:0;">'
        '<div class="t-sec-title">문서 관리</div>'
        '<div class="t-sec-sub">규정집 · DB 명세서 · 쿼리 예제 업로드 및 인덱스 연동</div>'
        '</div>'
    )
    _html('<div class="sec-white" style="padding-top:24px;">')
    try:
        from ui.doc_manager_ui import render_doc_manager_ui
        render_doc_manager_ui(admin_user="admin")
    except ImportError:
        st.error("`ui/doc_manager_ui.py` 를 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"문서 관리 UI 오류: {e}")
        logger.error(f"doc_manager_ui 오류: {e}", exc_info=True)
    _html("</div>")


# ══════════════════════════════════════════════════════════════════════
#  탭 5 — 시스템 정보
# ══════════════════════════════════════════════════════════════════════

def _tab_sysinfo() -> None:
    _html(
        '<div class="sec-light" style="padding-bottom:0;">'
        '<div class="t-sec-title">시스템 정보</div>'
        '<div class="t-sec-sub">Python 환경 · 설치 패키지 · 설정 요약</div>'
        '</div>'
    )
    _html('<div class="sec-white" style="padding-top:24px;">')

    s1, s2 = st.columns(2, gap="medium")
    with s1:
        env = [
            ("Python 버전",   platform.python_version()),
            ("플랫폼",        (platform.system() + " " + platform.release())[:46]),
            ("프로세서",      (platform.processor() or platform.machine())[:46]),
            ("프로젝트 루트", str(_ROOT)[:50]),
            ("로그 디렉토리", str(settings.log_dir)[:50]),
        ]
        body = "".join(
            f'<div class="info-row">'
            f'<span class="info-lbl">{k}</span>'
            f'<span class="info-val">{v}</span>'
            f'</div>'
            for k, v in env
        )
        _html(f'<div class="info-card"><div class="info-card-title">환경 정보</div>{body}</div>')

    with s2:
        try:
            cfg = [
                ("임베딩 모델", getattr(settings, "embedding_model", "—")),
                ("LLM 모델",    getattr(settings, "llm_model", "—")),
                ("청크 크기",   str(getattr(settings, "chunk_size", "—"))),
                ("검색 Top-K",  str(getattr(settings, "top_k", "—"))),
                ("Oracle DSN",  str(getattr(settings, "oracle_dsn", "—"))[:40]),
                ("Google API",  "••••••" + str(getattr(settings, "google_api_key", ""))[-4:]),
            ]
        except Exception:
            cfg = [("설정 로드", "settings.py 확인 필요")]
        body2 = "".join(
            f'<div class="info-row">'
            f'<span class="info-lbl">{k}</span>'
            f'<span class="info-val">{v}</span>'
            f'</div>'
            for k, v in cfg
        )
        _html(f'<div class="info-card"><div class="info-card-title">설정 요약</div>{body2}</div>')

    st.markdown("<br>", unsafe_allow_html=True)
    PKGS = [
        "streamlit","langchain","langchain-core","langchain-community",
        "google-genai","faiss-cpu","sentence-transformers","torch",
        "oracledb","pydantic","pandas","plotly",
    ]
    import importlib.metadata as im
    rows_html = ""
    for i in range(0, len(PKGS), 2):
        row = ""
        for pkg in PKGS[i:i+2]:
            try:
                ver   = im.version(pkg)
                vcol  = _C["blue"]
            except Exception:
                ver   = "미설치"
                vcol  = _C["err"]
            row += (
                f'<td style="color:{vcol};font-size:13px;padding:10px 14px;font-variant-numeric:tabular-nums;">{ver}</td>'
                f'<td style="color:{_C["t1"]};padding:10px 14px;">{pkg}</td>'
            )
        rows_html += f"<tr>{row}</tr>"

    with st.expander("주요 패키지 버전", expanded=True):
        _html(
            f'<table class="dt" style="font-size:13px;">'
            f'<thead><tr><th>버전</th><th>패키지</th><th>버전</th><th>패키지</th></tr></thead>'
            f'<tbody>{rows_html}</tbody></table>'
        )

    _html("</div>")


# ══════════════════════════════════════════════════════════════════════
#  메인 렌더
# ══════════════════════════════════════════════════════════════════════

def render_admin_dashboard() -> None:
    st.markdown(get_admin_css(), unsafe_allow_html=True)

    t1, t2, t3, t4, t5 = st.tabs([
        "운영 현황", "로그 뷰어", "벡터DB 관리", "문서 관리", "시스템 정보",
    ])
    with t1: _tab_ops()
    with t2: _tab_logs()
    with t3: _tab_vectordb()
    with t4: _tab_docs()
    with t5: _tab_sysinfo()
