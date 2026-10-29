"""대표 사례 흐름: 컨테이너 한 개를 도착 정보 변화부터 결과 비교까지 따라갑니다."""
from copy import deepcopy
from html import escape
import time
import streamlit as st
from domain.models import slot
from engine.yard import locate, rank
from services.recommend import propose_premarshal
from services.story import (STEPS, gate_and_yard_times, planned_conflict, blocking_pairs, build_options,
                            compare_branches, replay_steps, progress_state)
from ui.theme import html, badge, panel, table, tm, mins
from ui.scene import yard_figure, replay_figure, LEGEND

STATUS = {'EN_ROUTE': '운송 중', 'GATE_QUEUE': '게이트 대기', 'GATE_SERVICE': '게이트 처리', 'INTERNAL_TRAVEL': 'CY 이동 중',
          'YARD_QUEUE': '하차 대기', 'BLOCKED_CAPACITY': '공간 부족', 'STORED': '적치 완료', 'IN_MOVE': '작업 중',
          'RETRIEVED': '인출 완료', 'EXCEPTION_LATE': '마감 예외', 'WAIT_GATE_OPEN': '반입 대기'}
STAGES = ['① 상황 확인', '② 문제 확인', '③ 대안 비교', '④ 승인·보류', '⑤ 작업 실행', '⑥ 결과 확인']
REASONS = ['선택 안 함', '추천 근거와 현장 조건 일치', '장비 작업 순서 고려', '현장 혼잡', '시스템이 모르는 현장 제약', '기타']
SCOPE = '평가 범위: 야드 전체(블록 A1·B1) · 앞으로 60분 · 가능한 도착 상황 {n}가지를 가정한 예상 평균'


def cargo_text(c):
    if c.cargo_type == '위험물':
        return f'⚠ 위험물 {c.hazard_class}'
    if c.cargo_type == '환적':
        return f'환적 · {c.connecting_vessel}'
    return '일반 드라이'


def legend3d():
    items = ''.join(f'<span><i style="background:{c};{"opacity:.55" if "반투명" in t else ""}"></i>{t}</span>' for t, c in LEGEND)
    html(f'<div class="legend3d">{items}<span><i style="background:transparent;border:2px solid #FFB547"></i>기존 계획 위치</span>'
         '<span><b style="color:#fff">→</b> 승인된 이동 경로</span><span><b>⚠</b> 위험물(색과 무관)</span></div>')


def chart(fig, key):
    st.plotly_chart(fig, width='stretch', theme=None, key=key, config={'displayModeBar': False, 'scrollZoom': False})


def summary_bar(sim, story, cid):
    o = sim.observe()
    c = o.containers[cid]; f = o.forecasts.get(cid); p = o.plan.get(cid)
    pos = locate(o.yard, cid)
    d = story.get('decision')
    if sim.statuses[cid] == 'RETRIEVED':
        where = '본선 인출 완료'
    elif pos:
        where = f'현재 {slot(*pos)}'
    elif d and d['type'] == 'approve':
        where = f'예정 {d["slot"]}'
    else:
        where = f'기존 계획 {story["planned"]}'
    eta = f'{tm(f.p10)}–{tm(f.p90)}' if f and sim.statuses[cid] == 'EN_ROUTE' else (
        f'{tm(sim.trucks[cid]["gate_arrival"])}' if cid in sim.trucks else '정보 없음')
    top = '상위' if p and p.sequence <= max(1, int(len(o.plan) * .3)) else '하위'
    cells = [('컨테이너', cid), ('화물', cargo_text(c)), ('현재 상태', STATUS.get(sim.statuses[cid], sim.statuses[cid])),
             ('예약 구간', f'{tm(c.booking_start)}–{tm(c.booking_end)}'), ('ETA 구간' if sim.statuses[cid] == 'EN_ROUTE' else '게이트 도착(ATA)', eta),
             ('선적 우선순위', f'#{p.sequence} / {len(o.plan)} · {top}' if p else '미정'), ('위치', where)]
    html('<div class="case-bar"><div class="case-tag">대표 컨테이너</div>' +
         ''.join(f'<div><span>{k}</span><b>{escape(str(v))}</b></div>' for k, v in cells) + '</div>')


def checklist(sim, story):
    state = progress_state(story, sim)
    out = []
    for i, name in enumerate(STEPS, 1):
        v = state[name]
        if name == '승인 또는 보류' and v == 'hold':
            cls, mark, label = 'hold', '⏸', '보류(실행 안 함)'
        elif v:
            cls, mark, label = 'done', '✓', '승인' if v == 'approve' else '완료'
        else:
            cls, mark, label = '', str(i), '대기'
        out.append(f'<div class="check {cls}"><span>{mark}</span><div>{name}<small>{label}</small></div></div>')
    html('<div class="checklist">' + '<i>→</i>'.join(out) + '</div>')


def suggested_stage(sim, story):
    cid = story['focus']; d = story.get('decision'); p = story['progress']
    if story.get('compare'):
        return 5
    if d:
        return 4 if d['type'] == 'approve' else 3
    if sim.statuses[cid] == 'YARD_QUEUE':
        return 2 if p.get('compared') else (1 if not p.get('problem_seen') else 2)
    return 0


def go_stage(i):
    """단계 위젯 값은 다음 실행 시작 때 바꿉니다(위젯 생성 뒤에는 바꿀 수 없음)."""
    st.session_state._goto_stage = i
    st.rerun()


def advance_until(sim, cond, limit=None):
    end = sim.config.horizon + sim.config.cleanup if limit is None else limit
    while not cond() and sim.queue and sim.queue[0][0] <= end:
        sim.advance(one_event=True)


def story_page(sim, story, goto):
    cid = story['focus']
    o = sim.observe()
    if st.session_state.get('focus') != cid:
        html(f'<div class="section-note">지금 다른 화면에서 고른 컨테이너는 <b>{escape(st.session_state.get("focus") or "")}</b>입니다. '
             f'이 흐름은 대표 컨테이너 <b>{cid}</b>를 따라갑니다.</div>')
        if st.button('대표 컨테이너로 돌아가기'):
            st.session_state.focus = cid; st.rerun()
    summary_bar(sim, story, cid)
    checklist(sim, story)
    if '_goto_stage' in st.session_state:
        st.session_state.story_stage = STAGES[st.session_state.pop('_goto_stage')]
    if 'story_stage' not in st.session_state:
        st.session_state.story_stage = STAGES[suggested_stage(sim, story)]
    stage = st.segmented_control('진행 단계', STAGES, key='story_stage', label_visibility='collapsed')
    if stage is None:
        stage = STAGES[suggested_stage(sim, story)]
    idx = STAGES.index(stage)
    rec_info = None
    if idx in (2, 3) and sim.statuses[cid] == 'YARD_QUEUE' and not story.get('decision'):
        rec_info = build_options(o, cid, story['planned'])
    left, right = st.columns([1.55, 1], gap='medium')
    with left:
        with st.container(key='canvas'):
            render_canvas(sim, story, idx, rec_info)
            legend3d()
    with right:
        with st.container(key='focus'):
            [stage_situation, stage_problem, stage_options, stage_decide, stage_execute, stage_result][idx](sim, story, rec_info, goto)
    history(sim, story)


# ── 3D 영역 ───────────────────────────────────────────
def render_canvas(sim, story, idx, rec_info):
    cid = story['focus']; o = sim.observe(); d = story.get('decision')
    planned_mark = None
    if story['planned'] and not locate(o.yard, cid):
        planned_mark = (story['planned'], len(o.yard[story['planned']]) + 1) if len(o.yard[story['planned']]) < 4 else None
    focus_only = st.toggle('선택 화물 보기(나머지는 흐리게)', key='focus_only')
    if idx == 4 and d and d['type'] == 'approve':
        panel('승인한 작업 재생', 'REPLAY · 실행 로그', '승인 전 → 이동 중 → 완료. 다시 재생해도 작업·이동 횟수는 늘지 않습니다.')
        steps, final = replay_steps(sim.bundle, sim.moves, d['at'], sim.now, cid)
        chart(replay_figure(sim.bundle, sim.plan, steps, final, cid, trucks_at(sim)), 'yard3d_replay_ops')
        return
    if idx == 5 and story.get('compare'):
        cmp = story['compare']
        tabs = st.tabs(['선택한 대안 재생', '기존 계획 유지 재생'])
        for tab, key in zip(tabs, ('chosen', 'keep')):
            with tab:
                b = cmp.get(key)
                if not b:
                    st.info('비교할 갈래가 없습니다.'); continue
                s = b['sim']
                end = b['focus_retrieved_at'] or s.now
                steps, final = replay_steps(s.bundle, s.moves, d['at'], end, cid)
                chart(replay_figure(s.bundle, s.plan, steps, final, cid, trucks_at(s),
                                    title_prefix='선택 대안 · ' if key == 'chosen' else '기존 계획 · '), 'yard3d_cmp_' + key)
                st.caption(f'결정 시각 {tm(d["at"])}부터 대표 컨테이너 인출 완료 {tm(end)}까지의 실행 로그입니다. '
                           '다른 화물의 반입·인출도 함께 보여줍니다.')
        return
    target = None
    title = f'야드 현재 상태 · {tm(o.now)}'
    if rec_info and idx in (2, 3):
        rec, keep_i, best_i, _ = rec_info
        if rec.candidates:
            pick = st.session_state.get('story_choice' if idx == 3 else 'story_option', st.session_state.get('story_option', best_i if best_i is not None else 0))
            pick = min(pick, len(rec.candidates) - 1)
            c = rec.candidates[pick]; target = (c.stack, c.tier)
            title = f'대안 미리보기 · {cid} → {slot(c.stack, c.tier)}'
    panel('3D 야드', 'YARD / 3D', title)
    extra = [cid] if sim.statuses[cid] == 'EN_ROUTE' else []
    arrow = None
    if d and d['type'] == 'approve' and sim.statuses[cid] in ('YARD_QUEUE', 'IN_MOVE'):
        target = (d['stack'], d['tier'])
    chart(yard_figure(o, cid, target, 440, focus_only, planned_mark, arrow, extra), 'yard3d_story')
    if sim.statuses[cid] == 'EN_ROUTE':
        st.caption('대표 컨테이너는 아직 운송 중이라 야드에 그리지 않고 반입 대기 영역에 미리 표시했습니다. 주황 테두리는 기존 계획 위치입니다.')


def trucks_at(sim):
    def fn(t):
        return [c for c, x in sim.trucks.items() if x['gate_arrival'] <= t and not x['exception'] and
                (x['unload_start'] is None or x['unload_start'] >= t)]
    return fn


# ── 단계별 오른쪽 패널 ─────────────────────────────────
def stage_situation(sim, story, rec_info, goto):
    cid = story['focus']; o = sim.observe(); c = o.containers[cid]
    other = story['other']
    times = gate_and_yard_times(sim, cid)
    log = sim.forecast_log.get(cid, [])
    panel('① 상황 확인', 'WHY NOW', '예약·ETA·선적계획·야드 상태를 함께 봅니다.')
    if times['observed']:
        gate = f'게이트 도착 {tm(times["gate"])} (관측)'
        yard = f'CY 하차 가능 {tm(times["yard"])} (관측)' if times['yard'] else 'CY 이동 중'
    elif times['gate']:
        g = times['gate']; y = times['yard']
        gate = f'게이트 도착 예상 {tm(g[0])}–{tm(g[2])}'
        yard = f'CY 하차 가능 예상 {tm(y[0])}–{tm(y[2])} (게이트 처리·내부 이동 {times["lag"] // 60}분 뒤)'
    else:
        gate = yard = '정보 없음'
    rows = [['예약 구간', f'{tm(c.booking_start)}–{tm(c.booking_end)}'], ['도착', gate], ['하차', yard],
            ['선적 순서', f'#{o.plan[cid].sequence} (먼저 실을수록 앞 번호)'], ['기존 계획 위치', f'{story["planned"]} · {tm(story["planned_at"])}에 예약시각 기준으로 정함']]
    table(['항목', '내용'], rows)
    if log:
        hist = ' → '.join(f'{tm(f.observed_at)} 발행 {tm(f.p50)}' for f in log[-3:])
        html(f'<div class="section-note"><b>ETA 변화</b> · {hist}</div>')
    late = None
    f = o.forecasts.get(cid)
    if f and sim.statuses[cid] == 'EN_ROUTE':
        late = round((f.p50 - c.booking_end) / 60)
    fo = o.forecasts.get(other)
    why = []
    if late and late > 0:
        why.append(f'{cid}의 도착 예상이 예약 구간보다 약 {late}분 늦어졌습니다.')
    if fo and sim.statuses.get(other) == 'EN_ROUTE' and f and fo.p50 < f.p50:
        why.append(f'그 사이 먼저 인출할 {other}(#{o.plan[other].sequence})가 {tm(fo.p50)}쯤 먼저 도착할 예정입니다. '
                   f'기존 계획 위치 {story["planned"]}에 그 화물이 먼저 쌓이면, 늦게 온 {cid}가 그 위에 놓여 인출을 가로막을 수 있습니다.')
    elif locate(o.yard, other) and locate(o.yard, other)[0] == story['planned']:
        why.append(f'먼저 인출할 {other}가 이미 기존 계획 위치 {story["planned"]}에 들어와 있습니다.')
    if not why:
        why.append('현재 입력에서는 기존 계획을 바꿀 뚜렷한 이유가 없습니다. 도착 후 다시 확인합니다.')
    html('<div class="why"><b>왜 지금 배치를 검토하나요?</b><br>' + '<br>'.join(escape(x) for x in why) + '</div>')
    p = story['progress']
    if st.button('도착 정보 확인 완료', type='primary', width='stretch', disabled=bool(p.get('arrival_checked')), key='chk_arrival'):
        p['arrival_checked'] = tm(sim.now); st.rerun()
    if sim.statuses[cid] not in ('YARD_QUEUE', 'STORED', 'IN_MOVE', 'RETRIEVED'):
        if st.button(f'{cid}의 CY 도착까지 진행', width='stretch', key='to_arrival',
                     help='시뮬레이션 시각을 진행합니다. 다른 화물은 같은 규칙으로 자동 처리됩니다.'):
            advance_until(sim, lambda: sim.statuses[cid] in ('YARD_QUEUE', 'EXCEPTION_LATE'))
            go_stage(1)
        st.caption('진행하면 그사이 도착한 다른 화물은 같은 규칙(기준 정책)으로 자동 적치됩니다.')
    else:
        st.caption(f'{cid}는 {STATUS[sim.statuses[cid]]} 상태입니다. ② 문제 확인으로 넘어가세요.')


def stage_problem(sim, story, rec_info, goto):
    cid = story['focus']; o = sim.observe(); other = story['other']
    panel('② 문제 확인', 'WHAT COULD GO WRONG', '빨강은 지금 다른 화물의 인출을 가로막고 있는 화물입니다.')
    story['progress']['problem_seen'] = True
    pairs = blocking_pairs(o)
    if sim.statuses[cid] == 'EN_ROUTE':
        f = o.forecasts.get(cid); fo = o.forecasts.get(other)
        html('<div class="why">대표 컨테이너가 아직 도착 전입니다. 예측 기준으로 '
             + (f'{other}가 {tm(fo.p50)}쯤 먼저 도착해 기존 계획 위치에 쌓일 수 있습니다.' if fo and f and fo.p50 < f.p50 else '눈에 띄는 충돌은 없습니다.')
             + ' 실제 충돌 여부는 CY 도착 뒤 확인합니다.</div>')
    elif sim.statuses[cid] == 'YARD_QUEUE':
        conflict = planned_conflict(o, cid, story['planned'])
        if conflict:
            names = ', '.join(f'{x}(#{o.plan[x].sequence})' for x in conflict)
            html(f'<div class="why danger"><b>기존 계획대로 놓으면 문제가 생깁니다.</b><br>{story["planned"]}에는 이미 {names}가 있습니다. '
                 f'{cid}(#{o.plan[cid].sequence})를 그 위에 놓으면 먼저 실어야 할 화물을 가로막아, 인출 때 {cid}를 한 번 더 옮겨야 합니다.</div>')
        else:
            html(f'<div class="why"><b>기존 계획 위치에는 문제가 없습니다.</b><br>{story["planned"]}에 {cid}보다 먼저 인출할 화물이 없습니다. '
                 '억지로 위험으로 표시하지 않습니다. 그래도 다른 후보와 비교할 수 있습니다.</div>')
    else:
        html(f'<div class="why">{cid}는 {STATUS[sim.statuses[cid]]} 상태입니다.</div>')
    if pairs:
        rows = [[escape(above), escape(below), f'#{o.plan[below].sequence} 먼저 인출'] for below, above in pairs[:6]]
        table(['가로막는 화물(위·빨강)', '가로막히는 화물(아래)', '이유'], rows)
        st.caption(f'야드 전체에서 지금 방해 관계는 {len(pairs)}건입니다. 대부분은 시연 시작 전부터 있던 적치입니다.')
    else:
        st.caption('지금 야드에는 인출 순서를 거스르는 방해 관계가 없습니다.')


def option_rows(o, rec, keep_i, best_i, n):
    out = []
    for i, c in enumerate(rec.candidates):
        tag = '기존 계획 유지' if i == keep_i else f'시스템 대안 {i if keep_i == 0 else i + 1}'
        earlier = sum(rank(o.plan, x) < rank(o.plan, rec.container_id) for x in o.yard[c.stack])
        reason = (f'아래에 먼저 인출할 화물 {earlier}개 위에 놓여 그 화물을 가로막습니다.' if earlier
                  else '아래 화물보다 먼저 인출하므로 가로막는 관계가 생기지 않습니다.')
        if not o.yard[c.stack]:
            reason += ' 빈 스택입니다.'
        out.append({'i': i, 'tag': tag, 'slot': slot(c.stack, c.tier), 'what': f'{rec.container_id} 트럭 → {slot(c.stack, c.tier)} (최초 적치)',
                    'reason': reason, 'rehandle': c.rehandles, 'pm': c.premarshals, 'extra': c.rehandles + c.premarshals,
                    'wait': c.wait_seconds, 'delay': c.delay_seconds, 'best': i == best_i, 'score': c.score})
    return out


def stage_options(sim, story, rec_info, goto):
    cid = story['focus']; o = sim.observe()
    panel('③ 대안 비교', 'OPTIONS', '새로 도착한 화물의 최초 적치 대안입니다. 첫 줄은 항상 기존 계획 유지입니다.')
    if story.get('decision'):
        html('<div class="why">이미 판단을 기록했습니다. ④·⑤ 단계에서 이어서 확인하세요.</div>'); return
    if sim.statuses[cid] != 'YARD_QUEUE' or not rec_info:
        html('<div class="why">대표 컨테이너가 CY에 도착해야 실제 대안을 계산할 수 있습니다. ① 단계에서 도착까지 진행하세요.</div>'); return
    rec, keep_i, best_i, n = rec_info
    if not rec.candidates:
        html('<div class="why danger">공간·하중·화물 제약을 만족하는 위치가 없습니다.</div>'); return
    rows = option_rows(o, rec, keep_i, best_i, n)
    pick = st.radio('3D로 볼 대안', [r['i'] for r in rows], horizontal=True, key='story_option',
                    index=[r['i'] for r in rows].index(best_i) if best_i is not None else 0,
                    format_func=lambda i: ('기존 계획' if i == keep_i else '대안 ' + str(i if keep_i == 0 else i + 1)) + (' ★' if i == best_i else ''))
    for r in rows:
        html(f'<div class="opt {"best" if r["best"] else ""} {"sel" if r["i"] == pick else ""}"><div class="opt-head"><b>{r["tag"]}</b>'
             f'{badge("추천", "") if r["best"] else ""}<span>{r["slot"]}</span></div>'
             f'<div class="opt-what">{escape(r["what"])}</div><div class="opt-why">{escape(r["reason"])}</div>'
             f'<div class="opt-nums"><span>예상 재취급 <b>{r["rehandle"]:.1f}</b></span><span>선작업 <b>{r["pm"]:.0f}</b></span>'
             f'<span>총 추가 이동 <b>{r["extra"]:.1f}</b></span><span>트럭 대기 <b>{r["wait"] / 60:.1f}분</b></span>'
             f'<span>인출 지연 합 <b>{r["delay"] / 60:.0f}분</b></span></div></div>')
    keep = rows[keep_i] if keep_i is not None else None
    best = rows[best_i]
    if keep and best_i != keep_i:
        d = keep['extra'] - best['extra']
        html(f'<div class="why"><b>추천 근거</b> · {escape(best["reason"])} 기존 계획 유지보다 예상 총 추가 이동이 '
             f'{d:.1f}회 {"적고" if d > 0 else "같거나 많지만"}, 인출 지연 합이 {(keep["delay"] - best["delay"]) / 60:+.0f}분 차이 납니다.</div>')
    elif keep:
        html('<div class="why">기존 계획 유지가 가장 낫다는 계산입니다. 바꿀 이유가 없으면 그대로 두는 것을 추천합니다.</div>')
    st.caption(SCOPE.format(n=n) + '. 대표 컨테이너 한 개의 이동 횟수가 아니라, 이 결정을 했을 때 야드 전체에서 생길 것으로 계산한 값입니다. '
               '총 추가 이동 = 재취급 + 선작업이며 최초 적치·정상 인출은 셈하지 않습니다.')
    pm = propose_premarshal(o)
    if pm is None:
        st.caption('선작업: 지금은 추천하지 않습니다(하차 대기 화물이 있거나, 옮겨도 이동 비용보다 개선이 작습니다).')
    else:
        st.caption(f'선작업 후보: {pm.container_id} → {slot(pm.candidates[0].stack, pm.candidates[0].tier)} · 유휴시간 선작업 화면에서 따로 검토합니다.')
    if st.button('대안 비교 완료 → 승인 단계로', type='primary', width='stretch', disabled=bool(story['progress'].get('compared'))):
        story['progress']['compared'] = tm(sim.now); go_stage(3)


def stage_decide(sim, story, rec_info, goto):
    cid = story['focus']; o = sim.observe(); d = story.get('decision')
    panel('④ 승인 또는 보류', 'HUMAN DECISION', '최종 결정은 담당자가 합니다. 시스템은 선택을 채점하지 않습니다.')
    if d:
        word = '승인' if d['type'] == 'approve' else '보류'
        html(f'<div class="why"><b>{tm(d["at"])} {word}</b> · {escape(d.get("label", ""))}<br>사유: {escape(d.get("reason") or "입력 안 함")}</div>')
        if d['type'] == 'hold':
            st.caption('보류는 실행 완료로 처리하지 않습니다. 대표 컨테이너는 하차 대기 상태로 남습니다.')
            if st.button('보류 해제 후 다시 검토', width='stretch'):
                story['decision'] = None; story['progress'].pop('compared', None)
                go_stage(2)
        else:
            if st.button('⑤ 작업 실행 보기', type='primary', width='stretch'):
                go_stage(4)
        return
    if sim.statuses[cid] != 'YARD_QUEUE' or not rec_info or not rec_info[0].candidates:
        html('<div class="why">대표 컨테이너가 CY에 도착하고 대안이 계산된 뒤 승인할 수 있습니다.</div>'); return
    rec, keep_i, best_i, n = rec_info
    labels = {i: ('기존 계획 유지' if i == keep_i else f'대안 {i if keep_i == 0 else i + 1}') + f' · {slot(c.stack, c.tier)}'
              for i, c in enumerate(rec.candidates)}
    default = st.session_state.get('story_option', best_i)
    choice = st.radio('승인할 안', list(labels), format_func=labels.get, index=list(labels).index(default) if default in labels else 0,
                      key='story_choice')
    c = rec.candidates[choice]
    report = sim.validate_action(rec, c)
    job = sim.cranes[o.containers[cid].block]
    checks = [('최신 위치', f'{STATUS[sim.statuses[cid]]} · 트럭 위', sim.statuses[cid] == 'YARD_QUEUE'),
              ('작업 상태', f'YC-{o.containers[cid].block} ' + ('작업 중' if job else '대기'), job is None),
              ('계획 버전', f'추천 {rec.plan_version} / 현재 {sim.plan_version}', rec.plan_version == sim.plan_version),
              ('추천 유효성', f'야드 버전 Y{rec.yard_version} / 현재 Y{sim.yard_version} · {tm(rec.valid_until)}까지',
               rec.yard_version == sim.yard_version and sim.now <= rec.valid_until)]
    table(['승인 직전 확인', '내용', ''], [[k, escape(v), '✓' if ok else '✗'] for k, v, ok in checks])
    errors = [e for e in report.errors if not e.startswith('CARGO_REVIEW')]
    if errors:
        st.warning(' · '.join(errors))
    reason = st.selectbox('판단 사유(선택)', REASONS, key='story_reason')
    a, b = st.columns(2)
    if a.button('모의 승인', type='primary', width='stretch', disabled=bool(errors), key='story_approve'):
        pre = deepcopy(sim)
        sim.cargo_checks.add(cid)
        rep = sim.approve(rec, choice)
        if rep.valid:
            story['decision'] = {'type': 'approve', 'at': sim.now, 'rec': rec, 'rec_id': rec.recommendation_id, 'index': choice,
                                 'keep_index': keep_i, 'best_index': best_i, 'pre': pre, 'stack': c.stack, 'tier': c.tier,
                                 'slot': slot(c.stack, c.tier), 'label': labels[choice], 'reason': '' if reason == REASONS[0] else reason}
            log_decision(sim, cid, '승인', labels[choice], story['decision']['reason'], rec.recommendation_id)
            st.session_state.guides[cid] = {'id': rec.recommendation_id, 'container': cid, 'slot': slot(c.stack, c.tier),
                                            'block': o.containers[cid].block, 'at': tm(sim.now), 'plan': rec.plan_version,
                                            'ack': False, 'reason': story['decision']['reason']}
            go_stage(4)
        else:
            st.error(' · '.join(rep.errors))
    if b.button('보류', width='stretch', key='story_hold'):
        story['decision'] = {'type': 'hold', 'at': sim.now, 'label': '판단 보류 · 실행하지 않음',
                             'reason': '' if reason == REASONS[0] else reason}
        log_decision(sim, cid, '보류', '—', story['decision']['reason'], rec.recommendation_id)
        st.rerun()
    st.caption('승인 버튼을 여러 번 눌러도 같은 추천은 한 번만 실행됩니다. 실제 TOS 지시나 기사 알림은 보내지 않습니다.')


def log_decision(sim, cid, word, where, reason, rid):
    st.session_state.review_log.append({'시각': tm(sim.now), '컨테이너': cid, '결정': word, '위치': where,
                                        '사유': reason or '—', '추천ID': rid})


def stage_execute(sim, story, rec_info, goto):
    cid = story['focus']; d = story.get('decision')
    panel('⑤ 작업 실행', 'SIMULATED WORK', '승인한 작업을 모의 장비가 실행하고, 같은 사례를 인출까지 이어갑니다.')
    if not d:
        html('<div class="why">아직 판단하지 않았습니다. ④ 단계에서 승인하거나 보류하세요.</div>'); return
    if d['type'] == 'hold':
        html('<div class="why">보류했기 때문에 실행할 작업이 없습니다.</div>'); return
    acc = sim.accepted.get(d['rec_id'], {}).get('status', '—')
    word = {'EXECUTING': '이동 중', 'COMPLETED': '완료', 'QUEUED': '대기', 'APPROVED': '승인'}.get(acc, acc)
    table(['항목', '내용'], [['승인한 작업', f'{cid} 트럭 → {d["slot"]} (최초 적치)'], ['작업 상태', word],
                           ['현재 위치', slot(*locate(sim.yard, cid)) if locate(sim.yard, cid) else STATUS[sim.statuses[cid]]],
                           ['시뮬레이션 시각', tm(sim.now)]])
    if st.button('작업 완료까지 진행', type='primary', width='stretch', disabled=acc == 'COMPLETED'):
        advance_until(sim, lambda: sim.accepted.get(d['rec_id'], {}).get('status') == 'COMPLETED'); st.rerun()
    if st.button(f'{cid} 본선 인출까지 진행', width='stretch', disabled=sim.statuses[cid] == 'RETRIEVED' or acc != 'COMPLETED',
                 help='시뮬레이션 시각을 진행합니다. 다른 화물의 반입·인출과 재취급도 같은 규칙으로 함께 실행됩니다.'):
        advance_until(sim, lambda: sim.statuses[cid] == 'RETRIEVED'); st.rerun()
    steps, _ = replay_steps(sim.bundle, sim.moves, d['at'], sim.now, cid)
    if steps:
        table(['시각', '작업', '이유'], [[tm(s['move']['start_at']), s['label'], escape(s['reason'])] for s in steps[-8:]])
    if sim.statuses[cid] == 'RETRIEVED':
        st.caption('대표 컨테이너의 반입·적치·인출까지 끝났습니다. ⑥ 결과 확인에서 같은 사건의 기존 계획 유지와 비교하세요.')


def stage_result(sim, story, rec_info, goto):
    cid = story['focus']; d = story.get('decision')
    panel('⑥ 결과 확인', 'SAME EVENT · TWO BRANCHES', '결정 직전 상태를 복제해 두 갈래를 끝까지 돌린 실행 로그 값입니다.')
    if not d or d['type'] != 'approve':
        html('<div class="why">승인한 작업이 있어야 결과를 비교할 수 있습니다.</div>'); return
    keep_i = d['keep_index']; chosen_i = d['index']
    other_i = chosen_i
    note = ''
    if keep_i is not None and chosen_i == keep_i:
        other_i = d['best_index']; note = '기존 계획 유지를 승인했으므로, 시스템 추천안과 비교합니다.'
    if story.get('compare') is None:
        if st.button('같은 사건으로 결과 비교 실행', type='primary', width='stretch'):
            with st.spinner('같은 초기 상태에서 두 갈래를 끝까지 계산하고 있습니다…'):
                story['compare'] = compare_branches(d['pre'], d['rec'], keep_i, other_i, cid, story['other'])
                story['progress']['result_checked'] = tm(sim.now)
            st.rerun()
        st.caption('두 갈래 모두 대표 컨테이너 외 화물은 같은 규칙으로 처리하고, 실제 도착 사건·화물·장비 조건은 같습니다. '
                   '다른 시나리오의 자동 실험 결과를 가져오지 않습니다.')
        return
    cmp = story['compare']; k = cmp.get('keep'); c = cmp.get('chosen')
    if note:
        st.caption(note)
    if not k or not c:
        html('<div class="why">기존 계획 위치가 이미 제약을 벗어나 비교할 수 없습니다.</div>'); return
    km, cm = k['result'].metrics, c['result'].metrics

    def row(label, a, b, fmt='{:.0f}', lower=True):
        if a is None or b is None:
            return [label, '—', '—', '—']
        diff = b - a
        txt = '같음' if abs(diff) < 1e-9 else (('감소 ' if diff < 0 else '증가 ') + fmt.format(abs(diff)))
        good = (diff < 0) == lower
        cls = '' if abs(diff) < 1e-9 else ('good' if good else 'bad')
        return [label, fmt.format(a), fmt.format(b), f'<span class="{cls}">{txt}</span>']
    rows = [['대표 컨테이너 적치 위치', k['initial_slot'], c['initial_slot'], ''],
            row('대표 컨테이너가 다시 옮겨진 횟수', k['focus_rehandled'], c['focus_rehandled']),
            row('대표 컨테이너 인출 지연(분)', (k['focus_delay'] or 0) / 60, (c['focus_delay'] or 0) / 60, '{:.1f}'),
            row('야드 전체 재취급(회)', km['REHANDLE'], cm['REHANDLE']),
            row('야드 전체 선작업(회)', km['PREMARSH'], cm['PREMARSH']),
            row('야드 전체 총 추가 이동(회)', km['extra_moves'], cm['extra_moves']),
            row('평균 트럭 대기(분)', km['truck_wait']['mean'] and km['truck_wait']['mean'] / 60, cm['truck_wait']['mean'] and cm['truck_wait']['mean'] / 60, '{:.1f}'),
            row('평균 인출 지연(분)', km['retrieval_delay']['mean'] and km['retrieval_delay']['mean'] / 60, cm['retrieval_delay']['mean'] and cm['retrieval_delay']['mean'] / 60, '{:.1f}'),
            row('미완료·마감 예외(개)', km['incomplete'] + km['exceptions'], cm['incomplete'] + cm['exceptions']),
            ['최초 적치 · 정상 인출(별도)', f'{km["INITIAL"]} · {km["RETRIEVE"]}', f'{cm["INITIAL"]} · {cm["RETRIEVE"]}', '별도 집계']]
    table(['같은 사건 · 실행 후 관측값', '기존 계획 유지', '선택한 대안', '차이'], rows)
    msg = []
    de = cm['extra_moves'] - km['extra_moves']
    dw = (cm['truck_wait']['mean'] or 0) - (km['truck_wait']['mean'] or 0)
    if de < 0:
        msg.append(f'선택한 대안은 야드 전체 추가 이동이 {abs(de)}회 적었습니다.')
    elif de > 0:
        msg.append(f'선택한 대안은 야드 전체 추가 이동이 {de}회 많았습니다.')
    else:
        msg.append('야드 전체 추가 이동은 같았습니다.')
    if abs(dw) >= 6:
        msg.append(f'평균 트럭 대기는 {dw / 60:+.1f}분 달라졌습니다.')
    if k['focus_rehandled'] > c['focus_rehandled']:
        msg.append(f'기존 계획을 유지하면 대표 컨테이너가 먼저 실을 화물을 가로막아 {k["focus_rehandled"]}번 다시 옮겨졌습니다.')
    html('<div class="why"><b>해석</b> · ' + ' '.join(escape(m) for m in msg) +
         '<br><span class="muted">예상값(③의 평균)과 다를 수 있는 실행 후 관측값입니다. 합성 데이터 기반 시연입니다.</span></div>')
    st.caption('왼쪽 3D 탭에서 두 갈래의 이동을 결정 시각부터 대표 컨테이너 인출까지 재생할 수 있습니다.')


def history(sim, story):
    with st.container(key='arrivals'):
        panel('누적 작업 이력', 'CASE LOG', '대표 컨테이너와 관련된 판단·이동만 모았습니다. 판단은 중립 기록으로만 남깁니다.')
        cid = story['focus']
        rows = [[r['시각'], r['결정'], escape(r['컨테이너']), escape(r['위치']), escape(r['사유'])]
                for r in st.session_state.review_log if r['컨테이너'] == cid]
        for m in sim.moves:
            if m['completed'] and (m['container_id'] == cid or m.get('for_container') == cid):
                from services.story import move_reason, MOVE_WORDS
                rows.append([tm(m['end_at']), MOVE_WORDS[m['move_type']], escape(m['container_id']), escape(m['target_slot'] or '본선'), escape(move_reason(m, cid))])
        if story['progress'].get('arrival_checked'):
            rows.append([story['progress']['arrival_checked'], '도착 정보 확인', escape(cid), '—', '담당자가 ETA 변화를 확인'])
        rows.sort(key=lambda r: r[0])
        if rows:
            table(['시각', '구분', '컨테이너', '위치', '내용'], rows)
        else:
            st.caption('아직 기록이 없습니다.')
