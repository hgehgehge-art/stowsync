"""대표 시나리오: 상황 확인 → 문제 확인 → 대안 비교 → 적치 미리보기 → 배치 승인 → 결과 확인 → 누적 작업 이력.

모든 버튼은 실제 상태를 바꿉니다. 대안의 작업시간·절감시간은 같은 초기 상태에서 실행한 시뮬레이션 결과로 계산합니다.
"""
from copy import copy, deepcopy
from html import escape
import pandas as pd
import streamlit as st
from domain.models import slot
from engine.yard import locate, rank
from services import history as hist
from services import sequence as seq
from services.scenario import alternatives, plan_of, MOVE_WORDS
from services.story import (planned_conflict, blocking_pairs, gate_and_yard_times, compare_orders, replay_steps,
                            order_done, review_queue)
from ui.theme import html, badge, panel, table, tm
from ui.scene import yard_figure, replay_figure
from ui.story_page import (summary_bar, source_card, render_overview, role_notices, trucks_at, legend3d, advance_until,
                           STATUS, REASONS)
from ui import sequence_view as sv

STEPS = ['상황 확인', '문제 확인', '대안 비교', '적치 미리보기', '배치 승인', '결과 확인', '누적 작업 이력']
GUIDE = [
    ('대표 컨테이너의 예약·도착 예측과 야드 상황', '아래 정보를 확인한 뒤 CY 도착까지 진행', '대표 컨테이너가 CY에 도착하고 다음 단계로 이동'),
    ('기존 계획 위치에 그대로 놓으면 생기는 문제', '빨간 화물과 설명을 확인', '왜 배치를 다시 검토해야 하는지 확인'),
    ('함께 기다리는 트럭 3대의 처리 순서 대안', '대안을 고르고 [시뮬레이션 실행]으로 작업 과정을 재생', '대안마다 작업시간·장비 이동시간·재취급이 계산되어 비교'),
    ('선택한 대안대로 내렸을 때의 장치장 배치', '칸(컨테이너)을 클릭해 위치와 적층 상태를 확인', '선택한 컨테이너가 화살표와 색으로 강조'),
    ('승인 직전 상태와 선택한 대안', '판단 사유를 고르고 [배치 승인]', '작업이 실행·저장되고 결과 확인으로 이동'),
    ('승인한 배치의 실제 실행 결과', '위치·작업 순서·절감시간과 3D 재생을 확인', '같은 초기 상황의 기준안과 결과를 비교'),
    ('지금까지 승인·보류한 작업 기록', '행을 클릭해 상세 내용을 확인', '여러 번 승인한 결과가 누적되어 보임'),
]
ARRIVED = ('YARD_QUEUE', 'IN_MOVE', 'STORED', 'RETRIEVED')
VESSEL_KIND = {}


# ── 상태 ───────────────────────────────────────────────
def reached(sim, story):
    d = story.get('decision')
    if d and d['type'] == 'approve':
        return 5
    if sim.statuses[story['focus']] in ARRIVED:
        return 4
    return 0


def go(i):
    st.session_state.scn_step = i
    st.rerun()


def sid():
    return st.query_params.get('sid', 'local')


def alt_key(opt):
    return '>'.join(opt['order']) + '|' + '>'.join(str(d) for _, d, _ in opt['positions'])


def current_alts(sim, story):
    margin = st.session_state.get('seq_margin', seq.SWITCH_MARGIN)
    alts = alternatives(sim, story, margin)
    if alts['options']:
        story['seq_prev'] = alts['options'][0]['option']['order']
        keys = [alt_key(a['option']) for a in alts['options']]
        if story.get('alt') not in keys:
            story['alt'] = keys[0]
        k = alts['res'] and seq.cache_key(sim, sim.bundle.containers[story['focus']].block)
        if story.get('rec_key') != k:                      # 입력이 바뀌면 추천 유효시간을 새로 시작
            story['rec_key'] = k; story['rec_valid'] = sim.now + 60
    return alts


def chosen(alts, story):
    return next((a for a in alts['options'] if alt_key(a['option']) == story.get('alt')), alts['options'][0] if alts['options'] else None)


def new_job(reset, jump=True):
    """같은 초기 상황에서 새 작업을 시작합니다. 누적 작업 이력(SQLite)은 지우지 않습니다."""
    reset()
    for k in ('scn_play', 'hist_df', 'scn_reason', 'scn_special'):
        st.session_state.pop(k, None)
    if jump:
        sim, story = st.session_state.story_sim, st.session_state.story
        f = story['focus']
        story['progress']['arrival_checked'] = tm(sim.now)
        advance_until(sim, lambda: sim.statuses[f] in ('YARD_QUEUE', 'EXCEPTION_LATE'))
        go(2)
    go(0)


# ── 공통 화면 요소 ─────────────────────────────────────
def stepper(cur, top):
    # scnsteps: 좁은 화면에서 단계 버튼이 글자 단위로 끊기거나 세로로 쌓이지 않고 여러 줄로 감기도록 감쌉니다(theme.py).
    with st.container(key='scnsteps'):
        cols = st.columns(len(STEPS))
    for i, (col, name) in enumerate(zip(cols, STEPS)):
        state = 'cur' if i == cur else 'done' if (i < cur or (top >= 5 and i <= 5)) and i != 6 else 'todo'
        lock = i > top and i != 6
        with col:
            with st.container(key=f'scnstep-{state}-{i}'):
                mark = '✓' if state == 'done' and i != cur else str(i + 1)
                if st.button(f'{mark}  {name}', key=f'scn_nav_{i}', width='stretch', disabled=lock,
                             help='아직 이전 단계를 마치지 않았습니다.' if lock else f'{name} 단계로 이동'):
                    go(i)
    see, do, get = GUIDE[cur]
    html(f'<div class="scn-guide"><div><span>확인할 내용</span><b>{escape(see)}</b></div>'
         f'<div><span>할 일</span><b>{escape(do)}</b></div><div><span>결과</span><b>{escape(get)}</b></div></div>')


def saved_text(v):
    """기준안 대비 변화. 양수(절감)는 '단축', 음수는 '증가'로 씁니다. '+2.4분'이 늘어난 것처럼 읽히지 않게 합니다."""
    if v is None:
        return '—'
    return '변화 없음' if abs(v) < .05 else (f'{v:.1f}분 단축' if v > 0 else f'{-v:.1f}분 증가')


def nav(cur, top, next_label=None, next_disabled=False, on_next=None):
    a, b = st.columns([1, 2])
    with a:
        if cur > 0 and st.button('← 이전 단계', key=f'scn_prev_{cur}', width='stretch'):
            go(cur - 1)
    with b:
        if next_label and st.button(next_label, key=f'scn_next_{cur}', type='primary', width='stretch', disabled=next_disabled):
            (on_next or (lambda: go(cur + 1)))()


def yard_after(o, option):
    yard = {k: list(v) for k, v in o.yard.items()}
    tiers = {}
    for c, d, _ in option['positions']:
        if d:
            yard[d].append(c); tiers[c] = (d, len(yard[d]))
    return yard, tiers


def vessel_index(sim):
    names = sorted({c.vessel_id for c in sim.bundle.containers.values()})
    return {v: i % 3 for i, v in enumerate(names)}


def snapshot_html(sim, yard, labels, highlight=None, new=()):
    """재생용 장치장 그림(읽기 전용). 2블록 × 6스택 × 4단."""
    o = sim.observe(); vi = vessel_index(sim)
    out = []
    for b in sorted({k[:2] for k in yard}):
        cols = []
        for k in sorted(x for x in yard if x.startswith(b)):
            cells = []
            for t in range(4, 0, -1):
                if t <= len(yard[k]):
                    cid = yard[k][t - 1]
                    cls = f'v{vi[sim.bundle.containers[cid].vessel_id]}' + (' hl' if cid == highlight else '') + (' new' if cid in new else '')
                    txt = labels.get(cid) or str(o.plan[cid].sequence)
                    cells.append(f'<div class="pc {cls}" title="{escape(cid)}">{escape(txt)}</div>')
                else:
                    cells.append('<div class="pc empty"></div>')
            cols.append(f'<div class="ps"><div class="ps-cells">{"".join(cells)}</div><div class="ps-name">{k[3:]}</div></div>')
        out.append(f'<div class="pb"><div class="pb-name">{b} 블록</div><div class="pb-cols">{"".join(cols)}</div></div>')
    return '<div class="pgrid">' + ''.join(out) + '</div>'


# ── 1. 상황 확인 ───────────────────────────────────────
def step_situation(sim, story, top, reset):
    cid = story['focus']; o = sim.observe(); c = o.containers[cid]
    left, right = st.columns([1.5, 1], gap='medium')
    with left:
        with st.container(key='canvas'):
            render_overview(sim, story)
    with right:
        with st.container(key='focus'):
            panel('대표 컨테이너 상황', subtitle='반입 예약·도착 예측과 작업계획을 함께 봅니다.')
            log = sim.forecast_log.get(cid, [])
            hist_txt = ' → '.join(f'{tm(f.observed_at)} {tm(f.p50)}' for f in log[-3:]) if log else '갱신 없음'
            times = gate_and_yard_times(sim, cid)
            gate = tm(times['gate']) if times['observed'] else (f'{tm(times["gate"][0])}–{tm(times["gate"][2])} 예상' if times['gate'] else '정보 없음')
            source_card('allcone', [('반입 예약', f'{tm(c.booking_start)}–{tm(c.booking_end)}'), ('트럭 상태', STATUS[sim.statuses[cid]]),
                                    ('도착 예측(갱신 → ETA)', hist_txt), ('게이트 도착', gate)])
            first_due = min(p.due for p in o.plan.values())
            source_card('tos', [('선박 · 작업계획', f'{c.vessel_id} · {sim.plan_version} · 본선 인출 시작 {tm(first_due)}'),
                                ('대표 컨테이너 인출 순서', f'#{o.plan[cid].sequence} / {len(o.plan)}'),
                                ('기존 계획 위치', story['planned'])])
            rows = review_queue(sim)[:4]
            table(['검토 순위', '컨테이너', '상황 분류'], [[str(i), f'<b>{escape(r["cid"])}</b>' + (' ★' if r['cid'] == cid else ''),
                                                       f'{r["arrival"]} 도착 · 선적 {r["priority"]}'] for i, r in enumerate(rows, 1)])
            f = o.forecasts.get(cid)
            late = round((f.p50 - c.booking_end) / 60) if f and sim.statuses[cid] == 'EN_ROUTE' else None
            msg = (f'{cid}는 예약보다 약 {late}분 늦게 도착할 것으로 예측되고, 먼저 실어야 하는 선적 상위 화물입니다. '
                   '그래서 검토 순위 1위입니다.') if late and late > 0 else f'{cid}는 지연 도착 × 선적 상위 화물이라 검토 순위 1위입니다.'
            html(f'<div class="why"><b>왜 이 컨테이너를 보나요?</b><br>{escape(msg)}</div>')
    if sim.statuses[cid] in ARRIVED:
        nav(0, top, '다음 단계: 문제 확인 →')
    else:
        def arrive():
            story['progress']['arrival_checked'] = tm(sim.now)
            advance_until(sim, lambda: sim.statuses[cid] in ('YARD_QUEUE', 'EXCEPTION_LATE'))
            go(1)
        nav(0, top, f'확인 완료 · {cid}의 CY 도착까지 진행 →', on_next=arrive)
        st.caption('진행하면 운영 시각이 대표 컨테이너가 CY에 도착하는 때까지 흐르고, 그사이 다른 화물은 같은 규칙으로 처리됩니다.')


# ── 2. 문제 확인 ───────────────────────────────────────
def step_problem(sim, story, top):
    cid = story['focus']; o = sim.observe()
    left, right = st.columns([1.5, 1], gap='medium')
    planned = story['planned']
    with left:
        with st.container(key='canvas'):
            panel('야드 현재 상태', subtitle=f'{tm(o.now)} · 노랑 = 대표 컨테이너(트럭 위) · 노랑 테두리 = 기존 계획 위치 · 빨강 = 인출 방해')
            mark = (planned, len(o.yard[planned]) + 1) if not locate(o.yard, cid) and len(o.yard[planned]) < 4 else None
            st.plotly_chart(yard_figure(o, cid, None, 430, False, mark), width='stretch', theme=None, key='scn_problem3d',
                            config={'displayModeBar': False, 'scrollZoom': False})
            legend3d()
    with right:
        with st.container(key='focus'):
            panel('문제 확인')
            story['progress']['problem_seen'] = True
            conflict = planned_conflict(o, cid, planned) if sim.statuses[cid] == 'YARD_QUEUE' else []
            if conflict:
                names = ', '.join(f'{x}(#{o.plan[x].sequence})' for x in conflict)
                html(f'<div class="why danger"><b>기존 계획대로 놓으면 문제가 생깁니다.</b><br>{planned}에는 이미 {names}가 있습니다. '
                     f'{cid}(#{o.plan[cid].sequence})를 그 위에 놓으면 먼저 실어야 할 화물을 가로막아, 인출 때 다시 옮겨야 합니다.</div>')
            else:
                html(f'<div class="why"><b>기존 계획 위치 {planned}에는 먼저 실을 화물이 없습니다.</b><br>그래도 함께 기다리는 트럭과의 처리 순서는 비교할 수 있습니다.</div>')
            pairs = blocking_pairs(o)
            if pairs:
                table(['가로막는 화물(빨강)', '가로막히는 화물', '이유'],
                      [[escape(a), escape(b), f'#{o.plan[b].sequence} 먼저 인출'] for b, a in pairs[:5]])
                st.caption(f'야드 전체의 인출 방해 관계 {len(pairs)}건 중 일부입니다.')
            html(f'<div class="why">같은 블록에는 {cid} 외에도 하차를 기다리는 트럭이 있습니다. 다음 단계에서 <b>누구를 먼저, 어디에 내릴지</b> 비교합니다.</div>')
    nav(1, top, '다음 단계: 대안 비교 →')


# ── 3. 대안 비교 ───────────────────────────────────────
def alt_name(a, labels):
    return f'{a["rank"]}안 · {sv.order_text(a["option"]["order"], labels)}'


def alt_kind(a, base):
    """기준안과 무엇이 다른지: 순서 변경 / 위치만 변경. 위치만 바꾼 안과 비교하면 위치 변경의 효과를 따로 볼 수 있습니다."""
    same_order = a['option']['order'] == base['option']['order']
    return '도착순 유지 · 위치만 변경' if same_order else '처리 순서 변경'


def step_compare(sim, story, top):
    cid = story['focus']
    if sim.statuses[cid] not in ('YARD_QUEUE',) and not story.get('decision'):
        html('<div class="why">대표 컨테이너가 CY에 도착해야 대안을 계산할 수 있습니다. 1단계에서 도착까지 진행하세요.</div>')
        nav(2, top); return
    if story.get('decision'):
        html('<div class="why">이 작업은 이미 판단을 마쳤습니다. 다른 대안으로 다시 해 보려면 [같은 상황에서 새 작업 시작]을 누르세요.</div>')
        locked_summary(story)
        nav(2, top, '결과 확인으로 →', on_next=lambda: go(5 if story['decision']['type'] == 'approve' else 4))
        return
    alts = current_alts(sim, story)
    if not alts['options']:
        html('<div class="why danger">제약을 만족하는 처리 순서가 없습니다.</div>'); nav(2, top); return
    labels = alts['labels']; base = alts['baseline']; br = base['run']
    sv.waiting_list(sim, alts['res'], cid)
    pick = chosen(alts, story)
    # 비교 표
    rows = [['기준안(도착순 · 기존 계획 위치)', sv.order_text(base['option']['order'], labels), f'{br["total_min"]:.1f}분',
             f'{br["move_min"]:.1f}분', f'{br["wait_min"]:.1f}분', f'{seq.minutes_delta(base["option"], base["option"])["rehandles"][1]:.1f}회', '—']]
    for a in alts['options']:
        r = a['run']; saved = br['total_min'] - r['total_min']
        rows.append([('★ ' if a['rank'] == 1 else '') + f'{a["rank"]}안' + (' (추천 1위)' if a['rank'] == 1 else '') + f'<br><small>{alt_kind(a, base)}</small>',
                     sv.order_text(a['option']['order'], labels), f'{r["total_min"]:.1f}분', f'{r["move_min"]:.1f}분',
                     f'{r["wait_min"]:.1f}분', f'{a["delta"]["rehandles"][0]:.1f}회',
                     f'<span class="{"good" if saved > .05 else "bad" if saved < -.05 else ""}">{saved_text(saved)}</span>'])
    with st.container(key='altcompare'):
        panel('대안별 비교', subtitle='같은 초기 상태(지금 이 순간)에서 대안마다 하차를 실제로 실행해 계산한 값입니다.')
        table(['대안', '처리 순서', '하차 완료까지 작업시간', '장비 이동시간', '트럭 대기 합계', '예상 재취급(야드·60분)', '기준 대비 작업시간'], rows)
        st.caption('작업시간 = 지금부터 세 트럭의 하차가 모두 끝날 때까지. 장비 이동시간 = 그동안 크레인이 움직인 시간(하차·재취급·인출 포함). '
                   '예상 재취급 = 도착 시각 8가지 가정 · 앞으로 60분 · 야드 전체 평균. 규칙상 놓을 곳이 없는 순서는 대안에서 뺍니다.')
    # 대안 카드(선택)
    cols = st.columns(len(alts['options']))
    for col, a in zip(cols, alts['options']):
        k = alt_key(a['option']); sel = k == story['alt']; r = a['run']
        with col:
            with st.container(key=f'altcard-{"sel" if sel else "off"}-{a["rank"]}'):
                pos = ' · '.join(f'{labels[c]}→{d[3:]}' for c, d, _ in a['option']['positions'])
                html(f'<div class="alt-head"><b>{escape(alt_name(a, labels))}</b>{badge("추천 1위", "") if a["rank"] == 1 else ""}{badge(alt_kind(a, base), "blue")}'
                     f'{badge("선택됨", "amber") if sel else ""}</div>'
                     f'<div class="alt-pos">{escape(pos)}</div>'
                     f'<div class="alt-big">{r["total_min"]:.1f}<small>분</small><span>기준 대비 {saved_text(br["total_min"] - r["total_min"])}</span></div>')
                if st.button('✓ 선택됨' if sel else '이 대안 선택', key=f'alt_pick_{a["rank"]}', width='stretch',
                             type='secondary' if sel else 'primary', disabled=sel):
                    story['alt'] = k; st.session_state.pop('scn_play', None); st.rerun()
    pick = chosen(alts, story)
    top1 = alts['options'][0]
    t1 = top1['run']
    html(f'<div class="why"><b>추천 1위 근거</b> · 같은 초기 상태에서 기준안보다 하차 완료가 <b>{br["total_min"] - t1["total_min"]:.1f}분</b> 빠르고 '
         f'(기준 {br["total_min"]:.1f}분 → {t1["total_min"]:.1f}분), 장비 이동시간이 {br["move_min"] - t1["move_min"]:.1f}분 짧습니다. '
         f'앞으로 60분 예상 재취급은 {top1["delta"]["rehandles"][1]:.1f}회 → {top1["delta"]["rehandles"][0]:.1f}회입니다. '
         + escape(next((r['why'] for r in seq.reasons(sim, top1['option'], base['option']) if r['cid'] == cid), '')) + '</div>')
    if len(alts['options']) > 1:
        # 표의 실행 결과가 같아도 순위는 도착 상황 표본 전체의 종합 점수(J)로 정해집니다.
        sc = ' · '.join(f'{a["rank"]}안 {a["option"]["J"]:,.0f}점' for a in alts['options'])
        st.caption(f'순위 기준 · 도착 상황 {alts["res"]["samples"]}가지 표본에서 계산한 종합 점수 J(추가 이동 작업시간·트럭 대기·인출 지연·인출 가로막힘의 가중합, '
                   f'낮을수록 좋음): {sc}. 위 표의 실행 결과가 같은 대안도 이 점수로 순위가 갈립니다.')
    simulation_player(sim, story, pick, base, labels)
    with st.expander('대안별 화물 처리 근거(계산)'):
        for a in alts['options']:
            st.markdown(f'**{alt_name(a, labels)}**')
            for r in seq.reasons(sim, a['option'], base['option']):
                st.markdown(f'- {labels[r["cid"]]} {r["cid"]} · {r["vessel"]} · {r["why"]}')
    sv.sensitivity_panel(sim, story, alts['res'])
    nav(2, top, f'{alt_name(pick, labels)}으로 적치 미리보기 →')


def simulation_player(sim, story, a, base, labels):
    """선택한 대안의 실행 과정을 단계별로 재생합니다. 재생 · 일시정지 · 초기화."""
    run = a['run']; steps = run['steps']
    key = alt_key(a['option'])
    play = st.session_state.get('scn_play')
    with st.container(key='simplayer'):
        panel('시뮬레이션 실행', subtitle=f'선택한 대안: {alt_name(a, labels)} · 같은 초기 상태에서 실제 작업 규칙으로 실행합니다.')
        if not play or play.get('alt') != key:
            if st.button('▶ 시뮬레이션 실행', key='sim_run', type='primary'):
                st.session_state.scn_play = {'alt': key, 'i': 0, 'running': True}; st.rerun()
            st.caption('실행하면 세 트럭이 처리 순서대로 하차·적치되는 과정과 크레인 작업이 단계별로 재생됩니다.')
            return
        c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
        if c1.button('⏸ 일시정지' if play['running'] else '▶ 재생', key='sim_toggle', width='stretch'):
            if not play['running'] and play['i'] >= len(steps) - 1:
                play['i'] = 0
            play['running'] = not play['running']; st.rerun()
        if c2.button('⏭ 다음', key='sim_step', width='stretch', disabled=play['i'] >= len(steps) - 1):
            play['running'] = False; play['i'] += 1; st.rerun()
        if c3.button('⏮ 초기화', key='sim_reset', width='stretch'):
            play.update(i=0, running=False); st.rerun()

        @st.fragment(run_every=1.2 if play['running'] else None)
        def frame():
            p = st.session_state.scn_play
            if p['running'] and p['i'] < len(steps) - 1:
                p['i'] += 1
            elif p['running']:
                p['running'] = False
                st.rerun()
            i = p['i']; s = steps[i]; m = s['move']
            left, right = st.columns([1.3, 1], gap='medium')
            with left:
                new = [c for c in a['option']['order'] if any(x['move']['container_id'] == c and x['move']['move_type'] == 'INITIAL'
                                                               for x in steps[1:i + 1])]
                html(snapshot_html(sim, s['yard'], labels, m['container_id'] if m else None, new))
                html(f'<div class="sim-now">{i} / {len(steps) - 1} 단계 · {tm(s["t"])}'
                     + (f' · <b>{escape(labels.get(m["container_id"], ""))} {escape(m["container_id"])} {MOVE_WORDS[m["move_type"]]}</b>'
                        f' {escape(m["source_slot"] or "트럭")} → {escape(m["target_slot"] or "본선")}' if m else ' · 실행 전') + '</div>')
            with right:
                rows = []
                for j, x in enumerate(steps[1:], 1):
                    mv = x['move']
                    state = '완료' if j <= i else '대기'
                    rows.append([f'<b>{j}</b>' if j == i else str(j), tm(mv['start_at']) + '–' + tm(mv['end_at']),
                                 escape((labels.get(mv['container_id'], '') + ' ' + mv['container_id'][-4:]).strip()),
                                 MOVE_WORDS[mv['move_type']], badge(state, '' if state == '완료' else 'blue')])
                table(['#', '시각', '컨테이너', '작업', '상태'], rows)
                done = i >= len(steps) - 1
                br = base['run']
                html(f'<div class="why"><b>{"실행 완료" if done else "실행 중"}</b> · 하차 완료까지 {run["total_min"]:.1f}분 '
                     f'(기준안 {br["total_min"]:.1f}분, <b>{saved_text(br["total_min"] - run["total_min"])}</b>) · 장비 이동 {run["move_min"]:.1f}분 · '
                     f'재취급 {run["rehandles"]}회</div>')
        frame()


def locked_summary(story):
    d = story['decision']
    if d['type'] == 'approve':
        html(f'<div class="why"><b>승인한 대안</b> · {escape(d["label"])} · 하차 완료까지 {d["total_min"]:.1f}분(기준 대비 {saved_text(d["saved_min"])})</div>')
    else:
        html(f'<div class="why"><b>보류</b> · {escape(d.get("label", ""))}</div>')


# ── 4. 적치 미리보기 ───────────────────────────────────
def step_preview(sim, story, top):
    cid = story['focus']
    if sim.statuses[cid] != 'YARD_QUEUE' and not story.get('decision'):
        html('<div class="why">대표 컨테이너가 CY에 도착해야 미리보기를 만들 수 있습니다.</div>'); nav(3, top); return
    d = story.get('decision')
    if d:
        o = d['pre'].observe(); option = d['option']; labels = d['labels']; name = d['label']
    else:
        alts = current_alts(sim, story)
        a = chosen(alts, story)
        o = sim.observe(); option = a['option']; labels = alts['labels']; name = alt_name(a, labels)
        names = {alt_key(x['option']): alt_name(x, labels) + (' (추천 1위)' if x['rank'] == 1 else '') for x in alts['options']}
        new = st.radio('미리볼 대안', list(names), format_func=names.get, index=list(names).index(story['alt']), horizontal=True, key='prev_alt')
        if new != story['alt']:
            story['alt'] = new; st.session_state.pop('scn_play', None); st.rerun()
    yard, tiers = yard_after(o, option)
    pick = story.get('pick') if story.get('pick') in {x for v in yard.values() for x in v} else cid
    story['pick'] = pick
    panel(f'적치 미리보기 · {name}', subtitle='칸을 클릭하면 그 컨테이너가 강조되고 화살표가 위치를 가리킵니다. 점선 = 이번에 내릴 트럭(A·B·C).')
    clickable_grid(sim, o, yard, labels, tiers, pick, story)
    left, right = st.columns([1.5, 1], gap='medium')
    o2 = copy(o); o2.yard = yard
    o2.statuses = {**o.statuses, **{c: 'STORED' for c in tiers}}
    with left:
        with st.container(key='canvas'):
            st.plotly_chart(yard_figure(o2, pick, None, 430), width='stretch', theme=None, key='scn_preview3d',
                            config={'displayModeBar': False, 'scrollZoom': False})
            st.caption('3D에서도 선택한 컨테이너가 노랑으로 강조되고 ▼ 라벨이 위치를 가리킵니다. 마우스를 올리면 정보가 보입니다.')
    with right:
        with st.container(key='focus'):
            pick_detail(sim, o, yard, labels, tiers, pick, option)
    nav(3, top, '다음 단계: 배치 승인 →' if not d else '결과 확인으로 →', on_next=(lambda: go(5)) if d and d['type'] == 'approve' else None)


def clickable_grid(sim, o, yard, labels, tiers, pick, story):
    vi = vessel_index(sim)
    risks = set()
    for k, items in yard.items():
        for i, x in enumerate(items):
            if any(rank(o.plan, y) < rank(o.plan, x) for y in items[:i]):
                risks.add(x)
    stacks = sorted(yard)
    a1 = [k for k in stacks if k.startswith('A1')]; b1 = [k for k in stacks if k.startswith('B1')]
    cols = st.columns([1] * len(a1) + [.35] + [1] * len(b1), gap='small')
    pick_pos = locate(yard, pick)
    for col, k in zip(cols[:len(a1)] + cols[len(a1) + 1:], a1 + b1):
        with col:
            items = yard[k]
            # 선택한 컨테이너 바로 위 칸이 비어 있으면 그 칸에, 위가 막혀 있으면(또는 4단이면) 스택 맨 위에 화살표를 둡니다.
            here = pick_pos and pick_pos[0] == k
            arrow_in_cell = here and pick_pos[1] == len(items) and len(items) < 4
            arrow_top = here and not arrow_in_cell
            html(f'<div class="yarrow{" on" if arrow_top else ""}">{"▼" if arrow_top else ""}</div>')
            for t in range(4, 0, -1):
                if t <= len(items):
                    x = items[t - 1]
                    state = 'sel' if x == pick else 'new' if x in tiers else 'blk' if x in risks else f'v{vi[sim.bundle.containers[x].vessel_id]}'
                    lab = ('▶ ' if x == pick else '') + (labels[x] + '·' if x in tiers else '') + str(o.plan[x].sequence)
                    with st.container(key=f'ycell-{state}-{k}-{t}'):
                        if st.button(lab, key=f'ycell_btn_{k}_{t}', width='stretch', help=f'{x} · 선적 순서 #{o.plan[x].sequence}'):
                            story['pick'] = x; st.rerun()
                else:
                    on = arrow_in_cell and t == pick_pos[1] + 1
                    html(f'<div class="ycell-empty{" arrow" if on else ""}">{"▼" if on else ""}</div>')
            html(f'<div class="ycell-name">{k}</div>')
    html('<div class="ylegend"><span><i class="sw v0"></i>OCEAN HARMONY</span><span><i class="sw v1"></i>PACIFIC LINK</span>'
         '<span><i class="sw newk"></i>이번에 내릴 트럭(라벨)</span><span><i class="sw blk"></i>먼저 실을 화물 위에 놓인 화물</span>'
         '<span><i class="sw selk"></i>선택한 컨테이너 ▼</span><span class="muted">칸 숫자 = 선적(인출) 순서</span></div>')


def pick_detail(sim, o, yard, labels, tiers, pick, option):
    c = sim.bundle.containers[pick]
    k, t = locate(yard, pick)
    items = yard[k]
    below = [x for x in items[:t - 1] if rank(o.plan, x) < rank(o.plan, pick)]
    above = [x for x in items[t:] if rank(o.plan, x) > rank(o.plan, pick)]
    order = option['order']
    role = (f'이번 하차 {order.index(pick) + 1}번째 ({labels[pick]})' if pick in tiers else '기존 적치 화물')
    panel('선택한 컨테이너', subtitle=pick)
    table(['항목', '내용'], [['위치', slot(k, t)], ['역할', role], ['선박', c.vessel_id], ['선적(인출) 순서', f'#{o.plan[pick].sequence}'],
                           ['무게', f'{c.weight_t}t'], ['적층 상태', f'{k} 스택 {len(items)}단 중 {t}단']])
    if below:
        html(f'<div class="why danger">아래에 먼저 실을 화물 {len(below)}개({", ".join("#" + str(o.plan[x].sequence) for x in below)})를 가로막습니다.</div>')
    elif above:
        html(f'<div class="why danger">위에 늦게 실을 화물 {len(above)}개가 있어 인출 때 재취급이 필요할 수 있습니다.</div>')
    else:
        html('<div class="why">아래·위 화물과 인출 순서가 맞습니다. 이 화물 때문에 생기는 재취급은 없습니다.</div>')
    rows = [[labels[x], escape(x), f'{d[3:]}-{tiers[x][1]:02d}' if x in tiers else '—', f'#{o.plan[x].sequence}'] for x, d, _ in option['positions']]
    table(['라벨', '컨테이너', '내릴 위치', '선적'], rows)
    b = st.columns(len(option['order']))
    for col, x in zip(b, option['order']):
        if col.button(f'{labels[x]} 보기', key=f'pick_lab_{x}', width='stretch', disabled=x == pick):
            st.session_state.story['pick'] = x; st.rerun()


# ── 5. 배치 승인 ───────────────────────────────────────
def step_approve(sim, story, top, log_decision):
    cid = story['focus']; d = story.get('decision')
    if d:
        locked_summary(story)
        if d['type'] == 'hold':
            if st.button('보류 해제 후 다시 검토', key='scn_unhold'):
                story['decision'] = None; go(2)
            nav(4, top, '누적 작업 이력 보기 →', on_next=lambda: go(6))
        else:
            nav(4, top, '결과 확인 →', on_next=lambda: go(5))
        return
    if sim.statuses[cid] != 'YARD_QUEUE':
        html('<div class="why">대표 컨테이너가 CY에 도착한 뒤 승인할 수 있습니다.</div>'); nav(4, top); return
    alts = current_alts(sim, story); a = chosen(alts, story); labels = alts['labels']
    base = alts['baseline']; r = a['run']; saved = base['run']['total_min'] - r['total_min']
    o = sim.observe(); block = o.containers[cid].block
    left, right = st.columns([1.2, 1], gap='medium')
    with left:
        with st.container(key='focus'):
            panel(f'승인할 배치 · {alt_name(a, labels)}', subtitle='다른 대안으로 바꾸려면 ← 이전 단계에서 선택하세요.')
            _, tiers = yard_after(o, a['option'])
            table(['순서', '라벨', '컨테이너', '내릴 위치'], [[str(i), labels[c], escape(c) + (' (대표)' if c == cid else ''), slot(*tiers[c])]
                                                     for i, c in enumerate(a['option']['order'], 1)])
            html(f'<div class="why"><b>예상 결과</b> · 하차 완료까지 {r["total_min"]:.1f}분 (기준안 {base["run"]["total_min"]:.1f}분 대비 <b>{saved_text(saved)}</b>) · '
                 f'장비 이동 {r["move_min"]:.1f}분 · 앞으로 60분 예상 재취급 {a["delta"]["rehandles"][0]:.1f}회(기준 {a["delta"]["rehandles"][1]:.1f}회)</div>')
    with right:
        with st.container(key='review'):
            panel('승인 직전 확인')
            arrived = all(c in sim.yard_arrivals for c in a['option']['order'])
            idle = sim.cranes[block] is None
            same = story.get('rec_key') == seq.cache_key(sim, block)
            valid = sim.now <= story.get('rec_valid', 0)
            checks = [('대기 트럭', f'{sum(c in sim.yard_arrivals for c in a["option"]["order"])}/{len(a["option"]["order"])}대 CY 대기', arrived),
                      ('장비 상태', f'YC-{block} ' + ('대기 중' if idle else '작업 중'), idle),
                      ('야드·계획 버전', f'Y{sim.yard_version} · {sim.plan_version} (추천 계산 때와 같음)' if same else '추천 이후 바뀜', same),
                      ('추천 유효시간', f'{tm(story.get("rec_valid", 0))}까지 · 현재 {tm(sim.now)}', valid)]
            table(['확인 항목', '내용', ''], [[k, escape(v), '✓' if ok else '✗'] for k, v, ok in checks])
            sp = [c for c in a['option']['order'] if sv.special(sim, c)]
            ok_sp = st.checkbox(f'특수 화물({", ".join(labels[c] for c in sp)}) 현장 확인 완료', key='scn_special') if sp else True
            reason = st.selectbox('판단 사유(선택)', REASONS, key='scn_reason')
            ok = all(x[2] for x in checks) and ok_sp
            b1, b2 = st.columns(2)
            if b1.button('✓ 배치 승인', type='primary', width='stretch', disabled=not ok, key='scn_approve'):
                approve(sim, story, alts, a, reason, log_decision)
            if b2.button('보류', width='stretch', key='scn_hold'):
                hold(sim, story, alts, a, reason, log_decision)
            if not ok:
                st.caption('✗ 항목이 있으면 승인할 수 없습니다. ← 이전 단계에서 대안을 다시 계산하세요.')
            st.caption('승인하면 순서·위치가 장비 작업 계획에 한 번만 올라가 실행되고, 작업 이력에 저장된 뒤 결과 확인으로 이동합니다.')
    nav(4, top)


def compared_list(alts, labels):
    br = alts['baseline']['run']
    return [{'대안': '기준안', '순서': sv.order_text(alts['baseline']['option']['order'], labels), '작업시간(분)': round(br['total_min'], 1)}] + \
           [{'대안': f'{x["rank"]}안', '순서': sv.order_text(x['option']['order'], labels), '작업시간(분)': round(x['run']['total_min'], 1),
             '절감(분)': round(br['total_min'] - x['run']['total_min'], 1)} for x in alts['options']]


def approve(sim, story, alts, a, reason, log_decision):
    if story.get('decision'):
        return
    cid = story['focus']; labels = alts['labels']; base = alts['baseline']
    pre = deepcopy(sim)
    plan = plan_of(a['option']); base_plan = plan_of(base['option'])
    sim.unload_plan = list(plan)
    at = sim.now
    advance_until(sim, lambda: order_done(sim, a['option']['order']))    # 모의 장비가 승인한 순서대로 실행
    cmp_plan = plan if plan != base_plan else plan_of(alts['options'][0]['option'])
    compare = compare_orders(pre, base_plan, cmp_plan, cid, story['other'])
    pos = locate(sim.yard, cid)
    saved = base['run']['total_min'] - a['run']['total_min']
    basis = (f'기준안 대비 하차 완료 {saved_text(saved)}, 예상 재취급 {a["delta"]["rehandles"][1]:.1f}→{a["delta"]["rehandles"][0]:.1f}회'
             + (' · 추천 1위' if a['rank'] == 1 else f' · 추천 {a["rank"]}위(담당자 선택)'))
    reason_txt = '' if reason == REASONS[0] else reason
    km, cm = compare['keep']['result'].metrics, compare['chosen']['result'].metrics
    job = hist.add({'sid': sid(), 'sim_time': tm(at), 'source': '대표 시나리오', 'container': cid,
                    'compared': compared_list(alts, labels), 'approved': alt_name(a, labels),
                    'order_text': ' → '.join(f'{labels[c]}({c})' for c in a['option']['order']),
                    'total_min': round(a['run']['total_min'], 2), 'base_total_min': round(base['run']['total_min'], 2),
                    'saved_min': round(saved, 2), 'reason': (reason_txt + ' · ' if reason_txt else '') + basis, 'status': '완료',
                    'detail': {'적치 위치': ' · '.join(f'{labels[c]} {m["target_slot"]}' for c in a['option']['order']
                                                   for m in sim.moves if m['container_id'] == c and m['move_type'] == 'INITIAL' and m['completed']),
                               '장비 이동(분)': round(a['run']['move_min'], 1), '재취급(실행)': a['run']['rehandles'],
                               '같은 사건 끝까지 · 총 추가 이동': f'{km["extra_moves"]} → {cm["extra_moves"]}',
                               '대표 재이동': f'{compare["keep"]["focus_rehandled"]} → {compare["chosen"]["focus_rehandled"]}'}})
    story['decision'] = {'type': 'approve', 'kind': 'order', 'at': at, 'order': a['option']['order'], 'plan': plan, 'base_plan': base_plan,
                         'labels': labels, 'pre': pre, 'option': a['option'], 'label': alt_name(a, labels), 'reason': reason_txt,
                         'stack': pos[0] if pos else None, 'tier': pos[1] if pos else None, 'slot': slot(*pos) if pos else '—',
                         'rec_id': job, 'job_id': job, 'total_min': a['run']['total_min'], 'base_total_min': base['run']['total_min'],
                         'saved_min': saved, 'move_min': a['run']['move_min'], 'basis': basis, 'same_as_base': plan == base_plan,
                         'top_plan': plan_of(alts['options'][0]['option'])}
    story['compare'] = compare
    story['progress'].update(compared=tm(at), result_checked=tm(sim.now))
    story['guide'] = {'lane': f'{sim.bundle.containers[cid].block} 블록', 'at': tm(at)}
    log_decision(story, sim, cid, '승인', alt_name(a, labels), reason_txt, job)
    go(5)


def hold(sim, story, alts, a, reason, log_decision):
    cid = story['focus']; labels = alts['labels']
    reason_txt = '' if reason == REASONS[0] else reason
    job = hist.add({'sid': sid(), 'sim_time': tm(sim.now), 'source': '대표 시나리오', 'container': cid,
                    'compared': compared_list(alts, labels), 'approved': '— (보류)', 'order_text': '—',
                    'total_min': None, 'base_total_min': round(alts['baseline']['run']['total_min'], 2), 'saved_min': None,
                    'reason': reason_txt or '보류', 'status': '보류', 'detail': {'검토한 대안': alt_name(a, labels)}})
    story['decision'] = {'type': 'hold', 'at': sim.now, 'label': f'보류 · 검토한 대안 {alt_name(a, labels)}', 'reason': reason_txt, 'job_id': job}
    log_decision(story, sim, cid, '보류', '—', reason_txt, job)
    go(6)


# ── 6. 결과 확인 ───────────────────────────────────────
def step_result(sim, story, top):
    cid = story['focus']; d = story.get('decision')
    if not d or d['type'] != 'approve':
        html('<div class="why">승인한 배치가 있어야 결과를 볼 수 있습니다. 5단계에서 배치를 승인하세요.</div>'); nav(5, top); return
    labels = d['labels']
    html(f'<div class="done-banner">✓ 배치 승인 · 작업 완료 <span>{escape(d["label"])} · 작업 ID {escape(d["job_id"])} · 누적 작업 이력에 저장됨</span></div>')
    left, right = st.columns([1.5, 1], gap='medium')
    with left:
        with st.container(key='canvas'):
            panel('승인한 작업 3D 재생', subtitle='실행 로그를 그대로 재생합니다. 다시 봐도 작업이 다시 실행되지 않습니다.')
            steps, final = replay_steps(sim.bundle, sim.moves, d['at'], sim.now, cid)
            st.plotly_chart(replay_figure(sim.bundle, sim.plan, steps, final, cid, trucks_at(sim)), width='stretch', theme=None,
                            key='scn_result3d', config={'displayModeBar': False, 'scrollZoom': False})
    with right:
        with st.container(key='focus'):
            panel('실행 결과')
            rows = []
            for c in d['order']:
                m = next((m for m in sim.moves if m['container_id'] == c and m['move_type'] == 'INITIAL' and m['completed']), None)
                pos = locate(sim.yard, c)
                rows.append([labels[c], escape(c) + (' (대표)' if c == cid else ''), m['target_slot'] if m else '—',
                             tm(m['end_at']) if m else '—', slot(*pos) if pos else STATUS.get(sim.statuses[c], sim.statuses[c])])
            table(['라벨', '컨테이너', '적치 위치', '완료', '현재'], rows)
            html(f'<div class="kpis"><div><span>하차 완료까지</span><b>{d["total_min"]:.1f}분</b></div>'
                 f'<div><span>기준안</span><b>{d["base_total_min"]:.1f}분</b></div>'
                 f'<div class="hl"><span>기준안 대비</span><b>{saved_text(d["saved_min"])}</b></div></div>')
            html(f'<div class="why"><b>판단 근거</b> · {escape(d["basis"])}' + (f'<br>사유: {escape(d["reason"])}' if d['reason'] else '') + '</div>')
    cmp = story.get('compare')
    if cmp:
        km, cm = cmp['keep']['result'].metrics, cmp['chosen']['result'].metrics
        with st.container(key='arrivals'):
            panel('같은 사건을 끝까지 실행한 비교', subtitle='결정 직전 상태를 복제해 기준안과 승인한 안을 본선 인출까지 실행한 값입니다(합성 데이터 한 장면).')
            def row(label, a, b, fmt='{:.0f}'):
                diff = b - a
                cls = '' if abs(diff) < 1e-9 else ('good' if diff < 0 else 'bad')
                return [label, fmt.format(a), fmt.format(b), f'<span class="{cls}">{"같음" if abs(diff) < 1e-9 else ("감소 " if diff < 0 else "증가 ") + fmt.format(abs(diff))}</span>']
            table(['지표', '기준안', '승인한 안', '차이'], [
                row('야드 전체 총 추가 이동(회)', km['extra_moves'], cm['extra_moves']),
                row('대표 컨테이너 재이동(회)', cmp['keep']['focus_rehandled'], cmp['chosen']['focus_rehandled']),
                row('평균 트럭 대기(분)', (km['truck_wait']['mean'] or 0) / 60, (cm['truck_wait']['mean'] or 0) / 60, '{:.1f}'),
                row('평균 인출 지연(분)', (km['retrieval_delay']['mean'] or 0) / 60, (cm['retrieval_delay']['mean'] or 0) / 60, '{:.1f}')])
    if story.get('guide'):
        with st.expander('역할별 안내(기사 앱 · 관제 · 선사)'):
            role_notices(sim, story, cid, d)
    nav(5, top, '다음 단계: 누적 작업 이력 →')


# ── 7. 누적 작업 이력 ──────────────────────────────────
def step_history(sim, story, top, reset):
    jobs = hist.list_jobs(sid())
    with st.container(key='arrivals'):
        panel('누적 작업 이력', subtitle=f'이 브라우저 주소(sid={sid()})로 승인·보류한 작업 {len(jobs)}건 · 최신순. 행을 클릭하면 상세 내용을 봅니다.')
        if not jobs:
            st.info('아직 저장된 작업이 없습니다. 5단계에서 배치를 승인하면 여기에 쌓입니다.')
        else:
            df = pd.DataFrame([{'작업 ID': j['job_id'], '작업 시각': j['sim_time'], '출처': j['source'], '컨테이너': j['container'],
                                '비교한 대안': len(j['compared'] or []), '승인한 대안': j['approved'], '처리 순서': j['order_text'],
                                '예상 총 작업시간(분)': j['total_min'], '기준 대비 절감(분)': j['saved_min'], '상태': j['status']} for j in jobs])
            ev = st.dataframe(df, hide_index=True, width='stretch', on_select='rerun', selection_mode='single-row', key='hist_df')
            sel = ev.selection.rows if ev and ev.selection else []
            j = jobs[sel[0]] if sel else jobs[0]
            st.caption('행을 고르지 않으면 가장 최근 작업을 보여 줍니다.' if not sel else '')
            panel(f'상세 · {j["job_id"]}')
            detail = [['작업 시각(운영)', j['sim_time']], ['출처', j['source']], ['선택한 컨테이너', j['container']], ['최종 승인한 대안', j['approved']],
                      ['컨테이너 처리 순서', j['order_text']], ['예상 총 작업시간', f'{j["total_min"]}분' if j['total_min'] is not None else '—'],
                      ['기준 대안 대비', saved_text(j['saved_min'])],
                      ['판단 근거·사유', j['reason'] or '—'], ['작업 상태', j['status']]]
            for k, v in (j['detail'] or {}).items():
                detail.append([k, str(v)])
            table(['항목', '내용'], [[escape(a), escape(str(b))] for a, b in detail])
            if j['compared']:
                table(list(j['compared'][0].keys()) + (['절감(분)'] if '절감(분)' not in j['compared'][0] else []),
                      [[escape(str(r.get(k, '—'))) for k in list(j['compared'][0].keys()) + (['절감(분)'] if '절감(분)' not in j['compared'][0] else [])]
                       for r in j['compared']])
        st.caption('저장 위치: 서버의 SQLite 파일(runtime/history.db). 새로고침해도 같은 주소면 유지됩니다. '
                   '단, Streamlit Cloud에서 앱이 재시작·재배포되면 서버 디스크가 초기화되어 이력이 지워질 수 있습니다.')
    a, b = st.columns(2)
    if a.button('↻ 같은 상황에서 새 작업 시작(대안 비교부터)', type='primary', width='stretch', key='scn_new_job'):
        new_job(reset, True)
    if b.button('처음부터(상황 확인)', width='stretch', key='scn_new_start'):
        new_job(reset, False)


# ── 페이지 ─────────────────────────────────────────────
def scenario_page(sim, story, goto, reset):
    from ui.story_page import log_decision
    cid = story['focus']
    a, b = st.columns([5, 1.3], vertical_alignment='center')
    a.html('<div class="story-intro">도착이 늦어진 수출 컨테이너 <b>SYNC2600013</b>와 함께 기다리는 트럭들의 '
           '<b>하차 순서·적치 위치를 비교 → 승인 → 결과 확인</b>하는 대표 시나리오입니다. 아래 단계 버튼이나 [다음 단계]로 진행하세요.</div>')
    if b.button('↻ 같은 상황에서 새 작업', width='stretch', help='누적 작업 이력은 남기고, 시나리오만 처음 상태로 되돌려 대안 비교부터 다시 합니다.',
                key='scn_new_top'):
        new_job(reset, True)
    summary_bar(sim, story, cid)
    top = reached(sim, story)
    cur = st.session_state.get('scn_step', 0)
    if cur > top and cur != 6:
        cur = top
    st.session_state.scn_step = cur
    stepper(cur, top)
    [lambda: step_situation(sim, story, top, reset), lambda: step_problem(sim, story, top), lambda: step_compare(sim, story, top),
     lambda: step_preview(sim, story, top), lambda: step_approve(sim, story, top, log_decision), lambda: step_result(sim, story, top),
     lambda: step_history(sim, story, top, reset)][cur]()
