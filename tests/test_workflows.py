from dataclasses import replace
from pathlib import Path
import sqlite3
from streamlit.testing.v1 import AppTest
from adapters.mock import build_scenario
from domain.models import Config,Forecast
from engine.simulator import Simulator
from engine.yard import feasible,locate
from services.recommend import propose_premarshal,recommend_slots
from services.workflows import predict_arrival,quadrant,persist_event,change_vessel


def button(at,label):return next(b for b in at.button if b.label==label)
def select(at,label):return next(s for s in at.selectbox if s.label==label)
def use_scenario(at,preset):
    select(at,'시나리오').set_value(preset);button(at,'시나리오 적용 · 처음부터 시작').click().run()
    assert at.session_state['config'].preset==preset

def test_consent_excludes_gps_and_low_trust_blocks_premarshal():
    a,_=predict_arrival('C',0,1800,[0,5]*10,False,1,2.5)
    b,_=predict_arrival('C',0,1800,[0,5]*10,False,90,.5)
    assert a.p50==b.p50 and a.p10==b.p10 and a.trust_score==b.trust_score
    fresh,_=predict_arrival('C',0,1800,[0,5]*10,True,1,1,1)
    stale,_=predict_arrival('C',0,1800,[0,5]*10,True,1,1,10)
    assert fresh.p50!=a.p50 and stale.p50==a.p50
    s=Simulator(build_scenario(Config(target_count=40,occupancy=.5,preset='premarshal_demo')))
    s.manual=s.manual_initial=True;s.advance(0)
    assert propose_premarshal(s.observe())
    s.forecasts={cid:replace(f,trust_score=20) for cid,f in s.forecasts.items()}
    assert propose_premarshal(s.observe()) is None


def test_premarshal_approval_totals_and_special_cargo_gate():
    s=Simulator(build_scenario(Config(target_count=40,occupancy=.5,preset='premarshal_demo')))
    s.manual=s.manual_initial=True;s.advance(0)
    rec=propose_premarshal(s.observe());assert rec
    assert all(c.premarshals==1 for c in rec.candidates)
    assert rec.keep_rehandles>=0
    src=locate(s.yard,rec.container_id)
    assert s.approve(rec).valid
    assert locate(s.yard,rec.container_id)==src
    s.advance(s.cranes[s.bundle.containers[rec.container_id].block]['end_at'])
    assert locate(s.yard,rec.container_id)==(rec.candidates[0].stack,rec.candidates[0].tier)
    assert s.result().metrics['PREMARSH']==1
    danger=next(cid for cid,c in s.bundle.containers.items() if c.cargo_type=='위험물')
    keys=feasible(s.observe(),danger)
    assert keys and all(k.endswith('-02-03') for k in keys)
    r=recommend_slots(s.observe(),danger)
    assert any('CARGO_REVIEW' in error for error in s.validate_action(r,r.candidates[0]).errors)
    s.cargo_checks.add(danger)
    assert not any('CARGO_REVIEW' in error for error in s.validate_action(r,r.candidates[0]).errors)


def test_four_quadrants_and_vessel_plan_freeze():
    s=Simulator(build_scenario(Config(target_count=40,occupancy=.5)))
    s.manual=s.manual_initial=True;s.advance(0)
    o=s.observe();high=min(o.plan,key=lambda cid:o.plan[cid].sequence);low=max(o.plan,key=lambda cid:o.plan[cid].sequence)
    for cid,p in [(high,'상위'),(low,'하위')]:
        c=o.containers[cid]
        for time,a in [(c.booking_start-60,'조기'),(c.booking_end+60,'지연')]:
            o.forecasts[cid]=Forecast('test',0,cid,time-20,time,time+20)
            assert quadrant(o,cid)==(a,p)
    s.advance(2280);before=dict(s.plan)
    version,shift=change_vessel(s,30)
    assert shift==1800 and s.plan_version==version
    for cid,p in before.items():
        if s.statuses[cid]=='IN_MOVE' or p.due<=s.now+300:assert s.plan[cid].due==p.due
        else:assert s.plan[cid].due==p.due+1800


def test_decision_history_is_neutral_and_idempotent(tmp_path):
    r={'container':'X','action':'INITIAL','slot':'A1-01-01-01','reason':'장비 동선','plan':'P1'}
    persist_event('one','decision',r,tmp_path)
    persist_event('one','decision',r,tmp_path)
    with sqlite3.connect(tmp_path/'demo.sqlite3') as db:assert db.execute('SELECT count(*) FROM events').fetchone()[0]==1


def test_new_ui_flows_eta_approval_driver_and_premarshal():
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=60).run()
    use_scenario(at,'balanced')
    for page in ['exceptions','premarshal','sharing','eta','data']:
        at.button(key='nav_'+page).click().run();assert not at.exception
    at.button(key='nav_eta').click().run()
    cid=next(cid for cid,state in at.session_state['ops'].statuses.items() if state=='EN_ROUTE')
    select(at,'검토 컨테이너').set_value(cid).run()
    next(c for c in at.checkbox if c.label=='가상 위치정보 사용에 동의').uncheck()
    button(at,'ETA 계산·배치 추천에 반영').click().run()
    assert not at.exception
    assert at.session_state['ops'].forecasts[cid].source=='demo_input_fusion'
    assert at.session_state['eta_inputs'][cid]['evidence']['GPS 반영'] is False
    at.button(key='nav_dashboard').click().run();button(at,'배치 대안 검토').click().run()
    # Choose an alternative so the training path learns an actual override.
    choice=next(x for x in at.radio if x.label=='비교할 배치 대안')
    if len(choice.options)>1:choice.set_value(1).run()
    button(at,'선택한 배치 모의 승인').click().run()
    assert not at.exception and at.session_state['guides']
    at.button(key='nav_sharing').click().run()
    button(at,'기사 확인 모의 처리').click().run()
    assert not at.exception and all(g['ack'] for g in at.session_state['guides'].values())
    at.button(key='nav_premarshal').click().run()
    button(at,'선작업 시연 시나리오로 처음부터 시작').click().run()
    assert not at.exception
    button(at,'선작업 모의 승인').click().run()
    assert not at.exception and at.session_state['page']=='sync'
    button(at,'현재 작업 완료까지 진행').click().run()
    assert at.session_state['ops'].result().metrics['PREMARSH']==1
