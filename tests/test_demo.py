from dataclasses import asdict
from pathlib import Path
from streamlit.testing.v1 import AppTest
from domain.models import Config
from adapters.mock import build_scenario
from engine.simulator import Simulator, run_simulation
from engine.yard import assert_yard, locate
from services.recommend import recommend_slots


def test_same_events_and_all_moves_counted():
    bundle=build_scenario(Config(target_count=40,occupancy=.5))
    runs=[run_simulation(bundle,p) for p in 'ABC']
    assert len({r.manifest['truth_hash'] for r in runs})==1
    for r in runs:
        assert r.metrics['incomplete']==0
        assert r.metrics['extra_moves']==sum(m['completed'] and m['move_type'] in ('PREMARSH','REHANDLE') for m in r.moves)
        for snap in r.snapshots:
            assert_yard(snap['observation'].yard,bundle.containers,bundle.config.stack_weight_limit)
    repeated=run_simulation(bundle,'C')
    assert repeated.moves==runs[2].moves


def test_approval_is_idempotent_and_commits_only_on_completion():
    s=Simulator(build_scenario(Config(target_count=40,occupancy=.5)))
    s.manual=s.manual_initial=True;s.advance(2280)
    cid=next(x for x in s.yard_arrivals if s.cranes[s.bundle.containers[x].block] is None)
    rec=recommend_slots(s.observe(),cid)
    assert s.approve(rec).valid
    count=len(s.moves)
    assert s.approve(rec).valid and len(s.moves)==count
    assert locate(s.yard,cid) is None
    job=s.cranes[s.bundle.containers[cid].block]
    s.advance(job['end_at'])
    assert locate(s.yard,cid)==(rec.candidates[0].stack,rec.candidates[0].tier)
    assert s.accepted[rec.recommendation_id]['status']=='COMPLETED'


def test_pages_and_approval_flow():
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=60).run()
    assert not at.exception
    next(s for s in at.selectbox if s.label=='시나리오').set_value('balanced')
    next(b for b in at.button if b.label=='시나리오 적용 · 처음부터 시작').click().run()
    assert at.session_state['config'].preset=='balanced'
    for page in ['eta','recommend','sync','impact','data','dashboard']:
        at.button(key='nav_'+page).click().run()
        assert not at.exception, [(x.message) for x in at.exception]
    at.button(key='focus_action').click().run()
    approve=next(b for b in at.button if b.label=='선택한 배치 모의 승인')
    assert not approve.disabled
    approve.click().run()
    assert not at.exception
    assert at.session_state['page']=='sync'
    assert len(at.session_state['ops'].accepted)==1
    next(b for b in at.button if b.label=='현재 작업 완료까지 진행').click().run()
    assert not at.exception
    assert all(x['status']=='COMPLETED' for x in at.session_state['ops'].accepted.values())


def test_stale_recommendation_rejected():
    s=Simulator(build_scenario(Config(target_count=40,occupancy=.5)))
    s.manual=s.manual_initial=True;s.advance(2280)
    cid=next(iter(s.yard_arrivals));rec=recommend_slots(s.observe(),cid)
    s.yard_version+=1
    assert not s.approve(rec).valid
    assert not s.accepted
