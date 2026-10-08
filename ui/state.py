"""캐시된 데모 데이터와 세션(라이브) 상태."""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import streamlit as st

from core.params import load_params
from core.relocation import INF
from core.simulation import run_many, run_scenario, summarize, train_predictor
from core.stacking import copy_area
from ui.components import ROOT

ROLES = ["야드 플래너", "선사 적재 플래너", "본선 플래너", "화주·운송사"]


@st.cache_resource(show_spinner="가정값과 과거 항차 이력을 불러오는 중…")
def get_params() -> dict:
    return load_params()


@st.cache_resource(show_spinner="선적순서 예측 모델 학습 중…")
def get_predictor():
    return train_predictor(get_params())


@st.cache_resource(show_spinner="오늘의 야드 시나리오 생성 중…")
def get_demo():
    return run_scenario(get_params(), get_predictor())


@st.cache_data(show_spinner="시드별 시뮬레이션 집계 중…")
def get_multi_seed_summary() -> pd.DataFrame:
    p = get_params()
    n = p["simulation"]["dashboard_seeds"]
    return summarize(run_many(p, get_predictor(), range(p["seed"] + 1, p["seed"] + 1 + n)))


@st.cache_data(show_spinner=False)
def get_multi_seed_runs_boxes() -> pd.DataFrame:
    """화주 가이드용: 반입 시간대별로 '재조작에 연루된 박스' 비율 (현행 방식, 여러 시드)."""
    p, pred = get_params(), get_predictor()
    rows = []
    for s in range(p["seed"] + 1, p["seed"] + 1 + p["simulation"]["dashboard_seeds"]):
        r = run_scenario(p, pred, s)
        for v in r.scenario.vessels:
            boxes = r.scenario.boxes(v.vessel_id)
            moved = {e["box"] for e in r.runs[(v.vessel_id, "current")]["reloc_log"]}
            hrs = (v.cutoff - boxes.arrival_time).dt.total_seconds() / 3600
            rows.append(pd.DataFrame({"hours_before": hrs.values, "moved": boxes.cntr_no.isin(moved).values}))
    return pd.concat(rows, ignore_index=True)


# ── 라이브 세션 상태 (예측 → 장치, 계획 변경 이벤트) ─────────────
def live() -> dict:
    if "live" not in st.session_state:
        demo = get_demo()
        df = demo.scenario.containers
        preds = dict(zip(demo.preds.cntr_no, demo.preds.pred_pct))
        boxes = df.merge(demo.preds[["cntr_no", "weight_group", "pred_pct", "pred_lo", "pred_hi"]], on="cntr_no")
        st.session_state.live = {
            "boxes": boxes,
            "areas": {v.vessel_id: {"current": copy_area(demo.runs[(v.vessel_id, "current")]["area"]),
                                    "B": copy_area(demo.runs[(v.vessel_id, "B")]["area"])}
                      for v in demo.scenario.vessels},
            "preds": {**preds, **{c: INF for c in df.cntr_no[df.rolled]}},
            "user_boxes": [],
            "versions": {"선사 플래너": 12, "본선 플래너": 12, "야드 플래너": 12},
            "acks": {"선사 플래너": True, "본선 플래너": True, "야드 플래너": True},
            "events": [],
            "suggestions": [],
            "last_event": None,
            "event_count": 0,
        }
    return st.session_state.live


def true_seq(boxes: pd.DataFrame, vessel_id: str) -> dict:
    b = boxes[(boxes.vessel_id == vessel_id) & (~boxes.rolled)]
    return dict(zip(b.cntr_no, b.true_load_seq))


def display_seq(L: dict) -> dict:
    """3D·단면 표시용 선적 순서(백분위). 실제 박스 = 실제 순서, 사용자 장치 박스 = 예측, 롤오버 = INF."""
    b = L["boxes"]
    out = {c: (INF if r else p) for c, p, r in zip(b.cntr_no, b.true_pct, b.rolled)}
    for u in L["user_boxes"]:
        out[u["cntr_no"]] = u["pred_pct"]
    return out


# ── 사이드바 ──────────────────────────────────────────
def sidebar():
    demo = get_demo()
    st.logo(str(ROOT / "assets" / "logo.svg"), size="large", icon_image=str(ROOT / "assets" / "icon.svg"))
    with st.sidebar:
        st.markdown('<div class="ss-logo"><div class="tag">Yard · Vessel · Liner — 하나의 계획</div></div>',
                    unsafe_allow_html=True)
        st.selectbox("역할", ROLES, key="role")
        names = {v.vessel_id: f"{v.name} · 블록 {v.block}" for v in demo.scenario.vessels}
        st.selectbox("선박", list(names), format_func=names.get, key="vessel_id")


def sidebar_footer():
    with st.sidebar:
        st.markdown('<div class="ss-side-foot"><span class="dot"></span><b>데모 데이터 · 가정값 기반</b><br>'
                    '시드 고정 합성 데이터입니다. 실측치가 아닙니다. 가정값은 <code>config/params.yaml</code>.</div>',
                    unsafe_allow_html=True)


def current_vessel():
    demo = get_demo()
    vid = st.session_state.get("vessel_id", demo.scenario.vessels[0].vessel_id)
    return demo.scenario.vessel(vid)


def fmt_pct(x: float) -> str:
    return "—" if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else f"{x * 100:.0f}%"
