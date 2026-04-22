"""
admin_app.py  ─  좋은문화병원 관리자 대시보드 v3.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[핵심 규칙]
  · font-family 는 절대 HTML style="" 속성 안에 쓰지 않는다.
    → 이중따옴표 충돌로 invalid HTML 발생, 텍스트 그대로 출력됨.
  · font-family 는 CSS <style> 블록 안에서만 선언한다.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)

# ── 페이지 설정 ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="관리자 대시보드 | 좋은문화병원",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 CSS 주입
# 주의: <style> 블록 안에서는 CSS font-family 값에 따옴표 사용 가능
#       HTML style="" 속성 안에서는 절대 font-family 선언 금지
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

/* 전역 폰트 — Pretendard (design.py와 동일) */
html, body,
[data-testid], [class*="st-"],
p, div, span, a, li, ul, ol,
button, input, label, select, textarea {
  font-family: "Pretendard", -apple-system, BlinkMacSystemFont,
               "Apple SD Gothic Neo", sans-serif !important;
  -webkit-font-smoothing: antialiased;
}

/* Streamlit 기본 헤더 제거 */
header[data-testid="stHeader"] { display: none !important; }
.main .block-container { padding: 0 !important; max-width: 100% !important; }

/* ── 사이드바 배경 ──────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: rgba(15,23,42,0.97) !important;
  backdrop-filter: saturate(180%) blur(20px) !important;
  -webkit-backdrop-filter: saturate(180%) blur(20px) !important;
  border-right: 1px solid rgba(255,255,255,0.07) !important;
}
[data-testid="stSidebar"] > div,
[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: transparent !important;
}

/* 사이드바 일반 텍스트
   — .sb-link 내부 span 은 제외(아래에서 별도 제어) */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label {
  color: rgba(255,255,255,0.86) !important;
  font-size: 13px !important;
}
[data-testid="stSidebar"] span:not(.sb-link-name):not(.sb-link-port):not(.sb-link-sub) {
  color: rgba(255,255,255,0.86) !important;
  font-size: 13px !important;
}
[data-testid="stSidebar"] hr {
  border-top: 1px solid rgba(255,255,255,0.09) !important;
  margin: 12px 0 !important;
}

/* ── 사이드바 버튼 ──────────────────────────────────────────── */
[data-testid="stSidebar"] .stButton > button {
  background: rgba(255,255,255,0.08) !important;
  border: 1px solid rgba(255,255,255,0.15) !important;
  color: #fff !important;
  border-radius: 8px !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  letter-spacing: -0.1px !important;
  padding: 8px 14px !important;
  transition: background 150ms ease !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(255,255,255,0.15) !important;
}
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span {
  color: #fff !important;
  font-size: 13px !important;
  background: transparent !important;
}

/* ── 사이드바 입력 ──────────────────────────────────────────── */
[data-testid="stSidebar"] input {
  background: rgba(255,255,255,0.08) !important;
  border: 1px solid rgba(255,255,255,0.15) !important;
  color: #fff !important;
  font-size: 13px !important;
  border-radius: 8px !important;
}
[data-testid="stSidebar"] input::placeholder {
  color: rgba(255,255,255,0.30) !important;
}

/* ── 사이드바 앱 링크 카드 ──────────────────────────────────── */
.sb-link {
  display: block;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.12);
  border-left: 3px solid rgba(99,179,237,0.55);  /* 기본 액센트(스카이블루) */
  border-radius: 9px;
  padding: 10px 14px;
  text-decoration: none !important;
  margin-bottom: 7px;
  transition: background 150ms ease, border-color 150ms ease;
}
.sb-link:hover {
  background: rgba(255,255,255,0.12) !important;
  border-left-color: rgba(99,179,237,0.85) !important;
}
/* sb-link 내 Streamlit wrapping p 태그 마진 제거 */
.sb-link p { margin: 0 !important; padding: 0 !important; }

.sb-link-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}
/* 개별 색상 — 인라인 border-left-color 로 덮어씀 */
.sb-link-name {
  font-size: 12.5px !important;
  font-weight: 600 !important;
  color: rgba(255,255,255,0.90) !important;
  letter-spacing: -0.1px !important;
}
.sb-link-port {
  font-size: 10.5px !important;
  color: rgba(255,255,255,0.32) !important;
  font-weight: 400 !important;
}
.sb-link-sub {
  font-size: 11px !important;
  color: rgba(255,255,255,0.40) !important;
  font-weight: 400 !important;
}

/* ── 탭 ────────────────────────────────────────────────────── */
[data-testid="stTabs"] > div:first-child {
  background: #ffffff !important;
  border-bottom: 1px solid rgba(15,23,42,0.10) !important;
  padding: 0 48px !important;
  position: sticky !important;
  top: 0 !important;
  z-index: 100 !important;
}
[data-testid="stTabs"] [data-testid="stTab"] p,
[data-testid="stTabs"] [data-testid="stTab"] {
  font-size: 14px !important;
  font-weight: 500 !important;
  color: rgba(15,23,42,0.50) !important;
  padding: 14px 0 !important;
  margin-right: 28px !important;
  border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] p,
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
  font-weight: 700 !important;
  color: #0f172a !important;
  border-bottom-color: #2563eb !important;
}

/* ── metric ────────────────────────────────────────────────── */
[data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] label {
  font-size: 11px !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  font-weight: 700 !important;
  color: #94a3b8 !important;
}
[data-testid="stMetricValue"] div {
  font-size: 1.7rem !important;
  font-weight: 700 !important;
  color: #0f172a !important;
  letter-spacing: -0.4px !important;
}

/* ── 스크롤바 ───────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(15,23,42,0.18); border-radius: 9999px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
#  헬스체크
# ══════════════════════════════════════════════════════════════════════
if st.query_params.get("health", "") == "1":
    _h: dict = {"status": "ok", "app": "admin_dashboard", "ts": time.time()}
    try:
        from db.oracle_client import test_connection
        _ok, _ = test_connection()
        _h["oracle"] = _ok
    except Exception:
        _h["oracle"] = False
    try:
        import psutil
        _h["memory_rss_mb"] = round(psutil.Process().memory_info().rss / 1024 ** 2, 1)
    except ImportError:
        pass
    st.json(_h)
    st.stop()


# ══════════════════════════════════════════════════════════════════════
#  사이드바 — font-family 인라인 style 속성 완전 배제
# ══════════════════════════════════════════════════════════════════════

def _sidebar() -> bool:
    with st.sidebar:

        # ── 로고 ────────────────────────────────────────────────
        # font-family 없이 순수 레이아웃/색상/크기 스타일만 사용
        st.markdown(
            '<div style="padding:16px 0 18px;'
            'border-bottom:1px solid rgba(255,255,255,0.09);'
            'margin-bottom:16px;">'
            '<div style="font-size:22px;margin-bottom:6px;">⚙️</div>'
            '<div style="font-size:15px;font-weight:700;'
            'color:#fff;letter-spacing:-0.3px;line-height:1.2;">좋은문화병원</div>'
            '<div style="font-size:11px;font-weight:500;'
            'color:rgba(255,255,255,0.38);letter-spacing:0.05em;'
            'text-transform:uppercase;margin-top:3px;">Admin Dashboard</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        authed = st.session_state.get("adm_authed", False)

        # ── 인증 영역 ────────────────────────────────────────────
        if authed:
            login_t = st.session_state.get("adm_login_time", "")
            st.markdown(
                '<div style="background:rgba(16,185,129,0.12);'
                'border:1px solid rgba(16,185,129,0.28);'
                'border-radius:8px;padding:10px 14px;margin-bottom:14px;">'
                '<div style="font-size:12px;font-weight:700;color:#10b981;">✓ 관리자 인증 완료</div>'
                f'<div style="font-size:11px;color:rgba(255,255,255,0.38);margin-top:2px;">{login_t}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("로그아웃", key="adm_logout", use_container_width=True):
                st.session_state["adm_authed"] = False
                st.session_state.pop("adm_login_time", None)
                logger.info("관리자 로그아웃")
                st.rerun()
        else:
            st.markdown(
                '<div style="font-size:11px;font-weight:600;'
                'color:rgba(255,255,255,0.40);letter-spacing:0.06em;'
                'text-transform:uppercase;margin-bottom:8px;">관리자 로그인</div>',
                unsafe_allow_html=True,
            )
            pw = st.text_input(
                "패스워드",
                type="password",
                placeholder="관리자 패스워드 입력",
                key="adm_pw",
                label_visibility="collapsed",
            )
            if st.button("로그인", key="adm_login", use_container_width=True):
                if pw:
                    try:
                        if settings.check_admin(pw):
                            st.session_state["adm_authed"] = True
                            st.session_state["adm_login_time"] = (
                                "인증: " + datetime.now().strftime("%H:%M:%S")
                            )
                            logger.info("관리자 대시보드 인증 성공")
                            st.rerun()
                        else:
                            st.markdown(
                                '<div style="font-size:12px;color:#ef4444;'
                                'font-weight:600;margin-top:6px;">'
                                '패스워드가 올바르지 않습니다</div>',
                                unsafe_allow_html=True,
                            )
                            logger.warning("관리자 대시보드 인증 실패")
                    except Exception as e:
                        st.error(f"인증 오류: {e}")

        st.divider()

        # ── 다른 앱 링크 ─────────────────────────────────────────
        # CSS 클래스(sb-link, sb-link-name 등)로 스타일 제어
        # HTML 속성에는 font-family 미사용
        st.markdown(
            '<div style="font-size:11px;font-weight:600;'
            'color:rgba(255,255,255,0.35);letter-spacing:0.07em;'
            'text-transform:uppercase;margin-bottom:8px;">다른 앱</div>',
            unsafe_allow_html=True,
        )
        _ip = "192.1.1.231"
        # 포트별 액센트 색상 (border-left)
        _LINK_APPS = [
            ("8501", "병동 대시보드", "입퇴원 현황",   "#3B82F6"),   # 파랑
            ("8502", "AI 챗봇",       "규정·지침 검색", "#8B5CF6"),  # 보라
            ("8503", "원무 대시보드", "수납·미수금",   "#14B8A6"),   # 청록
        ]
        for port, name, sub, accent in _LINK_APPS:
            st.markdown(
                f'<a href="http://{_ip}:{port}/" target="_blank" class="sb-link"'
                f' style="border-left-color:{accent};">'
                '<div class="sb-link-row">'
                f'<span class="sb-link-name">{name}</span>'
                f'<span class="sb-link-port">:{port} ↗</span>'
                '</div>'
                f'<div class="sb-link-sub">{sub}</div>'
                '</a>',
                unsafe_allow_html=True,
            )

        st.divider()

        # ── 시스템 리소스 요약 ───────────────────────────────────
        try:
            import psutil
            proc_mb = round(psutil.Process().memory_info().rss / 1024 ** 2, 0)
            cpu     = psutil.cpu_percent(interval=None)
            vm      = psutil.virtual_memory()
            mem_col = (
                "#ef4444" if vm.percent > 85
                else "#f59e0b" if vm.percent > 70
                else "rgba(255,255,255,0.35)"
            )
            st.markdown(
                f'<div style="font-size:11px;color:rgba(255,255,255,0.35);line-height:1.9;">'
                f'CPU&nbsp;&nbsp;{cpu:.0f}%&nbsp;&nbsp;&nbsp;'
                f'<span style="color:{mem_col};">RAM&nbsp;&nbsp;{vm.percent:.0f}%</span>&nbsp;&nbsp;&nbsp;'
                f'앱&nbsp;&nbsp;{proc_mb:.0f}&nbsp;MB'
                '</div>',
                unsafe_allow_html=True,
            )
        except ImportError:
            pass

        # ── 버전 ─────────────────────────────────────────────────
        st.markdown(
            '<div style="font-size:10px;color:rgba(255,255,255,0.18);'
            'text-align:center;padding-top:20px;">'
            'Admin Dashboard v3.0 · 좋은문화병원'
            '</div>',
            unsafe_allow_html=True,
        )

    return st.session_state.get("adm_authed", False)


# ══════════════════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════════════════

def _login_center() -> None:
    """
    미인증 상태 — 메인 영역 중앙에 로그인 카드 표시 (2026-04-22 개선).
    사이드바가 닫혀 있어도 패스워드를 입력할 수 있도록
    사이드바 의존 없이 메인 컨텐츠 안에 폼을 배치한다.
    """
    st.markdown(
        """
<style>
html, body { background:#0f172a !important; }
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
    background: #0f172a !important;
}
/* Streamlit 기본 입력 필드 — 어두운 배경에 맞춰 재정의 */
.adm-login-wrap .stTextInput input {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    color: #fff !important;
    border-radius: 10px !important;
    font-size: 15px !important;
    padding: 10px 14px !important;
}
.adm-login-wrap .stTextInput label {
    color: rgba(255,255,255,0.55) !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}
.adm-login-wrap .stButton > button {
    width: 100%;
    background: #2563eb !important;
    border: none !important;
    color: #fff !important;
    font-size: 15px !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    padding: 11px 0 !important;
    margin-top: 4px !important;
    letter-spacing: -0.1px !important;
    transition: background 150ms ease !important;
}
.adm-login-wrap .stButton > button:hover {
    background: #1d4ed8 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # ── 중앙 정렬: 빈 컬럼으로 좌우 패딩 ──────────────────────────────
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown('<div class="adm-login-wrap">', unsafe_allow_html=True)

        # 로고 / 타이틀
        st.markdown(
            '<div style="text-align:center;padding:60px 0 32px;">'
            '<div style="font-size:40px;margin-bottom:10px;">⚙️</div>'
            '<div style="font-size:26px;font-weight:700;color:#fff;'
            'letter-spacing:-0.5px;margin-bottom:6px;">관리자 대시보드</div>'
            '<div style="font-size:13px;color:rgba(255,255,255,0.38);'
            'letter-spacing:0.04em;">좋은문화병원 · Admin Only</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # 로그인 카드
        st.markdown(
            '<div style="background:rgba(255,255,255,0.04);'
            'border:1px solid rgba(255,255,255,0.09);'
            'border-radius:16px;padding:32px 28px 28px;">'
            '<div style="font-size:14px;font-weight:600;color:rgba(255,255,255,0.55);'
            'letter-spacing:0.05em;text-transform:uppercase;margin-bottom:16px;">'
            '관리자 패스워드</div>',
            unsafe_allow_html=True,
        )

        pw = st.text_input(
            "패스워드",
            type="password",
            placeholder="패스워드를 입력하세요",
            key="adm_pw_main",
            label_visibility="collapsed",
        )
        login_clicked = st.button("로그인", key="adm_login_main")

        st.markdown("</div>", unsafe_allow_html=True)  # 카드 닫기

        # 로그인 처리
        if login_clicked:
            if pw:
                try:
                    if settings.check_admin(pw):
                        st.session_state["adm_authed"] = True
                        st.session_state["adm_login_time"] = (
                            "인증: " + datetime.now().strftime("%H:%M:%S")
                        )
                        logger.info("관리자 대시보드 인증 성공 (메인폼)")
                        st.rerun()
                    else:
                        st.markdown(
                            '<div style="margin-top:12px;padding:10px 14px;'
                            'background:rgba(239,68,68,0.12);'
                            'border:1px solid rgba(239,68,68,0.30);'
                            'border-radius:8px;font-size:13px;font-weight:600;'
                            'color:#ef4444;text-align:center;">'
                            '❌ 패스워드가 올바르지 않습니다</div>',
                            unsafe_allow_html=True,
                        )
                        logger.warning("관리자 대시보드 인증 실패 (메인폼)")
                except Exception as e:
                    st.error(f"인증 오류: {e}")
            else:
                st.warning("패스워드를 입력해 주세요.")

        st.markdown("</div>", unsafe_allow_html=True)  # adm-login-wrap 닫기


def main() -> None:
    logger.info("admin_app v3.0 시작 (포트 8504)")
    authed = _sidebar()

    # ── 미인증: 사이드바 의존 없이 메인 영역에 로그인 폼 표시 (2026-04-22) ──
    if not authed:
        _login_center()
        return

    try:
        from ui.admin_dashboard import render_admin_dashboard
        render_admin_dashboard()
    except Exception as e:
        st.error(f"관리자 대시보드 오류: {e}")
        logger.error(f"admin_app render 오류: {e}", exc_info=True)


if __name__ == "__main__":
    main()
