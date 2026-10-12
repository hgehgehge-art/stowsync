from statistics import mean,median
import csv,io,json,zipfile
from domain.models import ASSUMPTIONS

def percentile(values,p):
    if not values:return 0.
    a=sorted(values);i=(len(a)-1)*p;lo=int(i);hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(i-lo)

def describe(values):
    return {'mean':mean(values) if values else None,'median':median(values) if values else None,'p95':percentile(values,.95) if values else None,'n':len(values)}

def compute_metrics(move_log,truck_log,retrieval_log,now=None,target_count=None,statuses=None):
    now=now if now is not None else max([m['end_at'] for m in move_log],default=1)
    done=[m for m in move_log if m['completed'] and m['end_at']<=now]
    kinds={k:sum(m['move_type']==k for m in done) for k in ('INITIAL','PREMARSH','REHANDLE','RETRIEVE')}
    arrived=[t for t in truck_log if t['gate_arrival']<=now]
    completed=[t for t in arrived if t['gate_out'] is not None and t['gate_out']<=now]
    waits=[(t['gate_start']-t['gate_arrival'])+(t['unload_start']-t['yard_arrival']) for t in completed]
    dwell=[t['gate_out']-t['gate_arrival'] for t in completed]
    delays=[t['delay_seconds'] for t in retrieval_log if t['completed_at']<=now]
    busy=sum(max(0,min(now,m['end_at'])-m['start_at']) for m in move_log if m['start_at']<=now)
    ongoing_wait=0
    for t in arrived:
        if t['exception']:continue
        ongoing_wait+=max(0,(t['gate_start'] if t['gate_start'] is not None and t['gate_start']<=now else now)-t['gate_arrival'])
        if t['yard_arrival'] is not None and t['yard_arrival']<=now:ongoing_wait+=max(0,(t['unload_start'] if t['unload_start'] is not None and t['unload_start']<=now else now)-t['yard_arrival'])
    extra=kinds['PREMARSH']+kinds['REHANDLE']
    return {**kinds,'extra_moves':extra,'crane_moves':len(done),'extra_per_box':extra/target_count if target_count else None,'truck_wait':describe(waits),'truck_dwell':describe(dwell),'retrieval_delay':describe(delays),'truck_completed':len(completed),'truck_arrived':len(arrived),'truck_completion_rate':len(completed)/len(arrived) if arrived else None,'truck_incomplete':sum(not t['exception'] and (t['gate_out'] is None or t['gate_out']>now) for t in arrived),'exceptions':sum(t['exception'] for t in arrived),'incomplete':sum(s not in ('RETRIEVED','EXCEPTION_LATE') for s in statuses.values()) if statuses else max(0,(target_count or 0)-kinds['RETRIEVE']),'busy_seconds':busy,'crane_utilization':busy/(max(now,1)*2),'accumulated_wait_seconds':ongoing_wait}

def eta_accuracy(bundle,now,lead=1800):
    errors=[];coverage=[];missing=0
    for e in bundle.truth_events:
        if e.kind!='TRUCK_ARRIVAL' or e.at>now:continue
        fs=[f for f in bundle.forecasts if f.container_id==e.payload['container_id'] and f.observed_at<=e.at-lead]
        if not fs:missing+=1;continue
        f=max(fs,key=lambda f:f.observed_at);errors.append(abs(e.at-f.p50));coverage.append(f.p10<=e.at<=f.p90)
    return {'mae':mean(errors) if errors else None,'p90':percentile(errors,.9) if errors else None,'coverage':mean(coverage) if coverage else None,'n':len(errors),'missing':missing}

def csv_bytes(rows):
    if not rows:return b'\xef\xbb\xbfdata_mode,assumption_version\n'
    rows=[{**r,'data_mode':'synthetic','assumption_version':ASSUMPTIONS} for r in rows]
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')

def export_zip(results):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        summaries=[]
        for key,r in results.items():
            z.writestr(f'{key}/move_log.csv',csv_bytes(r.moves))
            z.writestr(f'{key}/decision_log.csv',csv_bytes(r.decisions))
            z.writestr(f'{key}/truck_log.csv',csv_bytes(r.trucks))
            z.writestr(f'{key}/retrieval_log.csv',csv_bytes(r.retrievals))
            z.writestr(f'{key}/run_manifest.json',json.dumps(r.manifest,ensure_ascii=False,indent=2))
            summaries.append({'policy':key,'run_id':r.run_id,**{k:v for k,v in r.metrics.items() if not isinstance(v,dict)},'truck_wait_mean':r.metrics['truck_wait']['mean'],'truck_wait_p95':r.metrics['truck_wait']['p95'],'retrieval_delay_mean':r.metrics['retrieval_delay']['mean']})
        z.writestr('summary.csv',csv_bytes(summaries))
    return out.getvalue()
