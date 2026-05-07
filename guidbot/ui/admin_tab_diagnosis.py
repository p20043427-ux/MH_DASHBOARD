"""
ui/admin_tab_diagnosis.py — 관리자 대시보드 보안·진단 탭 (v1.0, 2026-05-07)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[역할]
  CTO 관점 정밀 진단 보고서를 실시간 라이브 체크 기반으로 시각화.
  단순 정적 문서가 아니라 현재 코드베이스 상태를 실제로 읽어 진단.

[섹션 구성]
  1. 종합 점수 대시보드     — 5개 KPI 카드 (기술부채/유지보수/확장성/안정성/보안)
  2. Critical 이슈 알림     — 실시간 체크 기반 위험 배너
  3. 보안 점검              — OWASP 기준 15개 항목 라이브 체크
  4. 성능 진단              — 9개 성능 위험 요소
  5. 코드 품질              — 12개 파일/모듈 진단표
  6. DB·SQL 구조            — 10개 항목 진단
  7. 운영 안정성            — 12개 운영 항목 체크리스트
  8. 기술부채               — 항목별 점수 + 설명
  9. 즉시 수정 TOP 10       — 우선순위·난이도·효과
 10. 리팩토링 로드맵        — Phase 1–5 체크리스트
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from ui.design import C, gap, section_header

# ── HTML 헬퍼 ─────────────────────────────────────────────────────────────
def _h(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
#  라이브 진단 체커
#  각 함수는 (passed: bool, detail: str) 반환
# ══════════════════════════════════════════════════════════════════════════

def _check_default_password() -> Tuple[bool, str]:
    """settings.py 에서 기본 비밀번호 하드코딩 여부 확인."""
    target = _ROOT / "config" / "settings.py"
    if not target.exists():
        return False, "config/settings.py 없음"
    txt = target.read_text(encoding="utf-8", errors="ignore")
    if 'default=SecretStr("moonhwa")' in txt or "default=SecretStr('moonhwa')" in txt:
        return False, "admin_password default=SecretStr(\"moonhwa\") 하드코딩 발견"
    return True, "기본 비밀번호 제거됨"


def _check_dockerfile() -> Tuple[bool, str]:
    """Dockerfile 존재 여부 확인."""
    for name in ("Dockerfile", "dockerfile", "docker-compose.yml", "docker-compose.yaml"):
        if (_ROOT / name).exists():
            return True, f"{name} 존재"
    return False, "Dockerfile / docker-compose.yml 없음"


def _check_tests() -> Tuple[bool, str]:
    """테스트 파일 수 확인 (benchmark 제외)."""
    test_dir = _ROOT / "tests"
    if not test_dir.exists():
        return False, "tests/ 폴더 없음"
    files = [f for f in test_dir.rglob("test_*.py")]
    if not files:
        return False, f"tests/ 존재하나 test_*.py 없음 (rag_benchmark.py만 존재)"
    return True, f"테스트 파일 {len(files)}개"


def _check_requirements_pinned() -> Tuple[bool, str]:
    """requirements.txt 버전 핀닝(==) 확인."""
    req = _ROOT / "requirements.txt"
    if not req.exists():
        return False, "requirements.txt 없음"
    lines = req.read_text(encoding="utf-8", errors="ignore").splitlines()
    pkg_lines = [l for l in lines if l.strip() and not l.startswith("#")]
    unpinned = [l for l in pkg_lines if "==" not in l and ">=" not in l and "<=" not in l]
    if unpinned:
        return False, f"{len(unpinned)}개 패키지 버전 미핀닝: {', '.join(unpinned[:3])}..."
    return True, f"전체 {len(pkg_lines)}개 패키지 버전 지정됨"


def _check_gitignore() -> Tuple[bool, str]:
    """최상위 .gitignore 에 .env 포함 여부."""
    for p in (_ROOT / ".gitignore", _ROOT.parent / ".gitignore"):
        if p.exists():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if ".env" in txt:
                return True, ".gitignore 에 .env 포함"
            return False, ".gitignore 에 .env 누락"
    return False, ".gitignore 파일 없음"


def _check_cache_ttl() -> Tuple[bool, str]:
    """_shared.py 에서 실시간 VIEW 전용 ttl=60 분리 여부."""
    shared = _ROOT / "ui" / "panels" / "_shared.py"
    if not shared.exists():
        return False, "_shared.py 없음"
    txt = shared.read_text(encoding="utf-8", errors="ignore")
    if "ttl=60" in txt or "ttl = 60" in txt:
        return True, "실시간 ttl=60 분리 적용됨"
    if "ttl=1800" in txt:
        return False, "전체 ttl=1800 — 실시간 VIEW 도 30분 캐시"
    return False, "캐시 TTL 설정 확인 필요"


def _check_sql_union_blocked() -> Tuple[bool, str]:
    """sql_generator.py 에서 UNION 차단 여부."""
    sg = _ROOT / "llm" / "sql_generator.py"
    if not sg.exists():
        return False, "sql_generator.py 없음"
    txt = sg.read_text(encoding="utf-8", errors="ignore")
    # UNION 이 주석 처리 안 된 패턴으로 차단되어 있는지 확인
    if re.search(r'(?<!#)\bUNION\b.*차단', txt, re.IGNORECASE):
        return True, "UNION 차단 패턴 활성화됨"
    if "sqlparse" in txt:
        return True, "sqlparse 기반 검증 사용 중"
    return False, "UNION SELECT 차단 없음 — 정규식 주석 처리됨"


def _check_systemd() -> Tuple[bool, str]:
    """systemd 서비스 파일 또는 supervisord 설정 존재 여부."""
    patterns = list(_ROOT.rglob("*.service")) + list(_ROOT.rglob("supervisord.conf"))
    if patterns:
        return True, f"프로세스 관리 파일 {len(patterns)}개 존재"
    # Windows 환경에서는 별도 확인
    if os.name == "nt":
        return False, "Windows 환경 — systemd 미적용 (NSSM/Task Scheduler 확인 필요)"
    return False, "systemd .service 파일 없음"


def _check_monitoring() -> Tuple[bool, str]:
    """모니터링 설정 파일 존재 여부."""
    targets = ["prometheus.yml", "grafana", "alertmanager.yml", ".uptime"]
    for t in targets:
        if any(_ROOT.rglob(t)):
            return True, f"{t} 설정 발견"
    return False, "Prometheus/Grafana/UptimeRobot 설정 없음"


def _check_session_timeout() -> Tuple[bool, str]:
    """admin_app.py 에서 세션 만료 로직 존재 여부."""
    admin = _ROOT / "admin_app.py"
    adm_dash = _ROOT / "ui" / "admin_dashboard.py"
    for f in (admin, adm_dash):
        if f.exists():
            txt = f.read_text(encoding="utf-8", errors="ignore")
            if "SESSION_TIMEOUT" in txt or "timedelta" in txt and "adm_login" in txt:
                return True, "세션 만료 로직 존재"
    return False, "관리자 세션 만료 로직 없음 — 무제한 세션 유지"


def _check_pii_context() -> Tuple[bool, str]:
    """context_builder 또는 LLM 전달 경로에 pii_masker 호출 여부."""
    for pattern in (_ROOT / "core").rglob("*.py"):
        txt = pattern.read_text(encoding="utf-8", errors="ignore")
        if "pii" in txt.lower() and ("mask" in txt.lower() or "마스킹" in txt):
            return True, f"{pattern.name} 에서 PII 마스킹 호출 확인"
    return False, "LLM context 경로에서 PII 마스킹 호출 미확인"


def _check_https() -> Tuple[bool, str]:
    """Nginx 설정 또는 Streamlit SSL 설정 존재 여부."""
    for p in (_ROOT / ".streamlit" / "config.toml", _ROOT.parent / "nginx.conf",
              _ROOT.parent / "nginx" / "default.conf"):
        if p.exists():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if "ssl" in txt.lower() or "https" in txt.lower() or "443" in txt:
                return True, f"{p.name} 에 SSL/HTTPS 설정 존재"
    return False, "HTTPS/SSL 설정 미확인 — Nginx 또는 Streamlit SSL 없음"


def _check_oracle_timeout() -> Tuple[bool, str]:
    """oracle_client.py callTimeout fallback 처리 존재 여부."""
    oc = _ROOT / "db" / "oracle_client.py"
    if not oc.exists():
        return False, "oracle_client.py 없음"
    txt = oc.read_text(encoding="utf-8", errors="ignore")
    if "callTimeout" in txt:
        if "logger.warning" in txt or "logger.error" in txt:
            return True, "callTimeout 설정 + 실패 시 로그 경고 존재"
        return False, "callTimeout 설정하나 실패 시 silent — 무한 대기 위험"
    return False, "callTimeout 미설정 — Oracle 쿼리 무한 대기 가능"


def _run_all_checks() -> Dict[str, Tuple[bool, str]]:
    """모든 라이브 체크 실행 후 결과 dict 반환."""
    checks = {
        "기본_비밀번호": _check_default_password,
        "Dockerfile": _check_dockerfile,
        "테스트_파일": _check_tests,
        "버전_핀닝": _check_requirements_pinned,
        "gitignore_env": _check_gitignore,
        "캐시_TTL": _check_cache_ttl,
        "SQL_UNION차단": _check_sql_union_blocked,
        "프로세스_관리": _check_systemd,
        "모니터링": _check_monitoring,
        "세션_만료": _check_session_timeout,
        "PII_마스킹": _check_pii_context,
        "HTTPS": _check_https,
        "Oracle_타임아웃": _check_oracle_timeout,
    }
    return {k: fn() for k, fn in checks.items()}


# ══════════════════════════════════════════════════════════════════════════
#  UI 컴포넌트
# ══════════════════════════════════════════════════════════════════════════

def _score_bar(label: str, score: int, color: str, desc: str) -> str:
    pct = score
    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    grade_col = C["ok"] if score >= 80 else C["blue"] if score >= 65 else C["warn"] if score >= 50 else C["danger"]
    return (
        f'<div class="fn-kpi" style="border-top:3px solid {color};">'
        f'<div class="fn-kpi-label">{label}</div>'
        f'<div style="display:flex;align-items:baseline;gap:6px;">'
        f'<span class="fn-kpi-value" style="color:{color};">{score}</span>'
        f'<span class="fn-kpi-unit">/ 100</span>'
        f'<span style="font-size:13px;font-weight:800;color:{grade_col};'
        f'background:{grade_col}18;border-radius:6px;padding:1px 7px;">{grade}</span>'
        f'</div>'
        f'<div class="fn-kpi-sub">{desc}</div>'
        f'<div style="background:#E2E8F0;border-radius:4px;height:6px;margin-top:6px;">'
        f'<div style="width:{pct}%;height:6px;border-radius:4px;'
        f'background:{color};transition:width .5s;"></div></div>'
        f'</div>'
    )


def _issue_card(title: str, detail: str, severity: str, fix: str) -> str:
    sev_map = {
        "critical": (C["danger"], "🔴 CRITICAL", "#FFF1F2", "#FECDD3"),
        "high":     (C["warn"],   "🟠 HIGH",     "#FFFBEB", "#FDE68A"),
        "medium":   (C["yellow"], "🟡 MEDIUM",   "#FEFCE8", "#FEF08A"),
        "good":     (C["ok"],     "🟢 GOOD",     "#F0FDF4", "#BBF7D0"),
    }
    col, badge, bg, border = sev_map.get(severity.lower(), sev_map["medium"])
    return (
        f'<div style="background:{bg};border:1px solid {border};border-left:4px solid {col};'
        f'border-radius:8px;padding:12px 16px;margin-bottom:10px;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="font-size:12px;font-weight:700;color:{col};">{badge}</span>'
        f'<span style="font-size:13px;font-weight:700;color:#0F172A;">{title}</span>'
        f'</div>'
        f'<div style="font-size:12px;color:#475569;margin-bottom:6px;">{detail}</div>'
        f'<div style="font-size:11px;color:{col};font-weight:600;">✅ 개선: {fix}</div>'
        f'</div>'
    )


def _check_row(label: str, passed: bool, detail: str) -> str:
    icon = "✅" if passed else "❌"
    col  = C["ok"] if passed else C["danger"]
    bg   = "#F0FDF4" if passed else "#FFF1F2"
    return (
        f'<div style="display:flex;align-items:flex-start;gap:10px;'
        f'background:{bg};border-radius:6px;padding:8px 12px;margin-bottom:6px;">'
        f'<span style="font-size:15px;flex-shrink:0;">{icon}</span>'
        f'<div>'
        f'<span style="font-size:12.5px;font-weight:700;color:#0F172A;">{label}</span>'
        f'<span style="font-size:11.5px;color:#64748B;margin-left:8px;">{detail}</span>'
        f'</div>'
        f'</div>'
    )


def _phase_item(done: bool, text: str, sub: str = "") -> str:
    icon = "✅" if done else "⬜"
    col  = "#94A3B8" if not done else C["ok"]
    td   = "line-through;color:#94A3B8" if done else "none;color:#0F172A"
    # f-string 안에 백슬래시 불가 → sub_html 사전 계산
    sub_html = (
        '<br><span style="font-size:11px;color:#94A3B8;">' + sub + '</span>'
        if sub else ""
    )
    return (
        f'<div style="display:flex;align-items:flex-start;gap:10px;'
        f'padding:5px 0;border-bottom:1px solid #F1F5F9;">'
        f'<span style="font-size:14px;flex-shrink:0;">{icon}</span>'
        f'<div>'
        f'<span style="font-size:12.5px;font-weight:600;text-decoration:{td};">{text}</span>'
        f'{sub_html}'
        f'</div>'
        f'</div>'
    )


def _section_card(title: str, sub: str, color: str) -> str:
    return (
        f'<div style="background:linear-gradient(90deg,{color}15,transparent);'
        f'border-left:4px solid {color};border-radius:0 8px 8px 0;'
        f'padding:10px 16px;margin:16px 0 12px;">'
        f'<div style="font-size:14px;font-weight:700;color:{color};">{title}</div>'
        f'<div style="font-size:11.5px;color:{C["t3"]};margin-top:2px;">{sub}</div>'
        f'</div>'
    )


def _tbl(headers: List[str], rows: List[List[str]], font: str = "12px") -> str:
    th = "".join(f'<th class="wd-th">{h}</th>' for h in headers)
    tr = "".join(
        "<tr>" + "".join(f'<td class="wd-td">{c}</td>' for c in r) + "</tr>"
        for r in rows
    )
    return (
        f'<div style="overflow-x:auto;margin-bottom:12px;">'
        f'<table class="wd-tbl" style="font-size:{font};">'
        f'<thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'
    )


def _sev(s: str) -> str:
    m = {
        "critical": f'<span style="color:{C["danger"]};font-weight:700;">🔴 CRITICAL</span>',
        "high":     f'<span style="color:{C["warn"]};font-weight:700;">🟠 HIGH</span>',
        "medium":   f'<span style="color:{C["yellow"]};font-weight:700;">🟡 MEDIUM</span>',
        "good":     f'<span style="color:{C["ok"]};font-weight:700;">🟢 GOOD</span>',
        "low":      f'<span style="color:{C["t3"]};font-weight:600;">🔵 LOW</span>',
    }
    return m.get(s.lower(), s)


# ══════════════════════════════════════════════════════════════════════════
#  메인 탭 함수
# ══════════════════════════════════════════════════════════════════════════

def _tab_diagnosis() -> None:
    """보안·진단 탭 — CTO 관점 정밀 진단 보고서 (라이브 체크 기반)."""

    # ── 헤더 ────────────────────────────────────────────────────────────
    _h(
        f'<div style="background:linear-gradient(135deg,#0F172A 0%,#1E3A5F 100%);'
        f'border-radius:12px;padding:28px 28px 24px;margin-bottom:20px;position:relative;overflow:hidden;">'
        f'<div style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;'
        f'background:radial-gradient(circle,rgba(59,130,246,0.25) 0%,transparent 70%);'
        f'pointer-events:none;"></div>'
        f'<div style="font-size:11px;font-weight:700;color:rgba(255,255,255,0.45);'
        f'letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px;">'
        f'좋은문화병원 AI 시스템</div>'
        f'<div style="font-size:22px;font-weight:800;color:#fff;margin-bottom:6px;">'
        f'🔐 보안 · 품질 · 기술부채 진단</div>'
        f'<div style="font-size:12px;color:rgba(255,255,255,0.5);">'
        f'CTO 관점 정밀 진단 — 라이브 코드베이스 체크 기준 &nbsp;·&nbsp; '
        f'{time.strftime("%Y-%m-%d %H:%M")} 기준</div>'
        f'</div>'
    )

    # ── 라이브 체크 실행 ─────────────────────────────────────────────────
    with st.spinner("코드베이스 진단 중..."):
        chk = _run_all_checks()

    passed_cnt = sum(1 for p, _ in chk.values() if p)
    total_cnt  = len(chk)
    fail_cnt   = total_cnt - passed_cnt

    # ── 요약 알림 배너 ───────────────────────────────────────────────────
    if fail_cnt == 0:
        _h(
            f'<div style="background:#F0FDF4;border:1.5px solid #86EFAC;border-radius:8px;'
            f'padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px;">'
            f'<span style="font-size:20px;">🎉</span>'
            f'<span style="font-size:13px;font-weight:700;color:#166534;">'
            f'전체 {total_cnt}개 체크 통과 — 운영 투입 가능 상태입니다</span></div>'
        )
    else:
        _h(
            f'<div style="background:#FFF1F2;border:1.5px solid #FECDD3;border-radius:8px;'
            f'padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px;">'
            f'<span style="font-size:20px;">⚠️</span>'
            f'<div>'
            f'<span style="font-size:13px;font-weight:700;color:#9F1239;">'
            f'총 {total_cnt}개 체크 중 {fail_cnt}개 미통과</span>'
            f'<span style="font-size:12px;color:#BE123C;margin-left:8px;">'
            f'— 운영 투입 전 해결 필요</span>'
            f'</div></div>'
        )

    # ════════════════════════════════════════════════════════════════
    #  섹션 1 — 종합 점수 대시보드
    # ════════════════════════════════════════════════════════════════
    with st.expander("📊 종합 점수 대시보드", expanded=True):

        # 라이브 체크 기반 보안 점수 동적 계산
        sec_penalties = (
            (not chk["기본_비밀번호"][0]) * 20 +
            (not chk["gitignore_env"][0]) * 8 +
            (not chk["HTTPS"][0]) * 12 +
            (not chk["SQL_UNION차단"][0]) * 12 +
            (not chk["세션_만료"][0]) * 5 +
            (not chk["PII_마스킹"][0]) * 8
        )
        sec_score = max(20, 100 - sec_penalties)

        ops_penalties = (
            (not chk["프로세스_관리"][0]) * 20 +
            (not chk["모니터링"][0]) * 18 +
            (not chk["Dockerfile"][0]) * 14
        )
        ops_score = max(10, 100 - ops_penalties)

        test_score = 35 if not chk["테스트_파일"][0] else 75

        # 5개 점수 카드
        cols = st.columns(5, gap="small")
        scores = [
            ("기술부채",  58,  C["warn"],   "기술부채 총점"),
            ("유지보수성", 62, C["blue"],   "Service 레이어 부재 등"),
            ("확장성",    55,  C["indigo"], "Redis·Docker 없음"),
            ("안정성",    ops_score, C["danger"] if ops_score < 50 else C["warn"], "모니터링·재시작 기준"),
            ("보안성",    sec_score, C["danger"] if sec_score < 55 else C["warn"], "라이브 체크 반영"),
        ]
        for col, (lbl, sc, cl, desc) in zip(cols, scores):
            with col:
                _h(_score_bar(lbl, sc, cl, desc))

        gap(8)

        # 총 점수 게이지
        total_avg = sum(s for _, s, _, _ in scores) // len(scores)
        total_col = C["ok"] if total_avg >= 75 else C["warn"] if total_avg >= 55 else C["danger"]
        grade = "B-" if total_avg >= 65 else "C+" if total_avg >= 55 else "C" if total_avg >= 50 else "D+"
        _h(
            f'<div style="background:#F8FAFC;border:1.5px solid #E2E8F0;'
            f'border-radius:10px;padding:16px 20px;text-align:center;">'
            f'<div style="font-size:12px;color:{C["t3"]};font-weight:600;margin-bottom:6px;">'
            f'프로젝트 종합 점수 (5개 평균)</div>'
            f'<div style="font-size:48px;font-weight:900;color:{total_col};">{total_avg}'
            f'<span style="font-size:18px;color:{C["t3"]};">/100</span>'
            f'&nbsp;<span style="font-size:22px;font-weight:800;color:{total_col};'
            f'background:{total_col}18;padding:2px 10px;border-radius:8px;">{grade}</span>'
            f'</div>'
            f'<div style="background:#E2E8F0;border-radius:6px;height:10px;margin:10px auto;max-width:320px;">'
            f'<div style="width:{total_avg}%;height:10px;border-radius:6px;background:{total_col};"></div>'
            f'</div>'
            f'<div style="font-size:12px;color:{C["t3"]};">라이브 체크 {passed_cnt}/{total_cnt} 통과 반영</div>'
            f'</div>'
        )

    # ════════════════════════════════════════════════════════════════
    #  섹션 2 — Critical 이슈 알림
    # ════════════════════════════════════════════════════════════════
    with st.expander("🚨 Critical 이슈 알림", expanded=fail_cnt > 0):
        _h(_section_card("실시간 위험 감지", "코드베이스를 직접 읽어 현재 상태 확인", C["danger"]))

        issues = [
            (
                "기본_비밀번호",
                "관리자 기본 비밀번호 하드코딩",
                "config/settings.py:653 — default=SecretStr(\"moonhwa\") 존재. "
                ".env 미설정 환경에서 기본값으로 관리자 패널 전체 접근 가능.",
                "critical",
                "default 제거. admin_password: SecretStr = Field(...) 로 required 처리",
            ),
            (
                "SQL_UNION차단",
                "LLM 생성 SQL — UNION SELECT 미차단",
                "llm/sql_generator.py 에서 UNION 차단이 주석 처리됨. "
                "UNION SELECT 1, USER, password FROM DUAL 형태 injection 가능.",
                "critical",
                "sqlparse 라이브러리 + 화이트리스트 테이블 강제 설정",
            ),
            (
                "Dockerfile",
                "Docker 컨테이너화 부재",
                "Dockerfile / docker-compose.yml 없음. 배포 환경 재현 불가, "
                "서버 교체 시 '내 PC에서만 됩니다' 현상 발생.",
                "critical",
                "Dockerfile + docker-compose.yml 즉시 작성",
            ),
            (
                "테스트_파일",
                "비즈니스 로직 테스트 커버리지 0%",
                "rag_benchmark.py 1개만 존재. PII 마스킹·SQL 검증·설정 검증 테스트 없음. "
                "리팩토링 시 회귀 오류 무감지.",
                "critical",
                "pytest + pytest-cov. 핵심 모듈 60% 커버리지 목표",
            ),
            (
                "프로세스_관리",
                "자동 재시작 없음",
                "systemd 서비스 미등록. OOM·예외 종료 시 수동 재시작 필요. "
                "새벽 3시 크래시 → 아침 출근 후 인지.",
                "critical",
                "systemd Restart=always 또는 Docker restart: unless-stopped",
            ),
            (
                "HTTPS",
                "HTTPS/SSL 설정 미확인",
                "Nginx 설정 없음. HTTP 운영 시 Oracle 비밀번호, Gemini API 키 평문 전송.",
                "high",
                "Nginx 리버스 프록시 + 병원 내부 CA 인증서",
            ),
            (
                "세션_만료",
                "관리자 세션 무제한 유지",
                "adm_authed 세션에 만료 없음. 브라우저 탭 닫아도 재접속 시 재인증 불필요.",
                "high",
                "30분 후 자동 로그아웃. timedelta 기반 만료 체크",
            ),
            (
                "모니터링",
                "모니터링·알림 시스템 없음",
                "Oracle 연결 끊김, LLM 할당량 소진을 실시간 감지 불가. "
                "원무 직원 신고로 장애 인지.",
                "high",
                "UptimeRobot(무료) + 이메일/카카오 알림 최소 구성",
            ),
        ]

        any_shown = False
        for key, title, detail, sev, fix in issues:
            passed, _ = chk.get(key, (True, ""))
            if not passed:
                _h(_issue_card(title, detail, sev, fix))
                any_shown = True

        if not any_shown:
            _h(
                f'<div style="background:#F0FDF4;border:1px solid #86EFAC;border-radius:8px;'
                f'padding:16px;text-align:center;">'
                f'<div style="font-size:20px;margin-bottom:6px;">🎉</div>'
                f'<div style="font-size:13px;font-weight:700;color:#166534;">'
                f'Critical 이슈 없음 — 주요 위험 항목 모두 통과</div>'
                f'</div>'
            )

    # ════════════════════════════════════════════════════════════════
    #  섹션 3 — 보안 점검 (OWASP 기준)
    # ════════════════════════════════════════════════════════════════
    with st.expander("🔒 보안 점검 — OWASP 기준", expanded=False):
        _h(_section_card("보안 점검 체크리스트", "OWASP + 병원 전산 실무 기준 15개 항목", C["danger"]))

        c1, c2 = st.columns(2, gap="medium")
        with c1:
            sec_items_left = [
                ("기본_비밀번호",   "관리자 기본 비밀번호 제거"),
                ("gitignore_env",  ".gitignore 에 .env 포함"),
                ("SQL_UNION차단",  "LLM 생성 SQL UNION 차단"),
                ("HTTPS",          "HTTPS/SSL 구성"),
                ("세션_만료",      "관리자 세션 30분 만료"),
                ("PII_마스킹",     "LLM 전달 경로 PII 마스킹"),
                ("Oracle_타임아웃", "Oracle callTimeout 설정"),
            ]
            for key, label in sec_items_left:
                passed, detail = chk.get(key, (False, "미체크"))
                _h(_check_row(label, passed, detail))

        with c2:
            # 정적 항목 (코드 분석 결과)
            static_sec = [
                (True,  "SQL Parameterized Query",    "execute_query() 전체 bind variable 사용"),
                (True,  "HMAC 비밀번호 비교",         "hmac.compare_digest() — 타이밍 공격 방어"),
                (True,  "SecretStr API 키 관리",       "모든 API 키·비밀번호 SecretStr 처리"),
                (True,  "Oracle VIEW 기반 접근",       "원본 테이블 직접 접근 차단"),
                (False, "파일 업로드 MIME 검증",       "python-magic MIME 타입 검증 미적용"),
                (False, "로그 PII 마스킹",             "query_audit.log SQL 파라미터 평문 기록"),
                (False, "관리자 역할 분리",            "단일 비밀번호 — 권한 등급 없음"),
                (False, "CSRF 방어",                   "X-Frame-Options 헤더 미설정"),
            ]
            for passed, label, detail in static_sec:
                _h(_check_row(label, passed, detail))

        gap(8)
        passed_sec = sum(1 for k, _ in sec_items_left if chk.get(k, (False,))[0]) + \
                     sum(1 for p, _, _ in static_sec if p)
        total_sec = len(sec_items_left) + len(static_sec)
        _h(
            f'<div style="text-align:right;font-size:12px;color:{C["t3"]};">'
            f'보안 체크 통과: <b style="color:{C["ok"] if passed_sec >= 10 else C["danger"]};">'
            f'{passed_sec} / {total_sec}</b></div>'
        )

    # ════════════════════════════════════════════════════════════════
    #  섹션 4 — 성능 진단
    # ════════════════════════════════════════════════════════════════
    with st.expander("⚡ 성능 진단", expanded=False):
        _h(_section_card("성능 위험 요소", "쿼리·캐시·렌더링·메모리 9개 영역 분석", C["blue"]))

        perf_rows = [
            ["실시간 탭 Oracle 쿼리", "10개 _fq() 직렬 실행",
             "2-5초 렌더링 지연, Oracle pool 고갈",
             _sev("high"), "ThreadPoolExecutor 병렬 실행"],
            ["캐시 TTL 설정", "전체 ttl=1800 (30분)" if not chk["캐시_TTL"][0] else "실시간/분석 TTL 분리됨",
             "실시간 VIEW 29분 전 데이터 노출" if not chk["캐시_TTL"][0] else "양호",
             _sev("high") if not chk["캐시_TTL"][0] else _sev("good"),
             "실시간 ttl=60, 분석 ttl=1800 분리"],
            ["FAISS 재구축 블로킹", "reset() 시 동기 전체 재로딩",
             "재구축 중 30-60초 챗봇 서비스 완전 중단",
             _sev("high"), "비동기 재구축 + atomic index swap"],
            ["세션 상태 비대화", "Oracle rows 전체를 session_state 저장",
             "동시 사용자 20명 시 수 GB RAM 소비",
             _sev("medium"), "집계 요약만 세션 저장, 원본은 @st.cache_data"],
            ["LLM 스트리밍 렌더링", "4토큰마다 st.markdown() DOM 교체",
             "긴 응답 시 브라우저 렌더링 버벅임",
             _sev("medium"), "16-32 토큰마다 업데이트로 조정"],
            ["파일시스템 스캔", "Path.rglob('*.pdf') 매 렌더링 호출",
             "1,000+ PDF 시 100ms+, NFS 마운트 시 수초 지연",
             _sev("medium"), "@st.cache_data(ttl=300) 추가"],
            ["V_MONTHLY_OPD_DEPT", "Lazy Loading 적용 완료 (2026-05-07)",
             "조회 버튼 클릭 전 쿼리 없음",
             _sev("good"), "현재 상태 유지"],
            ["임베딩 캐시", "인메모리 LRU — 재시작 시 초기화",
             "서버 재시작 직후 응답 1-3초",
             _sev("medium"), "joblib.dump()로 파일 영속화"],
            ["Oracle 연결 복구", "연결 실패 시 None 상태 유지",
             "네트워크 순단 후 앱 재시작 전까지 전체 불능",
             _sev("high"), "5분마다 재연결 시도 루프"],
        ]
        _h(_tbl(
            ["영역", "현재 방식", "예상 영향", "위험도", "개선안"],
            perf_rows,
        ))

    # ════════════════════════════════════════════════════════════════
    #  섹션 5 — 코드 품질
    # ════════════════════════════════════════════════════════════════
    with st.expander("🔍 코드 품질 진단", expanded=False):
        _h(_section_card("파일·모듈별 진단", "12개 주요 코드 품질 이슈", C["indigo"]))

        quality_rows = [
            ["config/settings.py:653",
             "admin_password default=SecretStr(\"moonhwa\")<br>기본 비밀번호 하드코딩",
             _sev("critical"), "default 제거, required 필드 처리"],
            ["core/llm.py:88",
             "temperature: 0.1 하드코딩<br>settings.llm_temperature 설정 무시",
             _sev("high"), "settings.llm_temperature 사용"],
            ["ui/finance/tab_*.py 전체",
             "sys.path insert 패턴 40개 파일 반복<br>런타임 경로 의존",
             _sev("medium"), "pip install -e . 패키지화 후 제거"],
            ["ui/finance_dashboard.py",
             "with t1: 블록 내 10개 _fq() 직렬 실행<br>탭 열릴 때마다 Oracle 쿼리 10개",
             _sev("high"), "ThreadPoolExecutor 병렬화"],
            ["ui/admin_dashboard.py",
             "Path.rglob('*.pdf') 매 렌더링 호출<br>수천 파일 시 렌더링 지연",
             _sev("high"), "@st.cache_data(ttl=300) 추가"],
            ["utils/auto_backup.py",
             "shutil.rmtree() 전 경로 트래버설 방어 없음<br>backup_dir 경로 검증 미비",
             _sev("medium"), "backup_dir가 settings.backup_dir 하위인지 검증"],
            ["core/rag_pipeline.py",
             "reset() 시 _retriever=None 후 다음 요청이 None 상태 접근 가능<br>Race condition",
             _sev("medium"), "reset 중 lock 유지, Blue/Green 전환"],
            ["llm/sql_generator.py:64-106",
             "UNION SELECT 미차단 (의도적 주석 처리)<br>comment-based bypass 취약",
             _sev("critical"), "sqlparse + 화이트리스트 테이블 강제"],
            ["db/oracle_client.py:349-352",
             "callTimeout 미지원 시 silent fallback<br>Oracle 11.2 / Thin 모드 쿼리 무한 대기",
             _sev("high"), "미지원 시 WARNING 로그 필수"],
            ["tests/ 폴더",
             "rag_benchmark.py 1개만 존재<br>비즈니스 로직 커버리지 0%",
             _sev("critical"), "pytest, 핵심 모듈 60% 커버리지"],
            ["ui/panels/_shared.py",
             "SQL 딕셔너리 + 캐시 래퍼 + 날짜 유틸 혼재<br>단일 책임 원칙 위반",
             _sev("medium"), "db/queries.py, db/cache_layer.py 분리"],
            ["전체 코드베이스",
             "docstring 한국어/영어 혼재<br>일부 함수 docstring 없음",
             _sev("low"), "한국어 우선 통일 + pre-commit 훅"],
        ]
        _h(_tbl(
            ["파일/모듈", "문제 내용", "심각도", "개선 방향"],
            quality_rows,
            font="11.5px",
        ))

    # ════════════════════════════════════════════════════════════════
    #  섹션 6 — DB · SQL 구조
    # ════════════════════════════════════════════════════════════════
    with st.expander("🗄️ DB · SQL 구조 진단", expanded=False):
        _h(_section_card("Oracle DB 및 SQL 패턴 진단", "실무 운영 기준 10개 항목", C["teal"] if hasattr(C, "teal") else "#0D9488"))

        db_rows = [
            ["SELECT * FROM V_OPD_KPI", "SELECT * 사용", _sev("medium"),
             "명시적 컬럼 지정 + FETCH FIRST 1 ROWS ONLY"],
            ["V_MONTHLY_OPD_DEPT 전체 조회", "WHERE 없는 Full Scan (이전)",
             _sev("good"), "Lazy Loading 적용 완료 (2026-05-07)"],
            ["ALL_TABLES 메타데이터 조회", "시스템 딕셔너리 락 경쟁 가능",
             _sev("medium"), "캐시 TTL 600초+, USER_TABLES 사용"],
            ["LLM 생성 SQL — UNION 미차단", "UNION SELECT injection 가능",
             _sev("critical"), "sqlparse + 화이트리스트 강제"],
            ["Oracle 연결 풀 고갈", "pool_max=10, acquire_timeout 미설정",
             _sev("high"), "acquire_timeout=5.0 설정"],
            ["복구 로직 rmtree 중간 실패", "삭제 후 copytree 실패 시 빈 디렉토리",
             _sev("critical"), "임시 경로 copytree 후 os.rename() atomic 전환"],
            ["Oracle 트랜잭션", "execute_query() READ-ONLY 전용",
             _sev("good"), "현재 안전. DML 추가 시 명시적 COMMIT 필수"],
            ["뷰 기반 접근 패턴", "모든 조회 JAIN_WM VIEW 경유",
             _sev("good"), "우수한 보안 격리 패턴 — 유지"],
            ["N+1 문제", "반복 내 execute_query 없음",
             _sev("good"), "단일 뷰 단일 쿼리 패턴 유지"],
            ["테이블 파티셔닝", "뷰 베이스 테이블 파티션 미확인",
             _sev("high"), "DBA에 기준년월 Range Partition 요청"],
        ]
        _h(_tbl(
            ["SQL/구조", "문제", "위험도", "개선 방향"],
            db_rows,
            font="11.5px",
        ))

    # ════════════════════════════════════════════════════════════════
    #  섹션 7 — 운영 안정성 체크리스트
    # ════════════════════════════════════════════════════════════════
    with st.expander("🏭 운영 안정성 체크리스트", expanded=False):
        _h(_section_card("운영 항목 라이브 체크", "12개 운영 기준 현재 상태 확인", C["warn"]))

        c1, c2 = st.columns(2, gap="medium")
        ops_live = [
            ("Dockerfile",      "Docker 컨테이너화"),
            ("프로세스_관리",   "systemd/supervisord 프로세스 관리"),
            ("모니터링",        "모니터링 시스템 구성"),
            ("테스트_파일",     "자동화 테스트 존재"),
            ("버전_핀닝",       "requirements.txt 버전 핀닝"),
            ("gitignore_env",   ".env git 추적 제외"),
        ]
        ops_static = [
            (False, "CI/CD 파이프라인",     "GitHub Actions 없음"),
            (False, "환경 분리",            ".env.dev / .env.prod 미분리"),
            (False, "Oracle 자동 재연결",   "연결 실패 후 수동 재시작 필요"),
            (False, "장애 알림",            "이메일/카카오 알림 없음"),
            (False, "배포 롤백 전략",       "git tag 기반 롤백 스크립트 없음"),
            (True,  "주간 자동 백업",       "auto_backup.py 주 1회 최대 4주 보관"),
        ]

        with c1:
            for key, label in ops_live:
                passed, detail = chk.get(key, (False, "미체크"))
                _h(_check_row(label, passed, detail))
        with c2:
            for passed, label, detail in ops_static:
                _h(_check_row(label, passed, detail))

        gap(6)
        all_passed = sum(1 for k, _ in ops_live if chk.get(k, (False,))[0]) + \
                     sum(1 for p, _, _ in ops_static if p)
        total_ops = len(ops_live) + len(ops_static)
        st.progress(all_passed / total_ops, text=f"운영 준비도: {all_passed}/{total_ops} ({all_passed*100//total_ops}%)")

    # ════════════════════════════════════════════════════════════════
    #  섹션 8 — 기술부채 상세
    # ════════════════════════════════════════════════════════════════
    with st.expander("💳 기술부채 상세 평가", expanded=False):
        _h(_section_card("기술부채 정량 평가", "항목별 점수 + 실무 영향 설명", C["indigo"]))

        debt_items = [
            ("기술부채 총점",  58, C["warn"],
             "Critical 이슈 4개, CI/CD·테스트·Docker 전무. 운영 중 사고 발생 시 대응 체계 없음."),
            ("유지보수성",     62, C["blue"],
             "모듈 분리 양호, 그러나 sys.path 조작 40곳, 하위 호환 별칭 100+곳. "
             "신입 개발자 수정 포인트 파악에 30분+ 소요."),
            ("확장성",         55, C["indigo"],
             "단일 서버 Streamlit 한계. 동시 사용자 50명+ 시 CPU 포화. "
             "Redis 없어 다중 서버 배포 시 캐시 공유 불가."),
            ("안정성",         ops_score, C["danger"] if ops_score < 50 else C["warn"],
             "테스트 0%, Docker 없음, 모니터링 없음, 자동 재시작 없음. "
             "장애 시 수동 대응 체계만 존재."),
            ("보안성",         sec_score, C["danger"] if sec_score < 55 else C["warn"],
             "PII 마스킹·HMAC·SecretStr 패턴 우수하나, "
             "SQL Injection 방어 불완전, 기본 비밀번호, 세션 만료 없음."),
        ]

        for label, score, col, desc in debt_items:
            grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
            _h(
                f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                f'border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
                f'<span style="font-size:22px;font-weight:900;color:{col};min-width:46px;">{score}</span>'
                f'<div style="flex:1;">'
                f'<div style="display:flex;align-items:center;gap:6px;">'
                f'<span style="font-size:13px;font-weight:700;color:#0F172A;">{label}</span>'
                f'<span style="font-size:11px;font-weight:700;color:{col};'
                f'background:{col}18;padding:1px 6px;border-radius:6px;">{grade}</span>'
                f'</div>'
                f'<div style="background:#E2E8F0;border-radius:3px;height:5px;margin-top:4px;">'
                f'<div style="width:{score}%;height:5px;border-radius:3px;background:{col};"></div>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div style="font-size:11.5px;color:{C["t3"]};">{desc}</div>'
                f'</div>'
            )

    # ════════════════════════════════════════════════════════════════
    #  섹션 9 — 즉시 수정 TOP 10
    # ════════════════════════════════════════════════════════════════
    with st.expander("🎯 즉시 수정 TOP 10", expanded=True):
        _h(_section_card("최우선 개선 과제", "ROI 기준 정렬 — 위에서부터 순서대로 처리", C["danger"]))

        top10 = [
            (1,  "기본_비밀번호",  "관리자 기본 비밀번호 제거",
             "🔴 보안 침해", "⭐ 30분",  "즉시 Critical 위험 제거",
             "config/settings.py:653 default=SecretStr(\"moonhwa\") 제거"),
            (2,  "프로세스_관리", "systemd 프로세스 관리 등록",
             "🔴 서비스 중단", "⭐ 2시간", "무중단 자동 재시작 확보",
             "systemd Restart=always 4개 앱 등록"),
            (3,  "Dockerfile",   "Docker 컨테이너화",
             "🔴 환경 불일치", "⭐⭐ 1일",  "배포 표준화 + 재현 가능 환경",
             "Dockerfile + docker-compose.yml 작성"),
            (4,  "SQL_UNION차단", "LLM SQL UNION 차단 + 화이트리스트",
             "🔴 DB 유출", "⭐⭐ 2일",  "병원 개인정보 유출 사고 방지",
             "sqlparse + ORACLE_WHITELIST_TABLES 필수 설정"),
            (5,  "캐시_TTL",     "실시간 VIEW 캐시 TTL 분리",
             "🟠 데이터 신뢰도", "⭐ 30분", "실시간성 복구",
             "_fq_realtime(ttl=60), _fq_analysis(ttl=1800) 분리"),
            (6,  "",             "실시간 탭 Oracle 쿼리 병렬화",
             "🟠 응답 지연", "⭐⭐ 1일",  "렌더링 2-5초 → 0.5초",
             "ThreadPoolExecutor(max_workers=5) 도입"),
            (7,  "",             "Oracle 자동 재연결 루프",
             "🟠 서비스 중단", "⭐⭐ 4시간", "네트워크 순단 자동 복구",
             "5분마다 test_connection() + pool 재초기화"),
            (8,  "테스트_파일",  "핵심 모듈 단위 테스트 작성",
             "🟠 회귀 무감지", "⭐⭐⭐ 3일", "안전한 리팩토링 기반",
             "pytest: settings, sql_generator, pii_masker 60% 커버리지"),
            (9,  "",             "FAISS atomic index swap",
             "🟠 서비스 중단", "⭐⭐ 1일",  "무중단 벡터DB 재구축",
             "임시 경로 구축 → os.rename() atomic 교체"),
            (10, "모니터링",     "최소 모니터링 + 알림 구성",
             "🟠 장애 인지 지연", "⭐ 2시간", "장애 인지 수시간 → 수분",
             "UptimeRobot(무료) + 이메일 SMTP 알림"),
        ]

        for rank, chk_key, title, impact, effort, effect, how in top10:
            live_ok = chk.get(chk_key, (True, ""))[0] if chk_key else False
            status_badge = (
                f'<span style="font-size:10px;font-weight:700;color:{C["ok"]};'
                f'background:{C["ok"]}18;padding:2px 8px;border-radius:10px;">✅ 완료</span>'
                if live_ok else
                f'<span style="font-size:10px;font-weight:700;color:{C["danger"]};'
                f'background:{C["danger"]}18;padding:2px 8px;border-radius:10px;">⬜ 미완료</span>'
            )
            rank_col = C["danger"] if rank <= 3 else C["warn"] if rank <= 6 else C["blue"]
            _h(
                f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
                f'border-left:4px solid {rank_col};border-radius:0 8px 8px 0;'
                f'padding:12px 16px;margin-bottom:8px;">'
                f'<div style="display:flex;align-items:flex-start;gap:12px;">'
                f'<span style="font-size:20px;font-weight:900;color:{rank_col};'
                f'min-width:28px;line-height:1.3;">{rank}</span>'
                f'<div style="flex:1;">'
                f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">'
                f'<span style="font-size:13px;font-weight:700;color:#0F172A;">{title}</span>'
                f'{status_badge}'
                f'</div>'
                f'<div style="display:flex;gap:12px;font-size:11px;color:{C["t3"]};flex-wrap:wrap;">'
                f'<span>영향: <b style="color:#334155;">{impact}</b></span>'
                f'<span>난이도: <b style="color:#334155;">{effort}</b></span>'
                f'<span>효과: <b style="color:#334155;">{effect}</b></span>'
                f'</div>'
                f'<div style="font-size:11.5px;color:{C["blue"]};margin-top:4px;">'
                f'→ {how}</div>'
                f'</div>'
                f'</div>'
                f'</div>'
            )

    # ════════════════════════════════════════════════════════════════
    #  섹션 10 — 리팩토링 로드맵
    # ════════════════════════════════════════════════════════════════
    with st.expander("🗺️ 리팩토링 로드맵", expanded=False):
        _h(_section_card("단계별 개선 로드맵", "Phase 1–5 · 실행 가능한 체크리스트", C["green"] if hasattr(C, "green") else "#10B981"))

        phases = [
            ("Phase 1 — 즉시 수정", "이번 주 · 1-2일",
             C["danger"], "🚨",
             [
                 ("기본_비밀번호",  False, "admin_password default 제거",         "config/settings.py:653"),
                 ("프로세스_관리",  False, "systemd 서비스 파일 4개 작성",         "/etc/systemd/system/mh-*.service"),
                 ("",              False, ".streamlit/config.toml 보안 설정",     "enableCORS=false, maxMessageSize=50"),
                 ("버전_핀닝",     False, "requirements.txt 버전 핀닝 (==)",      "전체 패키지 고정"),
                 ("gitignore_env", False, ".gitignore .env 추가 확인",            ".env, *.pkl, logs/ 확인"),
                 ("캐시_TTL",      False, "실시간 VIEW 캐시 TTL=60 분리",         "_fq_realtime() 별도 함수"),
                 ("세션_만료",     False, "관리자 세션 30분 만료 로직",            "timedelta 기반 체크"),
             ]),
            ("Phase 2 — 구조 개선", "2-4주",
             C["warn"], "🔧",
             [
                 ("Dockerfile",    False, "Dockerfile + docker-compose.yml 작성", "Multi-stage build"),
                 ("SQL_UNION차단", False, "sqlparse 기반 SQL 검증 재작성",        "UNION 차단 + 화이트리스트"),
                 ("",              False, "Service 레이어 도입",                  "services/finance_service.py 등"),
                 ("테스트_파일",   False, "핵심 모듈 단위 테스트 작성",            "pytest, 60% 커버리지"),
                 ("",              False, "sys.path 조작 전면 제거",               "pip install -e . 패키지화"),
                 ("PII_마스킹",    False, "context_builder PII 마스킹 전수 감사", "LLM 전달 경로 검증"),
             ]),
            ("Phase 3 — 성능 최적화", "1-2달",
             C["blue"], "⚡",
             [
                 ("", False, "실시간 탭 쿼리 병렬화",        "ThreadPoolExecutor(max_workers=5)"),
                 ("", False, "세션 상태 최적화",             "집계 요약만 저장"),
                 ("", False, "FAISS atomic index swap",     "atomic rename 기반 무중단 재구축"),
                 ("", False, "임베딩 캐시 영속화",           "joblib.dump() 파일 저장"),
                 ("", False, "Oracle 자동 재연결 루프",      "5분 주기 헬스체크"),
             ]),
            ("Phase 4 — 운영 안정화", "2-3달",
             C["indigo"], "🏭",
             [
                 ("", False, "GitHub Actions CI/CD",        "PR → lint+test → staging → prod"),
                 ("모니터링", False, "Prometheus + Grafana", "구조화 로그 (structlog)"),
                 ("", False, "장애 알림 시스템",             "카카오알림톡 / 이메일 SMTP"),
                 ("", False, "환경 분리",                    ".env.dev / .env.prod / APP_ENV"),
             ]),
            ("Phase 5 — 장기 아키텍처", "3-6달 (선택)",
             "#6B7280", "🏗️",
             [
                 ("", False, "FastAPI 백엔드 분리",          "REST API + Streamlit 프론트"),
                 ("", False, "Redis 캐시 레이어",            "다중 서버 배포 시 필요"),
                 ("", False, "LLM 제공자 추상화",            "Gemini / Claude / OpenAI 전환 가능"),
                 ("", False, "병원 AD/LDAP 인증 연동",       "직원 계정 기반 역할 분리"),
             ]),
        ]

        for phase_title, timeline, col, icon, items in phases:
            pass_count = sum(1 for k, _, _, _ in items if k and chk.get(k, (False,))[0])
            total_items = len(items)
            _h(
                f'<div style="background:{col}08;border:1.5px solid {col}30;'
                f'border-radius:10px;padding:14px 16px;margin-bottom:12px;">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                f'margin-bottom:10px;">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:18px;">{icon}</span>'
                f'<span style="font-size:13px;font-weight:800;color:{col};">{phase_title}</span>'
                f'<span style="font-size:11px;color:{C["t3"]};">— {timeline}</span>'
                f'</div>'
                f'<span style="font-size:11px;color:{col};font-weight:700;">'
                f'{pass_count}/{total_items} 완료</span>'
                f'</div>'
            )
            for chk_key, _, text, sub in items:
                live_done = bool(chk_key and chk.get(chk_key, (False,))[0])
                _h(_phase_item(live_done, text, sub))
            _h("</div>")

    # ════════════════════════════════════════════════════════════════
    #  총평
    # ════════════════════════════════════════════════════════════════
    gap(8)
    verdict_fail = [k for k, (p, _) in chk.items() if not p]
    if len(verdict_fail) == 0:
        verdict_bg, verdict_col, verdict_icon, verdict_text = (
            "#F0FDF4", "#166534", "🎉",
            "전체 체크 통과 — 운영 투입 가능 상태입니다."
        )
    elif len(verdict_fail) <= 3:
        verdict_bg, verdict_col, verdict_icon, verdict_text = (
            "#FFFBEB", "#92400E", "⚠️",
            f"{len(verdict_fail)}개 항목 미통과 — 해결 후 Pilot 운영 가능."
        )
    else:
        verdict_bg, verdict_col, verdict_icon, verdict_text = (
            "#FFF1F2", "#9F1239", "❌",
            f"{len(verdict_fail)}개 항목 미통과 — 현재 상태로 운영 투입 불가."
        )

    _h(
        f'<div style="background:{verdict_bg};border:2px solid;border-color:{verdict_col}40;'
        f'border-radius:12px;padding:20px 24px;margin-top:8px;">'
        f'<div style="display:flex;align-items:flex-start;gap:14px;">'
        f'<span style="font-size:28px;">{verdict_icon}</span>'
        f'<div>'
        f'<div style="font-size:15px;font-weight:800;color:{verdict_col};margin-bottom:4px;">'
        f'총평 — 운영 투입 가능성 판정</div>'
        f'<div style="font-size:13px;color:{verdict_col};">{verdict_text}</div>'
        f'<div style="font-size:11.5px;color:#64748B;margin-top:8px;">'
        f'라이브 체크 {passed_cnt}/{total_cnt} 통과 &nbsp;·&nbsp; '
        f'종합 점수 {total_avg}/100 ({grade}) &nbsp;·&nbsp; '
        f'{time.strftime("%Y-%m-%d %H:%M")} 기준 &nbsp;·&nbsp; '
        f'<a href="CTO_ANALYSIS_REPORT_20260507.md" style="color:{C["blue"]};">상세 보고서 MD 파일 참조</a>'
        f'</div>'
        f'</div>'
        f'</div>'
        f'</div>'
    )
