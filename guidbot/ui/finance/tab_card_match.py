"""ui/finance/tab_card_match.py — 카드 매칭 탭"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
import streamlit as st

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False  # type: ignore

import sys, os as _os
_PR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../.."))
if _PR not in sys.path:
    sys.path.insert(0, _PR)

try:
    from utils.logger import get_logger as _gl
    from config.settings import settings as _s
    logger = _gl(__name__, log_dir=_s.log_dir)
except Exception:
    import logging as _l
    logger = _l.getLogger(__name__)
    if not logger.handlers:
        _fh = _l.StreamHandler()
        _fh.setFormatter(_l.Formatter(
            "[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(_fh)
        logger.setLevel(_l.DEBUG)

from ui.design import (
    C,
    PLOTLY_PALETTE,
    PLOTLY_CFG,
    kpi_card,
    section_header,
    gap,
    fmt_won,
    empty_state,
)

# backward-compat aliases (same names used in the original finance_dashboard.py)
_kpi_card      = kpi_card
_sec_hd        = section_header
_gap           = gap
_fmt_won       = fmt_won
_plotly_empty  = empty_state
_PALETTE       = PLOTLY_PALETTE
_PLOTLY_LAYOUT = PLOTLY_CFG

# ════════════════════════════════════════════════════════════════════
# 탭 6 — 카드사 승인내역 ↔ 병원 결제 매칭
# ════════════════════════════════════════════════════════════════════
def _tab_card_match() -> None:
    import io, datetime as _dt_cm

    st.markdown(f'<div class="wd-card" style="border-top:3px solid {C["indigo"]};padding:16px;">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="wd-sec"><span class="wd-sec-bar" style="background:{C["indigo"]};"></span>'
        f'💳 카드사 승인내역 ↔ 병원 결제 매칭'
        f'<span class="wd-sec-sub"> 정방향(카드사→병원) / 역방향(병원→카드사) 이중 검증</span></div>',
        unsafe_allow_html=True,
    )
    col_lbl, col_dt, col_dir, col_btn = st.columns([1,2,3,1], gap="small")
    with col_lbl:
        st.markdown(f'<div style="font-size:12px;font-weight:700;color:{C["t2"]};padding:8px 0 0 4px;">📅 입금일자</div>', unsafe_allow_html=True)
    with col_dt:
        _cm_date    = st.date_input("입금일자", value=st.session_state.get("cm_date",_dt_cm.date.today()),
                                    key="cm_date", label_visibility="collapsed", format="YYYY-MM-DD",
                                    max_value=_dt_cm.date.today(),
                                    help="병원 DB 조회 기준 날짜 (±2일 허용)")
        _cm_date_str = _cm_date.strftime("%Y%m%d")
    with col_dir:
        _direction  = st.radio("매칭 방향",
            options=["① 정방향 — 카드사 xlsx → 병원 DB 매칭","② 역방향 — 병원 DB → 카드사 xlsx 매칭"],
            key="cm_direction", label_visibility="collapsed", horizontal=True)
        _is_forward = "정방향" in _direction
    with col_btn:
        _do_match = st.button("🔍 매칭 실행", key="btn_card_match", type="primary", use_container_width=True)

    col_up, col_info = st.columns([4,6], gap="small")
    with col_up:
        uploaded = st.file_uploader("카드사 승인내역 xlsx", type=["xlsx","xls"], key="card_match_file",
                                    help="필수 컬럼: 승인일시, 승인번호, 승인금액")
    with col_info:
        st.markdown(
            f'<div style="background:#F0F4FF;border:1px solid #BFDBFE;border-radius:8px;padding:8px 14px;margin-top:4px;font-size:11.5px;color:{C["t2"]};">'
            f'<b>① 정방향</b>: 카드사 파일 기준 → 병원 DB 누락건 탐지<br>'
            f'<b>② 역방향</b>: 병원 DB 기준 → 카드사 파일 미확인건 탐지<br>'
            f'<span style="color:{C["t3"]};font-size:10.5px;">🔒 승인번호·카드번호는 AI 채팅 미전송</span></div>',
            unsafe_allow_html=True,
        )

    _d_from = (_dt_cm.datetime.strptime(_cm_date_str,"%Y%m%d")-_dt_cm.timedelta(days=2)).strftime("%Y%m%d")
    _d_to   = (_dt_cm.datetime.strptime(_cm_date_str,"%Y%m%d")+_dt_cm.timedelta(days=2)).strftime("%Y%m%d")
    _hosp_rows: List[Dict[str, Any]] = []; _db_ok = False; _db_err = ""
    try:
        from db.oracle_client import execute_query
        _sql_view = f"""
            SELECT 승인일시 AS 거래일자, REGEXP_REPLACE(승인번호,'[^0-9]','') AS 승인번호,
                   승인금액, NVL(카드사명,'') AS 카드사명, NVL(단말기ID,'') AS 단말기ID, NVL(설치위치,'') AS 설치위치
            FROM JAIN_WM.V_KIOSK_CARD_APPROVAL
            WHERE 승인일시 BETWEEN '{_d_from}' AND '{_d_to}'
            ORDER BY 승인일시
        """
        _rows_view = execute_query(_sql_view)
        if _rows_view is not None: _hosp_rows = _rows_view; _db_ok = True
    except Exception as _e1:
        _db_err = str(_e1); logger.error(f"[CardMatch] V_KIOSK_CARD_APPROVAL: {_e1}")

    if _db_ok:
        _db_badge = (f'<span style="background:{C["green"]}1A;color:{C["green"]};border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;">✅ DB 연결 ({len(_hosp_rows):,}건)</span>')
    else:
        _db_badge = (f'<span style="background:{C["red"]}1A;color:{C["red"]};border-radius:5px;padding:2px 8px;font-size:11px;font-weight:700;">❌ VIEW 조회 실패</span>'
                     f'<span style="font-size:10.5px;color:{C["t3"]};margin-left:6px;">DBeaver(관리자)에서 V_KIOSK_CARD_APPROVAL 생성 후 GRANT SELECT TO RAG_READONLY 실행</span>')
    st.markdown(f'<div style="margin:6px 0 8px;display:flex;align-items:center;gap:8px;">'
                f'<span style="font-size:11px;color:{C["t3"]};">병원 DB 현황:</span>{_db_badge}'
                f'<span style="font-size:10.5px;color:{C["t3"]};">{_cm_date_str} ±2일 / 총 {len(_hosp_rows):,}건</span></div>', unsafe_allow_html=True)

    _df_card = None
    if uploaded:
        try:
            import pandas as pd
            _bytes = uploaded.read()
            _df_raw = pd.read_excel(io.BytesIO(_bytes), dtype=str)
            _df_raw.columns = [str(c).strip() for c in _df_raw.columns]
            _missing = {"승인일시","승인번호","승인금액"} - set(_df_raw.columns)
            if _missing:
                st.error(f"❌ 필수 컬럼 없음: {', '.join(_missing)}")
            else:
                _df_card = _df_raw[_df_raw["거래결과"].str.contains("정상",na=False)].copy() if "거래결과" in _df_raw.columns else _df_raw.copy()
                _df_card["_apv_no"]   = _df_card["승인번호"].astype(str).str.strip().str.replace(r"\D","",regex=True)
                _df_card["_apv_amt"]  = pd.to_numeric(_df_card["승인금액"].astype(str).str.replace(r"[,￦₩\s]","",regex=True).str.replace(r"[^\d\-]","",regex=True),errors="coerce").fillna(0).astype(int)
                _df_card["_apv_date"] = pd.to_datetime(_df_card["승인일시"].astype(str).str[:10].str.replace(r"[/\-]","",regex=True),format="%Y%m%d",errors="coerce").dt.strftime("%Y%m%d")
                _df_card = _df_card[_df_card["_apv_amt"]>0].reset_index(drop=True)
                if "카드번호" in _df_card.columns:
                    _df_card["카드번호_표시"] = _df_card["카드번호"].astype(str).apply(
                        lambda v: v[:4]+"-****-****-"+v[-4:] if len(v.replace("-","").replace("*",""))>=8 else "****-****-****-****")
                with st.expander(f"📄 카드사 파일 — {len(_df_card):,}건 (정상승인)", expanded=False):
                    _prev_cols = [c for c in ["승인일시","승인번호","승인금액","카드사","카드번호_표시","거래결과","단말기ID","설치위치"] if c in _df_card.columns]
                    st.dataframe(_df_card[_prev_cols].rename(columns={"카드번호_표시":"카드번호(마스킹)"}).head(50), use_container_width=True, height=200)
        except Exception as _pe:
            st.error(f"❌ 파일 파싱 오류: {_pe}"); _df_card = None

    if not _is_forward and _hosp_rows:
        import pandas as pd
        with st.expander(f"🏥 병원 DB 조회 결과 — {len(_hosp_rows):,}건", expanded=True):
            st.dataframe(pd.DataFrame(_hosp_rows), use_container_width=True, height=260)

    if not _do_match and "card_match_result" not in st.session_state:
        if not uploaded:
            st.markdown(f'<div style="padding:30px;text-align:center;color:{C["t4"]};font-size:13px;">카드사 xlsx를 업로드하고 [매칭 실행] 버튼을 클릭하세요.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True); return

    if _do_match:
        import pandas as pd
        if not _db_ok and not _hosp_rows:
            st.error("❌ 병원 DB 연결 실패"); st.markdown("</div>", unsafe_allow_html=True); return
        if _df_card is None:
            st.warning("⚠️ 카드사 파일을 먼저 업로드하세요."); st.markdown("</div>", unsafe_allow_html=True); return
        _hosp_dict = {str(_hr.get("승인번호","") or "").strip().replace(" ",""): _hr for _hr in _hosp_rows if str(_hr.get("승인번호","") or "").strip()}
        _card_dict = {}
        for _, _crow in _df_card.iterrows():
            _cno = str(_crow.get("_apv_no","")).strip()
            if _cno: _card_dict[_cno] = _crow.to_dict()
        _results = []; _card_matched = set()
        if _is_forward:
            for _, _crow in _df_card.iterrows():
                _cno = str(_crow["_apv_no"]).strip(); _camt = int(_crow["_apv_amt"])
                _hrow = _hosp_dict.get(_cno)
                if _hrow:
                    _hamt = int(_hrow.get("승인금액",0) or 0)
                    _status = "정상" if _camt==_hamt else "금액불일치"; _card_matched.add(_cno)
                else:
                    _status = "누락"; _hrow = {}
                _results.append({"상태":_status,"거래일자":str(_crow.get("_apv_date",""))[:8],"승인번호":_cno,
                    "카드사금액":_camt,"병원금액":int(_hrow.get("승인금액",0) or 0),
                    "차이":_camt-int(_hrow.get("승인금액",0) or 0),
                    "카드사":str(_crow.get("카드사","")) if "카드사" in _df_card.columns else "",
                    "단말기ID":str(_crow.get("단말기ID","") or _hrow.get("단말기ID","")),
                    "설치위치":str(_crow.get("설치위치","") or _hrow.get("설치위치","")),"출처":"카드사→병원"})
            for _hno, _hr in _hosp_dict.items():
                if _hno not in _card_matched:
                    _results.append({"상태":"병원만","거래일자":str(_hr.get("거래일자",""))[:8],"승인번호":_hno,
                        "카드사금액":0,"병원금액":int(_hr.get("승인금액",0) or 0),
                        "차이":-int(_hr.get("승인금액",0) or 0),"카드사":str(_hr.get("카드사명","")),"단말기ID":str(_hr.get("단말기ID","")),"설치위치":str(_hr.get("설치위치","")),"출처":"병원만"})
        else:
            for _hno, _hr in _hosp_dict.items():
                _hamt = int(_hr.get("승인금액",0) or 0); _crow = _card_dict.get(_hno)
                if _crow: _camt = int(_crow.get("_apv_amt",0) or 0); _status = "정상" if _hamt==_camt else "금액불일치"; _card_matched.add(_hno)
                else:      _status = "병원만"; _crow = {}; _camt = 0
                _results.append({"상태":_status,"거래일자":str(_hr.get("거래일자",""))[:8],"승인번호":_hno,
                    "병원금액":_hamt,"카드사금액":_camt,"차이":_hamt-_camt,
                    "카드사":str(_hr.get("카드사명","")),"단말기ID":str(_hr.get("단말기ID","")),"설치위치":str(_hr.get("설치위치","")),"출처":"병원→카드사"})
            for _cno, _crow in _card_dict.items():
                if _cno not in _card_matched:
                    _camt = int(_crow.get("_apv_amt",0) or 0)
                    _results.append({"상태":"누락","거래일자":str(_crow.get("_apv_date",""))[:8],"승인번호":_cno,
                        "병원금액":0,"카드사금액":_camt,"차이":_camt,
                        "카드사":str(_crow.get("카드사","")) if "카드사" in _df_card.columns else "",
                        "단말기ID":str(_crow.get("단말기ID","")),"설치위치":str(_crow.get("설치위치","")),"출처":"카드사만"})
        st.session_state["card_match_result"] = _results
        st.session_state["card_match_dir"]    = "정방향" if _is_forward else "역방향"
        st.session_state["card_match_date"]   = _cm_date_str

    _results   = st.session_state.get("card_match_result",[])
    _match_dir = st.session_state.get("card_match_dir","정방향")
    if not _results: st.markdown("</div>", unsafe_allow_html=True); return

    _cnt_ok   = sum(1 for r in _results if r["상태"]=="정상")
    _cnt_miss = sum(1 for r in _results if r["상태"]=="누락")
    _cnt_amt  = sum(1 for r in _results if r["상태"]=="금액불일치")
    _cnt_hosp = sum(1 for r in _results if r["상태"]=="병원만")
    _total    = len(_results)
    _match_rate = round(_cnt_ok/max(_cnt_ok+_cnt_miss+_cnt_amt,1)*100,1)
    _gap()
    kc1,kc2,kc3,kc4,kc5 = st.columns(5, gap="small")
    def _cm_kpi(col,icon,label,val,color,sub=""):
        col.markdown(f'<div class="fn-kpi" style="border-top:3px solid {color};min-height:90px;">'
                     f'<div class="fn-kpi-icon">{icon}</div><div class="fn-kpi-label" style="font-size:9px;">{label}</div>'
                     f'<div class="fn-kpi-value" style="color:{color};font-size:26px;">{val}</div>'
                     f'<div class="fn-kpi-sub">{sub}</div></div>', unsafe_allow_html=True)
    _cm_kpi(kc1,"✅","정상 매칭",  f"{_cnt_ok:,}건",   C["green"],  f"매칭률 {_match_rate}%")
    _cm_kpi(kc2,"🔴","누락",       f"{_cnt_miss:,}건", C["red"],    "즉시 확인 필요")
    _cm_kpi(kc3,"🟡","금액불일치", f"{_cnt_amt:,}건",  C["yellow"], "금액 다름")
    _cm_kpi(kc4,"🟠","병원만",     f"{_cnt_hosp:,}건", C["orange"], "카드사 재확인")
    _cm_kpi(kc5,"📋",f"전체({_match_dir})",f"{_total:,}건",C["t2"],f"{_cm_date_str} 기준")
    _gap()
    _flt_c, _dl_c = st.columns([7,3], gap="small")
    with _flt_c:
        _flt_status = st.multiselect("상태 필터",options=["정상","누락","금액불일치","병원만"],
                                     default=["누락","금액불일치","병원만"],key="cm_flt_status",label_visibility="collapsed")
    with _dl_c:
        import pandas as _pd_dl
        _dl_csv = _pd_dl.DataFrame(_results).to_csv(index=False,encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("⬇️ 전체 결과 CSV",data=_dl_csv,
            file_name=f"카드매칭_{_match_dir}_{_cm_date_str}.csv",mime="text/csv",key="btn_cm_dl",use_container_width=True)

    _filtered = [r for r in _results if r["상태"] in (_flt_status or ["정상","누락","금액불일치","병원만"])]
    _STATUS_STYLE = {
        "정상":("#DCFCE7","#15803D","#059669","✅ 정상"),
        "누락":("#FEE2E2","#991B1B","#DC2626","🔴 누락"),
        "금액불일치":("#FEF3C7","#92400E","#D97706","🟡 금액차이"),
        "병원만":("#FFF7ED","#9A3412","#EA580C","🟠 병원만"),
    }
    _TH2 = "padding:7px 10px;font-size:10.5px;font-weight:700;color:#64748B;border-bottom:2px solid #E2E8F0;background:#F8FAFC;white-space:nowrap;"
    _tbl = (
        '<div style="overflow-x:auto;max-height:500px;overflow-y:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
        '<thead style="position:sticky;top:0;z-index:2;"><tr>'
        f'<th style="{_TH2}text-align:center;width:90px;">상태</th>'
        f'<th style="{_TH2}text-align:center;width:80px;">거래일자</th>'
        f'<th style="{_TH2}text-align:left;width:95px;">승인번호</th>'
        f'<th style="{_TH2}text-align:right;width:90px;">카드사금액</th>'
        f'<th style="{_TH2}text-align:right;width:90px;">병원금액</th>'
        f'<th style="{_TH2}text-align:right;width:80px;">차이</th>'
        f'<th style="{_TH2}text-align:left;">카드사</th>'
        f'<th style="{_TH2}text-align:left;">단말기</th>'
        f'<th style="{_TH2}text-align:left;">설치위치</th>'
        '</tr></thead><tbody>'
    )
    _fmta = lambda v: f"{v:,}" if v else "─"
    _fmtd = lambda v: (f'<span style="color:#DC2626;font-weight:700;">▲{v:,}</span>' if v>0
                       else f'<span style="color:#2563EB;font-weight:700;">▼{abs(v):,}</span>' if v<0 else "─")
    for _i, _r in enumerate(_filtered[:500]):
        _st = _r["상태"]
        _bg, _tx, _ac, _badge = _STATUS_STYLE.get(_st, ("#F8FAFC","#334155","#334155",_st))
        _rbg = _bg if _st!="정상" else ("#F8FAFC" if _i%2==0 else "#FFFFFF")
        _td2 = f"padding:6px 10px;background:{_rbg};border-bottom:1px solid #F0F4F8;"
        _tbl += (
            f"<tr><td style='{_td2}text-align:center;'>"
            f'<span style="background:{_bg};color:{_ac};border-radius:5px;padding:2px 7px;font-size:10.5px;font-weight:700;">{_badge}</span></td>'
            f'<td style="{_td2}text-align:center;font-family:Consolas,monospace;color:{C["t3"]};font-size:11.5px;">{_r["거래일자"]}</td>'
            f'<td style="{_td2}font-family:Consolas,monospace;font-weight:600;color:{C["t1"]};font-size:11.5px;">{_r["승인번호"]}</td>'
            f'<td style="{_td2}text-align:right;font-family:Consolas,monospace;color:{C["blue"]};">{_fmta(_r["카드사금액"])}</td>'
            f'<td style="{_td2}text-align:right;font-family:Consolas,monospace;color:{C["indigo"]};">{_fmta(_r["병원금액"])}</td>'
            f'<td style="{_td2}text-align:right;">{_fmtd(_r["차이"])}</td>'
            f'<td style="{_td2}color:{C["t2"]};">{_r.get("카드사","") or "─"}</td>'
            f'<td style="{_td2}color:{C["t3"]};font-size:11.5px;">{_r.get("단말기ID","") or "─"}</td>'
            f'<td style="{_td2}color:{C["t2"]};">{_r.get("설치위치","") or "─"}</td></tr>'
        )
    if len(_filtered)>500:
        _tbl += f'<tr><td colspan="9" style="padding:8px;text-align:center;color:{C["t3"]};font-size:11px;">... 이하 {len(_filtered)-500:,}건 생략 — CSV 다운로드 이용</td></tr>'
    if not _filtered:
        _tbl += f'<tr><td colspan="9" style="padding:30px;text-align:center;color:{C["t4"]};">필터 조건에 맞는 데이터 없음</td></tr>'
    st.markdown(_tbl+"</tbody></table></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid #F1F5F9;font-size:10.5px;">'
        f'<span style="color:{C["green"]};font-weight:700;">✅ 정상: 승인번호+금액 일치</span>'
        f'<span style="color:{C["red"]};font-weight:700;">🔴 누락: 한쪽에만 존재</span>'
        f'<span style="color:{C["yellow"]};font-weight:700;">🟡 금액불일치</span>'
        f'<span style="color:{C["orange"]};font-weight:700;">🟠 병원만: 카드사 재확인</span>'
        f'<span style="color:{C["t3"]};">🔒 승인번호·카드번호 → AI 채팅 미전송</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 메인 진입점 — render_finance_dashboard  v2.3
# ════════════════════════════════════════════════════════════════════
