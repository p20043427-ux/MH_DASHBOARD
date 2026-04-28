"""
core/dept_vector_store.py — 부서별 FAISS 벡터 DB 관리 (v1.0, 2026-04-22)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[설계 배경]
G드라이브 규정집 폴더가 부서별로 구성되어 있음:
  G:\\공유드라이브\\좋은문화병원_DATA\\규정집\\
    ├── QPS팀\\*.pdf
    ├── 간호부\\*.pdf
    ├── 공통문서\\*.pdf
    ├── 원무심사팀\\*.pdf
    ├── 의료정보팀\\*.pdf
    ├── 인사총무팀\\*.pdf
    ├── 전산운영팀\\*.pdf
    ├── 진료지원\\*.pdf
    └── *.pdf  (루트에 직접 있는 공통 PDF)

이 구조를 그대로 반영하여 부서별 독립 FAISS 인덱스를 관리하고,
부서 단위 재구축 + 마스터 병합을 지원합니다.

[저장 경로]
  data_rag_working\\depts\\{부서명}\\*.pdf        ← G드라이브 동기화본
  vector_store\\depts\\{부서명}\\index.faiss     ← 부서 전용 FAISS
  vector_store\\index.faiss                      ← 마스터 (모든 부서 병합)

[사용 예시]
  mgr = DeptVectorStoreManager()

  # 부서 목록 조회
  depts = mgr.list_source_depts()       # G드라이브 기준
  stats = mgr.get_dept_stats()          # 부서별 파일/청크 수

  # 부서 단위 재구축
  mgr.rebuild_dept_and_merge("간호부")  # 동기화→재구축→마스터병합 한번에

  # 전체 재구축
  mgr.rebuild_all_depts_and_merge()

  # CLI (build_db.py --dept 간호부)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from config.settings import settings
from core.document_loader import load_and_split
from core.embeddings import get_embeddings_auto
from core.vector_store import VectorStoreManager
from utils.file_sync import sync_pdf_files, SyncResult
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)

# ── 경로 상수 ─────────────────────────────────────────────────────────────
_ROOT         = Path(settings.rag_db_path).parent          # D:\MH\guidbot
_DEPT_WORK    = settings.dept_work_dir    # data_rag_working/depts/
_DEPT_DB      = settings.dept_db_path     # vector_store/depts/
_MASTER_PATH  = Path(settings.rag_db_path)                 # vector_store/
_SRC_ROOT     = Path(settings.rag_source_path)             # G:\공유드라이브\규정집\

# 루트 PDF(폴더 없이 규정집 최상위에 있는 파일)를 담을 가상 부서명
_ROOT_DEPT    = "_공통(루트)"


# ── 결과 데이터클래스 ──────────────────────────────────────────────────────

@dataclass
class DeptRebuildResult:
    dept_name:    str
    pdf_count:    int  = 0
    chunk_count:  int  = 0
    elapsed_sec:  float = 0.0
    success:      bool = False
    error:        str  = ""
    synced:       Optional[SyncResult] = None


@dataclass
class MergeResult:
    total_chunks: int = 0
    dept_count:   int = 0
    elapsed_sec:  float = 0.0
    success:      bool = False
    error:        str  = ""


# ── DeptVectorStoreManager ────────────────────────────────────────────────

class DeptVectorStoreManager:
    """
    G드라이브 규정집 폴더 구조를 반영한 부서별 FAISS 인덱스 관리자.

    [주요 기능]
    - list_source_depts()        : G드라이브 기준 부서 폴더 목록
    - list_indexed_depts()       : FAISS 인덱스가 생성된 부서 목록
    - get_dept_stats()           : 부서별 상세 통계 (파일수, 청크수, 크기 등)
    - sync_dept(dept)            : G드라이브 → 로컬 동기화 (부서 단위)
    - rebuild_dept(dept)         : 한 부서 FAISS 재구축
    - rebuild_dept_and_merge()   : 재구축 + 마스터 병합 (원버튼)
    - merge_all_to_master()      : 모든 부서 인덱스 → 마스터 병합
    - rebuild_all_depts_and_merge(): 전체 부서 재구축 + 마스터 병합
    """

    def __init__(self) -> None:
        _DEPT_WORK.mkdir(parents=True, exist_ok=True)
        _DEPT_DB.mkdir(parents=True, exist_ok=True)

    # ── 조회 ────────────────────────────────────────────────────────────────

    def list_source_depts(self) -> List[str]:
        """
        G드라이브 소스 경로에서 실제 존재하는 부서 폴더 목록을 반환합니다.
        G드라이브 미연결 시 로컬 캐시(_DEPT_WORK) 기준으로 폴백합니다.
        """
        if _SRC_ROOT.exists():
            depts = sorted(
                d.name for d in _SRC_ROOT.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            # 루트에 PDF가 있으면 _공통(루트) 추가
            root_pdfs = list(_SRC_ROOT.glob("*.pdf"))
            if root_pdfs:
                depts = [_ROOT_DEPT] + depts
            return depts
        # G드라이브 미연결 → 로컬 캐시 폴백
        if _DEPT_WORK.exists():
            return sorted(
                d.name for d in _DEPT_WORK.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
        return []

    def list_indexed_depts(self) -> List[str]:
        """FAISS 인덱스가 생성된 부서 목록."""
        if not _DEPT_DB.exists():
            return []
        return sorted(
            d.name for d in _DEPT_DB.iterdir()
            if d.is_dir() and (d / "index.faiss").exists()
        )

    def list_local_depts(self) -> List[str]:
        """로컬 동기화 폴더(_DEPT_WORK)에 PDF가 있는 부서 목록."""
        if not _DEPT_WORK.exists():
            return []
        result = []
        for d in sorted(_DEPT_WORK.iterdir()):
            if d.is_dir() and list(d.rglob("*.pdf")):
                result.append(d.name)
        return result

    def get_dept_stats(self) -> List[Dict]:
        """
        부서별 상태 딕셔너리 리스트 반환.

        반환 필드:
            dept_name  : 부서명
            pdf_count  : 로컬 PDF 파일 수
            indexed    : FAISS 인덱스 존재 여부
            faiss_mb   : FAISS 인덱스 크기 (MB)
            chunk_count: 인덱스 내 벡터 수 (인덱스 있을 때만)
            mtime      : 인덱스 최종 수정 시각 (문자열)
            src_exists : G드라이브 소스 폴더 존재 여부
        """
        all_depts: Dict[str, Dict] = {}

        # G드라이브 / 로컬 파일 수
        for dept in self.list_source_depts():
            all_depts[dept] = {
                "dept_name":  dept,
                "pdf_count":  self._count_local_pdfs(dept),
                "indexed":    False,
                "faiss_mb":   0.0,
                "chunk_count": 0,
                "mtime":      "—",
                "src_exists": self._src_dir(dept).exists() if dept != _ROOT_DEPT else _SRC_ROOT.exists(),
            }

        # 인덱스 정보 추가
        for dept in self.list_indexed_depts():
            if dept not in all_depts:
                all_depts[dept] = {
                    "dept_name":   dept,
                    "pdf_count":   self._count_local_pdfs(dept),
                    "indexed":     True,
                    "faiss_mb":    0.0,
                    "chunk_count": 0,
                    "mtime":       "—",
                    "src_exists":  False,
                }
            faiss_path = _DEPT_DB / dept / "index.faiss"
            if faiss_path.exists():
                mb = faiss_path.stat().st_size / 1024 ** 2
                mtime = datetime.fromtimestamp(faiss_path.stat().st_mtime).strftime("%m-%d %H:%M")
                all_depts[dept].update({
                    "indexed":   True,
                    "faiss_mb":  round(mb, 1),
                    "mtime":     mtime,
                })
                # 벡터 수 (빠르게 읽기 — ntotal만)
                try:
                    import faiss as _faiss
                    idx = _faiss.read_index(str(faiss_path))
                    all_depts[dept]["chunk_count"] = idx.ntotal
                except Exception:
                    pass  # faiss 패키지 없으면 스킵

        return sorted(all_depts.values(), key=lambda x: x["dept_name"])

    # ── 동기화 ──────────────────────────────────────────────────────────────

    def sync_dept(self, dept_name: str) -> SyncResult:
        """
        G드라이브 한 부서 폴더를 로컬로 동기화합니다.

        [_공통(루트) 처리]
        G드라이브 규정집 루트에 있는 PDF(폴더 없이)를 _공통(루트)로 동기화합니다.
        """
        local_dir = _DEPT_WORK / dept_name
        local_dir.mkdir(parents=True, exist_ok=True)

        if dept_name == _ROOT_DEPT:
            # 루트 PDF만 동기화 (하위 폴더 제외)
            return self._sync_root_pdfs(local_dir)

        src_dir = self._src_dir(dept_name)
        logger.info(f"[동기화] {dept_name}: {src_dir} → {local_dir}")
        return sync_pdf_files(src_dir, local_dir)

    def sync_all_depts(self) -> Dict[str, SyncResult]:
        """모든 부서를 G드라이브에서 로컬로 동기화합니다."""
        results: Dict[str, SyncResult] = {}
        for dept in self.list_source_depts():
            results[dept] = self.sync_dept(dept)
        return results

    # ── 재구축 ──────────────────────────────────────────────────────────────

    def rebuild_dept(
        self,
        dept_name: str,
        use_markdown: bool = False,
        chunk_size:   int  = 800,
        overlap:      int  = 150,
    ) -> DeptRebuildResult:
        """
        한 부서의 로컬 PDF 를 읽어 부서 전용 FAISS 인덱스를 재구축합니다.

        [동작]
        1. data_rag_working/depts/{dept_name}/ 에서 PDF 로드
        2. metadata.source_dept = dept_name 태깅
        3. vector_store/depts/{dept_name}/ 에 FAISS 저장

        Returns:
            DeptRebuildResult (success, chunk_count, elapsed_sec, error)
        """
        import time
        t0 = time.perf_counter()
        result = DeptRebuildResult(dept_name=dept_name)

        local_dir = _DEPT_WORK / dept_name
        if not local_dir.exists() or not list(local_dir.rglob("*.pdf")):
            result.error = f"로컬 PDF 없음: {local_dir}"
            logger.warning(f"[rebuild_dept] {dept_name}: {result.error}")
            return result

        # PDF 수
        pdf_files = list(local_dir.rglob("*.pdf"))
        result.pdf_count = len(pdf_files)
        logger.info(f"[rebuild_dept] {dept_name}: {len(pdf_files)}개 PDF 로드 시작")

        try:
            docs = self._load_pdfs(local_dir, use_markdown, chunk_size, overlap)
            if not docs:
                result.error = "로드된 청크 없음"
                return result

            # 부서 메타데이터 태깅
            for d in docs:
                d.metadata["source_dept"]     = dept_name
                d.metadata["category"]        = "regulation"
                d.metadata["source_dept_path"] = str(local_dir)

            # 부서 전용 FAISS 구축
            dept_db_path = _DEPT_DB / dept_name
            dept_db_path.mkdir(parents=True, exist_ok=True)

            mgr = VectorStoreManager(
                db_path    = dept_db_path,
                model_name = settings.embedding_model,
                cache_dir  = str(settings.local_cache_path),
                batch_size = settings.batch_size,
            )
            db = mgr.build(docs)
            if db is None:
                result.error = "FAISS 빌드 실패"
                return result

            result.chunk_count = db.index.ntotal
            result.elapsed_sec = round(time.perf_counter() - t0, 1)
            result.success = True
            logger.info(
                f"[rebuild_dept] {dept_name} 완료: "
                f"{result.chunk_count:,}개 벡터 ({result.elapsed_sec}s)"
            )

        except Exception as exc:
            result.error = str(exc)
            logger.error(f"[rebuild_dept] {dept_name} 실패: {exc}", exc_info=True)

        return result

    def rebuild_dept_and_merge(
        self,
        dept_name:    str,
        sync_first:   bool = True,
        use_markdown: bool = False,
    ) -> tuple[DeptRebuildResult, MergeResult]:
        """
        [통합 원버튼] 부서 동기화 → 재구축 → 마스터 병합을 한 번에 수행합니다.

        Args:
            dept_name:    재구축할 부서명
            sync_first:   True이면 재구축 전 G드라이브 동기화 먼저
            use_markdown: Markdown 변환 방식 사용 여부

        Returns:
            (DeptRebuildResult, MergeResult)
        """
        # Step 1: 동기화 (선택)
        sync_result = None
        if sync_first:
            sync_result = self.sync_dept(dept_name)

        # Step 2: 재구축
        rb = self.rebuild_dept(dept_name, use_markdown=use_markdown)
        if sync_result:
            rb.synced = sync_result

        if not rb.success:
            return rb, MergeResult(error=f"{dept_name} 재구축 실패: {rb.error}")

        # Step 3: 마스터 병합
        mg = self.merge_all_to_master()
        return rb, mg

    def rebuild_all_depts_and_merge(
        self,
        sync_first:   bool = True,
        use_markdown: bool = False,
    ) -> tuple[List[DeptRebuildResult], MergeResult]:
        """
        모든 부서를 재구축하고 마스터 인덱스를 재생성합니다.
        동기화 → 각 부서 재구축 → 마스터 병합 순서로 진행합니다.
        """
        if sync_first:
            logger.info("[rebuild_all] 전체 동기화 시작")
            self.sync_all_depts()

        depts = self.list_local_depts()
        results: List[DeptRebuildResult] = []
        for dept in depts:
            r = self.rebuild_dept(dept, use_markdown=use_markdown)
            results.append(r)

        mg = self.merge_all_to_master()
        return results, mg

    # ── 마스터 병합 ─────────────────────────────────────────────────────────

    def merge_all_to_master(self) -> MergeResult:
        """
        모든 부서 FAISS 인덱스를 병합하여 마스터 인덱스를 재생성합니다.

        [동작]
        1. vector_store/depts/*/index.faiss 로드
        2. merge_from() 으로 병합
        3. 기존 마스터 백업 후 저장

        [주의]
        이 함수로 생성된 마스터는 규정집(부서별) 내용만 포함합니다.
        DB명세서·스키마·쿼리 등을 포함하려면 build_db.py 를 실행하세요.
        """
        import time
        t0 = time.perf_counter()
        result = MergeResult()

        indexed = self.list_indexed_depts()
        if not indexed:
            result.error = "병합할 부서 인덱스가 없습니다"
            logger.warning(f"[merge_master] {result.error}")
            return result

        logger.info(f"[merge_master] {len(indexed)}개 부서 인덱스 병합 시작: {indexed}")

        try:
            emb = get_embeddings_auto()
            master: Optional[FAISS] = None

            for dept in indexed:
                dept_path = _DEPT_DB / dept
                try:
                    db = FAISS.load_local(
                        str(dept_path), emb,
                        allow_dangerous_deserialization=True,
                    )
                    if master is None:
                        master = db
                    else:
                        master.merge_from(db)
                    logger.info(
                        f"  [병합] {dept}: {db.index.ntotal:,}개 벡터 추가"
                    )
                except Exception as exc:
                    logger.warning(f"  [병합 스킵] {dept}: {exc}")

            if master is None:
                result.error = "유효한 부서 인덱스 없음"
                return result

            # 기존 마스터 백업 (재구축 전 안전망)
            self._backup_master()

            # 마스터 저장
            _MASTER_PATH.mkdir(parents=True, exist_ok=True)
            master.save_local(str(_MASTER_PATH))

            result.total_chunks = master.index.ntotal
            result.dept_count   = len(indexed)
            result.elapsed_sec  = round(time.perf_counter() - t0, 1)
            result.success      = True
            logger.info(
                f"[merge_master] 완료: {result.dept_count}개 부서, "
                f"{result.total_chunks:,}개 벡터 ({result.elapsed_sec}s)"
            )

        except Exception as exc:
            result.error = str(exc)
            logger.error(f"[merge_master] 실패: {exc}", exc_info=True)

        return result

    # ── Private 헬퍼 ────────────────────────────────────────────────────────

    def _src_dir(self, dept_name: str) -> Path:
        """G드라이브 부서 폴더 경로."""
        return _SRC_ROOT / dept_name

    def _local_dir(self, dept_name: str) -> Path:
        """로컬 동기화 부서 폴더 경로."""
        return _DEPT_WORK / dept_name

    def _count_local_pdfs(self, dept_name: str) -> int:
        """로컬 부서 폴더의 PDF 파일 수."""
        local = _DEPT_WORK / dept_name
        if not local.exists():
            return 0
        return len(list(local.rglob("*.pdf")))

    def _load_pdfs(
        self,
        pdf_dir:      Path,
        use_markdown: bool,
        chunk_size:   int,
        overlap:      int,
    ) -> List[Document]:
        """PDF 디렉토리를 Document 리스트로 로드합니다."""
        if use_markdown:
            try:
                from core.pdf_to_markdown import batch_convert_pdfs
                docs = batch_convert_pdfs(
                    pdf_dir=pdf_dir,
                    save_md=False,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                if docs:
                    return docs
            except Exception as exc:
                logger.warning(f"Markdown 변환 실패 → 기존 방식 폴백: {exc}")

        # 기존 방식
        load_result = load_and_split(pdf_dir)
        return load_result.documents

    def _sync_root_pdfs(self, local_dir: Path) -> SyncResult:
        """G드라이브 규정집 루트의 PDF(하위 폴더 제외)를 동기화합니다."""
        from utils.file_sync import SyncResult
        import shutil as _shutil

        result = SyncResult()
        if not _SRC_ROOT.exists():
            logger.warning(f"G드라이브 소스 없음: {_SRC_ROOT}")
            return result

        local_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(_SRC_ROOT.glob("*.pdf")):  # 하위폴더 제외
            dst = local_dir / src.name
            try:
                if not dst.exists():
                    _shutil.copy2(src, dst)
                    result.copied.append(src.name)
                elif src.stat().st_mtime > dst.stat().st_mtime:
                    _shutil.copy2(src, dst)
                    result.updated.append(src.name)
                else:
                    result.skipped += 1
            except OSError as exc:
                result.failed.append(src.name)
                logger.error(f"루트 PDF 복사 실패 {src.name}: {exc}")
        result.log_summary()
        return result

    def _backup_master(self) -> None:
        """마스터 인덱스 백업 (최근 5개 보관)."""
        master_faiss = _MASTER_PATH / "index.faiss"
        if not master_faiss.exists():
            return
        backup_dir = Path(settings.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backup_dir / f"vector_store_{ts}"
        try:
            shutil.copytree(str(_MASTER_PATH), str(dest),
                            ignore=shutil.ignore_patterns("depts"))  # dept 하위 제외
            logger.info(f"[backup] 마스터 백업 완료: {dest.name}")
            # 최근 5개 보관
            old_bks = sorted(backup_dir.glob("vector_store_*"))
            for old in old_bks[:-5]:
                shutil.rmtree(old)
                logger.info(f"[backup] 오래된 백업 삭제: {old.name}")
        except Exception as exc:
            logger.warning(f"[backup] 마스터 백업 실패 (계속 진행): {exc}")
