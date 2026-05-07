"""
utils/auto_backup.py  ─  벡터DB 자동 백업 스케줄러 (v1.0, 2026-05-07)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[역할]
  앱 실행 중 백그라운드 스레드로 주 1회(7일 간격) 벡터DB 마스터 인덱스를
  자동으로 백업합니다.

[보관 정책]
  · 명명 규칙 : weekly_YYYYMMDD_HHMMSS (수동 백업과 구분)
  · 최대 보관 : 4개 → 약 1달치, 초과 시 오래된 것부터 자동 삭제
  · 대상       : 마스터 index.faiss / index.pkl (depts/ 서브인덱스 제외)

[동작 흐름]
  1. start_auto_backup() 호출 → 싱글톤 스케줄러 생성 + 데몬 스레드 시작
  2. 스레드 내부: 1시간마다 "마지막 weekly 백업으로부터 7일 경과" 체크
  3. 조건 충족 시 → _do_backup() → _prune()
  4. Streamlit @st.cache_resource 로 앱 생명주기 동안 1회만 기동

[사용 예시]
  from utils.auto_backup import start_auto_backup, get_auto_backup_scheduler
  start_auto_backup()                     # 앱 시작 시 1회 호출
  sch = get_auto_backup_scheduler()
  sch.last_backup_at()                    # 마지막 백업 시각 (UI 표시용)
  sch.next_backup_at()                    # 다음 예약 시각
  sch.weekly_backups()                    # weekly 백업 목록 [{name, created_at, size_mb}]
"""

from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# ── 로거 ────────────────────────────────────────────────────────────
try:
    from config.settings import settings as _settings
    from utils.logger import get_logger
    _logger = get_logger(__name__, log_dir=_settings.log_dir)
except Exception:
    import logging
    _logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────
_INTERVAL_DAYS = 7          # 백업 주기 (7일)
_MAX_BACKUPS   = 4          # 최대 보관 개수 (약 1달치)
_PREFIX        = "weekly_"  # weekly 자동 백업 구분 접두어
_CHECK_SEC     = 3600       # 스케줄 체크 주기 (1시간)


# ══════════════════════════════════════════════════════════════════════
#  AutoBackupScheduler 클래스
# ══════════════════════════════════════════════════════════════════════

class AutoBackupScheduler:
    """
    백그라운드 데몬 스레드로 주 1회 자동 백업을 수행하는 스케줄러.

    Streamlit 환경에서는 @st.cache_resource 싱글톤으로 1회만 생성됩니다.
    """

    def __init__(self, db_path: Path, backup_dir: Path) -> None:
        self._db_path    = db_path       # 마스터 FAISS 인덱스 경로
        self._backup_dir = backup_dir    # 백업 저장 디렉토리
        self._thread: Optional[threading.Thread] = None
        self._stop_flag  = threading.Event()

    # ── 시작 / 중지 ────────────────────────────────────────────────

    def start(self) -> None:
        """백그라운드 스케줄 스레드 시작 (이미 실행 중이면 무시)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,       # 앱 종료 시 스레드도 자동 종료
            name="auto-backup-weekly",
        )
        self._thread.start()
        _logger.info("[AutoBackup] 주 1회 자동 백업 스케줄러 시작")

    def stop(self) -> None:
        """스케줄 스레드 중지 신호 전송."""
        self._stop_flag.set()

    # ── 메인 루프 ────────────────────────────────────────────────

    def _run(self) -> None:
        """1시간마다 백업 필요 여부를 체크하는 루프."""
        while not self._stop_flag.is_set():
            try:
                self._check_and_backup()
            except Exception as exc:
                _logger.error(f"[AutoBackup] 스케줄 체크 오류: {exc}", exc_info=True)
            # 1시간 대기 (stop_flag 설정 시 즉시 탈출)
            self._stop_flag.wait(_CHECK_SEC)

    def _check_and_backup(self) -> None:
        """마지막 weekly 백업이 7일 이상 경과했으면 백업 실행."""
        last = self._last_backup_time()
        now  = datetime.now()

        if last is None:
            # weekly 백업이 한 번도 없으면 즉시 실행
            _logger.info("[AutoBackup] 첫 번째 weekly 백업 실행")
            self._do_backup()
            self._prune()
        elif (now - last).days >= _INTERVAL_DAYS:
            _logger.info(
                f"[AutoBackup] {_INTERVAL_DAYS}일 경과 — 자동 백업 실행 "
                f"(마지막: {last.strftime('%Y-%m-%d %H:%M')})"
            )
            self._do_backup()
            self._prune()

    # ── 백업 실행 ────────────────────────────────────────────────

    def _do_backup(self) -> None:
        """현재 마스터 인덱스를 weekly_ 이름으로 백업."""
        index_file = self._db_path / "index.faiss"
        if not index_file.exists():
            # 인덱스가 없으면 백업 불가 (정상 상태: DB 미구축)
            _logger.warning("[AutoBackup] index.faiss 없음 — 백업 건너뜀")
            return

        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = self._backup_dir / f"{_PREFIX}{ts}"

        try:
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            # depts/ 는 부서별 인덱스이므로 마스터 백업에서 제외
            shutil.copytree(
                str(self._db_path),
                str(dst),
                ignore=shutil.ignore_patterns("depts"),
            )
            _logger.info(f"[AutoBackup] 백업 완료 → {dst.name}")
        except Exception as exc:
            _logger.error(f"[AutoBackup] 백업 생성 실패: {exc}", exc_info=True)

    def _prune(self) -> None:
        """_MAX_BACKUPS 초과 weekly 백업을 오래된 것부터 삭제."""
        if not self._backup_dir.exists():
            return

        # weekly_ 접두어 백업만 대상 (수동 백업에는 영향 없음)
        bks = sorted(
            [d for d in self._backup_dir.iterdir()
             if d.is_dir() and d.name.startswith(_PREFIX)],
            key=lambda d: d.stat().st_mtime,  # 오래된 것 = 앞쪽
        )

        while len(bks) > _MAX_BACKUPS:
            oldest = bks.pop(0)
            try:
                shutil.rmtree(str(oldest))
                _logger.info(f"[AutoBackup] 오래된 백업 삭제: {oldest.name}")
            except Exception as exc:
                _logger.warning(f"[AutoBackup] 백업 삭제 실패: {oldest.name} — {exc}")

    # ── 조회용 Public API (UI 표시용) ─────────────────────────────

    def _last_backup_time(self) -> Optional[datetime]:
        """가장 최근 weekly 백업의 생성 시각. 없으면 None."""
        if not self._backup_dir.exists():
            return None
        bks = [
            d for d in self._backup_dir.iterdir()
            if d.is_dir() and d.name.startswith(_PREFIX)
        ]
        if not bks:
            return None
        latest = max(bks, key=lambda d: d.stat().st_mtime)
        return datetime.fromtimestamp(latest.stat().st_mtime)

    def last_backup_at(self) -> str:
        """마지막 자동 백업 시각 문자열 (없으면 '없음')."""
        t = self._last_backup_time()
        return t.strftime("%Y-%m-%d %H:%M") if t else "없음"

    def next_backup_at(self) -> str:
        """다음 예약 백업 시각 문자열."""
        t = self._last_backup_time()
        if t is None:
            return "앱 가동 후 최초 체크 시"
        nxt = t + timedelta(days=_INTERVAL_DAYS)
        return nxt.strftime("%Y-%m-%d %H:%M")

    def is_running(self) -> bool:
        """스케줄러 스레드가 살아있는지 여부."""
        return bool(self._thread and self._thread.is_alive())

    def weekly_backups(self) -> List[Dict]:
        """
        weekly 자동 백업 목록 반환.
        반환 형식: [{"name": ..., "created_at": ..., "size_mb": ...}]
        최신순 정렬.
        """
        if not self._backup_dir.exists():
            return []
        result = []
        for d in sorted(
            [x for x in self._backup_dir.iterdir()
             if x.is_dir() and x.name.startswith(_PREFIX)],
            key=lambda x: x.stat().st_mtime,
            reverse=True,   # 최신이 맨 위
        ):
            try:
                mb      = sum(
                    f.stat().st_size for f in d.rglob("*") if f.is_file()
                ) / 1024 ** 2
                created = datetime.fromtimestamp(
                    d.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M")
            except Exception:
                mb, created = 0.0, "—"
            result.append({
                "name":       d.name,
                "created_at": created,
                "size_mb":    round(mb, 1),
            })
        return result


# ══════════════════════════════════════════════════════════════════════
#  싱글톤 + 편의 함수
# ══════════════════════════════════════════════════════════════════════

_instance: Optional[AutoBackupScheduler] = None
_lock = threading.Lock()


def get_auto_backup_scheduler() -> AutoBackupScheduler:
    """AutoBackupScheduler 싱글톤 반환 (없으면 생성)."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                from config.settings import settings
                _instance = AutoBackupScheduler(
                    db_path=settings.rag_db_path,
                    backup_dir=settings.backup_dir,
                )
    return _instance


def start_auto_backup() -> None:
    """
    자동 백업 스케줄러를 시작합니다.
    admin_app.py의 @st.cache_resource 함수에서 1회만 호출하세요.
    """
    get_auto_backup_scheduler().start()
