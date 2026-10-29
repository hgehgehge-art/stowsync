"""대표 시나리오 화면에서 함께 쓰는 표시 요소(요약 띠, 출처 카드, 도착 현황, 역할별 안내)."""
from copy import deepcopy
from html import escape
import time
import streamlit as st
from domain.models import slot
from engine.yard import locate, rank
from services.recommend import propose_premarshal
from services.story import (STEPS, gate_and_yard_times, planned_conflict, blocking_pairs, build_options,
                            compare_branches, compare_orders, order_done, replay_steps, progress_state, review_queue, apply_plan_change)
from ui import sequence_view as sv
import plotly.graph_objects as go
from ui.theme import html, badge, panel, table, tm, mins
from ui.scene import yard_figure, replay_figure, LEGEND

STATUS = {'EN_ROUTE': '운송 중', 'GATE_QUEUE': '게이트 대기', 'GATE_SERVICE': '게이트 처리', 'INTERNAL_TRAVEL': 'CY 이동 중',
          'YARD_QUEUE': '하차 대기', 'BLOCKED_CAPACITY': '공간 부족', 'STORED': '적치 완료', 'IN_MOVE': '작업 중',
          'RETRIEVED': '인출 완료', 'EXCEPTION_LATE': '마감 예외', 'WAIT_GATE_OPEN': '반입 대기'}
REASONS = ['선택 안 함', '추천 근거와 현장 조건 일치', '장비 작업 순서 고려', '현장 혼잡', '시스템이 모르는 현장 제약', '기타']


SOURCES = {'allcone': ('올컨e', '반입 예약·운송 진행', '#FF8A3D'),
           'tos': ('TOS', '야드·선박·선적 작업계획', '#A78BFA'), 'stowsync': ('StowSync', '연결해서 계산한 판단', '#59E0CE')}


def source_card(key, rows, note=''):
    name, sub, color = SOURCES[key]
    body = ''.join(f'<div class="src-row"><span>{escape(k)}</span><b>{escape(str(v))}</b></div>' for k, v in rows)
    html(f'<div class="src-card{" allcone-card" if key == "allcone" else ""}" style="--src:{color}"><div class="src-head"><b>{name}{" 앱" if key == "allcone" else ""}</b><span>{sub}</span>'
         f'</div>{body}' + (f'<div class="src-note">{escape(note)}</div>' if note else '') + '</div>')


def src_tag(key):
    name, _, color = SOURCES[key]
    return f'<i class="src-tag" style="--src:{color}">{name}</i>'


def cargo_text(c):
    if c.cargo_type == '위험물':
        return f'⚠ 위험물 {c.hazard_class}'
    if c.cargo_type == '환적':
        return f'환적 · {c.connecting_vessel}'
    return '일반 드라이'


def legend3d():
    items = ''.join(f'<span><i style="background:{c};{"opacity:.55" if "반투명" in t else ""}"></i>{t}</span>' for t, c in LEGEND)
    html(f'<div class="legend3d">{items}<span><i style="background:transparent;border:2px solid #FFB547"></i>기존 계획 위치(노랑 테두리)</span>'
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
    tags = {'예약 구간': 'allcone', 'ETA 구간': 'allcone', '게이트 도착(ATA)': 'allcone', '선적 우선순위': 'tos', '위치': 'tos', '현재 상태': 'tos'}
    html('<div class="case-bar"><div class="case-tag">대표 컨테이너</div>' +
         ''.join(f'<div><span>{k} {src_tag(tags[k]) if k in tags else ""}</span><b>{escape(str(v))}</b></div>' for k, v in cells) + '</div>')


def advance_until(sim, cond, limit=None):
    end = sim.config.horizon + sim.config.cleanup if limit is None else limit
    while not cond() and sim.queue and sim.queue[0][0] <= end:
        sim.advance(one_event=True)


# ── 3D 영역 ───────────────────────────────────────────


def trucks_at(sim):
    def fn(t):
        return [c for c, x in sim.trucks.items() if x['gate_arrival'] <= t and not x['exception'] and
                (x['unload_start'] is None or x['unload_start'] >= t)]
    return fn


# ── 단계별 오른쪽 패널 ─────────────────────────────────


def log_decision(story, sim, cid, word, where, reason, rid):
    story.setdefault('log', []).append({'시각': tm(sim.now), '컨테이너': cid, '결정': word, '위치': where,
                                        '사유': reason or '—', '추천ID': rid})


# ── ⓪ 관제 ─────────────────────────────────────────────
def render_overview(sim, story):
    panel('20개 화물 도착 현황', 'ARRIVAL BOARD', '회색 막대 = 반입 예약 구간 · 점 = 최신 ETA(운송 중) 또는 실제 도착 · 노랑 = 대표 컨테이너')
    rows = review_queue(sim)
    o = sim.observe()
    fig = go.Figure()
    order = sorted(rows, key=lambda r: r['booking'][0])
    for r in order:
        y = f'…{r["cid"][-4:]} · #{r["seq"]}'
        hl = r['cid'] == story['focus']
        fig.add_trace(go.Scatter(x=[r['booking'][0] / 60, r['booking'][1] / 60], y=[y, y], mode='lines',
                                 line=dict(color='#FFD12E' if hl else '#3d536e', width=12), showlegend=False,
                                 hovertemplate=f'{r["cid"]} 예약 {tm(r["booking"][0])}–{tm(r["booking"][1])}<extra></extra>'))
        if r['ref'] is not None:
            late = (r['dev'] or 0) > 0
            fig.add_trace(go.Scatter(x=[r['ref'] / 60], y=[y], mode='markers', showlegend=False,
                                     marker=dict(size=13 if hl else 10, symbol='circle' if r['kind'] == 'ETA' else 'diamond',
                                                 color='#E0474C' if late else '#64d8c5', line=dict(color='#05080D', width=1.5)),
                                     hovertemplate=f'{r["cid"]} {r["kind"]} {tm(r["ref"])}<extra></extra>'))
    fig.add_vline(x=sim.now / 60, line_dash='dot', line_color='#e6b877', annotation_text=f'현재 {tm(sim.now)}', annotation_font_color='#e6b877')
    ticks = list(range(0, 181, 15))
    fig.update_xaxes(tickvals=ticks, ticktext=[tm(t * 60) for t in ticks], gridcolor='#25384b', tickfont_size=10)
    fig.update_yaxes(autorange='reversed', gridcolor='#25384b', tickfont=dict(size=11))
    fig.update_layout(height=420, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=96, r=10, t=10, b=30),
                      font=dict(color='#a8bdd0'))
    chart(fig, 'overview_board')
    n_init = sum(c.initial for c in o.containers.values())
    st.caption(f'전체 {len(o.containers)}개 중 {n_init}개는 이미 야드에 있고, {len(o.containers) - n_init}개가 반입 예정입니다. '
               '빨간 점은 예약 구간보다 늦게 올 것으로 예측된 화물입니다.')


# ── ⑤ 역할별 결과 안내 ─────────────────────────────────
def role_notices(sim, story, cid, d):
    g = story['guide']
    left, right = st.columns([1, 1.15])
    with left:
        html(f'<div class="phone mini"><div class="phone-bar">{tm(sim.now)} <span class="phone-brand">올컨e</span></div>'
             f'<div class="phone-title">하차 위치가<br>정해졌어요</div><p>{escape(cid)}</p>'
             f'<div class="phone-slot">{escape(g["lane"].split()[0])}<small>BLOCK</small></div>'
             f'<div class="phone-route">게이트 → 지정 진입로 → {escape(g["lane"])} 인계 지점</div>'
             f'<div class="phone-status">{g["at"]} 발행 · 슬롯 번호는 표시하지 않음</div></div>')
    with right:
        rows = [['야드 플래너', f'{d["slot"]} 승인 · 대안 비교 근거 · 판단 사유'],
                ['관제 담당', f'YC-{d["slot"][:2]} 작업 지시 · 트럭 → {d["slot"]}'],
                ['운송기사(올컨e)', f'{g["lane"]} 하차 지점만'],
                ['선사', '반입·적치 완료 여부만(위치 비공개)']]
        table(['받는 사람', '받는 정보'], [[a, escape(b)] for a, b in rows])
        st.caption('같은 결정을 역할에 필요한 만큼만 나눠 전합니다. 실제 알림은 보내지 않습니다.')


