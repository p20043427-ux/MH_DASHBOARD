"""
ui/admin_tab_manual.py — 관리자 매뉴얼 뷰어 탭 (v1.0, 2026-05-07)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
docs/ 폴더 문서 인라인 뷰어 + 다운로드

[구성]
  · 주요 매뉴얼: docs/ 최상위 .md / .docx / .sql 쌍 그룹
    - Markdown → 인라인 렌더링
    - DOCX     → 다운로드 전용 (라이브러리 미의존)
    - SQL      → 코드 하이라이팅
  · 문서 라이브러리: docs/ 하위 폴더 파일 목록 + 다운로드 + 뷰어
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_DOCS = _ROOT / "docs"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui.design import C, gap, section_header


def _h(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


# ── 파일 메타 ─────────────────────────────────────────────────────────────

_MANUAL_META: Dict[str, Tuple[str, str, str]] = {
    # stem: (icon, 표시명, 설명)
    "사용자매뉴얼": ("👤", "사용자 매뉴얼",  "시스템 기본 사용법 — 챗봇·대시보드·주요 기능 활용 가이드"),
    "설치_매뉴얼":  ("🔧", "설치 매뉴얼",    "서버 환경 구성·Python 패키지·Oracle 연결 초기 설치 절차"),
    "운영_매뉴얼":  ("🏭", "운영 매뉴얼",    "일상 운영·장애 대응·벡터DB 재구축·백업 관리 절차"),
    "oracle_views": ("🗄️", "Oracle Views 명세", "Oracle 뷰 정의·컬럼·조인 구조 설명"),
    "create_views": ("📋", "Create Views SQL",  "Oracle 뷰 생성 스크립트 (DDL)"),
}

_FOLDER_META: Dict[str, Tuple[str, str]] = {
    "db_manuals":    ("🗄️", "DB 매뉴얼"),
    "db_specs":      ("📊", "DB 명세서"),
    "markdown":      ("📝", "마크다운 문서"),
    "other":         ("📁", "기타 문서"),
    "preview":       ("👁️", "미리보기"),
    "query_library": ("🔍", "SQL 쿼리 예제"),
    "regulations":   ("📋", "업무 규정"),
    "system_guide":  ("🏥", "시스템 안내서"),
}

_VIEWABLE = {".md", ".txt", ".sql"}
_DL_MIME = {
    ".md":   "text/markdown",
    ".txt":  "text/plain",
    ".sql":  "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf":  "application/pdf",
}


# ── 스캔 헬퍼 ─────────────────────────────────────────────────────────────

def _get_manuals() -> List[Dict]:
    """docs/ 최상위 md·docx·sql 파일을 줄기(stem) 기준으로 그룹화."""
    if not _DOCS.exists():
        return []
    by_stem: Dict[str, Dict] = {}
    for ext in ("*.md", "*.docx", "*.sql"):
        for p in sorted(_DOCS.glob(ext)):
            s = p.stem
            if s not in by_stem:
                by_stem[s] = {"title": s, "md": None, "docx": None, "sql": None}
            by_stem[s][p.suffix.lstrip(".")] = p
    # 우선순위 순서로 정렬
    order = list(_MANUAL_META.keys())
    rest  = [k for k in by_stem if k not in order]
    return [by_stem[k] for k in order + rest if k in by_stem]


def _scan_subfolders() -> List[Tuple[str, List[Dict]]]:
    """docs/ 하위 폴더별 텍스트 파일 목록. 비어 있는 폴더는 제외."""
    result: List[Tuple[str, List[Dict]]] = []
    if not _DOCS.exists():
        return result
    for d in sorted(_DOCS.iterdir()):
        if not d.is_dir():
            continue
        files: List[Dict] = []
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            try:
                stat = p.stat()
                files.append({
                    "name":     p.name,
                    "path":     p,
                    "rel":      str(p.relative_to(d)),
                    "size_kb":  round(stat.st_size / 1024, 1),
                    "ext":      p.suffix.lower(),
                })
            except Exception:
                continue
        if files:
            result.append((d.name, files))
    return result


# ── 인라인 뷰어 렌더 ──────────────────────────────────────────────────────

def _render_file(p: Path, max_kb: int = 512) -> None:
    """파일 내용을 확장자에 따라 인라인 렌더링. max_kb 초과 시 경고."""
    try:
        size_kb = p.stat().st_size / 1024
    except Exception:
        st.error("파일 크기 확인 불가")
        return

    if size_kb > max_kb:
        st.warning(f"파일이 큽니다 ({size_kb:.0f} KB). 렌더링이 느릴 수 있습니다.")
        if not st.checkbox(f"그래도 표시하기 ({p.name})", key=f"force_{p}"):
            return

    try:
        ext = p.suffix.lower()
        if ext in (".md", ".txt"):
            content = p.read_text(encoding="utf-8", errors="replace")
            _h(
                '<div style="background:#fff;border:1px solid #E2E8F0;'
                'border-radius:10px;padding:24px 28px;margin-top:8px;'
                'max-height:70vh;overflow-y:auto;">'
            )
            st.markdown(content)
            _h("</div>")
        elif ext == ".sql":
            content = p.read_text(encoding="utf-8", errors="replace")
            st.code(content, language="sql")
        else:
            st.info("이 형식은 인라인 뷰어를 지원하지 않습니다. 다운로드 버튼을 이용하세요.")
    except Exception as e:
        st.error(f"파일 읽기 실패: {e}")


def _download_btn(p: Path, key: str, label: str = "⬇️") -> None:
    """단일 다운로드 버튼 렌더링."""
    try:
        mime = _DL_MIME.get(p.suffix.lower(), "application/octet-stream")
        st.download_button(
            label,
            data=p.read_bytes(),
            file_name=p.name,
            mime=mime,
            key=key,
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"다운로드 준비 실패: {e}")


# ══════════════════════════════════════════════════════════════════════════
#  메인 탭 렌더
# ══════════════════════════════════════════════════════════════════════════

def _tab_manual() -> None:
    """매뉴얼 뷰어 탭 — docs/ 폴더 문서 인라인 렌더링 + 다운로드."""
    from ui.design import topbar
    topbar()

    # ── 헤더 ────────────────────────────────────────────────────────────
    _h(
        '<div style="background:linear-gradient(135deg,#0F172A 0%,#1E3A5F 100%);'
        'border-radius:12px;padding:24px 28px 20px;margin-bottom:20px;'
        'position:relative;overflow:hidden;">'
        '<div style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;'
        'background:radial-gradient(circle,rgba(59,130,246,0.2) 0%,transparent 70%);'
        'pointer-events:none;"></div>'
        '<div style="font-size:11px;font-weight:700;color:rgba(255,255,255,0.4);'
        'letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px;">'
        '좋은문화병원 AI 시스템</div>'
        '<div style="font-size:20px;font-weight:800;color:#fff;margin-bottom:6px;">'
        '📚 매뉴얼 · 문서 뷰어</div>'
        '<div style="font-size:12px;color:rgba(255,255,255,0.45);">'
        'docs/ 폴더 — Markdown 인라인 렌더링 · DOCX/MD 다운로드</div>'
        '</div>'
    )

    manuals    = _get_manuals()
    subfolders = _scan_subfolders()

    if not manuals and not subfolders:
        st.info("docs/ 폴더가 없거나 문서 파일이 없습니다.")
        return

    # ════════════════════════════════════════════════════════════════
    #  주요 매뉴얼
    # ════════════════════════════════════════════════════════════════
    if manuals:
        section_header(
            "주요 매뉴얼",
            "docs/ 최상위 문서 — 클릭하면 인라인으로 열림 · MD/DOCX 다운로드",
            C["blue"],
        )

        for item in manuals:
            stem   = item["title"]
            icon, label, desc = _MANUAL_META.get(stem, ("📄", stem, ""))
            md_p   = item.get("md")
            docx_p = item.get("docx")
            sql_p  = item.get("sql")

            # 파일 크기 표시
            size_tags = []
            for p, tag in [(md_p, "MD"), (docx_p, "DOCX"), (sql_p, "SQL")]:
                if p and p.exists():
                    try:
                        kb = round(p.stat().st_size / 1024, 1)
                        size_tags.append(f"{tag} {kb}KB")
                    except Exception:
                        size_tags.append(tag)
            size_str = "  ·  ".join(size_tags)

            with st.expander(
                f"{icon} **{label}**" + (f"  — {size_str}" if size_str else ""),
                expanded=False,
            ):
                # 설명 + 다운로드 버튼 행
                _h(
                    f'<div style="font-size:12px;color:{C["t3"]};'
                    f'margin-bottom:10px;">{desc}</div>'
                )
                dl_cols = []
                if md_p and md_p.exists():
                    dl_cols.append(("⬇️ MD 다운로드",   md_p,   f"dl_md_{stem}"))
                if docx_p and docx_p.exists():
                    dl_cols.append(("⬇️ DOCX 다운로드", docx_p, f"dl_docx_{stem}"))
                if sql_p and sql_p.exists():
                    dl_cols.append(("⬇️ SQL 다운로드",  sql_p,  f"dl_sql_{stem}"))

                if dl_cols:
                    btn_cols = st.columns(len(dl_cols))
                    for col, (lbl, p, key) in zip(btn_cols, dl_cols):
                        with col:
                            _download_btn(p, key, lbl)

                st.divider()

                # 인라인 뷰어
                view_p = md_p or sql_p
                if view_p and view_p.exists():
                    _render_file(view_p)
                elif docx_p and docx_p.exists():
                    _h(
                        '<div style="background:#FFFBEB;border:1px solid #FDE68A;'
                        'border-radius:8px;padding:12px 16px;text-align:center;">'
                        '<div style="font-size:13px;color:#92400E;">📎 DOCX 파일</div>'
                        '<div style="font-size:11.5px;color:#B45309;margin-top:4px;">'
                        'DOCX 인라인 뷰어는 지원하지 않습니다. 위 버튼으로 다운로드하세요.</div>'
                        '</div>'
                    )

        gap(16)

    # ════════════════════════════════════════════════════════════════
    #  문서 라이브러리 (하위 폴더)
    # ════════════════════════════════════════════════════════════════
    if subfolders:
        section_header(
            "문서 라이브러리",
            "docs/ 하위 폴더 — 파일 목록 · 다운로드 · 텍스트 파일 인라인 뷰",
            C["indigo"],
        )

        for folder_name, files in subfolders:
            ficon, flabel = _FOLDER_META.get(folder_name, ("📁", folder_name))
            viewable_cnt  = sum(1 for f in files if f["ext"] in _VIEWABLE)

            with st.expander(
                f"{ficon} **{flabel}** ({folder_name})  —  {len(files)}개 파일"
                + (f", {viewable_cnt}개 뷰 가능" if viewable_cnt else ""),
                expanded=False,
            ):
                # 파일 목록 테이블 헤더
                _h(
                    '<div style="display:grid;grid-template-columns:1fr auto auto;'
                    'gap:8px;padding:4px 0;border-bottom:2px solid #E2E8F0;'
                    'font-size:11px;font-weight:700;color:#64748B;margin-bottom:4px;">'
                    '<span>파일명</span><span style="text-align:right;">크기</span>'
                    '<span style="text-align:center;">다운로드</span></div>'
                )

                for finfo in files:
                    p   = finfo["path"]
                    ext = finfo["ext"]

                    row_c, dl_c = st.columns([5, 1])
                    with row_c:
                        ext_badge_col = {
                            ".md":   C["blue"],
                            ".sql":  C["warn"],
                            ".txt":  C["ok"],
                            ".docx": "#6B7280",
                            ".xlsx": "#059669",
                            ".pdf":  C["danger"],
                        }.get(ext, C["t3"])
                        _h(
                            f'<div style="padding:4px 0;border-bottom:1px solid #F1F5F9;'
                            f'display:flex;align-items:center;gap:8px;">'
                            f'<span style="font-size:10px;font-weight:700;color:{ext_badge_col};'
                            f'background:{ext_badge_col}18;padding:1px 6px;border-radius:4px;">'
                            f'{ext.lstrip(".").upper()}</span>'
                            f'<span style="font-size:12px;color:#334155;">{finfo["rel"]}</span>'
                            f'<span style="font-size:11px;color:{C["t3"]};margin-left:auto;">'
                            f'{finfo["size_kb"]} KB</span>'
                            f'</div>'
                        )
                    with dl_c:
                        _download_btn(p, f"dl_{folder_name}_{finfo['name']}", "⬇️")

                    # 뷰어 — md/txt/sql 만
                    if ext in _VIEWABLE:
                        view_key = f"view_{folder_name}_{finfo['name']}"
                        if st.toggle(f"  👁️ {p.name} 보기", key=view_key):
                            _render_file(p)
