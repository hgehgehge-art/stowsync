"""다조건 실험(docs/multiseed.csv) 요약. tools/multiseed.py가 만든 결과를 화면에서 읽기만 합니다.

같은 시드(같은 도착 사건)끼리 예약 기반(A)과 ETA + 선작업(C)을 짝지어 비교합니다.
점유율 0.65는 야드 포화로 미완료가 많아 비교에서 제외합니다(docs/수치_점검_보고.md 참고).
"""
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

SRC = Path(__file__).resolve().parents[1] / 'docs' / 'multiseed.csv'
COMPARED_OCCUPANCY = (0.35, 0.5)
METRICS = (('truck_wait_mean_s', '평균 트럭 대기', 60, '분'),
           ('retrieval_delay_mean_s', '평균 본선 인출 지연', 60, '분'),
           ('extra_moves', '총 추가 이동(재취급 + 선작업)', 1, '회'))


def summarize(path=SRC):
    if not Path(path).exists():
        return None
    runs = defaultdict(dict)
    for r in csv.DictReader(open(path, encoding='utf8')):
        runs[(float(r['occupancy']), int(r['eta_error_s']), int(r['seed']))][r['policy']] = r
    pairs = [v for (occ, _, _), v in runs.items() if occ in COMPARED_OCCUPANCY and 'A' in v and 'C' in v]
    if not pairs:
        return None
    out = {'conditions': len(pairs), 'rows': [],
           'premarshal_mean': mean(float(v['C']['premarshal']) for v in pairs),
           'seeds': len({k[2] for k in runs}), 'errors_min': sorted({k[1] // 60 for k in runs}),
           'occupancy': COMPARED_OCCUPANCY}
    for key, label, scale, unit in METRICS:
        a = [float(v['A'][key]) / scale for v in pairs]; c = [float(v['C'][key]) / scale for v in pairs]
        d = [y - x for x, y in zip(a, c)]
        out['rows'].append({'label': label, 'unit': unit, 'a': mean(a), 'c': mean(c),
                            'pct': (mean(c) - mean(a)) / mean(a) * 100 if mean(a) else 0.0,
                            'less': sum(x < -1e-9 for x in d), 'same': sum(abs(x) <= 1e-9 for x in d),
                            'more': sum(x > 1e-9 for x in d)})
    return out
