"""대표 사례 흐름(20개)의 완료 기준을 고정하는 테스트."""
from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from adapters.mock import build_scenario
from engine.yard import locate
from services.recommend import recommend_slots
from services.story import STORY_CONFIG, start_story, build_options, compare_branches, replay_steps, progress_state

APP = Path(__file__).resolve().parents[1] / 'app.py'
PAGES = ['dashboard', 'eta', 'recommend', 'premarshal', 'exceptions', 'sync', 'sharing', 'impact', 'data', 'story']


def button(at, label):
    return next(b for b in at.button if b.label == label)


def walk_to_decision(at, focus):
    assert at.segmented_control[0].value == '⓪ 관제'                              # 시작은 20개 전체 관제
    at.segmented_control[0].set_value('① 상황 확인').run()
    button(at, '도착 정보 확인 완료').click().run()
    button(at, f'{focus}의 CY 도착까지 진행').click().run()
    at.segmented_control[0].set_value('③ 대안 비교').run()
    button(at, '대안 비교 완료 → 승인 단계로').click().run()
    assert not at.exception


def test_story_has_exactly_20_containers_and_fixed_focus():
    sim, story = start_story()
    assert len(sim.bundle.containers) == 20
    initial = sum(c.initial for c in sim.bundle.containers.values())
    assert initial + sum(not c.initial for c in sim.bundle.containers.values()) == 20
    focus = story['focus']
    assert sim.statuses[focus] == 'EN_ROUTE' and locate(sim.yard, focus) is None   # 도착 전 화물은 야드에 없음
    assert len(sim.forecast_log[focus]) >= 2                                      # ETA가 실제로 갱신됨
    assert sim.plan[focus].sequence <= 6                                          # 선적 상위


def test_branches_start_from_same_state_and_count_moves_from_logs():
    sim, story = start_story()
    focus = story['focus']
    while sim.statuses[focus] != 'YARD_QUEUE':
        sim.advance(one_event=True)
    rec, keep_i, best_i, n = build_options(sim.observe(), focus, story['planned'])
    assert keep_i == 0 and best_i != keep_i and len(rec.candidates) <= 4
    pre = deepcopy(sim)
    cmp = compare_branches(pre, rec, keep_i, best_i, focus, story['other'])
    k, c = cmp['keep']['result'], cmp['chosen']['result']
    assert k.manifest['truth_hash'] == c.manifest['truth_hash']                  # 같은 실제 사건
    assert k.manifest['target_count'] == c.manifest['target_count'] == 20
    for r in (k, c):
        done = [m for m in r.moves if m['completed']]
        assert r.metrics['extra_moves'] == sum(m['move_type'] in ('REHANDLE', 'PREMARSH') for m in done)
        assert r.metrics['incomplete'] == 0
    # 기존 계획을 유지하면 대표 컨테이너가 먼저 실을 화물을 가로막아 다시 옮겨짐
    assert cmp['keep']['focus_rehandled'] >= 1 and cmp['chosen']['focus_rehandled'] == 0
    assert c.metrics['extra_moves'] < k.metrics['extra_moves']
    # 원래 상태는 바뀌지 않음
    assert pre.now == sim.now and pre.moves == sim.moves


def test_recommendation_does_not_use_future_arrivals():
    sim, story = start_story()
    o = sim.observe()
    base = recommend_slots(o, story['focus'], 'C')
    sim2, _ = start_story()
    # 실제 도착 사건(미래)을 바꿔도 지금 시점의 추천은 같아야 함
    sim2.queue = [(t + 900 if kind == 'TRUCK_ARRIVAL' else t, pr, eid, kind, p) for t, pr, eid, kind, p in sim2.queue]
    other = recommend_slots(sim2.observe(), story['focus'], 'C')
    assert [c.stack for c in base.candidates] == [c.stack for c in other.candidates]
    assert [round(c.score, 6) for c in base.candidates] == [round(c.score, 6) for c in other.candidates]


def test_full_flow_keeps_focus_and_never_double_counts():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    story = at.session_state['story']; focus = story['focus']
    assert at.session_state['page'] == 'story'
    assert len(at.session_state['story_sim'].bundle.containers) == 20 and len(at.session_state['ops'].bundle.containers) == 40
    walk_to_decision(at, focus)
    approve = button(at, '모의 승인')
    approve.click().run()
    sim = at.session_state['story_sim']
    d = at.session_state['story']['decision']
    assert d['kind'] == 'order' and focus in d['order'] and sim.unload_plan == d['plan']
    # 승인 버튼이 다시 눌려도(같은 결정) 계획이 한 번만 올라감
    at.segmented_control[0].set_value('④ 승인·보류').run()
    assert not any(b.label == '모의 승인' for b in at.button) and at.session_state['story_sim'].unload_plan == d['plan']
    at.segmented_control[0].set_value('⑤ 현장 안내·실행').run()
    button(at, '작업 완료까지 진행').click().run()
    sim = at.session_state['story_sim']
    initial = [m['container_id'] for m in sim.moves if m['move_type'] == 'INITIAL' and m['container_id'] in d['order']]
    assert initial == d['order']                                                 # 승인한 순서대로 하차
    assert locate(sim.yard, focus)[0] == d['stack']                               # 화면·로그·완료 상태 일치
    state = progress_state(at.session_state['story'], sim)
    assert state['작업 완료'] and state['승인 또는 보류'] == 'approve' and not state['결과 확인']
    # 재생은 로그를 읽기만 함: 여러 번 그려도 이동 수 불변
    n = len(sim.moves)
    for _ in range(3):
        steps, _ = replay_steps(sim.bundle, sim.moves, d['at'], sim.now, focus)
    assert len(sim.moves) == n and any(s['move']['container_id'] == focus for s in steps)
    # 화면 이동·뒤로 가기(URL)로 대표 컨테이너·시각·기록이 초기화되지 않음
    now = sim.now
    feature_focus = at.session_state['focus']
    for page in PAGES:
        at.button(key='nav_' + page).click().run()
        assert not at.exception, page
        assert at.session_state['story']['focus'] == focus and at.session_state['story_sim'].now == now
        assert at.session_state['story']['decision']['order'] == d['order']
        assert at.session_state['focus'] == feature_focus                       # 기능 시연 쪽 선택도 유지
    at.query_params['page'] = 'eta'
    at.run()
    assert at.session_state['page'] == 'eta' and at.session_state['story_sim'].now == now and len(at.session_state['story_sim'].moves) == n


def test_hold_is_a_separate_branch_not_completion():
    at = AppTest.from_file(APP, default_timeout=120).run()
    focus = at.session_state['story']['focus']
    walk_to_decision(at, focus)
    button(at, '보류').click().run()
    sim = at.session_state['story_sim']; story = at.session_state['story']
    state = progress_state(story, sim)
    assert state['승인 또는 보류'] == 'hold' and not state['작업 완료']
    assert not sim.accepted and not sim.unload_plan and sim.statuses[focus] == 'YARD_QUEUE'


def test_selection_does_not_jump_when_focus_leaves_pending_list():
    at = AppTest.from_file(APP, default_timeout=120).run()
    focus = at.session_state['story']['focus']
    walk_to_decision(at, focus)
    button(at, '모의 승인').click().run()
    button(at, '작업 완료까지 진행').click().run()
    at.button(key='nav_recommend').click().run()
    assert not at.exception and at.session_state['story']['focus'] == focus
    # 기능 화면: 승인한 화물이 미적치 목록에서 빠져도 다른 화물로 자동 전환하지 않음
    ops = at.session_state['ops']; f = at.session_state['focus']
    next(b for b in at.button if b.label == '선택한 배치 모의 승인').click().run()
    assert any(v['container_id'] == f for v in at.session_state['ops'].accepted.values())
    next(b for b in at.button if b.label == '현재 작업 완료까지 진행').click().run()
    at.button(key='nav_recommend').click().run()
    assert not at.exception and at.session_state['focus'] == f


def test_feature_scenario_reset_does_not_touch_story():
    at = AppTest.from_file(APP, default_timeout=120).run()
    focus = at.session_state['story']['focus']
    walk_to_decision(at, focus)
    before = at.session_state['story_sim'].now
    next(s for s in at.selectbox if s.label == '시나리오').set_value('capacity')
    button(at, '시나리오 적용 · 처음부터 시작').click().run()
    assert at.session_state['config'].preset == 'capacity'
    assert at.session_state['story_sim'].now == before and at.session_state['story']['progress'].get('compared')


def test_no_preference_learning_or_scoring_left():
    root = APP.parent
    src = ''.join(p.read_text(encoding='utf-8') for p in list(root.glob('*.py')) + list((root / 'ui').glob('*.py')) + list((root / 'services').glob('*.py')))
    for word in ('train_preferences', 'personalize', 'trained_model', '선호모델', '현장 판단 학습'):
        assert word not in src, word


def test_overview_picks_focus_first_and_plan_change_keeps_valid_position():
    from services.story import review_queue, apply_plan_change
    sim, story = start_story()
    assert review_queue(sim)[0]['cid'] == story['focus']                          # 검토 순위 1위 = 대표
    focus = story['focus']
    while sim.statuses[focus] != 'YARD_QUEUE':
        sim.advance(one_event=True)
    rec, keep_i, best_i, n = build_options(sim.observe(), focus, story['planned'])
    assert sim.approve(rec, best_i).valid
    while sim.statuses[focus] != 'STORED':
        sim.advance(one_event=True)
    old = sim.plan[focus].due
    r = apply_plan_change(sim, story, -30)
    assert r['mode'] == 'stored' and r['keep'] and r['new_due'] == old - 1800


def test_order_branches_same_event_and_focus_not_rehandled():
    import services.sequence as seq
    from services.story import compare_orders
    sim, story = start_story()
    focus = story['focus']
    while sim.statuses[focus] != 'YARD_QUEUE':
        sim.advance(one_event=True)
    res = seq.recommend_order(sim, 'A1', {focus: story['planned']})
    base = [(c, d) for c, d, _ in res['baseline']['positions']]
    top = [(c, d) for c, d, _ in res['options'][0]['positions']]
    assert dict(base)[focus] == story['planned'] and res['options'][0]['order'] != res['baseline']['order']
    cmp = compare_orders(deepcopy(sim), base, top, focus, story['other'])
    k, c = cmp['keep'], cmp['chosen']
    assert k['result'].manifest['truth_hash'] == c['result'].manifest['truth_hash']
    assert k['focus_rehandled'] >= 1 and c['focus_rehandled'] == 0
    assert c['result'].metrics['extra_moves'] <= k['result'].metrics['extra_moves']   # 결과는 실행 로그 값 그대로
