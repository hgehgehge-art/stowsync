"""Demo input fusion, exception policies and neutral decision history (no preference learning).

No production forecast, IMDG validation or external delivery is performed.
"""
from dataclasses import asdict
from statistics import mean, median, pstdev
from copy import deepcopy
import json
import random
import sqlite3
from pathlib import Path
from domain.models import Forecast, stable_hash, PlanEntry
from engine.yard import rank

RULES = {
    ('조기','상위'): ('접근성 확보', '선행 화물을 가리지 않는 낮은 적층 후보를 우선 검토하고, 상부 공간을 확보합니다.'),
    ('조기','하위'): ('후순위 화물끼리 배치', '나중에 인출할 화물과 묶고, 먼저 실을 화물 위에 쌓지 않도록 비교합니다.'),
    ('지연','상위'): ('긴급 인출 동선 확보', '도착 후 빠르게 인출할 수 있는 후보를 검토하고, 선적 마감과 장비 여유를 재확인합니다.'),
    ('지연','하위'): ('가용 공간에 순차 배치', '현재 긴급 작업을 유지하며 빈 공간과 후순위 화물의 인출 순서를 함께 검토합니다.'),
}

def quadrant(o,cid):
    c=o.containers[cid];f=o.forecasts.get(cid)
    high=cid in sorted(o.plan,key=lambda x:rank(o.plan,x))[:max(1,int(len(o.plan)*.3))]
    priority='상위' if high else '하위'
    if not f:return '정보 부족',priority
    arrival='조기' if f.p50<c.booking_start else '지연' if f.p50>c.booking_end else '정시'
    return arrival,priority

def demo_history(cid):
    rng=random.Random(int(stable_hash([cid,'driver-history']),16))
    return [rng.choice([-14,-8,-3,0,2,5,9,17,22]) for _ in range(20)]

def predict_arrival(cid,now,booking,history,gps_consent=False,remaining_minutes=None,traffic=1.,gps_age=0):
    """Transparent rule-based fusion. trust_score is not calibrated probability."""
    history=[float(x) for x in history]
    bias=median(history)*60 if history else 0
    base=booking+bias
    spread=max(300,pstdev(history)*60) if len(history)>1 else 1200
    usable=gps_consent and remaining_minutes is not None and gps_age<=5
    weight=.75 if usable else 0
    if usable:
        route=now+max(0,remaining_minutes)*60*traffic
        mid=max(now,round(weight*route+(1-weight)*base))
        width=max(180,round(spread*.5+gps_age*30))
    else:
        mid=max(now,round(base));width=round(spread*1.4)
    adherence=sum(abs(x)<=15 for x in history)/len(history) if history else 0
    trust=round(25+20*min(len(history)/20,1)+15*adherence+(30 if usable else 0)+max(0,10-width/120))
    f=Forecast('INPUT-'+stable_hash([cid,now,booking,history,gps_consent,remaining_minutes if usable else None,traffic if usable else None]),now,cid,max(now,mid-width),mid,mid+width,'demo_input_fusion',max(0,min(100,trust)))
    return f,{'예약 기준':booking,'이력 보정(분)':round(bias/60,1),'준수율':adherence,'표본 수':len(history),'GPS 반영':usable,'GPS 가중치':weight,'입력 품질 점수':f.trust_score,'GPS 제외 사유':'동의 없음' if not gps_consent else '갱신 지연' if gps_age>5 else ''}

def terminal_feed(sim):
    rows=[]
    for i in range(9):
        terminal=f'T{i+1:02d}';actual=i==0
        vessel='OCEAN HARMONY' if actual else f'VESSEL {i+1:02d}'
        eta=sim.bundle.vessels['OCEAN HARMONY'].get('eta',1800) if actual else 2100+i*900
        used=sum(map(len,sim.yard.values())) if actual else 42+i*5
        capacity=48 if actual else 100
        rows.append({'터미널':terminal,'선박':vessel,'접안 예정':eta,'변동(분)':sim.bundle.vessels['OCEAN HARMONY'].get('delay_minutes',0) if actual else [0,10,-5][i%3], '혼잡도':round(100*used/capacity),'갱신':sim.now})
    return rows

def change_vessel(sim,minutes):
    vessel=sim.bundle.vessels['OCEAN HARMONY']
    old=vessel.get('delay_minutes',0);shift=(minutes-old)*60
    vessel['delay_minutes']=minutes;vessel['eta']=1800+minutes*60
    entries={cid:asdict(PlanEntry(cid,p.sequence,max(0,p.due+shift),p.group)) for cid,p in sim.plan.items()}
    version='P-DEMO-'+stable_hash([sim.now,sim.plan_version,minutes])[:4]
    sim.handle('PLAN_UPDATE',{'version':version,'entries':entries})
    return version,shift

def persist_event(event_id,kind,data,folder=None):
    folder=Path(folder) if folder else Path(__file__).resolve().parents[1]/'runtime'
    folder.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(folder/'demo.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, kind TEXT, payload TEXT)')
        db.execute('INSERT OR REPLACE INTO events VALUES (?,?,?)',(event_id,kind,json.dumps(data,ensure_ascii=False)))
