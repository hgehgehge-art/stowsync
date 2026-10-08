"""재조작(리핸들링) 횟수 계산 — SPEC 5.4.

야드 표현:
    bays: {bay_key: [stack0, stack1, ...]}, 각 stack 은 아래→위 순서의 박스 ID 리스트
    load_seq: {box_id: 선적 순서(작을수록 먼저)}. 없는 박스(롤오버 등)는 선적하지 않음(= +inf).
"""
from __future__ import annotations

import math
from typing import Hashable

INF = math.inf


def _seq(load_seq: dict, box: str) -> float:
    v = load_seq.get(box)
    return INF if v is None or (isinstance(v, float) and math.isnan(v)) else v


def stack_min(stack: list[str], load_seq: dict) -> float:
    return min((_seq(load_seq, b) for b in stack), default=INF)


def choose_destination(stacks: list[list[str]], src: int, s: float, load_seq: dict, max_tiers: int):
    """옮길 스택 선택. 우선: 스택 최소 seq > s 인 곳 중 가장 낮은 스택, 없으면 가장 낮은 스택. 동률은 왼쪽."""
    cands = [j for j, st in enumerate(stacks) if j != src and len(st) < max_tiers]
    if not cands:
        return None
    good = [j for j in cands if stack_min(stacks[j], load_seq) > s]
    pool = good or cands
    return min(pool, key=lambda j: (len(stacks[j]), j))


def count_relocations(bays: dict[Hashable, list[list[str]]], load_seq: dict, max_tiers: int,
                      return_log: bool = False):
    """load_seq 순서대로 박스를 꺼내며 재조작 횟수를 센다. 입력은 변경하지 않는다."""
    work = {k: [list(s) for s in v] for k, v in bays.items()}
    loc = {b: (k, i) for k, stacks in work.items() for i, st in enumerate(stacks) for b in st}
    order = sorted((b for b in loc if _seq(load_seq, b) < INF), key=lambda b: (_seq(load_seq, b), b))
    n, log = 0, []
    for box in order:
        k, i = loc[box]
        st = work[k][i]
        while st[-1] != box:
            top = st.pop()
            dk, j = k, choose_destination(work[k], i, _seq(load_seq, top), load_seq, max_tiers)
            if j is None:  # 같은 베이가 꽉 참 → 다른 베이로 (드문 경우)
                for ok, ostacks in work.items():
                    if ok == k:
                        continue
                    j = choose_destination(ostacks, -1, _seq(load_seq, top), load_seq, max_tiers)
                    if j is not None:
                        dk = ok
                        break
            if j is None:
                raise RuntimeError("야드에 옮길 공간이 없습니다 (단 수 / 여유 용량 확인)")
            work[dk][j].append(top)
            loc[top] = (dk, j)
            n += 1
            log.append({"box": top, "for": box, "bay": k, "from_stack": i, "to_bay": dk,
                        "to_stack": j, "to_height": len(work[dk][j])})
        st.pop()
        del loc[box]
    return (n, log) if return_log else n


def blocking_count(stacks: list[list[str]], load_seq: dict) -> int:
    """하한 지표: 아래에 더 먼저 실릴 박스가 있는 박스 수 (각 박스는 최소 1회 옮겨야 함)."""
    n = 0
    for st in stacks:
        running = INF
        for b in st:
            s = _seq(load_seq, b)
            if s > running:
                n += 1
            running = min(running, s)
    return n


def blockers_above(stack: list[str], idx: int, load_seq: dict) -> int:
    """stack[idx] 박스 위에 쌓인 '방해 박스' 수 (자신보다 늦게 실리거나 선적되지 않는 박스)."""
    s = _seq(load_seq, stack[idx])
    return sum(1 for b in stack[idx + 1:] if _seq(load_seq, b) > s)
