"""Non-preemptive discrete-event yard, gate and crane simulator."""
from copy import deepcopy
from dataclasses import asdict
import heapq
from domain.models import Observation,PlanEntry,RunResult,ValidationReport,stable_hash,VERSION,ASSUMPTIONS,slot
from adapters.mock import validate_bundle
from engine.yard import locate,rank,duration,feasible,assert_yard
from services.recommend import recommend_slots,propose_premarshal

PRIORITY={'MOVE_END':0,'GATE_SERVICE_END':0,'TRUCK_EXIT':0,'PLAN_UPDATE':1,'FORECAST_UPDATE':1,'TRUCK_ARRIVAL':2,'YARD_ARRIVAL':2,'WAKE':3}

def premarshal_beneficiary(yard,plan,cid):
    """선작업으로 옮기는 화물 아래에서 가장 먼저 인출할 화물(이 이동으로 인출을 준비하는 대상)."""
    src=locate(yard,cid)
    if not src:return None
    below=[x for x in yard[src[0]][:src[1]-1] if rank(plan,x)<rank(plan,cid)]
    return min(below,key=lambda x:rank(plan,x)) if below else None

class Simulator:
    def __init__(self,bundle,policy='C'):
        report=validate_bundle(bundle)
        if not report.valid:raise ValueError('INVALID_INPUT: '+'; '.join(report.errors))
        self.bundle=bundle;self.config=bundle.config;self.policy=policy
        self.now=0;self.yard=deepcopy(bundle.initial_yard);self.plan=dict(bundle.initial_plan)
        self.plan_version='P1';self.yard_version=0;self.forecasts={}
        self.statuses={cid:'STORED' if c.initial else 'EN_ROUTE' for cid,c in bundle.containers.items()}
        self.cranes={'A1':None,'B1':None};self.gate_busy=False;self.reserved={'A1':0,'B1':0}
        self.gate_queue=[];self.yard_arrivals={};self.trucks={};self.retrieved=set()
        self.moves=[];self.decisions=[];self.events=[];self.retrievals=[];self.snapshots=[]
        self.headroom={};self.last_premarshal={};self.idle_used=set();self.accepted={}
        self.manual=False;self.manual_initial=False;self.queue=[];self.serial=0
        self.cargo_checks=set();self.eta_overrides=set()
        # 수동 승인이 필요한 컨테이너(대표 컨테이너). 나머지는 같은 규칙으로 자동 처리합니다.
        self.manual_ids=set();self.forecast_log={}
        self.run_id=f'{policy}-{stable_hash([bundle.config.model_dump(),bundle.truth_events,bundle.initial_yard])}'
        self.termination='RUNNING'
        for e in bundle.truth_events:self.push(e.at,e.kind,deepcopy(e.payload),e.event_id)
        for f in bundle.forecasts:self.push(f.observed_at,'FORECAST_UPDATE',{'forecast':f},f.update_id)
        for p in self.plan.values():self.push(p.due,'WAKE',{},f'DUE-{p.container_id}')
        self.push(0,'WAKE',{})
        self.push(self.config.horizon+self.config.cleanup,'WAKE',{})

    def push(self,at,kind,payload,eid=None):
        self.serial+=1
        heapq.heappush(self.queue,(int(at),PRIORITY[kind],eid or f'INTERNAL-{self.serial:07d}',kind,payload))

    def log(self,kind,cid='',detail=''):
        self.events.append({'at':self.now,'kind':kind,'container_id':cid,'detail':detail,'plan_version':self.plan_version})

    def observe(self):
        locks=set()
        for job in self.cranes.values():
            if job:
                locks.update(k for k in (job['source_stack'],job['target_stack']) if k)
        return Observation(self.now,dict(self.bundle.containers),deepcopy(self.yard),dict(self.plan),dict(self.forecasts),dict(self.statuses),{b:j['end_at'] if j else self.now for b,j in self.cranes.items()},locks,deepcopy(self.headroom),dict(self.yard_arrivals),dict(self.last_premarshal),self.yard_version,self.plan_version,self.config)

    def snapshot(self):
        snap={'at':self.now,'observation':self.observe(),'jobs':deepcopy(self.cranes),'gate_queue':list(self.gate_queue)}
        if self.snapshots and self.snapshots[-1]['at']==self.now:self.snapshots[-1]=snap
        else:self.snapshots.append(snap)

    def handle(self,kind,p):
        cid=p.get('container_id','')
        if kind=='FORECAST_UPDATE':
            f=p['forecast']
            if self.statuses[f.container_id]=='EN_ROUTE' and f.container_id not in self.eta_overrides:
                old=self.forecasts.get(f.container_id);self.forecasts[f.container_id]=f
                if old is None or abs(old.p50-f.p50)>=180:self.forecast_log.setdefault(f.container_id,[]).append(f)
        elif kind=='PLAN_UPDATE':
            new={x:PlanEntry(**entry) for x,entry in p['entries'].items()}
            for x,old in self.plan.items():
                if self.statuses[x]=='IN_MOVE' or old.due<=self.now+300:
                    if new.get(x)!=old:self.log('FROZEN_PLAN',x,'실행 중 또는 5분 내 작업 · 기존 계획 유지')
                    new[x]=old
            self.plan=new;self.plan_version=p['version'];self.headroom.clear()
            for entry in self.plan.values():
                if entry.due>=self.now:self.push(entry.due,'WAKE',{})
            self.log('PLAN_UPDATE',detail=f'{self.plan_version} 발표 · 동결 작업 보존')
        elif kind=='TRUCK_ARRIVAL':
            c=self.bundle.containers[cid];window=self.bundle.vessels[c.vessel_id]
            self.trucks[cid]={'container_id':cid,'gate_arrival':self.now,'gate_start':None,'yard_arrival':None,'unload_start':None,'unload_end':None,'gate_out':None,'exception':False}
            if self.now>window['gate_cutoff']:
                self.statuses[cid]='EXCEPTION_LATE';self.trucks[cid]['exception']=True
                self.log('EXCEPTION_LATE',cid,'게이트 반입 마감 초과');return
            self.gate_queue.append(cid)
            if self.now<window['gate_open']:
                self.statuses[cid]='WAIT_GATE_OPEN';self.push(window['gate_open'],'WAKE',{})
            else:self.statuses[cid]='GATE_QUEUE'
            self.log(kind,cid,'게이트 도착 · 합성 사건')
        elif kind=='GATE_SERVICE_END':
            self.gate_busy=False;self.statuses[cid]='INTERNAL_TRAVEL'
            self.push(self.now+self.config.internal_travel,'YARD_ARRIVAL',{'container_id':cid})
        elif kind=='YARD_ARRIVAL':
            self.statuses[cid]='YARD_QUEUE';self.yard_arrivals[cid]=self.now
            self.trucks[cid]['yard_arrival']=self.now;self.idle_used.discard(self.bundle.containers[cid].block)
            self.log(kind,cid,'CY 하차 대기')
        elif kind=='TRUCK_EXIT':self.trucks[cid]['gate_out']=self.now
        elif kind=='MOVE_END':
            b=p['block'];job=self.cranes[b]
            assert job and job['move_id']==p['move_id']
            cid=job['container_id'];src=job['source_stack'];dst=job['target_stack']
            if src:
                assert self.yard[src][-1]==cid
                self.yard[src].pop()
            if dst:self.yard[dst].append(cid)
            self.yard_version+=1;job['completed']=True;self.cranes[b]=None
            if job['move_type']=='RETRIEVE':
                self.statuses[cid]='RETRIEVED';self.retrieved.add(cid)
                self.retrievals.append({'container_id':cid,'completed_at':self.now,'due_at':job['retrieval_due_at'],'delay_seconds':max(0,self.now-job['retrieval_due_at'])})
                self.headroom={k:r for k,r in self.headroom.items() if r['container_id']!=cid}
            else:
                self.statuses[cid]='STORED'
                if job['move_type']=='INITIAL':
                    self.trucks[cid]['unload_end']=self.now
                    self.push(self.now+self.config.exit_travel,'TRUCK_EXIT',{'container_id':cid})
                    if self.policy=='C' and self.config.headroom and cid in self.plan and len(self.yard[dst])<4:
                        priority=sorted(self.plan,key=lambda x:rank(self.plan,x))[:max(1,int(len(self.plan)*.3))]
                        if cid in priority and not any(k.startswith(b) for k in self.headroom):
                            self.headroom[dst]={'container_id':cid,'until':self.now+1200,'plan_version':self.plan_version}
                            self.push(self.now+1200,'WAKE',{})
                elif job['move_type']=='PREMARSH':self.last_premarshal[cid]=self.now
            if job.get('recommendation_id') in self.accepted:self.accepted[job['recommendation_id']]['status']='COMPLETED'
            if job['move_type']!='PREMARSH':self.idle_used.discard(b)
            self.log('MOVE_END',cid,f"{job['move_type']} · {job['source_slot'] or 'GATE'} → {job['target_slot'] or 'VESSEL'}")
            assert_yard(self.yard,self.bundle.containers,self.config.stack_weight_limit)

    def start_move(self,cid,kind,target=None,recommendation_id=None,for_cid=None):
        c=self.bundle.containers[cid];b=c.block;source=locate(self.yard,cid)
        src=source[0] if source else None
        if self.cranes[b] or self.statuses[cid]=='IN_MOVE':return False
        if kind=='INITIAL' and cid not in self.yard_arrivals:return False
        if kind!='INITIAL' and (not src or self.yard[src][-1]!=cid):return False
        if target and target not in feasible(self.observe(),cid,src,ignore_headroom=kind=='REHANDLE'):return False
        dt=duration(self.config,src,target)
        job={'run_id':self.run_id,'move_id':f'M-{len(self.moves)+1:05d}','container_id':cid,'move_type':kind,'source_stack':src,'target_stack':target,'source_slot':slot(src,source[1]) if src else '', 'target_slot':slot(target,len(self.yard[target])+1) if target else '', 'start_at':self.now,'end_at':self.now+dt,'crane_id':f'YC-{b}','reason_code':'ACCESSIBILITY_GAIN' if kind=='PREMARSH' else 'PLAN_SEQUENCE' if kind in ('RETRIEVE','REHANDLE') else 'LOWEST_ROLLOUT_COST','plan_version':self.plan_version,'completed':False,'recommendation_id':recommendation_id,'retrieval_due_at':self.plan[cid].due if cid in self.plan else None,'for_container':for_cid or ''}
        self.moves.append(job);self.cranes[b]=job;self.statuses[cid]='IN_MOVE'
        # Reservations change recommendation validity even before occupancy commits.
        self.yard_version+=1
        if kind=='INITIAL':
            self.trucks[cid]['unload_start']=self.now;self.yard_arrivals.pop(cid);self.reserved[b]-=1
        self.push(self.now+dt,'MOVE_END',{'block':b,'move_id':job['move_id']})
        self.log('MOVE_START',cid,f'{kind} · YC-{b}')
        return True

    def record_decision(self,rec,selected=None,status='AUTO'):
        for candidate in rec.candidates:
            self.decisions.append({'at':self.now,'run_id':self.run_id,'recommendation_id':rec.recommendation_id,'container_id':rec.container_id,'action':rec.action,'target_slot':slot(candidate.stack,candidate.tier),'score':candidate.score,'score_low':candidate.low,'score_high':candidate.high,'extra_seconds':candidate.extra_seconds,'wait_seconds':candidate.wait_seconds,'delay_seconds':candidate.delay_seconds,'blocked_pairs':candidate.blocked_pairs,'chosen':candidate.stack==selected,'status':status if candidate.stack==selected else 'REJECTED','reason_codes':'|'.join(candidate.reason_codes) if candidate.stack==selected else 'HIGHER_COST_OR_CONSTRAINT','yard_version':rec.yard_version,'plan_version':rec.plan_version})

    def dispatch(self):
        self.headroom={k:r for k,r in self.headroom.items() if r['until']>self.now and r['plan_version']==self.plan_version}
        if not self.gate_busy:
            for cid in list(self.gate_queue):
                c=self.bundle.containers[cid]
                if self.now<self.bundle.vessels[c.vessel_id]['gate_open'] or self.reserved[c.block]>=self.config.queue_limit:continue
                self.gate_queue.remove(cid);self.gate_busy=True;self.reserved[c.block]+=1
                self.statuses[cid]='GATE_SERVICE';self.trucks[cid]['gate_start']=self.now
                self.push(self.now+self.config.gate_service,'GATE_SERVICE_END',{'container_id':cid});break
        next_targets={}
        for vessel in self.bundle.vessels:
            ordered=sorted((x for x in self.plan if self.bundle.containers[x].vessel_id==vessel and self.statuses[x] not in ('RETRIEVED','EXCEPTION_LATE')),key=lambda x:(rank(self.plan,x),x))
            if ordered and self.plan[ordered[0]].due<=self.now:next_targets[self.bundle.containers[ordered[0]].block]=ordered[0]
        for b in self.cranes:
            if self.cranes[b]:continue
            waiting=sorted((x for x in self.yard_arrivals if self.bundle.containers[x].block==b and x not in self.manual_ids),key=lambda x:(self.yard_arrivals[x],x))
            old_truck=bool(waiting and self.now-self.yard_arrivals[waiting[0]]>900)
            def unload():
                if not waiting or self.manual_initial:return False
                cid=waiting[0];o=self.observe();rec=recommend_slots(o,cid,self.policy)
                if not rec.candidates and self.headroom:
                    protected=deepcopy(self.headroom);self.headroom.clear()
                    rec=recommend_slots(self.observe(),cid,self.policy)
                    if not rec.candidates:self.headroom=protected
                    else:self.log('HEADROOM_RELEASE',cid,'공간 부족으로 상부 보호 해제')
                if not rec.candidates:
                    self.statuses[cid]='BLOCKED_CAPACITY';return False
                dst=rec.candidates[0].stack
                self.record_decision(rec,dst)
                return self.start_move(cid,'INITIAL',dst)
            if old_truck and unload():continue
            target=next_targets.get(b)
            if target and self.statuses[target]=='STORED':
                src=locate(self.yard,target)[0]
                if self.yard[src][-1]==target:
                    if self.start_move(target,'RETRIEVE'):continue
                else:
                    blocker=self.yard[src][-1];o=self.observe();keys=feasible(o,blocker,src,ignore_headroom=True)
                    if keys:
                        dst=min(keys,key=lambda k:(sum(rank(self.plan,x)<rank(self.plan,blocker) for x in self.yard[k]),duration(self.config,src,k),k))
                        if self.start_move(blocker,'REHANDLE',dst,for_cid=target):continue
                    else:self.log('BLOCKED_CAPACITY',target,'인출 재취급 목적지 없음')
            if unload():continue
            if self.policy=='C' and self.config.premarshal and not self.manual and b not in self.idle_used and not waiting:
                rec=propose_premarshal(self.observe(),b)
                if rec:
                    self.record_decision(rec,rec.candidates[0].stack)
                    if self.start_move(rec.container_id,'PREMARSH',rec.candidates[0].stack,for_cid=premarshal_beneficiary(self.yard,self.plan,rec.container_id)):self.idle_used.add(b)

    def advance(self,until=None,one_event=False):
        end=self.config.horizon+self.config.cleanup
        until=min(until if until is not None else end,end)
        while self.queue and self.queue[0][0]<=until:
            self.now=self.queue[0][0]
            while self.queue and self.queue[0][0]==self.now:
                _,_,_,kind,p=heapq.heappop(self.queue);self.handle(kind,p)
            self.dispatch();self.snapshot()
            if one_event:break
        if not one_event and self.now<until:
            self.now=until;self.snapshot()
        if self.now>=end or not self.queue:
            remaining=sum(s not in ('RETRIEVED','EXCEPTION_LATE') for s in self.statuses.values())
            self.termination='COMPLETED' if remaining==0 else 'CAPACITY_DEADLOCK' if any(s=='BLOCKED_CAPACITY' for s in self.statuses.values()) else 'INCOMPLETE'
        return self

    def validate_action(self,rec,candidate):
        errors=[]
        if rec.yard_version!=self.yard_version or rec.plan_version!=self.plan_version or self.now>rec.valid_until:errors.append('STALE_RECOMMENDATION · 입력 버전 또는 유효기간이 변경되었습니다.')
        cid=rec.container_id;src=locate(self.yard,cid);b=self.bundle.containers[cid].block
        if self.cranes[b]:errors.append('RESOURCE_BUSY · 크레인 작업 중')
        if candidate.stack not in feasible(self.observe(),cid,src[0] if src else None):errors.append('NO_FEASIBLE_SLOT · 슬롯 제약 위반')
        if rec.action=='INITIAL' and cid not in self.yard_arrivals:errors.append('NOT_ARRIVED · CY 도착 후 승인할 수 있습니다.')
        if self.bundle.containers[cid].cargo_type!='일반' and cid not in self.cargo_checks:errors.append('CARGO_REVIEW · 특수화물 검토 확인이 필요합니다.')
        if rec.action=='PREMARSH':
            allowed=propose_premarshal(self.observe(),b)
            if not allowed or allowed.container_id!=cid or candidate.stack not in [c.stack for c in allowed.candidates]:errors.append('NO_SAFE_GAIN · 필수 작업·여유시간·개선 조건 미충족')
        return ValidationReport(errors)

    def approve(self,rec,index=0):
        if rec.recommendation_id in self.accepted:return ValidationReport()
        if not 0<=index<len(rec.candidates):return ValidationReport(['NO_FEASIBLE_SLOT'])
        c=rec.candidates[index];report=self.validate_action(rec,c)
        if not report.valid:return report
        self.accepted[rec.recommendation_id]={'status':'APPROVED','container_id':rec.container_id}
        self.log('APPROVED',rec.container_id,rec.recommendation_id)
        self.accepted[rec.recommendation_id]['status']='QUEUED';self.log('QUEUED',rec.container_id,rec.recommendation_id)
        beneficiary=premarshal_beneficiary(self.yard,self.plan,rec.container_id) if rec.action=='PREMARSH' else None
        if self.start_move(rec.container_id,rec.action,c.stack,rec.recommendation_id,beneficiary):
            self.accepted[rec.recommendation_id]['status']='EXECUTING';self.record_decision(rec,c.stack,'APPROVED');self.snapshot()
        else:
            self.accepted.pop(rec.recommendation_id);return ValidationReport(['ACTION_REVALIDATION_FAILED'])
        return report

    def result(self):
        from services.metrics import compute_metrics
        metrics=compute_metrics(self.moves,list(self.trucks.values()),self.retrievals,self.now,len(self.bundle.containers),self.statuses)
        manifest={'run_id':self.run_id,'policy':self.policy,'policy_version':VERSION,'assumption_version':ASSUMPTIONS,'data_mode':'synthetic','mode':'manual' if self.manual else 'automatic','seed':self.config.seed,'scenario_hash':stable_hash([self.bundle.containers,self.bundle.initial_yard,self.bundle.initial_plan]),'truth_hash':stable_hash(self.bundle.truth_events),'forecast_hash':stable_hash(self.bundle.forecasts),'config_hash':stable_hash(self.config),'target_count':len(self.bundle.containers),'initial_count':sum(c.initial for c in self.bundle.containers.values()),'actual_occupancy':sum(map(len,self.bundle.initial_yard.values()))/48,'termination':self.termination,'observed_until':self.now,'config':self.config.model_dump()}
        return RunResult(self.policy,self.run_id,deepcopy(self.moves),deepcopy(list(self.trucks.values())),deepcopy(self.retrievals),deepcopy(self.decisions),deepcopy(self.events),list(self.snapshots),metrics,manifest)

def run_simulation(bundle,policy='C',config=None):
    if config is not None and config!=bundle.config:raise ValueError('Config must match generated scenario')
    return Simulator(bundle,policy).advance().result()

def observe(state,now=None):
    if now is not None and now!=state.now:raise ValueError('Observation requires current simulation time')
    return state.observe()

def validate_action(state,action):
    return state.validate_action(action,action.candidates[0]) if action.candidates else ValidationReport(['NO_FEASIBLE_SLOT'])
