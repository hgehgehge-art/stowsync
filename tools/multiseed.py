"""정책 비교 다조건 실험: 시드 20개 × 초기 점유율 3 × ETA 오차 3, 기능 시연 설정(40개).

실행: python tools/multiseed.py  →  docs/multiseed.csv
한 번 실행 결과(시드 7 하나)가 표본에 따라 뒤집히므로, 정책 차이를 조건별 분포로 확인하기 위한 도구입니다.
"""
import csv, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domain.models import Config
from adapters.mock import build_scenario
from engine.simulator import run_simulation

SEEDS = range(20)
OCC = (.35, .5, .65)
ETA_ERR = (300, 600, 1200)
OUT = Path(__file__).resolve().parents[1] / 'docs' / 'multiseed.csv'


def main():
    t0 = time.time()
    rows = []
    for occ in OCC:
        for err in ETA_ERR:
            for seed in SEEDS:
                cfg = Config(target_count=40, occupancy=occ, eta_error=err, seed=seed)
                b = build_scenario(cfg)
                for p in 'ABC':
                    m = run_simulation(b, p).metrics
                    rows.append({'occupancy': occ, 'eta_error_s': err, 'seed': seed, 'policy': p,
                                 'rehandle': m['REHANDLE'], 'premarshal': m['PREMARSH'], 'extra_moves': m['extra_moves'],
                                 'truck_wait_mean_s': round(m['truck_wait']['mean'] or 0, 1),
                                 'retrieval_delay_mean_s': round(m['retrieval_delay']['mean'] or 0, 1),
                                 'incomplete': m['incomplete'], 'exceptions': m['exceptions']})
            print(f'occ {occ} err {err} done {time.time() - t0:.0f}s', flush=True)
    with OUT.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print('saved', OUT, len(rows), f'{time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
