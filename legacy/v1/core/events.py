"""계획 변경 이벤트 (롤오버 / 막판 부킹 추가 / VGM 중량 수정) — SPEC 5.1, 5.3.

- 시나리오 생성 시 선박별 이벤트를 만든다 (plan_events).
- 계획 동기화 보드의 '버튼 이벤트'도 같은 규칙으로 만든다 (live_*).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

EVENT_LABEL = {"rollover": "롤오버", "add": "막판 부킹 추가", "weight_fix": "VGM 중량 수정"}


@dataclass
class PlanEvent:
    time: datetime
    type: str                      # rollover / add / weight_fix
    vessel_id: str
    affected_cntrs: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def label(self) -> str:
        return EVENT_LABEL[self.type]


def split_counts(n_boxes: int, params: dict) -> dict[str, int]:
    ev = params["events"]
    total = int(round(n_boxes * ev["change_ratio"]))
    out = {k: int(round(total * v)) for k, v in ev["shares"].items()}
    return out


def plan_events(rng: np.random.Generator, vessel, df: pd.DataFrame, params: dict, make_boxes) -> tuple[pd.DataFrame, list[PlanEvent]]:
    """선박 하나의 박스 표에 이벤트를 적용하고 (수정된 표, 이벤트 목록)을 돌려준다.

    make_boxes(rng, n, vessel, arrival_window) → 새 박스 DataFrame (막판 부킹용)
    """
    counts = split_counts(len(df), params)
    lo, hi = params["events"]["window_hours"]
    c = params["containers"]
    wmin, wmax = c["weight_clip"]
    events: list[PlanEvent] = []

    # VGM 중량 수정: 이미 반입된 박스 중 일부의 신고중량이 크게 틀렸음이 드러남
    if counts["weight_fix"] > 0:
        t = vessel.cutoff - timedelta(hours=float(rng.uniform(lo + 3, hi)))
        pool = df.index[df.arrival_time < t]
        k = min(counts["weight_fix"], len(pool))
        if k:
            idx = rng.choice(pool, size=k, replace=False)
            sign = rng.choice([-1, 1], size=k)
            err = rng.uniform(*c["weight_fix_error"], size=k)
            df.loc[idx, "declared_weight"] = np.clip(df.loc[idx, "vgm_weight"] + sign * err, wmin, wmax).round(1)
            df.loc[idx, "weight_fixed"] = True
            ids = df.loc[idx, "cntr_no"].tolist()
            events.append(PlanEvent(t, "weight_fix", vessel.vessel_id, ids,
                                    f"VGM 재측정 {k}개 박스 중량 수정"))

    # 롤오버: 반입된 박스 일부가 다음 항차로 넘어감 (야드에는 남아 방해 박스가 됨)
    if counts["rollover"] > 0:
        t = vessel.cutoff - timedelta(hours=float(rng.uniform(lo, hi)))
        pool = df.index[(df.arrival_time < t) & (~df.rolled)]
        k = min(counts["rollover"], len(pool))
        if k:
            idx = rng.choice(pool, size=k, replace=False)
            df.loc[idx, "rolled"] = True
            ids = df.loc[idx, "cntr_no"].tolist()
            teu = int(df.loc[idx, "size"].sum() / 20)
            events.append(PlanEvent(t, "rollover", vessel.vessel_id, ids, f"롤오버 {teu}TEU"))

    # 막판 부킹 추가: 이벤트 이후 마감 전까지 새 박스 반입
    if counts["add"] > 0:
        t = vessel.cutoff - timedelta(hours=float(rng.uniform(lo, min(hi, lo + 8))))
        new = make_boxes(rng, counts["add"], vessel, (t, vessel.cutoff))
        new["late_add"] = True
        df = pd.concat([df, new], ignore_index=True)
        teu = int(new["size"].sum() / 20)
        events.append(PlanEvent(t, "add", vessel.vessel_id, new["cntr_no"].tolist(), f"막판 부킹 {teu}TEU 추가"))

    events.sort(key=lambda e: e.time)
    return df, events


def boxes_beneath(area: dict, cntrs, loadable: set) -> list[str]:
    """area 안에서 cntrs 박스들 아래에 깔린 '선적될' 박스 목록 = 이벤트 영향 박스."""
    target, out = set(cntrs), []
    for stacks in area.values():
        for st in stacks:
            hit = [i for i, b in enumerate(st) if b in target]
            if hit:
                top = max(hit)
                out += [b for b in st[:top] if b in loadable and b not in target]
    return list(dict.fromkeys(out))


# ── 계획 동기화 보드용 '버튼 이벤트' ─────────────────────────
def _resequence(boxes: pd.DataFrame, vessel_id: str, lr: dict) -> pd.DataFrame:
    from core.generator import assign_true_seq
    m = boxes.vessel_id == vessel_id
    sub = assign_true_seq(boxes[m], lr)
    boxes.loc[m, ["true_load_seq", "true_pct"]] = sub[["true_load_seq", "true_pct"]]
    return boxes


def apply_live_event(kind: str, L: dict, vessel, params: dict, predictor, rng: np.random.Generator,
                     now: datetime) -> dict:
    """세션 상태 L 에 이벤트를 적용하고 영향 요약을 돌려준다.

    L: {"boxes": DataFrame, "areas": {vid: {"current": area, "B": area}}, "preds": {cntr: pct}}
    """
    from core.relocation import count_relocations
    from core.stacking import place_current, place_predictive, weight_group_fixed

    boxes, lr = L["boxes"], params["load_rule"]
    vid, tiers = vessel.vessel_id, params["yard"]["max_tiers"]
    areas = L["areas"][vid]
    mine = boxes[(boxes.vessel_id == vid) & (~boxes.rolled)]

    def relocs():
        b = L["boxes"]
        ld = b[(b.vessel_id == vid) & (~b.rolled)]
        seq = dict(zip(ld.cntr_no, ld.true_pct))
        seq.update({u["cntr_no"]: u["pred_pct"] for u in L.get("user_boxes", []) if u["vessel_id"] == vid})
        return {k: count_relocations(a, seq, tiers) for k, a in areas.items()}

    before = relocs()
    c = params["containers"]
    if kind == "rollover":
        k = int(rng.integers(6, 11))
        ids = list(rng.choice(mine.cntr_no.to_numpy(), size=min(k, len(mine)), replace=False))
        boxes.loc[boxes.cntr_no.isin(ids), "rolled"] = True
        for i in ids:
            L["preds"][i] = float("inf")
        teu = int(boxes.loc[boxes.cntr_no.isin(ids), "size"].sum() / 20)
        note = f"롤오버 {teu}TEU"
    elif kind == "weight_fix":
        k = int(rng.integers(5, 9))
        ids = list(rng.choice(mine.cntr_no.to_numpy(), size=min(k, len(mine)), replace=False))
        m = boxes.cntr_no.isin(ids)
        sign = rng.choice([-1, 1], size=m.sum())
        boxes.loc[m, "vgm_weight"] = np.clip(boxes.loc[m, "declared_weight"] + sign * rng.uniform(*c["weight_fix_error"], m.sum()),
                                             *c["weight_clip"]).round(1)
        sub = boxes[m]
        upd = predictor.predict_batch(sub.pod_d, sub.vgm_weight, sub["size"], sub.is_dg)
        for cn, pp in zip(sub.cntr_no, upd.pred_pct):
            L["preds"][cn] = float(pp)
        note = f"VGM 재측정 {len(ids)}개 박스 중량 수정"
    elif kind == "add":
        n = int(rng.integers(4, 8))
        src = mine.sample(n=n, replace=True, random_state=int(rng.integers(1e9)))
        new = src.copy()
        base = len(boxes)
        new["cntr_no"] = [f"LATE{base + i:07d}" for i in range(n)]
        new["vgm_weight"] = np.clip(new.vgm_weight + rng.normal(0, 3, n), *c["weight_clip"]).round(1)
        new["declared_weight"] = new.vgm_weight
        new["load_noise"] = rng.normal(0, lr["noise"], n)
        new["arrival_time"] = pd.Timestamp(now)
        new["late_add"] = True
        pr = predictor.predict_batch(new.pod_d, new.declared_weight, new["size"], new.is_dg)
        new["pred_pct"] = pr.pred_pct.values
        new["weight_group"] = pr.weight_group.values
        L["boxes"] = boxes = pd.concat([boxes, new], ignore_index=True)
        keys = {}
        st = params["strategy"]
        info = boxes.set_index("cntr_no")
        for stacks in areas["current"].values():
            for s in stacks:
                for b in s:
                    if b in info.index:
                        keys[b] = (info.at[b, "pod"], weight_group_fixed(info.at[b, "declared_weight"], st["weight_groups"]))
        for _, r in new.iterrows():
            place_current(areas["current"], r.cntr_no, (r.pod, weight_group_fixed(r.declared_weight, st["weight_groups"])),
                          keys, tiers)
            place_predictive(areas["B"], r.cntr_no, float(r.pred_pct), L["preds"], tiers)
        ids = new.cntr_no.tolist()
        teu = int(new["size"].sum() / 20)
        note = f"막판 부킹 {teu}TEU 추가"
    else:
        raise ValueError(kind)

    _resequence(L["boxes"], vid, lr)
    after = relocs()
    loadable = set(L["boxes"].cntr_no[~L["boxes"].rolled])
    ev = PlanEvent(now, kind, vid, ids, note)
    return {"event": ev, "before": before, "after": after,
            "affected_current": boxes_beneath(areas["current"], ids, loadable),
            "affected_B": boxes_beneath(areas["B"], ids, loadable)}
