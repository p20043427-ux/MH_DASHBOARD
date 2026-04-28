"""
build_db.py  ─  RAG 지식 베이스 구축 배치 스크립트 (v3.2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   
##  변경사항 테스트 
[v3.2 변경사항 — PDF → Markdown 변환 방식 추가]

■ --use-markdown 플래그 신규 추가
  · pdfplumber 로 표 구조를 보존하여 Markdown 으로 변환
  · 제N조 / 제N장 헤더 기반 청킹 → 조항이 두 청크에 걸치지 않음
  · NEDIS 코드표처럼 표가 많은 문서에 권장
  · 변환된 .md 파일은 docs/markdown/ 에 저장 (검수용)
  · --chunk-size / --overlap 파라미터로 크기 조정 가능

[v3.1 변경사항 — DB 명세서 PDF 자동 포함]

■ 새 소스 디렉토리: docs/db_manuals/
  · DB 관련 PDF 를 이 폴더에만 넣으면 build_db.py 실행 시 자동 포함
  · 별도 설정 없이 동작 — 폴더가 없거나 비어있으면 건너뜀
  · metadata.category = "db_manual" 태그로 출처 구분

■ 처리 흐름 (v3.2)
  ┌─────────────────────────────────────────────────────────┐
  │  Step 1: G드라이브 → data_rag_working/ PDF 동기화       │
  │  Step 2: data_rag_working/ 규정집 PDF 로드              │
  │          → --use-markdown 이면 Markdown 변환 방식       │
  │          → metadata.category = "regulation"             │
  │  Step 3: docs/db_manuals/ DB 명세서 PDF 로드            │
  │          → --use-markdown 이면 Markdown 변환 방식       │
  │          → metadata.category = "db_manual"              │
  │  Step 4: Oracle DB 스키마 추출 (선택)                   │
  │          → metadata.category = "db_schema"              │
  │  Step 5: (규정집 + DB명세서 + DB스키마) 통합 벡터DB 구축 │
  └─────────────────────────────────────────────────────────┘

■ 폴더 구조
  D:\\MH\\guidbot\\
  ├── data_rag_working\\      규정집 PDF (G드라이브 동기화)
  ├── docs\\
  │   ├── db_manuals\\       DB 명세서 PDF 여기에 넣기
  │   └── markdown\\         --use-markdown 변환 결과 (.md 검수용)
  └── vector_store\\          통합 FAISS

[실행 방법]
  python build_db.py                              # 전체 실행 (기존 방식)
  python build_db.py --use-markdown               # Markdown 변환 방식 (권장)
  python build_db.py --use-markdown --no-sync     # 동기화 없이 Markdown 변환
  python build_db.py --no-sync                    # G드라이브 동기화 건너뜀
  python build_db.py --no-db-schema               # DB 스키마 추출 건너뜀
  python build_db.py --no-sync --no-db-schema     # 빠른 로컬 재구축
  python build_db.py --db-docs-only               # DB 명세서 PDF 만 재빌드
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List

import logging

logging.getLogger("pypdf").setLevel(logging.ERROR)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import settings
from core.document_loader import load_and_split, LoadResult
from core.vector_store import VectorStoreManager
from langchain_core.documents import Document
from utils.file_sync import sync_pdf_files
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)


# ──────────────────────────────────────────────────────────────────────
#  인수 파싱
# ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="좋은문화병원 가이드봇 RAG Vector DB 구축",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python build_db.py                              # 전체 실행 (기존 방식)
  python build_db.py --use-markdown --no-sync     # Markdown 변환 방식 (권장)
  python build_db.py --no-sync                    # G드라이브 연결 없을 때
  python build_db.py --no-sync --no-db-schema     # PDF 만 빠른 재구축
  python build_db.py --db-docs-only               # DB 명세서 PDF 만 테스트
        """,
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=settings.rag_source_path,
        help=f"규정집 PDF 소스 경로 (기본: {settings.rag_source_path})",
    )
    parser.add_argument(
        "--db-docs-dir",
        type=Path,
        default=settings.db_docs_dir,
        help=f"DB 명세서 PDF 경로 (기본: {settings.db_docs_dir})",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        default=False,
        help="G드라이브 동기화 건너뜀",
    )
    parser.add_argument(
        "--no-db-schema",
        action="store_true",
        default=False,
        help="Oracle DB 스키마 추출 건너뜀",
    )
    parser.add_argument(
        "--no-db-docs",
        action="store_true",
        default=False,
        help="docs/db_manuals/ PDF 로드 건너뜀",
    )
    parser.add_argument(
        "--db-docs-only",
        action="store_true",
        default=False,
        help="DB 명세서 PDF 만 로드하여 단독 테스트 (벡터DB 재구축)",
    )
    # ── v3.2 신규 ──────────────────────────────────────────────────────
    parser.add_argument(
        "--use-markdown",
        action="store_true",
        default=False,
        help=(
            "[v3.2 신규] PDF → Markdown 변환 방식으로 청킹. "
            "pdfplumber 로 표 구조를 보존하고 제N조 헤더 경계로 청킹. "
            "NEDIS 코드표 등 표가 많은 문서에 권장. "
            "(pip install pdfplumber 필요)"
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=800,
        help="청크 최대 크기 (기본: 800, --use-markdown 적용 시에만 사용)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=150,
        help="청크 간 중복 크기 (기본: 150, --use-markdown 적용 시에만 사용)",
    )
    # ── v3.3 신규: 부서별 재구축 ────────────────────────────────────────────
    parser.add_argument(
        "--dept",
        type=str,
        default=None,
        metavar="DEPT_NAME",
        help=(
            "[v3.3 신규] 부서명을 지정하여 해당 부서만 재구축합니다.\n"
            "예: --dept 간호부  → 간호부 동기화→재구축→마스터병합\n"
            "    --dept all     → 모든 부서 재구축 + 마스터병합\n"
            "G드라이브 규정집/ 하위 폴더명과 일치해야 합니다."
        ),
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        help="[--dept 와 함께 사용] 재구축 후 마스터 병합 건너뜀 (부서 인덱스만 갱신)",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────
#  카테고리 메타데이터 태깅
# ──────────────────────────────────────────────────────────────────────


def _tag_category(
    docs: List[Document],
    category: str,
    extra_meta: dict | None = None,
) -> List[Document]:
    """
    Document 목록에 metadata.category 태그를 추가합니다.

    [태그 종류]
    regulation  : 규정집 PDF (data_rag_working/)
    db_manual   : DB 명세서 PDF (docs/db_manuals/)
    db_schema   : Oracle 스키마 자동 추출 (schema_extractor)
    """
    extra = extra_meta or {}
    for doc in docs:
        doc.metadata["category"] = category
        doc.metadata.update(extra)
    return docs


# ──────────────────────────────────────────────────────────────────────
#  PDF 로드 공통 함수 (기존 방식 / Markdown 방식 분기)
# ──────────────────────────────────────────────────────────────────────


def _load_pdf_dir(
    pdf_dir: Path,
    use_markdown: bool,
    chunk_size: int = 800,
    overlap: int = 150,
    step_label: str = "",
) -> List[Document]:
    """
    PDF 디렉토리를 로드하여 Document 리스트 반환.

    [use_markdown=True]
    · core.pdf_to_markdown.batch_convert_pdfs() 사용
    · pdfplumber 표 구조 보존 → Markdown 변환
    · MarkdownHeaderTextSplitter 헤더 경계 청킹
    · docs/markdown/ 에 .md 파일 저장 (검수용)
    · pdfplumber 미설치 시 자동으로 기존 방식으로 폴백

    [use_markdown=False]
    · 기존 load_and_split() 사용 (하위 호환)
    · PyPDFLoader + 조항 경계 청킹

    Args:
        pdf_dir:      PDF 파일들이 있는 디렉토리
        use_markdown: Markdown 변환 방식 사용 여부
        chunk_size:   Markdown 방식 청크 최대 크기
        overlap:      Markdown 방식 청크 간 중복
        step_label:   로그 표시용 단계 레이블 (예: "[Step 2/5]")

    Returns:
        Document 리스트 (실패 시 빈 리스트)
    """
    if not pdf_dir.exists() or not list(pdf_dir.glob("*.pdf")):
        return []

    pfx = f"{step_label} " if step_label else ""

    if use_markdown:
        # ── Markdown 변환 방식 ─────────────────────────────────────
        try:
            from core.pdf_to_markdown import batch_convert_pdfs

            docs = batch_convert_pdfs(
                pdf_dir=pdf_dir,
                save_md=True,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            if docs:
                logger.info(
                    f"{pfx}Markdown 변환 완료: "
                    f"{len(list(pdf_dir.glob('*.pdf')))}개 파일 "
                    f"→ {len(docs):,}개 청크"
                )
            return docs
        except ImportError:
            # pdfplumber 없으면 기존 방식으로 폴백
            logger.warning(
                f"{pfx}pdfplumber 미설치 → 기존 방식으로 폴백. "
                "`pip install pdfplumber` 로 Markdown 변환 품질을 높일 수 있습니다."
            )
        except Exception as exc:
            logger.warning(
                f"{pfx}Markdown 변환 실패 → 기존 방식으로 폴백: {exc}",
                exc_info=True,
            )

    # ── 기존 방식 (하위 호환 / 폴백) ─────────────────────────────
    result: LoadResult = load_and_split(pdf_dir)
    if result.documents:
        logger.info(
            f"{pfx}기존 방식 로드 완료: "
            f"{len(result.loaded_files)}개 파일 "
            f"→ {len(result.documents):,}개 청크"
        )
    return result.documents


# ──────────────────────────────────────────────────────────────────────
#  DB 명세서 PDF 로드
# ──────────────────────────────────────────────────────────────────────


def _load_db_manual_docs(
    db_docs_dir: Path,
    use_markdown: bool = False,
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[Document]:
    """
    docs/db_manuals/ 폴더의 PDF 를 로드하여 Document 리스트로 반환합니다.

    [v3.2] use_markdown 파라미터 추가 — Markdown 변환 방식 지원
    """
    if not db_docs_dir.exists():
        logger.info(
            f"[Step 3] db_docs_dir 폴더 없음 → 건너뜀: {db_docs_dir}\n"
            f"         DB 명세서 PDF 를 넣으려면 폴더를 만들고 PDF 를 넣으세요."
        )
        return []

    pdf_files = list(db_docs_dir.glob("*.pdf"))
    if not pdf_files:
        logger.info(
            f"[Step 3] db_docs_dir 에 PDF 없음 → 건너뜀: {db_docs_dir}\n"
            f"         PDF 파일을 이 폴더에 넣으세요."
        )
        return []

    mode_label = "Markdown 변환" if use_markdown else "기존 방식"
    logger.info(
        f"[Step 3] DB 명세서 PDF 로드 시작 ({mode_label}): {db_docs_dir}\n"
        f"         파일 목록: {[f.name for f in pdf_files]}"
    )

    try:
        docs = _load_pdf_dir(
            pdf_dir=db_docs_dir,
            use_markdown=use_markdown,
            chunk_size=chunk_size,
            overlap=overlap,
            step_label="[Step 3]",
        )

        if not docs:
            logger.warning(f"[Step 3] DB 명세서 PDF 처리 결과 Document 없음")
            return []

        # category 태깅
        docs = _tag_category(
            docs,
            category="db_manual",
            extra_meta={"doc_source": "db_manual_pdf"},
        )

        logger.info(f"[Step 3] DB 명세서 PDF 로드 완료: {len(docs):,}개 청크")
        return docs

    except Exception as exc:
        logger.warning(
            f"[Step 3] DB 명세서 PDF 로드 실패 (계속 진행): {exc}",
            exc_info=True,
        )
        return []


# ──────────────────────────────────────────────────────────────────────
#  메인
# ──────────────────────────────────────────────────────────────────────


def main(args: argparse.Namespace) -> int:
    total_start = time.perf_counter()

    mode_label = "Markdown 변환" if args.use_markdown else "기존 PyPDF"
    logger.info("=" * 65)
    logger.info("RAG Vector DB 구축 시작 (v3.2)")
    logger.info(f"  PDF 처리 방식:   {mode_label}")
    logger.info(f"  규정집 소스:     {args.source_dir}")
    logger.info(f"  DB 명세서 경로:  {args.db_docs_dir}")
    logger.info(f"  작업 경로:       {settings.local_work_dir}")
    logger.info(f"  벡터DB 저장:     {settings.rag_db_path}")
    if args.use_markdown:
        logger.info(f"  청크 크기:       {args.chunk_size} (overlap={args.overlap})")
    logger.info("=" * 65)

    all_docs: List[Document] = []

    # ─────────────────────────────────────────────────────────────
    #  Step 1: G드라이브 → 로컬 PDF 동기화
    # ─────────────────────────────────────────────────────────────
    t1 = time.perf_counter()
    if args.db_docs_only:
        logger.info("[Step 1/5] --db-docs-only 모드: 동기화 건너뜀")
    elif args.no_sync:
        logger.info("[Step 1/5] G드라이브 동기화 건너뜀 (--no-sync)")
    else:
        logger.info("[Step 1/5] G드라이브 PDF 동기화 시작")
        try:
            result = sync_pdf_files(args.source_dir, settings.local_work_dir)
            logger.info(
                f"[Step 1/5] 동기화 완료 ({time.perf_counter() - t1:.1f}s): "
                f"신규 {len(result.copied)}개, 업데이트 {len(result.updated)}개"
            )
        except Exception as exc:
            logger.warning(f"[Step 1/5] 동기화 실패 (계속 진행): {exc}")

    # ─────────────────────────────────────────────────────────────
    #  Step 2: 규정집 PDF 로드 (data_rag_working/)
    # ─────────────────────────────────────────────────────────────
    t2 = time.perf_counter()
    if args.db_docs_only:
        logger.info("[Step 2/5] --db-docs-only 모드: 규정집 로드 건너뜀")
    else:
        logger.info(f"[Step 2/5] 규정집 PDF 로드 시작 ({mode_label})")

        regulation_docs = _load_pdf_dir(
            pdf_dir=settings.local_work_dir,
            use_markdown=args.use_markdown,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            step_label="[Step 2/5]",
        )

        if regulation_docs:
            regulation_docs = _tag_category(regulation_docs, category="regulation")
            all_docs.extend(regulation_docs)
            logger.info(
                f"[Step 2/5] 규정집 로드 완료 ({time.perf_counter() - t2:.1f}s): "
                f"{len(regulation_docs):,}개 청크"
            )
        else:
            logger.warning(
                f"[Step 2/5] 규정집 PDF 없음: {settings.local_work_dir}\n"
                f"           DB 명세서 PDF 만으로 계속 진행합니다."
            )

    # ─────────────────────────────────────────────────────────────
    #  Step 3: DB 명세서 PDF 로드 (docs/db_manuals/)
    # ─────────────────────────────────────────────────────────────
    t3 = time.perf_counter()
    if args.no_db_docs:
        logger.info("[Step 3/5] DB 명세서 PDF 로드 건너뜀 (--no-db-docs)")
    else:
        db_docs = _load_db_manual_docs(
            db_docs_dir=args.db_docs_dir,
            use_markdown=args.use_markdown,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        if db_docs:
            all_docs.extend(db_docs)
            logger.info(
                f"[Step 3/5] DB 명세서 추가 완료 ({time.perf_counter() - t3:.1f}s): "
                f"{len(db_docs):,}개 청크 → 누적 {len(all_docs):,}개"
            )

    # ─────────────────────────────────────────────────────────────
    #  Step 4: Oracle DB 스키마 추출 (선택)
    # ─────────────────────────────────────────────────────────────
    t4 = time.perf_counter()
    _skip_reason = (
        "--no-db-schema"
        if args.no_db_schema
        else "--db-docs-only"
        if args.db_docs_only
        else (
            "settings.db_enabled=False"
            if not getattr(settings, "db_enabled", False)
            else ""
        )
    )

    if _skip_reason:
        logger.info(f"[Step 4/5] DB 스키마 추출 건너뜀 ({_skip_reason})")
    else:
        logger.info("[Step 4/5] Oracle DB 스키마 추출 시작")
        try:
            from db.schema_extractor import extract_schema_documents

            db_schema_docs = extract_schema_documents()
            if db_schema_docs:
                db_schema_docs = _tag_category(db_schema_docs, category="db_schema")
                all_docs.extend(db_schema_docs)
                logger.info(
                    f"[Step 4/5] DB 스키마 추출 완료 ({time.perf_counter() - t4:.1f}s): "
                    f"{len(db_schema_docs)}개 Document → 누적 {len(all_docs):,}개"
                )
            else:
                logger.info("[Step 4/5] DB 스키마 Document 없음 (건너뜀)")
        except Exception as exc:
            logger.warning(f"[Step 4/5] DB 스키마 추출 실패 (계속 진행): {exc}")

    # ─────────────────────────────────────────────────────────────
    #  최종 검사
    # ─────────────────────────────────────────────────────────────
    if not all_docs:
        logger.error(
            "유효한 Document 가 없습니다. 다음을 확인하세요:\n"
            f"  · 규정집 PDF 경로: {settings.local_work_dir}\n"
            f"  · DB 명세서 경로:  {args.db_docs_dir}\n"
            "  · --db-docs-only 모드에서는 docs/db_manuals/ 에 PDF 가 있어야 합니다."
        )
        return 2

    # 소스별 청크 수 요약 로그
    from collections import Counter

    cat_counts = Counter(d.metadata.get("category", "unknown") for d in all_docs)
    logger.info(
        f"최종 Document 구성:\n"
        + "\n".join(f"  {cat:15s}: {cnt:,}개" for cat, cnt in cat_counts.items())
        + f"\n  {'합계':15s}: {len(all_docs):,}개"
    )

    # ─────────────────────────────────────────────────────────────
    #  Step 5: 벡터 DB 구축 (임베딩 + FAISS 인덱싱)
    # ─────────────────────────────────────────────────────────────
    t5 = time.perf_counter()
    logger.info(f"[Step 5/5] 벡터 DB 구축 시작 (총 {len(all_docs):,}개 청크)")

    manager = VectorStoreManager(
        db_path=settings.rag_db_path,
        model_name=settings.embedding_model,
        cache_dir=str(settings.local_cache_path),
        batch_size=settings.batch_size,
    )
    result_db = manager.build(all_docs)

    if result_db is None:
        logger.error("[Step 5/5] 벡터 DB 구축 실패")
        return 1

    # ─────────────────────────────────────────────────────────────
    #  완료 통계
    # ─────────────────────────────────────────────────────────────
    total_elapsed = time.perf_counter() - total_start
    logger.info("=" * 65)
    logger.info("RAG Vector DB 구축 완료 ✅")
    logger.info(f"  PDF 처리 방식: {mode_label}")
    logger.info(f"  총 청크 수:    {len(all_docs):,}개")
    logger.info(f"  벡터 수:       {result_db.index.ntotal:,}개")
    for cat, cnt in cat_counts.items():
        logger.info(f"  [{cat}]:  {cnt:,}개")
    logger.info(f"  저장 경로:     {settings.rag_db_path}")
    logger.info(f"  총 소요 시간:  {total_elapsed:.1f}초")
    if args.use_markdown:
        md_dir = Path(settings.local_work_dir).parent / "docs" / "markdown"
        logger.info(f"  Markdown 저장: {md_dir}")
    logger.info("=" * 65)
    return 0


# ──────────────────────────────────────────────────────────────────────
#  부서별 재구축 모드 (v3.3)
# ──────────────────────────────────────────────────────────────────────


def _run_dept_mode(args: argparse.Namespace) -> int:
    """
    --dept 옵션이 있을 때 실행되는 부서별 재구축 진입점.

    [모드]
    --dept all      : 모든 부서 동기화 → 재구축 → 마스터 병합
    --dept {이름}   : 한 부서만 동기화 → 재구축 → 마스터 병합
    --dept {이름} --no-merge : 마스터 병합 생략 (부서 FAISS만 갱신)

    [실행 예시]
    python build_db.py --dept 간호부
    python build_db.py --dept 간호부 --use-markdown
    python build_db.py --dept all
    python build_db.py --dept 간호부 --no-merge   # 마스터 병합 없이 부서만
    """
    from core.dept_vector_store import DeptVectorStoreManager

    mgr = DeptVectorStoreManager()
    dept_arg     = args.dept
    sync_first   = not args.no_sync
    use_markdown = args.use_markdown
    no_merge     = getattr(args, "no_merge", False)

    logger.info("=" * 65)
    logger.info(f"[부서별 재구축 모드] --dept {dept_arg}")
    logger.info(f"  동기화:       {'건너뜀' if not sync_first else '실행'}")
    logger.info(f"  Markdown변환: {'사용' if use_markdown else '미사용'}")
    logger.info(f"  마스터병합:   {'건너뜀' if no_merge else '실행'}")
    logger.info("=" * 65)

    if dept_arg == "all":
        # ── 전체 부서 재구축 ─────────────────────────────────────────────
        logger.info("[부서전체] 동기화 시작...")
        results, merge = mgr.rebuild_all_depts_and_merge(
            sync_first=sync_first,
            use_markdown=use_markdown,
        )
        ok = sum(1 for r in results if r.success)
        ng = len(results) - ok
        logger.info(f"[부서전체] 재구축 완료: {ok}개 성공 / {ng}개 실패")
        for r in results:
            status = "OK" if r.success else f"FAIL({r.error})"
            logger.info(f"  {r.dept_name:15s}: {status} — {r.chunk_count:,}청크 {r.elapsed_sec}s")
        if not no_merge:
            if merge.success:
                logger.info(
                    f"[마스터병합] 완료: {merge.dept_count}개 부서, "
                    f"{merge.total_chunks:,}청크 ({merge.elapsed_sec}s)"
                )
            else:
                logger.error(f"[마스터병합] 실패: {merge.error}")
        return 0 if ok > 0 else 1

    else:
        # ── 한 부서 재구축 ─────────────────────────────────────────────
        available = mgr.list_source_depts() + mgr.list_local_depts()
        if dept_arg not in available:
            logger.warning(
                f"[경고] '{dept_arg}' 부서를 찾을 수 없습니다.\n"
                f"사용 가능한 부서: {sorted(set(available))}"
            )
            # 경고만 출력하고 계속 시도 (로컬에 PDF 있을 수 있음)

        if sync_first:
            logger.info(f"[{dept_arg}] G드라이브 동기화 시작...")
            sr = mgr.sync_dept(dept_arg)
            logger.info(
                f"[{dept_arg}] 동기화: 신규 {len(sr.copied)} / "
                f"업데이트 {len(sr.updated)} / 실패 {len(sr.failed)}"
            )

        logger.info(f"[{dept_arg}] 재구축 시작...")
        rb = mgr.rebuild_dept(dept_arg, use_markdown=use_markdown)

        if not rb.success:
            logger.error(f"[{dept_arg}] 재구축 실패: {rb.error}")
            return 1

        logger.info(
            f"[{dept_arg}] 재구축 완료: {rb.chunk_count:,}청크 ({rb.elapsed_sec}s)"
        )

        if no_merge:
            logger.info(f"[{dept_arg}] --no-merge: 마스터 병합 생략")
        else:
            logger.info("[마스터병합] 시작...")
            mg = mgr.merge_all_to_master()
            if mg.success:
                logger.info(
                    f"[마스터병합] 완료: {mg.dept_count}개 부서, "
                    f"{mg.total_chunks:,}청크 ({mg.elapsed_sec}s)"
                )
            else:
                logger.error(f"[마스터병합] 실패: {mg.error}")
                return 1

        return 0


if __name__ == "__main__":
    try:
        _args = parse_args()
        # --dept 옵션이 있으면 부서별 모드, 없으면 기존 전체 재구축 모드
        if _args.dept is not None:
            sys.exit(_run_dept_mode(_args))
        else:
            sys.exit(main(_args))
    except KeyboardInterrupt:
        logger.warning("사용자 중단 (Ctrl+C)")
        sys.exit(1)
    except Exception as exc:
        logger.critical(f"예기치 않은 오류: {exc}", exc_info=True)
        sys.exit(1)
