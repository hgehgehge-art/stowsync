"""BRLP 벤치마크 파서 — SPEC 5.6.

출처: Jovanovic et al. (2016), https://mail.ipb.ac.rs/~rakaj/brlp/brlp.htm
데이터셋 페이지 설명 기준 형식 (실제 파일로 다시 확인할 것):
    Number Of Containers, N
    Number Of Yard Stacks, YS
    MaxTier of Yard Stacks, YT
    Number of Vessel Stacks, NVS
    (NVS개의 선박 스택별 최대 단)
    Yard Bay
    Stack 0:
    B_3 B_1 C_1 A_0          ← 아래 → 위, ID = 선박스택_선박단
레이블 문구가 조금 달라도 읽히도록, 'Yard Bay' 앞의 정수를 순서대로 읽는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.relocation import blocking_count, count_relocations
from core.stacking import premarshal

_INT = re.compile(r"-?\d+")
_BOX = re.compile(r"[A-Za-z]+_\d+")
_STACK = re.compile(r"^\s*stack\s*\d*\s*:?", re.I)


@dataclass
class BRLPInstance:
    name: str
    n_containers: int
    yard_stacks: int
    max_tier: int
    vessel_stacks: int
    vessel_tiers: list[int]
    stacks: list[list[str]]          # 아래 → 위

    def load_order(self) -> dict[str, int]:
        """선박 스택은 아래 단부터 채워야 하므로 (선박단, 선박스택) 순서로 고정한 적재 순서 (단순화 가정)."""
        boxes = [b for s in self.stacks for b in s]

        def key(b):
            st, tier = b.split("_")
            return int(tier), st
        return {b: i + 1 for i, b in enumerate(sorted(boxes, key=key))}


def parse_brlp(text: str, name: str = "instance") -> BRLPInstance:
    lines = text.splitlines()
    yb = next((i for i, l in enumerate(lines) if "yard bay" in l.lower()), None)
    if yb is None:
        raise ValueError("'Yard Bay' 줄을 찾지 못했습니다 — 파일 형식을 확인하세요.")
    nums = [int(x) for l in lines[:yb] for x in _INT.findall(l)]
    if len(nums) < 4:
        raise ValueError("헤더 숫자(컨테이너 수, 야드 스택 수, 최대 단, 선박 스택 수)를 읽지 못했습니다.")
    n, ys, yt, nvs = nums[:4]
    vt = nums[4:4 + nvs]
    stacks: list[list[str]] = []
    cur = None
    for l in lines[yb + 1:]:
        if _STACK.match(l):
            cur = []
            stacks.append(cur)
            l = _STACK.sub("", l, count=1)
        if cur is not None:
            cur.extend(_BOX.findall(l))
    while len(stacks) < ys:
        stacks.append([])
    found = sum(len(s) for s in stacks)
    if found != n:
        raise ValueError(f"컨테이너 수 불일치: 헤더 {n}개, 읽은 박스 {found}개")
    return BRLPInstance(name, n, ys, yt, nvs, vt, stacks)


def load_dir(path: Path) -> list[BRLPInstance]:
    out = []
    for p in sorted(path.rglob("*")):
        if p.suffix.lower() in (".pro", ".txt") and p.is_file():
            try:
                out.append(parse_brlp(p.read_text(errors="ignore"), p.name))
            except ValueError:
                continue
    return out


def evaluate(inst: BRLPInstance, budget: int) -> dict:
    seq = inst.load_order()
    bay = {0: [list(s) for s in inst.stacks]}
    lb = blocking_count(bay[0], seq)
    base = count_relocations(bay, seq, inst.max_tier)
    moves = premarshal(bay, {k: float(v) for k, v in seq.items()}, inst.max_tier, budget)
    after = count_relocations(bay, seq, inst.max_tier)
    return {"instance": inst.name, "containers": inst.n_containers, "yard_stacks": inst.yard_stacks,
            "max_tier": inst.max_tier, "lower_bound": lb, "relocations_rule": base,
            "premarshal_moves": len(moves), "relocations_after_premarshal": after,
            "total_moves_B": len(moves) + after}
