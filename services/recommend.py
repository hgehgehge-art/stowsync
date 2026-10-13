"""Eight shared 60-minute rollouts; a fixed greedy inner policy avoids recursion."""
from copy import deepcopy
from statistics import mean
from domain.models import Candidate, Recommendation, stable_hash
from engine.yard import feasible,locate,rank,blockers,duration,cargo_allowed
from services.eta import sample_arrivals

def rollout(o,sampled,cid=None,target=None,action='INITIAL',counts=False):
    yard={k:list(v) for k,v in o.yard.items()}
    busy={k:max(o.now,t) for k,t in o.crane_busy_until.items()}
    extra=wait=delay=0.; cutoff=o.now+o.config.lookahead
    rehandles=premarshals=0
    present={x for items in yard.values() for x in items}
    arrival=dict(sampled)
    if cid is not None and target:
        source=locate(yard,cid)
        start=max(o.now,busy[o.containers[cid].block],arrival.get(cid,o.now) if action=='INITIAL' else o.now)
        dt=duration(o.config,source[0] if source else None,target)
        if source: yard[source[0]].remove(cid)
        yard[target].append(cid); present.add(cid)
        busy[o.containers[cid].block]=start+dt
        if action=='PREMARSH': extra+=dt;premarshals+=1
        else: wait+=max(0,start-arrival.get(cid,o.now))
        arrival.pop(cid,None)
    def destinations(box,source=None):
        return [k for k,v in yard.items() if k.startswith(o.containers[box].block) and k!=source and len(v)<4 and sum(o.containers[x].weight_t for x in v)+o.containers[box].weight_t<=o.config.stack_weight_limit and cargo_allowed(o.containers,box,k,v)]
    def greedy(box,keys):
        return min(keys,key=lambda k:(sum(rank(o.plan,x)<rank(o.plan,box) for x in yard[k]),len(yard[k]),k))
    pending=sorted(((t,x) for x,t in arrival.items() if t<=cutoff),key=lambda z:(z[0],z[1]))
    ordered=sorted((p for x,p in o.plan.items() if o.statuses.get(x) not in ('RETRIEVED','EXCEPTION_LATE')),key=lambda p:rank(o.plan,p.container_id))
    def insert_until(t):
        nonlocal wait
        retry=[]
        while pending and pending[0][0]<=t:
            at,box=pending.pop(0)
            if box in present: continue
            keys=destinations(box)
            if not keys: retry.append((at,box));continue
            key=greedy(box,keys); b=o.containers[box].block
            start=max(at,busy[b],o.now)
            wait+=max(0,start-at)
            busy[b]=start+duration(o.config,None,key)
            yard[key].append(box);present.add(box)
        pending[:0]=retry
    for p in ordered:
        if p.due>cutoff: break
        box=p.container_id
        insert_until(max(o.now,p.due))
        if box not in present:
            at=arrival.get(box,cutoff+1)
            insert_until(min(cutoff,at))
            if box not in present:
                delay+=max(0,cutoff-p.due);break
        src=locate(yard,box)[0];b=o.containers[box].block
        busy[b]=max(o.now,busy[b],p.due)
        blocked=False
        while yard[src][-1]!=box:
            above=yard[src][-1];keys=destinations(above,src)
            if not keys: blocked=True;break
            dest=greedy(above,keys);dt=duration(o.config,src,dest)
            extra+=dt;busy[b]+=dt;rehandles+=1
            yard[src].pop();yard[dest].append(above)
        if blocked:
            delay+=max(0,cutoff-p.due);break
        busy[b]+=duration(o.config,src,None)
        delay+=max(0,busy[b]-p.due)
        yard[src].pop();present.remove(box)
    insert_until(cutoff)
    wait+=sum(max(0,cutoff-at) for at,_ in pending)
    pairs=len(blockers(yard,o.plan)[1])
    values=(extra,.5*wait,2*delay,60*pairs)
    return values+(rehandles,premarshals) if counts else values

def evaluate(o,cid,key,samples,action):
    components=[rollout(o,s,cid,key,action,counts=True) for s in samples]
    vals=[sum(x[:4]) for x in components]
    src=locate(o.yard,cid)
    means=[mean(v[i] for v in components) for i in range(4)]
    earlier=sum(rank(o.plan,x)<rank(o.plan,cid) for x in o.yard[key])
    reasons=['NO_EARLIER_BOX_BELOW' if earlier==0 else 'BLOCKING_TRADEOFF','HEIGHT_WEIGHT_VALID']
    if not o.yard[key]: reasons.append('EMPTY_STACK')
    if cid not in o.plan: reasons.append('UNKNOWN_PRIORITY')
    return Candidate(key,len(o.yard[key])+1,mean(vals),means[0],means[1]/.5,means[2]/2,means[3]/60,min(vals),max(vals),vals,reasons,duration(o.config,src[0] if src else None,key),mean(x[4] for x in components),mean(x[5] for x in components))

def recommend_slots(o,cid,policy='C',action='INITIAL'):
    src=locate(o.yard,cid)
    candidates=[]
    reason=''
    if action=='PREMARSH' and (not src or o.yard[src[0]][-1]!=cid or o.statuses[cid]=='IN_MOVE'):
        reason='최상단의 이동 가능한 컨테이너만 사전 이동할 수 있습니다.'
    elif action=='INITIAL' and src:
        reason='이미 야드에 적치된 컨테이너입니다.'
    else:
        samples=sample_arrivals(o,policy)
        candidates=[evaluate(o,cid,k,samples,action) for k in feasible(o,cid,src[0] if src else None)]
        candidates.sort(key=lambda x:(x.score,x.move_seconds,x.stack))
    rid=stable_hash([cid,action,o.now,o.yard_version,o.plan_version,policy])
    return Recommendation(rid,cid,action,o.now,o.now+60,o.yard_version,o.plan_version,candidates,reason=reason or ('' if candidates else 'NO_FEASIBLE_SLOT · 합법적인 빈 위치가 없습니다.'))

def propose_premarshal(o,block=None):
    risks,_=blockers(o.yard,o.plan)
    candidates=[]
    samples=sample_arrivals(o,'C')
    keep=[sum(rollout(o,s)) for s in samples]
    for key,items in o.yard.items():
        if not items or (block and not key.startswith(block)):continue
        cid=items[-1];b=o.containers[cid].block
        if cid not in risks or o.statuses[cid]!='STORED' or o.crane_busy_until[b]>o.now:continue
        if o.now-o.last_premarshal.get(cid,-10000)<600:continue
        if any(o.containers[x].block==b for x in o.yard_arrivals):continue
        upcoming=[];missing=False
        for x,c in o.containers.items():
            if c.block!=b:continue
            if o.statuses[x] in ('GATE_QUEUE','WAIT_GATE_OPEN','GATE_SERVICE','INTERNAL_TRAVEL','YARD_QUEUE','BLOCKED_CAPACITY'):missing=True
            if o.statuses[x]=='EN_ROUTE':
                f=o.forecasts.get(x)
                if not f or o.now-f.observed_at>=o.config.eta_stale or f.trust_score<o.config.min_eta_trust or f.p90-f.p10>1800:missing=True
                else:upcoming.append(f.p10)
            if x in o.plan and o.statuses[x] not in ('RETRIEVED','EXCEPTION_LATE'):upcoming.append(o.plan[x].due)
        if missing:continue
        rec=recommend_slots(o,cid,'C','PREMARSH')
        eligible=[]
        for candidate in rec.candidates:
            if min(upcoming,default=o.now+99999)-o.now<=candidate.move_seconds+120:continue
            non_worse=sum(a<=b for a,b in zip(candidate.sample_scores,keep))
            if mean(keep)-candidate.score>=o.config.min_gain and non_worse>=max(1,(o.config.samples*3+3)//4):eligible.append(candidate)
        if eligible:
            rec.candidates=eligible;rec.keep_score=mean(keep)
            rec.keep_rehandles=mean(rollout(o,s,counts=True)[4] for s in samples)
            rec.non_worse=sum(a<=b for a,b in zip(eligible[0].sample_scores,keep))
            candidates.append(rec)
    return max(candidates,key=lambda r:r.keep_score-r.candidates[0].score) if candidates else None
