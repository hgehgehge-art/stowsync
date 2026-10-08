"""4.1 관제 대시보드."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.events import EVENT_LABEL, boxes_beneath
from core.relocation import blocking_count
from ui.components import (C, RISK_SCALE, VESSEL_COLORS, callout, chart, hero, kpi_card, kpi_row, legend,
                           section)
from ui.state import get_demo, get_multi_seed_summary, get_params, live

params = get_params()
demo = get_demo()
scn = demo.scenario
m = demo.metrics
L = live()

hero("관제 대시보드", "오늘 입항 선박 3척의 선적 준비 상태와 재조작 위험을 한 화면에서 봅니다.")

# ── 역할별 한 줄 안내 ──
role = st.session_state.get("role", "야드 플래너")
tips = {
    "야드 플래너": "반입 컨테이너마다 <b>추천 슬롯</b>이 준비되어 있습니다 → <b>선적위치 예측</b>",
    "선사 적재 플래너": "계획을 바꾸면 야드에 주는 영향이 즉시 계산됩니다 → <b>계획 동기화</b>",
    "본선 플래너": "재조작 위험이 높은 블록을 아래 히트맵에서 먼저 확인하세요.",
    "화주·운송사": "재조작 위험이 낮은 반입 시간대를 미리 볼 수 있습니다 → <b>화주 반입가이드</b>",
}
callout(f"<b>{role}</b> · {tips[role]}")

# ── KPI ──
tot = m.groupby("strategy")[["relocations", "n_loaded", "crane_wait_min"]].sum()
cur, ss = tot.loc["current"], tot.loc["B"]
ms = get_multi_seed_summary()
spark_b = ms[ms.strategy == "B"].sort_values("seed")
pct = lambda a, b: (a - b) / b * 100 if b else 0.0
cards = [
    kpi_card("오늘 선적 예정 박스", f"{int(ss.n_loaded):,}", "개",
             sub=f"롤오버 {int(scn.containers.rolled.sum())}개 제외 · 3척 합계",
             spark=spark_b.n_loaded.tolist(), accent=C["primary"], delay=0),
    kpi_card("예상 재조작 횟수", f"{int(ss.relocations):,}", "회", delta=pct(ss.relocations, cur.relocations),
             sub=f"현행 방식이면 {int(cur.relocations):,}회", spark=spark_b.relocations.tolist(), accent=C["safe"], delay=.08),
    kpi_card("박스당 재조작률", f"{ss.relocations / ss.n_loaded:.2f}", "회/박스",
             delta=pct(ss.relocations / ss.n_loaded, cur.relocations / cur.n_loaded),
             sub=f"현행 {cur.relocations / cur.n_loaded:.2f}회/박스", spark=spark_b.reloc_per_box.tolist(),
             accent=C["warn"], delay=.16),
    kpi_card("예상 크레인 대기", f"{ss.crane_wait_min:,.0f}", "분", delta=pct(ss.crane_wait_min, cur.crane_wait_min),
             sub=f"재조작 1회 = {params['ops']['minutes_per_relocation']}분 (가정)",
             spark=spark_b.crane_wait_min.tolist(), accent=C["danger"], delay=.24),
]
kpi_row(cards)
st.caption(f"StowSync(방식 B) 기준 · 배지는 같은 데이터로 돌린 현행 방식 대비 · 스파크라인은 시드 {len(spark_b)}개 시뮬레이션 분포")

left, right = st.columns([1.55, 1], gap="medium")

# ── 선박 스케줄 타임라인 ──
with left:
    section("선박 스케줄", "반입 마감 · 입항 · 출항")
    fig = go.Figure()
    phases = [("반입 피크(마감 전 24h)", C["border"]), ("마감 → 입항", "#24476F"), ("접안 · 선적", None)]
    ylab = {v.name: f"<b>{v.name}</b><br><span style='font-size:10px;color:{C['muted']}'>{' → '.join(v.port_rotation)}</span>"
            for v in scn.vessels}
    for i, v in enumerate(scn.vessels):
        spans = [(v.cutoff - timedelta(hours=24), v.cutoff), (v.cutoff, v.eta), (v.eta, v.etd)]
        for (name, col), (a, b) in zip(phases, spans):
            fig.add_trace(go.Bar(
                y=[ylab[v.name]], x=[(b - a).total_seconds() * 1000], base=[a.isoformat()], orientation="h",
                marker=dict(color=col or VESSEL_COLORS[i], line=dict(color=C["bg"], width=2), cornerradius=4),
                showlegend=False, width=0.55,
                hovertemplate=f"<b>{v.name}</b><br>{name}<br>{a:%m-%d %H:%M} → {b:%m-%d %H:%M}<extra></extra>"))
        fig.add_annotation(x=v.cutoff.isoformat(), y=ylab[v.name], text="마감", showarrow=False, yshift=19,
                           font=dict(size=10, color=C["danger"]))
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    demo_now = datetime.fromisoformat(params["base_date"]).replace(hour=now_kst.hour, minute=now_kst.minute)
    fig.add_shape(type="line", x0=demo_now.isoformat(), x1=demo_now.isoformat(), y0=0, y1=1, yref="paper",
                  line=dict(color=C["primary"], width=1.5, dash="dot"))
    fig.add_annotation(x=demo_now.isoformat(), y=1.06, yref="paper", text="NOW", showarrow=False,
                       font=dict(family="JetBrains Mono", size=11, color=C["primary"]))
    x0 = min(v.cutoff for v in scn.vessels) - timedelta(hours=26)
    x1 = max(v.etd for v in scn.vessels) + timedelta(hours=2)
    fig.update_layout(barmode="overlay", showlegend=False,
                      xaxis=dict(type="date", tickformat="%m-%d<br>%H:%M", range=[x0.isoformat(), x1.isoformat()]),
                      yaxis=dict(autorange="reversed", showgrid=False), margin=dict(l=150, r=20, t=30, b=40))
    chart(fig, height=270)
    legend([("반입 피크(마감 전 24h)", C["border"]), ("마감 → 입항", "#24476F")] +
           [(f"{v.name} 접안·선적", VESSEL_COLORS[i]) for i, v in enumerate(scn.vessels)])

    # ── 블록 × 베이 재조작 위험 히트맵 ──
    section("블록별 재조작 위험", "베이마다 '아래에 먼저 실릴 박스를 깔고 있는' 박스 수")
    mode = st.segmented_control("배치 기준", ["현행 배치", "StowSync 배치"], default="StowSync 배치",
                                key="heat_mode", label_visibility="collapsed")
    skey = "current" if mode == "현행 배치" else "B"
    seq = dict(zip(L["boxes"].cntr_no, L["boxes"].true_load_seq))
    rows, maxbay = [], max(len(L["areas"][v.vessel_id][skey]) for v in scn.vessels)
    for v in scn.vessels:
        area = L["areas"][v.vessel_id][skey]
        z = [blocking_count(area[b], seq) if b in area else np.nan for b in range(maxbay)]
        rows.append(z)
    z = np.array(rows, float)
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{b + 1:02d}" for b in range(maxbay)], y=[f"{v.block} · {v.name}" for v in scn.vessels],
        colorscale=RISK_SCALE, zmin=0, zmax=max(8, np.nanmax(z)), xgap=3, ygap=3,
        colorbar=dict(title=dict(text="위험 박스", font=dict(color=C["muted"], size=11)), thickness=10,
                      tickfont=dict(color=C["muted"]), outlinewidth=0),
        hovertemplate="%{y}<br>베이 %{x}<br>위험 박스 %{z}개<extra></extra>"))
    fig.update_layout(xaxis=dict(title="베이", showgrid=False), yaxis=dict(showgrid=False, autorange="reversed"),
                      margin=dict(l=120, r=10, t=10, b=40))
    chart(fig, height=230)

# ── 최근 이벤트 피드 ──
with right:
    section("최근 이벤트", "계획 변경 → 야드 영향")
    loadable = set(L["boxes"].cntr_no[~L["boxes"].rolled])
    items = []
    for e in L["events"][::-1] + scn.events[::-1]:
        v = scn.vessel(e.vessel_id)
        aff = boxes_beneath(L["areas"][v.vessel_id]["current"], e.affected_cntrs, loadable)
        items.append(
            f'<div class="item {e.type}"><div class="time">{e.time:%H:%M}</div><div class="msg">'
            f'<b>{v.name}</b> {e.note} → 영향 박스 <b>{len(aff)}</b>개'
            f'<small>{e.time:%m-%d} · {EVENT_LABEL[e.type]} · 대상 {len(e.affected_cntrs)}개</small></div></div>')
    st.markdown('<div class="ss-feed">' + "".join(items) + "</div>", unsafe_allow_html=True)

    section("선박별 비교", "재조작 수")
    piv = m.pivot_table(index="vessel", columns="strategy", values="relocations").reindex(
        [v.name for v in scn.vessels])
    fig = go.Figure()
    for s, col, name in [("current", "#6B7F9E", "현행"), ("B", C["primary"], "StowSync")]:
        fig.add_trace(go.Bar(x=piv.index, y=piv[s], name=name, marker=dict(color=col, cornerradius=4),
                             text=piv[s], textposition="outside", textfont=dict(color=C["muted"], size=11),
                             hovertemplate="%{x}<br>" + name + " %{y}회<extra></extra>"))
    fig.update_layout(barmode="group", bargap=.35, bargroupgap=.08, yaxis=dict(title="재조작 (회)"),
                      margin=dict(l=50, r=10, t=40, b=30))
    chart(fig, height=260)
