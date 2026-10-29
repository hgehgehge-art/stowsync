"""대표 컨테이너 한 개를 따라가는 시연 흐름(20개 합성 사건).

입력 변화 → 기존 계획 영향 → 대안과 근거 → 승인·보류 → 모의 작업 → 같은 사건의 결과 비교.
결과 비교는 '결정 직전 상태'를 복제해 두 갈래(기존 계획 유지 / 선택한 대안)로 나눠 끝까지 돌립니다.
두 갈래 모두 대표 컨테이너 외 화물은 같은 규칙(기준 정책 A)으로 처리하고, 실제 도착 사건·화물·장비 조건은 같습니다.
"""
from copy import deepcopy
from domain.models import Config, Recommendation, slot, stable_hash
from adapters.mock import build_scenario, STORY_PLAN_AT, STORY_UPDATE
from engine.simulator import Simulator
from engine.yard import blockers, locate, rank, feasible
from services.recommend import recommend_slots, evaluate
from services.eta import sample_arrivals

STORY_CONFIG = Config(seed=4, preset='story', target_count=20, occupancy=.25, plan_changes=False)
STEPS = ['도착 정보 확인', '대안 비교', '승인 또는 보류', '작업 완료', '결과 확인']


def story_ids(bundle):
    ids = list(bundle.containers)
    ic = sum(c.initial for c in bundle.containers.values())
    return ids[ic], ids[ic + 4]


def start_story(cfg=STORY_CONFIG):
    """시연 시작 상태: 대표 컨테이너 A의 ETA가 지연으로 갱신된 직후."""
    bundle = build_scenario(cfg)
    focus, other = story_ids(bundle)
    sim = Simulator(bundle, 'A')
    sim.manual = True          # 자동 선작업 없음(선작업은 사람이 승인할 때만)
    # 대표 컨테이너와 비슷한 시각에 같은 블록으로 들어오는 트럭(처리 순서 검토 대상)은 플래너 승인 대상, 나머지는 같은 규칙으로 자동 처리
    from adapters.mock import STORY_BATCH
    ic = sum(c.initial for c in bundle.containers.values())
    ids = list(bundle.containers)
    sim.manual_ids = {focus} | {ids[ic + k] for k in STORY_BATCH}
    sim.advance(STORY_PLAN_AT)
    # 기존 계획: 예약시각(지연 전)에 맞춰 잡아 둔 적치 위치
    planned = recommend_slots(sim.observe(), focus, 'A').candidates[0].stack
    sim.advance(STORY_UPDATE + 60)
    return sim, {'focus': focus, 'other': other, 'planned': planned, 'planned_at': STORY_PLAN_AT,
                 'progress': {}, 'decision': None, 'compare': None}


def gate_and_yard_times(sim, cid):
    """게이트 도착 예상과 CY 하차 가능 예상(게이트 처리 + 터미널 내부 이동)을 따로 계산합니다."""
    t = sim.trucks.get(cid)
    lag = sim.config.gate_service + sim.config.internal_travel
    f = sim.forecasts.get(cid)
    if t:
        return {'gate': t['gate_arrival'], 'yard': t['yard_arrival'], 'observed': True, 'lag': lag}
    if f:
        return {'gate': (f.p10, f.p50, f.p90), 'yard': (f.p10 + lag, f.p50 + lag, f.p90 + lag), 'observed': False, 'lag': lag}
    return {'gate': None, 'yard': None, 'observed': False, 'lag': lag}


def planned_conflict(o, focus, planned):
    """기존 계획 위치에 대표 컨테이너를 놓으면 가로막게 되는 화물(대표보다 먼저 인출)."""
    items = o.yard.get(planned, [])
    return [x for x in items if rank(o.plan, x) < rank(o.plan, focus)]


def blocking_pairs(o):
    """(아래 화물, 위에서 가로막는 화물) 목록."""
    return blockers(o.yard, o.plan)[1]


def build_options(o, focus, planned, max_alt=3):
    """기존 계획 유지안 + 시스템 대안 최대 3개. 모두 같은 표본(공통 난수)으로 평가합니다."""
    rec = recommend_slots(o, focus, 'C')
    feas = feasible(o, focus, None)
    samples = sample_arrivals(o, 'C')
    keep = evaluate(o, focus, planned, samples, 'INITIAL') if planned in feas else None
    alts = [c for c in rec.candidates if c.stack != planned][:max_alt]
    cands = ([keep] if keep else []) + alts
    rid = stable_hash([rec.recommendation_id, planned, 'story'])
    combined = Recommendation(rid, focus, 'INITIAL', o.now, rec.valid_until, o.yard_version, o.plan_version, cands,
                              reason=rec.reason)
    best = min(range(len(cands)), key=lambda i: (cands[i].score, i)) if cands else None
    return combined, (0 if keep else None), best, len(samples)


def run_branch(pre, rec, index):
    """결정 직전 상태(pre)를 복제해 rec.candidates[index]를 승인하고 끝까지 진행합니다."""
    s = deepcopy(pre)
    s.cargo_checks.add(rec.container_id)
    report = s.approve(rec, index)
    if not report.valid:
        return None, report.errors
    s.manual_ids = set()
    s.advance()
    return s, []


def focus_outcome(sim, focus, other):
    r = sim.result()
    mv = [m for m in r.moves if m['completed']]
    initial = next((m for m in mv if m['container_id'] == focus and m['move_type'] == 'INITIAL'), None)
    retrieve = next((m for m in mv if m['container_id'] == focus and m['move_type'] == 'RETRIEVE'), None)
    focus_rehandled = sum(m['container_id'] == focus and m['move_type'] == 'REHANDLE' for m in mv)
    for_focus = sum(m['move_type'] == 'REHANDLE' and m['for_container'] == focus for m in mv)
    truck = next((t for t in r.trucks if t['container_id'] == focus), None)
    ret = next((x for x in r.retrievals if x['container_id'] == focus), None)
    return {'result': r, 'initial_slot': initial['target_slot'] if initial else '—',
            'focus_rehandled': focus_rehandled, 'for_focus': for_focus,
            'focus_retrieved_at': retrieve['end_at'] if retrieve else None,
            'focus_delay': ret['delay_seconds'] if ret else None,
            'focus_wait': ((truck['gate_start'] - truck['gate_arrival']) + (truck['unload_start'] - truck['yard_arrival']))
            if truck and truck['unload_start'] is not None else None}


def compare_branches(pre, rec, keep_index, chosen_index, focus, other):
    """같은 결정 직전 상태에서 '기존 계획 유지'와 '선택한 대안'을 각각 끝까지 돌린 결과."""
    out = {}
    for name, idx in (('keep', keep_index), ('chosen', chosen_index)):
        if idx is None:
            out[name] = None
            continue
        s, errors = run_branch(pre, rec, idx)
        out[name] = None if s is None else {**focus_outcome(s, focus, other), 'sim': s, 'index': idx}
    return out


# ── 작업 재생(실행 로그 → 장면 목록) ─────────────────────────
def yard_at(bundle, moves, t):
    """초기 적치 + 완료 시각이 t 이하인 이동을 차례로 적용한 야드."""
    yard = deepcopy(bundle.initial_yard)
    for m in sorted((m for m in moves if m['completed'] and m['end_at'] <= t), key=lambda m: (m['end_at'], m['move_id'])):
        apply_move(yard, m)
    return yard


def apply_move(yard, m):
    if m['source_stack'] and m['container_id'] in yard[m['source_stack']]:
        yard[m['source_stack']].remove(m['container_id'])
    if m['target_stack']:
        yard[m['target_stack']].append(m['container_id'])


MOVE_WORDS = {'INITIAL': '최초 적치', 'PREMARSH': '선작업', 'REHANDLE': '재취급', 'RETRIEVE': '본선 인출'}


def move_reason(m, focus):
    kind, cid, beneficiary = m['move_type'], m['container_id'], m.get('for_container') or ''
    if kind == 'INITIAL':
        return f'{cid} 트럭에서 하차해 {m["target_slot"]}에 처음 적치합니다.'
    if kind == 'RETRIEVE':
        return f'선적 순서에 따라 {cid}를 본선으로 인출합니다.'
    if kind == 'REHANDLE':
        who = '대표 컨테이너 ' + focus if beneficiary == focus else beneficiary
        return f'{who}의 인출을 위해 위에 있던 {cid}를 {m["target_slot"]}로 옮깁니다.' if beneficiary else f'{cid}를 옮깁니다.'
    if kind == 'PREMARSH':
        who = '대표 컨테이너 ' + focus if beneficiary == focus else beneficiary
        return f'{who}의 인출을 준비하기 위해 {cid}를 {m["target_slot"]}로 미리 이동합니다.' if beneficiary else f'{cid}를 미리 이동합니다.'
    return ''


def replay_steps(bundle, moves, t_from, t_to, focus):
    """t_from 이후 시작해 t_to 이전에 끝난 이동을 시간순으로. 각 단계: 이동 전 야드, 이동 정보."""
    done = sorted((m for m in moves if m['completed'] and m['start_at'] >= t_from and m['end_at'] <= t_to),
                  key=lambda m: (m['end_at'], m['move_id']))
    yard = yard_at(bundle, [m for m in moves if m['end_at'] <= t_from], t_from)
    steps = []
    for m in done:
        steps.append({'yard': deepcopy(yard), 'move': m, 'reason': move_reason(m, focus), 'label': MOVE_WORDS[m['move_type']]})
        apply_move(yard, m)
    return steps, yard


def progress_state(story, sim):
    """체크리스트: 실제 처리 사건으로만 완료를 표시합니다. 보류는 별도 분기."""
    p = story['progress']
    d = story.get('decision')
    done_job = False
    if d and d['type'] == 'approve':
        done_job = order_done(sim, d['order']) if d.get('kind') == 'order' else sim.accepted.get(d['rec_id'], {}).get('status') == 'COMPLETED'
    return {'도착 정보 확인': p.get('arrival_checked'), '대안 비교': p.get('compared'),
            '승인 또는 보류': d['type'] if d else None, '작업 완료': done_job,
            '결과 확인': p.get('result_checked')}


# ── ⓪ 관제: 검토 대상 선정 ─────────────────────────────
QUAD_ORDER = {('지연', '상위'): 0, ('조기', '하위'): 1, ('지연', '하위'): 2, ('조기', '상위'): 3}


def review_queue(sim):
    """반입 예정 화물을 검토 우선순위로 정렬합니다. 2×2 분류는 정렬과 설명에만 쓰고 위치를 고정하지 않습니다."""
    from services.workflows import quadrant
    o = sim.observe()
    rows = []
    for cid, c in o.containers.items():
        if c.initial:
            continue
        f = o.forecasts.get(cid)
        t = sim.trucks.get(cid)
        arrival, priority = quadrant(o, cid)
        if t:
            ref = t['gate_arrival']; eta_txt = 'ATA'
        elif f:
            ref = f.p50; eta_txt = 'ETA'
        else:
            ref = None; eta_txt = ''
        dev = None if ref is None else (ref - c.booking_end if ref > c.booking_end else ref - c.booking_start if ref < c.booking_start else 0)
        rank_q = QUAD_ORDER.get((arrival, priority), 4)
        rows.append({'cid': cid, 'arrival': arrival, 'priority': priority, 'dev': dev, 'ref': ref, 'kind': eta_txt,
                     'seq': o.plan[cid].sequence, 'status': sim.statuses[cid], 'cargo': c.cargo_type,
                     'booking': (c.booking_start, c.booking_end), 'rank_q': rank_q})
    rows.sort(key=lambda r: (r['rank_q'], -abs(r['dev'] or 0), r['seq']))
    return rows


# ── ⑥ 계획 변경 대응 ─────────────────────────────────
def apply_plan_change(sim, story, minutes=-30):
    """Port-i 선박 일정 변경(접안 앞당김)을 TOS 인출 예정시각에 반영하고, 대표 컨테이너 결정을 재평가합니다."""
    from services.workflows import change_vessel
    focus = story['focus']
    before_due = sim.plan[focus].due
    before_ver = sim.plan_version
    version, shift = change_vessel(sim, minutes)
    o = sim.observe()
    pos = locate(o.yard, focus)
    result = {'at': sim.now, 'minutes': minutes, 'version': version, 'old_version': before_ver,
              'old_due': before_due, 'new_due': sim.plan[focus].due}
    if pos:
        stack = o.yard[pos[0]]
        i = pos[1] - 1
        below_earlier = [x for x in stack[:i] if rank(o.plan, x) < rank(o.plan, focus)]
        above_later = [x for x in stack[i + 1:] if rank(o.plan, x) > rank(o.plan, focus)]
        result.update({'mode': 'stored', 'slot': slot(pos[0], pos[1]), 'blocks': below_earlier, 'covered_by': above_later,
                       'keep': not below_earlier and not above_later})
    elif sim.statuses[focus] == 'YARD_QUEUE':
        rec, keep_i, best_i, n = build_options(o, focus, story['planned'])
        prev = story.get('last_best')
        new = rec.candidates[best_i].stack if best_i is not None else None
        result.update({'mode': 'pending', 'prev_best': prev, 'new_best': new, 'keep': prev == new})
    elif sim.statuses[focus] == 'RETRIEVED':
        result.update({'mode': 'retrieved', 'keep': True})
    else:
        result.update({'mode': 'en_route', 'keep': True})
    story['plan_change'] = result
    return result


# ── 처리 순서 결정의 두 갈래 비교 ────────────────────────
def run_order_branch(pre, plan):
    """결정 직전 상태에서 처리 순서·위치 계획 [(cid, 스택)]을 실행해 끝까지 진행합니다."""
    s = deepcopy(pre)
    s.unload_plan = list(plan)
    s.advance()
    return s


def compare_orders(pre, base_plan, chosen_plan, focus, other):
    out = {}
    for name, plan in (('keep', base_plan), ('chosen', chosen_plan)):
        s = run_order_branch(pre, plan)
        out[name] = {**focus_outcome(s, focus, other), 'sim': s, 'plan': plan}
    return out


def order_done(sim, order):
    return all(any(m['container_id'] == c and m['move_type'] == 'INITIAL' and m['completed'] for m in sim.moves) for c in order)
