"""
ui/design_rules.py — 좋은문화병원 대시보드 디자인 규칙 (v1.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이 파일은 실행 코드가 아닌 규칙 문서다.
UI 코드 작성 전 반드시 이 파일을 참조하라.

[목차]
  1. 디자인 원칙
  2. 색상 사용 규칙
  3. 컴포넌트 규칙
  4. 레이아웃 규칙
  5. 타이포그래피
  6. 차트 규칙
  7. 금지 사항
"""

# ════════════════════════════════════════════════════════════════════
# 1. 디자인 원칙
# ════════════════════════════════════════════════════════════════════
PRINCIPLES = """
[1] 단일 소스 원칙
    모든 색상·CSS·컴포넌트는 ui/design.py 에서만 가져온다.
    대시보드 파일 내부에 색상값을 하드코딩하지 않는다.

[2] 일관성 원칙
    KPI 카드는 항상 fn-kpi CSS 클래스를 사용한다.
    섹션 헤더는 항상 section_header() 함수를 사용한다.
    카드 컨테이너는 항상 wd-card CSS 클래스를 사용한다.

[3] 계층 원칙
    페이지 상단 → 그라데이션 바 (fn-topbar)
    섹션 컨테이너 → wd-card
    섹션 제목 → wd-sec + wd-sec-bar
    KPI 행 → fn-kpi × 4열

[4] 데이터 없음 원칙
    데이터가 없을 경우 항상 empty_state() 를 사용한다.
    빈 차트 공간을 남기지 않는다.
"""

# ════════════════════════════════════════════════════════════════════
# 2. 색상 사용 규칙
# ════════════════════════════════════════════════════════════════════
COLOR_RULES = """
[주 강조색] C["blue"] = #1E40AF
    - 주요 수치·KPI 강조, 탭 선택 색상, 기본 버튼
    - 예: 총 환자수, 매출 합계

[보조 강조색] C["indigo"] = #4F46E5
    - 2차 데이터 계열, 이전 기간 비교
    - 예: 전월 데이터, 비교 시리즈

[성공/정상] C["green"] = #059669
    - 목표 달성, 정상 상태, 양호 지표
    - 배경: C["green_l"], 테두리: C["ok_bd"]

[경고] C["yellow"] = #D97706
    - 주의 필요, 목표 70~99%
    - 배경: C["yellow_l"]

[위험/오류] C["red"] = #DC2626
    - 이상 감지, 목표 미달, 오류
    - 배경: C["red_l"]

[데이터 계열 추천 순서]
    1위: C["blue"]   2위: C["teal"]   3위: C["indigo"]
    4위: C["green"]  5위: C["violet"] 6위: C["orange"]

[텍스트 계층]
    제목·강조  → C["t1"] = #0F172A
    본문       → C["t2"] = #334155
    보조 설명  → C["t3"] = #64748B
    힌트·메타  → C["t4"] = #94A3B8
    비활성     → C["t5"] = #CBD5E1

[금지]
    ❌ 8자리 hex 색상 (#RRGGBBAA) — Plotly 미지원
       대신: rgba(r,g,b,a) 또는 _c(hex, alpha) 헬퍼 사용
    ❌ 파일 내부에 컬러 토큰 중복 정의
    ❌ C_WARD, C_FINANCE 직접 참조 (design.py의 C 사용)
"""

# ════════════════════════════════════════════════════════════════════
# 3. 컴포넌트 규칙
# ════════════════════════════════════════════════════════════════════
COMPONENT_RULES = """
[KPI 카드] kpi_card(col, icon, label, val, unit, sub, color)
    - 항상 4컬럼 행에 배치: col1, col2, col3, col4 = st.columns(4)
    - icon: 단일 이모지 (예: "👥", "📍", "💰")
    - label: 대문자, 10자 이내
    - val: 포맷된 숫자 문자열 (예: "1,234")
    - unit: 단위 문자열 (예: "명", "원", "%")
    - sub: 부연 설명 (예: "지역미상 제외")
    - color: C["blue"] 등 C 딕셔너리 값
    - goal_pct: 목표 달성률 (0~100, None 이면 바 미표시)

[섹션 헤더] section_header(title, sub, color)
    - wd-card 시작 직후 첫 번째 요소로 사용
    - sub: 데이터 출처·기준 설명 (예: "최근 7일 기준")
    - color: 섹션 강조색 (C["blue"], C["teal"] 등)

[카드 컨테이너] HTML 패턴
    st.markdown('<div class="wd-card" style="border-top:3px solid {color};">',
                unsafe_allow_html=True)
    # ... 내용 ...
    st.markdown('</div>', unsafe_allow_html=True)

[배지] badge_html(text, kind) → str
    - HTML 문자열 반환, f-string 내부에 삽입
    - kind: blue / green / yellow / red / gray / ok / warn / err

[여백] gap(px=8)
    - 섹션 사이: gap(12)
    - KPI와 차트 사이: gap(8) (기본값)
    - 미세 조정: gap(4)
"""

# ════════════════════════════════════════════════════════════════════
# 4. 레이아웃 규칙
# ════════════════════════════════════════════════════════════════════
LAYOUT_RULES = """
[페이지 구조]
    1. CSS 주입: st.markdown(APP_CSS, unsafe_allow_html=True)
    2. 상단 바:  topbar()
    3. 탑바 행:  st.columns([3, 4, 5]) — 제목 / 버튼들 / 상태/날짜
    4. 탭:       tab1, tab2, ... = st.tabs([...])
    5. 각 탭:    with tab1: _tab_xxx(...)

[컬럼 비율 가이드]
    KPI 4개:     st.columns(4, gap="small")
    2분할:       st.columns([6, 4], gap="small")  또는 [5, 5]
    3분할:       st.columns([4, 4, 4], gap="small") 또는 [3, 5, 4]
    차트+표:     st.columns([7, 5], gap="small")
    컨트롤 행:   st.columns([2, 2, 2, 1, 1, ...], gap="small")

[카드 내부 구조]
    wd-card 열기
    └─ section_header()
    └─ gap(4)
    └─ 내용 (KPI/차트/표)
    wd-card 닫기

[온디맨드 로딩 패턴]
    - 무거운 쿼리는 session_state 캐시 사용
    - 최상단에 컴팩트 컨트롤 행 표시 (selectbox + 버튼)
    - 데이터 미로드 상태에서는 return 으로 조기 종료
    - 로드 후 st.rerun() 으로 갱신
"""

# ════════════════════════════════════════════════════════════════════
# 5. 타이포그래피
# ════════════════════════════════════════════════════════════════════
TYPOGRAPHY_RULES = """
[폰트]
    기본: Pretendard Variable (CDN 자동 로드)
    폴백: Malgun Gothic, -apple-system, sans-serif
    숫자: Consolas (tabular-nums 적용)

[폰트 크기 기준]
    10px  — 배지·레이블·메타 정보 (letter-spacing .12em)
    11px  — 보조 설명·힌트
    12px  — 테이블 셀·차트 주석
    13px  — 탭·버튼·섹션 헤더
    14px  — 기본 본문
    18px  — KPI 아이콘
    30px  — KPI 주요 수치
    36px  — 강조 KPI (페이지 최상위)

[폰트 굵기]
    400 — 일반 본문
    500 — 보조 강조
    600 — 버튼·탭
    700 — 레이블·섹션 제목
    800 — KPI 수치·중요 데이터
"""

# ════════════════════════════════════════════════════════════════════
# 6. 차트 규칙
# ════════════════════════════════════════════════════════════════════
CHART_RULES = """
[Plotly 기본 설정]
    항상 PLOTLY_CFG 딕셔너리를 **언패킹하여 사용:
        fig.update_layout(**PLOTLY_CFG, height=300, ...)

[차트 색상]
    단일 계열:      C["blue"]
    현재/이전 비교: C["blue"] / _c(C["indigo"], 0.67)
    다중 계열:      PLOTLY_PALETTE 순서대로
    강조 항목:      C["blue"], 나머지: _c(C["t3"], 0.33)

[rgba 헬퍼] _c(hex, alpha)
    Plotly는 8자리 hex (#RRGGBBAA) 미지원.
    반투명 색상은 반드시 rgba() 형식 사용:
        C["indigo"] + "aa"  ❌
        _c(C["indigo"], 0.67)  ✅

[차트 크기]
    KPI 행 아래 차트:  height=260
    단독 차트:         height=300~400
    소형 보조 차트:    height=200

[마진]
    기본: margin=dict(l=0, r=0, t=30, b=8)
    레이블 공간 필요: margin=dict(l=0, r=90, t=8, b=8)

[공통 설정]
    showlegend=False (범례는 별도 HTML로 표현)
    bargap=0.25 (막대 그래프)
    tickfont=dict(size=10)
"""

# ════════════════════════════════════════════════════════════════════
# 7. 금지 사항
# ════════════════════════════════════════════════════════════════════
FORBIDDEN = """
❌ 대시보드 파일 내 CSS 직접 정의
   → 모든 CSS는 APP_CSS (ui/design.py) 에 추가 후 사용

❌ C_FINANCE / C_WARD 직접 임포트
   → from ui.design import C 로 통일

❌ 8자리 hex 색상 (#RRGGBBAA)
   → _c(hex, alpha) 헬퍼 또는 rgba() 사용

❌ st.write() 로 데이터 출력
   → st.markdown() + HTML 테이블 패턴 사용

❌ 섹션 카드 없이 차트 직접 출력
   → 반드시 wd-card 컨테이너 안에 포함

❌ 하드코딩된 색상값 (예: color="#1E40AF")
   → C["blue"] 등 토큰 참조

❌ print() 디버깅
   → logger.debug() 사용

❌ 컴포넌트별 중복 CSS 클래스 (nr-kpi, admin-kpi 등)
   → 모두 fn-kpi 로 통일
"""

# ════════════════════════════════════════════════════════════════════
# 파일 가이드 — 어느 파일에 무엇을 추가하는가
# ════════════════════════════════════════════════════════════════════
FILE_GUIDE = """
ui/design.py
    → 색상 토큰 C, APP_CSS, PLOTLY_CFG, 공통 컴포넌트 함수

ui/design_rules.py  (이 파일)
    → 규칙 문서, 신규 개발자 온보딩 자료

ui/dashboard_ui.py
    → design.py 재익스포트 (하위 호환 유지)
    → 병동 전용 ward_kpi_card, ward_section_title 잠정 유지

ui/finance_dashboard.py
    → 원무 대시보드 로직 (탭 함수, 쿼리, 렌더러)
    → UI 기준 파일 — 다른 대시보드는 이 파일 스타일을 따름

ui/hospital_dashboard.py
    → 병동/외래 대시보드 로직

ui/nursing_dashboard.py
    → 간호 대시보드 로직 (fn-kpi 통일 완료)

ui/admin_dashboard.py
    → 관리자 대시보드 (C 토큰 통일 완료)

ui/components.py
    → AI 채팅 결과 카드, 출처 카드, 사이드바 컴포넌트
    → 대시보드 KPI/섹션과 무관한 RAG 전용 컴포넌트
"""
