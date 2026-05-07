"""
ui/finance/tab_chat.py — 원무 대시보드 탭별 AI 분석 채팅 컴포넌트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[2026-05-07] 신규 작성

[역할]
  각 탭 하단에 표시되는 AI 분석 채팅 위젯.
  탭별 집계 데이터를 JSON 컨텍스트로 LLM 에 전달해
  원무관리자가 추세·이슈를 자연어로 분석할 수 있게 한다.

[구성]
  render_tab_chat()     — 공통 채팅 UI (재사용)
  build_ctx_realtime()  — 실시간 현황 컨텍스트
  build_ctx_weekly()    — 주간추이 컨텍스트 (session_state)
  build_ctx_monthly()   — 월간추이 컨텍스트 (session_state)
  build_ctx_dept()      — 진료과 분석 컨텍스트 (session_state)
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

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

try:
    from ui.design import C
except Exception:
    C = {
        "blue": "#3B82F6", "indigo": "#6366F1", "green": "#10B981",
        "t1": "#0F172A", "t2": "#334155", "t3": "#64748B", "t4": "#94A3B8",
    }

# ── 공통 시스템 프롬프트 ─────────────────────────────────────────────
_SYS_BASE = (
    "당신은 병원 원무팀 업무 지원 AI입니다.\n"
    "반드시 아래 [현재 대시보드 데이터]만 근거로 답변하세요. 데이터에 없는 내용은 추측하지 마세요.\n"
    "핵심 수치는 **굵게**, 위험/주의는 🔴, 정상은 🟢, 권장 조치는 ✅ 로 표시하세요.\n"
    "개인 환자 정보(환자명, 주민번호, 카드번호 등)는 절대 언급하지 마세요.\n"
    "답변은 간결하게 핵심 위주로 작성하세요.\n\n"
)

_NO_DATA_PROMPT = (
    "당신은 병원 원무팀 업무 지원 AI입니다.\n"
    "현재 대시보드 데이터가 아직 조회되지 않았습니다. "
    "'조회' 버튼을 눌러 데이터를 불러온 후 질문하면 데이터 기반으로 분석해 드립니다.\n"
    "일반적인 원무 관리 질문에는 답변할 수 있습니다."
)


# ══════════════════════════════════════════════════════════════════════
#  컨텍스트 빌더 — 탭 데이터 → LLM 프롬프트용 요약 dict
# ══════════════════════════════════════════════════════════════════════

def build_ctx_realtime(
    opd_kpi:         Dict,
    dept_status:     List[Dict],
    bed_detail:      List[Dict],
    discharge_pipe:  List[Dict],
    daily_dept_stat: List[Dict] = None,
) -> Dict:
    """실시간 현황 탭 — KPI·외래·병동·퇴원 파이프라인 요약."""
    dept_status     = dept_status     or []
    bed_detail      = bed_detail      or []
    discharge_pipe  = discharge_pipe  or []
    daily_dept_stat = daily_dept_stat or []

    _stay = sum(int(r.get("재원수",   0) or 0) for r in bed_detail)
    _adm  = sum(int(r.get("금일입원", 0) or 0) for r in bed_detail)
    _disc = sum(int(r.get("금일퇴원", 0) or 0) for r in bed_detail)
    _tot  = sum(int(r.get("총병상",   0) or 0) for r in bed_detail)
    _wait = sum(int(r.get("대기",     0) or 0) for r in dept_status)
    _proc = sum(int(r.get("진료중",   0) or 0) for r in dept_status)
    _done = sum(int(r.get("완료",     0) or 0) for r in dept_status)

    _pipe: Dict = {}
    for r in discharge_pipe:
        s = r.get("단계", ""); n = int(r.get("환자수", 0) or 0)
        if s: _pipe[s] = _pipe.get(s, 0) + n

    return {
        "기준시각": time.strftime("%Y-%m-%d %H:%M"),
        "외래KPI": opd_kpi,
        "외래_현황": {
            "대기": _wait, "진료중": _proc, "완료": _done,
            "진료과별_대기순": [
                {
                    "진료과": r.get("진료과명"), "대기": r.get("대기"),
                    "진료중": r.get("진료중"), "완료": r.get("완료"),
                }
                for r in sorted(dept_status, key=lambda x: -int(x.get("대기", 0) or 0))[:12]
            ],
        },
        "병동_현황": {
            "금일입원": _adm, "금일퇴원": _disc, "재원수": _stay,
            "총병상": _tot, "가동률": f"{round(_stay / max(_tot, 1) * 100, 1)}%",
            "병동별": [
                {"병동": r.get("병동명"), "재원": r.get("재원수"), "가동률": r.get("가동률")}
                for r in bed_detail[:10]
            ],
        },
        "퇴원_파이프라인": _pipe,
    }


def build_ctx_weekly() -> Dict:
    """주간추이분석 탭 — session_state['fin_weekly_data'] 에서 요약."""
    from collections import defaultdict as _dd
    _wd = st.session_state.get("fin_weekly_data", {})
    if not _wd:
        return {}

    _daily = _wd.get("daily_dept_stat", []) or []
    _opd   = _wd.get("opd_dept_trend",  []) or []
    _ipd   = _wd.get("ipd_dept_trend",  []) or []
    _los   = _wd.get("los_dist_dept",   []) or []

    # 7일간 일별 카테고리 합계
    _day_sum: dict = _dd(lambda: _dd(int))
    for r in _daily:
        d = str(r.get("기준일", ""))[:10]
        cat = r.get("구분", "")
        if cat in ("외래", "입원", "퇴원", "재원"):
            _day_sum[d][cat] += int(r.get("건수", 0) or 0)

    # 진료과별 합계
    _opd_d: dict = _dd(int)
    for r in _opd:
        _opd_d[r.get("진료과명", "")] += int(r.get("외래환자수", 0) or 0)

    _ipd_d: dict = _dd(int)
    for r in _ipd:
        _ipd_d[r.get("진료과명", "")] += int(r.get("입원환자수", 0) or 0)

    _los_d: dict = _dd(int)
    for r in _los:
        _los_d[r.get("재원일수구간", "")] += int(r.get("환자수", 0) or 0)

    return {
        "7일간_일별추이": {d: dict(v) for d, v in sorted(_day_sum.items())[-7:]},
        "외래_진료과별_합계_상위10": dict(
            sorted(_opd_d.items(), key=lambda x: -x[1])[:10]
        ),
        "입원_진료과별_합계_상위10": dict(
            sorted(_ipd_d.items(), key=lambda x: -x[1])[:10]
        ),
        "재원일수_구간별_환자수": dict(_los_d),
    }


def build_ctx_monthly() -> Dict:
    """월간추이분석 탭 — session_state['mon_opd_data'] 에서 요약."""
    _data = st.session_state.get("mon_opd_data", []) or []
    _m1   = st.session_state.get("mon_sel_m1")
    _m2   = st.session_state.get("mon_sel_m2")
    if not _data:
        return {}

    def _summarize(rows: list) -> dict:
        return {
            r.get("진료과명", ""): {
                "방문자수": int(r.get("방문자수", 0) or 0),
                "신환자수": int(r.get("신환자수", 0) or 0),
                "구환자수": int(r.get("구환자수", 0) or 0),
            }
            for r in rows if r.get("진료과명")
        }

    _m1_rows = [r for r in _data if str(r.get("기준년월", "")) == str(_m1)]
    _m2_rows = [r for r in _data if str(r.get("기준년월", "")) == str(_m2)]

    return {
        "기준월": str(_m1) if _m1 else "미선택",
        "비교월": str(_m2) if _m2 else "미선택",
        "기준월_진료과별": _summarize(_m1_rows),
        "비교월_진료과별": _summarize(_m2_rows),
    }


def build_ctx_dept() -> Dict:
    """진료과 분석 탭 — session_state['fin_dept_data'] 에서 요약."""
    from collections import defaultdict as _dd
    _data = st.session_state.get("fin_dept_data", []) or []
    if not _data:
        return {}

    _months = sorted(
        {str(r.get("기준년월", "")) for r in _data if r.get("기준년월")},
        reverse=True,
    )[:6]

    _dm: dict = _dd(dict)
    for r in _data:
        ym   = str(r.get("기준년월", ""))
        dept = r.get("진료과명", "")
        if ym in _months and dept:
            _dm[dept][ym] = {
                "방문자수": int(r.get("방문자수", 0) or 0),
                "신환자수": int(r.get("신환자수", 0) or 0),
            }

    _top = sorted(
        _dm.items(),
        key=lambda x: -sum(v.get("방문자수", 0) for v in x[1].values()),
    )[:15]

    return {
        "분석기간": _months,
        "진료과별_월별_방문자_상위15": dict(_top),
    }


# ══════════════════════════════════════════════════════════════════════
#  채팅 UI 컴포넌트
# ══════════════════════════════════════════════════════════════════════

def render_tab_chat(
    ctx_data: Dict,
    tab_key:  str,
    tab_label: str,
    quick_questions: Optional[List[Tuple[str, str]]] = None,
) -> None:
    """탭 하단 AI 분석 채팅 위젯.

    Args:
        ctx_data:        LLM 컨텍스트 요약 dict (비어있으면 "데이터 없음" 프롬프트 사용).
        tab_key:         탭 식별자 — session_state 키 접미어 (예: 'realtime', 'weekly').
        tab_label:       탭 한글명 (헤더·입력 플레이스홀더에 표시).
        quick_questions: [(버튼 레이블, 질문 텍스트), ...] 최대 4개.
    """
    _hkey = f"fn_chat_{tab_key}_hist"
    _pfkey = f"fn_chat_{tab_key}_pf"
    _ikey  = f"fn_chat_{tab_key}_inp"

    if _hkey not in st.session_state:
        st.session_state[_hkey] = []
    _history = st.session_state[_hkey]

    # ── 시스템 프롬프트 구성
    if ctx_data:
        _ctx_json = json.dumps(ctx_data, ensure_ascii=False, indent=2)
        _sys = (
            _SYS_BASE
            + f"## [{tab_label}] 현재 데이터 — {time.strftime('%Y-%m-%d %H:%M')} 기준\n"
            + f"```json\n{_ctx_json[:5500]}\n```"
        )
        _has_data = True
    else:
        _sys = _NO_DATA_PROMPT
        _has_data = False

    # ── 채팅 패널 ─────────────────────────────────────────────────────
    st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:#F8FAFC;border:1.5px solid #E2E8F0;'
        f'border-radius:12px;padding:16px 18px;margin-top:4px;">',
        unsafe_allow_html=True,
    )

    # 헤더
    _badge_col  = C["blue"]  if _has_data else C["t4"]
    _badge_txt  = "데이터 기반 분석 가능" if _has_data else "조회 후 분석 가능"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">'
        f'<span style="font-size:20px;">🤖</span>'
        f'<div>'
        f'<span style="font-size:14px;font-weight:700;color:{C["t1"]};">AI 원무 분석</span>'
        f'<span style="font-size:12px;color:{C["t3"]};">&nbsp;— {tab_label}</span>'
        f'<span style="font-size:10px;font-weight:600;color:{_badge_col};margin-left:8px;'
        f'background:{_badge_col}1A;padding:2px 8px;border-radius:10px;">'
        f'{_badge_txt}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── 빠른 질문 버튼
    _qs = (quick_questions or [])[:4]
    if _qs:
        _qcols = st.columns(len(_qs), gap="small")
        for _qi, (_ql, _qv) in enumerate(_qs):
            with _qcols[_qi]:
                if st.button(
                    _ql, key=f"fn_qs_{tab_key}_{_qi}",
                    use_container_width=True, type="secondary",
                ):
                    st.session_state[_pfkey] = _qv
                    st.rerun()

    # ── 히스토리 렌더링
    for _msg in _history:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])

    # ── 입력창 (탭별 고유 key)
    _prefill = st.session_state.pop(_pfkey, None)
    _user_in = (
        st.chat_input(f"{tab_label} 데이터에 대해 질문하세요", key=_ikey)
        or _prefill
    )

    if _user_in:
        with st.chat_message("user"):
            st.markdown(_user_in)
        _history.append({"role": "user", "content": _user_in})

        with st.chat_message("assistant"):
            _ph = st.empty()
            _toks: list = []
            _full = ""
            try:
                from core.llm import get_llm_client
                _llm  = get_llm_client()
                _safe = (
                    _sys[:6000] + "\n...(데이터 생략)"
                    if len(_sys) > 6000 else _sys
                )
                for _tok in _llm.generate_stream(
                    _user_in, _safe, request_id=uuid.uuid4().hex[:8]
                ):
                    _toks.append(_tok)
                    if len(_toks) % 4 == 0:
                        _ph.markdown("".join(_toks) + "▌")
                _full = "".join(_toks)
            except Exception as _e:
                _full = f"**LLM 연결 오류**\n\n`{_e}`"
                logger.error(f"[TabChat:{tab_key}] LLM 오류: {_e}", exc_info=True)
            _ph.markdown(_full)

        _history.append({"role": "assistant", "content": _full})
        st.session_state[_hkey] = _history
        st.rerun()

    # ── 대화 초기화 (히스토리가 있을 때만 표시)
    if _history:
        if st.button(
            "🗑 대화 초기화", key=f"fn_chat_{tab_key}_clr", type="secondary"
        ):
            st.session_state[_hkey] = []
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
