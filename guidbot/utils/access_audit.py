"""
utils/access_audit.py  ─  사용자 데이터 접근 감사 로그 (2026-05-15)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[목적]
  개인정보보호법 제29조 / 의료법 제21조 준수를 위한
  환자·민감 데이터 접근 이력 기록.

  "누가 언제 어떤 데이터를 조회/다운로드했는가"를
  logs/access_audit.jsonl 에 1줄씩 JSONL 형태로 기록.

[보관 정책]
  90일 — 의료정보 감사 목적 (query_audit.log 와 동일 기준)

[사용법]
    from utils.access_audit import log_access

    # 대시보드 데이터 조회 시
    log_access(
        user_id=st.session_state.get("user_id", "anonymous"),
        action="VIEW",
        data_category="patient_bed_detail",
        dept="내과",
        row_count=len(bed_detail),
    )

    # 다운로드 시
    log_access(
        user_id=st.session_state.get("user_id", "anonymous"),
        action="DOWNLOAD",
        data_category="dept_analysis_region",
        dept="외과",
        row_count=len(df),
        extra={"file_format": "csv"},
    )

[액션 종류]
  VIEW      : 화면 조회 (KPI 카드, 차트, 테이블)
  DOWNLOAD  : 파일 다운로드 (CSV, Excel, PDF)
  SEARCH    : 검색 실행 (챗봇 RAG 쿼리)
  EXPORT    : 보고서 내보내기
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ── 감사 로그 전용 Lock (멀티 스레드 안전 JSONL append) ───────────────
_AUDIT_LOCK = threading.Lock()

# ── 기록 대상 데이터 카테고리 정의 (화이트리스트 — 오타 방지) ─────────
AUDIT_CATEGORIES = {
    # 병동 대시보드
    "patient_bed_detail":       "병상 현황 (환자 포함)",
    "patient_dept_stay":        "진료과 재원 현황",
    "patient_op_stat":          "수술 통계",
    "patient_admit_cands":      "입원 예약 현황",
    "patient_trend":            "병동 주간 추이",
    "patient_dx_today":         "당일 주상병 분포",

    # 진료과 분석
    "dept_analysis_region":     "진료과별 지역 분석",
    "dept_analysis_gender":     "진료과별 성별 분석",
    "dept_analysis_age":        "진료과별 연령대 분석",
    "dept_analysis_cat_age":    "진료과별 구분·연령 분석",
    "dept_analysis_trend":      "진료과별 외래 추세",

    # 원무 대시보드
    "finance_revenue":          "수납·미수금 데이터",
    "finance_region":           "지역별 환자 분포",
    "finance_monthly":          "월별 수익 통계",

    # AI 챗봇
    "chatbot_query":            "규정 검색 (RAG 쿼리)",
    "chatbot_document":         "규정 문서 접근",

    # 관리자
    "admin_log_view":           "운영 로그 조회",
    "admin_vector_rebuild":     "벡터 DB 재구축",
    "admin_doc_download":       "문서 다운로드",
}


def _get_audit_path() -> Path:
    """감사 로그 파일 경로 반환. 설정 실패 시 현재 디렉토리 fallback."""
    try:
        from config.settings import settings
        audit_dir = Path(settings.log_dir)
    except Exception:
        audit_dir = Path("logs")
    audit_dir.mkdir(parents=True, exist_ok=True)
    return audit_dir / "access_audit.jsonl"


def log_access(
    action: str,
    data_category: str,
    user_id: str = "",
    dept: str = "",
    row_count: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    데이터 접근 감사 로그 한 건 기록.

    Args:
        action        : 액션 종류 ("VIEW" / "DOWNLOAD" / "SEARCH" / "EXPORT")
        data_category : AUDIT_CATEGORIES 에 정의된 카테고리 키
        user_id       : 접근한 사용자 ID (세션 기반). 없으면 "anonymous"
        dept          : 관련 진료과·부서 (선택)
        row_count     : 조회된 행 수 (선택)
        extra         : 추가 컨텍스트 딕셔너리 (선택)

    Example::
        from utils.access_audit import log_access
        log_access(
            action="VIEW",
            data_category="patient_bed_detail",
            user_id=st.session_state.get("user_id", ""),
            dept="내과",
            row_count=42,
        )
    """
    # user_id 보정: Streamlit session_state에서 자동 추출 시도
    if not user_id:
        try:
            import streamlit as st
            user_id = (
                st.session_state.get("user_id") or
                st.session_state.get("admin_user") or
                "anonymous"
            )
        except Exception:
            user_id = "anonymous"

    record: Dict[str, Any] = {
        "ts":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id":   user_id,
        "action":    action.upper(),
        "category":  data_category,
        "category_desc": AUDIT_CATEGORIES.get(data_category, data_category),
        "dept":      dept,
        "row_count": row_count,
    }
    if extra:
        record["extra"] = extra

    try:
        audit_path = _get_audit_path()
        with _AUDIT_LOCK:
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as _e:
        # 감사 로그 실패가 서비스를 중단시켜선 안 됨 → 조용히 처리
        try:
            import logging
            logging.getLogger(__name__).warning(f"[감사로그] 기록 실패: {_e}")
        except Exception:
            pass


def load_audit_log(
    days: int = 7,
    action_filter: str = "",
    category_filter: str = "",
    user_filter: str = "",
) -> list[dict]:
    """
    감사 로그 파일에서 최근 N일 데이터 로드 (관리자 뷰어용).

    Args:
        days            : 조회 기간 (기본 7일)
        action_filter   : 액션 필터 ("VIEW", "DOWNLOAD" 등, 빈값=전체)
        category_filter : 카테고리 필터 (빈값=전체)
        user_filter     : 사용자 ID 필터 (빈값=전체)

    Returns:
        dict 리스트 (최신순 정렬)
    """
    audit_path = _get_audit_path()
    if not audit_path.exists():
        return []

    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    results: list[dict] = []

    try:
        with open(audit_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # 날짜 필터
                if rec.get("ts", "") < cutoff:
                    continue

                # 액션 필터
                if action_filter and rec.get("action") != action_filter.upper():
                    continue

                # 카테고리 필터
                if category_filter and category_filter not in rec.get("category", ""):
                    continue

                # 사용자 필터
                if user_filter and user_filter not in rec.get("user_id", ""):
                    continue

                results.append(rec)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).error(f"[감사로그] 로드 실패: {_e}")

    # 최신순 정렬
    results.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return results
