"""합성 선박·컨테이너·반입 스트림 생성 — SPEC 5.2.

모든 분포는 config/params.yaml 의 '가정'값을 따른다. 같은 시드 → 같은 결과.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from core.events import PlanEvent, plan_events


@dataclass
class Vessel:
    vessel_id: str
    name: str
    eta: datetime
    etd: datetime
    cutoff: datetime
    port_rotation: list[str]   # 양하항 순서 (앞 = 먼저 하역)
    block: str


@dataclass
class Scenario:
    seed: int
    vessels: list[Vessel]
    containers: pd.DataFrame
    events: list[PlanEvent]

    def vessel(self, vessel_id: str) -> Vessel:
        return next(v for v in self.vessels if v.vessel_id == vessel_id)

    def boxes(self, vessel_id: str) -> pd.DataFrame:
        return self.containers[self.containers.vessel_id == vessel_id]


# ── 적재 순서 규칙 ────────────────────────────────────────────
def load_score(pod_d, weight, size, is_dg, noise, lr: dict) -> np.ndarray:
    """작을수록 먼저 실림. 먼 양하항(pod_d=1) 먼저, 무거운 박스 먼저."""
    wn = np.clip((np.asarray(weight, float) - 2.0) / 28.0, 0, 1)
    return ((1 - np.asarray(pod_d, float)) * lr["pod"] + (1 - wn) * lr["weight"]
            + np.asarray(is_dg, float) * lr["dg"] + (np.asarray(size) == 40) * lr["size40"]
            + np.asarray(noise, float))


def assign_true_seq(df: pd.DataFrame, lr: dict) -> pd.DataFrame:
    """VGM 중량 기준 실제 적재 순서. 롤오버 박스는 선적하지 않음(NaN)."""
    df = df.copy()
    df["true_load_seq"] = np.nan
    df["true_pct"] = np.nan
    for _, g in df[~df.rolled].groupby("vessel_id"):
        s = load_score(g.pod_d, g.vgm_weight, g["size"], g.is_dg, g.load_noise, lr)
        order = np.argsort(np.argsort(s, kind="stable"), kind="stable")
        df.loc[g.index, "true_load_seq"] = order + 1
        df.loc[g.index, "true_pct"] = order / max(len(g) - 1, 1)
    return df


# ── 박스 생성 ─────────────────────────────────────────────────
class _Namer:
    def __init__(self, rng, owners):
        self.rng, self.owners, self.used = rng, owners, set()

    def __call__(self) -> str:
        while True:
            n = f"{self.rng.choice(self.owners)}{self.rng.integers(0, 10**7):07d}"
            if n not in self.used:
                self.used.add(n)
                return n


def _make_boxes(rng, n, vessel: Vessel, window, params, namer, pod_probs) -> pd.DataFrame:
    c, lr = params["containers"], params["load_rule"]
    m = len(vessel.port_rotation)
    pos = rng.choice(m, size=n, p=pod_probs)
    size = np.where(rng.random(n) < c["ratio_20ft"], 20, 40)
    mu = np.where(size == 20, c["weight_20"][0], c["weight_40"][0])
    sd = np.where(size == 20, c["weight_20"][1], c["weight_40"][1])
    vgm = np.clip(rng.normal(mu, sd), *c["weight_clip"]).round(1)
    declared = np.clip(vgm + rng.normal(0, c["declared_error_std"], n), *c["weight_clip"]).round(1)
    start, end = window
    if start is None:  # 일반 반입: 마감 전 며칠, 마감 직전에 몰림
        hrs = c["arrival_days"] * 24 * rng.beta(*c["arrival_beta"], size=n) + 0.1
        arrival = [end - timedelta(hours=float(h)) for h in hrs]
    else:
        span = (end - start).total_seconds() / 3600
        arrival = [start + timedelta(hours=float(h)) for h in rng.uniform(0, span, n)]
    return pd.DataFrame({
        "cntr_no": [namer() for _ in range(n)],
        "vessel_id": vessel.vessel_id,
        "pod": [vessel.port_rotation[p] for p in pos],
        "pod_pos": pos,
        "pod_d": pos / max(m - 1, 1),
        "size": size,
        "declared_weight": declared,
        "vgm_weight": vgm,
        "is_dg": rng.random(n) < c["dg_ratio"],
        "arrival_time": pd.to_datetime(arrival),
        "load_noise": rng.normal(0, lr["noise"], n),
        "rolled": False,
        "weight_fixed": False,
        "late_add": False,
    })


def generate_scenario(params: dict, seed: int | None = None) -> Scenario:
    seed = params["seed"] if seed is None else seed
    rng = np.random.default_rng(seed)
    vp = params["vessels"]
    base = datetime.fromisoformat(params["base_date"])
    namer = _Namer(rng, params["containers"]["owner_codes"])
    vessels, frames, events = [], [], []
    for i, name in enumerate(vp["names"]):
        m = int(rng.integers(vp["pod_count"][0], vp["pod_count"][1] + 1))
        rotation = list(rng.choice(params["ports"], size=m, replace=False))
        eta = base + timedelta(hours=vp["eta_hours"][i])
        v = Vessel(vessel_id=f"V{i + 1}", name=name, eta=eta,
                   etd=eta + timedelta(hours=vp["stay_hours"][i]),
                   cutoff=eta - timedelta(hours=vp["cutoff_before_eta"]),
                   port_rotation=rotation, block=params["yard"]["block_names"][i])
        pod_probs = rng.dirichlet(np.full(m, 2.0))
        df = _make_boxes(rng, vp["boxes"][i], v, (None, v.cutoff), params, namer, pod_probs)

        def make(rng_, n, vessel, window, _pp=pod_probs):
            return _make_boxes(rng_, n, vessel, window, params, namer, _pp)

        df, ev = plan_events(rng, v, df, params, make)
        vessels.append(v)
        frames.append(df)
        events.extend(ev)
    cont = pd.concat(frames, ignore_index=True)
    cont = assign_true_seq(cont, params["load_rule"])
    cont = cont.sort_values(["vessel_id", "arrival_time"]).reset_index(drop=True)
    events.sort(key=lambda e: e.time)
    return Scenario(seed=seed, vessels=vessels, containers=cont, events=events)


def generate_history(params: dict, seed: int | None = None) -> pd.DataFrame:
    """과거 항차 이력 (같은 적재 규칙). 예측 학습용 — 실제 VGM 중량과 적재 백분위가 기록됨."""
    seed = (params["seed"] if seed is None else seed) + 7919
    rng = np.random.default_rng(seed)
    h, c, lr = params["history"], params["containers"], params["load_rule"]
    rows = []
    for voy in range(h["voyages"]):
        n = int(rng.integers(h["boxes"][0], h["boxes"][1] + 1))
        m = int(rng.integers(params["vessels"]["pod_count"][0], params["vessels"]["pod_count"][1] + 1))
        rotation = list(rng.choice(params["ports"], size=m, replace=False))
        pos = rng.choice(m, size=n, p=rng.dirichlet(np.full(m, 2.0)))
        size = np.where(rng.random(n) < c["ratio_20ft"], 20, 40)
        mu = np.where(size == 20, c["weight_20"][0], c["weight_40"][0])
        sd = np.where(size == 20, c["weight_20"][1], c["weight_40"][1])
        w = np.clip(rng.normal(mu, sd), *c["weight_clip"]).round(1)
        dg = rng.random(n) < c["dg_ratio"]
        pod_d = pos / max(m - 1, 1)
        s = load_score(pod_d, w, size, dg, rng.normal(0, lr["noise"], n), lr)
        pct = np.argsort(np.argsort(s, kind="stable"), kind="stable") / max(n - 1, 1)
        rows.append(pd.DataFrame({
            "voyage": f"H{voy + 1:02d}", "pod": [rotation[p] for p in pos], "pod_pos": pos,
            "n_pods": m, "pod_d": pod_d, "size": size, "weight": w, "is_dg": dg, "load_pct": pct}))
    return pd.concat(rows, ignore_index=True)
