"""
ui/chart_selector.py  ─  병동 대시보드 차트 타입 선택기 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[설계 목표]
    병동 대시보드의 5개 시각화 섹션에서 사용자가 원하는
    차트 타입을 직접 선택할 수 있는 UI를 제공합니다.

[대상 섹션]
    1. 진료과별 재원 구성        → 도넛 / 가로막대 / 트리맵
    2. 주간 추이 7일              → 라인 / 영역 / 막대
    3. 병동별 당일 현황           → 테이블 / 가로막대 / 히트맵
    4. 최근 7일 입원 주상병 분포  → 파이 / 가로막대 / 트리맵
    5. 금일 vs 전일 주상병 분포   → 중첩막대 / 그룹막대 / 수평막대

[UI 방식]
    각 카드 헤더 우측에 작은 pill 버튼 형태로 표시됩니다.
    선택 상태는 st.session_state 에 저장되어 리프레시 후에도 유지됩니다.

[사용 예시]
    from ui.chart_selector import render_chart_selector, get_chart_type

    chart_type = render_chart_selector("dept_stay")
    # chart_type → "donut" | "bar_h" | "treemap"
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import streamlit as st

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  차트 설정 레지스트리
#  각 섹션마다 사용 가능한 차트 타입과 기본값을 정의합니다.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Dict 구조: {section_key: {"options": [(value, label), ...], "default": str}}
CHART_REGISTRY: Dict[str, Dict] = {
    # ── 섹션 1: 진료과별 재원 구성 ─────────────────────────────────
    "dept_stay": {
        "label": "진료과별 재원 구성",
        "options": [
            ("donut",   "🍩 도넛"),      # 기본값: 중앙 총계가 강조되는 도넛 차트
            ("bar_h",   "📊 막대"),      # 가로 막대: 수치 비교가 명확
            ("treemap", "🗺️ 트리맵"),   # 트리맵: 면적으로 비율 직관 파악
        ],
        "default": "donut",
    },

    # ── 섹션 2: 주간 추이 7일 ──────────────────────────────────────
    "weekly_trend": {
        "label": "주간 추이 7일",
        "options": [
            ("table", "📋 테이블"),      # 기본값: 현재 날짜·가동률·입원·퇴원 표
            ("line",  "📈 라인"),        # 라인: 추세 변화 파악에 최적
            ("area",  "🏔️ 영역"),       # 영역: 볼륨감 강조 (재원수 강조시)
            ("bar",   "📊 막대"),        # 막대: 일별 절대값 비교
        ],
        "default": "table",
    },

    # ── 섹션 3: 병동별 당일 현황 ───────────────────────────────────
    "ward_detail": {
        "label": "병동별 당일 현황",
        "options": [
            ("table",   "📋 테이블"),    # 기본값: 모든 컬럼 정확한 수치 확인
            ("bar_h",   "📊 막대"),      # 가로 막대: 병동간 가동률 한눈 비교
            ("heatmap", "🔥 히트맵"),   # 히트맵: 병동×지표 색상 매핑
        ],
        "default": "table",
    },

    # ── 섹션 4: 최근 7일 입원 주상병 분포 ──────────────────────────
    "dx_7day": {
        "label": "최근 7일 주상병 분포",
        "options": [
            ("pie",     "🍩 파이"),      # 기본값: 비율 파악
            ("bar_h",   "📊 막대"),      # 가로 막대: 상병명이 긴 경우 가독성 좋음
            ("treemap", "🗺️ 트리맵"),   # 트리맵: 빈도가 높은 상병 시각적 강조
        ],
        "default": "pie",
    },

    # ── 섹션 5: 금일 vs 전일 입원 주상병 분포 ──────────────────────
    "dx_compare": {
        "label": "금일 vs 전일 비교",
        "options": [
            ("overlay", "🔀 중첩막대"),  # 기본값: 같은 축에 투명도로 중첩
            ("grouped", "📊 그룹막대"),  # 그룹 막대: 나란히 비교
            ("bar_h",   "↔️ 수평막대"), # 수평: 상병명 공간 여유
        ],
        "default": "overlay",
    },
}

# ── session_state 키 접두사 ────────────────────────────────────────────
# 섹션별 선택값을 session_state 에 저장할 때 사용하는 키 형식
_STATE_PREFIX = "chart_type__"


def get_chart_type(section_key: str) -> str:
    """
    특정 섹션의 현재 선택된 차트 타입을 반환합니다.

    session_state 에 저장된 값이 없으면 해당 섹션의 기본값을 반환합니다.
    (처음 대시보드를 열었을 때 기본 차트로 표시되는 이유)

    Args:
        section_key: CHART_REGISTRY 에 정의된 섹션 키
                     예: "dept_stay", "weekly_trend" 등

    Returns:
        선택된 차트 타입 문자열
        예: "donut", "bar_h", "line" 등

    Example:
        chart_type = get_chart_type("dept_stay")
        # → "donut"  (기본값, 사용자가 아직 변경 안 한 경우)
    """
    config = CHART_REGISTRY.get(section_key)
    if not config:
        # 등록되지 않은 섹션 키 → 빈 문자열 반환 (렌더러에서 기본값으로 처리)
        return ""

    state_key = _STATE_PREFIX + section_key
    return st.session_state.get(state_key, config["default"])


def set_chart_type(section_key: str, chart_type: str) -> None:
    """
    특정 섹션의 차트 타입을 session_state 에 저장합니다.

    이 함수는 render_chart_selector 내부에서 자동 호출됩니다.
    외부에서 직접 호출하면 프로그래밍 방식으로 차트를 변경할 수 있습니다.

    Args:
        section_key: 섹션 키 (예: "dept_stay")
        chart_type:  저장할 차트 타입 (예: "bar_h")
    """
    state_key = _STATE_PREFIX + section_key
    st.session_state[state_key] = chart_type


def render_chart_selector(
    section_key: str,
    *,
    align_right: bool = True,
) -> str:
    """
    카드 헤더 영역에 차트 타입 선택 pill 버튼을 렌더링합니다.

    [UI 구조]
        [섹션 제목 레이블]          [🍩 도넛 | 📊 막대 | 🗺 트리맵]
        ←── 좌측 (자동) ───────────────────────────── 우측 (선택기) ──→

    [동작 방식]
        1. 현재 session_state 에서 선택값을 읽음
        2. st.radio(horizontal=True) 로 pill 버튼 렌더링
        3. 사용자가 변경하면 session_state 업데이트 → 자동 리렌더

    Args:
        section_key:  CHART_REGISTRY 에 정의된 섹션 키
        align_right:  선택기를 우측 정렬할지 여부 (기본: True)

    Returns:
        현재 선택된 차트 타입 문자열

    Example:
        chart_type = render_chart_selector("dept_stay")
        # → "donut"  (사용자가 선택한 값 또는 기본값)
    """
    config = CHART_REGISTRY.get(section_key)
    if not config:
        # 알 수 없는 섹션 → 빈 값 반환 (렌더러가 기본 동작)
        return ""

    state_key = _STATE_PREFIX + section_key
    options: List[Tuple[str, str]] = config["options"]
    current = st.session_state.get(state_key, config["default"])

    # ── pill 버튼용 CSS 주입 (최초 1회만 적용되도록 key로 구분) ────────
    # Streamlit의 radio 위젯을 pill 모양 버튼처럼 스타일링합니다.
    # 각 섹션마다 다른 st.radio 가 존재하므로 section_key 로 CSS 범위를 지정합니다.
    _inject_pill_css(section_key)

    # ── 레이아웃: [넓은 빈 공간] | [선택기] ────────────────────────────
    # 비율 [5, 3] → 제목 텍스트는 호출자가 별도 렌더링하므로 여기서는 빈칸
    col_spacer, col_selector = st.columns([5, 3] if align_right else [1, 9])

    with col_selector:
        # st.radio 로 옵션 표시
        # label_visibility="collapsed" → 라벨 숨김 (섹션 제목과 중복 방지)
        # horizontal=True → 가로 방향으로 옵션 나열
        labels = [label for _, label in options]
        values = [value for value, _ in options]

        try:
            current_idx = values.index(current)
        except ValueError:
            current_idx = 0  # 저장된 값이 옵션 목록에 없으면 첫 번째 선택

        selected_label = st.radio(
            label=f"chart_type_{section_key}",    # 내부 식별자 (화면에 안 보임)
            options=labels,
            index=current_idx,
            horizontal=True,
            label_visibility="collapsed",          # 라벨 숨김
            key=f"radio_{section_key}",            # 위젯 고유 키
        )

        # 선택된 라벨 → 값으로 역변환 후 session_state 에 저장
        selected_value = values[labels.index(selected_label)]
        if selected_value != current:
            # 이전 선택과 다르면 상태 업데이트 (st.rerun 불필요, radio가 자동 처리)
            st.session_state[state_key] = selected_value

    return st.session_state.get(state_key, config["default"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  내부 헬퍼: CSS 주입
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 이미 CSS를 주입한 섹션 키를 추적 (동일 CSS 중복 주입 방지)
_CSS_INJECTED: set = set()


def _inject_pill_css(section_key: str) -> None:
    """
    radio 위젯을 pill 버튼처럼 보이게 하는 CSS를 한 번만 주입합니다.

    [왜 CSS 주입이 필요한가?]
    Streamlit 기본 radio 위젯은 동그란 선택 점(●) 스타일입니다.
    CSS로 이를 숨기고 선택된 항목에 배경색을 주면 pill 버튼처럼 보입니다.

    [주의]
    이 CSS는 전체 앱에 적용됩니다. section_key 별로 다른 스타일을 주려면
    data-testid 등을 활용하여 범위를 좁혀야 합니다. 현재는 동일 스타일 공유.
    """
    if section_key in _CSS_INJECTED:
        return  # 이미 주입된 경우 스킵

    # pill 버튼 스타일 CSS
    # - input[type="radio"] 숨김 (원래 라디오 버튼 아이콘 제거)
    # - label 에 박스 스타일 적용 (테두리, 패딩, 배경)
    # - 선택된 항목(aria-checked 활용)에 파란 배경 적용
    css = """
    <style>
    /* ── 차트 타입 선택기 pill 스타일 ── */

    /* radio 위젯 wrapper 줄간격 축소 */
    div[data-testid="stRadio"] > div {
        gap: 4px !important;
        flex-wrap: nowrap !important;
    }

    /* 개별 라디오 레이블 — pill 모양 */
    div[data-testid="stRadio"] label {
        display: inline-flex !important;
        align-items: center !important;
        padding: 3px 10px !important;
        border-radius: 20px !important;
        border: 1px solid #CBD5E1 !important;
        background: #F8FAFC !important;
        color: #475569 !important;
        font-size: 11px !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        transition: all 0.15s ease !important;
        white-space: nowrap !important;
        line-height: 1.4 !important;
        margin: 0 !important;
    }

    /* hover 효과 */
    div[data-testid="stRadio"] label:hover {
        background: #EFF6FF !important;
        border-color: #93C5FD !important;
        color: #1D4ED8 !important;
    }

    /* 선택된 항목 — 파란 pill */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked),
    div[data-testid="stRadio"] label[aria-checked="true"] {
        background: #1E40AF !important;
        border-color: #1E40AF !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }

    /* 라디오 원형 아이콘 숨김 */
    div[data-testid="stRadio"] input[type="radio"] {
        display: none !important;
    }

    /* radio 위젯 좌측 여백 제거 */
    div[data-testid="stRadio"] {
        padding: 0 !important;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    _CSS_INJECTED.add(section_key)


def render_section_header(
    section_key: str,
    title: str,
    subtitle: str = "",
    accent_color: str = "#1E40AF",
) -> str:
    """
    섹션 헤더와 차트 선택기를 한 줄에 렌더링하는 통합 헬퍼 함수입니다.

    [렌더링 결과 예시]
        ┌──────────────────────────────────────────────────────────────┐
        │  │ 진료과별 재원 구성  · 전체        [🍩 도넛][📊 막대][🗺 트리맵] │
        └──────────────────────────────────────────────────────────────┘

    [사용법]
        chart_type = render_section_header(
            section_key="dept_stay",
            title="진료과별 재원 구성",
            subtitle="전체 병동",
        )
        # 반환값으로 chart_type 을 받아 렌더러 함수에 전달

    Args:
        section_key:   CHART_REGISTRY 섹션 키
        title:         헤더 제목 텍스트
        subtitle:      헤더 부제목 텍스트 (선택 사항, 예: "전체 병동")
        accent_color:  좌측 강조선 색상 (기본: 딥블루)

    Returns:
        현재 선택된 차트 타입 문자열
    """
    # 제목 + 부제목 영역 (HTML로 렌더링 — Streamlit 기본 텍스트보다 정밀 제어 가능)
    sub_html = (
        f'<span style="font-size:10px;color:#94A3B8;margin-left:6px;">{subtitle}</span>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;margin-bottom:2px;">
            <span style="
                display:inline-block;width:3px;height:16px;
                background:{accent_color};border-radius:2px;
                margin-right:8px;flex-shrink:0;
            "></span>
            <span style="
                font-size:13px;font-weight:700;color:#0F172A;
                letter-spacing:-0.01em;
            ">{title}</span>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 차트 선택기 pill 버튼 (우측 정렬)
    return render_chart_selector(section_key)


def reset_all_chart_types() -> None:
    """
    모든 섹션의 차트 타입을 기본값으로 초기화합니다.

    [사용 시나리오]
    관리자 패널 또는 사이드바에 "차트 초기화" 버튼을 만들 때 사용합니다.

    Example:
        if st.sidebar.button("🔄 차트 초기화"):
            reset_all_chart_types()
    """
    for section_key, config in CHART_REGISTRY.items():
        state_key = _STATE_PREFIX + section_key
        st.session_state[state_key] = config["default"]