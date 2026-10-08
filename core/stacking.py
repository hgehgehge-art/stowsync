"""장치 전략 (현행 / A: 예측 공유 / B: A + 실시간 변경 반영) — SPEC 5.3.

야드 영역(area): {bay: [stack0, ..., stackR-1]}, stack = 아래→위 박스 ID 리스트.
선박마다 전용 블록 하나를 쓴다 (가정).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from core.relocation import INF, count_relocations

STRATEGIES = {"current": "현행", "A": "방식 A · 예측 공유", "B": "방식 B · A + 실시간 변경"}


def make_area(n_boxes: int, yard: dict) -> dict[int, list[list[str]]]:
    per_bay = yard["rows_per_bay"] * yard["max_tiers"]
    n_bays = max(1, math.ceil(n_boxes * yard["slack"] / per_bay))
    return {b: [[] for _ in range(yard["rows_per_bay"])] for b in range(n_bays)}


def copy_area(area):
    return {k: [list(s) for s in v] for k, v in area.items()}


def _stacks(area):
    for b, stacks in area.items():
        for i, st in enumerate(stacks):
            yield b, i, st


def weight_group_fixed(w: float, edges) -> int:
    return int(np.searchsorted(edges, w, side="right"))


# ── 현행: 도착 순, 신고중량 그룹이 같은 스택 또는 가장 낮은 스택 (Kim et al. 2000) ──
def place_current(area, cntr: str, key, keys: dict, max_tiers: int):
    """key = (양하항, 중량그룹). 맨 위 박스의 key 가 같은 스택 중 가장 낮은 곳, 없으면 가장 낮은 스택."""
    open_ = [(b, i, st) for b, i, st in _stacks(area) if len(st) < max_tiers]
    same = [(b, i, st) for b, i, st in open_ if st and keys[st[-1]] == key]
    b, i, st = min(same or open_, key=lambda x: (len(x[2]), x[0], x[1]))
    st.append(cntr)
    keys[cntr] = key
    return b, i


# ── A/B: 예측 선적 순서로 '나중에 실릴 박스 위에 얹지 않기' ──
def score_stacks(area, p: float, preds: dict, max_tiers: int):
    """각 열린 스택의 (충돌 수, 최소 예측, 높이, 빈 스택 여부)."""
    out = []
    for b, i, st in _stacks(area):
        if len(st) >= max_tiers:
            continue
        ps = [preds.get(x, INF) for x in st]
        m = min(ps, default=INF)
        conflicts = sum(1 for q in ps if q < p)   # 이 박스보다 먼저 실릴 박스 → 이 박스가 방해
        out.append({"bay": b, "stack": i, "height": len(st), "min_pred": m, "conflicts": conflicts,
                    "empty": not st})
    return out


def choose_predictive(area, p: float, preds: dict, max_tiers: int):
    cands = score_stacks(area, p, preds, max_tiers)
    valid = [c for c in cands if not c["empty"] and c["min_pred"] >= p]
    if valid:  # 충돌 0 & 가장 꼭 맞는 스택 (빈 스택 아껴두기)
        return min(valid, key=lambda c: (c["min_pred"] - p, -c["height"], c["bay"], c["stack"]))
    empty = [c for c in cands if c["empty"]]
    if empty:
        return min(empty, key=lambda c: (c["bay"], c["stack"]))
    return min(cands, key=lambda c: (c["conflicts"], -c["min_pred"], c["height"], c["bay"], c["stack"]))


def place_predictive(area, cntr: str, p: float, preds: dict, max_tiers: int):
    c = choose_predictive(area, p, preds, max_tiers)
    area[c["bay"]][c["stack"]].append(cntr)
    preds[cntr] = p
    return c["bay"], c["stack"]


# ── B: 유휴시간 사전 재정렬 (예산 내) ──
def premarshal(area, preds: dict, max_tiers: int, budget: int) -> list[dict]:
    """방해하는 맨 위 박스를 '문제없는' 스택으로 옮긴다 (같은 베이 우선, 없으면 같은 블록 내 다른 베이).
    가장 먼저 실릴 박스를 막는 것부터 처리한다."""
    moves = []
    while len(moves) < budget:
        open_ = [(b2, j, min((preds.get(x, INF) for x in dst), default=None))
                 for b2, j, dst in _stacks(area) if len(dst) < max_tiers]
        best = None
        for b, stacks in area.items():
            for i, st in enumerate(stacks):
                if len(st) < 2:
                    continue
                pt = preds.get(st[-1], INF)
                below = min(preds.get(x, INF) for x in st[:-1])
                if pt <= below:
                    continue
                dests = []
                for b2, j, m in open_:
                    if (b2, j) == (b, i):
                        continue
                    other_bay = int(b2 != b)
                    if m is None:
                        dests.append((other_bay, 1, 0, b2, j))          # 빈 스택은 차선
                    elif m >= pt:
                        dests.append((other_bay, 0, m - pt if pt < INF else 0, b2, j))
                if not dests:
                    continue
                d = min(dests)
                cand = (below, b, i, d[3], d[4])
                if best is None or cand < best:
                    best = cand
        if best is None:
            break
        _, b, i, b2, j = best
        box = area[b][i].pop()
        area[b2][j].append(box)
        moves.append({"box": box, "bay": b, "from_stack": i, "to_bay": b2, "to_stack": j})
    return moves


# ── 선박 하나에 대해 전략 실행 ──
def run_vessel(strategy: str, boxes: pd.DataFrame, events: list, preds_declared: dict,
               repredict, params: dict) -> dict:
    """반입·이벤트 타임라인을 따라 장치하고, 선적 시 재조작 수를 센다.

    preds_declared: 반입 시점 예측(신고중량 기준) {cntr: pct}
    repredict(cntr_list) → {cntr: pct} (VGM 기준 재예측, 방식 B 전용)
    """
    yard, st = params["yard"], params["strategy"]
    max_tiers = yard["max_tiers"]
    area = make_area(len(boxes), yard)
    rows = boxes.set_index("cntr_no")
    preds: dict[str, float] = {}
    known = dict(preds_declared)          # B 가 알고 있는 최신 예측
    keys: dict = {}
    pm_log: list[dict] = []
    budget = st["premarshal_budget"] if strategy == "B" else 0
    per_event = budget // (len(events) + 1) if budget else 0

    timeline = [(t, 0, c) for c, t in zip(boxes.cntr_no, boxes.arrival_time)]
    timeline += [(e.time, 1, e) for e in events]
    timeline.sort(key=lambda x: (x[0], x[1]))

    for _, kind, obj in timeline:
        if kind == 0:
            c = obj
            r = rows.loc[c]
            if strategy == "current":
                g = weight_group_fixed(r.declared_weight, st["weight_groups"])
                key = (r.pod, g) if st["current_by_pod"] else g
                place_current(area, c, key, keys, max_tiers)
            elif strategy == "A":
                place_predictive(area, c, known[c], preds, max_tiers)
            else:
                place_predictive(area, c, known[c], preds, max_tiers)
        elif strategy == "B":
            e = obj
            if e.type == "rollover":
                for c in e.affected_cntrs:
                    known[c] = INF
                    if c in preds:
                        preds[c] = INF
            elif e.type == "weight_fix":
                upd = repredict(e.affected_cntrs)
                known.update(upd)
                preds.update({c: v for c, v in upd.items() if c in preds})
            take = min(per_event, budget - len(pm_log))
            if take > 0:
                for m in premarshal(area, preds, max_tiers, take):
                    m["when"] = e.time
                    pm_log.append(m)
    if strategy == "B" and budget - len(pm_log) > 0:   # 선적 전 유휴시간
        for m in premarshal(area, preds, max_tiers, budget - len(pm_log)):
            m["when"] = "pre-load"
            pm_log.append(m)

    loaded = boxes[~boxes.rolled]
    true_seq = dict(zip(loaded.cntr_no, loaded.true_load_seq))
    n, log = count_relocations(area, true_seq, max_tiers, return_log=True)
    return {"strategy": strategy, "area": area, "relocations": n, "reloc_log": log,
            "premarshal": len(pm_log), "premarshal_log": pm_log, "preds": preds,
            "n_loaded": len(loaded)}
