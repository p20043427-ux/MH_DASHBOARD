"""
config/ui_labels.py — UI 화면 표시 레이블 관리 (2026-05-11)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
병원명, 사이드바 버튼 명칭 등 화면 표시 텍스트를 JSON 파일로 관리합니다.

[저장 경로]
    config/ui_labels.json  (이 파일과 같은 디렉토리)

[사용처]
    · ui/sidebar.py        — 로고 병원명, 검색 모드 버튼, 바로가기 버튼
    · ui/hospital_dashboard_v2.py — v2 다크 헤더 병원명
    · ui/admin_dashboard.py  — 환경설정 탭 "화면 표시 설정" 섹션에서 편집

[캐시 정책]
    파일 읽기는 매우 빠르므로(수 KB JSON) 별도 캐시 없이 직접 읽습니다.
    관리자 저장 후 st.rerun() 하면 즉시 반영됩니다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

# ── 파일 경로 ──────────────────────────────────────────────────────────────
_CFG_PATH: Path = Path(__file__).resolve().parent / "ui_labels.json"

# ── 기본값 ─────────────────────────────────────────────────────────────────
# 파일이 없거나 키가 누락됐을 때 사용되는 fallback 값.
DEFAULTS: Dict[str, Any] = {
    "hospital_name": "좋은문화병원",
    "search_modes": [
        {"id": "fast",         "label": "빠른 검색",  "meta": "3건 · 빠른 응답"},
        {"id": "standard",     "label": "표준 검색",  "meta": "5건 · 균형 검색"},
        {"id": "deep",         "label": "심층 검색",  "meta": "10건 · 정밀 분석"},
        {"id": "separator",    "label": "",           "meta": ""},
        {"id": "data_analysis","label": "데이터 분석","meta": "Oracle DB · 차트"},
    ],
    "shortcuts": {
        "docs_label":   "회람 문서",
        "clinic_label": "진료",
        "admin_label":  "원무",
        "nurse_label":  "간호",
    },
}


def load_ui_labels() -> Dict[str, Any]:
    """
    ui_labels.json 을 읽어 레이블 딕셔너리를 반환합니다.

    · 파일 없음  → DEFAULTS 반환
    · 키 누락    → 해당 키만 DEFAULTS 로 채움 (하위 호환)
    · 파싱 오류  → DEFAULTS 반환
    """
    try:
        if _CFG_PATH.exists():
            raw = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
            # 최상위 키 누락 방어 — DEFAULTS 복사 후 파일 값으로 덮어쓰기
            merged: Dict[str, Any] = {}
            for k, v in DEFAULTS.items():
                merged[k] = raw.get(k, v)
            return merged
    except Exception:
        pass
    return {k: v for k, v in DEFAULTS.items()}


def save_ui_labels(data: Dict[str, Any]) -> bool:
    """
    레이블 딕셔너리를 ui_labels.json 에 저장합니다.

    Returns:
        True  — 저장 성공
        False — 파일 권한 등 오류
    """
    try:
        _CFG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def get_hospital_name() -> str:
    """병원명만 필요할 때의 편의 함수."""
    return load_ui_labels().get("hospital_name", DEFAULTS["hospital_name"])


def get_search_modes() -> List[Dict[str, Any]]:
    """검색 모드 목록만 필요할 때의 편의 함수."""
    return load_ui_labels().get("search_modes", DEFAULTS["search_modes"])


def get_shortcuts() -> Dict[str, str]:
    """바로가기 버튼 레이블만 필요할 때의 편의 함수."""
    return load_ui_labels().get("shortcuts", DEFAULTS["shortcuts"])
