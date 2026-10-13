import random
from domain.models import stable_hash

def eta_status(c,forecast,now,config):
    if forecast is None or now-forecast.observed_at>=config.eta_stale:
        return '정보 부족',True
    lo,hi=c.booking_start-config.tolerance,c.booking_end+config.tolerance
    state='조기' if forecast.p50<lo else '지연' if forecast.p50>hi else '정상'
    uncertain=forecast.p10<lo<forecast.p90 or forecast.p10<hi<forecast.p90
    return state,uncertain

def sample_arrivals(o,policy):
    """Common random numbers across candidates, independent from truth generation."""
    rng=random.Random(int(stable_hash([o.config.seed,o.now,'public-eta-samples']),16))
    result=[]
    for _ in range(o.config.samples):
        sampled={}
        for cid,c in o.containers.items():
            if o.statuses.get(cid) in ('RETRIEVED','EXCEPTION_LATE','STORED','IN_MOVE'): continue
            if cid in o.yard_arrivals:
                sampled[cid]=o.yard_arrivals[cid]; continue
            u=rng.random(); f=o.forecasts.get(cid)
            if policy=='A' or f is None or o.now-f.observed_at>=o.config.eta_stale or f.trust_score<o.config.min_eta_trust:
                begin=max(o.now,c.booking_start)
                end=c.booking_end if c.booking_end>begin else begin+max(60,c.booking_end-c.booking_start)
                t=begin+u*(end-begin)
            else:
                spread=max(f.p90-f.p10,60)
                points=[(0,f.p10-spread),(.1,f.p10),(.5,f.p50),(.9,f.p90),(1,f.p90+spread)]
                for (a,x),(b,y) in zip(points,points[1:]):
                    if a<=u<=b:
                        t=x+(u-a)/(b-a)*(y-x);break
            sampled[cid]=max(o.now,int(t))+o.config.gate_service+o.config.internal_travel
        result.append(sampled)
    return result
