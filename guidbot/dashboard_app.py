"""
dashboard_app.py  ─  좋은문화병원 병동 현황 대시보드 v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[v2.0 운영 개선]
  · 포트 정정: 대시보드 8501 / 챗봇 8502
  · 헬스체크 엔드포인트 추가 (?health=1)
  · Windows 프로세스 우선순위 ABOVE_NORMAL 설정
  · 사이드바 시스템 모니터링 (RAM/CPU, psutil 설치 시)
  · psutil 미설치 환경 graceful degradation

[분리 구성]
    ┌─────────────────────────────────────────────────────┐
    │  dashboard_app.py (포트 8501)  main.py (포트 8502)  │
    │  ───────────────────────────  ─────────────────     │
    │  · 병동 입퇴원 현황             · RAG 규정 검색     │
    │  · 진료과별 재원 파이           · AI 질의응답       │
    │  · 주간 추이 차트               · SQL 데이터 분석   │
    │  → 사용자: 통계과/수간호사      → 사용자: 전 직원   │
    └─────────────────────────────────────────────────────┘

[실행 방법]
    # 병동 대시보드 (포트 8502)
    streamlit run dashboard_app.py --server.port 8501

    # RAG 챗봇 (포트 8501)
    streamlit run main.py --server.port 8502

[헬스체크]
    http://서버IP:8501/?health=1
    → JSON 응답: {"status":"ok","oracle":true,"memory_rss_mb":420}

[의존 모듈]
    ui/hospital_dashboard.py  ← 실제 화면 렌더링
    db/oracle_client.py       ← Oracle 연결
    config/settings.py        ← 환경 변수 설정
    ui/theme.py               ← CSS 테마
"""

from __future__ import annotations

# ── 표준 라이브러리 ────────────────────────────────────────────────────
import sys
import time
import json
from pathlib import Path

# ── 서드파티 ──────────────────────────────────────────────────────────
import streamlit as st

# ── 내부 모듈 ─────────────────────────────────────────────────────────
from config.settings import settings
from ui.theme import UITheme as T
from ui.hospital_dashboard import render_hospital_dashboard
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)


# ══════════════════════════════════════════════════════════════════════
# [운영 v2.0] Windows 프로세스 우선순위 설정
# 대시보드는 주 사용 앱이므로 ABOVE_NORMAL 우선순위 부여
# → Oracle I/O + Plotly 렌더링 응답성 향상
# main.py(챗봇)는 CPU 집약적이므로 기본 우선순위 유지
# ══════════════════════════════════════════════════════════════════════
if sys.platform == "win32":
    try:
        import ctypes
        # ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        # HIGH(0x80)는 시스템 불안정 유발 위험 → ABOVE_NORMAL만 사용
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(),
            0x00008000,
        )
        logger.info("Windows 프로세스 우선순위: ABOVE_NORMAL 설정 완료")
    except Exception as _e:
        logger.debug(f"우선순위 설정 실패 (무시): {_e}")


# ══════════════════════════════════════════════════════════════════════
# Streamlit 페이지 설정
# st.set_page_config()는 반드시 모든 st 호출 전 최상단에 위치해야 함
# ══════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="병동 현황 대시보드 | 좋은문화병원",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 공통 CSS 테마 적용 ─────────────────────────────────────────────────
st.markdown(T.get_global_css(), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# [운영 v2.0] 헬스체크 엔드포인트
# URL: http://서버IP:8501/?health=1
#
# 모니터링 도구(Zabbix, 브라우저 북마크 등)에서 주기적으로 호출하여
# 앱 생존 여부 + Oracle 연결 상태를 확인합니다.
#
# 응답 예시:
#   {"status": "ok", "oracle": true, "memory_rss_mb": 420.5,
#    "system_memory_pct": 38.2, "ts": 1711507200.0}
# ══════════════════════════════════════════════════════════════════════
_health_param = st.query_params.get("health", "")
if _health_param == "1":
    _health: dict = {"status": "ok", "ts": time.time(), "oracle": False}

    # Oracle 연결 상태 확인
    try:
        from db.oracle_client import test_connection
        _ok, _msg = test_connection()
        _health["oracle"] = _ok
        _health["oracle_msg"] = _msg
    except Exception as _e:
        _health["oracle_msg"] = str(_e)

    # 메모리 상태 (psutil 설치 시)
    try:
        import psutil
        _proc = psutil.Process()
        _mem  = _proc.memory_info()
        _health["memory_rss_mb"]      = round(_mem.rss / 1024 / 1024, 1)
        _sys_mem = psutil.virtual_memory()
        _health["system_memory_pct"]  = _sys_mem.percent
        _health["system_memory_avail_gb"] = round(_sys_mem.available / 1024**3, 1)
    except ImportError:
        _health["psutil"] = "not installed"

    st.json(_health)
    st.stop()  # 헬스체크 후 나머지 렌더링 중단


# ══════════════════════════════════════════════════════════════════════
# 미니 사이드바
# ══════════════════════════════════════════════════════════════════════
def _render_mini_sidebar() -> None:
    """
    대시보드 전용 미니 사이드바.
    - Oracle 상태 표시
    - AI 챗봇(8501) 이동 링크
    - 시스템 모니터링 (psutil 설치 시)
    """
    with st.sidebar:
        # ── 병원 로고 ────────────────────────────────────────────────
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;'
            "padding:12px 0 16px;border-bottom:1px solid rgba(255,255,255,0.15);"
            'margin-bottom:16px;">'
            '<span style="font-size:22px;">🏥</span>'
            "<div>"
            '<div style="font-size:14px;font-weight:700;color:#FFFFFF;">좋은문화병원</div>'
            '<div style="font-size:10px;color:rgba(255,255,255,0.5);">병동 현황 대시보드</div>'
            "</div></div>",
            unsafe_allow_html=True,
        )

        # ── Oracle 연결 상태 (세션당 1회만 ping) ─────────────────────
        if "dash_oracle_ok" not in st.session_state:
            _ok = False
            try:
                from db.oracle_client import test_connection
                _ok, _ = test_connection()
            except Exception:
                pass
            st.session_state["dash_oracle_ok"] = _ok

        _oracle_ok = st.session_state.get("dash_oracle_ok", False)

        if _oracle_ok:
            st.markdown(
                '<div style="display:flex;align-items:center;gap:6px;'
                "background:rgba(22,163,74,0.15);border:1px solid rgba(22,163,74,0.3);"
                'border-radius:6px;padding:6px 10px;margin-bottom:10px;">'
                '<span style="width:8px;height:8px;border-radius:50%;'
                'background:#16A34A;display:inline-block;flex-shrink:0;"></span>'
                '<span style="font-size:12px;font-weight:600;color:#16A34A;">Oracle 연결 정상</span>'
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="display:flex;align-items:center;gap:6px;'
                "background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.3);"
                'border-radius:6px;padding:6px 10px;margin-bottom:10px;">'
                '<span style="width:8px;height:8px;border-radius:50%;'
                'background:#F59E0B;display:inline-block;flex-shrink:0;"></span>'
                '<span style="font-size:12px;font-weight:600;color:#F59E0B;">Oracle 미연결</span>'
                "</div>",
                unsafe_allow_html=True,
            )

        # ── 마지막 갱신 시각 ─────────────────────────────────────────
        _last_ts = st.session_state.get(
            "dash_last_ts", time.strftime("%Y-%m-%d %H:%M")
        )
        st.markdown(
            f'<div style="font-size:11px;color:rgba(255,255,255,0.45);'
            f'margin-bottom:16px;">마지막 갱신: {_last_ts}</div>',
            unsafe_allow_html=True,
        )

        # ── AI 챗봇 이동 링크 (포트 8501) ────────────────────────────
        st.markdown(
            '<div style="margin-bottom:16px;">'
            '<a href="http://192.1.1.231:8502/" target="_blank" style="'
            "display:flex;align-items:center;gap:6px;"
            "background:rgba(30,64,175,0.20);border:1px solid rgba(30,64,175,0.35);"
            'border-radius:7px;padding:8px 12px;text-decoration:none;">'
            '<span style="font-size:14px;">💬</span>'
            "<div>"
            '<div style="font-size:12px;font-weight:600;color:rgba(255,255,255,0.88);">AI 챗봇</div>'
            '<div style="font-size:10px;color:rgba(255,255,255,0.40);">규정·지침 검색 (8502)</div>'
            "</div>"
            '<span style="margin-left:auto;font-size:11px;color:rgba(255,255,255,0.35);">↗</span>'
            "</a></div>",
            unsafe_allow_html=True,
        )

        st.divider()

        # ── [운영 v2.0] 시스템 모니터링 ─────────────────────────────
        # psutil 설치 시 RAM/CPU 실시간 표시
        # 미설치 시 조용히 생략 (운영 중단 없음)
        try:
            import psutil

            _proc    = psutil.Process()
            _mem_mb  = round(_proc.memory_info().rss / 1024 / 1024, 0)
            _sys_mem = psutil.virtual_memory()
            _cpu_pct = psutil.cpu_percent(interval=None)

            # 메모리 사용률에 따른 색상
            _mem_color = (
                "#EF4444" if _sys_mem.percent > 85
                else "#F59E0B" if _sys_mem.percent > 70
                else "rgba(255,255,255,0.45)"
            )

            st.markdown(
                f'<div style="font-size:10px;color:rgba(255,255,255,0.45);">'
                f'<div style="margin-bottom:3px;">🖥️ CPU: {_cpu_pct:.0f}%</div>'
                f'<div style="margin-bottom:3px;color:{_mem_color};">'
                f'💾 RAM: {_sys_mem.percent:.0f}% '
                f'({round(_sys_mem.available/1024**3,1)}GB 여유)</div>'
                f'<div>📦 이 앱: {_mem_mb:.0f} MB</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        except ImportError:
            # psutil 미설치 — 모니터링 없이 정상 동작
            pass

        # ── 버전 정보 ────────────────────────────────────────────────
        st.markdown(
            '<div style="font-size:10px;color:rgba(255,255,255,0.25);'
            'text-align:center;padding-top:12px;">'
            "병동 대시보드 v2.0<br>"
            "좋은문화병원 통계과"
            "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════
# 메인 함수
# ══════════════════════════════════════════════════════════════════════
def main() -> None:
    """
    dashboard_app.py 진입점.

    [화면 구성]
    1. 사이드바: Oracle 상태 + 챗봇 링크 + 시스템 모니터링
    2. 메인 영역: render_hospital_dashboard(tab="ward")

    [tab 고정]
    이 앱은 병동 대시보드 전용.
    원무/외래 탭은 main.py(챗봇, 8501) 관리자 모드에서만 접근.
    """
    logger.info("dashboard_app v2.0 시작 — 병동 대시보드 (포트 8501)")

    # 사이드바 렌더
    _render_mini_sidebar()

    # 갱신 시각 초기화
    if "dash_last_ts" not in st.session_state:
        st.session_state["dash_last_ts"] = time.strftime("%Y-%m-%d %H:%M")

    # 병동 대시보드 렌더
    try:
        render_hospital_dashboard(tab="ward")
    except Exception as e:
        st.error(
            f"대시보드 로드 중 오류가 발생했습니다.\n\n"
            f"오류 내용: {e}\n\n"
            f"Oracle 연결 상태를 확인하거나 관리자에게 문의하세요."
        )
        logger.error(f"dashboard_app 렌더 오류: {e}", exc_info=True)


if __name__ == "__main__":
    main()