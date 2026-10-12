"""재조작 계산 단위 테스트 — 3×3(스택 3개, 최대 3단) 예제를 손으로 계산한 값과 비교.

규칙 (SPEC 5.4):
  1. load_seq 오름차순으로 꺼낸다.
  2. 대상 위의 박스는 같은 베이 다른 스택으로 하나씩 옮기고 1회로 센다.
  3. 목적지: '스택 최소 load_seq > 옮기는 박스 seq' 인 스택 중 가장 낮은 스택(동률이면 왼쪽),
     없으면 가장 낮은 스택(동률이면 왼쪽). 최대 단 수 준수.
"""
import math

import pytest

from core.relocation import count_relocations, blocking_count


def _bay(*stacks):
    # 박스 ID를 선적 순서 숫자 그대로 쓴다: "3" → seq 3
    return {0: [[str(b) for b in s] for s in stacks]}


def _seq(bays):
    return {b: int(b) for st in bays[0] for b in st}


def test_example1_well_ordered_no_relocation():
    # 각 스택이 위에서부터 먼저 실리는 순서 → 재조작 0
    bays = _bay([3, 2, 1], [6, 5, 4], [9, 8, 7])
    assert count_relocations(bays, _seq(bays), max_tiers=3) == 0


def test_example2_single_blocker():
    # [1,2] [3] [] : 1을 꺼내려면 2를 옮김 → 후보(최소>2): 스택1(h1), 스택2(빈,h0) → 스택2. 총 1
    bays = _bay([1, 2], [3], [])
    n, log = count_relocations(bays, _seq(bays), max_tiers=3, return_log=True)
    assert n == 1
    assert log[0]["box"] == "2" and log[0]["to_stack"] == 2


def test_example3_full_stack_and_tie_break():
    # [1,2,3] [4,5,6] [] → 손계산 4회
    #  1 꺼내기: 3→스택2(빈), 2→스택2(최소3>2) / 4 꺼내기: 6→스택0(빈, 동률 왼쪽), 5→스택2(빈, 더 낮음)
    bays = _bay([1, 2, 3], [4, 5, 6], [])
    n, log = count_relocations(bays, _seq(bays), max_tiers=3, return_log=True)
    assert n == 4
    assert [(e["box"], e["to_stack"]) for e in log] == [("3", 2), ("2", 2), ("6", 0), ("5", 2)]


def test_example4_no_good_stack_falls_back_to_lowest():
    # [1,5] [2,4] [3] → 손계산 3회
    #  1: 5 → 좋은 스택 없음 → 가장 낮은 스택2 / 2: 4 → 스택0(빈) / 3: 5 → 스택1(빈)
    bays = _bay([1, 5], [2, 4], [3])
    n, log = count_relocations(bays, _seq(bays), max_tiers=3, return_log=True)
    assert n == 3
    assert [(e["box"], e["to_stack"]) for e in log] == [("5", 2), ("4", 0), ("5", 1)]


def test_rolled_box_not_loaded_but_blocks():
    # 'R' 은 롤오버(선적 안 함) — 꺼내지 않지만 위에 있으면 방해 박스
    bays = {0: [["1", "R"], ["2"], []]}
    seq = {"1": 1, "2": 2}
    assert count_relocations(bays, seq, max_tiers=3) == 1


def test_input_not_mutated_and_deterministic():
    bays = _bay([1, 2, 3], [4, 5, 6], [])
    snapshot = [list(s) for s in bays[0]]
    a = count_relocations(bays, _seq(bays), max_tiers=3)
    b = count_relocations(bays, _seq(bays), max_tiers=3)
    assert a == b == 4
    assert bays[0] == snapshot


def test_tier_limit_respected():
    bays = _bay([1, 2, 3], [4, 5, 6], [])
    _, log = count_relocations(bays, _seq(bays), max_tiers=3, return_log=True)
    # 시뮬레이션 내내 스택 높이가 3을 넘지 않았는지 로그의 높이로 확인
    assert all(e["to_height"] <= 3 for e in log)


def test_blocking_count():
    assert blocking_count([["1", "2"], ["3"]], {"1": 1, "2": 2, "3": 3}) == 1
    assert blocking_count([["2", "1"]], {"1": 1, "2": 2}) == 0
    assert blocking_count([["1", "R"]], {"1": 1}) == 1
    assert math.isinf(float("inf"))
