"""Interactive workflow panels for the proposal demo."""
from dataclasses import asdict
from html import escape
from uuid import uuid4
import json
import streamlit as st
from domain.models import Config, slot
from engine.yard import locate,rank
from services.recommend import propose_premarshal,recommend_slots
from services.workflows import (RULES,quadrant,demo_history,predict_arrival,terminal_feed,change_vessel,persist_event)
from engine.simulator import premarshal_beneficiary
from services.metrics import csv_bytes
from ui.theme import html,badge,panel,metric,table,tm,allcone
from ui.scene import yard_figure


def ensure_workflows():
    defaults={'notices':[],'guides':{},'eta_inputs':{},'session_id':str(uuid4()),'review_log':[],'held':set(),'capture_mode':False}
    for key,value in defaults.items():
        if key not in st.session_state:st.session_state[key]=value


def notify_demo(sim,title,detail,roles=('플래너','관제 담당자','운송기사','선사')):
    st.session_state.notices.insert(0,{'id':str(uuid4()),'at':tm(sim.now),'title':title,'detail':detail,'roles':list(roles),'read':[],'version':sim.plan_version})


def record_approval(sim,rec,index,reason):
    """승인 결과를 기사 안내와 알림으로 넘기고 중립 이력으로 남깁니다. 판단을 채점하거나 학습에 쓰지 않습니다."""
    chosen=rec.candidates[index]
    persist_event(st.session_state.session_id+rec.recommendation_id,'decision',{'container':rec.container_id,'action':rec.action,'slot':slot(chosen.stack,chosen.tier),'reason':reason,'plan':rec.plan_version})
    if rec.action=='INITIAL':
        guide={'id':rec.recommendation_id,'container':rec.container_id,'slot':slot(chosen.stack,chosen.tier),'block':sim.bundle.containers[rec.container_id].block,'at':tm(sim.now),'plan':rec.plan_version,'ack':False,'reason':reason}
        st.session_state.guides[rec.container_id]=guide
        notify_demo(sim,'하차 위치 승인',f'{rec.container_id} · {guide["slot"]} · 기사 안내 생성')
    else:notify_demo(sim,'선작업 승인',f'{rec.container_id} → {slot(chosen.stack,chosen.tier)}',('플래너','관제 담당자'))


def cargo_panel(sim,cid,key='cargo'):
    c=sim.bundle.containers[cid]
    if c.cargo_type=='일반':
        html(badge('일반 드라이 · 수출 FCL','blue'));return True
    if c.cargo_type=='위험물':
        title=f'위험물 · Class {c.hazard_class}'
        text=f'위험물 전용 구역 {c.block}-02-03만 후보로 허용합니다. 동일 분류 외 혼적을 제한하며, 현장 담당자의 서류·구역 확인 후 승인합니다.'
        label='위험물 서류와 전용 구역 확인'
    else:
        title='환적 화물'
        text=f'연결 선박 {c.connecting_vessel} / 인출 대상 {c.vessel_id}. 연결 항차와 인출 순서를 담당자가 확인합니다. 수출 FCL 핵심 범위 외 예외 처리 예시입니다.'
        label='연결 항차와 인출 순서 확인'
    html(f'<div class="cargo-alert"><div>{badge(title,"coral" if c.cargo_type=="위험물" else "amber")}</div><p>{escape(text)}</p></div>')
    checked=st.checkbox(label,value=cid in sim.cargo_checks,key=key+'_'+cid)
    if checked:sim.cargo_checks.add(cid)
    else:sim.cargo_checks.discard(cid)
    return checked


def arrival_inputs(sim,cid):
    c=sim.bundle.containers[cid];f=sim.forecasts.get(cid)
    with st.container(key='eta_inputs'):
        panel('도착 예측 입력과 근거','INPUT → ETA','예약·기사 이력·동의한 위치정보를 바꾸면 예측을 다시 계산합니다.')
        existing=st.session_state.eta_inputs.get(cid,{})
        with st.form('arrival_'+cid):
            a,b,c3=st.columns(3)
            with a:
                booking=st.number_input('예약 시각 · 09:00 이후 분',min_value=0,max_value=360,value=existing.get('booking',round((c.booking_start+c.booking_end)/120)))
                consent=st.checkbox('위치정보 사용에 동의',value=existing.get('consent',True))
            with b:
                remaining=st.number_input('GPS · 게이트까지 남은 분',0,180,existing.get('remaining',max(1,round(((f.p50 if f else sim.now+900)-sim.now)/60))))
                age=st.number_input('위치정보 갱신 경과 · 분',0,60,existing.get('age',1))
            with c3:
                traffic=st.slider('교통 소요 배수',.5,2.5,existing.get('traffic',1.),.1)
                history_mode=st.selectbox('기사 예약 준수 이력', ['기본 이력 20건','정시 위주 20건','지연 위주 20건','이력 없음'],index=['기본 이력 20건','정시 위주 20건','지연 위주 20건','이력 없음'].index(existing.get('history_mode','기본 이력 20건')))
            history={'기본 이력 20건':demo_history(cid),'정시 위주 20건':[-3,0,2,4,5]*4,'지연 위주 20건':[10,16,22,28,34]*4,'이력 없음':[]}[history_mode]
            predicted,evidence=predict_arrival(cid,sim.now,booking*60,history,consent,remaining,traffic,age)
            if st.form_submit_button('ETA 계산·배치 추천에 반영',type='primary',disabled=sim.statuses[cid]!='EN_ROUTE'):
                from dataclasses import replace
                sim.bundle.containers[cid]=replace(c,booking_start=max(0,booking*60-300),booking_end=booking*60+300)
                sim.forecasts[cid]=predicted;sim.eta_overrides.add(cid);sim.yard_version+=1
                st.session_state.eta_inputs[cid]={'booking':booking,'consent':consent,'remaining':remaining,'age':age,'traffic':traffic,'history_mode':history_mode,'evidence':evidence}
                st.session_state.pop('active_recommendation',None)
                notify_demo(sim,'도착 예측 갱신',f'{cid} · ETA {tm(predicted.p50)} · 입력 품질 점수 {predicted.trust_score}점',('플래너','관제 담당자','운송기사'))
                st.rerun()
        if sim.statuses[cid]!='EN_ROUTE':st.caption('이미 도착한 화물은 예측을 덮어쓰지 않습니다. 운송 중인 컨테이너를 선택하면 입력을 반영할 수 있습니다.')
        a,b,c3=st.columns(3)
        with a:metric('현재 ETA 입력 품질',f.trust_score if f else '—','점','규칙 기반 점수 · 확률 아님','teal')
        with b:metric('입력 이력의 준수율',round(evidence['준수율']*100),'%',f'{len(history)}건 · 예약 ±15분 이내 도착 비율','blue')
        with c3:metric('위치정보 반영', '사용' if evidence['GPS 반영'] else '제외','','입력 미리보기 · 반영 버튼으로 적용','amber')
        detail=st.session_state.eta_inputs.get(cid,{}).get('evidence')
        if detail:
            table(['반영 항목','현재 계산 근거'],[['예약 기준',tm(detail['예약 기준'])],['기사 이력 보정',f'{detail["이력 보정(분)"]:+.1f}분 · {detail["표본 수"]}건'],['GPS 가중치',f'{detail["GPS 가중치"]:.0%} · {detail["GPS 제외 사유"] or "동의·최신성 확인"}']])
        with st.expander('입력 품질 점수 산식과 이력 확인'):
            st.caption('기본 25점 + 이력량 최대 20점 + 준수율 최대 15점 + 유효 GPS 30점 + 예측폭 최대 10점. 검증된 확률이 아닌 입력 품질 점수입니다. 동의하지 않거나 5분을 초과한 위치정보는 계산에서 제외합니다. 적용한 입력은 자동 ETA 갱신보다 우선합니다.')
            st.dataframe({'운행':list(range(1,len(history)+1)),'예약 대비 도착 편차(분)':history},hide_index=True,width='stretch')


def exceptions_page(sim,choose,chart,goto):
    o=sim.observe();cid=choose();arrival,priority=quadrant(o,cid)
    html(f'<div class="section-note"><strong>{cid}</strong> · 현재 분류 {badge(arrival,"amber")} {badge("선적 "+priority,"blue")}<br>예약 구간보다 빠르거나 늦은지를 구분하고, TOS 인출 순서 상위 30%를 우선 검토합니다. 정시·정보 부족은 네 칸에 억지로 분류하지 않습니다.</div>')
    cells=[]
    for (a,p),(title,desc) in RULES.items():
        active=(a,p)==(arrival,priority)
        cells.append(f'<div class="quadrant {"selected" if active else ""}"><div class="eyebrow">{a} 도착 × 선적 {p}</div><h3>{title}</h3><p>{desc}</p><span>{"● 현재 컨테이너" if active else "배치 검토 원칙"}</span></div>')
    html('<div class="quadrant-grid">'+''.join(cells)+'</div>')
    f=o.forecasts.get(cid)
    if o.statuses[cid]=='EN_ROUTE' and (not f or f.trust_score<o.config.min_eta_trust or o.now-f.observed_at>=o.config.eta_stale):
        st.warning('ETA 입력 품질·최신성 기준 미충족: 선작업을 보류하고 예약 기반 후보와 필수 작업을 우선합니다.')
    rec=recommend_slots(o,cid)
    panel('현재 상황의 배치 대안','EXPECTED REHANDLING','해당 후보를 선택했을 때 야드 전체에서 생길 추가 이동입니다. 트럭 도착 시각을 예측 범위 안에서 8가지로 가정한 평균이라 소수로 표시됩니다.')
    table(['후보','예상 재취급','선작업','총 추가 이동','전체 누적 인출 지연'],[[slot(c.stack,c.tier),f'{c.rehandles:.2f}회',f'{c.premarshals:.2f}회',f'{c.rehandles+c.premarshals:.2f}회',f'{c.delay_seconds/60:.1f}분'] for c in rec.candidates[:3]])
    if rec.candidates:chart(yard_figure(o,cid,(rec.candidates[0].stack,rec.candidates[0].tier),height=300),'exception_yard')
    else:st.info('현재 상태에서는 신규 적치 후보가 없습니다. 통합 관제·배치에서 미적치 화물을 선택하세요.')
    if st.button('이 화물의 배치 검토',type='primary'):goto('dashboard')


def premarshal_page(sim,chart,reset,goto):
    o=sim.observe();rec=propose_premarshal(o)
    html('<div class="section-note"><strong>선작업도 이동 비용입니다.</strong> · 재취급 감소와 선작업 증가를 함께 계산하고, 장비 유휴시간·ETA 품질·예상 작업 개선 조건을 통과한 경우에만 추천합니다.</div>')
    a,b,c=st.columns(3)
    with a:metric('가용 크레인',sum(j is None for j in sim.cranes.values()),'/ 2','현재 작업을 중단하지 않음','blue')
    with b:metric('추천 상태','검토 가능' if rec else '대기','','도착 대기·ETA·유휴시간 재검증','teal' if rec else 'amber')
    with c:metric('ETA 입력 품질 기준',o.config.min_eta_trust,'점','규칙 기반 점수 · 확률 아님 · 가정값','blue')
    if not rec:
        st.info('현재 안전하게 앞당길 선작업이 없습니다. 필수 작업·하차 대기·예측 불확실성이 있거나, 이동 비용을 포함한 개선 조건을 충족하지 못했습니다.')
        st.caption('아래 버튼은 지금까지의 진행 상태와 판단 기록을 지우고 선작업 검토 시나리오를 처음부터 시작합니다.')
        if st.button('선작업 검토 시나리오로 처음부터 시작',type='primary',help='현재 운영 상태를 초기화하고 반입 전 유휴시간이 있는 시나리오로 전환합니다.'):
            reset(o.config.model_copy(update={'preset':'premarshal_demo'}));goto('premarshal')
        with st.expander('추천을 보류하는 조건',expanded=True):
            st.write('크레인 작업 중 / 해당 블록 하차·진입 대기 / ETA 갱신 지연 또는 낮은 입력 품질 점수(65점 미만) / 다음 작업까지 이동시간 + 2분 여유 부족 / 총 평가 비용 개선 부족 / 최근 10분 내 같은 화물 이동')
        return
    cid=rec.container_id;src=locate(o.yard,cid);options=rec.candidates[:3]
    who=premarshal_beneficiary(o.yard,o.plan,cid)
    focus=st.session_state.get('focus')
    if who:
        subject=f'대표 컨테이너 {who}' if who==focus else who
        html(f'<div class="section-note"><strong>{subject}의 인출을 준비하기 위해 {cid}를 이동합니다.</strong> 이동 대상은 {cid}이고, 인출을 준비하는 화물은 {who}입니다. 대표 컨테이너 선택은 바뀌지 않습니다.</div>')
    selected=st.radio('선작업 대안',range(len(options)),format_func=lambda i:f'대안 {i+1} · {slot(options[i].stack,options[i].tier)}',horizontal=True)
    candidate=options[selected]
    left,right=st.columns([1.7,1])
    with left:
        with st.container(key='canvas'):
            panel('선작업 전후 위치','PRE-MARSHALLING',f'{cid} · {slot(*src)} → {slot(candidate.stack,candidate.tier)}')
            from ui.scene import coords,PITCH,DX,DY,DZ
            x0,y0=coords(src[0]);x1,y1=coords(candidate.stack)
            arrow=[(x0+DX/2,y0+DY/2,(src[1]-1)*PITCH+DZ),(x0+DX/2,y0+DY/2,3),(x1+DX/2,y1+DY/2,3),(x1+DX/2,y1+DY/2,(candidate.tier-1)*PITCH+DZ)]
            # 노랑은 대표 컨테이너로 유지하고, 이동 대상은 화살표와 목적 위치(초록)로 구분합니다
            chart(yard_figure(o,st.session_state.get('focus'),(candidate.stack,candidate.tier),height=350,arrow=arrow),'premarshal_yard')
            st.caption(f'흰 화살표: 이동 대상 {cid}의 경로 · 반투명 초록: 목적 위치 · 노랑: 대표 컨테이너')
    with right:
        with st.container(key='focus'):
            panel('유휴시간에 앞당길 작업','REVIEW BEFORE MOVE')
            html(f'<div class="focus-route"><span>{slot(*src)}</span><strong>→ {slot(candidate.stack,candidate.tier)}</strong></div><div class="detail-row"><span>작업 시간</span><b>{candidate.move_seconds/60:.1f}분</b></div><div class="detail-row"><span>이동 대상</span><b>{cid}</b></div><div class="detail-row"><span>인출을 준비하는 화물</span><b>{who or '—'}</b></div><div class="detail-row"><span>추천 평가</span><b>도착 상황 {len(candidate.sample_scores)}가지 가정 · 60분</b></div>')
            ready=cargo_panel(sim,cid,'pre_cargo')
            reason=st.selectbox('선작업 판단 사유',['유휴시간 활용·인출 방해 예방','현장 장비 동선 고려','다른 작업 우선'])
            if st.button('선작업 승인',type='primary',width='stretch',disabled=not ready):
                report=sim.approve(rec,selected)
                if report.valid:
                    record_approval(sim,rec,selected,reason)
                    st.session_state.review_log.append({'시각':tm(sim.now),'컨테이너':cid,'결정':'선작업 승인','위치':slot(candidate.stack,candidate.tier),'사유':reason,'추천ID':rec.recommendation_id})
                    goto('sync')
                else:st.error(' · '.join(report.errors))
            if st.button('선작업 보류',width='stretch'):
                st.session_state.review_log.append({'시각':tm(sim.now),'컨테이너':cid,'결정':'선작업 보류','위치':'—','사유':reason,'추천ID':rec.recommendation_id})
                goto('sync')
    panel('그대로 둘 때와 미리 옮길 때','TOTAL EXTRA MOVES')
    rows=[['현행 유지',f'{rec.keep_rehandles:.2f}','0.00',f'{rec.keep_rehandles:.2f}','기준']]
    for i,c in enumerate(options):rows.append([f'대안 {i+1}',f'{c.rehandles:.2f}',f'{c.premarshals:.2f}',f'{c.rehandles+c.premarshals:.2f}',f'{rec.keep_score-c.score:+.1f}'])
    table(['선택','예상 재취급 / 회','선작업 / 회','총 추가 이동 / 회','종합 비용 개선 / 점'],rows)
    st.caption('60분·공통 도착 시나리오 평균. 총 추가 이동 = 재취급 + 선작업. 최초 적치·본선 인출은 제외합니다. 종합 비용에는 대기·지연도 포함되므로 이동 횟수만 줄어드는 것은 아닙니다.')


def sharing_page(sim):
    driver,notifications=st.tabs(['기사 하차 안내','역할별 변경 알림'])
    with driver:
        panel('올컨e 앱 기사 하차 안내')
        html(f'<div class="allcone-box">{allcone("올컨e 앱")} 승인한 하차 블록과 진입 경로를 운송기사 앱 화면으로 보냅니다.</div>')
        guides=list(st.session_state.guides.values())
        if not guides:st.info('통합 관제·배치에서 화물을 승인하면 이곳에 안내가 생성됩니다.')
        else:
            cid=st.selectbox('안내할 컨테이너',[g['container'] for g in guides])
            g=st.session_state.guides[cid];state=sim.statuses.get(cid,'RESET')
            completed=state in ('STORED','RETRIEVED');valid=state in ('IN_MOVE','STORED','RETRIEVED')
            left,right=st.columns([1,1.2])
            with left:
                html(f'<div class="phone"><div class="phone-bar">{tm(sim.now)} <span class="phone-brand">올컨e</span></div><div class="phone-title">{"하차 완료" if completed else "하차 위치가 확정됐어요"}</div><p>관제 담당자가 승인한 위치를 확인해 주세요.</p><div class="phone-container">{escape(cid)}</div><div class="phone-slot">{escape(g["block"])}<small>BLOCK</small></div><div class="phone-destination">배정 위치 {escape(g["slot"])}</div><div class="phone-route">게이트 → 지정 진입로 → {escape(g["block"])} 인계 지점</div><p>차량은 관제 지시에 따라 이동하고, 컨테이너 적치는 장비 담당자가 수행합니다.</p><div class="phone-status">{"✓ 기사 확인 완료" if g["ack"] else "기사 확인 대기"}</div></div>')
            with right:
                with st.container(key='focus'):
                    panel('관제·기사 간 확인','DELIVERY STATUS')
                    table(['항목','안내 내용'],[['승인 시각',g['at']],['승인 계획',g['plan']],['현재 작업',{'IN_MOVE':'하차 작업 중','STORED':'적치 완료','RETRIEVED':'본선 인출 완료'}.get(state,'유효성 재확인')],['기사 수신', '확인 완료' if g['ack'] else '미확인']])
                    if st.button('기사 확인 처리',type='primary',disabled=g['ack'] or not valid):
                        g['ack']=True;persist_event(st.session_state.session_id+g['id']+'-ack','driver_ack',g)
                        notify_demo(sim,'기사 안내 확인',f'{cid} · 하차 위치 확인 완료',('플래너','관제 담당자'));st.rerun()
                    st.download_button('기사 안내 JSON',json.dumps(g,ensure_ascii=False,indent=2),'driver_guide.json','application/json')
                    st.caption('기사에게는 하차 블록과 인계 지점만 안내합니다. 슬롯 단위 작업 지시는 크레인에만 전달합니다.')
    with notifications:
        role=st.radio('조회 역할',['플래너','관제 담당자','운송기사','선사'],horizontal=True)
        notices=[n for n in st.session_state.notices if role in n['roles']]
        if not notices:st.info('도착 예측·선박 일정 변경이나 배치 승인이 발생하면 알림이 표시됩니다.')
        for n in notices[:12]:
            # Driver and carrier see operational outcome only, no complete yard arrangement.
            detail=n['detail'] if role in ('플래너','관제 담당자') else ('배정 위치는 기사 하차 안내에서 확인해 주세요.' if n['title']=='하차 위치 승인' else n['detail'])
            html(f'<div class="notice-card"><span>{n["at"]} · {escape(n["version"])}</span><h3>{escape(n["title"])}</h3><p>{escape(detail)}</p>{badge("확인 완료" if role in n["read"] else "새 알림","blue")}</div>')
            if role not in n['read'] and st.button('알림 확인',key=n['id']+role):n['read'].append(role);st.rerun()
        st.caption('역할을 바꾸면 그 역할에 전달되는 알림만 보입니다.')


def connections_panel(sim):
    with st.container(key='connections'):
        panel('9개 터미널 통합 선석 일정','PORT-i → TOS','접안 예정과 개별 컨테이너 인출 순서는 구분합니다.')
        rows=terminal_feed(sim)
        table(['터미널','선박','접안 예정','변동','혼잡 참고'],[[r['터미널'],r['선박'],tm(r['접안 예정']),f'{r["변동(분)"]:+d}분',f'{r["혼잡도"]}%'] for r in rows])
        a,b=st.columns([1,1])
        with a:
            delay=st.slider('T01 선박 일정 편차 · 분',-15,120,sim.bundle.vessels['OCEAN HARMONY'].get('delay_minutes',0),5)
            if st.button('선박 일정 변경·영향 반영',type='primary'):
                version,shift=change_vessel(sim,delay)
                notify_demo(sim,'선박 일정 변경',f'OCEAN HARMONY · {shift/60:+.0f}분 변경 · 새 작업계획 {version}')
                st.session_state.pop('active_recommendation',None);st.rerun()
            st.caption('일정 편차만큼 아직 동결되지 않은 인출 예정시각을 조정합니다. 실제 운영에서는 터미널이 확정한 작업계획을 확인한 뒤 반영합니다.')
        with b:
            o=sim.observe();counts={block:sum(len(v) for k,v in o.yard.items() if k.startswith(block)) for block in ('A1','B1')}
            table(['TOS 블록','사용 / 물리 슬롯','슬롯별 제약'],[[block,f'{used} / 24','높이·하중·위험물 구역 확인'] for block,used in counts.items()])
            st.caption('터미널 단위 혼잡도는 참고 지표입니다. 실제 적치 가능 여부는 TOS 슬롯별 공간·화물·장비 제약으로 판단합니다.')
