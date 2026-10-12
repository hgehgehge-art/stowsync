"""같은 데이터로 현행 / A / B 를 돌리는 실험 러너."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.generator import Scenario, generate_history, generate_scenario
from core.predictor import LoadSeqPredictor
from core.stacking import STRATEGIES, run_vessel


def train_predictor(params: dict) -> LoadSeqPredictor:
    return LoadSeqPredictor(params).fit(generate_history(params))


@dataclass
class SimResult:
    scenario: Scenario
    runs: dict            # (vessel_id, strategy) → run dict
    preds: pd.DataFrame   # cntr_no 별 예측 (신고중량 기준)
    metrics: pd.DataFrame


def run_scenario(params: dict, predictor: LoadSeqPredictor, seed: int | None = None) -> SimResult:
    scn = generate_scenario(params, seed)
    df = scn.containers
    pr = predictor.predict_batch(df.pod_d, df.declared_weight, df["size"], df.is_dg)
    pr.insert(0, "cntr_no", df.cntr_no.values)
    decl = dict(zip(pr.cntr_no, pr.pred_pct))
    by_id = df.set_index("cntr_no")

    def repredict(cntrs):
        sub = by_id.loc[cntrs]
        out = predictor.predict_batch(sub.pod_d, sub.vgm_weight, sub["size"], sub.is_dg)
        return dict(zip(cntrs, out.pred_pct))

    runs, rows = {}, []
    mpr = params["ops"]["minutes_per_relocation"]
    for v in scn.vessels:
        boxes = scn.boxes(v.vessel_id)
        evs = [e for e in scn.events if e.vessel_id == v.vessel_id]
        for s in STRATEGIES:
            r = run_vessel(s, boxes, evs, decl, repredict, params)
            runs[(v.vessel_id, s)] = r
            rows.append({"seed": scn.seed, "vessel_id": v.vessel_id, "vessel": v.name, "strategy": s,
                         "relocations": r["relocations"], "premarshal": r["premarshal"],
                         "n_loaded": r["n_loaded"], "crane_wait_min": r["relocations"] * mpr})
    return SimResult(scn, runs, pr, pd.DataFrame(rows))


def summarize(metrics: pd.DataFrame) -> pd.DataFrame:
    """시드×전략 합계 (선박 합산)."""
    g = metrics.groupby(["seed", "strategy"], as_index=False)[["relocations", "premarshal", "n_loaded", "crane_wait_min"]].sum()
    g["reloc_per_box"] = g.relocations / g.n_loaded
    return g


def run_many(params: dict, predictor: LoadSeqPredictor, seeds, progress=None) -> pd.DataFrame:
    frames = []
    seeds = list(seeds)
    for i, s in enumerate(seeds):
        frames.append(run_scenario(params, predictor, s).metrics)
        if progress:
            progress((i + 1) / len(seeds))
    return pd.concat(frames, ignore_index=True)
