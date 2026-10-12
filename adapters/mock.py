"""Reproducible synthetic input, generated once independently of policy RNG."""
import random
from dataclasses import asdict
from domain.models import Config, Container, Forecast, PlanEntry, Event, ScenarioBundle, ValidationReport, stack_keys

def build_scenario(config: Config, seed=None) -> ScenarioBundle:
    cfg = config.model_copy(update={"seed": config.seed if seed is None else seed})
    rng = random.Random(cfg.seed)
    occupancy = .9 if cfg.preset == "capacity" else cfg.occupancy
    initial_count = min(cfg.target_count - 4, round(48 * occupancy))
    containers, yard, plan, forecasts, events = {}, {k: [] for k in stack_keys()}, {}, [], []
    n = cfg.target_count
    for i in range(n):
        cid = f"SYNC{2600001+i:07d}"
        block = "A1" if i % 2 == 0 else "B1"
        initial = i < initial_count
        # Initial inventory deliberately includes inverted stacks, never invalid tiers.
        arrival = max(0, int(1000 + (i-initial_count) * 105 + rng.gauss(0, 320)))
        if rng.random() < cfg.concentration: arrival = max(120, int(2100 + rng.gauss(0, 250)))
        booking = arrival + rng.choice([-1400, -700, 0, 700, 1400])
        if cfg.preset == "normal": booking = arrival
        if cfg.preset.startswith("early"): booking = arrival + 1500
        if cfg.preset.startswith("late"): booking = arrival - 1500
        if cfg.preset == "surprise" and i == initial_count: arrival, booking = 35, 1600
        if cfg.preset == "cutoff" and i >= n-5: arrival = 11000 + (i-n+5)*90
        containers[cid] = Container(cid, "OCEAN HARMONY", block, max(0, booking-300), max(600, booking+300), round(rng.uniform(12, 25), 1), initial)
        if initial:
            choices = [k for k in yard if k.startswith(block) and len(yard[k]) < 4 and sum(containers[x].weight_t for x in yard[k]) + containers[cid].weight_t <= cfg.stack_weight_limit]
            if not choices:
                raise ValueError("initial_yard: 초기 점유율과 스택 하중 한도를 동시에 만족할 수 없습니다.")
            # Packed initial stacks create meaningful blocking examples.
            key = choices[0] if i < 10 else rng.choice(choices)
            yard[key].append(cid)
        else:
            events.append(Event(arrival, "TRUCK_ARRIVAL", f"ARR-{cid}", {"container_id": cid}))
            err_scale = cfg.eta_error * (2.6 if cfg.preset == "uncertain" else 1)
            for observed in range(0, arrival, 300):
                bias = rng.gauss(0, err_scale * max(.22, (arrival-observed)/max(arrival,1)))
                if cfg.preset == "surprise" and i == initial_count: bias = 1800
                mid = max(observed, int(arrival + bias))
                width = max(120, int(err_scale*.7))
                f = Forecast(f"ETA-{cid}-{observed}", observed, cid, max(observed, mid-width), mid, mid+width)
                forecasts.append(f)
        due = 1800 + i * 110
        if i >= initial_count: due = max(due, arrival + 900)
        plan[cid] = PlanEntry(cid, i+1, due, 1+i//20)
    if cfg.preset.endswith("priority"):
        focus = list(containers)[initial_count]
        ordered = [focus] + [x for x in containers if x != focus]
        plan = {cid: PlanEntry(cid, j+1, 1800+j*110, 1+j//20) for j,cid in enumerate(ordered)}
    if cfg.plan_changes or cfg.preset == "reversal":
        ordered = list(plan)
        # Publish all changes at 35 minutes; never leak them to earlier observations.
        future = ordered[12:]
        if cfg.preset == "reversal": future.reverse()
        else: rng.shuffle(future)
        ordered = ordered[:12] + future
        changed = {cid: asdict(PlanEntry(cid,j+1,max(2400,2700+j*90),1+j//20)) for j,cid in enumerate(ordered)}
        events.append(Event(2100,"PLAN_UPDATE","PLAN-P2",{"version":"P2","entries":changed}))
    vessels = {"OCEAN HARMONY": {"gate_open": 0, "gate_cutoff": 10800}}
    return ScenarioBundle(cfg, containers, yard, plan, forecasts, events, vessels)

def validate_bundle(bundle: ScenarioBundle) -> ValidationReport:
    errors, seen = [], set()
    for i,(key,c) in enumerate(bundle.containers.items(),1):
        prefix=f"containers.csv 행 {i}"
        if key != c.container_id: errors.append(f"{prefix} container_id: 키 불일치")
        if c.vessel_id not in bundle.vessels: errors.append(f"{prefix} vessel_id: 선박 없음")
        if c.booking_start > c.booking_end: errors.append(f"{prefix} booking_start: 예약 시간 역전")
        if c.size_ft != 20 or c.weight_t <= 0: errors.append(f"{prefix} size_ft/weight_t: 20ft, 양수 중량 필요")
        if c.block not in ("A1","B1"): errors.append(f"{prefix} block: 지원하지 않는 블록")
    for key, items in bundle.initial_yard.items():
        if key not in stack_keys() or len(items)>4: errors.append(f"initial_yard.csv {key}: 슬롯 범위 초과")
        weight=0
        for cid in items:
            if cid in seen or cid not in bundle.containers: errors.append(f"initial_yard.csv {key} container_id: 중복/누락 {cid}")
            else:
                c=bundle.containers[cid]
                weight += c.weight_t
                if not key.startswith(c.block): errors.append(f"initial_yard.csv {key}: 블록 불일치")
            seen.add(cid)
        if weight > bundle.config.stack_weight_limit: errors.append(f"initial_yard.csv {key}: 하중 초과")
    for cid,c in bundle.containers.items():
        if c.initial != (cid in seen): errors.append(f"initial_yard.csv {cid}: 초기 재고 상태 불일치")
    for i,f in enumerate(bundle.forecasts,1):
        if f.container_id not in bundle.containers or not (f.observed_at <= f.p10 <= f.p50 <= f.p90): errors.append(f"eta_updates.csv 행 {i} p10/p50/p90: 참조 또는 시간 오류")
    for cid,p in bundle.initial_plan.items():
        if cid not in bundle.containers or p.sequence<=0: errors.append(f"load_plan.csv {cid}: 참조/순서 오류")
    for v,w in bundle.vessels.items():
        if w['gate_open']>=w['gate_cutoff']: errors.append(f"vessels.csv {v}: 반입 시간 오류")
    ids=[e.event_id for e in bundle.truth_events]
    if len(ids)!=len(set(ids)): errors.append("truth_events.jsonl event_id: 중복")
    for e in bundle.truth_events:
        if e.at<0: errors.append(f"truth_events.jsonl {e.event_id}: 음수 시각")
        if e.kind=='TRUCK_ARRIVAL' and e.payload.get('container_id') not in bundle.containers: errors.append(f"truth_events.jsonl {e.event_id}: 컨테이너 없음")
    return ValidationReport(errors)
