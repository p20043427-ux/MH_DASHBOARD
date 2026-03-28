"""
utils/dashboard_monitor.py  ─  병동 대시보드 사용자 로그 / 모니터링 (v1.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[수집 데이터]
  ① 사용자 액션 로그
     - 빠른 분석 버튼 클릭 (어떤 버튼, 언제)
     - AI 채팅 질문 (질문 내용, 응답 소요 시간, 성공 여부)
     - 새로고침 / 병실현황 / 병동 필터 변경
     - 쿼리 실패 / Circuit Breaker 발동

  ② 성능 메트릭
     - 쿼리별 응답 시간 (ms)
     - AI LLM 응답 시간
     - 오류율 / 실패 쿼리 목록

[저장 형식]
  logs/dashboard_events.jsonl   ← 이벤트 로그 (1줄 = 1이벤트)
  logs/dashboard_metrics.json   ← 집계 메트릭 (주기적 갱신)

[사용법]
  from utils.dashboard_monitor import get_dash_monitor

  mon = get_dash_monitor()
  mon.log_action("quick_btn", label="익일 가용")
  mon.log_llm_query(question="위험 병동?", elapsed_ms=1230, success=True)

[설계 원칙]
  - 모든 쓰기는 threading.Lock 보호 (동시접속 20명 안전)
  - 실패해도 대시보드 동작에 영향 없음 (try-except 완전 격리)
  - JSONL 형식 → pandas / Excel 분석 가능
  - 로그는 30일 자동 순환 (TimedRotatingFileHandler 동일 방식)
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  경로 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_log_dir() -> Path:
    """로그 디렉토리 반환. settings 없어도 안전하게 fallback."""
    try:
        from config.settings import settings
        base = Path(settings.log_dir)
    except Exception:
        base = Path("logs")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _events_path() -> Path:
    return _get_log_dir() / "dashboard_events.jsonl"


def _metrics_path() -> Path:
    return _get_log_dir() / "dashboard_metrics.json"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  데이터 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class DashEvent:
    """단일 대시보드 이벤트."""
    event_id:    str   = field(default_factory=lambda: uuid.uuid4().hex[:10])
    timestamp:   str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type:  str   = ""       # action / llm / query_fail / system
    action:      str   = ""       # quick_btn / refresh / room_panel / ward_filter / llm_chat
    label:       str   = ""       # 버튼 라벨 or 질문 앞 30자
    ward:        str   = "전체"   # 선택 병동
    elapsed_ms:  int   = 0        # 소요 시간
    success:     bool  = True
    detail:      str   = ""       # 추가 정보 (오류 메시지 등)
    session_id:  str   = ""       # Streamlit 세션 ID (마스킹)


@dataclass
class DashMetrics:
    """집계 메트릭. dashboard_metrics.json에 저장."""
    total_actions:      int   = 0    # 총 사용자 액션 수
    total_llm_queries:  int   = 0    # AI 채팅 총 질문 수
    total_llm_errors:   int   = 0    # LLM 오류 수
    total_query_fails:  int   = 0    # DB 쿼리 실패 수
    avg_llm_ms:         float = 0.0  # LLM 평균 응답 시간 (ms)
    avg_query_ms:       float = 0.0  # DB 쿼리 평균 응답 시간 (ms)
    quick_btn_counts:   Dict[str, int] = field(default_factory=dict)  # 버튼별 클릭 수
    ward_filter_counts: Dict[str, int] = field(default_factory=dict)  # 병동 필터별 사용 수
    last_updated:       str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_keys:         List[str] = field(default_factory=list)       # 최근 실패 쿼리 키


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  메인 모니터 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DashboardMonitor:
    """
    병동 대시보드 전용 사용자 활동 로그 + 성능 모니터.

    싱글턴 패턴 — get_dash_monitor() 로 접근.
    모든 public 메서드는 try-except 완전 격리:
      실패해도 대시보드 본 기능에 절대 영향 없음.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: Optional[DashMetrics] = None
        self._llm_times: List[int] = []   # 최근 LLM 응답 시간 목록 (최대 100개)
        self._query_times: List[int] = []  # 최근 쿼리 응답 시간 목록

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────

    def _load_metrics(self) -> DashMetrics:
        """metrics JSON 로드. 없으면 새로 생성."""
        if self._metrics is not None:
            return self._metrics
        try:
            p = _metrics_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self._metrics = DashMetrics(**{
                    k: v for k, v in data.items()
                    if k in DashMetrics.__dataclass_fields__
                })
            else:
                self._metrics = DashMetrics()
        except Exception:
            self._metrics = DashMetrics()
        return self._metrics

    def _save_metrics(self, m: DashMetrics) -> None:
        """metrics JSON 저장."""
        try:
            m.last_updated = datetime.now(timezone.utc).isoformat()
            _metrics_path().write_text(
                json.dumps(asdict(m), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _append_event(self, ev: DashEvent) -> None:
        """이벤트를 JSONL에 append."""
        try:
            line = json.dumps(asdict(ev), ensure_ascii=False) + "\n"
            with self._lock:
                with _events_path().open("a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            pass

    def _session_id(self) -> str:
        """Streamlit 세션 ID 앞 8자리 (익명화)."""
        try:
            import streamlit as st
            sid = st.runtime.scriptrunner.get_script_run_ctx().session_id
            return sid[:8]
        except Exception:
            return "unknown"

    def _current_ward(self) -> str:
        """현재 선택된 병동."""
        try:
            import streamlit as st
            return st.session_state.get("ward_selected", "전체")
        except Exception:
            return "전체"

    # ── Public API ─────────────────────────────────────────────────────

    def log_action(self, action: str, label: str = "", detail: str = "") -> None:
        """
        사용자 액션 로그.

        사용 예:
            mon.log_action("quick_btn", label="익일 가용")
            mon.log_action("refresh")
            mon.log_action("ward_filter", label="08병동")
            mon.log_action("room_panel", label="열기")
        """
        try:
            ev = DashEvent(
                event_type="action",
                action=action,
                label=label[:50],
                ward=self._current_ward(),
                session_id=self._session_id(),
                detail=detail[:100],
            )
            self._append_event(ev)

            # 메트릭 갱신
            with self._lock:
                m = self._load_metrics()
                m.total_actions += 1
                if action == "quick_btn":
                    m.quick_btn_counts[label] = m.quick_btn_counts.get(label, 0) + 1
                elif action == "ward_filter":
                    m.ward_filter_counts[label] = m.ward_filter_counts.get(label, 0) + 1
                self._save_metrics(m)
        except Exception:
            pass

    def log_llm_query(
        self,
        question: str,
        elapsed_ms: int,
        success: bool,
        error: str = "",
    ) -> None:
        """
        AI 채팅 질문 로그.

        사용 예:
            t0 = time.perf_counter()
            # ... LLM 호출 ...
            elapsed = int((time.perf_counter() - t0) * 1000)
            mon.log_llm_query(question=prompt, elapsed_ms=elapsed, success=True)
        """
        try:
            _q = (question[:40] + "…") if len(question) > 40 else question
            ev = DashEvent(
                event_type="llm",
                action="llm_chat",
                label=_q,
                ward=self._current_ward(),
                elapsed_ms=elapsed_ms,
                success=success,
                detail=error[:150] if error else "",
                session_id=self._session_id(),
            )
            self._append_event(ev)

            with self._lock:
                m = self._load_metrics()
                m.total_llm_queries += 1
                if not success:
                    m.total_llm_errors += 1
                self._llm_times.append(elapsed_ms)
                if len(self._llm_times) > 100:
                    self._llm_times.pop(0)
                if self._llm_times:
                    m.avg_llm_ms = round(sum(self._llm_times) / len(self._llm_times), 1)
                self._save_metrics(m)
        except Exception:
            pass

    def log_query_fail(self, key: str, error: str = "") -> None:
        """
        DB 쿼리 실패 로그.

        hospital_dashboard.py 의 _query() 실패 시 호출.
        """
        try:
            ev = DashEvent(
                event_type="query_fail",
                action="db_query",
                label=key,
                ward=self._current_ward(),
                success=False,
                detail=error[:150],
                session_id=self._session_id(),
            )
            self._append_event(ev)

            with self._lock:
                m = self._load_metrics()
                m.total_query_fails += 1
                # 최근 실패 쿼리 키 최대 20개 유지
                if key not in m.error_keys:
                    m.error_keys.append(key)
                if len(m.error_keys) > 20:
                    m.error_keys = m.error_keys[-20:]
                self._save_metrics(m)
        except Exception:
            pass

    def log_query_time(self, key: str, elapsed_ms: int) -> None:
        """
        DB 쿼리 응답 시간 로그 (성공 건만 기록).
        """
        try:
            with self._lock:
                self._query_times.append(elapsed_ms)
                if len(self._query_times) > 200:
                    self._query_times.pop(0)
                m = self._load_metrics()
                if self._query_times:
                    m.avg_query_ms = round(
                        sum(self._query_times) / len(self._query_times), 1
                    )
                self._save_metrics(m)
        except Exception:
            pass

    def get_metrics(self) -> DashMetrics:
        """현재 집계 메트릭 반환 (뷰어용)."""
        try:
            with self._lock:
                return self._load_metrics()
        except Exception:
            return DashMetrics()

    def get_recent_events(self, n: int = 50) -> List[Dict[str, Any]]:
        """
        최근 N개 이벤트 반환 (뷰어용).
        JSONL 파일 끝에서 역방향으로 읽어 최신 순 반환.
        """
        try:
            p = _events_path()
            if not p.exists():
                return []
            lines = p.read_text(encoding="utf-8").strip().split("\n")
            lines = [l for l in lines if l.strip()]
            recent = lines[-n:][::-1]  # 최신 n개, 역순
            result = []
            for line in recent:
                try:
                    result.append(json.loads(line))
                except Exception:
                    pass
            return result
        except Exception:
            return []

    def clear_old_events(self, keep_days: int = 30) -> int:
        """
        30일 이상 된 이벤트 정리. 삭제된 건수 반환.
        """
        try:
            p = _events_path()
            if not p.exists():
                return 0
            cutoff = time.time() - keep_days * 86400
            kept, removed = [], 0
            for line in p.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                    ts_str = ev.get("timestamp", "")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    if ts >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except Exception:
                    kept.append(line)  # 파싱 불가 → 보존
            with self._lock:
                p.write_text("\n".join(kept) + "\n", encoding="utf-8")
            return removed
        except Exception:
            return 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  싱글턴 접근자
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_monitor_instance: Optional[DashboardMonitor] = None
_monitor_lock = threading.Lock()


def get_dash_monitor() -> DashboardMonitor:
    """프로세스 전역 DashboardMonitor 싱글턴 반환."""
    global _monitor_instance
    if _monitor_instance is None:
        with _monitor_lock:
            if _monitor_instance is None:
                _monitor_instance = DashboardMonitor()
    return _monitor_instance