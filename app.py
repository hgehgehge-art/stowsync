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
from ui.theme import inject, html, badge, panel, metric, table, tm, mins, footer, allcone
from ui.charts import arrival_chart, comparison_chart, cumulative_chart
from ui.scene import yard_figure, replay_figure
from ui.scene_html import render as render_3d, placement_figure
from ui.workflows import (ensure_workflows, arrival_inputs, cargo_panel,
    record_approval, notify_demo, exceptions_page, premarshal_page, sharing_page, connections_panel)
from ui.story_page import legend3d, trucks_at
from ui.scenario_page import scenario_page
from services import history as job_history
import uuid
from services.story import STORY_CONFIG, start_story, replay_steps

st.set_page_config(page_title='StowSync | 수출 컨테이너 통합 관제',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
inject()
ensure_workflows()

PAGES={'story':'대표 시나리오','dashboard':'통합 관제·배치','eta':'트럭 ETA','premarshal':'유휴시간 선작업',
       'exceptions':'2×2 예외 대응','sharing':'기사 안내·알림','sync':'변경·승인','impact':'정책 실험실','data':'데이터 연계'}
ALIASES={'recommend':'dashboard'}  # 예전 'CY 배치 추천' 주소는 통합 관제·배치로 연결합니다.
PRESET_LABELS={'balanced':'기본 운영','late_priority':'지연 도착 · 선적 상위','early_priority':'조기 도착 · 선적 상위','uncertain':'ETA 불확실성 확대','reversal':'선적계획 변경','capacity':'공간 부족','cutoff':'반입 마감 초과','early_low':'조기 도착 · 선적 하위','late_low':'지연 도착 · 선적 하위','premarshal_demo':'유휴시간 선작업 검토'}
STATUSES={'EN_ROUTE':'운송 중','GATE_QUEUE':'게이트 대기','GATE_SERVICE':'게이트 처리','INTERNAL_TRAVEL':'CY 이동 중','YARD_QUEUE':'하차 대기','BLOCKED_CAPACITY':'공간 부족','STORED':'적치 완료','IN_MOVE':'작업 중','RETRIEVED':'인출 완료','EXCEPTION_LATE':'마감 예외','WAIT_GATE_OPEN':'반입 대기'}
MOVE_LABELS={'INITIAL':'최초 적치','PREMARSH':'사전 이동','REHANDLE':'재취급','RETRIEVE':'본선 인출'}

@st.cache_data(show_spinner=False)
def comparison(config_json):
    cfg=Config.model_validate_json(config_json)
    bundle=build_scenario(cfg)
    return {p:run_simulation(bundle,p) for p in 'ABC'}

FEATURE_CONFIG=Config(target_count=40,occupancy=.5)

def reset_story():
    """대표 사례(20개) 전용 데이터. 기능 시연 데이터와 따로 보관해 서로 지우지 않습니다."""
    sim,story=start_story(STORY_CONFIG)
    st.session_state.story_sim=sim
    st.session_state.story=story
    for key in ('story_stage','story_option','story_choice','_goto_stage','scn_step','scn_play','prev_alt','scn_reason','scn_special'):st.session_state.pop(key,None)

def reset_operations(cfg):
    """기능별 화면(통합 관제~데이터 연계)의 시연 데이터. 명시적인 '시나리오 적용 · 처음부터 시작'에서만 호출합니다."""
    st.session_state.config=cfg
    bundle=build_scenario(cfg)
    sim=Simulator(bundle,'C');sim.manual=True;sim.manual_initial=True;sim.advance(0 if cfg.preset=='premarshal_demo' else 2280)
    st.session_state.ops=sim
    st.session_state.review_log=[]
    st.session_state.guides={}
    st.session_state.notices=[]
    st.session_state.eta_inputs={}
    st.session_state.held=set()
    ready=sorted(sim.yard_arrivals,key=lambda x:(sim.cranes[bundle.containers[x].block] is not None,bundle.containers[x].cargo_type!='일반',sim.yard_arrivals[x]))
    st.session_state.focus=ready[0] if ready else next(cid for cid,c in bundle.containers.items() if not c.initial)
    st.session_state.pop('active_recommendation',None)

if 'config' not in st.session_state or st.session_state.get('workflow_version')!=4:
    reset_operations(FEATURE_CONFIG)
    reset_story()
    st.session_state.workflow_version=4
# 누적 작업 이력을 새로고침 뒤에도 찾도록 브라우저 주소에 세션 ID(sid)를 둡니다.
if not st.query_params.get('sid'):st.query_params['sid']=uuid.uuid4().hex[:10]
# 화면 이동은 조회만 바꿉니다. URL(뒤로 가기 포함)의 page를 따라가되 시뮬레이션 상태는 건드리지 않습니다.
_qp=ALIASES.get(st.query_params.get('page'),st.query_params.get('page'))
if _qp in PAGES:st.session_state.page=_qp
elif 'page' not in st.session_state:st.session_state.page='story'
if st.query_params.get('page')!=st.session_state.page:st.query_params['page']=st.session_state.page

def navigate(page):
    page=ALIASES.get(page,page)
    st.session_state.page=page;st.query_params['page']=page

def goto(page): navigate(page);st.rerun()

cfg=st.session_state.config
with st.sidebar:
    html('<div class="brand"><div class="brand-symbol">◈</div><div><div class="brand-name">StowSync<span class="teal">.</span></div><div class="brand-sub">수출 컨테이너 의사결정 지원</div></div></div>')
    html('<div class="side-label">터미널</div>')
    st.selectbox('터미널', ['부산항 터미널'],label_visibility='collapsed',key='terminal')
    html('<div class="side-label">운영</div>')
    icons={'story':':material/route:','dashboard':':material/view_in_ar:','eta':':material/local_shipping:','sync':':material/rule:','impact':':material/monitoring:','data':':material/hub:','premarshal':':material/forklift:','exceptions':':material/grid_view:','sharing':':material/connect_without_contact:'}
    for key in PAGES:
        if key=='impact':html('<div class="side-label">검증·연계</div>')
        st.button(PAGES[key],icon=icons[key],key='nav_'+key,type='primary' if st.session_state.page==key else 'secondary',width='stretch',on_click=navigate,args=(key,))
    if st.session_state.page=='story':
        html('<div class="side-label">대표 시나리오 · 추천 변경 기준</div>')
        st.slider('1순위를 바꾸는 점수 차이(J)',0,120,30,5,key='seq_margin',help='새 1순위의 점수가 이전 1순위보다 이 값 이상 좋아야 추천을 바꾸고 알림을 띄웁니다. 작은 차이로 추천이 자주 뒤집히지 않게 하는 가정값입니다.')
    html('<div class="side-label">운영 시나리오 · 40개</div>')
    with st.form('scenario_form',border=False):
        preset=st.selectbox('시나리오',list(PRESET_LABELS),format_func=lambda x:PRESET_LABELS[x],index=list(PRESET_LABELS).index(cfg.preset),label_visibility='collapsed')
        if st.form_submit_button('시나리오 적용 · 처음부터 시작',width='stretch',help='기능별 화면의 진행 상태와 판단 기록을 지우고 선택한 시나리오를 처음부터 시작합니다. 대표 시나리오(20개)는 바뀌지 않습니다.'):
            reset_operations(Config(target_count=40,occupancy=.5,preset=preset));st.rerun()
    st.toggle('캡처 모드',key='capture_mode',help='조작 안내를 줄여 기획서에 넣기 편하게 표시합니다.')
    html('<div class="side-card"><div class="allcone-box"><b>올컨e 앱 연동</b><br>반입 예약·운송 정보를 받아 하차 순서·적치 위치를 검토하고, 승인 결과를 기사 앱으로 안내합니다.</div><p>수출 FCL · 2개 블록 · 20ft<br>대표 시나리오 20개 · 기능 시연 40개</p></div>')

page=st.session_state.page
# 대표 시나리오는 20개 사례 데이터, 나머지 기능 화면은 기능 시연 데이터(40개)를 씁니다.
sim=st.session_state.story_sim if page=='story' else st.session_state.ops
o=sim.observe();cfg=st.session_state.config
with st.spinner('동일 조건의 비교 결과를 계산하고 있습니다…'):
    results=comparison(cfg.model_dump_json())

title=PAGES[page]
html(f'<div class="page-head"><div><h1>{title}</h1></div><div class="head-right"><div class="head-time">{tm(o.now)}<span style="font-size:13px;color:#7892a8"> KST</span></div><div class="head-date">2026.10.12</div></div></div>')

def source_strip():
    html('<div class="source-strip"><span class="src-allcone"><b>올컨e 앱</b><em>반입 예약·운송 정보</em></span><span class="arrow">→</span><span><b>TOS</b><em>야드·선박·선적계획</em></span><span class="arrow">→</span><span class="teal">StowSync 의사결정</span></div>')

def chart(fig,key): st.plotly_chart(fig,width='stretch',theme=None,key=key,config={'displayModeBar':False,'scrollZoom':False})


def cargo_word(cid):
    c=o.containers[cid]
    return '⚠ 위험물' if c.cargo_type=='위험물' else c.cargo_type

def _set_focus(key):
    st.session_state.focus=st.session_state[key]

def choose_container(label='검토 컨테이너',only_pending=False):
    """대표 컨테이너는 사용자가 직접 바꾸기 전까지 유지합니다. 목록에서 빠져도 다른 화물로 자동 전환하지 않습니다."""
    focus=st.session_state.focus
    choices=[cid for cid,c in o.containers.items() if not c.initial and (not only_pending or o.statuses[cid] not in ('STORED','RETRIEVED','IN_MOVE','EXCEPTION_LATE'))]
    if only_pending:choices.sort(key=lambda x:(x not in sim.yard_arrivals,sim.yard_arrivals.get(x,0)))  # CY에 도착해 바로 승인할 수 있는 화물을 위로
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

def mini_stack(cid,candidate):
    """이 대안을 고르면 해당 스택이 아래→위로 어떤 순서가 되는지 보여 줍니다."""
    items=list(o.yard.get(candidate.stack,[]))+[cid]
    after={k:list(v) for k,v in o.yard.items()};after[candidate.stack]=items
    risks,pairs=blockers(after,o.plan)
    blocked=[below for below,above in pairs if above==cid]
    cells=[]
    for t in range(4):
        if t<len(items):
            x=items[t];p=o.plan.get(x)
            cls='new' if x==cid else 'risk' if x in risks else ''
            cells.append(f'<div class="ms {cls}"><span>{t+1}단 · {escape(x[-4:])}</span><b>#{p.sequence if p else "—"}</b></div>')
        else:cells.append(f'<div class="ms empty"><span>{t+1}단</span><b>비어 있음</b></div>')
    flag=(f'<div class="mini-flag bad">먼저 실을 {", ".join("#"+str(o.plan[b].sequence) for b in blocked)} 위에 놓여 인출 방해</div>' if blocked
          else '<div class="mini-flag ok">아래 화물의 인출을 막지 않음</div>')
    return '<div class="mini-stack">'+''.join(cells)+'</div><div class="mini-cap">아래 → 위 적재 순서 · #은 선적(인출) 순서</div>'+flag

def detail_card(cid,rec,chosen):
    c=o.containers[cid];f=o.forecasts.get(cid)
    html(f'<div class="focus-id">{cid} · 수출 FCL · {cargo_word(cid)}</div>'
         f'<div class="detail-row"><span>현재 상태</span><b>{STATUSES[o.statuses[cid]]}</b></div>'
         f'<div class="detail-row"><span>예약 시간대</span><b>{tm(c.booking_start)}–{tm(c.booking_end)}</b></div>'
         f'<div class="detail-row"><span>도착 예측 범위</span><b>{tm(f.p10)+"–"+tm(f.p90) if f else "정보 없음"}</b></div>'
         f'<div class="detail-row"><span>선적 순위</span><b>#{o.plan[cid].sequence:02d} / {len(o.plan)}</b></div>'
         f'<div class="detail-row"><span>크레인</span><b>YC-{c.block}</b></div>'
         f'<div class="detail-row"><span>계획 버전</span><b>{rec.plan_version} / Y{rec.yard_version}</b></div>'
         f'<div class="detail-row"><span>추천 유효시각</span><b>{tm(rec.valid_until)}</b></div>'
         f'<div class="focus-route"><span>선택한 적치 위치</span><strong>{slot(chosen.stack,chosen.tier)}</strong></div>')

CODE_KO=[('PREMARSH','선작업'),('REHANDLE','재취급'),('RETRIEVE','본선 인출'),('INITIAL','최초 적치'),('VESSEL','본선')]
def ko(text):
    for k,v in CODE_KO:text=text.replace(k,v)
    return text

def overview_events():
    rows=[f'<div class="event"><div class="event-time">{tm(o.now)}</div><div><div class="event-title">하차 위치 검토 대기 {len(sim.yard_arrivals)}건</div><div class="event-copy">CY에 도착해 적치 위치 승인을 기다리는 화물입니다.</div></div></div>']
    kinds={'MOVE_END':'이동 완료','PLAN_UPDATE':'작업계획 변경','YARD_ARRIVAL':'CY 도착','APPROVED':'승인'}
    for e in [e for e in sim.events if e['kind'] in kinds][-3:][::-1]:
        rows.append(f'<div class="event"><div class="event-time">{tm(e["at"])}</div><div><div class="event-title">{kinds[e["kind"]]} · {escape(e["container_id"] or o.plan_version)}</div><div class="event-copy">{escape(ko(e["detail"]))}</div></div></div>')
    html(''.join(rows))

def dashboard():
    """통합 관제·배치: 야드 현황, 검토 대상, 배치 대안 비교, 현장 관리자 승인을 한 화면에서 처리합니다."""
    source_strip();risks,pairs=blockers(o.yard,o.plan)
    upcoming=sum(o.statuses[x]=='EN_ROUTE' and f.p50<=o.now+3600 for x,f in o.forecasts.items())
    cs=st.columns(4)
    with cs[0]:metric('야드 장치 현황',sum(map(len,o.yard.values())),'/ 48 슬롯',f'2개 블록 · 계획 {o.plan_version}','blue')
    with cs[1]:metric('60분 내 반입 예정',upcoming,'대','운송 중 · ETA 기준','teal')
    with cs[2]:metric('인출 방해 컨테이너',len(risks),'개',f'현재 선적 순서 기준 · 방해 관계 {len(pairs)}건','coral')
    with cs[3]:metric('배치 검토 대기',len(sim.yard_arrivals),'건','CY 도착 · 승인 전','amber')
    cid=choose_container(only_pending=True)
    if cid is None or o.statuses[cid] in ('STORED','RETRIEVED','IN_MOVE','EXCEPTION_LATE'):
        if cid:
            pos=locate(o.yard,cid)
            st.info(f'{cid}는 {STATUSES[o.statuses[cid]]} 상태입니다'+(f' (현재 {slot(*pos)})' if pos else '')+'. 위 목록에서 검토할 다른 화물을 고르세요.')
        else:st.info('모든 반입 대상의 적치가 완료되었습니다.')
        with st.container(key='canvas'):
            panel('야드 현황',subtitle=f'A1 / B1 블록 · {tm(o.now)} · 컨테이너에 마우스를 올리면 번호·인출 순서가 보입니다')
            render_3d(placement_figure(o,cid,None,height=400),400);legend()
        return
    cargo_ready=cargo_panel(sim,cid)
    rec=selected_recommendation(cid)
    if not rec.candidates:st.warning('허용 가능한 적치 후보가 없습니다. 공간·화물·장비 제약을 확인해 주세요.');return
    options=rec.candidates[:3]
    with st.container(key='options'):
        panel('배치 대안 비교',subtitle='대안을 고르면 아래 3D에서 해당 위치로 적치되는 과정이 재생됩니다.')
        selected_index=st.radio('배치 대안 선택',range(len(options)),format_func=lambda i:f'대안 {i+1} · {slot(options[i].stack,options[i].tier)}'+(' (추천)' if i==0 else ''),horizontal=True,key='candidate_'+rec.recommendation_id)
        chosen=options[selected_index]
        for i,(col,candidate) in enumerate(zip(st.columns(len(options)),options)):
            with col:
                reasons='선행 화물의 인출을 가로막지 않음' if 'NO_EARLIER_BOX_BELOW' in candidate.reason_codes else '기존 화물과의 인출 순서 상충 검토'
                html(f'<div class="cand-opt {"sel" if i==selected_index else ""}"><div class="cand-head"><span>대안 {i+1}</span>{badge("추천" if i==0 else "대안", "" if i==0 else "blue")}</div>'
                     f'<div class="cand-slot">{slot(candidate.stack,candidate.tier)}</div>'
                     f'<div class="cand-row"><span>예상 재취급(야드 전체)</span><b>{candidate.rehandles:.2f}회</b></div>'
                     f'<div class="cand-row"><span>총 추가 이동</span><b>{candidate.rehandles+candidate.premarshals:.2f}회</b></div>'
                     f'<div class="cand-row"><span>추가 이동 작업시간</span><b>{candidate.extra_seconds/60:.1f}분</b></div>'
                     f'<div class="cand-why">{reasons}</div>{mini_stack(cid,candidate)}</div>')
        st.caption(f'수치는 같은 블록에 들어올 트럭들의 도착 시각을 예측 범위 안에서 {cfg.samples}가지로 가정하고 앞으로 60분을 계산한 평균입니다. '
                   '2×2 상황 분류(조기·지연 × 선적 상위·하위)와는 별개이며, 이 컨테이너 하나가 아니라 이 위치를 골랐을 때 야드 전체(블록 A1·B1)에서 생길 추가 이동입니다.')
    left,right=st.columns([1.75,1],gap='medium')
    with left:
        with st.container(key='canvas'):
            panel('적치 미리보기',subtitle=f'{cid} → {slot(chosen.stack,chosen.tier)} · 컨테이너에 마우스를 올리면 번호·인출 순서가 보입니다')
            render_3d(placement_figure(o,cid,(chosen.stack,chosen.tier),height=420),420,autoplay_ms=110);legend()
    with right:
        with st.container(key='review'):
            panel('현장 관리자 검토')
            detail_card(cid,rec,chosen)
            reason=st.selectbox('판단 사유(선택)',['선택 안 함','추천 근거와 현장 조건 일치','장비 작업 순서 고려','현장 혼잡으로 보류','추천 외 대안이 현장에 적합'],key='decision_reason')
            already=any(v['container_id']==cid for v in sim.accepted.values())
            can_approve=cid in sim.yard_arrivals and sim.cranes[o.containers[cid].block] is None and cid not in st.session_state.held and cargo_ready and not already
            if st.button('선택한 배치 승인',type='primary',width='stretch',disabled=not can_approve):
                report=sim.approve(rec,selected_index)
                if report.valid:
                    record_approval(sim,rec,selected_index,reason)
                    job_history.add({'sid':st.query_params.get('sid','local'),'sim_time':tm(sim.now),'source':'통합 관제·배치','container':cid,
                        'compared':[{'대안':f'대안 {i+1}','위치':slot(c.stack,c.tier),'예상 재취급':round(c.rehandles,2),'추가 이동 작업시간(분)':round(c.extra_seconds/60,1)} for i,c in enumerate(options)],
                        'approved':f'대안 {selected_index+1} · {slot(chosen.stack,chosen.tier)}','order_text':f'{cid} 단독 하차','total_min':round(chosen.extra_seconds/60,2),
                        'base_total_min':round(options[0].extra_seconds/60,2),'saved_min':round((options[0].extra_seconds-chosen.extra_seconds)/60,2),
                        'reason':('' if reason=='선택 안 함' else reason+' · ')+('추천 1위' if selected_index==0 else f'추천 {selected_index+1}위(담당자 선택)')+f' · 예상 재취급 {chosen.rehandles:.2f}회',
                        'status':'승인(작업 대기)','detail':{'추천ID':rec.recommendation_id,'계획 버전':rec.plan_version}})
                    st.session_state.review_log.append({'시각':tm(sim.now),'컨테이너':cid,'결정':'승인','위치':slot(chosen.stack,chosen.tier),'사유':reason,'추천ID':rec.recommendation_id})
                    st.session_state.pop('active_recommendation',None);goto('sync')
                else:st.error(' · '.join(report.errors))
            if st.button('추천 보류',width='stretch',disabled=cid in st.session_state.held):
                job_history.add({'sid':st.query_params.get('sid','local'),'sim_time':tm(sim.now),'source':'통합 관제·배치','container':cid,'approved':'— (보류)','order_text':'—','reason':reason,'status':'보류'})
                st.session_state.held.add(cid);st.session_state.review_log.append({'시각':tm(sim.now),'컨테이너':cid,'결정':'보류','위치':'—','사유':reason,'추천ID':rec.recommendation_id});goto('sync')
            if not can_approve:st.caption('승인하려면 CY 도착, 크레인 가용, 화물 확인, 보류 해제가 필요합니다.')
            html(f'<div class="allcone-box">승인하면 {allcone("올컨e 앱")} 기사 화면에 하차 블록 <b>{escape(chosen.stack.split("-")[0])}</b> 안내가 생성됩니다.</div>')
    with st.container(key='stack'):
        panel('블록 적층 단면',subtitle='먼저 꺼내야 하는 화물을 가로막는 위치는 붉게, 선택한 위치는 청록색으로 표시합니다.')
        stack_view((chosen.stack,chosen.tier))
    left,right=st.columns([1.75,1],gap='medium')
    with left:
        with st.container(key='arrivals'):
            panel('우선 검토 화물')
            table(['컨테이너','예약 구간','도착 예측 범위','선적 순위','현재 상태'],arrival_rows(5))
    with right:
        with st.container(key='events'):
            panel('운영 이벤트')
            overview_events()

def eta_page():
    source_strip()
    cid=choose_container();c=o.containers[cid];f=o.forecasts.get(cid)
    cs=st.columns(4)
    with cs[0]:metric('반입 예약',tm((c.booking_start+c.booking_end)//2),'',f'{tm(c.booking_start)}–{tm(c.booking_end)}','blue')
    with cs[1]:metric('예측 도착시각',tm(f.p50) if f else '—','', '도착 예측 중앙값','teal')
    with cs[2]:metric('예측 구간 폭',round((f.p90-f.p10)/60) if f else '—','분','트럭이 도착할 가능성이 높은 시간 범위의 길이 · 좁을수록 도착 시각이 확실함','amber')
    with cs[3]:metric('선적 우선순위',f'#{o.plan[cid].sequence:02d}','',f'작업계획 {o.plan_version} 기준','blue')
    left,right=st.columns([2.1,1],gap='medium')
    with left:
        with st.container(key='eta_chart'):
            panel('예약과 도착의 간격','ARRIVAL WINDOWS','굵은 회색 막대는 예약 구간, 청록색 선은 ETA 구간입니다.')
            chart(arrival_chart(o,355),'eta_intervals')
    with right:
        with st.container(key='focus'):
            panel('도착 정보','',f'{cid}')
            html(f'<div class="detail-row"><span>현재 진행 상태</span><b>{STATUSES[o.statuses[cid]]}</b></div><div class="detail-row"><span>마지막 예측 갱신</span><b>{tm(f.observed_at) if f else "없음"}</b></div><div class="detail-row"><span>예측 입력</span><b>예약 · 기사 운행 이력 · 위치</b></div><div class="detail-row"><span>위치정보</span><b>동의한 기사만 반영</b></div>')
            if st.button('이 화물의 배치 검토',type='primary',width='stretch'):goto('dashboard')
    arrival_inputs(sim,cid)
    with st.container(key='arrivals'):
        panel('컨테이너별 도착 현황','TRANSPORT STATUS')
        table(['컨테이너','예약 구간','ETA 구간','선적 순위','상태'],arrival_rows(8))

def sync_page():
    source_strip()
    accepted=sim.accepted
    completed=sum(v['status']=='COMPLETED' for v in accepted.values())
    executing=sum(v['status']=='EXECUTING' for v in accepted.values())
    cs=st.columns(4)
    with cs[0]:metric('승인',len(accepted),'건','관리자 결정','teal')
    with cs[1]:metric('작업 중',executing,'건','승인된 비선점 작업','amber')
    with cs[2]:metric('작업 완료',completed,'건','이동 완료 사건 기준','blue')
    with cs[3]:metric('보류',len(st.session_state.held),'건','현장 사유 기록','coral')
    approved=[e['at'] for e in sim.events if e['kind']=='APPROVED']
    if approved:
        with st.container(key='canvas'):
            panel('승인한 작업의 3D 재생','REPLAY · 실행 로그','첫 승인 시각부터 지금까지 실행 로그를 그대로 재생합니다. 다시 보기를 해도 작업이 다시 실행되지 않습니다.')
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
                html('<div class="focus-copy">아직 승인한 작업이 없습니다. 통합 관제·배치에서 대안을 승인하면 판단 사유와 작업 상태가 여기에 연결됩니다.</div>')
                if st.button('통합 관제·배치로 이동',type='primary'):goto('dashboard')
            panel('최근 작업 이벤트','TERMINAL EVENTS')
            kinds={'MOVE_END':'이동 완료','MOVE_START':'이동 시작','PLAN_UPDATE':'계획 변경','YARD_ARRIVAL':'CY 도착','APPROVED':'관리자 승인','QUEUED':'작업 등록'}
            events=[e for e in sim.events if e['kind'] in kinds][-5:]
            for event in reversed(events):
                html(f'<div class="event"><div class="event-time">{tm(event["at"])}</div><div><div class="event-title">{kinds[event["kind"]]} · {escape(event["container_id"] or o.plan_version)}</div><div class="event-copy">{escape(ko(event["detail"]))}</div></div></div>')
    with right:
        with st.container(key='focus'):
            panel('작업 진행','',"승인한 컨테이너는 크레인 작업 완료 후 야드에 반영됩니다. 실행 중인 작업은 계획이 바뀌어도 끝까지 수행합니다.")
            jobs=[j for j in sim.cranes.values() if j]
            for j in jobs:html(f'<div class="detail-row"><span>{j["crane_id"]}</span><b>{MOVE_LABELS[j["move_type"]]} · {tm(j["end_at"])} 완료</b></div>')
            if st.button('다음 3분 진행',type='primary',width='stretch'):
                sim.advance(sim.now+180);st.session_state.pop('active_recommendation',None);st.rerun()
            if st.button('현재 작업 완료까지 진행',width='stretch',disabled=not jobs):
                sim.advance(max(j['end_at'] for j in jobs));st.session_state.pop('active_recommendation',None);st.rerun()
            if st.session_state.held and st.button('보류 해제 후 재검토',width='stretch'):
                st.session_state.focus=sorted(st.session_state.held)[0];st.session_state.held.clear();goto('dashboard')
            if st.button('기사 안내·알림 열기',width='stretch'):goto('sharing')
            if st.button('누적 작업 이력 보기',width='stretch',key='sync_history'):
                st.session_state.scn_step=6;goto('story')
            html(f'<div class="allcone-box">승인한 하차 블록은 {allcone("올컨e 앱")} 기사 안내로 연결됩니다.</div>')
    if st.session_state.review_log:
        st.download_button('판단 이력 CSV',csv_bytes(st.session_state.review_log),'stowsync_decisions.csv','text/csv',icon=':material/download:')

def impact_page():
    source_strip();a=results['A'].metrics;b=results['B'].metrics;c=results['C'].metrics
    html('<div class="section-note"><strong>별도 자동 실험</strong> · 같은 사건(40개 화물)에 세 정책을 자동으로 적용한 결과입니다. 대표 시나리오에서 승인한 작업의 결과는 대표 시나리오의 결과 확인 단계에서 봅니다.</div>')
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
            panel('정책별 총 추가 이동','','재취급 + 선작업(사전 이동)')
            chart(comparison_chart(results,300),'comparison_bar')
    with right:
        with st.container(key='review'):
            panel('누적 추가 이동','SAME SCENARIO / SAME INPUT')
            chart(cumulative_chart(results,300),'cumulative')
    with st.container(key='arrivals'):
        panel('정책별 비교 결과','REPRODUCIBLE EVALUATION',f'컨테이너 {cfg.target_count}개 · Seed {cfg.seed} · 초기 점유율 {results["A"].manifest["actual_occupancy"]:.0%} · 완료 기준 집계')
        rows=[]
        for p in 'ABC':
            m=results[p].metrics
            rows.append([POLICIES[p],str(m['REHANDLE']),str(m['PREMARSH']),f'<b>{m["extra_moves"]}</b>',mins(m['truck_wait']['mean']),mins(m['retrieval_delay']['mean']),str(m['incomplete'])])
        table(['정책','재취급 / 회','선작업 / 회','총 추가 이동 / 회','평균 대기 / 분','평균 인출 지연 / 분','미완료 / 개'],rows)
    if not complete:
        st.warning('미완료 작업이 있습니다. 이동 감소율만으로 정책 우열을 판단할 수 없습니다. 공간 부족·마감 예외를 함께 확인해 주세요.')
    html('<div class="section-note"><strong>검증 범위</strong> · 세 정책은 같은 실제 도착 사건과 계획 변경을 사용합니다. 예약 기반 정책은 비교용 기준 규칙이며 실제 터미널 TOS를 대표하지 않습니다. 한 번 실행한 결과는 Seed에 따라 정책 순위가 바뀔 수 있습니다.</div>')
    left,right=st.columns([2,1])
    with left:
        with st.expander('실험 조건 변경'):
            with st.form('experiment'):
                seed=st.number_input('재현용 난수 Seed',0,999999,cfg.seed)
                target_count=st.slider('대상 컨테이너 수',24,80,cfg.target_count,step=4)
                error=st.slider('ETA 오차 규모 / 분',1,40,cfg.eta_error//60)
                if st.form_submit_button('새 조건으로 비교 실행',type='primary'):
                    reset_operations(cfg.model_copy(update={'seed':seed,'target_count':target_count,'eta_error':error*60}));st.rerun()
    with right:st.download_button('전체 결과·이동 로그 다운로드',export_zip(results),'stowsync_simulation_results.zip','application/zip',width='stretch',icon=':material/download:')

def data_page():
    source_strip()
    connections_panel(sim)
    html(f'<div class="allcone-box">{allcone("올컨e 앱")} 반입 예약·운송 진행 정보 → TOS 야드·선박·작업계획 순으로 연결해 하차 순서·적치 위치를 판단합니다.</div>')
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
    infos=[('01 반입','올컨e 앱 · VBS','반입 예약, 출발 및 운송 진행 정보','예약·진행 상태 제공 범위와 권한 협의'),('02 선박','선박 일정(TOS)','선박 작업 시간대와 변경 정보','개별 컨테이너 선적 순서와 함께 터미널 TOS에서 수신'),('03 야드','터미널 TOS','적치 위치, 인출 순서, 장비 작업 이력','읽기 전용 검증 후 승인 작업 연계')]
    for col,(num,name,detail,note) in zip(st.columns(3),infos):
        with col:html(f'<div class="integration{" allcone-int" if "올컨e" in name else ""}"><div class="num">{num}</div><h3>{name}</h3>{badge("연계 준비","amber")}<p>{detail}</p><div class="small-note">{note}</div></div>')
    html('<div class="steps"><div class="step active">01 입력 정합성<small>ID · 시각 · 계획 버전</small></div><div class="step active">02 도착 예측<small>중앙값 · 불확실성 구간</small></div><div class="step active">03 제약 기반 탐색<small>위치 · 하중 · 장비</small></div><div class="step active">04 승인 및 결과<small>판단 사유 · 실제 이동</small></div></div>')
    with st.container(key='arrivals'):
        panel('현재 구현 범위와 후속 연결')
        table(['구분','현재 구현','후속 연결'],[
            ['대상','수출 FCL · 20ft / 위험물·환적 예외 확인','실제 화물 규정·참여 항차 확정'],
            ['야드','2개 블록 · 48슬롯 · 블록별 크레인 1대','실제 형상·장비 제약 반영'],
            ['도착 예측','예약·기사 이력·동의 위치 기반 규칙 결합','실데이터로 예측 오차·입력 품질 점수 보정 검증'],
            ['배치 추천','앞으로 60분 · 도착 시각 표본 8개 평가','현장 비용·제약 보정'],
            ['의사결정','승인·보류·실행 이력','TOS 승인·지시 절차 연결'],
            ['판단 이력','승인·보류·사유를 중립 기록으로 저장(채점·자동 학습 없음)','현장 검토를 거친 정기 개선'],
        ])
    left,right=st.columns([1,1])
    with left:
        st.download_button('컨테이너 데이터 CSV',csv_bytes([asdict(c) for c in sim.bundle.containers.values()]),'stowsync_synthetic_containers.csv','text/csv',width='stretch',icon=':material/download:')
    with right:
        st.download_button('설정·가정 JSON',json.dumps({'data_mode':'synthetic','config':cfg.model_dump()},ensure_ascii=False,indent=2),'stowsync_config.json','application/json',width='stretch',icon=':material/download:')
    with st.expander('기획 근거 자료'):
        st.markdown('- [올컨e 공식 매뉴얼](https://www.chainportal.co.kr/manual/download?filename=ChainPortal_APP_Manual.pdf)\n- [도착 불확실성을 고려한 배치 연구](https://research.utwente.nl/en/publications/approximate-dynamic-programming-for-container-stacking/)')
    

{'story':lambda:scenario_page(sim,st.session_state.story,goto,reset_story),'dashboard':dashboard,'eta':eta_page,'sync':sync_page,'impact':impact_page,'data':data_page,
 'exceptions':lambda:exceptions_page(sim,choose_container,chart,goto),
 'premarshal':lambda:premarshal_page(sim,chart,reset_operations,goto),
 'sharing':lambda:sharing_page(sim)}[page]()
footer()
