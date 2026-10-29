"""대표 사례 흐름(20개)의 완료 기준을 고정하는 테스트."""
from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from adapters.mock import build_scenario
from engine.yard import locate
from services.recommend import recommend_slots
from services.story import STORY_CONFIG, start_story, build_options, compare_branches, replay_steps, progress_state

APP = Path(__file__).resolve().parents[1] / 'app.py'
PAGES = ['dashboard', 'eta', 'premarshal', 'exceptions', 'sync', 'sharing', 'impact', 'data', 'story']


def walk_to_compare(at):
    """대표 시나리오: 상황 확인 → (CY 도착까지 진행) → 문제 확인 → 대안 비교."""
    assert at.session_state['scn_step'] == 0
    at.button(key='scn_next_0').click().run()
    assert at.session_state['scn_step'] == 1 and not at.exception
    at.button(key='scn_next_1').click().run()
    assert at.session_state['scn_step'] == 2 and not at.exception


def approve_current(at):
    at.button(key='scn_next_2').click().run()          # 적치 미리보기
    assert at.session_state['scn_step'] == 3
    at.button(key='scn_next_3').click().run()          # 배치 승인
    assert at.session_state['scn_step'] == 4
    at.button(key='scn_approve').click().run()
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


def test_scenario_a_recommended_approval_moves_to_result_and_history():
    from services import history
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception and at.session_state['page'] == 'story'
    assert at.sidebar.button(key='nav_story').label == '대표 시나리오'
    walk_to_compare(at)
    story = at.session_state['story']; focus = story['focus']
    first = story['alt']
    approve_current(at)
    # 승인 → 결과 확인으로 자동 이동, 실제 실행 완료, 이력 저장
    assert at.session_state['scn_step'] == 5
    sim = at.session_state['story_sim']; d = at.session_state['story']['decision']
    assert d['type'] == 'approve' and d['option']['order'] == first.split('|')[0].split('>')
    done = [m['container_id'] for m in sim.moves if m['move_type'] == 'INITIAL' and m['container_id'] in d['order']]
    assert done == d['order']                                                   # 승인한 순서대로 하차
    assert locate(sim.yard, focus)[0] == d['plan'][d['order'].index(focus)][1]   # 승인한 위치
    jobs = history.list_jobs()
    assert len(jobs) == 1 and jobs[0]['job_id'] == d['job_id'] and jobs[0]['status'] == '완료'
    assert abs(jobs[0]['saved_min'] - (d['base_total_min'] - d['total_min'])) < .01
    # 같은 승인을 다시 시도해도 한 번만
    moves = len(sim.moves)
    at.session_state.scn_step = 4; at.run()
    assert not any(b.key == 'scn_approve' for b in at.button) and len(at.session_state['story_sim'].moves) == moves
    # 누적 작업 이력 화면
    at.button(key='scn_next_4').click().run()
    at.button(key='scn_next_5').click().run()
    assert at.session_state['scn_step'] == 6 and not at.exception and len(at.dataframe) == 1


def test_scenario_b_c_other_alternative_and_repeat_accumulate():
    from services import history
    at = AppTest.from_file(APP, default_timeout=180).run()
    walk_to_compare(at)
    # 시뮬레이션 실행·한 단계 진행·초기화
    at.button(key='sim_run').click().run()
    assert at.session_state['scn_play']['running']
    i0 = at.session_state['scn_play']['i']
    at.button(key='sim_step').click().run()
    assert at.session_state['scn_play']['i'] == i0 + 1 and not at.session_state['scn_play']['running']
    at.button(key='sim_reset').click().run()
    assert at.session_state['scn_play']['i'] == 0
    # 추천 1위가 아닌 대안 선택 → 처리 순서·작업시간이 그 대안 값으로 바뀜
    before = at.session_state['story']['alt']
    at.button(key='alt_pick_2').click().run()
    second = at.session_state['story']['alt']
    assert second != before
    # 적치 미리보기: 칸 클릭 → 선택·화살표, 이전 단계로 가도 선택 유지
    at.button(key='scn_next_2').click().run()
    cells = [b for b in at.button if b.key and b.key.startswith('ycell_btn_')]
    assert len(cells) >= 10
    cells[0].click().run()
    picked = at.session_state['story']['pick']
    assert picked and any(b.key.startswith('ycell_btn_') for b in at.button)
    at.button(key='scn_prev_3').click().run()
    assert at.session_state['scn_step'] == 2 and at.session_state['story']['alt'] == second
    at.button(key='scn_next_2').click().run()
    assert at.session_state['story']['pick'] == picked
    at.button(key='scn_next_3').click().run(); at.button(key='scn_approve').click().run()
    d1 = at.session_state['story']['decision']
    assert d1['option']['order'] == second.split('|')[0].split('>')
    # 반복: 같은 상황에서 새 작업 → 다른 대안 승인 → 이력 2건 누적
    at.session_state.scn_step = 6; at.run()
    at.button(key='scn_new_job').click().run()
    assert at.session_state['scn_step'] == 2 and at.session_state['story'].get('decision') is None
    approve_current(at)
    jobs = history.list_jobs()
    assert len(jobs) == 2 and {j['approved'] for j in jobs} == {d1['label'], at.session_state['story']['decision']['label']}


def test_hold_is_saved_and_not_executed():
    from services import history
    at = AppTest.from_file(APP, default_timeout=180).run()
    walk_to_compare(at)
    at.button(key='scn_next_2').click().run(); at.button(key='scn_next_3').click().run()
    at.button(key='scn_hold').click().run()
    sim = at.session_state['story_sim']; story = at.session_state['story']
    assert story['decision']['type'] == 'hold' and not sim.unload_plan and sim.statuses[story['focus']] == 'YARD_QUEUE'
    assert at.session_state['scn_step'] == 6 and history.list_jobs()[0]['status'] == '보류'


def test_pages_keep_state_and_removed_items_are_gone():
    at = AppTest.from_file(APP, default_timeout=180).run()
    walk_to_compare(at)
    now = at.session_state['story_sim'].now
    for page in PAGES:
        at.button(key='nav_' + page).click().run()
        assert not at.exception, page
        assert at.session_state['story_sim'].now == now
    root = APP.parent
    src = ''.join(p.read_text(encoding='utf-8') for p in list(root.glob('*.py')) + list((root / 'ui').glob('*.py')))
    assert 'port-i' not in src.lower() and '계획 변경 대응' not in src and '대표 사례 흐름' not in src
    assert '선택 화물 보기' not in src


def test_feature_scenario_reset_does_not_touch_story():
    at = AppTest.from_file(APP, default_timeout=180).run()
    walk_to_compare(at)
    before = at.session_state['story_sim'].now
    next(s for s in at.selectbox if s.label == '시나리오').set_value('capacity')
    next(b for b in at.button if b.label == '시나리오 적용 · 처음부터 시작').click().run()
    assert at.session_state['config'].preset == 'capacity'
    assert at.session_state['story_sim'].now == before and at.session_state['scn_step'] == 2


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
