from domain.models import Observation

def locate(yard, cid):
    for key, items in yard.items():
        if cid in items: return key, items.index(cid)+1
    return None

def rank(plan,cid):
    p=plan.get(cid)
    return (p.group,p.sequence) if p else (9999,9999)

def blockers(yard,plan):
    boxes, pairs=set(),[]
    for key,items in yard.items():
        for i,cid in enumerate(items):
            for above in items[i+1:]:
                if rank(plan,cid)<rank(plan,above):
                    boxes.add(above); pairs.append((cid,above))
    return boxes,pairs

def duration(config,source,target):
    def xy(k):
        return tuple(map(int,k.split('-')[1:3])) if k else (0,0)
    a,b=xy(source),xy(target)
    return config.handling+15*abs(a[0]-b[0])+10*abs(a[1]-b[1])

def feasible(o: Observation,cid,source=None,ignore_headroom=False):
    c=o.containers[cid]
    result=[]
    for key,items in o.yard.items():
        if not key.startswith(c.block) or key==source or key in o.locked_stacks: continue
        if len(items)>=4 or sum(o.containers[x].weight_t for x in items)+c.weight_t>o.config.stack_weight_limit: continue
        reservation=o.headroom.get(key)
        if not ignore_headroom and reservation and reservation['until']>o.now and reservation['plan_version']==o.plan_version and reservation['container_id']!=cid: continue
        # Unknown priorities are accepted only into empty stacks; no invented order.
        if cid not in o.plan and items: continue
        result.append(key)
    return result

def assert_yard(yard,containers,limit):
    seen=set()
    for k,items in yard.items():
        assert len(items)<=4, 'HEIGHT_EXCEEDED'
        assert sum(containers[x].weight_t for x in items)<=limit+1e-8, 'WEIGHT_EXCEEDED'
        for cid in items:
            assert cid not in seen,'DUPLICATE_OCCUPANCY'
            assert k.startswith(containers[cid].block),'CROSS_BLOCK_MOVE'
            seen.add(cid)
