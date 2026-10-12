"""params.yaml 로더."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PARAMS_PATH = ROOT / "config" / "params.yaml"


def load_params(path: Path = PARAMS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def with_overrides(params: dict, total_boxes: int | None = None, max_tiers: int | None = None,
                   change_ratio: float | None = None) -> dict:
    """실험실 슬라이더 값으로 덮어쓴 사본."""
    p = copy.deepcopy(params)
    if total_boxes is not None:
        base = p["vessels"]["boxes"]
        s = sum(base)
        p["vessels"]["boxes"] = [max(10, round(total_boxes * b / s)) for b in base]
    if max_tiers is not None:
        p["yard"]["max_tiers"] = int(max_tiers)
    if change_ratio is not None:
        p["events"]["change_ratio"] = float(change_ratio)
    return p
