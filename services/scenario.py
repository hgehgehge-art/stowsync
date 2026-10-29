"""대표 시나리오의 대안 실행 시뮬레이션.

같은 초기 상태(결정 직전 시뮬레이터)를 복제해 대안마다 처리 순서·위치 계획을 실제 이벤트 규칙으로 실행합니다.
화면의 예상 작업시간·절감시간은 모두 이 실행 결과에서 계산하며, 고정 숫자를 쓰지 않습니다.
"""
from copy import deepcopy
from engine.yard import locate
from services import sequence as seq
from services.story import order_done

MOVE_WORDS = {'INITIAL': '하차·적치', 'REHANDLE': '재취급', 'PREMARSH': '선작업', 'RETRIEVE': '본선 인출'}


def plan_of(option):
    return [(c, d) for c, d, _ in option['positions']]


def feasible(option):
    """모든 화물에 제약을 만족하는 위치가 있어야 실행 가능한 대안입니다."""
    return all(d for _, d, _ in option['positions'])


def simulate(sim, plan, order, limit=3600):
    """결정 직전 상태를 복제해 계획대로 실행. 이동이 끝날 때마다 야드 상태를 기록합니다."""
    s = deepcopy(sim)
    s.unload_plan = list(plan)
    t0, n0 = s.now, len(s.moves)
    steps = [{'t': t0, 'move': None, 'yard': {k: list(v) for k, v in s.yard.items()}, 'statuses': dict(s.statuses)}]
    done_moves = 0
    while not order_done(s, order) and s.queue and s.queue[0][0] <= t0 + limit:
        s.advance(one_event=True)
        completed = [m for m in s.moves[n0:] if m['completed']]
        while done_moves < len(completed):
            m = completed[done_moves]; done_moves += 1
            steps.append({'t': m['end_at'], 'move': m, 'yard': {k: list(v) for k, v in s.yard.items()}, 'statuses': dict(s.statuses)})
    moves = [m for m in s.moves[n0:] if m['completed']]
    ini = [m for m in moves if m['move_type'] == 'INITIAL' and m['container_id'] in order]
    ok = order_done(s, order)
    end = max((m['end_at'] for m in ini), default=s.now)
    wait = sum(max(0, s.trucks[c]['unload_start'] - s.trucks[c]['yard_arrival']) for c in order
               if s.trucks.get(c, {}).get('unload_start') is not None)
    return {'ok': ok, 'start': t0, 'end': end, 'total_min': (end - t0) / 60,
            'move_min': sum(m['end_at'] - m['start_at'] for m in moves) / 60,
            'wait_min': wait / 60, 'rehandles': sum(m['move_type'] == 'REHANDLE' for m in moves),
            'steps': steps, 'moves': moves,
            'placed': {c: (locate(s.yard, c) or (None, None)) for c in order}}


def alternatives(sim, story, margin=seq.SWITCH_MARGIN):
    """추천 상위 대안(실행 가능한 것만)과 기준안을 같은 초기 상태에서 실행한 결과."""
    focus = story['focus']
    block = sim.bundle.containers[focus].block
    res = seq.recommend_order(sim, block, {focus: story['planned']}, prev_top=story.get('seq_prev'), margin=margin)
    key = seq.cache_key(sim, block)
    cache = story.setdefault('sim_cache', {})
    if cache.get('key') != key:
        cache.clear(); cache['key'] = key
    base = res.get('baseline')
    out = {'res': res, 'baseline': None, 'options': [], 'labels': {it['cid']: 'ABCDEFGH'[i] for i, it in enumerate(res['items'])}}
    if not base:
        return out

    def run(name, option):
        if name not in cache:
            cache[name] = simulate(sim, plan_of(option), option['order'])
        return cache[name]
    out['baseline'] = {'option': base, 'run': run('base', base)}
    for i, opt in enumerate(res['options']):
        if not feasible(opt):
            continue
        out['options'].append({'option': opt, 'run': run('>'.join(opt['order']) + '|' + '>'.join(str(d) for _, d, _ in opt['positions']), opt),
                               'rank': len(out['options']) + 1, 'delta': seq.minutes_delta(opt, base)})
    return out
