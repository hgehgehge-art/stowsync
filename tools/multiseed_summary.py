"""docs/multiseed.csv → 조건별 요약(마크다운 표). 차이는 같은 시드(같은 사건)끼리 짝지어 계산합니다."""
import csv, sys
from collections import defaultdict
from statistics import mean
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'docs' / 'multiseed.csv'


def load():
    d = defaultdict(dict)
    for r in csv.DictReader(SRC.open()):
        d[(float(r['occupancy']), int(r['eta_error_s']), int(r['seed']))][r['policy']] = {k: float(v) for k, v in r.items() if k not in ('policy',)}
    return d


def table(d, other, metric='extra_moves', scale=1):
    conds = sorted({(o, e) for o, e, _ in d})
    out = [f'| 점유율 | ETA 오차 | 예약 기반 평균 | 비교 정책 평균 | 차이 평균(범위) | 줄어든 시드 | 같음 | 늘어난 시드 |', '|---|---|---:|---:|---:|---:|---:|---:|']
    tot = [0, 0, 0]
    for o, e in conds:
        rows = [v for (oo, ee, s), v in d.items() if (oo, ee) == (o, e)]
        a = [r['A'][metric] / scale for r in rows]; b = [r[other][metric] / scale for r in rows]
        diff = [y - x for x, y in zip(a, b)]
        less = sum(x < -1e-9 for x in diff); same = sum(abs(x) <= 1e-9 for x in diff); more = sum(x > 1e-9 for x in diff)
        tot = [tot[0] + less, tot[1] + same, tot[2] + more]
        out.append(f'| {o:.2f} | {e // 60}분 | {mean(a):.1f} | {mean(b):.1f} | {mean(diff):+.1f} ({min(diff):+.0f}~{max(diff):+.0f}) | {less} | {same} | {more} |')
    out.append(f'| 합계 | | | | | {tot[0]} | {tot[1]} | {tot[2]} |')
    return '\n'.join(out)


if __name__ == '__main__':
    d = load()
    for other, name in (('C', 'ETA + 선작업(C) vs 예약 기반(A)'), ('B', 'ETA 기반(B) vs 예약 기반(A)')):
        print(f'### 총 추가 이동 · {name}\n'); print(table(d, other)); print()
    for other, name in (('C', 'C vs A'),):
        print(f'### 평균 트럭 대기(분) · {name}\n'); print(table(d, other, 'truck_wait_mean_s', 60)); print()
        print(f'### 평균 인출 지연(분) · {name}\n'); print(table(d, other, 'retrieval_delay_mean_s', 60)); print()
