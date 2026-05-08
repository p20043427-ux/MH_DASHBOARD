"""
core/pdf_to_markdown.py  ─  PDF → Markdown 변환 파이프라인 v2.0  (2026-05-08)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[v2.0 개선 내용]

1. 표 추출 이중 전략 (병원 문서 특화)
   - lines  전략: 테두리 있는 표 (검사 기준표, 약품표, 수가 코드표)
   - text   전략: 테두리 없는 표 (코드 목록, 정렬 기반 코드표)
   → 두 전략 모두 시도 후 더 많은 셀을 추출한 결과 선택

2. 병합 셀(Merged Cell) Forward-Fill 처리
   - pdfplumber 는 병합 셀을 None 으로 반환
   - 이전 행의 값을 아래 행에 채워 RAG 검색 정확도 향상
   - 예: 약품 분류 컬럼이 여러 행에 걸쳐 표시되는 경우

3. pypdfium2 텍스트 추출 (선택)
   - Chromium PDFium 기반 → 한글 레이아웃 보존 우수
   - pdfplumber 추출 실패 시 폴백으로 사용

4. 표 유형 자동 분류 메타데이터
   - 헤더 키워드 기반: 코드표 / 약품표 / 검사기준표 / 일반표
   - 청킹 시 메타데이터로 저장 → 필터 검색 활용 가능

5. RAG 최적화 청킹
   - 표 청크에는 헤더 행 반복 주입 (검색 정확도 향상)
   - 조항 경계 인식 (제N장/절/조)

[패키지 우선순위]
  텍스트 추출: pdfplumber (primary)  → pypdfium2 (fallback)  → pypdf (last resort)
  표   추출 : pdfplumber lines/text 이중 전략

[처리 흐름]
  PDF 파일
    → 1. pdfplumber 페이지 순회
       ├─ 텍스트 추출 (pdfplumber)
       └─ 표 추출 (lines + text 전략 이중 시도)
           └─ 병합 셀 forward-fill
           └─ 표 유형 분류
    → 2. 텍스트 → Markdown 구조화 (제N장/절/조 헤더)
    → 3. 표 → | Markdown 표 | 형식
    → 4. .md 파일 저장 (선택)
    → 5. MarkdownHeaderTextSplitter 청킹
    → Document 리스트 반환
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_core.documents import Document

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__, log_dir=settings.log_dir)

# ── 구조 인식 패턴 ─────────────────────────────────────────────────────────
_RE_ARTICLE = re.compile(r"^(제\s*\d+\s*조)", re.MULTILINE)
_RE_CHAPTER = re.compile(r"^(제\s*\d+\s*장)", re.MULTILINE)
_RE_SECTION = re.compile(r"^(제\s*\d+\s*절)", re.MULTILINE)
_RE_ITEM_NUM = re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩])", re.MULTILINE)
_RE_FOOTER   = re.compile(r"^\s*[-–]\s*\d+\s*[-–]\s*$", re.MULTILINE)
_RE_PAGE_NUM = re.compile(r"^\s*\d+\s*$", re.MULTILINE)

# ── 표 유형 분류 키워드 ────────────────────────────────────────────────────
_TABLE_TYPE_KEYWORDS = {
    "코드표":     ["코드", "code", "분류코드", "진료코드", "처치코드", "EDI", "NEDIS"],
    "약품표":     ["약품명", "약품코드", "투여량", "용량", "단위", "성분", "효능"],
    "검사기준표": ["기준값", "정상범위", "참고치", "판정기준", "단위", "검사항목"],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  표 유형 분류
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _classify_table_type(header_row: List[str]) -> str:
    """
    헤더 행 키워드를 기반으로 표 유형을 분류합니다.

    Returns:
        "코드표" | "약품표" | "검사기준표" | "일반표"
    """
    header_text = " ".join(str(h) for h in header_row).lower()
    for table_type, keywords in _TABLE_TYPE_KEYWORDS.items():
        if any(kw.lower() in header_text for kw in keywords):
            return table_type
    return "일반표"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  병합 셀 처리 (Forward-Fill)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _forward_fill(table: List[List[Optional[str]]]) -> List[List[str]]:
    """
    pdfplumber 가 None 으로 반환하는 병합 셀을 이전 행 값으로 채웁니다.

    [예시]
      입력:                    출력:
      | 분류 | 약품명 |        | 분류 | 약품명 |
      | 항생제 | 아목시실린 |  | 항생제 | 아목시실린 |
      | None  | 세파클러 |    | 항생제 | 세파클러 |   ← 병합 셀 복원
      | 해열제 | 타이레놀 |   | 해열제 | 타이레놀 |
    """
    if not table:
        return []

    col_count = max(len(row) for row in table)
    prev_row = [""] * col_count
    result: List[List[str]] = []

    for row in table:
        # 컬럼 수 맞추기 (불규칙 행 보정)
        padded = list(row) + [""] * (col_count - len(row))
        filled = []
        for j, cell in enumerate(padded):
            val = str(cell or "").strip().replace("\n", " ")
            # 빈 셀이고 j < col_count 이면 이전 행 값 사용
            filled.append(val if val else prev_row[j])
        prev_row = filled
        result.append(filled)

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2D 리스트 → Markdown 표 문자열
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _table_to_markdown(
    table: List[List[str]],
    table_type: str = "일반표",
    include_type_comment: bool = True,
) -> str:
    """
    2D 리스트 (forward-fill 완료) → Markdown 표 문자열.

    표 유형 주석 예시:
        <!-- table_type: 약품표 -->
        | 약품명 | 투여량 | 단위 |
        | --- | --- | --- |
        | 아목시실린 | 500mg | 정 |
    """
    if not table or not table[0]:
        return ""

    rows: List[str] = []

    # 표 유형 주석 (RAG 검색 시 표 컨텍스트 강화)
    if include_type_comment and table_type != "일반표":
        rows.append(f"<!-- table_type: {table_type} -->")

    headers = table[0]
    rows.append("| " + " | ".join(headers) + " |")
    rows.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for row in table[1:]:
        # 모든 셀이 빈 행은 제외
        if all(c == "" for c in row):
            continue
        rows.append("| " + " | ".join(row) + " |")

    # 헤더 + 구분선만 있는 빈 표 제외
    if len(rows) <= (3 if include_type_comment and table_type != "일반표" else 2):
        return ""

    return "\n".join(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  pdfplumber 표 추출 — 이중 전략
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# lines 전략: 테두리 있는 표 (검사기준표, 약품표, 수가코드표)
_SETTINGS_LINES = {
    "vertical_strategy":   "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance":       3,
    "intersection_tolerance": 5,
    "edge_min_length":      3,
    "text_tolerance":       3,
}

# text 전략: 테두리 없는 표 (코드표, 텍스트 정렬 표)
_SETTINGS_TEXT = {
    "vertical_strategy":   "text",
    "horizontal_strategy": "text",
    "min_words_vertical":   3,
    "min_words_horizontal": 1,
    "text_tolerance":       3,
    "text_x_tolerance":     3,
    "text_y_tolerance":     3,
}

# lines_strict 전략: 명시적 선 + 넓은 허용 오차 (복잡한 혼합 레이아웃)
_SETTINGS_LINES_STRICT = {
    "vertical_strategy":   "lines_strict",
    "horizontal_strategy": "lines_strict",
    "snap_tolerance":       5,
    "intersection_tolerance": 7,
}


def _score_raw_tables(tables: List[List[List[Optional[str]]]]) -> int:
    """추출된 표의 총 비어있지 않은 셀 수로 품질 점수를 계산합니다."""
    total = 0
    for table in tables:
        for row in table:
            total += sum(1 for c in row if c and str(c).strip())
    return total


def _extract_tables_from_page(page, page_num: int) -> List[str]:
    """
    pdfplumber 페이지에서 이중 전략으로 표를 추출합니다.

    [전략 선택 로직]
    1. lines 전략 시도 → 점수 계산
    2. text  전략 시도 → 점수 계산
    3. 더 높은 점수의 전략 결과 사용
    4. lines_strict 전략: lines + text 결과가 모두 0이면 추가 시도

    Returns:
        Markdown 표 문자열 리스트
    """
    results_by_strategy: dict = {}

    for name, settings_dict in [
        ("lines",        _SETTINGS_LINES),
        ("text",         _SETTINGS_TEXT),
    ]:
        try:
            raw = page.extract_tables(table_settings=settings_dict)
            if raw:
                results_by_strategy[name] = (raw, _score_raw_tables(raw))
        except Exception as exc:
            logger.debug(f"  표 추출 실패 ({name}, 페이지 {page_num}): {exc}")

    # 아무 결과도 없으면 lines_strict 시도
    if not results_by_strategy:
        try:
            raw = page.extract_tables(table_settings=_SETTINGS_LINES_STRICT)
            if raw:
                results_by_strategy["lines_strict"] = (raw, _score_raw_tables(raw))
        except Exception:
            pass

    if not results_by_strategy:
        return []

    # 가장 높은 점수 전략 선택
    best_name = max(results_by_strategy, key=lambda k: results_by_strategy[k][1])
    best_tables, best_score = results_by_strategy[best_name]
    logger.debug(
        f"  페이지 {page_num} 표 전략: {best_name} "
        f"(점수 {best_score}, {len(best_tables)}개 표)"
    )

    # Markdown 변환
    md_tables: List[str] = []
    for raw_table in best_tables:
        if not raw_table or not raw_table[0]:
            continue
        filled = _forward_fill(raw_table)
        if not filled:
            continue
        table_type = _classify_table_type(filled[0])
        md = _table_to_markdown(filled, table_type=table_type)
        if md.strip():
            md_tables.append(md)

    return md_tables


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  텍스트 추출 (pdfplumber primary, pypdfium2 fallback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_text_pypdfium2(pdf_path: Path) -> List[str]:
    """
    pypdfium2 (Chromium PDFium) 로 페이지별 텍스트를 추출합니다.

    pypdf 에 비해 한글 레이아웃 보존이 우수하며,
    pdfplumber 추출 품질이 낮을 때 대안으로 사용합니다.

    Returns:
        페이지별 텍스트 리스트
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pages_text: List[str] = []
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        for page in pdf:
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            pages_text.append(text or "")
            textpage.close()
            page.close()
        pdf.close()
    except Exception as exc:
        logger.debug(f"pypdfium2 추출 실패 [{pdf_path.name}]: {exc}")
    return pages_text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  텍스트 → Markdown 구조화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _text_to_markdown_structure(text: str) -> str:
    """
    추출된 텍스트에 Markdown 헤더 구조를 적용합니다.

    [변환 규칙]
    · "제N장 제목"   → ## 제N장 제목
    · "제N절 제목"   → ### 제N절 제목
    · "제N조(제목)"  → #### 제N조(제목)
    · "①②③..."     → - ① 내용 (목록)
    · 헤더/푸터 제거
    """
    text = _RE_FOOTER.sub("", text)
    text = _RE_PAGE_NUM.sub("", text)

    lines = text.splitlines()
    result = []

    for line in lines:
        s = line.strip()
        if not s:
            result.append("")
            continue
        if _RE_CHAPTER.match(s):
            result.append(f"## {s}")
        elif _RE_SECTION.match(s):
            result.append(f"### {s}")
        elif _RE_ARTICLE.match(s):
            result.append(f"#### {s}")
        elif _RE_ITEM_NUM.match(s):
            result.append(f"- {s}")
        else:
            result.append(s)

    return "\n".join(result)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PDF → Markdown 변환 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def pdf_to_markdown(
    pdf_path: Path,
    save_md: bool = True,
    md_output_dir: Optional[Path] = None,
) -> str:
    """
    PDF 파일을 Markdown 문자열로 변환합니다.

    [처리 순서]
    1. pdfplumber 로 페이지별 텍스트 추출
       · 텍스트가 빈 페이지는 pypdfium2 로 재시도
    2. pdfplumber 이중 전략으로 표 추출 (lines + text)
       · 병합 셀 forward-fill → Markdown 표 변환
    3. 텍스트 → ## 헤더 구조 적용
    4. 페이지 순서로 텍스트 + 표 병합
    5. save_md=True 이면 docs/markdown/ 에 저장

    Args:
        pdf_path:      PDF 파일 경로
        save_md:       Markdown 파일 저장 여부
        md_output_dir: Markdown 저장 디렉토리 (기본: docs/markdown/)

    Returns:
        Markdown 형식 문자열
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber 미설치 → PyPDFLoader 폴백")
        return _fallback_pypdf_to_markdown(pdf_path)

    logger.info(f"PDF → Markdown 변환 시작: {pdf_path.name}")

    # pypdfium2 텍스트 미리 추출 (pdfplumber 실패 페이지 대비)
    pdfium_pages = _extract_text_pypdfium2(pdf_path)

    md_pages: List[str] = []
    total_tables = 0

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                parts: List[str] = [f"\n<!-- page {page_num} -->"]

                # ── 텍스트 추출 ─────────────────────────────────────────
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""

                # pdfplumber 텍스트가 너무 짧으면 pypdfium2 로 보완
                if len(text.strip()) < 30 and pdfium_pages:
                    idx = page_num - 1
                    if idx < len(pdfium_pages) and pdfium_pages[idx].strip():
                        text = pdfium_pages[idx]
                        logger.debug(f"  페이지 {page_num}: pypdfium2 텍스트로 보완")

                if text.strip():
                    structured = _text_to_markdown_structure(text)
                    if structured.strip():
                        parts.append(structured)

                # ── 표 추출 (이중 전략 + 병합 셀 처리) ─────────────────
                tables_md = _extract_tables_from_page(page, page_num)
                total_tables += len(tables_md)
                for tbl_md in tables_md:
                    if tbl_md.strip():
                        parts.append(f"\n{tbl_md}\n")

                md_pages.append("\n".join(parts))

    except Exception as exc:
        logger.error(f"PDF 변환 실패 ({pdf_path.name}): {exc}", exc_info=True)
        return _fallback_pypdf_to_markdown(pdf_path)

    full_md = f"# {pdf_path.stem}\n\n" + "\n\n".join(md_pages)

    if save_md:
        _save_markdown(full_md, pdf_path, md_output_dir)

    logger.info(
        f"PDF → Markdown 변환 완료: {pdf_path.name} "
        f"({len(md_pages)}페이지, {total_tables}개 표, {len(full_md):,}자)"
    )
    return full_md


def _fallback_pypdf_to_markdown(pdf_path: Path) -> str:
    """pdfplumber 없을 때 PyPDFLoader 로 폴백."""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            docs = PyPDFLoader(str(pdf_path)).load()
        parts = [f"# {pdf_path.stem}\n"]
        for doc in docs:
            text = _text_to_markdown_structure(doc.page_content)
            if text.strip():
                page = doc.metadata.get("page", 0)
                parts.append(f"\n<!-- page {page + 1} -->\n{text}")
        return "\n".join(parts)
    except Exception as exc:
        logger.error(f"PyPDFLoader 폴백도 실패: {exc}")
        return f"# {pdf_path.stem}\n\n(변환 실패: {exc})"


def _save_markdown(md_text: str, pdf_path: Path, output_dir: Optional[Path]) -> None:
    """변환된 Markdown 을 파일로 저장합니다."""
    if output_dir is None:
        output_dir = Path(settings.markdown_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{pdf_path.stem}.md"
    md_path.write_text(md_text, encoding="utf-8")
    logger.info(f"Markdown 저장: {md_path}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Markdown → Document 청킹
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def markdown_to_documents(
    md_text: str,
    source: str = "",
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[Document]:
    """
    Markdown 텍스트를 헤더 경계로 청킹하여 Document 리스트로 반환합니다.

    [청킹 전략 — 2단계]
    1단계: MarkdownHeaderTextSplitter
       · ## 제N장 / ### 제N절 / #### 제N조 경계로 분리
       · 조항이 두 청크에 걸쳐 분리되는 문제 해결

    2단계: RecursiveCharacterTextSplitter
       · 1단계 결과가 chunk_size 초과 시 추가 분할
       · 표(|) 포함 청크는 chunk_size × 2 까지 허용 (표 구조 보존)
       · overlap 으로 문맥 연속성 보장

    [메타데이터]
    · source:       파일명
    · chapter:      제N장
    · section:      제N절
    · article:      제N조
    · table_type:   표 유형 (코드표 / 약품표 / 검사기준표 / 일반표 / "")
    · content_hash: 중복 감지용 MD5
    """
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )

    # ── 1단계: 헤더 경계 분리 ─────────────────────────────────────────
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#",    "title"),
            ("##",   "chapter"),
            ("###",  "section"),
            ("####", "article"),
        ],
        strip_headers=False,
    )
    header_docs = header_splitter.split_text(md_text)
    if not header_docs:
        return []

    # ── 2단계: 크기 초과 청크 재분할 ──────────────────────────────────
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
    )

    final_docs: List[Document] = []
    seen_hashes: set = set()

    for doc in header_docs:
        content_raw = doc.page_content

        # 표 포함 청크는 크기 제한을 2배로 완화 (표 구조 분리 방지)
        has_table = "|" in content_raw and "---" in content_raw
        effective_limit = chunk_size * 2 if has_table else chunk_size

        if len(content_raw) <= effective_limit:
            chunks = [doc]
        else:
            sub_chunks = char_splitter.split_documents([doc])
            chunks = sub_chunks

        for chunk in chunks:
            # 페이지 주석 제거
            content = re.sub(r"<!--\s*page\s*\d+\s*-->", "", chunk.page_content).strip()
            if len(content) < 30:
                continue

            # 중복 제거
            content_hash = hashlib.md5(content.encode()).hexdigest()
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)

            # 표 유형 추출 (<!-- table_type: XXX --> 주석에서)
            ttype_match = re.search(r"<!--\s*table_type:\s*(\S+)\s*-->", content)
            table_type = ttype_match.group(1) if ttype_match else ""

            meta = {
                "source":       source,
                "chapter":      chunk.metadata.get("chapter", ""),
                "section":      chunk.metadata.get("section", ""),
                "article":      chunk.metadata.get("article", ""),
                "table_type":   table_type,
                "content_hash": content_hash,
            }
            final_docs.append(Document(page_content=content, metadata=meta))

    logger.info(
        f"Markdown 청킹 완료: {len(header_docs)}개 섹션 "
        f"→ {len(final_docs)}개 청크 [{source}]"
    )
    return final_docs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 함수: PDF → Document 리스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_pdf_as_markdown_docs(
    pdf_path: Path,
    save_md: bool = True,
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[Document]:
    """
    PDF → Markdown 변환 → 청킹 → Document 리스트 반환.

    [build_db.py 통합]
        from core.pdf_to_markdown import load_pdf_as_markdown_docs
        docs = load_pdf_as_markdown_docs(pdf_path, save_md=True)
    """
    md_text = pdf_to_markdown(pdf_path, save_md=save_md)
    if not md_text.strip():
        logger.warning(f"빈 Markdown 결과: {pdf_path.name}")
        return []
    return markdown_to_documents(
        md_text=md_text,
        source=pdf_path.name,
        chunk_size=chunk_size,
        overlap=overlap,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  배치 처리: 디렉토리 내 모든 PDF
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def batch_convert_pdfs(
    pdf_dir: Path,
    save_md: bool = True,
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[Document]:
    """
    디렉토리 내 모든 PDF 를 Markdown 으로 변환하여 Document 목록 반환.

    [build_db.py 에서 사용]
        from core.pdf_to_markdown import batch_convert_pdfs
        all_docs = batch_convert_pdfs(pdf_dir=settings.local_work_dir, save_md=True)
    """
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"PDF 파일 없음: {pdf_dir}")
        return []

    logger.info(f"배치 변환 시작: {len(pdf_files)}개 PDF → Markdown")
    all_docs: List[Document] = []

    for pdf_path in pdf_files:
        try:
            docs = load_pdf_as_markdown_docs(
                pdf_path,
                save_md=save_md,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            all_docs.extend(docs)
            logger.info(f"  OK  {pdf_path.name}: {len(docs)}개 청크")
        except Exception as exc:
            logger.error(f"  ERR {pdf_path.name}: {exc}", exc_info=True)

    logger.info(f"배치 변환 완료: {len(pdf_files)}개 파일 → 총 {len(all_docs)}개 청크")
    return all_docs
