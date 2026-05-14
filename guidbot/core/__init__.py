"""
core 패키지 ─ RAG 파이프라인 핵심 모듈

[패키지 구성]
  document_loader  : PDF 로드 + 텍스트 전처리 + 청킹
  embeddings       : HuggingFace 임베딩 모델 관리
  vector_store     : FAISS 벡터 DB 구축·로드·백업
  retriever        : FAISS 검색 + Cross-Encoder 리랭킹
  hybrid_retriever : BM25 + FAISS 하이브리드 검색
  query_rewriter   : LLM 기반 쿼리 확장·정제
  context_builder  : 검색 결과 → LLM 컨텍스트 변환
  rag_pipeline     : 위 모듈들을 통합한 단일 파이프라인
  llm              : Gemini LLM 클라이언트 (API 키 풀)

[빠른 사용]
  # 파이프라인 실행
  from core.rag_pipeline import RAGPipeline, get_pipeline

  # 벡터 DB 관리
  from core.vector_store import VectorStoreManager

  # 검색 결과 타입
  from core.retriever import RankedDocument
"""

from core.retriever import RankedDocument
from core.rag_pipeline import RAGPipeline, PipelineResult, get_pipeline
from core.vector_store import VectorStoreManager

# [2026-05-14] LLM 임포트 방어 처리 ─────────────────────────────────────
# google-genai 패키지 미설치 시 LLM 로드 실패가 나머지 모듈 전체를 죽이는
# 연쇄 실패(ModuleNotFoundError cascade)를 방지한다.
# get_llm_client 가 실제로 호출될 때 ImportError 가 발생하도록 지연 처리.
try:
    from core.llm import get_llm_client
except ImportError as _llm_import_err:          # google.genai 미설치 등
    import warnings as _w
    _w.warn(
        f"[core] LLM 모듈 로드 실패 — LLM 기능을 사용할 수 없습니다. "
        f"원인: {_llm_import_err}  |  해결: pip install 'google-genai>=1.10.0'",
        ImportWarning,
        stacklevel=2,
    )
    def get_llm_client(*_a, **_kw):             # noqa: E302 — 더미 함수
        raise RuntimeError(
            "google-genai 패키지가 설치되지 않아 LLM 기능을 사용할 수 없습니다. "
            "pip install 'google-genai>=1.10.0' 를 실행하세요."
        ) from _llm_import_err
# ─────────────────────────────────────────────────────────────────────────

__all__ = [
    "RankedDocument",
    "RAGPipeline",
    "PipelineResult",
    "get_pipeline",
    "VectorStoreManager",
    "get_llm_client",
]
