"""하차 대기 트럭의 처리 순서 추천.

기존 추천 구조(제약 기반 후보 + 표본 기반 롤아웃, 비용 J = E + 0.5T + 2D + 60B)를 그대로 쓰고,
'어떤 순서로 내릴지'를 한 층 더 얹습니다.

- 대상: 같은 블록의 하차 대기 트럭 + 곧(WINDOW 안) 도착할 트럭, 최대 MAX_ITEMS개
- 후보: 대상의 순열. 각 순서대로 내리되 위치는 롤아웃의 탐욕 기본 정책으로 정함
- 평가: 모든 순열에 같은 도착 표본(공통 난수)을 쓰고, 순서대로 하차한 뒤 나머지는 기존 rollout()으로 60분 진행
- 선택: 평균 J가 낮은 상위 3개(동률은 이동 시간 → 이름순). 화면에는 J 대신 E·T·D(분)와 재취급 횟수를 보여 줌
- 기준: 도착순(+ 대표 컨테이너는 기존 계획 위치)도 같은 표본으로 평가
"""
from copy import copy, deepcopy
from itertools import permutations
from statistics import mean
import time
from engine.yard import feasible, duration, rank, locate
from services.eta import sample_arrivals, sample_seed
from services.recommend import rollout, recommend_slots
from domain.models import stable_hash, slot

MAX_ITEMS = 5          # 순열로 평가할 최대 트럭 수(넘으면 대기 시간이 긴 순 5대만)
WINDOW = 1800          # 지금부터 30분 안에 도착할 트럭까지 대상
TWO_STAGE_FROM = 4     # 이 수 이상이면 2단계(빠른 선별 → 상위 정밀 평가)
SCREEN_SAMPLES = 2
REFINE_TOP = 10
SWITCH_MARGIN = 30.0   # 이전 1위를 바꾸려면 점수(J) 차이가 이 값 이상이어야 함(가정값)
WEIGHTS = {'T': .5, 'D': 2., 'B': 60.}


# ── 대상 ───────────────────────────────────────────────
def queue_items(sim, block, now=None):
    """하차 대기 + 곧 도착할 트럭. 반환: [{'cid','arrival','eta','arrived'}] 대기 시간이 긴 순."""
    now = sim.now if now is None else now
    out = []
    for cid, at in sim.yard_arrivals.items():
        if sim.bundle.containers[cid].block == block:
            out.append({'cid': cid, 'arrival': at, 'eta': None, 'arrived': True})
    for cid, s in sim.statuses.items():
        c = sim.bundle.containers[cid]
        if c.block != block or s not in ('EN_ROUTE', 'GATE_QUEUE', 'GATE_SERVICE', 'INTERNAL_TRAVEL'):
            continue
        if cid not in sim.manual_ids:
            continue
        f = sim.forecasts.get(cid)
        lag = sim.config.gate_service + sim.config.internal_travel
        if s == 'EN_ROUTE':
            if f is None or f.p50 + lag > now + WINDOW:
                continue
            out.append({'cid': cid, 'arrival': f.p50 + lag, 'eta': f, 'arrived': False})
        else:
            t = sim.trucks.get(cid, {}).get('gate_arrival', now)
            out.append({'cid': cid, 'arrival': t + lag, 'eta': f, 'arrived': False})
    out.sort(key=lambda x: (x['arrival'], x['cid']))
    return out


# ── 한 순서의 롤아웃 ──────────────────────────────────
def _greedy_slot(o, yard, cid):
    o3 = copy(o); o3.yard = yard
    keys = feasible(o3, cid, None)
    if not keys:
        return None
    return min(keys, key=lambda k: (sum(rank(o.plan, x) < rank(o.plan, cid) for x in yard[k]), len(yard[k]), k))


def place_in_order(o, order, arrivals, fixed=None):
    """순서대로 하차할 때의 위치·시각. 크레인은 한 대(블록)씩 순서를 지킵니다.
    fixed: {cid: 스택} 위치를 미리 정한 화물(예: 기존 계획)."""
    yard = {k: list(v) for k, v in o.yard.items()}
    b = o.containers[order[0]].block
    free = max(o.now, o.crane_busy_until.get(b, o.now))
    placed, wait, move = [], 0., 0.
    for cid in order:
        arr = arrivals.get(cid, o.now)
        start = max(free, arr)
        dst = (fixed or {}).get(cid)
        if dst is None or len(yard.get(dst, [])) >= 4:
            dst = _greedy_slot(o, yard, cid)
        if dst is None:
            placed.append((cid, None, start)); continue
        dt = duration(o.config, None, dst)
        yard[dst].append(cid)
        wait += start - arr
        move += dt
        free = start + dt
        placed.append((cid, dst, start))
    return yard, free, wait, move, placed


def evaluate_order(o, order, samples, fixed=None, weights=WEIGHTS):
    """순서 하나를 표본마다 롤아웃. 반환: 표본별 (E초, T초, D초, B쌍, 재취급수)와 위치."""
    comps = []
    positions = None
    b = o.containers[order[0]].block
    for w in samples:
        yard, free, wait0, move, placed = place_in_order(o, order, w, fixed)
        if positions is None:
            positions = placed
        o2 = copy(o)
        o2.yard = yard
        o2.crane_busy_until = dict(o.crane_busy_until); o2.crane_busy_until[b] = free
        o2.yard_arrivals = {k: v for k, v in o.yard_arrivals.items() if k not in order}
        rest = {k: v for k, v in w.items() if k not in order}
        extra, half_wait, double_delay, pairs60, reh, pm = rollout(o2, rest, counts=True)
        comps.append((extra, half_wait / .5 + wait0, double_delay / 2, pairs60 / 60, reh))
    return comps, positions


def score(comps, weights=WEIGHTS):
    return mean(e + weights['T'] * t + weights['D'] * d + weights['B'] * bp for e, t, d, bp, _ in comps)


# ── 추천 ───────────────────────────────────────────────
_CACHE = {}


def cache_key(sim, block):
    o = sim.observe()
    return stable_hash([block, sample_seed(o), sim.yard_version, sim.plan_version])


def recommend_order(sim, block, fixed_baseline=None, prev_top=None, margin=SWITCH_MARGIN):
    """처리 순서 상위 3개와 기준(도착순)을 같은 표본으로 평가합니다. 입력이 같으면 캐시를 씁니다."""
    key = cache_key(sim, block) + stable_hash([fixed_baseline, prev_top, margin])
    if key in _CACHE:
        return _CACHE[key]
    t0 = time.perf_counter()
    o = sim.observe()
    items = queue_items(sim, block)
    if not items:
        res = {'items': [], 'options': [], 'baseline': None, 'ms': 0, 'note': '처리 순서를 정할 대기 트럭이 없습니다.'}
        _CACHE[key] = res
        return res
    head, tail = items[:MAX_ITEMS], items[MAX_ITEMS:]
    samples = sample_arrivals(o, 'C')
    arrivals_fix = {it['cid']: it['arrival'] for it in items if it['arrived']}
    for w in samples:
        w.update(arrivals_fix)
    tail_ids = [it['cid'] for it in tail]
    perms = [list(p) + tail_ids for p in permutations([it['cid'] for it in head])]
    if len(head) >= TWO_STAGE_FROM:
        screen = sorted(perms, key=lambda p: score(evaluate_order(o, p, samples[:SCREEN_SAMPLES])[0]))
        perms = screen[:REFINE_TOP]
    evals = []
    for p in perms:
        comps, pos = evaluate_order(o, p, samples)
        evals.append({'order': p, 'comps': comps, 'positions': pos, 'J': score(comps),
                      'move': sum(duration(o.config, None, d) for _, d, _ in pos if d)})
    evals.sort(key=lambda e: (round(e['J'], 6), e['move'], '>'.join(e['order'])))
    base_order = [it['cid'] for it in items]
    bcomps, bpos = evaluate_order(o, base_order, samples, fixed_baseline)
    baseline = {'order': base_order, 'comps': bcomps, 'positions': bpos, 'J': score(bcomps)}
    top = evals[:3]
    switched = None
    if prev_top and top and prev_top != top[0]['order']:
        prev = next((e for e in evals if e['order'] == prev_top), None)
        if prev and prev['J'] - top[0]['J'] < margin:
            top = [prev] + [e for e in top if e is not prev][:2]
        elif prev:
            switched = {'from': prev_top, 'to': top[0]['order'], 'gain': prev['J'] - top[0]['J']}
    res = {'items': items, 'options': top, 'baseline': baseline, 'samples': len(samples), 'switched': switched,
           'ms': round((time.perf_counter() - t0) * 1000), 'limited': len(tail) > 0, 'all': evals}
    _CACHE[key] = res
    return res


# ── 화면용 통계 ────────────────────────────────────────
def minutes_delta(option, baseline):
    """기준 대비 E·T·D(분) 차이의 평균과 표본별 범위, 재취급 차이."""
    out = {}
    for i, name in enumerate(('E', 'T', 'D')):
        diffs = [(a[i] - b[i]) / 60 for a, b in zip(option['comps'], baseline['comps'])]
        out[name] = (mean(diffs), min(diffs), max(diffs))
    tot = [((a[0] + a[1] + a[2]) - (b[0] + b[1] + b[2])) / 60 for a, b in zip(option['comps'], baseline['comps'])]
    out['total'] = (mean(tot), min(tot), max(tot))
    out['rehandles'] = (mean(c[4] for c in option['comps']), mean(c[4] for c in baseline['comps']))
    return out


def vessel_status(sim, vessel_id, now=None):
    now = sim.now if now is None else now
    entries = [p for cid, p in sim.plan.items() if sim.bundle.containers[cid].vessel_id == vessel_id]
    remaining = [p for p in entries if sim.statuses.get(p.container_id) not in ('RETRIEVED', 'EXCEPTION_LATE')]
    if entries and not remaining:
        return '작업 종료', None
    if not entries:
        return '미정', None
    first = min(p.due for p in entries)          # 선박의 첫 인출 예정 = 작업 시작
    if first <= now:
        return '작업중', 0
    return '입항 전', round((first - now) / 60)


def reasons(sim, option, baseline):
    """롤아웃 결과(첫 표본의 하차 시각·위치)와 선박 상태에서 화물별 사유를 만듭니다. 고정 문장이 아닙니다."""
    o = sim.observe()
    lines = []
    base_pos = {c: i for i, c in enumerate(baseline['order'])}
    base_place = {c: (d, t) for c, d, t in baseline['positions']}
    for i, (cid, dst, start) in enumerate(option['positions']):
        c = sim.bundle.containers[cid]
        st, mins = vessel_status(sim, c.vessel_id)
        due_min = round((sim.plan[cid].due - sim.now) / 60)
        if st == '작업중':
            vtxt = f'{c.vessel_id} 작업중 · 이 화물 인출 예정 {max(due_min, 0)}분 후'
        elif st == '입항 전':
            vtxt = f'{c.vessel_id} 작업 시작 {mins}분 후 · 이 화물 인출 예정 {due_min}분 후'
        elif st == '작업 종료':
            vtxt = f'{c.vessel_id} 작업 종료'
        else:
            vtxt = f'{c.vessel_id} 일정 미정'
        earlier_below = sum(rank(o.plan, x) < rank(o.plan, cid) for x in o.yard.get(dst, [])) if dst else 0
        bd, bt = base_place.get(cid, (None, None))
        shift = (start - bt) / 60 if bt is not None else 0
        facts = [f'{i + 1}번째 하차(도착순 {base_pos[cid] + 1}번째)', f'하차 시작 {shift:+.1f}분']
        if dst:
            facts.append(f'위치 {dst}' + (f' · 아래에 먼저 실을 화물 {earlier_below}개' if earlier_below else ' · 먼저 실을 화물을 덮지 않음'))
        if bd and bd != dst:
            b_below = sum(rank(o.plan, x) < rank(o.plan, cid) for x in o.yard.get(bd, []))
            facts.append(f'도착순이면 {bd}' + (f'(먼저 실을 화물 {b_below}개 위)' if b_below else ''))
        lines.append({'cid': cid, 'vessel': vtxt, 'why': ' · '.join(facts)})
    return lines


# ── 민감도 ─────────────────────────────────────────────
def sensitivity(sim, block, fixed_baseline=None, T=(.25, .5, 1.), D=(1., 2., 4.), B=(30., 60., 120.), S=(8, 16, 32)):
    """가중치·표본 수 격자에서 기본 1위 순서가 유지되는 비율. 대상은 기본 평가의 상위 10개 순서."""
    t0 = time.perf_counter()
    base = recommend_order(sim, block, fixed_baseline)
    if not base['options']:
        return {'total': 0, 'same': 0, 'changes': [], 'ms': 0}
    top_order = base['options'][0]['order']
    orders = [e['order'] for e in base['all'][:REFINE_TOP]]
    o = sim.observe()
    arrivals_fix = {it['cid']: it['arrival'] for it in base['items'] if it['arrived']}
    comps_by_s = {}
    for s in S:
        o2 = copy(o); o2.config = o.config.model_copy(update={'samples': s})
        samples = sample_arrivals(o2, 'C')
        for w in samples:
            w.update(arrivals_fix)
        comps_by_s[s] = {tuple(p): evaluate_order(o, p, samples)[0] for p in orders}
    total = same = 0
    changes = []
    for s in S:
        for t in T:
            for d in D:
                for b in B:
                    w = {'T': t, 'D': d, 'B': b}
                    best = min(orders, key=lambda p: (round(score(comps_by_s[s][tuple(p)], w), 6), '>'.join(p)))
                    total += 1
                    if best == top_order:
                        same += 1
                    else:
                        changes.append({'S': s, 'T': t, 'D': d, 'B': b, 'top': best})
    return {'total': total, 'same': same, 'changes': changes, 'ms': round((time.perf_counter() - t0) * 1000), 'top': top_order}


# ── 이벤트 주입 ────────────────────────────────────────
def inject_truck_delay(sim, cid, minutes):
    """운송 중 트럭의 실제 도착과 최신 ETA를 minutes만큼 늦춥니다(시연용 지연 이벤트)."""
    import heapq
    from domain.models import Forecast
    shift = int(minutes * 60)
    q = []
    for at, pr, eid, kind, p in sim.queue:
        if kind == 'TRUCK_ARRIVAL' and p.get('container_id') == cid:
            at += shift
        if kind == 'FORECAST_UPDATE' and p['forecast'].container_id == cid:
            continue
        q.append((at, pr, eid, kind, p))
    heapq.heapify(q)
    sim.queue = q
    f = sim.forecasts.get(cid)
    if f:
        nf = Forecast(f'INJECT-{cid}-{sim.now}', sim.now, cid, f.p10 + shift, f.p50 + shift, f.p90 + shift, 'demo_injected', f.trust_score)
        sim.forecasts[cid] = nf
        sim.eta_overrides.add(cid)
        sim.forecast_log.setdefault(cid, []).append(nf)
    sim.yard_version += 1
    sim.log('INJECTED_DELAY', cid, f'트럭 {minutes}분 지연(시연용 주입)')
