"""처리 순서 추천: 공통 난수, 시드 고정, 지연 주입, 1위 유지 임계값, 상위 5개 제한, 분 단위 합산, 민감도."""
from copy import deepcopy
import services.sequence as seq
from services.story import start_story
from services.eta import sample_arrivals


def at_decision():
    sim, story = start_story()
    f = story['focus']
    while sim.statuses[f] != 'YARD_QUEUE':
        sim.advance(one_event=True)
    return sim, story


def test_a_all_orders_share_the_same_samples(monkeypatch):
    sim, story = at_decision()
    seen = []
    real = seq.evaluate_order

    def spy(o, order, samples, fixed=None, weights=seq.WEIGHTS):
        seen.append(samples)
        return real(o, order, samples, fixed, weights)
    monkeypatch.setattr(seq, 'evaluate_order', spy)
    seq._CACHE.clear()
    seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    assert len(seen) >= 2 and all(s is seen[0] for s in seen)       # 같은 표본 객체를 모든 순서에


def test_b_same_input_same_recommendation_regardless_of_time():
    sim, story = at_decision()
    seq._CACHE.clear()
    a = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    seq._CACHE.clear()
    b = seq.recommend_order(deepcopy(sim), 'A1', {story['focus']: story['planned']})
    assert [o['order'] for o in a['options']] == [o['order'] for o in b['options']]
    o1 = sim.observe(); o2 = sim.observe(); o2.now += 37                 # 시각만 바뀌면 표본은 같아야 함
    assert sample_arrivals(o1, 'C') == [{k: v for k, v in w.items()} for w in sample_arrivals(o1, 'C')]
    assert seq.sample_seed(o1) == seq.sample_seed(o2)


def test_c_injected_delay_changes_order():
    sim, story = start_story()
    f = story['focus']
    while not any(i['cid'] == f for i in seq.queue_items(sim, 'A1')):
        sim.advance(one_event=True)
    before = seq.recommend_order(sim, 'A1', {f: story['planned']})['options'][0]['order']
    seq.inject_truck_delay(sim, f, 30)
    after = seq.recommend_order(sim, 'A1', {f: story['planned']})
    assert f in before and (not after['options'] or after['options'][0]['order'] != before)
    assert any(e['kind'] == 'INJECTED_DELAY' for e in sim.events)


def test_d_small_score_gap_keeps_previous_top():
    sim, story = at_decision()
    seq._CACHE.clear()
    res = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    second = res['options'][1]['order']
    gap = res['options'][1]['J'] - res['options'][0]['J']
    assert gap > 0
    kept = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']}, prev_top=second, margin=gap + 1)
    assert kept['options'][0]['order'] == second and kept['switched'] is None
    swapped = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']}, prev_top=second, margin=0)
    assert swapped['options'][0]['order'] != second and swapped['switched']


def test_e_future_arrivals_not_used():
    sim, story = at_decision()
    seq._CACHE.clear()
    a = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    sim.queue = [(t + 900 if k == 'TRUCK_ARRIVAL' else t, p, e, k, d) for t, p, e, k, d in sim.queue]
    seq._CACHE.clear()
    b = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    assert [o['order'] for o in a['options']] == [o['order'] for o in b['options']]
    assert [round(o['J'], 6) for o in a['options']] == [round(o['J'], 6) for o in b['options']]


def test_f_more_than_five_only_top_five_permuted(monkeypatch):
    sim, story = at_decision()
    fake = [{'cid': cid, 'arrival': sim.now + i, 'eta': None, 'arrived': True}
            for i, cid in enumerate([c for c, x in sim.bundle.containers.items() if x.block == 'A1' and not x.initial][:4]
                                    + [c for c, x in sim.bundle.containers.items() if x.block == 'A1' and x.initial][:3])]
    monkeypatch.setattr(seq, 'queue_items', lambda s, b, now=None: fake)
    seq._CACHE.clear()
    res = seq.recommend_order(sim, 'A1')
    tail = [x['cid'] for x in fake[5:]]
    assert res['limited'] and all(o['order'][5:] == tail for o in res['options'])


def test_g_minutes_match_rollout_components():
    sim, story = at_decision()
    seq._CACHE.clear()
    res = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    opt, base = res['options'][0], res['baseline']
    d = seq.minutes_delta(opt, base)
    from statistics import mean
    for i, k in enumerate('ETD'):
        assert abs(d[k][0] - mean((a[i] - b[i]) / 60 for a, b in zip(opt['comps'], base['comps']))) < 1e-9
        assert d[k][1] <= d[k][0] <= d[k][2]
    assert abs(d['total'][0] - (d['E'][0] + d['T'][0] + d['D'][0])) < 1e-9


def test_h_approval_recheck_and_idempotence_unchanged():
    from services.story import build_options
    sim, story = at_decision()
    f = story['focus']
    rec, k, b, n = build_options(sim.observe(), f, story['planned'])
    assert sim.approve(rec, b).valid
    moves = len(sim.moves)
    assert sim.approve(rec, b).valid and len(sim.moves) == moves
    sim.yard_version += 1
    rec2, *_ = build_options(sim.observe(), f, story['planned'])
    sim.yard_version += 1
    assert not sim.approve(rec2, 0).valid


def test_i_sensitivity_ratio():
    sim, story = at_decision()
    seq._CACHE.clear()
    s = seq.sensitivity(sim, 'A1', {story['focus']: story['planned']})
    assert s['total'] == 81 and 0 <= s['same'] <= 81
    assert s['same'] + len(s['changes']) == s['total']


def test_unload_plan_executes_in_order():
    sim, story = at_decision()
    res = seq.recommend_order(sim, 'A1', {story['focus']: story['planned']})
    top = res['options'][0]
    sim.unload_plan = [(c, d) for c, d, _ in top['positions']]
    done = []
    while sim.unload_plan or any(c in sim.yard_arrivals for c, _, _ in top['positions']):
        sim.advance(one_event=True)
    done = [m['container_id'] for m in sim.moves if m['move_type'] == 'INITIAL' and m['container_id'] in top['order']]
    assert done == top['order']
