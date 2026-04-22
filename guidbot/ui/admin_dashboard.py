"""
ui/admin_dashboard.py  ─  좋은문화병원 관리자 대시보드 v5.0  (2026-04-22)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[v5.0 변경 — 디자인 시스템 통일]
  · APP_CSS (design.py) 를 기반 CSS 로 채택 → 병동/원무 대시보드와 동일한 토큰
  · KPI 카드: dark kpi-card → fn-kpi (design.py 표준 — 흰 카드 + 컬러 top border)
  · 섹션 헤더: _sec_header() → section_header() from design.py
  · 테이블: dt/th/td → wd-tbl/wd-th/wd-td (design.py 표준)
  · expander 제목 emoji 정리 (arrow_down 텍스트 누이 방지)
  · font-family 인라인 속성 완전 배제 유지
"""

from __future__ import annotations

import json
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

# ── design.py 단일 소스 임포트 ─────────────────────────────────────────
from ui.design import (
    C, APP_CSS,
    section_header, gap, kpi_card as _design_kpi_card,
    badge_html, topbar,
)

logger = get_logger(__name__, log_dir=settings.log_dir)


# ════════════════════════════════════════════════════════════════════════
#  관리자 전용 추가 CSS  (APP_CSS 위에 덮어쓰는 관리자 전용 규칙만)
# ════════════════════════════════════════════════════════════════════════
_ADMIN_CSS: str = """
<style>
/* ── 관리자 히어로 섹션 ─── */
.adm-hero {
  background: #0F172A;
  padding: 36px 0 32px;
  margin: 0 -.75rem 24px;
  position: relative; overflow: hidden;
}
.adm-hero::before {
  content: '';
  position: absolute; top: -60px; right: -60px;
  width: 320px; height: 320px;
  background: radial-gradient(circle, rgba(30,64,175,0.30) 0%, transparent 70%);
  pointer-events: none;
}
.adm-hero-title {
  font-size: 2.25rem; font-weight: 800; line-height: 1.10;
  letter-spacing: -.5px; color: #fff; margin: 0 0 8px;
  padding: 0 .75rem;
}
.adm-hero-sub {
  font-size: .9375rem; font-weight: 400;
  color: rgba(255,255,255,0.55); letter-spacing: -.2px;
  padding: 0 .75rem;
}

/* ── KPI 어두운 배경 strip ─── */
.adm-kpi-strip {
  background: #0F172A;
  margin: 0 -.75rem 24px;
  padding: 4px .75rem 28px;
}

/* ── 관리자 상태점 ─── */
.adm-dot {
  display: inline-block; width: 9px; height: 9px;
  border-radius: 50%; flex-shrink: 0; margin-right: 6px;
}
.adm-dot-ok   { background: #059669; box-shadow: 0 0 0 3px rgba(5,150,105,.20); }
.adm-dot-warn { background: #F59E0B; box-shadow: 0 0 0 3px rgba(245,158,11,.20); }
.adm-dot-err  { background: #DC2626; box-shadow: 0 0 0 3px rgba(220,38,38,.20); }

/* ── 진행률 바 (KPI 카드 내부) ─── */
.adm-pb-track { height: 3px; background: #F1F5F9; border-radius: 9999px; overflow: hidden; margin-top: 6px; }
.adm-pb-fill  { height: 3px; border-radius: 9999px; }

/* ── 서비스 카드 ─── */
.adm-svc-card {
  background: #fff; border: 1px solid #E2E8F0;
  border-radius: 12px; padding: 20px 18px 18px;
  box-shadow: 0 2px 8px rgba(15,23,42,.06);
  position: relative; transition: box-shadow 160ms ease, transform 160ms ease;
}
.adm-svc-card:hover { box-shadow: 0 6px 20px rgba(15,23,42,.12); transform: translateY(-2px); }
.adm-svc-badge {
  position: absolute; top: 14px; right: 14px;
  background: rgba(30,64,175,.10); color: #1E40AF;
  border: 1px solid rgba(30,64,175,.20); border-radius: 9999px;
  padding: 2px 9px; font-size: 10px; font-weight: 700; letter-spacing: .06em;
}
.adm-svc-icon { font-size: 22px; margin-bottom: 8px; }
.adm-svc-name { font-size: .9375rem; font-weight: 700; color: #0F172A; letter-spacing: -.2px; margin-bottom: 5px; }
.adm-svc-desc { font-size: 12px; color: #64748B; line-height: 1.55; margin-bottom: 14px; min-height: 36px; }
.adm-svc-btn  {
  display: inline-flex; align-items: center; gap: 5px;
  background: #1E40AF; color: #fff; text-decoration: none;
  padding: 6px 14px; border-radius: 20px;
  font-size: 12px; font-weight: 600; letter-spacing: -.1px;
  transition: background 120ms ease, transform 120ms ease;
}
.adm-svc-btn:hover { background: #1D4ED8; color: #fff; transform: translateY(-1px); }

/* ── 정보 카드 ─── */
.adm-info-card {
  background: #fff; border: 1px solid #E2E8F0;
  border-radius: 12px; padding: 20px 20px 16px;
  box-shadow: 0 2px 8px rgba(15,23,42,.06);
}
.adm-info-title {
  font-size: 13px; font-weight: 700; color: #0F172A; letter-spacing: -.2px;
  padding-bottom: 10px; margin-bottom: 2px;
  border-bottom: 1px solid #F1F5F9;
}
.adm-info-row {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 8px 0; border-bottom: 1px solid #F8FAFC;
  font-size: 13px; gap: 10px;
}
.adm-info-row:last-child { border-bottom: none; }
.adm-info-lbl { color: #64748B; font-weight: 400; flex-shrink: 0; }
.adm-info-val { color: #0F172A; font-weight: 600; text-align: right; word-break: break-all; max-width: 62%; }

/* ── 로그 박스 ─── */
.adm-log {
  background: #0F172A; border: 1px solid rgba(255,255,255,.07);
  border-radius: 10px; padding: 14px 16px;
  font-size: 11.5px; line-height: 1.75;
  max-height: 520px; overflow-y: auto; overflow-x: auto;
}
.adm-log pre {
  margin: 0; white-space: pre-wrap; word-break: break-all;
  font-family: "IBM Plex Mono", Consolas, "Courier New", monospace !important;
}
.adm-le { color: #fc8181; }
.adm-lw { color: #fcd34d; }
.adm-li { color: #6ee7b7; }
.adm-ld { color: rgba(148,163,184,.55); }

/* ── 경고 배너 ─── */
.adm-warn {
  background: rgba(245,158,11,.08); border: 1px solid rgba(245,158,11,.25);
  border-radius: 8px; padding: 10px 14px;
  font-size: 13px; color: #92400E; margin-bottom: 14px;
}

/* ── expander 오버라이드 (arrow 텍스트 노출 방지) ─── */
[data-testid="stExpander"] details summary svg { display: inline !important; }
[data-testid="stExpander"] details summary { font-size: 13px !important; font-weight: 600 !important; color: #0F172A !important; }
</style>
"""


def get_admin_css() -> str:
    """APP_CSS(design.py) + 관리자 전용 추가 CSS."""
    return APP_CSS + _ADMIN_CSS


# ── HTML 렌더 헬퍼 (완결형 블록 전용) ───────────────────────────────────
def _html(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


# ── 관리자 전용 KPI fn-kpi 카드 ─────────────────────────────────────────
def _adm_kpi(label: str, value: str, unit: str, sub: str,
             color: str, pct: Optional[float] = None) -> str:
    """fn-kpi 스타일 카드 HTML (design.py 표준과 동일한 클래스)."""
    bar = ""
    if pct is not None:
        w = f"{min(pct, 100):.1f}"
        bar = (
            f'<div class="adm-pb-track">'
            f'<div class="adm-pb-fill" style="width:{w}%;background:{color};"></div>'
            f'</div>'
        )
    return (
        f'<div class="fn-kpi" style="border-top:3px solid {color};">'
        f'<div class="fn-kpi-label">{label}</div>'
        f'<div class="fn-kpi-value" style="color:{color};">{value}'
        f'<span class="fn-kpi-unit">{unit}</span></div>'
        f'<div class="fn-kpi-sub">{sub}</div>'
        f'{bar}'
        f'</div>'
    )


# ── 정보 카드 HTML 헬퍼 ──────────────────────────────────────────────────
def _info_card(title: str, rows: List[Tuple[str, str]]) -> str:
    body = "".join(
        f'<div class="adm-info-row">'
        f'<span class="adm-info-lbl">{k}</span>'
        f'<span class="adm-info-val">{v}</span>'
        f'</div>'
        for k, v in rows
    )
    return f'<div class="adm-info-card"><div class="adm-info-title">{title}</div>{body}</div>'


# ── 테이블 HTML (design.py 표준 클래스) ─────────────────────────────────
def _table(headers: List[str], rows: List[List[str]], font_size: str = "12.5px") -> str:
    th = "".join(f'<th class="wd-th">{h}</th>' for h in headers)
    body = "".join(
        "<tr>" + "".join(f'<td class="wd-td">{c}</td>' for c in row) + "</tr>"
        for row in rows
    )
    return (
        f'<div style="overflow-x:auto;">'
        f'<table class="wd-tbl" style="font-size:{font_size};">'
        f'<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'
    )


# ══════════════════════════════════════════════════════════════════════════
#  헬퍼 — 시스템 정보
# ══════════════════════════════════════════════════════════════════════════

def _sys_stats() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "cpu_pct": None, "mem_pct": None,
        "mem_used_gb": None, "mem_total_gb": None,
        "disk_pct": None, "disk_free_gb": None,
        "proc_mb": None, "psutil": False,
    }
    try:
        import psutil
        out["psutil"]       = True
        out["cpu_pct"]      = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        out["mem_pct"]      = vm.percent
        out["mem_used_gb"]  = round(vm.used  / 1024**3, 1)
        out["mem_total_gb"] = round(vm.total / 1024**3, 1)
        du = psutil.disk_usage(str(_ROOT))
        out["disk_pct"]     = du.percent
        out["disk_free_gb"] = round(du.free  / 1024**3, 1)
        out["proc_mb"]      = round(psutil.Process().memory_info().rss / 1024**2, 1)
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
            "mb":    round(p.stat().st_size / 1024**2, 2) if p.exists() else None,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                     if p.exists() else "—",
        }
    for sub in ["doc_db", "query_db", "schema_db"]:
        fi = vs / sub / "index.faiss"
        result[sub] = {
            "exists": fi.exists(),
            "mb":    round(fi.stat().st_size / 1024**2, 2) if fi.exists() else None,
        }
    return result


def _doc_registry_stats() -> Dict[str, Any]:
    reg = _ROOT / "doc_registry.json"
    empty: Dict[str, Any] = {"total": 0, "unindexed": 0, "by_category": {}, "size_kb": 0}
    if not reg.exists():
        return empty
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return empty
        by_cat: Dict[str, int] = {}
        for d in data:
            c = d.get("category", "기타")
            by_cat[c] = by_cat.get(c, 0) + 1
        return {
            "total":       len(data),
            "unindexed":   sum(1 for d in data if not d.get("indexed", True)),
            "by_category": by_cat,
            "size_kb":     round(reg.stat().st_size / 1024, 1),
        }
    except Exception:
        return empty


def _load_doc_registry() -> List[Dict[str, Any]]:
    reg = _ROOT / "doc_registry.json"
    if not reg.exists():
        return []
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _load_faiss_docs(max_docs: int = 300) -> List[Dict[str, Any]]:
    pkl_path = _ROOT / "vector_store" / "index.pkl"
    if not pkl_path.exists():
        return []
    try:
        import pickle
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
        if not (isinstance(data, tuple) and len(data) >= 1):
            return []
        docs_dict = getattr(data[0], "_dict", {})
        result = []
        for doc_id, doc in list(docs_dict.items())[:max_docs]:
            meta = getattr(doc, "metadata", {}) or {}
            result.append({
                "청크ID":        str(doc_id)[:10],
                "파일명":        meta.get("source", "—"),
                "페이지":        str(meta.get("page", "—")),
                "카테고리":      meta.get("category", "—"),
                "내용(미리보기)": (getattr(doc, "page_content", "") or "")[:80],
            })
        return result
    except Exception as e:
        logger.warning(f"[Admin] FAISS pkl 로드 실패: {e}")
        return []


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
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


def _colorize(line: str) -> str:
    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lo = line.upper()
    if " ERROR "   in lo or lo.lstrip().startswith("ERROR"):
        return f'<span class="adm-le">{esc}</span>'
    if " WARNING " in lo or " WARN " in lo or lo.lstrip().startswith("WARNING"):
        return f'<span class="adm-lw">{esc}</span>'
    if " INFO "    in lo or lo.lstrip().startswith("INFO"):
        return f'<span class="adm-li">{esc}</span>'
    return f'<span class="adm-ld">{esc}</span>'


def _pct_str(v: Optional[float]) -> str:
    return f"{v:.0f}%" if v is not None else "—"


def _pct_color(val: Optional[float], warn: float = 70, err: float = 85) -> str:
    if val is None: return C["warn"]
    if val >= err:  return C["danger"]
    if val >= warn: return C["warn"]
    return C["ok"]


def _dot_cls(val: Optional[float], warn: float = 70, err: float = 85) -> str:
    if val is None: return "adm-dot adm-dot-warn"
    if val >= err:  return "adm-dot adm-dot-err"
    if val >= warn: return "adm-dot adm-dot-warn"
    return "adm-dot adm-dot-ok"


# ── 모니터링 / 챗봇 헬퍼 ──────────────────────────────────────────────────

def _events_jsonl_path() -> Path:
    return _log_dir() / "dashboard_events.jsonl"


def _read_monitor_events(n: int = 2000) -> List[Dict[str, Any]]:
    path = _events_jsonl_path()
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        events = []
        for ln in lines[-n:]:
            ln = ln.strip()
            if ln:
                try:
                    events.append(json.loads(ln))
                except Exception:
                    pass
        return events
    except Exception as e:
        logger.warning(f"[Admin] monitor events 읽기 실패: {e}")
        return []


def _chatbot_cfg_path() -> Path:
    return _ROOT / "config" / "chatbot_runtime.json"


def _get_chatbot_cfg() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "enabled":      True,
        "model":        getattr(settings, "llm_model", "gemini-2.5-pro"),
        "temperature":  getattr(settings, "llm_temperature", 0.1),
        "max_tokens":   getattr(settings, "llm_max_tokens", 8192),
        "thinking":     not getattr(settings, "llm_thinking_disabled", True),
        "top_k":        getattr(settings, "retrieve_top_k", 10),
        "rerank_top_n": getattr(settings, "rerank_top_n", 4),
    }
    path = _chatbot_cfg_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults


def _set_chatbot_cfg(cfg: Dict[str, Any]) -> None:
    path = _chatbot_cfg_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    logger.info(f"[Admin] 챗봇 설정 저장: {cfg}")


# ══════════════════════════════════════════════════════════════════════════
#  탭 1 — 운영 현황
# ══════════════════════════════════════════════════════════════════════════

def _tab_ops() -> None:
    sys_s     = _sys_stats()
    oracle_ok, oracle_msg = _oracle_status()

    topbar()

    # Hero
    _html(
        f'<div class="adm-hero">'
        f'<div class="adm-hero-title">운영 현황</div>'
        f'<div class="adm-hero-sub">'
        f'좋은문화병원 AI 시스템&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'{datetime.now().strftime("%Y년 %m월 %d일  %H:%M")}'
        f'</div></div>'
    )

    # KPI 카드 — fn-kpi (design.py 표준)
    cpu  = sys_s["cpu_pct"]
    mem  = sys_s["mem_pct"]
    disk = sys_s["disk_pct"]
    pmb  = sys_s["proc_mb"]
    has  = sys_s["psutil"]

    def _hint(foot: str) -> str:
        return foot if has else "psutil 미설치"

    o_color = C["ok"] if oracle_ok else C["danger"]
    o_dot   = f'<span class="adm-dot {"adm-dot-ok" if oracle_ok else "adm-dot-err"}"></span>'
    o_lbl   = "정상" if oracle_ok else "오류"

    kpis_html = [
        _adm_kpi("Oracle DB",    f'{o_dot}{o_lbl}',       "","Oracle 연결 " + (oracle_msg[:30] if oracle_msg else "정상"), o_color),
        _adm_kpi("CPU 사용률",   _pct_str(cpu),            "", _hint("현재 프로세서 부하"),        _pct_color(cpu, 60, 80), cpu),
        _adm_kpi("메모리",        _pct_str(mem),            "", _hint(f'{sys_s["mem_used_gb"]} / {sys_s["mem_total_gb"]} GB' if sys_s["mem_total_gb"] else ""), _pct_color(mem), mem),
        _adm_kpi("디스크",        _pct_str(disk),           "", _hint(f'여유 {sys_s["disk_free_gb"]} GB' if sys_s["disk_free_gb"] else ""), _pct_color(disk, 75, 90), disk),
        _adm_kpi("앱 메모리",    f'{pmb:.0f}' if pmb else "—", "MB", _hint("admin_app 프로세스"), C["indigo"]),
    ]

    cols = st.columns(len(kpis_html), gap="small")
    for col, html in zip(cols, kpis_html):
        col.markdown(html, unsafe_allow_html=True)

    gap(20)

    # 서비스 현황
    section_header("서비스 현황", "실행 중인 앱 포트 및 접속 주소", C["blue"])
    _ip  = "192.1.1.231"
    svcs = [
        ("8501", "🏥", "병동 대시보드",  "입퇴원 현황 · 병동 KPI · 환자 흐름 분석"),
        ("8502", "💬", "AI 챗봇",         "규정·지침 RAG 검색 · Gemini LLM 연동"),
        ("8503", "💼", "원무 대시보드",   "수납·미수금 · 외래 통계 · 지역 분석"),
        ("8504", "⚙️", "관리자 대시보드", "로그 · 벡터DB · 문서 관리  ★ 현재"),
    ]
    sc = st.columns(4, gap="small")
    for col, (port, icon, name, desc) in zip(sc, svcs):
        col.markdown(
            f'<div class="adm-svc-card">'
            f'<div class="adm-svc-badge">:{port}</div>'
            f'<div class="adm-svc-icon">{icon}</div>'
            f'<div class="adm-svc-name">{name}</div>'
            f'<div class="adm-svc-desc">{desc}</div>'
            f'<a class="adm-svc-btn" href="http://{_ip}:{port}/" target="_blank">접속 →</a>'
            f'</div>',
            unsafe_allow_html=True,
        )

    gap(20)
    st.divider()

    # 시스템 상세
    section_header("시스템 상세", "Oracle DB · 서버 환경")
    d1, d2 = st.columns(2, gap="medium")
    oc = C["ok"] if oracle_ok else C["danger"]
    with d1:
        _html(_info_card("Oracle DB 연결", [
            ("상태",      f'<span style="color:{oc};font-weight:700;">{"✓ 정상" if oracle_ok else "✗ 오류"}</span>'),
            ("메시지",    (oracle_msg or "—")[:55]),
            ("스키마",    "JAIN_WM"),
            ("접속 모드", "Thin Mode (python-oracledb)"),
        ]))
    with d2:
        uptime = "—"
        try:
            import psutil
            up = timedelta(seconds=time.time() - psutil.boot_time())
            uptime = f"{up.days}일 {up.seconds // 3600}시간"
        except ImportError:
            uptime = "psutil 미설치"
        _html(_info_card("서버 환경", [
            ("Python",     platform.python_version()),
            ("OS",         (platform.system() + " " + platform.release())[:46]),
            ("서버 업타임", uptime),
            ("현재 시각",   datetime.now().strftime("%Y-%m-%d  %H:%M:%S")),
        ]))


# ══════════════════════════════════════════════════════════════════════════
#  탭 2 — 로그 뷰어
# ══════════════════════════════════════════════════════════════════════════

def _tab_logs() -> None:
    topbar()
    section_header("로그 뷰어", "모듈별 로그 파일 탐색 · 키워드 검색 · 다운로드")

    modules = _list_log_modules()
    if not modules:
        st.info("로그 디렉토리에 파일이 없습니다.")
        return

    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 3], gap="small")
    with c1:
        sel_mod  = st.selectbox("모듈", modules, key="adm_log_mod")
    with c2:
        dates    = ["(최신)"] + _available_log_dates(sel_mod)
        sel_date = st.selectbox("날짜", dates, key="adm_log_date")
    with c3:
        sel_level = st.selectbox("레벨", ["전체", "ERROR", "WARNING", "INFO", "DEBUG"],
                                 key="adm_log_level")
    with c4:
        tail_opts = {"최근 200줄": 200, "최근 500줄": 500, "최근 1000줄": 1000, "전체": 999999}
        tail_lbl  = st.selectbox("표시 줄", list(tail_opts.keys()), key="adm_log_tail")
        tail_n    = tail_opts[tail_lbl]
    with c5:
        kw = st.text_input("키워드", placeholder="ERROR / 함수명 / 텍스트...",
                           key="adm_log_kw", label_visibility="collapsed")

    date_arg = None if sel_date == "(최신)" else sel_date
    raw = _read_log(sel_mod, date_arg)

    if raw is None:
        st.warning(f"파일 없음: {sel_mod}.log{'.' + date_arg if date_arg else ''}")
        return

    lines = raw.splitlines()
    total = len(lines)

    if sel_level != "전체":
        lines = [l for l in lines if f" {sel_level} " in l.upper() or f"|{sel_level}|" in l.upper()]
    if kw.strip():
        lines = [l for l in lines if kw.strip().lower() in l.lower()]

    err_n  = sum(1 for l in lines if " ERROR "   in l.upper())
    warn_n = sum(1 for l in lines if " WARNING " in l.upper() or " WARN " in l.upper())
    info_n = sum(1 for l in lines if " INFO "    in l.upper())

    m1, m2, m3, m4, m5 = st.columns(5, gap="small")
    m1.metric("전체 라인", f"{total:,}")
    m2.metric("필터 결과", f"{len(lines):,}")
    m3.metric("ERROR",     f"{err_n}")
    m4.metric("WARNING",   f"{warn_n}")
    m5.metric("INFO",      f"{info_n}")

    show    = lines[-tail_n:] if len(lines) > tail_n else lines
    colored = "\n".join(_colorize(l) for l in show)
    _html(f'<div class="adm-log"><pre>{colored}</pre></div>')

    gap(8)
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
        if st.button("30일 이상 로그 정리", key="adm_log_clean"):
            ld, cutoff, removed = _log_dir(), datetime.now() - timedelta(days=30), 0
            for f in ld.iterdir():
                if ".log." in f.name:
                    try:
                        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                            f.unlink(); removed += 1
                    except Exception:
                        pass
            st.success(f"{removed}개 파일 삭제 완료")


# ══════════════════════════════════════════════════════════════════════════
#  탭 3 — 벡터DB 관리
# ══════════════════════════════════════════════════════════════════════════

def _tab_vectordb() -> None:
    topbar()
    section_header("벡터DB 관리", "FAISS 인덱스 통계 · 문서 목록 · 파트별 재구축 · 백업/복구")

    vs  = _vector_store_stats()
    reg = _doc_registry_stats()
    fi  = vs.get("index.faiss", {})

    # KPI
    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.metric("메인 인덱스", "있음" if fi.get("exists") else "없음")
    k2.metric("인덱스 크기", f'{fi.get("mb","—")} MB')
    k3.metric("등록 문서",   f'{reg["total"]}건')
    k4.metric("인덱스 대기", f'{reg["unindexed"]}건',
              delta="재구축 필요" if reg["unindexed"] > 0 else None,
              delta_color="inverse")

    gap(16)
    ic1, ic2 = st.columns(2, gap="medium")
    with ic1:
        pi = vs.get("index.pkl", {})
        _html(_info_card("메인 벡터 인덱스", [
            ("index.faiss", f'{fi.get("mb","—")} MB' if fi.get("exists") else "없음"),
            ("index.pkl",   f'{pi.get("mb","—")} MB' if pi.get("exists") else "없음"),
            ("마지막 수정",  fi.get("mtime", "—")),
            ("저장 위치",    str(_ROOT / "vector_store")[:50]),
        ]))
    with ic2:
        by_cat  = reg.get("by_category", {})
        cat_str = " · ".join(f"{k} {v}건" for k, v in list(by_cat.items())[:3]) or "—"
        _html(_info_card("문서 레지스트리", [
            ("총 등록 문서",    f'{reg["total"]}건'),
            ("인덱스 대기",     f'{reg["unindexed"]}건'),
            ("카테고리",        cat_str),
            ("레지스트리 크기", f'{reg.get("size_kb","—")} KB'),
        ]))

    gap(16)
    sub_label = {"doc_db": "규정집", "query_db": "쿼리 예제", "schema_db": "테이블 명세"}
    rows = []
    for key in ["doc_db", "query_db", "schema_db"]:
        s   = vs.get(key, {})
        sz  = f'{s.get("mb","—")} MB' if s.get("exists") else "없음"
        bge = badge_html("정상", "ok") if s.get("exists") else badge_html("미생성", "warn")
        rows.append([f"<b>{key}</b>", sub_label[key], sz, bge])
    _html(_table(["인덱스", "용도", "크기", "상태"], rows))

    # ── 파트별 재구축 ───────────────────────────────────────────────────
    gap(16)
    st.divider()
    section_header("인덱스 재구축", "파트별 또는 전체 재구축")
    _html('<div class="adm-warn">⚠️ 재구축은 수 분 소요됩니다. 재구축 중 챗봇 응답이 느려질 수 있습니다.</div>')

    r1, r2, r3 = st.columns(3, gap="small")
    with r1:
        if st.button("규정집 재구축 (doc_db)", key="adm_rb_doc", use_container_width=True):
            prog = st.progress(0, text="규정집 재구축 중...")
            try:
                from db.knowledge_db_builder import rebuild_doc_index
                rebuild_doc_index(); prog.progress(100, text="완료")
                st.success("규정집 인덱스 완료")
            except AttributeError:
                try:
                    from db.knowledge_db_builder import rebuild_vector_store
                    rebuild_vector_store(part="doc_db")
                    prog.progress(100, text="완료"); st.success("규정집 인덱스 완료")
                except Exception as e2:
                    prog.empty(); st.error(f"오류: {e2}")
            except Exception as e:
                prog.empty(); st.error(f"오류: {e}")
    with r2:
        if st.button("쿼리예제 재구축 (query_db)", key="adm_rb_query", use_container_width=True):
            prog = st.progress(0, text="쿼리 예제 재구축 중...")
            try:
                from db.knowledge_db_builder import rebuild_query_index
                rebuild_query_index(); prog.progress(100, text="완료")
                st.success("쿼리 예제 인덱스 완료")
            except AttributeError:
                try:
                    from db.knowledge_db_builder import rebuild_vector_store
                    rebuild_vector_store(part="query_db")
                    prog.progress(100, text="완료"); st.success("쿼리 예제 인덱스 완료")
                except Exception as e2:
                    prog.empty(); st.error(f"오류: {e2}")
            except Exception as e:
                prog.empty(); st.error(f"오류: {e}")
    with r3:
        if st.button("스키마 재구축 (schema_db)", key="adm_rb_schema", use_container_width=True):
            prog = st.progress(0, text="스키마 재구축 중...")
            try:
                from db.schema_vector_store import rebuild_schema_index
                rebuild_schema_index(); prog.progress(100, text="완료")
                st.success("스키마 인덱스 완료")
            except Exception as e:
                prog.empty(); st.error(f"오류: {e}")

    r4, r5, r6 = st.columns(3, gap="small")
    with r4:
        if st.button("메인 전체 재구축", key="adm_rb_main", use_container_width=True):
            prog = st.progress(0, text="메인 재구축 중...")
            try:
                from db.knowledge_db_builder import rebuild_vector_store
                prog.progress(30, text="문서 로딩 중...")
                rebuild_vector_store(); prog.progress(100, text="완료")
                st.success("메인 인덱스 완료")
            except Exception as e:
                prog.empty(); st.error(f"오류: {e}")
    with r5:
        if st.button("전체 재구축 (메인+스키마)", key="adm_rb_all", use_container_width=True):
            prog = st.progress(0, text="전체 재구축 시작..."); errs = []
            try:
                from db.knowledge_db_builder import rebuild_vector_store
                prog.progress(20, text="메인 재구축 중..."); rebuild_vector_store()
                prog.progress(60, text="스키마 재구축 중...")
            except Exception as e:
                errs.append(f"메인: {e}")
            try:
                from db.schema_vector_store import rebuild_schema_index
                rebuild_schema_index(); prog.progress(100, text="완료")
            except Exception as e:
                errs.append(f"스키마: {e}")
            if errs:
                st.error(" | ".join(errs))
            else:
                st.success("전체 재구축 완료")
    with r6:
        if st.button("백업 생성", key="adm_backup", use_container_width=True):
            with st.spinner("백업 생성 중..."):
                try:
                    import shutil
                    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dst = _ROOT / "vector_store_backup" / ts
                    shutil.copytree(str(_ROOT / "vector_store"), str(dst))
                    st.success(f"백업 완료 → vector_store_backup/{ts}")
                except Exception as e:
                    st.error(f"백업 오류: {e}")

    # 백업 목록
    bk_dir = _ROOT / "vector_store_backup"
    if bk_dir.exists():
        bks = sorted([d for d in bk_dir.iterdir() if d.is_dir()], reverse=True)
        if bks:
            gap(8)
            with st.expander(f"백업 목록  ({len(bks)}개)  — 선택 후 복구", expanded=False):
                bk_names = [b.name for b in bks[:10]]
                sel_bk   = st.selectbox("복구할 백업", bk_names, key="adm_sel_backup")
                rc1, _   = st.columns([2, 6])
                with rc1:
                    if st.button("선택 백업으로 복구", key="adm_restore",
                                 use_container_width=True, type="primary"):
                        try:
                            import shutil
                            vs_path = _ROOT / "vector_store"
                            ets     = datetime.now().strftime("restore_before_%Y%m%d_%H%M%S")
                            shutil.copytree(str(vs_path), str(bk_dir / ets))
                            shutil.rmtree(str(vs_path))
                            shutil.copytree(str(bk_dir / sel_bk), str(vs_path))
                            st.success(f"복구 완료: {sel_bk}")
                        except Exception as e:
                            st.error(f"복구 오류: {e}")
                rows_bk = []
                for b in bks[:10]:
                    mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    mb    = sum(f.stat().st_size for f in b.rglob("*") if f.is_file()) / 1024**2
                    rows_bk.append([b.name, mtime, f"{mb:.1f} MB"])
                _html(_table(["백업명", "생성일시", "크기"], rows_bk, "12px"))

    # ── 문서 목록 브라우저 ──────────────────────────────────────────────
    gap(8)
    st.divider()
    section_header("인덱스된 문서 목록", "doc_registry.json 기반", C["ok"])

    all_docs = _load_doc_registry()
    if not all_docs:
        st.info("doc_registry.json 이 없거나 비어 있습니다.")
    else:
        f1, f2, f3 = st.columns([2, 2, 4], gap="small")
        cats = sorted(set(d.get("category", "기타") for d in all_docs))
        with f1:
            sel_cat = st.selectbox("카테고리", ["전체"] + cats, key="adm_vdb_cat")
        with f2:
            idx_opts = {"전체": None, "인덱스됨": True, "미인덱스": False}
            sel_idx  = st.selectbox("인덱스", list(idx_opts.keys()), key="adm_vdb_idx")
        with f3:
            doc_kw = st.text_input("파일명 검색", key="adm_vdb_kw",
                                   label_visibility="collapsed",
                                   placeholder="파일명 일부 입력...")

        filtered = all_docs
        if sel_cat != "전체":
            filtered = [d for d in filtered if d.get("category", "기타") == sel_cat]
        if idx_opts[sel_idx] is not None:
            filtered = [d for d in filtered if bool(d.get("indexed", True)) == idx_opts[sel_idx]]
        if doc_kw.strip():
            kw_l = doc_kw.strip().lower()
            filtered = [d for d in filtered
                        if kw_l in str(d.get("name", d.get("filename", ""))).lower()
                        or kw_l in str(d.get("file_path", "")).lower()]

        st.caption(f"총 {len(all_docs)}건 중 {len(filtered)}건")
        if filtered:
            rows_doc = []
            for d in filtered[:200]:
                name    = d.get("name") or d.get("filename") or d.get("file_path", "—")
                name    = Path(str(name)).name if name != "—" else "—"
                indexed = d.get("indexed", True)
                bge     = badge_html("인덱스됨", "ok") if indexed else badge_html("대기중", "warn")
                cat     = d.get("category", "기타")
                added   = str(d.get("added_at", d.get("created_at", "—")))[:16]
                rows_doc.append([name, bge, cat, added])
            _html(_table(["파일명", "상태", "카테고리", "등록일시"], rows_doc, "12px"))

    gap(8)
    with st.expander("FAISS 인덱스 청크 미리보기 (index.pkl)", expanded=False):
        with st.spinner("로딩 중..."):
            faiss_docs = _load_faiss_docs(300)
        if not faiss_docs:
            st.info("FAISS index.pkl 파일이 없거나 읽을 수 없습니다.")
        else:
            st.caption(f"청크 {len(faiss_docs)}건 (최대 300건)")
            try:
                import pandas as pd
                st.dataframe(pd.DataFrame(faiss_docs), use_container_width=True,
                             hide_index=True, height=min(380, len(faiss_docs) * 35 + 40))
            except ImportError:
                rows_f = [[d["청크ID"], d["파일명"], d["페이지"], d["카테고리"], d["내용(미리보기)"]]
                          for d in faiss_docs[:50]]
                _html(_table(["청크ID", "파일명", "페이지", "카테고리", "내용"], rows_f, "11.5px"))


# ══════════════════════════════════════════════════════════════════════════
#  탭 4 — 문서 관리
# ══════════════════════════════════════════════════════════════════════════

def _tab_docs() -> None:
    topbar()
    section_header("문서 관리", "규정집 · DB 명세서 · 쿼리 예제 업로드 및 인덱스 연동")
    try:
        from ui.doc_manager_ui import render_doc_manager_ui
        render_doc_manager_ui(admin_user="admin")
    except ImportError:
        st.error("`ui/doc_manager_ui.py` 를 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"문서 관리 UI 오류: {e}")
        logger.error(f"doc_manager_ui 오류: {e}", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════
#  탭 5 — 시스템 정보
# ══════════════════════════════════════════════════════════════════════════

def _tab_sysinfo() -> None:
    topbar()
    section_header("시스템 정보", "Python 환경 · 설치 패키지 · 설정 요약")

    s1, s2 = st.columns(2, gap="medium")
    with s1:
        _html(_info_card("환경 정보", [
            ("Python 버전",   platform.python_version()),
            ("플랫폼",        (platform.system() + " " + platform.release())[:46]),
            ("프로세서",      (platform.processor() or platform.machine())[:46]),
            ("프로젝트 루트", str(_ROOT)[:50]),
            ("로그 디렉토리", str(settings.log_dir)[:50]),
        ]))
    with s2:
        try:
            cfg_rows = [
                ("임베딩 모델", getattr(settings, "embedding_model", "—")),
                ("LLM 모델",    getattr(settings, "llm_model", "—")),
                ("청크 크기",   str(getattr(settings, "chunk_size", "—"))),
                ("검색 Top-K",  str(getattr(settings, "top_k", "—"))),
                ("Oracle DSN",  str(getattr(settings, "oracle_dsn", "—"))[:40]),
                ("Google API",  "••••••" + str(getattr(settings, "google_api_key", ""))[-4:]),
            ]
        except Exception:
            cfg_rows = [("설정 로드", "settings.py 확인 필요")]
        _html(_info_card("설정 요약", cfg_rows))

    gap(16)
    PKGS = [
        "streamlit", "langchain", "langchain-core", "langchain-community",
        "google-genai", "faiss-cpu", "sentence-transformers", "torch",
        "oracledb", "pydantic", "pandas", "plotly",
    ]
    import importlib.metadata as im
    rows_pkg = []
    for i in range(0, len(PKGS), 2):
        row = []
        for pkg in PKGS[i:i + 2]:
            try:
                ver = im.version(pkg)
                row += [badge_html(ver, "blue"), pkg]
            except Exception:
                row += [badge_html("미설치", "err"), pkg]
        rows_pkg.append(row)

    with st.expander("주요 패키지 버전", expanded=True):
        _html(_table(["버전", "패키지", "버전", "패키지"], rows_pkg, "12.5px"))


# ══════════════════════════════════════════════════════════════════════════
#  탭 6 — 챗봇 관리
# ══════════════════════════════════════════════════════════════════════════

def _tab_chatbot() -> None:
    topbar()
    section_header("챗봇 관리", "LLM 서비스 ON/OFF · 파라미터 조정 · 실시간 테스트")

    cfg = _get_chatbot_cfg()

    sa1, sa2 = st.columns([2, 6], gap="medium")
    with sa1:
        enabled = st.toggle("챗봇 서비스 활성화",
                            value=cfg.get("enabled", True),
                            key="adm_chatbot_enabled",
                            help="OFF → 챗봇 응답 중단 (재시작 후 반영)")
    with sa2:
        sc = C["ok"] if enabled else C["warn"]
        sl = "서비스 중" if enabled else "중지됨"
        _html(
            f'<div style="display:flex;align-items:center;gap:8px;padding:10px 0;">'
            f'<span class="adm-dot {"adm-dot-ok" if enabled else "adm-dot-warn"}"></span>'
            f'<span style="font-size:14px;font-weight:700;color:{sc};">{sl}</span>'
            f'<span style="font-size:12px;color:{C["t4"]};margin-left:8px;">포트 8502 · main.py</span>'
            f'</div>'
        )

    st.divider()
    section_header("LLM 파라미터", color=C["indigo"])

    p1, p2, p3 = st.columns(3, gap="medium")
    with p1:
        model_opts = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        cur_model  = cfg.get("model", model_opts[0])
        if cur_model not in model_opts:
            model_opts.insert(0, cur_model)
        new_model = st.selectbox("LLM 모델", model_opts,
                                 index=model_opts.index(cur_model), key="adm_chatbot_model")
    with p2:
        new_temp = st.slider("Temperature", 0.0, 1.0, float(cfg.get("temperature", 0.1)),
                             0.05, key="adm_chatbot_temp",
                             help="낮을수록 일관적, 높을수록 창의적")
    with p3:
        new_max_tok = st.slider("Max Tokens", 1024, 65536,
                                int(cfg.get("max_tokens", 8192)), 1024,
                                key="adm_chatbot_maxtok")

    q1, q2, q3 = st.columns(3, gap="medium")
    with q1:
        new_topk = st.slider("검색 Top-K", 3, 30, int(cfg.get("top_k", 10)), 1,
                             key="adm_chatbot_topk")
    with q2:
        new_rerank = st.slider("Rerank Top-N", 1, 10, int(cfg.get("rerank_top_n", 4)), 1,
                               key="adm_chatbot_rerank")
    with q3:
        new_thinking = st.toggle("Extended Thinking",
                                 value=bool(cfg.get("thinking", False)),
                                 key="adm_chatbot_thinking",
                                 help="Gemini 2.5 계열 전용. 응답 지연 증가.")

    if st.button("설정 저장", key="adm_chatbot_save", type="primary"):
        _set_chatbot_cfg({
            "enabled":      enabled,
            "model":        new_model,
            "temperature":  new_temp,
            "max_tokens":   new_max_tok,
            "top_k":        new_topk,
            "rerank_top_n": new_rerank,
            "thinking":     new_thinking,
            "saved_at":     datetime.now().isoformat(),
        })
        st.success("설정 저장 완료. 챗봇 서비스 재시작 후 반영됩니다.")

    st.divider()
    section_header("실시간 테스트 쿼리", color=C["teal"])
    tq1, tq2 = st.columns([7, 1], gap="small")
    with tq1:
        tq_input = st.text_input("테스트 쿼리",
                                 placeholder="예: 오늘 외래 환자 몇 명이에요?",
                                 key="adm_test_query", label_visibility="collapsed")
    with tq2:
        run_btn = st.button("실행", key="adm_test_run", use_container_width=True, type="primary")

    if run_btn and tq_input.strip():
        with st.spinner("RAG 파이프라인 실행 중..."):
            try:
                import time as _t
                _start = _t.time()
                from core.rag_pipeline import RAGPipeline
                _pipe = RAGPipeline()
                _ans  = ""
                for _step in _pipe.iter_steps(tq_input.strip()):
                    if isinstance(_step, dict) and "answer" in _step:
                        _ans = _step["answer"]; break
                _elapsed = round((_t.time() - _start) * 1000)
                if _ans:
                    _html(
                        f'<div class="adm-info-card" style="border-left:3px solid {C["teal"]};">'
                        f'<div class="adm-info-title">응답 '
                        f'<span style="font-size:11px;color:{C["t4"]};font-weight:400;">({_elapsed:,}ms)</span></div>'
                        f'<div style="font-size:13px;line-height:1.8;">{_ans}</div></div>'
                    )
                else:
                    st.warning("응답 없음")
            except Exception as e:
                st.error(f"파이프라인 오류: {e}")


# ══════════════════════════════════════════════════════════════════════════
#  탭 7 — 모니터링
# ══════════════════════════════════════════════════════════════════════════

def _tab_monitoring() -> None:
    topbar()
    section_header("모니터링", "접속 현황 · 오류율 · LLM 응답 지연 · 이벤트 로그")

    r1, r2 = st.columns([1, 9], gap="small")
    with r1:
        if st.button("새로고침", key="adm_mon_refresh", use_container_width=True):
            st.rerun()
    with r2:
        ev_range = st.selectbox(
            "조회 범위", ["최근 500건", "최근 1000건", "최근 3000건", "전체"],
            key="adm_mon_range", label_visibility="collapsed",
        )
    ev_n_map = {"최근 500건": 500, "최근 1000건": 1000, "최근 3000건": 3000, "전체": 99999}
    events   = _read_monitor_events(ev_n_map[ev_range])

    if not events:
        st.info("dashboard_events.jsonl 이 없거나 비어 있습니다. 대시보드 사용 시 자동 생성됩니다.")
        return

    from collections import defaultdict as _dd, Counter as _cnt

    total_ev   = len(events)
    err_ev     = sum(1 for e in events
                     if e.get("success") is False or e.get("event_type") == "error")
    llm_events = [e for e in events if e.get("elapsed_ms") is not None]
    avg_ms     = (int(sum(e["elapsed_ms"] for e in llm_events) / len(llm_events))
                  if llm_events else 0)

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.metric("총 이벤트",     f"{total_ev:,}")
    k2.metric("오류 이벤트",   f"{err_ev:,}",
              delta=f"{err_ev/total_ev*100:.1f}%" if total_ev else None,
              delta_color="inverse")
    k3.metric("LLM 쿼리",      f"{len(llm_events):,}")
    k4.metric("평균 응답(ms)", f"{avg_ms:,}")

    gap(16)

    try:
        import plotly.graph_objects as _go
        from ui.design import PLOTLY_CFG

        ch1, ch2 = st.columns(2, gap="medium")
        with ch1:
            hour_cnt: dict = _dd(int)
            for e in events:
                ts = e.get("timestamp", "")
                try:
                    h = int(ts[11:13]) if len(ts) >= 13 else -1
                    if 0 <= h < 24: hour_cnt[h] += 1
                except Exception:
                    pass
            hours  = list(range(24))
            counts = [hour_cnt.get(h, 0) for h in hours]
            fig1 = _go.Figure(_go.Bar(
                x=[f"{h:02d}시" for h in hours], y=counts,
                marker_color=C["blue"], opacity=0.85,
            ))
            fig1.update_layout(**{**PLOTLY_CFG, "title": "시간대별 이벤트 수", "height": 260,
                                  "margin": dict(l=10, r=10, t=36, b=20)})
            st.plotly_chart(fig1, use_container_width=True, key="adm_mon_hour")

        with ch2:
            type_cnt = _cnt(e.get("event_type", "unknown") for e in events)
            from ui.design import PLOTLY_PALETTE
            labels = list(type_cnt.keys())[:10]
            vals   = [type_cnt[lb] for lb in labels]
            fig2 = _go.Figure(_go.Bar(
                x=labels, y=vals,
                marker_color=PLOTLY_PALETTE[:len(labels)], opacity=0.85,
            ))
            fig2.update_layout(**{**PLOTLY_CFG, "title": "이벤트 타입 분포", "height": 260,
                                  "margin": dict(l=10, r=10, t=36, b=20)})
            st.plotly_chart(fig2, use_container_width=True, key="adm_mon_type")

        if llm_events:
            ms_vals = [e["elapsed_ms"] for e in llm_events if e.get("elapsed_ms", 0) < 120_000]
            if ms_vals:
                fig3 = _go.Figure(_go.Histogram(
                    x=ms_vals, nbinsx=30, marker_color=C["violet"], opacity=0.80,
                ))
                fig3.update_layout(**{**PLOTLY_CFG,
                                      "title": f"LLM 응답 시간 분포  (평균 {avg_ms:,}ms)",
                                      "xaxis_title": "응답시간 (ms)", "yaxis_title": "건수",
                                      "height": 220, "margin": dict(l=10, r=10, t=36, b=30)})
                st.plotly_chart(fig3, use_container_width=True, key="adm_mon_llm")

    except ImportError:
        st.info("plotly 미설치 — 차트를 표시할 수 없습니다.")

    gap(8)
    with st.expander("최근 이벤트 로그 (최대 50건)", expanded=False):
        recent = events[-50:][::-1]
        rows_ev = []
        for e in recent:
            ts   = e.get("timestamp", "")[:19]
            ok   = e.get("success")
            ok_h = (badge_html("OK", "ok") if ok else badge_html("ERR", "err")) if ok is not None else "—"
            ms   = e.get("elapsed_ms")
            rows_ev.append([
                ts,
                e.get("event_type", ""),
                e.get("action", ""),
                e.get("label", ""),
                f"{ms:,}ms" if ms else "—",
                ok_h,
            ])
        _html(_table(["시각", "타입", "액션", "레이블", "응답", "결과"], rows_ev, "12px"))


# ══════════════════════════════════════════════════════════════════════════
#  메인 렌더
# ══════════════════════════════════════════════════════════════════════════

def render_admin_dashboard() -> None:
    st.markdown(get_admin_css(), unsafe_allow_html=True)

    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "🖥️ 운영 현황",   "📋 로그 뷰어",  "🗄️ 벡터DB 관리",
        "📄 문서 관리",   "⚙️ 시스템 정보",
        "🤖 챗봇 관리",   "📊 모니터링",
    ])
    with t1: _tab_ops()
    with t2: _tab_logs()
    with t3: _tab_vectordb()
    with t4: _tab_docs()
    with t5: _tab_sysinfo()
    with t6: _tab_chatbot()
    with t7: _tab_monitoring()
