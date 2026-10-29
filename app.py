"""StowSync: synthetic, presentation-ready Streamlit operations demo.

Run from this directory: python -m streamlit run app.py
No external API, GPS, credentials, or operational terminal data is used.
"""
from pathlib import Path
from html import escape
from dataclasses import asdict
import json
import streamlit as st
import pandas as pd
from domain.models import Config, PRESETS, POLICIES, slot
from adapters.mock import build_scenario
from engine.simulator import Simulator, run_simulation
from engine.yard import blockers, locate, rank
from services.recommend import recommend_slots, propose_premarshal
from services.metrics import export_zip, eta_accuracy, csv_bytes
from ui.theme import inject, html, badge, panel, metric, table, tm, mins, footer
from ui.charts import arrival_chart, comparison_chart, cumulative_chart
from ui.scene import yard_figure, replay_figure
from ui.workflows import (ensure_workflows, arrival_inputs, cargo_panel,
    record_approval, notify_demo, exceptions_page, premarshal_page, sharing_page, connections_panel)
from ui.story_page import story_page, checklist, legend3d, trucks_at, STAGES
from services.story import STORY_CONFIG, start_story, replay_steps

st.set_page_config(page_title='StowSync | 수출 컨테이너 통합 관제',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
inject()
ensure_workflows()

PAGES={'story':('대표 사례 흐름','CASE WALKTHROUGH','컨테이너 한 개의 도착 정보 변화부터 승인·작업·결과까지 이어서 확인합니다.'),
       'dashboard':('통합 관제','CONTROL CENTER','항만의 흐름을 연결하고, 다음 작업을 준비합니다.'),
       'eta':('트럭 ETA','ARRIVAL INTELLIGENCE','예약과 도착의 차이를, 배치 의사결정의 시작으로.'),
       'recommend':('CY 배치 추천','YARD DECISION','보이는 근거로 비교하고, 현장의 판단으로 결정합니다.'),
       'premarshal':('유휴시간 선작업','PRE-MARSHALLING','미리 움직이는 비용까지 비교하고, 여유시간에 실행합니다.'),
       'exceptions':('2×2 예외 대응','EXCEPTION PLAYBOOK','도착 편차와 선적 순위에 따라, 다음 배치의 원칙을 정합니다.'),
       'sharing':('기사 안내·알림','CONNECTED DECISIONS','승인 결과를 역할별로 안내하고, 판단은 중립 이력으로 남깁니다.'),
       'sync':('변경·승인','HUMAN + AI','계획 변경부터 실행 확인까지, 하나의 결정 이력으로.'),
       'impact':('정책 실험실','POLICY LAB · 별도 자동 실험','대표 사례와 별개로, 같은 합성 사건에서 세 정책을 자동으로 비교합니다.'),
       'data':('데이터 연계','CONNECTED OPERATIONS','지금은 모의 데이터로, 이후에는 기존 시스템과 연결합니다.')}
PRESET_LABELS={'story':'대표 사례 · 20개','balanced':'기본 운영','late_priority':'지연 도착 · 선적 상위','early_priority':'조기 도착 · 선적 상위','uncertain':'ETA 불확실성 확대','reversal':'선적계획 변경','capacity':'공간 부족','cutoff':'반입 마감 초과','early_low':'조기 도착 · 선적 하위','late_low':'지연 도착 · 선적 하위','premarshal_demo':'유휴시간 선작업 검토'}
STATUSES={'EN_ROUTE':'운송 중','GATE_QUEUE':'게이트 대기','GATE_SERVICE':'게이트 처리','INTERNAL_TRAVEL':'CY 이동 중','YARD_QUEUE':'하차 대기','BLOCKED_CAPACITY':'공간 부족','STORED':'적치 완료','IN_MOVE':'작업 중','RETRIEVED':'인출 완료','EXCEPTION_LATE':'마감 예외','WAIT_GATE_OPEN':'반입 대기'}
MOVE_LABELS={'INITIAL':'최초 적치','PREMARSH':'사전 이동','REHANDLE':'재취급','RETRIEVE':'본선 인출'}

@st.cache_data(show_spinner=False)
def comparison(config_json):
    cfg=Config.model_validate_json(config_json)
    bundle=build_scenario(cfg)
    return {p:run_simulation(bundle,p) for p in 'ABC'}

def reset_operations(cfg):
    """명시적인 '시나리오 적용 · 처음부터 시작'에서만 호출합니다."""
    st.session_state.config=cfg
    if cfg.preset=='story':
        sim,story=start_story(cfg)
        bundle=sim.bundle
    else:
        bundle=build_scenario(cfg);story=None
        sim=Simulator(bundle,'C');sim.manual=True;sim.manual_initial=True;sim.advance(0 if cfg.preset=='premarshal_demo' else 2280)
    st.session_state.ops=sim
    st.session_state.story=story
    for key in ('story_stage','story_option','story_choice','_goto_stage'):st.session_state.pop(key,None)
    st.session_state.review_log=[]
    st.session_state.guides={}
    st.session_state.notices=[]
    st.session_state.eta_inputs={}
    st.session_state.held=set()
    ready=sorted(sim.yard_arrivals,key=lambda x:(sim.cranes[bundle.containers[x].block] is not None,bundle.containers[x].cargo_type!='일반',sim.yard_arrivals[x]))
    st.session_state.focus=story['focus'] if story else (ready[0] if ready else next(cid for cid,c in bundle.containers.items() if not c.initial))
    st.session_state.pop('active_recommendation',None)

if 'config' not in st.session_state or st.session_state.get('workflow_version')!=3:
    reset_operations(STORY_CONFIG)
    st.session_state.workflow_version=3
# 화면 이동은 조회만 바꿉니다. URL(뒤로 가기 포함)의 page를 따라가되 시뮬레이션 상태는 건드리지 않습니다.
_qp=st.query_params.get('page')
if _qp in PAGES:st.session_state.page=_qp
elif 'page' not in st.session_state:st.session_state.page='story'
if st.query_params.get('page')!=st.session_state.page:st.query_params['page']=st.session_state.page

def navigate(page):
    st.session_state.page=page;st.query_params['page']=page

def goto(page): navigate(page);st.rerun()

cfg=st.session_state.config
with st.sidebar:
    html('<div class="brand"><div class="brand-symbol">◈</div><div><div class="brand-name">StowSync<span class="teal">.</span></div><div class="brand-sub">PORT INTELLIGENCE</div></div></div>')
    html('<div class="side-label">WORKSPACE</div>')
    st.selectbox('터미널', ['부산항 · 가상 터미널'],label_visibility='collapsed',key='terminal')
    html('<div class="side-label">OPERATIONS</div>')
    icons={'story':':material/route:','dashboard':':material/dashboard:','eta':':material/local_shipping:','recommend':':material/view_in_ar:','sync':':material/rule:','impact':':material/monitoring:','data':':material/hub:','premarshal':':material/forklift:','exceptions':':material/grid_view:','sharing':':material/connect_without_contact:'}
    for key in PAGES:
        if key=='impact':html('<div class="side-label">INSIGHTS</div>')
        st.button(PAGES[key][0],icon=icons[key],key='nav_'+key,type='primary' if st.session_state.page==key else 'secondary',width='stretch',on_click=navigate,args=(key,))
    html('<div class="side-label">DEMO SCENARIO</div>')
    with st.form('scenario_form',border=False):
        preset=st.selectbox('시나리오',list(PRESET_LABELS),format_func=lambda x:PRESET_LABELS[x],index=list(PRESET_LABELS).index(cfg.preset),label_visibility='collapsed')
        if st.form_submit_button('시나리오 적용 · 처음부터 시작',width='stretch',help='진행 상태와 판단 기록을 지우고 선택한 시나리오를 처음부터 시작합니다.'):
            reset_operations(STORY_CONFIG if preset=='story' else Config(target_count=40,occupancy=.5,preset=preset));st.rerun()
    st.toggle('캡처 모드',key='capture_mode',help='조작 안내를 줄여 기획서에 넣기 편하게 표시합니다. 합성 데이터 표시는 유지됩니다.')
    html('<div class="side-card"><span class="side-stamp">CONCEPT DEMO · 2026</span><p><strong>올컨e 연계 서비스 제안</strong><br>수출 FCL · 2개 블록 · 20ft · 대표 사례 20개<br>야드 플래너 의사결정 지원</p><p>기존 시스템과의 연계는 준비 단계입니다.<br>현재 화면은 합성 데이터로 동작합니다.</p></div>')

sim=st.session_state.ops;o=sim.observe();cfg=st.session_state.config;page=st.session_state.page
with st.spinner('동일 조건의 비교 결과를 계산하고 있습니다…'):
    results=comparison(cfg.model_dump_json())

title,eyebrow,description=PAGES[page]
title='수출 컨테이너 통합 관제' if page=='dashboard' else title
html(f'<div class="page-head"><div><div class="eyebrow">OPERATIONS / {eyebrow}</div><h1>{title}</h1><p>{description}</p></div><div class="head-right">{badge("SYNTHETIC DEMO")}<div class="head-time">{tm(o.now)}<span style="font-size:13px;color:#7892a8"> KST</span></div><div class="head-date">2026.10.12 · 시뮬레이션 시각</div></div></div>')

def source_strip():
    html('<div class="source-strip"><span><b>올컨e</b><em>반입·운송 정보</em></span><span class="arrow">→</span><span><b>Port-i</b><em>선박 일정</em></span><span class="arrow">→</span><span><b>TOS</b><em>야드·선적계획</em></span><span class="arrow">→</span><span class="teal">StowSync 의사결정</span><span class="right">모의 데이터 연계</span></div>')

def chart(fig,key): st.plotly_chart(fig,width='stretch',theme=None,key=key,config={'displayModeBar':False,'scrollZoom':False})

def focus_toggle():
    return st.toggle('선택 화물 보기(나머지는 흐리게)',key='focus_only',help='가려진 대표 컨테이너를 확인할 수 있도록 다른 스택을 흐리게 표시합니다.')

def cargo_word(cid):
    c=o.containers[cid]
    return '⚠ 위험물' if c.cargo_type=='위험물' else c.cargo_type

def _set_focus(key):
    st.session_state.focus=st.session_state[key]

def choose_container(label='검토 컨테이너',only_pending=False):
    """대표 컨테이너는 사용자가 직접 바꾸기 전까지 유지합니다. 목록에서 빠져도 다른 화물로 자동 전환하지 않습니다."""
    focus=st.session_state.focus
    choices=[cid for cid,c in o.containers.items() if not c.initial and (not only_pending or o.statuses[cid] not in ('STORED','RETRIEVED','IN_MOVE','EXCEPTION_LATE'))]
    if focus in o.containers and focus not in choices:choices=[focus]+choices
    if not choices:return None
    key='choose_'+page
    st.session_state[key]=focus if focus in choices else choices[0]
    st.selectbox(label,choices,format_func=lambda x:f'{x}  ·  {STATUSES.get(o.statuses[x],o.statuses[x])}  ·  {cargo_word(x)}',key=key,on_change=_set_focus,args=(key,))
    return st.session_state[key]

def state_badge(cid):
    s=o.statuses[cid]
    return badge(STATUSES.get(s,s),'amber' if s in ('YARD_QUEUE','GATE_QUEUE') else 'coral' if s in ('BLOCKED_CAPACITY','EXCEPTION_LATE') else 'blue' if s=='EN_ROUTE' else '')

def arrival_rows(limit=5):
    cids=[cid for cid,c in o.containers.items() if not c.initial]
    cids.sort(key=lambda x:(x not in sim.yard_arrivals,o.plan[x].sequence))
    rows=[]
    for cid in cids[:limit]:
        c=o.containers[cid];f=o.forecasts.get(cid)
        eta=f'{tm(f.p10)}–{tm(f.p90)}' if f else '정보 없음'
        rows.append([escape(cid),f'{tm(c.booking_start)}–{tm(c.booking_end)}',eta,f'#{o.plan[cid].sequence:02d}',state_badge(cid)])
    return rows

def legend(): legend3d()

def selected_recommendation(cid):
    current=st.session_state.get('active_recommendation')
    if current is None or current.container_id!=cid or current.yard_version!=o.yard_version or current.plan_version!=o.plan_version or o.now>current.valid_until:
        current=recommend_slots(o,cid,'C');st.session_state.active_recommendation=current
    return current

def focus_card(cid):
    c=o.containers[cid];f=o.forecasts.get(cid)
    rec=recommend_slots(o,cid,'C') if o.statuses[cid] not in ('STORED','IN_MOVE','RETRIEVED') else None
    candidate=rec.candidates[0] if rec and rec.candidates else None
    html('<div class="focus-kicker">DECISION ASSISTANT</div>'+badge('관리자 검토 필요','amber'))
    html('<div class="focus-title">도착의 변화,<br>배치의 다음 선택.</div><div class="focus-copy">최신 도착 정보와 선적 순서를 함께 검토해<br>꺼내기 쉬운 적치 후보를 제안합니다.</div>')
    html(f'<div class="focus-id">{cid} · 수출 FCL</div><div class="detail-row"><span>예약 시간대</span><b>{tm(c.booking_start)}–{tm(c.booking_end)}</b></div><div class="detail-row"><span>도착 예측 구간</span><b>{tm(f.p10)+"–"+tm(f.p90) if f else "정보 없음"}</b></div><div class="detail-row"><span>현재 선적 순위</span><b>#{o.plan[cid].sequence:02d} / {len(o.plan)}</b></div>')
    html(f'<div class="focus-route"><span>추천 적치 위치</span><strong>{slot(candidate.stack,candidate.tier) if candidate else "재검토 필요"}</strong></div>')
    if st.button('배치 대안 검토',icon=':material/arrow_forward:',type='primary',width='stretch',key='focus_action'):
        st.session_state.focus=cid;goto('recommend')

def stack_view(target=None):
    risks,_=blockers(o.yard,o.plan)
    keys=[k for k in o.yard if k.startswith(o.containers[st.session_state.focus].block)]
    columns=[]
    for k in keys:
        cells=[]
        for tier in range(4,0,-1):
            items=o.yard[k]
            cid=items[tier-1] if len(items)>=tier else None
            cls='target' if target and (k,tier)==target else 'risk' if cid in risks else '' if cid else 'empty'
            txt='추천 위치' if target and (k,tier)==target else (f'{cid[-4:]} · #{o.plan[cid].sequence}' if cid else '—')
            cells.append(f'<div class="stack-cell {cls}">{txt}</div>')
        columns.append('<div class="stack-column">'+''.join(cells)+f'<div class="stack-label">{k}</div></div>')
    html('<div class="stack-grid">'+''.join(columns)+'</div>')

def dashboard():
    source_strip();risks,pairs=blockers(o.yard,o.plan)
    upcoming=sum(o.statuses[x]=='EN_ROUTE' and f.p50<=o.now+3600 for x,f in o.forecasts.items())
    cs=st.columns(4)
    with cs[0]:metric('야드 장치 현황',sum(map(len,o.yard.values())),'/ 48 슬롯',f'2개 블록 · 계획 {o.plan_version}','blue','YARD')
    with cs[1]:metric('60분 내 반입 예정',upcoming,'대','현재 운송 중 · 합성 ETA 기준','teal','ETA')
    with cs[2]:metric('인출 방해 컨테이너',len(risks),'개',f'현재 선적 순서 기준 · 방해 관계 {len(pairs)}건','coral','RISK')
    with cs[3]:metric('배치 검토 대기',len(sim.yard_arrivals),'건','CY 도착 · 관리자 승인 전','amber','ACTION')
    left,right=st.columns([2.2,1],gap='medium')
    pending=sorted((x for x in sim.yard_arrivals if x not in st.session_state.held),key=lambda x:(sim.cranes[o.containers[x].block] is not None,o.containers[x].cargo_type!='일반',sim.yard_arrivals[x]))
    cid=pending[0] if pending else st.session_state.focus
    rec=recommend_slots(o,cid,'C');target=(rec.candidates[0].stack,rec.candidates[0].tier) if rec.candidates else None
    with left:
        with st.container(key='canvas'):
            panel('야드 디지털 뷰','YARD / 3D',f'가상 터미널 · A1 / B1 블록 · 현재 상태 {tm(o.now)}')
            chart(yard_figure(o,cid,target,height=380,focus_only=focus_toggle()),'yard3d')
            legend()
    with right:
        with st.container(key='focus'):focus_card(cid)
    left,right=st.columns([1.75,1],gap='medium')
    with left:
        with st.container(key='arrivals'):
            panel('우선 검토 화물','INBOUND QUEUE')
            table(['컨테이너','예약 구간','도착 예측','선적 순위','현재 상태'],arrival_rows(4))
    with right:
        with st.container(key='events'):
            panel('운영 인사이트','OPERATIONS NOTE')
            html(f'<div class="event"><div class="event-time">{tm(o.now)}</div><div><div class="event-title">{len(sim.yard_arrivals)}건의 하차 위치 검토 대기</div><div class="event-copy">후보 위치의 제약과 예상 작업량을 비교합니다.</div></div></div><div class="event"><div class="event-time">{tm(2100)}</div><div><div class="event-title">선적 작업계획 {o.plan_version} 반영</div><div class="event-copy">변경된 인출 순서에 맞춰 배치를 재검토합니다.</div></div></div><div class="event"><div class="event-time">AI</div><div><div class="event-title">추천 이후에도, 결정은 현장에</div><div class="event-copy">승인·보류 이유와 실제 이동 결과를 기록합니다.</div></div></div>')

def eta_page():
    source_strip()
    cid=choose_container();c=o.containers[cid];f=o.forecasts.get(cid)
    cs=st.columns(4)
    with cs[0]:metric('반입 예약',tm((c.booking_start+c.booking_end)//2),'',f'{tm(c.booking_start)}–{tm(c.booking_end)}','blue')
    with cs[1]:metric('예측 도착시각',tm(f.p50) if f else '—','', '합성 ETA 중앙값','teal')
    with cs[2]:metric('예측 구간 폭',round((f.p90-f.p10)/60) if f else '—','분','실제 모델 정확도 지표가 아닙니다','amber')
    with cs[3]:metric('선적 우선순위',f'#{o.plan[cid].sequence:02d}','',f'작업계획 {o.plan_version} 기준','blue')
    left,right=st.columns([2.1,1],gap='medium')
    with left:
        with st.container(key='eta_chart'):
            panel('예약과 도착의 간격','ARRIVAL WINDOWS','굵은 회색 막대는 예약 구간, 청록색 선은 합성 ETA 구간입니다.')
            chart(arrival_chart(o,355),'eta_intervals')
    with right:
        with st.container(key='focus'):
            panel('도착 정보 해석','PREDICTION CONTEXT')
            html(f'<div class="focus-title">시각 하나보다,<br>가능한 도착 범위.</div><div class="focus-copy">예측 구간과 마지막 갱신시각을 함께 확인합니다. 불확실성이 큰 경우에는 선작업을 보류합니다.</div><div class="detail-row"><span>현재 진행 상태</span><b>{STATUSES[o.statuses[cid]]}</b></div><div class="detail-row"><span>마지막 예측 갱신</span><b>{tm(f.observed_at) if f else "없음"}</b></div><div class="detail-row"><span>예측 입력</span><b>합성 운송 이력</b></div><div class="detail-row"><span>GPS / 교통 API</span><b>미연계</b></div>')
            if st.button('이 화물의 배치 검토',type='primary',width='stretch'):goto('recommend')
    arrival_inputs(sim,cid)
    with st.container(key='arrivals'):
        panel('컨테이너별 도착 현황','TRANSPORT STATUS')
        table(['컨테이너','예약 구간','ETA 구간','선적 순위','상태'],arrival_rows(8))

def recommend_page():
    source_strip();cid=choose_container(only_pending=True)
    if cid is None:st.info('모든 반입 대상의 적치가 완료되었습니다. 다른 시나리오를 적용해 보세요.');return
    if o.statuses[cid] in ('STORED','RETRIEVED','IN_MOVE','EXCEPTION_LATE'):
        pos=locate(o.yard,cid)
        st.info(f'{cid}는 {STATUSES[o.statuses[cid]]} 상태입니다'+(f' (현재 {slot(*pos)})' if pos else '')+'. 다른 화물은 위 목록에서 직접 고를 수 있습니다.')
        chart(yard_figure(o,cid,height=400,focus_only=focus_toggle()),'yard3d');legend();return
    cargo_ready=cargo_panel(sim,cid)
    rec=selected_recommendation(cid)
    if not rec.candidates:st.warning('허용 가능한 적치 후보가 없습니다. 공간·화물·장비 제약을 확인해 주세요.');return
    options=rec.candidates[:3]
    selected_index=st.radio('비교할 배치 대안',range(len(options)),format_func=lambda i:f'대안 {i+1} · {slot(options[i].stack,options[i].tier)}',horizontal=True,key='candidate_'+rec.recommendation_id)
    chosen=options[selected_index]
    for i,(col,candidate) in enumerate(zip(st.columns(len(options)),options)):
        with col:
            reasons='선행 화물의 인출을 가로막지 않음' if 'NO_EARLIER_BOX_BELOW' in candidate.reason_codes else '기존 화물과의 인출 순서 상충 검토'
            html(f'<div class="candidate {"best" if i==0 else ""}"><div class="candidate-rank">OPTION 0{i+1} &nbsp; {"RECOMMENDED" if i==0 else "ALTERNATIVE"}</div><div class="candidate-slot">{slot(candidate.stack,candidate.tier)}</div><div class="candidate-fact">평가 야드 재취급 <b>{candidate.rehandles:.2f}회</b></div><div class="candidate-fact">총 추가 이동 <b>{candidate.rehandles+candidate.premarshals:.2f}회</b></div><div class="candidate-fact">추가 이동 작업시간 <b>{candidate.extra_seconds/60:.1f}분</b></div><div class="candidate-fact">평가 범위 <b>야드 전체 · 60분</b></div><div class="candidate-fact">위치·높이·하중 제약 <b class="teal">충족</b></div><div class="reason">{reasons}</div></div>')
    st.caption(f'카드의 수치는 앞으로 60분 동안 가능한 도착 상황 {cfg.samples}가지를 가정해 후보를 비교한 예상 평균입니다. '
               '대표 컨테이너 한 개가 아니라 이 후보를 골랐을 때 야드 전체(블록 A1·B1)에서 생길 추가 이동이며, 실행 후 관측값과 다를 수 있습니다.')
    left,right=st.columns([1.65,1],gap='medium')
    with left:
        with st.container(key='canvas'):
            panel('선택한 적치 대안','SPATIAL PREVIEW',f'{cid} → {slot(chosen.stack,chosen.tier)} · 반투명 청록색은 추천 위치')
            chart(yard_figure(o,cid,(chosen.stack,chosen.tier),height=380,focus_only=focus_toggle()),'yard3d');legend()
    with right:
        with st.container(key='review'):
            panel('현장 관리자 검토','HUMAN IN THE LOOP')
            html(f'<div class="detail-row"><span>추천 대상</span><b>{cid}</b></div><div class="detail-row"><span>계획 버전</span><b>{rec.plan_version} / Y{rec.yard_version}</b></div><div class="detail-row"><span>추천 유효시각</span><b>{tm(rec.valid_until)}</b></div><div class="detail-row"><span>크레인</span><b>YC-{o.containers[cid].block}</b></div>')
            reason=st.selectbox('판단 사유(선택)',['선택 안 함','추천 근거와 현장 조건 일치','장비 작업 순서 고려','현장 혼잡으로 보류','추천 외 대안이 현장에 적합'],key='decision_reason')
            already=any(v['container_id']==cid for v in sim.accepted.values())
            can_approve=cid in sim.yard_arrivals and sim.cranes[o.containers[cid].block] is None and cid not in st.session_state.held and cargo_ready and not already
            if st.button('선택한 배치 모의 승인',type='primary',width='stretch',disabled=not can_approve):
                report=sim.approve(rec,selected_index)
                if report.valid:
                    record_approval(sim,rec,selected_index,reason)
                    st.session_state.review_log.append({'시각':tm(sim.now),'컨테이너':cid,'결정':'승인','위치':slot(chosen.stack,chosen.tier),'사유':reason,'추천ID':rec.recommendation_id})
                    st.session_state.pop('active_recommendation',None);goto('sync')
                else:st.error(' · '.join(report.errors))
            if st.button('추천 보류',width='stretch',disabled=cid in st.session_state.held):
                st.session_state.held.add(cid);st.session_state.review_log.append({'시각':tm(sim.now),'컨테이너':cid,'결정':'보류','위치':'—','사유':reason,'추천ID':rec.recommendation_id});goto('sync')
            if not can_approve:st.caption('CY 도착, 크레인 가용 여부, 화물 검토와 보류 상태를 확인해 주세요.')
            html('<div class="small-note">횟수는 해당 후보를 선택한 경우의 평가 야드 전체 추정치입니다. 총 추가 이동 = 재취급 + 선작업이며 최초 적치·인출은 제외합니다. 승인하면 기사 안내가 생성됩니다.</div>')
    with st.container(key='stack'):
        panel('적층 단면으로 근거 확인','STACK SECTION','하단 화물을 먼저 꺼내야 하는 위치는 붉게 표시합니다.')
        stack_view((chosen.stack,chosen.tier))

def sync_page():
    source_strip()
    accepted=sim.accepted
    completed=sum(v['status']=='COMPLETED' for v in accepted.values())
    executing=sum(v['status']=='EXECUTING' for v in accepted.values())
    cs=st.columns(4)
    with cs[0]:metric('모의 승인',len(accepted),'건','현재 세션의 관리자 결정','teal')
    with cs[1]:metric('작업 중',executing,'건','승인된 비선점 작업','amber')
    with cs[2]:metric('작업 완료',completed,'건','이동 완료 사건 기준','blue')
    with cs[3]:metric('보류',len(st.session_state.held),'건','현장 사유 기록','coral')
    story=st.session_state.story
    if story:checklist(sim,story)
    approved=[e['at'] for e in sim.events if e['kind']=='APPROVED']
    if approved:
        with st.container(key='canvas'):
            panel('승인한 작업의 3D 재생','REPLAY · 실행 로그','첫 승인 시각부터 지금까지 실제 시뮬레이션 로그를 그대로 재생합니다. 다시 보기를 해도 작업이 다시 실행되지 않습니다.')
            steps,final=replay_steps(sim.bundle,sim.moves,min(approved),sim.now,st.session_state.focus)
            chart(replay_figure(sim.bundle,sim.plan,steps,final,st.session_state.focus,trucks_at(sim)),'yard3d_replay_sync');legend3d()
            if not steps:st.caption('아직 완료된 이동이 없습니다. 오른쪽 아래 버튼으로 작업을 진행하면 이동 중 → 완료 장면이 생깁니다.')
    left,right=st.columns([1.6,1])
    with left:
        with st.container(key='review'):
            panel('결정과 실행 이력','DECISION LOG')
            if st.session_state.review_log:
                rows=[]
                for row in reversed(st.session_state.review_log[-8:]):
                    state=accepted.get(row['추천ID'],{}).get('status','보류')
                    label={'EXECUTING':'작업 중','COMPLETED':'완료','APPROVED':'승인','QUEUED':'대기'}.get(state,state)
                    rows.append([row['시각'],row['컨테이너'],badge(label,'amber' if label=='작업 중' else ''),row['위치']])
                table(['시각','컨테이너','상태','적치 위치'],rows)
            else:
                html('<div class="focus-title">다음 배치를 승인해 보세요.</div><div class="focus-copy">CY 배치 추천에서 대안을 선택하면 이곳에 판단 사유와 작업 상태가 연결됩니다.</div>')
                if st.button('배치 추천으로 이동',type='primary'):goto('recommend')
            panel('최근 작업 이벤트','TERMINAL EVENTS')
            kinds={'MOVE_END':'이동 완료','MOVE_START':'이동 시작','PLAN_UPDATE':'계획 변경','YARD_ARRIVAL':'CY 도착','APPROVED':'관리자 승인','QUEUED':'작업 등록'}
            events=[e for e in sim.events if e['kind'] in kinds][-5:]
            for event in reversed(events):
                html(f'<div class="event"><div class="event-time">{tm(event["at"])}</div><div><div class="event-title">{kinds[event["kind"]]} · {escape(event["container_id"] or o.plan_version)}</div><div class="event-copy">{escape(event["detail"])}</div></div></div>')
    with right:
        with st.container(key='focus'):
            panel('모의 작업 진행','SIMULATION CONTROL')
            html('<div class="focus-title">승인은 시작,<br>완료는 기록으로.</div><div class="focus-copy">승인한 컨테이너는 크레인 작업 완료 후 야드에 반영됩니다. 실행 중인 작업은 계획이 바뀌어도 끝까지 수행합니다.</div>')
            jobs=[j for j in sim.cranes.values() if j]
            for j in jobs:html(f'<div class="detail-row"><span>{j["crane_id"]}</span><b>{MOVE_LABELS[j["move_type"]]} · {tm(j["end_at"])} 완료</b></div>')
            if st.button('다음 3분 진행',type='primary',width='stretch'):
                sim.advance(sim.now+180);st.session_state.pop('active_recommendation',None);st.rerun()
            if st.button('현재 작업 완료까지 진행',width='stretch',disabled=not jobs):
                sim.advance(max(j['end_at'] for j in jobs));st.session_state.pop('active_recommendation',None);st.rerun()
            if st.session_state.held and st.button('보류 해제 후 재검토',width='stretch'):
                st.session_state.focus=sorted(st.session_state.held)[0];st.session_state.held.clear();goto('recommend')
            if st.button('기사 안내·알림 열기',width='stretch'):goto('sharing')
            html('<div class="section-note">이 버튼은 데모의 시간을 진행합니다. 승인한 하차 위치는 기사 안내 미리보기에 연결됩니다. 실제 TOS 지시나 기사 알림은 전송되지 않습니다.</div>')
    if st.session_state.review_log:
        st.download_button('판단 이력 CSV',csv_bytes(st.session_state.review_log),'stowsync_decisions.csv','text/csv',icon=':material/download:')

def impact_page():
    source_strip();a=results['A'].metrics;b=results['B'].metrics;c=results['C'].metrics
    html('<div class="section-note"><strong>별도 자동 실험입니다.</strong> 대표 사례 흐름에서 방금 승인한 작업의 효과가 아니라, 같은 합성 사건(40개 화물)에 세 정책을 자동으로 적용한 결과입니다. 방금 승인한 작업의 결과는 대표 사례 흐름 ⑥에서 확인합니다.</div>')
    complete=all(results[p].metrics['incomplete']==0 for p in 'ABC')
    gain=(a['extra_moves']-c['extra_moves'])/a['extra_moves']*100 if a['extra_moves'] else None
    cs=st.columns(4)
    with cs[0]:metric('총 추가 이동',c['extra_moves'],'회',f'예약 기반 {a["extra_moves"]}회 · 선작업 포함','teal')
    with cs[1]:metric('총 추가 이동 변화',f'{gain:+.1f}' if gain is not None else '—','%', '양수: 감소 / 음수: 증가','teal' if gain is not None and gain>=0 else 'coral')
    with cs[2]:metric('평균 트럭 대기',mins(c['truck_wait']['mean']),'분',f'예약 기반 {mins(a["truck_wait"]["mean"])}분','amber')
    with cs[3]:metric('대상 인출 완료',c['RETRIEVE'],f'/ {cfg.target_count}개',f'미완료 {c["incomplete"]}개 · 마감 예외 {c["exceptions"]}개','blue')
    left,right=st.columns([1,1])
    with left:
        with st.container(key='chart'):
            panel('이동을 앞당긴 것과, 줄인 것의 차이','TOTAL EXTRA MOVES')
            chart(comparison_chart(results,300),'comparison_bar')
    with right:
        with st.container(key='review'):
            panel('누적 추가 이동','SAME SCENARIO / SAME INPUT')
            chart(cumulative_chart(results,300),'cumulative')
    with st.container(key='arrivals'):
        panel('정책별 비교 결과','REPRODUCIBLE EVALUATION',f'합성 컨테이너 {cfg.target_count}개 · Seed {cfg.seed} · 초기 점유율 {results["A"].manifest["actual_occupancy"]:.0%} · 완료 기준 집계')
        rows=[]
        for p in 'ABC':
            m=results[p].metrics
            rows.append([POLICIES[p],str(m['REHANDLE']),str(m['PREMARSH']),f'<b>{m["extra_moves"]}</b>',mins(m['truck_wait']['mean']),mins(m['retrieval_delay']['mean']),str(m['incomplete'])])
        table(['정책','재취급 / 회','선작업 / 회','총 추가 이동 / 회','평균 대기 / 분','평균 인출 지연 / 분','미완료 / 개'],rows)
    if not complete:
        st.warning('미완료 작업이 있습니다. 이동 감소율만으로 정책 우열을 판단할 수 없습니다. 공간 부족·마감 예외를 함께 확인해 주세요.')
    html('<div class="section-note"><strong>검증 범위</strong> · 세 정책은 같은 실제 도착 사건과 계획 변경을 사용합니다. 예약 기반 정책은 데모용 비교 규칙이며 실제 터미널 TOS를 대표하지 않습니다. 이 결과는 합성 시나리오의 계산값으로, 부산항의 실제 절감 효과를 의미하지 않습니다.</div>')
    left,right=st.columns([2,1])
    with left:
        with st.expander('실험 조건 변경'):
            with st.form('experiment'):
                seed=st.number_input('재현용 난수 Seed',0,999999,cfg.seed)
                target_count=st.slider('대상 컨테이너 수',24,80,cfg.target_count,step=4)
                error=st.slider('합성 ETA 오차 규모 / 분',1,40,cfg.eta_error//60)
                if st.form_submit_button('새 조건으로 비교 실행',type='primary'):
                    reset_operations(cfg.model_copy(update={'seed':seed,'target_count':target_count,'eta_error':error*60}));st.rerun()
    with right:st.download_button('전체 결과·이동 로그 다운로드',export_zip(results),'stowsync_simulation_results.zip','application/zip',width='stretch',icon=':material/download:')

def data_page():
    source_strip()
    connections_panel(sim)
    html('<div class="section-note"><strong>현재 상태: 합성 데이터로 핵심 업무 흐름 구현</strong><br>외부 시스템의 실제 예약·위치·작업 정보는 연결되어 있지 않습니다. 화면에 표시된 터미널·컨테이너·운송 이력은 모두 시연용입니다.</div>')
    with st.container(key='arrival-evidence'):
        panel('VBS 매뉴얼에서 확인한 예약·도착 기능','공개자료 확인 · 2022 화면 예시')
        table(['구분','매뉴얼에서 확인되는 내용','기획상 의미'],[
            ['예약 가능량','날짜별 예약 가능 수량을 시간대(Z1=0~1시 등)별로 조회','시간대별 용량관리와 세부 예약시각을 구분'],
            ['세부 예약시각','시간 선택 화면에 0·10·20·30·40·50분 예시','분 단위 신규 예약 기능을 제안하는 것이 아님'],
            ['예약 준수 범위','22:00 선택 예시는 21:45~22:15, 설정에 따라 변경 가능','±15분은 해당 화면 예시이며 터미널 설정 확인 필요'],
            ['운송 중 위치·ETA','위치 서비스 사용 시 15km·5km 구간 통과 기록, 구간별 도착예정 표시','위치/ETA 기능의 존재와 TOS 연계를 별도로 확인'],
            ['게이트·야드 안내','게이트 1km 지점에서 예약 준수 판정 예시, 진입 후 장치장·블록 위치 표시','공개 화면만으로 실시간 TOS 장치계획 연계를 단정할 수 없음'],
        ])
        html('<div class="section-note"><strong>해석</strong> · 매뉴얼은 예약시각 조정과 운송 중 위치·도착 상태 안내가 있음을 보여줍니다. 다만 2022년 화면 예시이므로 현재 운영 여부·세부 간격·터미널별 설정은 재확인해야 합니다. 이 공개자료만으로 외부 API 제공 범위나 개별 컨테이너 ETA가 TOS의 최초 적치·선작업 계획에 자동 반영되는지는 확인할 수 없습니다. StowSync의 제안은 기존 정보를 새로 만드는 것이 아니라, 그 정보와 TOS 작업계획의 연결 수준을 조사하고, 부족한 연결·예측·비교 기능을 보완하는 것입니다.</div>')
    infos=[('01 / INBOUND','올컨e · VBS','반입 예약, 출발 및 운송 진행 정보','예약·진행 상태 제공 범위와 권한 협의'),('02 / VESSEL','Port-i','선박 일정과 변경 정보','개별 컨테이너 선적 순서는 TOS에서 수신'),('03 / YARD','터미널 TOS','적치 위치, 인출 순서, 장비 작업 이력','읽기 전용 검증 후 승인 작업 연계')]
    for col,(num,name,detail,note) in zip(st.columns(3),infos):
        with col:html(f'<div class="integration"><div class="num">{num}</div><h3>{name}</h3>{badge("연계 준비","amber")}<p>{detail}</p><div class="small-note">{note}</div></div>')
    html('<div class="steps"><div class="step active">01 입력 정합성<small>ID · 시각 · 계획 버전</small></div><div class="step active">02 도착 예측<small>중앙값 · 불확실성 구간</small></div><div class="step active">03 제약 기반 탐색<small>위치 · 하중 · 장비</small></div><div class="step active">04 승인 및 결과<small>판단 사유 · 실제 이동</small></div></div>')
    with st.container(key='arrivals'):
        panel('데모의 가정과 적용 범위','MODEL CARD')
        table(['구분','현재 구현','후속 연결'],[
            ['대상','수출 FCL · 20ft / 위험물·환적 예외 시연','실제 화물 규정·참여 항차 확정'],
            ['야드','2개 블록 · 48슬롯 · 블록별 크레인 1대','실제 형상·장비 제약 반영'],
            ['도착 예측','합성 ETA + 예약·이력·동의 GPS 입력 실험','현장 이력 학습·신뢰도 보정'],
            ['배치 추천','60분 미래·8개 시나리오 평가','현장 비용·제약 보정'],
            ['의사결정','모의 승인·보류·실행 이력','TOS 승인·지시 절차 연결'],
            ['판단 이력','승인·보류·사유를 중립 기록으로 저장(채점·자동 학습 없음)','현장 검토를 거친 정기 개선'],
        ])
    left,right=st.columns([1,1])
    with left:
        st.download_button('합성 컨테이너 데이터 CSV',csv_bytes([asdict(c) for c in sim.bundle.containers.values()]),'stowsync_synthetic_containers.csv','text/csv',width='stretch',icon=':material/download:')
    with right:
        st.download_button('설정·가정 JSON',json.dumps({'data_mode':'synthetic','config':cfg.model_dump()},ensure_ascii=False,indent=2),'stowsync_config.json','application/json',width='stretch',icon=':material/download:')
    with st.expander('기획 근거 자료'):
        st.markdown('- [올컨e 공식 매뉴얼](https://www.chainportal.co.kr/manual/download?filename=ChainPortal_APP_Manual.pdf)\n- [BPA Port-i 서비스 소개](https://busanpa.com/board/view.do?boardId=BBS_0000031&dataSid=34863&menuCd=DOM_000000105002001000)\n- [도착 불확실성을 고려한 배치 연구](https://research.utwente.nl/en/publications/approximate-dynamic-programming-for-container-stacking/)')
    html('<div class="export-banner"><strong>기획서 캡처 추천</strong> · 통합 관제: 서비스 전체상 / CY 배치 추천: 핵심 의사결정 / 변경·승인: Human-AI 협업 / 효과 분석: 성과 검증 구조<br>좌측의 캡처 모드를 켜면 조작 도움말이 간소화됩니다. 합성 데이터 표시는 유지됩니다.</div>')

{'story':lambda:story_page(sim,st.session_state.story,goto) if st.session_state.story else st.info('대표 사례 흐름은 「대표 사례 · 20개」 시나리오에서 볼 수 있습니다. 왼쪽에서 시나리오를 적용해 주세요.'),'dashboard':dashboard,'eta':eta_page,'recommend':recommend_page,'sync':sync_page,'impact':impact_page,'data':data_page,
 'exceptions':lambda:exceptions_page(sim,choose_container,chart,goto),
 'premarshal':lambda:premarshal_page(sim,chart,reset_operations,goto),
 'sharing':lambda:sharing_page(sim)}[page]()
if not st.session_state.capture_mode and page in ('dashboard','eta','story'):
    st.caption('시연 방법: 대표 사례 흐름에서 ① 상황 확인 → ② 문제 확인 → ③ 대안 비교 → ④ 승인·보류 → ⑤ 작업 실행 → ⑥ 결과 확인')
footer()
