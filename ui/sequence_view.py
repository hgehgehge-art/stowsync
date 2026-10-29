"""③ 대안 비교의 3분할 화면: 위 대기 리스트 · 왼쪽 처리 순서 추천 카드 · 오른쪽 장치장 미리보기.

숫자는 모두 services.sequence의 롤아웃 결과에서 계산합니다. 화면에 고정 수치를 쓰지 않습니다.
"""
from html import escape
import time
import streamlit as st
from domain.models import slot
from engine.yard import rank
from services import sequence as seq
from services.recommend import recommend_slots
from services.workflows import quadrant
from ui.theme import html, badge, panel, table, tm

LETTERS = 'ABCDEFGH'
SOURCE_NOTE = '올컨e·Port-i·TOS 정보 연결'
VALID_SECONDS = 60
# 선박별 색과 무늬: 색만으로 구분하지 않도록 무늬를 함께 씁니다.
# 노랑은 대표 컨테이너 표시에 쓰므로 선박 색에서는 뺍니다.
VESSEL_STYLE = [('#4C8DF0', 'solid'), ('#A78BFA', 'stripe'), ('#64d8c5', 'dots'), ('#c3cfdc', 'cross')]


def quality_grade(f):
    """입력 품질 등급(규칙 기반 점수 → 3단계). 확률이 아니므로 %를 쓰지 않습니다."""
    if f is None:
        return '미흡'
    return '양호' if f.trust_score >= 80 else '보통' if f.trust_score >= 60 else '미흡'


def vessel_styles(sim):
    names = sorted({c.vessel_id for c in sim.bundle.containers.values()})
    return {v: VESSEL_STYLE[i % len(VESSEL_STYLE)] for i, v in enumerate(names)}


def label_map(res):
    return {it['cid']: LETTERS[i] for i, it in enumerate(res['items'])}


def order_text(order, labels):
    return ' → '.join(labels.get(c, '?') for c in order)


def special(sim, cid):
    c = sim.bundle.containers[cid]
    return c.cargo_type if c.cargo_type and c.cargo_type != '일반' else ''


# ── 위: 대기 리스트 ────────────────────────────────────
def waiting_list(sim, res, focus):
    o = sim.observe()
    labels = label_map(res)
    styles = vessel_styles(sim)
    chips = []
    for it in res['items']:
        cid = it['cid']; c = sim.bundle.containers[cid]
        f = o.forecasts.get(cid)
        vs, vm = seq.vessel_status(sim, c.vessel_id)
        vtxt = f'{vs}' + (f' · {vm}분 후' if vm else '')
        if it['arrived']:
            eta = f'CY 도착 {tm(it["arrival"])}'
            grade = '도착 확인'
        else:
            eta = f'ETA {tm(f.p50)} ({tm(f.p10)}~{tm(f.p90)})' if f else 'ETA 없음'
            grade = '입력 품질 ' + quality_grade(f)
        arr, pri = quadrant(o, cid)
        color, pat = styles[c.vessel_id]
        sp = special(sim, cid)
        chips.append(f'<div class="wq {"focus" if cid == focus else ""}"><div class="wq-head"><span class="wq-l">{labels[cid]}</span>'
                     f'<b>{escape(cid)}</b>{badge("대표", "") if cid == focus else ""}{badge(sp, "red") if sp else ""}</div>'
                     f'<div class="wq-v"><i class="sw {pat}" style="--c:{color}"></i>{escape(c.vessel_id)} · {vtxt}</div>'
                     f'<div class="wq-row"><span>{eta}</span></div>'
                     f'<div class="wq-row"><span>{grade}</span><span>{arr} 도착 · 선적 {pri}</span><span>선적 순서 #{o.plan[cid].sequence}</span></div></div>')
    html(f'<div class="wq-wrap">{"".join(chips)}</div>')
    st.caption(f'{SOURCE_NOTE} · 입력 품질은 규칙 기반 점수를 3단계로 나눈 것이며 확률이 아닙니다. '
               '2×2 분류(도착 조기·지연 × 선적 상위·하위)는 검토 순서 설명용입니다.')


# ── 왼쪽: 추천 카드 ────────────────────────────────────
def fmt_delta(t):
    m, lo, hi = t
    return f'{m:+.1f}분 <small>({lo:+.1f}~{hi:+.1f})</small>'


def order_cards(sim, res, focus, pick_key='seq_pick'):
    labels = label_map(res)
    base = res['baseline']
    opts = res['options']
    if not opts:
        html(f'<div class="why">{escape(res.get("note", "추천할 순서가 없습니다."))}</div>')
        return None
    names = [f'{i + 1}안 · {order_text(o["order"], labels)}' for i, o in enumerate(opts)]
    pick = st.radio('미리볼 처리 순서', list(range(len(opts))), format_func=names.__getitem__, key=pick_key, horizontal=True)
    pick = min(pick or 0, len(opts) - 1)
    for i, opt in enumerate(opts):
        d = seq.minutes_delta(opt, base)
        same = opt['order'] == base['order']
        rh_o, rh_b = d['rehandles']
        why = seq.reasons(sim, opt, base)
        lines = ''.join(f'<li><b>{labels[r["cid"]]}</b> {escape(r["cid"])} · {escape(r["vessel"])}<br><span>{escape(r["why"])}</span></li>' for r in why)
        sp = [c for c in opt['order'] if special(sim, c)]
        html(f'<div class="opt {"best" if i == 0 else ""} {"sel" if i == pick else ""}"><div class="opt-head"><b>{i + 1}안 · {order_text(opt["order"], labels)}</b>'
             f'{badge("1순위", "") if i == 0 else ""}{badge("도착순과 같음", "") if same else ""}</div>'
             f'<div class="opt-nums"><span>추가 이동 작업시간 E {fmt_delta(d["E"])}</span><span>트럭 대기 T {fmt_delta(d["T"])}</span>'
             f'<span>인출 지연 D {fmt_delta(d["D"])}</span></div>'
             f'<div class="opt-nums"><span>예상 재취급(야드 전체·60분) <b>{rh_o:.1f}회</b> · 기준 {rh_b:.1f}회</span></div>'
             f'<ul class="opt-why">{lines}</ul>'
             + (f'<div class="why danger">특수 화물 포함({", ".join(labels[c] for c in sp)}) · 승인 전 현장 확인 필요</div>' if sp else '') +
             '</div>')
    st.caption(f'차이는 기준(도착순 · 대표는 기존 계획 위치) 대비이며, 같은 도착 표본 {res["samples"]}개의 평균(괄호는 표본별 최소~최대)입니다. '
               '음수가 줄어든 값입니다. 재취급은 대표 화물만이 아니라 야드 전체에서 앞으로 60분 동안 생길 것으로 계산한 값입니다.')
    with st.expander('계산 세부(점수 J)'):
        rows = [[f'{i + 1}안', order_text(o['order'], labels), f'{o["J"]:.0f}'] for i, o in enumerate(opts)]
        rows.append(['기준', order_text(base['order'], labels), f'{base["J"]:.0f}'])
        table(['안', '순서', '평균 J'], rows)
        st.caption(f'J = E + {seq.WEIGHTS["T"]}T + {seq.WEIGHTS["D"]}D + {seq.WEIGHTS["B"]:.0f}B. E 추가 이동(재취급·선작업) 작업시간, T 트럭 대기, D 인출 지연(모두 초), B 먼저 실을 화물을 가로막는 쌍의 수. 가중치는 가정값. '
                   f'평가한 순서 {len(res["all"])}개 · 계산 {res["ms"]}ms' + (' · 대기 5대 초과분은 도착순으로 뒤에 붙임' if res.get('limited') else ''))
    first = opts[pick]['order'][0]
    o = sim.observe()
    if first in o.containers and not o.containers[first].initial:
        rec = recommend_slots(o, first, 'C')
        if rec.candidates:
            table([f'첫 하차 {labels[first]} 위치 후보', '예상 재취급', '트럭 대기(분)'],
                  [[slot(c.stack, c.tier), f'{c.rehandles:.1f}', f'{c.wait_seconds / 60:.1f}'] for c in rec.candidates[:3]])
    return pick


# ── 오른쪽: 장치장 미리보기 ────────────────────────────
def yard_grid(sim, positions, labels, title=''):
    """2블록 × 6스택 × 4단. 점선 칸 = 이번 순서의 하차 위치, 빨간 테두리 = 그 위치 때문에 가로막히는 화물."""
    o = sim.observe()
    styles = vessel_styles(sim)
    height = {k: len(v) for k, v in o.yard.items()}
    planned = {}
    blocked = set()
    for cid, dst, _ in positions:
        if not dst:
            continue
        tier = height[dst] + 1
        height[dst] = tier
        planned[(dst, tier)] = cid
        for x in o.yard[dst]:
            if rank(o.plan, x) < rank(o.plan, cid):
                blocked.add(x)
        for (k, t), y in planned.items():
            if k == dst and t < tier and rank(o.plan, y) < rank(o.plan, cid):
                blocked.add(y)
    blocks = sorted({k[:2] for k in o.yard})
    out = []
    for b in blocks:
        stacks = sorted(k for k in o.yard if k.startswith(b))
        cols = []
        for k in stacks:
            cells = []
            for t in range(4, 0, -1):
                stack = o.yard[k]
                if t <= len(stack):
                    cid = stack[t - 1]; c = sim.bundle.containers[cid]
                    color, pat = styles[c.vessel_id]
                    cells.append(f'<div class="yc {pat} {"blk" if cid in blocked else ""}" style="--c:{color}" '
                                 f'title="{escape(cid)} · {escape(c.vessel_id)} · 선적 #{o.plan[cid].sequence}">{o.plan[cid].sequence}</div>')
                elif (k, t) in planned:
                    cid = planned[(k, t)]; c = sim.bundle.containers[cid]
                    color, _ = styles[c.vessel_id]
                    cells.append(f'<div class="yc plan" style="--c:{color}" title="{escape(cid)} 하차 예정">{labels.get(cid, "?")}</div>')
                else:
                    cells.append('<div class="yc empty"></div>')
            cols.append(f'<div class="ys"><div class="ys-cells">{"".join(cells)}</div><div class="ys-name">{k[3:]}</div></div>')
        out.append(f'<div class="yb"><div class="yb-name">{b} 블록</div><div class="yb-cols">{"".join(cols)}</div></div>')
    legend = ''.join(f'<span><i class="sw {p}" style="--c:{c}"></i>{escape(v)}</span>' for v, (c, p) in styles.items())
    html(f'<div class="ygrid">{"".join(out)}</div><div class="ylegend">{legend}<span><i class="sw plan"></i>하차 예정(라벨)</span>'
         f'<span><i class="sw blk"></i>가로막히게 될 화물</span><span class="muted">칸 숫자 = 선적 순서</span></div>')
    if title:
        st.caption(title)


# ── 실시간 이벤트 ─────────────────────────────────────
EVENT_WORDS = {'TRUCK_ARRIVAL': '트럭 게이트 도착', 'YARD_ARRIVAL': 'CY 도착', 'FORECAST_UPDATE': 'ETA 갱신', 'INJECTED_DELAY': '지연 주입',
               'MOVE_START': '작업 시작', 'MOVE_END': '작업 완료', 'PLAN_CHANGE': '계획 변경'}


def event_feed(sim, n=6):
    rows = [[tm(e['at']), EVENT_WORDS.get(e['kind'], e['kind']), escape(e['container_id'] or ''), escape(str(e['detail'])[:40])]
            for e in sim.events[-n:][::-1]]
    if rows:
        table(['시각', '사건', '컨테이너', '내용'], rows)


def live_controls(sim, story, focus):
    """시작·일시정지, 배속, 지연 주입. 1배속 = 실제 1초에 시뮬레이션 10초."""
    a, b, c = st.columns([1, 1.3, 1.6], vertical_alignment='bottom')
    running = st.session_state.get('seq_running', False)
    if a.button('⏸ 일시정지' if running else '▶ 시작', width='stretch', key='seq_run'):
        st.session_state.seq_running = not running; st.session_state.seq_last_tick = time.time(); st.rerun()
    speed = b.segmented_control('배속', ['1x', '5x', '10x'], default='1x', key='seq_speed')
    waiting = [it for it in seq.queue_items(sim, 'A1') if not it['arrived']]
    en_route = [cid for cid in sorted(sim.manual_ids) if sim.statuses.get(cid) == 'EN_ROUTE']
    targets = [it['cid'] for it in waiting] + [x for x in en_route if x not in [it['cid'] for it in waiting]]
    with c.popover('지연 주입', width='stretch', disabled=not targets):
        tgt = st.selectbox('운송 중 트럭', targets, key='seq_delay_cid')
        mins = st.select_slider('지연(분)', [10, 20, 30], value=20, key='seq_delay_min')
        if st.button('주입', key='seq_delay_go', width='stretch'):
            seq.inject_truck_delay(sim, tgt, mins)
            story.setdefault('log', []).append({'시각': tm(sim.now), '컨테이너': tgt, '결정': '지연 주입', '위치': f'+{mins}분', '사유': '도착 지연 사건'})
            st.rerun()
    if running:
        step = 10 * int((speed or '1x')[:-1])

        @st.fragment(run_every=1)
        def tick():
            # 앱 전체 실행 중에 함께 불릴 때는 건너뜁니다(1초 주기 재실행에서만 진행).
            now = time.time()
            if now - st.session_state.get('seq_last_tick', 0) < .9:
                return
            st.session_state.seq_last_tick = now
            end = sim.now + step
            while sim.queue and sim.queue[0][0] <= end:
                sim.advance(one_event=True)
            sim.now = max(sim.now, end)
            st.rerun(scope='app')
        tick()


# ── ③ 화면 ─────────────────────────────────────────────
def current_recommendation(sim, story, margin):
    focus = story['focus']
    block = sim.bundle.containers[focus].block
    res = seq.recommend_order(sim, block, {focus: story['planned']}, prev_top=story.get('seq_prev'), margin=margin)
    if res['options']:
        top = res['options'][0]['order']
        key = seq.cache_key(sim, block)
        if story.get('seq_key') != key:                 # 입력이 바뀌었을 때만 유효시간을 새로 시작
            story['seq_key'] = key
            story['seq_valid_until'] = sim.now + VALID_SECONDS
            if res['switched']:
                lab = label_map(res)
                story['seq_alert'] = (f'{tm(sim.now)} 추천 1순위가 {order_text(res["switched"]["from"], lab)} → {order_text(top, lab)}로 '
                                      f'바뀌었습니다(점수 차이 {res["switched"]["gain"]:.0f} ≥ 기준 {margin:.0f}).')
        elif sim.now > story.get('seq_valid_until', 0):   # 유효시간이 지나면 같은 입력으로 다시 확인
            story['seq_valid_until'] = sim.now + VALID_SECONDS
            story['seq_rechecked'] = tm(sim.now)
        story['seq_prev'] = top
        pos = {c: d for c, d, _ in res['options'][0]['positions']}
        story['last_best'] = pos.get(focus)
    return res


def stage_sequence(sim, story, goto):
    focus = story['focus']
    margin = st.session_state.get('seq_margin', seq.SWITCH_MARGIN)
    panel('③ 대안 비교 · 하차 처리 순서', 'QUEUE ORDER', '같은 블록에서 함께 기다리는 트럭을 어떤 순서로, 어디에 내릴지 비교합니다.')
    if story.get('decision'):
        html('<div class="why">이미 판단을 기록했습니다. ④·⑤ 단계에서 이어서 확인하세요.</div>'); return None
    live_controls(sim, story, focus)
    if sim.statuses[focus] != 'YARD_QUEUE':
        html('<div class="why">대표 컨테이너가 CY에 도착해야 실제 처리 순서를 계산할 수 있습니다. ① 단계에서 도착까지 진행하거나 ▶ 시작으로 진행하세요.</div>')
        event_feed(sim)
        return None
    res = current_recommendation(sim, story, margin)
    if story.get('seq_alert'):
        st.warning(story['seq_alert'])
    waiting_list(sim, res, focus)
    left, right = st.columns([1.1, 1], gap='medium')
    with left:
        pick = order_cards(sim, res, focus)
        sensitivity_panel(sim, story, res)
        if st.button('대안 비교 완료 → 승인 단계로', type='primary', width='stretch', disabled=bool(story['progress'].get('compared'))):
            story['progress']['compared'] = tm(sim.now); goto_stage(4)
    with right:
        if res['options']:
            opt = res['options'][pick or 0]
            panel('장치장 미리보기', 'YARD 2×6×4', f'{pick + 1 if pick is not None else 1}안대로 내렸을 때(첫 표본 기준)')
            yard_grid(sim, opt['positions'], label_map(res))
            vu = story.get('seq_valid_until')
            st.caption(f'추천 계산 {tm(sim.now)} · 유효 {tm(vu)}까지(60초, 지나면 같은 입력으로 다시 확인)'
                       + (f' · 마지막 재확인 {story["seq_rechecked"]}' if story.get('seq_rechecked') else '') + f' · 계산 {res["ms"]}ms')
        event_feed(sim)
    return res


def goto_stage(i):
    st.session_state._goto_stage = i
    st.rerun()


# ── ④ 처리 순서 승인 ──────────────────────────────────
def stage_decide_order(sim, story, reasons_list, log_decision):
    from copy import deepcopy
    focus = story['focus']
    block = sim.bundle.containers[focus].block
    margin = st.session_state.get('seq_margin', seq.SWITCH_MARGIN)
    res = current_recommendation(sim, story, margin)
    if not res['options']:
        html('<div class="why">승인할 처리 순서가 없습니다.</div>'); return
    labels = label_map(res)
    opts = res['options']
    names = [f'{i + 1}안 · {order_text(o["order"], labels)}' + (' (도착순과 같음)' if o['order'] == res['baseline']['order'] else '')
             for i, o in enumerate(opts)]
    default = min(st.session_state.get('seq_pick', 0) or 0, len(opts) - 1)
    choice = st.radio('승인할 처리 순서', list(range(len(opts))), format_func=names.__getitem__, index=default, key='seq_choice')
    opt = opts[choice]
    arrived = {c for c in sim.yard_arrivals}
    key_now = seq.cache_key(sim, block)
    vu = story.get('seq_valid_until', 0)
    checks = [('최신 대기 상태', f'대기 {len([c for c in opt["order"] if c in arrived])}/{len(opt["order"])}대 · 작업 중 장비 ' +
               ('있음' if sim.cranes[block] else '없음'), all(c in arrived or sim.statuses[c] in ('EN_ROUTE', 'GATE_QUEUE', 'GATE_SERVICE', 'INTERNAL_TRAVEL') for c in opt['order'])),
              ('입력 버전', f'야드 Y{sim.yard_version} · 계획 P{sim.plan_version}', story.get('seq_key') == key_now),
              ('추천 유효시간', f'{tm(vu)}까지 · 현재 {tm(sim.now)}', sim.now <= vu)]
    table(['승인 직전 확인', '내용', ''], [[k, escape(v), '✓' if ok else '✗'] for k, v, ok in checks])
    sp = [c for c in opt['order'] if special(sim, c)]
    ok_special = True
    if sp:
        ok_special = st.checkbox(f'특수 화물({", ".join(labels[c] + " " + special(sim, c) for c in sp)}) 현장 확인 완료', key='seq_special')
    ok = all(x[2] for x in checks) and ok_special
    if not ok:
        st.caption('확인 항목이 맞지 않으면 승인할 수 없습니다. ③으로 돌아가 다시 계산하세요.')
    reason = st.selectbox('판단 사유(선택)', reasons_list, key='story_reason')
    a, b = st.columns(2)
    if a.button('승인', type='primary', width='stretch', disabled=not ok, key='story_approve'):
        if story.get('decision'):                       # 한 번만 실행
            st.rerun()
        pre = deepcopy(sim)
        base_plan = [(c, d) for c, d, _ in res['baseline']['positions']]
        plan = [(c, d) for c, d, _ in opt['positions']]
        sim.unload_plan = list(plan)
        stack = dict(plan).get(focus)
        tier = len(sim.observe().yard[stack]) + 1 + sum(1 for c, d in plan[:[c for c, _ in plan].index(focus)] if d == stack) if stack else None
        label = names[choice]
        story['decision'] = {'type': 'approve', 'kind': 'order', 'at': sim.now, 'order': opt['order'], 'plan': plan, 'base_plan': base_plan,
                             'labels': labels, 'pre': pre, 'stack': stack, 'tier': tier, 'slot': slot(stack, tier) if stack else '—',
                             'rec_id': key_now[:12], 'label': label, 'reason': '' if reason == reasons_list[0] else reason,
                             'same_as_base': opt['order'] == res['baseline']['order'] and plan == base_plan,
                             'top_plan': [(c, d) for c, d, _ in opts[0]['positions']]}
        log_decision(story, sim, focus, '승인', label, story['decision']['reason'], key_now[:12])
        story['guide'] = {'lane': f'{block} 블록', 'at': tm(sim.now)}
        st.session_state.seq_running = False
        goto_stage(5)
    if b.button('보류', width='stretch', key='story_hold'):
        story['decision'] = {'type': 'hold', 'at': sim.now, 'label': '판단 보류 · 실행하지 않음',
                             'reason': '' if reason == reasons_list[0] else reason}
        log_decision(story, sim, focus, '보류', '—', story['decision']['reason'], key_now[:12])
        st.session_state.seq_running = False
        st.rerun()
    st.caption('승인하면 순서와 위치가 장비 작업 계획에 한 번만 올라갑니다.')


# ── 민감도 ─────────────────────────────────────────────
def sensitivity_panel(sim, story, res):
    """가중치·표본 수를 바꿔도 1순위가 유지되는지 확인합니다. 버튼을 눌렀을 때만 계산합니다."""
    if not res['options']:
        return
    focus = story['focus']
    block = sim.bundle.containers[focus].block
    labels = label_map(res)
    with st.expander('가정이 바뀌면 1순위도 바뀔까? (민감도)'):
        st.caption('추가 이동 작업시간 E의 가중치를 1로 두고 트럭 대기 T 가중치 0.25·0.5·1, 인출 지연 D 가중치 1·2·4, 가로막힘 B 가중치 30·60·120, '
                   '도착 표본 8·16·32개를 모두 조합(81가지)해 상위 10개 순서 중 1위가 무엇인지 다시 셉니다.')
        key = seq.cache_key(sim, block)
        if st.button('민감도 계산', key='seq_sens', width='stretch'):
            story['seq_sens'] = (key, seq.sensitivity(sim, block, {focus: story['planned']}))
        got = story.get('seq_sens')
        if not got or got[0] != key:
            return
        s = got[1]
        top = order_text(s['top'], labels)
        html(f'<div class="why"><b>{s["same"]}/{s["total"]}개 조합</b>에서 1순위가 기본 설정과 같은 <b>{top}</b>였습니다. '
             f'<span class="muted">계산 {s["ms"]}ms</span></div>')
        if s['changes']:
            from collections import Counter
            cnt = Counter(order_text(c['top'], labels) for c in s['changes'])
            table(['다른 1순위', '조합 수', '예시 조건'],
                  [[o, n, escape(next(f'T {c["T"]} · D {c["D"]} · B {c["B"]:.0f} · 표본 {c["S"]}' for c in s['changes']
                                      if order_text(c['top'], labels) == o))] for o, n in cnt.most_common()])
        st.caption('가중치는 정책 판단이 담긴 가정값이며 현장 자료로 보정하지 않았습니다. 이 결과는 이 사례 한 장면에 대한 계산이고, '
                   '어떤 가중치가 옳은지 알려 주지 않습니다.')
