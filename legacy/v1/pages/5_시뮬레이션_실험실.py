"""4.5 시뮬레이션 실험실 — 현행 vs A vs B 를 같은 데이터로 비교."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.brlp_loader import evaluate, load_dir, parse_brlp
from core.params import with_overrides
from core.simulation import run_many, summarize
from ui.components import (C, STRATEGY_COLORS, STRATEGY_SHORT, callout, chart, hero, kpi_card, kpi_row,
                           legend, section)
from ui.state import get_params, get_predictor

params = get_params()
ROOT = Path(__file__).resolve().parent.parent
ORDER = ["current", "A", "B"]
NAMES = {"current": "현행", "A": "A · 예측 공유", "B": "B · A + 실시간 변경"}

hero("시뮬레이션 실험실", "같은 합성 데이터로 현행 · 방식 A · 방식 B를 돌려 재조작 수를 비교합니다.", eyebrow="EVALUATION LAB")


@st.cache_data(show_spinner=False)
def lab_run(total, tiers, change, reps):
    p = with_overrides(params, total_boxes=total, max_tiers=tiers, change_ratio=change)
    m = run_many(p, get_predictor(), range(1000, 1000 + reps))
    return m


tab_syn, tab_brlp = st.tabs(["합성 데이터", "BRLP 벤치마크"])

with tab_syn:
    with st.form("lab"):
        c1, c2, c3, c4 = st.columns(4)
        total = c1.slider("컨테이너 수 (3척 합계)", 150, 900, sum(params["vessels"]["boxes"]), step=25)
        tiers = c2.slider("야드 단 수", 3, 6, params["yard"]["max_tiers"])
        change = c3.slider("계획 변경 비율", 0.0, 0.30, params["events"]["change_ratio"], step=0.02, format="%.2f")
        reps = c4.slider("반복 횟수 (시드 개수)", 3, 30, params["simulation"]["default_reps"])
        st.form_submit_button("▶  시뮬레이션 실행", type="primary", use_container_width=True)

    with st.spinner(f"시드 {reps}개 × 전략 3개 실행 중…"):
        raw = lab_run(total, tiers, change, reps)
    s = summarize(raw)
    agg = s.groupby("strategy").relocations.agg(["mean", "std", "count"]).reindex(ORDER)
    agg["ci"] = 1.96 * agg["std"].fillna(0) / np.sqrt(agg["count"])
    pm = s[s.strategy == "B"].premarshal.mean()
    base = agg.loc["current", "mean"]
    red = lambda k: (agg.loc[k, "mean"] - base) / base * 100

    kpi_row([
        kpi_card("현행 평균 재조작", f"{base:,.1f}", "회", sub=f"± {agg.loc['current', 'ci']:.1f} (95% 구간)",
                 accent=STRATEGY_COLORS["current"]),
        kpi_card("방식 A · 예측 공유", f"{agg.loc['A', 'mean']:,.1f}", "회", delta=red("A"),
                 sub=f"± {agg.loc['A', 'ci']:.1f} (95% 구간)", accent=STRATEGY_COLORS["A"], delay=.08),
        kpi_card("방식 B · 실시간 변경", f"{agg.loc['B', 'mean']:,.1f}", "회", delta=red("B"),
                 sub=f"± {agg.loc['B', 'ci']:.1f} (95% 구간)", accent=STRATEGY_COLORS["B"], delay=.16),
        kpi_card("B 사전 재정렬 (별도 집계)", f"{pm:,.1f}", "회", sub="유휴 시간 이동 · 재조작에 포함 안 함",
                 accent=C["warn"], delay=.24),
    ])

    worse = [NAMES[k] for k in ["A", "B"] if agg.loc[k, "mean"] >= base]
    if worse:
        callout(f"<b>주의:</b> 이 설정에서는 {', '.join(worse)}이(가) 현행보다 재조작이 적지 않습니다. 숫자는 조정하지 않았습니다.",
                "warn")
    b_total = agg.loc["B", "mean"] + pm
    callout(f"방식 B는 재조작 <b>{agg.loc['B', 'mean']:.1f}</b>회 + 사전 재정렬 <b>{pm:.1f}</b>회 = 총 이동 "
            f"<b>{b_total:.1f}</b>회 (현행 대비 {(b_total - base) / base * 100:+.0f}%). 사전 재정렬은 선박 작업 중이 아닌 유휴 시간에 실행됩니다.")

    left, right = st.columns(2, gap="medium")
    with left:
        section("평균 재조작 수", "점 = 평균 · 막대 = 95% 신뢰구간")
        fig = go.Figure()
        for k in ORDER:
            fig.add_trace(go.Scatter(
                x=[NAMES[k]], y=[agg.loc[k, "mean"]], mode="markers+text", name=NAMES[k],
                error_y=dict(type="data", array=[agg.loc[k, "ci"]], color=STRATEGY_COLORS[k], thickness=2, width=10),
                marker=dict(size=16, color=STRATEGY_COLORS[k], line=dict(color=C["bg"], width=2)),
                text=[f"{agg.loc[k, 'mean']:.1f}"], textposition="middle right", textfont=dict(color=C["text"], size=13),
                hovertemplate=f"{NAMES[k]}<br>평균 %{{y:.1f}}회<extra></extra>"))
        fig.update_layout(showlegend=False, yaxis=dict(title="재조작 (회, 3척 합계)", rangemode="tozero"),
                          xaxis=dict(showgrid=False, range=[-0.5, 2.8]))
        chart(fig, height=340)
    with right:
        section("반복별 분포", f"시드 {reps}개")
        fig = go.Figure()
        for k in ORDER:
            d = s[s.strategy == k]
            fig.add_trace(go.Box(y=d.relocations, name=NAMES[k], boxpoints="all", jitter=.35, pointpos=0,
                                 marker=dict(color=STRATEGY_COLORS[k], size=7, opacity=.85,
                                             line=dict(color=C["bg"], width=1)),
                                 line=dict(color=STRATEGY_COLORS[k], width=2), fillcolor="rgba(0,0,0,0)",
                                 customdata=d.seed, hovertemplate="시드 %{customdata}<br>%{y}회<extra></extra>"))
        fig.update_layout(showlegend=False, yaxis=dict(title="재조작 (회)", rangemode="tozero"))
        chart(fig, height=340)
    legend([(NAMES[k], STRATEGY_COLORS[k]) for k in ORDER])

    section("시드별 결과", "선박 3척 합계")
    wide = s.pivot_table(index="seed", columns="strategy", values="relocations")[ORDER]
    wide.columns = [NAMES[k] for k in ORDER]
    wide["B 사전재정렬"] = s[s.strategy == "B"].set_index("seed").premarshal
    wide["A 감소율"] = (1 - wide[NAMES["A"]] / wide[NAMES["current"]]).map("{:.0%}".format)
    wide["B 감소율"] = (1 - wide[NAMES["B"]] / wide[NAMES["current"]]).map("{:.0%}".format)
    st.dataframe(wide, use_container_width=True, height=260)
    out = raw.assign(total_boxes=total, max_tiers=tiers, change_ratio=change)
    st.download_button("⬇  결과 CSV 다운로드", out.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"stowsync_sim_{total}box_{tiers}tier_{int(change * 100)}pct_{reps}seeds.csv",
                       mime="text/csv")
    st.caption("모든 입력은 config/params.yaml 의 가정값 기반 합성 데이터입니다. 같은 시드 → 같은 결과.")

with tab_brlp:
    callout("BRLP(Jovanovic et al. 2016) 공개 인스턴스의 야드 초기 배치에 <b>같은 재조작 규칙</b>을 적용하고, "
            "방식 B의 사전 재정렬을 예산만큼 적용했을 때를 비교합니다. 적재 순서는 (선박 단, 선박 스택) 순으로 고정했습니다(단순화 가정).")
    budget = st.slider("사전 재정렬 예산 (인스턴스당)", 0, 30, 5, key="brlp_budget")
    ups = st.file_uploader("BRLP .pro 파일 업로드 (여러 개 가능)", type=["pro", "txt"], accept_multiple_files=True)
    insts, errors = [], []
    for f in ups or []:
        try:
            insts.append(parse_brlp(f.getvalue().decode("utf-8", "ignore"), f.name))
        except ValueError as e:
            errors.append(f"{f.name}: {e}")
    if not insts:
        insts = load_dir(ROOT / "data" / "brlp")
        src = "data/brlp 폴더"
    else:
        src = "업로드 파일"
    for e in errors:
        st.error(e)
    if not insts:
        st.info("BRLP 파일이 없습니다. data/brlp/README.md 를 참고해 내려받거나 업로드하세요.")
    else:
        only_sample = all(i.name.startswith("SAMPLE_") for i in insts)
        if only_sample:
            callout("지금 보이는 것은 <b>자체 작성한 형식 예시 파일</b>입니다 (BRLP 실제 데이터 아님). "
                    "실제 인스턴스를 data/brlp 에 두거나 업로드하세요.", "warn")
        res = pd.DataFrame([evaluate(i, budget) for i in insts])
        st.caption(f"{src} · 인스턴스 {len(res)}개")
        t = res[["relocations_rule", "relocations_after_premarshal", "premarshal_moves", "lower_bound"]].sum()
        kpi_row([
            kpi_card("재조작 (규칙, 재정렬 없음)", f"{t.relocations_rule:,}", "회", accent=STRATEGY_COLORS["current"]),
            kpi_card("재조작 (B 사전 재정렬 후)", f"{t.relocations_after_premarshal:,}", "회",
                     delta=(t.relocations_after_premarshal - t.relocations_rule) / max(t.relocations_rule, 1) * 100,
                     delta_label="규칙 대비", accent=STRATEGY_COLORS["B"], delay=.08),
            kpi_card("사전 재정렬 이동", f"{t.premarshal_moves:,}", "회", sub="별도 집계", accent=C["warn"], delay=.16),
            kpi_card("하한 (방해 박스 수)", f"{t.lower_bound:,}", "회", sub="어떤 방법도 이보다 적을 수 없음",
                     accent=C["muted"], delay=.24),
        ])
        show = res.head(40)
        fig = go.Figure()
        for col, name, color in [("relocations_rule", "규칙", STRATEGY_COLORS["current"]),
                                 ("relocations_after_premarshal", "B 재정렬 후", STRATEGY_COLORS["B"]),
                                 ("lower_bound", "하한", C["muted"])]:
            fig.add_trace(go.Bar(x=show.instance, y=show[col], name=name, marker=dict(color=color, cornerradius=3),
                                 hovertemplate="%{x}<br>" + name + " %{y}회<extra></extra>"))
        fig.update_layout(barmode="group", yaxis=dict(title="재조작 (회)"), xaxis=dict(tickangle=-30))
        chart(fig, height=340)
        st.dataframe(res, use_container_width=True, hide_index=True)
        st.download_button("⬇  BRLP 결과 CSV", res.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"stowsync_brlp_budget{budget}.csv", mime="text/csv")
