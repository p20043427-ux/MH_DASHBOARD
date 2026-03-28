"""
ui/dashboard_log_viewer.py  ─  병동 대시보드 관리자 모니터링 뷰어 (v1.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[기능]
  ① 실시간 핵심 KPI 카드 (총 액션 / AI 질문 / 오류율 / 평균 응답시간)
  ② 빠른 분석 버튼 클릭 순위
  ③ 병동 필터 사용 현황
  ④ 최근 이벤트 로그 테이블 (필터 가능)
  ⑤ 오류 쿼리 목록
  ⑥ 이벤트 파일 다운로드 (CSV 변환)
  ⑦ 30일 이상 이벤트 정리 버튼

[사용법]
  # dashboard_app.py 에서 관리자 탭으로 호출
  from ui.dashboard_log_viewer import render_dashboard_monitor

  if current_role == "admin":
      with tab_monitor:
          render_dashboard_monitor()
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st


def _kv(label: str, value: str, color: str = "#1E40AF") -> str:
    """KPI 카드 HTML."""
    return (
        f'<div style="background:#FFFFFF;border:1px solid #E8EDF2;border-radius:10px;'
        f'padding:14px 16px;text-align:center;box-shadow:0 1px 4px rgba(15,23,42,0.06);">'
        f'<div style="font-size:10px;font-weight:700;color:#64748B;text-transform:uppercase;'
        f'letter-spacing:.1em;margin-bottom:6px;">{label}</div>'
        f'<div style="font-size:26px;font-weight:800;color:{color};'
        f'font-variant-numeric:tabular-nums;line-height:1;">{value}</div>'
        f'</div>'
    )


def _ts_to_local(ts_str: str) -> str:
    """ISO 타임스탬프 → 로컬 시간 문자열."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        # UTC+9 변환 (병원 로컬 시간)
        from datetime import timedelta
        kst = dt.astimezone(tz=timezone(timedelta(hours=9)))
        return kst.strftime("%m/%d %H:%M:%S")
    except Exception:
        return ts_str[:16]


def _event_type_badge(et: str) -> str:
    BADGE = {
        "action":     ("#DBEAFE", "#1E40AF", "액션"),
        "llm":        ("#D1FAE5", "#065F46", "AI 채팅"),
        "query_fail": ("#FEE2E2", "#991B1B", "DB 실패"),
        "system":     ("#F3E8FF", "#6B21A8", "시스템"),
    }
    bg, fg, label = BADGE.get(et, ("#F1F5F9", "#475569", et))
    return (
        f'<span style="background:{bg};color:{fg};border-radius:4px;'
        f'padding:1px 8px;font-size:11px;font-weight:700;">{label}</span>'
    )


def render_dashboard_monitor() -> None:
    """
    병동 대시보드 모니터링 뷰어 렌더링.

    관리자 로그인 후 대시보드 탭에서 호출.
    """
    try:
        from utils.dashboard_monitor import get_dash_monitor
        mon = get_dash_monitor()
    except Exception as e:
        st.error(f"모니터 모듈 로드 실패: {e}")
        return

    st.markdown(
        '<div style="font-size:16px;font-weight:800;color:#0F172A;'
        'margin-bottom:12px;display:flex;align-items:center;gap:8px;">'
        '<span style="font-size:20px;">📊</span> 병동 대시보드 모니터링</div>',
        unsafe_allow_html=True,
    )

    # ── 새로고침 + 정리 버튼 ──────────────────────────────────────────
    _bc1, _bc2, _bc3 = st.columns([2, 2, 6], gap="small")
    with _bc1:
        if st.button("🔄 새로고침", key="mon_refresh", use_container_width=True):
            st.rerun()
    with _bc2:
        if st.button("🗑 30일 이상 정리", key="mon_purge", use_container_width=True):
            removed = mon.clear_old_events(keep_days=30)
            st.success(f"{removed}건 삭제 완료")
            st.rerun()

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [1] 핵심 KPI 카드
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    m = mon.get_metrics()

    _llm_err_rate = (
        round(m.total_llm_errors / m.total_llm_queries * 100, 1)
        if m.total_llm_queries > 0 else 0.0
    )
    _err_color = "#DC2626" if _llm_err_rate >= 10 else "#F59E0B" if _llm_err_rate >= 5 else "#059669"

    k1, k2, k3, k4, k5 = st.columns(5, gap="small")
    k1.markdown(_kv("총 사용자 액션", f"{m.total_actions:,}"), unsafe_allow_html=True)
    k2.markdown(_kv("AI 채팅 질문", f"{m.total_llm_queries:,}", "#7C3AED"), unsafe_allow_html=True)
    k3.markdown(_kv("LLM 오류율", f"{_llm_err_rate:.1f}%", _err_color), unsafe_allow_html=True)
    k4.markdown(_kv("LLM 평균 응답", f"{m.avg_llm_ms:.0f}ms", "#0891B2"), unsafe_allow_html=True)
    k5.markdown(_kv("DB 쿼리 실패", f"{m.total_query_fails:,}", "#DC2626"), unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [2] 빠른 분석 버튼 클릭 순위 + 병동 필터 사용
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _col_btn, _col_ward = st.columns(2, gap="small")

    with _col_btn:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E8EDF2;border-radius:10px;'
            'padding:14px 16px;box-shadow:0 1px 4px rgba(15,23,42,0.06);">',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:#1E293B;margin-bottom:8px;">'
            '🔘 빠른 분석 버튼 클릭 순위</div>',
            unsafe_allow_html=True,
        )
        if m.quick_btn_counts:
            sorted_btns = sorted(m.quick_btn_counts.items(), key=lambda x: -x[1])
            _total_clicks = max(sum(m.quick_btn_counts.values()), 1)
            for i, (label, cnt) in enumerate(sorted_btns[:8], 1):
                pct = cnt / _total_clicks * 100
                _bar_color = ["#1E40AF", "#2563EB", "#3B82F6", "#60A5FA", "#93C5FD"][min(i-1, 4)]
                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'font-size:12px;margin-bottom:3px;">'
                    f'<span style="color:#334155;font-weight:500;">{i}. {label}</span>'
                    f'<span style="color:#1E40AF;font-weight:700;font-family:Consolas,monospace;">'
                    f'{cnt}회 ({pct:.0f}%)</span></div>'
                    f'<div style="height:6px;background:#F1F5F9;border-radius:3px;">'
                    f'<div style="width:{pct:.0f}%;height:100%;background:{_bar_color};'
                    f'border-radius:3px;"></div></div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("아직 클릭 데이터 없음")
        st.markdown("</div>", unsafe_allow_html=True)

    with _col_ward:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E8EDF2;border-radius:10px;'
            'padding:14px 16px;box-shadow:0 1px 4px rgba(15,23,42,0.06);">',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:#1E293B;margin-bottom:8px;">'
            '🏥 병동 필터 사용 현황</div>',
            unsafe_allow_html=True,
        )
        if m.ward_filter_counts:
            sorted_wards = sorted(m.ward_filter_counts.items(), key=lambda x: -x[1])
            _total_wards = max(sum(m.ward_filter_counts.values()), 1)
            for wname, wcnt in sorted_wards[:8]:
                wpct = wcnt / _total_wards * 100
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:4px 0;border-bottom:1px solid #F8FAFC;font-size:12px;">'
                    f'<span style="color:#334155;">{wname}</span>'
                    f'<span style="color:#7C3AED;font-weight:700;font-family:Consolas,monospace;">'
                    f'{wcnt}회 ({wpct:.0f}%)</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("아직 필터 데이터 없음")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [3] 최근 이벤트 로그 테이블
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.markdown(
        '<div style="font-size:13px;font-weight:700;color:#1E293B;margin-bottom:6px;">'
        '📋 최근 이벤트 로그</div>',
        unsafe_allow_html=True,
    )
    _col_filter, _col_n, _ = st.columns([2, 2, 6], gap="small")
    with _col_filter:
        _type_filter = st.selectbox(
            "이벤트 유형",
            ["전체", "action", "llm", "query_fail"],
            key="mon_type_filter",
            label_visibility="collapsed",
        )
    with _col_n:
        _n_events = st.selectbox(
            "표시 건수",
            [20, 50, 100],
            key="mon_n_events",
            label_visibility="collapsed",
        )

    events = mon.get_recent_events(n=_n_events)
    if _type_filter != "전체":
        events = [e for e in events if e.get("event_type") == _type_filter]

    if not events:
        st.info("이벤트 없음")
    else:
        # ── 테이블 HTML ─────────────────────────────────────────────────
        _TH = (
            "padding:7px 10px;font-size:10px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:.07em;color:#64748B;border-bottom:1.5px solid #E2E8F0;"
            "background:#F8FAFC;white-space:nowrap;"
        )
        rows_html = ""
        for i, ev in enumerate(events):
            _bg = "#F8FAFC" if i % 2 == 0 else "#FFFFFF"
            _ts  = _ts_to_local(ev.get("timestamp", ""))
            _type = ev.get("event_type", "")
            _action = ev.get("action", "")
            _label = ev.get("label", "")
            _ward  = ev.get("ward", "")
            _ms    = ev.get("elapsed_ms", 0)
            _ok    = ev.get("success", True)
            _ok_html = (
                '<span style="color:#059669;font-weight:700;">✓</span>'
                if _ok else
                '<span style="color:#DC2626;font-weight:700;">✗</span>'
            )
            _ms_color = "#DC2626" if _ms > 5000 else "#F59E0B" if _ms > 2000 else "#059669"
            _ms_html = (
                f'<span style="font-family:Consolas,monospace;color:{_ms_color};">{_ms}ms</span>'
                if _ms > 0 else "─"
            )
            _td = f"padding:6px 10px;background:{_bg};border-bottom:1px solid #F8FAFC;font-size:12px;"
            rows_html += (
                f"<tr>"
                f'<td style="{_td}color:#64748B;font-family:Consolas,monospace;">{_ts}</td>'
                f'<td style="{_td}">{_event_type_badge(_type)}</td>'
                f'<td style="{_td}color:#475569;">{_action}</td>'
                f'<td style="{_td}color:#0F172A;font-weight:500;max-width:220px;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_label}</td>'
                f'<td style="{_td}color:#7C3AED;">{_ward}</td>'
                f'<td style="{_td}text-align:right;">{_ms_html}</td>'
                f'<td style="{_td}text-align:center;">{_ok_html}</td>'
                f"</tr>"
            )

        st.markdown(
            f'<div style="overflow-x:auto;border:1px solid #E8EDF2;border-radius:10px;'
            f'background:#FFFFFF;box-shadow:0 1px 4px rgba(15,23,42,0.06);">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>'
            f'<th style="{_TH}text-align:left;min-width:120px;">시간</th>'
            f'<th style="{_TH}text-align:left;">유형</th>'
            f'<th style="{_TH}text-align:left;">액션</th>'
            f'<th style="{_TH}text-align:left;">내용</th>'
            f'<th style="{_TH}text-align:left;">병동</th>'
            f'<th style="{_TH}text-align:right;">응답시간</th>'
            f'<th style="{_TH}text-align:center;">성공</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # [4] 오류 쿼리 목록 + CSV 다운로드
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    _col_err, _col_dl = st.columns([1, 1], gap="small")

    with _col_err:
        if m.error_keys:
            st.markdown(
                '<div style="background:#FEF2F2;border:1px solid #FCA5A5;border-radius:10px;'
                'padding:14px 16px;">'
                '<div style="font-size:12px;font-weight:700;color:#991B1B;margin-bottom:8px;">'
                '⚠️ 최근 실패 DB 쿼리</div>',
                unsafe_allow_html=True,
            )
            for ek in m.error_keys[-10:]:
                st.markdown(
                    f'<div style="font-size:12px;color:#7F1D1D;padding:3px 0;'
                    f'font-family:Consolas,monospace;border-bottom:1px solid #FEE2E2;">'
                    f'• {ek}</div>',
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)

    with _col_dl:
        st.markdown(
            '<div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;'
            'padding:14px 16px;">',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:#0C4A6E;margin-bottom:8px;">'
            '📥 로그 내보내기</div>',
            unsafe_allow_html=True,
        )
        try:
            all_events = mon.get_recent_events(n=1000)
            if all_events:
                # CSV 변환
                headers = ["timestamp", "event_type", "action", "label", "ward",
                           "elapsed_ms", "success", "detail", "session_id"]
                lines = [",".join(headers)]
                for ev in all_events:
                    row = [str(ev.get(h, "")).replace(",", "，") for h in headers]
                    lines.append(",".join(row))
                csv_data = "\n".join(lines)
                st.download_button(
                    "📥 이벤트 로그 CSV",
                    data=csv_data.encode("utf-8-sig"),
                    file_name=f"dashboard_events_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.caption("이벤트 없음")
        except Exception as e:
            st.caption(f"내보내기 실패: {e}")

        # 메트릭 JSON 다운로드
        try:
            _metrics_file = Path("logs") / "dashboard_metrics.json"
            if _metrics_file.exists():
                st.download_button(
                    "📊 메트릭 JSON",
                    data=_metrics_file.read_bytes(),
                    file_name="dashboard_metrics.json",
                    mime="application/json",
                    use_container_width=True,
                )
        except Exception:
            pass

        st.markdown("</div>", unsafe_allow_html=True)

    # 마지막 갱신 시각
    st.markdown(
        f'<div style="font-size:10px;color:#94A3B8;text-align:right;margin-top:8px;">'
        f'메트릭 마지막 갱신: {m.last_updated[:19]}</div>',
        unsafe_allow_html=True,
    )