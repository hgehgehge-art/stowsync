"""3D 야드 장면과 작업 재생.

색 의미(모든 화면 공통)
  파랑  일반 적치 화물
  빨강  현재 인출 순서를 방해하는 화물(위험물 표시가 아닙니다)
  노랑  선택한 대표 컨테이너(+ '선택한 컨테이너' 라벨, 굵은 테두리)
  반투명 초록  추천 목적 위치
  화살표 + 라벨  승인된 이동 경로와 현재 이동 대상
모든 컨테이너는 검정 외곽선을 그립니다. 위험물은 색이 아니라 '⚠ 위험물' 문자로 표시합니다.
"""
import plotly.graph_objects as go
from engine.yard import blockers, rank, locate

BLUE = '#4A7FD4'; RED = '#E0474C'; YELLOW = '#FFD12E'; GREEN = '#3DDC97'; CHASSIS = '#3B4654'; FADE = '#7D8EA3'
DX, DY, DZ, PITCH = 2.02, .9, .52, .57
TRUCK_Y = -2.45
VESSEL_Y = 5.2
UIREV = 'stowsync-yard-v2'
_I = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
_J = [1, 2, 4, 5, 2, 5, 3, 6, 0, 7, 5, 6]
_K = [2, 3, 5, 1, 5, 6, 6, 7, 7, 4, 6, 7]
_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
LEGEND = [('일반 적치 화물', BLUE), ('인출 순서를 방해하는 화물', RED), ('선택한 대표 컨테이너', YELLOW),
          ('추천 목적 위치(반투명)', GREEN), ('트럭 위·반입 대기', CHASSIS)]


def coords(stack):
    block, bay, row = stack.split('-')
    return (int(bay) - 1) * 2.35 + (0 if block == 'A1' else 6.2), (int(row) - 1) * 1.17


def truck_xy(block, i):
    return (0 if block == 'A1' else 6.2) + (i % 2) * 2.35, TRUCK_Y - (i // 2) * 1.25


def _verts(x, y, z, dx=DX, dy=DY, dz=DZ):
    return ([x, x + dx, x + dx, x, x, x + dx, x + dx, x], [y, y, y + dy, y + dy, y, y, y + dy, y + dy],
            [z, z, z, z, z + dz, z + dz, z + dz, z + dz])


class _Layer:
    def __init__(self):
        self.x, self.y, self.z, self.i, self.j, self.k, self.fc, self.text = [], [], [], [], [], [], [], []

    def add(self, x, y, z, color, text, dx=DX, dy=DY, dz=DZ):
        xs, ys, zs = _verts(x, y, z, dx, dy, dz)
        n = len(self.x)
        self.x += xs; self.y += ys; self.z += zs
        self.i += [a + n for a in _I]; self.j += [b + n for b in _J]; self.k += [c + n for c in _K]
        self.fc += [color] * 12
        self.text += [text] * 8

    def trace(self, opacity):
        return go.Mesh3d(x=self.x or [0], y=self.y or [0], z=self.z or [0], i=self.i or [0], j=self.j or [0], k=self.k or [0],
                         facecolor=self.fc or ['rgba(0,0,0,0)'], opacity=opacity if self.x else 0, flatshading=True,
                         text=self.text or [''], hovertemplate='%{text}<extra></extra>',
                         lighting=dict(ambient=.72, diffuse=.75, specular=.12, roughness=.8),
                         lightposition=dict(x=-80, y=-50, z=130), showscale=False, name='')


def _lines(segments, color, width):
    xs, ys, zs = [], [], []
    for (a, b) in segments:
        xs += [a[0], b[0], None]; ys += [a[1], b[1], None]; zs += [a[2], b[2], None]
    return go.Scatter3d(x=xs or [None], y=ys or [None], z=zs or [None], mode='lines', line=dict(color=color, width=width),
                        hoverinfo='skip', showlegend=False)


def _box_edges(x, y, z):
    xs, ys, zs = _verts(x, y, z)
    return [((xs[a], ys[a], zs[a]), (xs[b], ys[b], zs[b])) for a, b in _EDGES]


def scene_traces(containers, plan, yard, statuses=None, focus=None, target=None, trucks=(), moving=None,
                 arrow=None, focus_only=False, planned=None, captions=None):
    """고정된 8개 트레이스: 불투명 상자, 추천 위치, 흐리게 한 상자, 검정 외곽선, 대표 테두리, 라벨, 화살표, 계획 위치 표시.

    yard: stack -> [cid] / trucks: [cid] (트럭 위·반입 대기) / moving: (cid, x, y, z) 이동 중 위치
    target: (stack, tier) 추천 목적 위치 / arrow: [(x,y,z), ...] 승인된 이동 경로 / planned: (stack, tier) 기존 계획 위치
    """
    solid, ghost, fade = _Layer(), _Layer(), _Layer()
    edges, focus_edges = [], []
    lx, ly, lz, lt = [], [], [], []
    risks, _ = blockers(yard, plan)
    statuses = statuses or {}

    def label(cid):
        c = containers[cid]
        p = plan.get(cid)
        extra = ''
        if c.cargo_type == '위험물':
            extra = f'<br>⚠ 위험물 {c.hazard_class}'
        elif c.cargo_type == '환적':
            extra = '<br>환적 화물'
        return f'<b>{cid}</b><br>인출 순서 #{p.sequence if p else "미정"} · {c.weight_t}t{extra}'

    def color(cid):
        if cid == focus:
            return YELLOW
        return RED if cid in risks else BLUE

    for key, items in yard.items():
        x, y = coords(key)
        for t, cid in enumerate(items):
            if moving and cid == moving[0]:
                continue
            z = t * PITCH
            role = '대표 컨테이너' if cid == focus else ('인출 방해' if cid in risks else '일반 적치')
            txt = label(cid) + f'<br>{key}-{t + 1:02d} · {role}'
            if focus_only and cid != focus and (not focus or key != (locate(yard, focus) or ('',))[0]):
                fade.add(x, y, z, FADE, txt)
            else:
                solid.add(x, y, z, color(cid), txt)
            edges += _box_edges(x, y, z)
            if cid == focus:
                focus_edges += _box_edges(x - .03, y - .03, z - .02)
            if containers[cid].cargo_type == '위험물':
                lx.append(x + DX / 2); ly.append(y + DY / 2); lz.append(z + DZ + .12); lt.append('⚠')
    per_block = {}
    for cid in trucks:
        if moving and cid == moving[0]:
            continue
        b = containers[cid].block
        i = per_block.get(b, 0); per_block[b] = i + 1
        x, y = truck_xy(b, i)
        solid.add(x - .05, y - .02, -.16, CHASSIS, f'{cid} 트럭', DX + .1, DY + .04, .14)
        z = 0
        solid.add(x, y, z, color(cid), label(cid) + f'<br>{(captions or {}).get(cid, "트럭 위 · 반입 대기")}')
        edges += _box_edges(x, y, z)
        if cid == focus:
            focus_edges += _box_edges(x - .03, y - .03, z - .02)
    if moving:
        cid, x, y, z = moving
        solid.add(x, y, z, color(cid), label(cid) + '<br>이동 중')
        edges += _box_edges(x, y, z)
        if cid == focus:
            focus_edges += _box_edges(x - .03, y - .03, z - .02)
        lx.append(x + DX / 2); ly.append(y + DY / 2); lz.append(z + DZ + .55)
        lt.append(f'<b>이동 중 · {cid[-4:]}</b>' if cid != focus else '<b>이동 중 · 선택한 컨테이너</b>')
    if target:
        key, tier = target
        x, y = coords(key)
        ghost.add(x, y, (tier - 1) * PITCH, GREEN, f'추천 목적 위치 {key}-{tier:02d}')
        lx.append(x + DX / 2); ly.append(y + DY / 2); lz.append((tier - 1) * PITCH + DZ + .3); lt.append(f'추천 위치 {key}-{tier:02d}')
    plan_marks = []
    if planned:
        key, tier = planned
        x, y = coords(key)
        z = (tier - 1) * PITCH
        plan_marks = _box_edges(x, y, z)
        lx.append(x + DX / 2); ly.append(y + DY / 2); lz.append(z + DZ + .25); lt.append(f'기존 계획 {key}-{tier:02d}')
    # 대표 컨테이너 라벨(마우스를 올리지 않아도 보이게)
    if focus:
        pos = None
        if moving and moving[0] == focus:
            pos = None
        elif locate(yard, focus):
            k, t = locate(yard, focus)
            x, y = coords(k); pos = (x, y, (t - 1) * PITCH)
        elif focus in trucks:
            b = containers[focus].block
            i = [c for c in trucks if containers[c].block == b].index(focus)
            x, y = truck_xy(b, i); pos = (x, y, 0)
        if pos:
            top = max([pos[2]] + [len(v) * PITCH for k, v in yard.items() if coords(k) == (pos[0], pos[1])])
            lx.append(pos[0] + DX / 2); ly.append(pos[1] + DY / 2); lz.append(top + .75)
            lt.append(f'<b>▼ 선택한 컨테이너 {focus}</b>')
    arrow_segments = []
    if arrow and len(arrow) >= 2:
        arrow_segments = list(zip(arrow[:-1], arrow[1:]))
        (ax, ay, az), (bx, by, bz) = arrow[-2], arrow[-1]
        # 화살촉
        arrow_segments += [((bx, by, bz), (bx - .25 * (1 if bx >= ax else -1), by - .25, bz + .25)),
                           ((bx, by, bz), (bx + .25 * (1 if bx >= ax else -1), by - .25, bz + .25))]
    return [solid.trace(1), ghost.trace(.42), fade.trace(.14), _lines(edges, '#05080D', 2.5),
            _lines(focus_edges, YELLOW, 9), go.Scatter3d(x=lx or [None], y=ly or [None], z=lz or [None], mode='text',
                                                          text=lt or [''], textfont=dict(size=12, color='#F4F7FB'),
                                                          hoverinfo='skip', showlegend=False),
            _lines(arrow_segments, '#FFFFFF', 7), _lines(plan_marks, '#FFB547', 4)]


def _static_traces():
    out = [go.Mesh3d(x=[-.8, 11.3, 11.3, -.8], y=[-4.2, -4.2, 5.9, 5.9], z=[-.2] * 4, i=[0, 0], j=[1, 2], k=[2, 3],
                     color='#13283a', opacity=1, hoverinfo='skip', showscale=False)]
    for x in [-.35, 4.65, 5.85, 10.85]:
        out.append(go.Scatter3d(x=[x, x], y=[-.5, 3.5], z=[-.06, -.06], mode='lines', line=dict(color='#3a5a6a', width=3),
                                hoverinfo='skip', showlegend=False))
    for offset in [0, 6.2]:
        x = offset + 3.4
        out.append(go.Scatter3d(x=[x, x, x, x], y=[-.4, -.4, 3.5, 3.5], z=[0, 3, 3, 0], mode='lines',
                                line=dict(color='#6a8598', width=6), hoverinfo='skip', showlegend=False))
    out.append(go.Scatter3d(x=[2.1, 8.3, 2.1, 8.3, 5.2], y=[-.9, -.9, TRUCK_Y - 1.4, TRUCK_Y - 1.4, VESSEL_Y],
                            z=[0, 0, 0, 0, 0], mode='text',
                            text=['BLOCK A1', 'BLOCK B1', '반입 대기(트럭)', '반입 대기(트럭)', '본선 방향 →'],
                            textfont=dict(size=12, color='#c2d7e6'), hoverinfo='skip', showlegend=False))
    return out


def _layout(fig, height):
    fig.update_layout(height=height, paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=36, b=0), showlegend=False,
                      title=dict(text='', font=dict(size=14, color='#eaf3fb'), x=.01, y=.98),
                      scene=dict(bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, range=[-.9, 11.4]),
                                 yaxis=dict(visible=False, range=[-4.3, 6]), zaxis=dict(visible=False, range=[-.25, 3.6]),
                                 aspectmode='manual', aspectratio=dict(x=2.4, y=2.0, z=.75),
                                 camera=dict(eye=dict(x=.92, y=-1.36, z=1.0), center=dict(x=0, y=0, z=-.12), projection=dict(type='orthographic'))),
                      uirevision=UIREV)
    return fig


def arriving(o):
    return [cid for cid, s in o.statuses.items() if s in ('GATE_QUEUE', 'GATE_SERVICE', 'INTERNAL_TRAVEL', 'YARD_QUEUE', 'BLOCKED_CAPACITY')]


def yard_figure(o, selected=None, target=None, height=420, focus_only=False, planned=None, arrow=None, extra_trucks=()):
    """현재 상태 3D. 도착 전 화물은 야드에 그리지 않고, 게이트·CY에 온 화물은 트럭 위에 그립니다."""
    trucks = arriving(o) + [c for c in extra_trucks if c not in arriving(o)]
    captions = {cid: {'GATE_QUEUE': '게이트 대기', 'GATE_SERVICE': '게이트 처리 중', 'INTERNAL_TRAVEL': 'CY로 이동 중',
                      'YARD_QUEUE': '트럭 위 · 하차 대기', 'BLOCKED_CAPACITY': '트럭 위 · 공간 부족'}.get(o.statuses.get(cid), '트럭 위')
                for cid in trucks}
    fig = go.Figure(_static_traces() + scene_traces(o.containers, o.plan, o.yard, o.statuses, selected, target, trucks,
                                                    arrow=arrow, focus_only=focus_only, planned=planned, captions=captions))
    return _layout(fig, height)


def move_path(containers, yard_before, m, trucks_before):
    """이동 시작점·끝점의 좌표(트럭 → 슬롯, 슬롯 → 슬롯, 슬롯 → 본선)."""
    cid = m['container_id']
    if m['source_stack']:
        x0, y0 = coords(m['source_stack'])
        z0 = (len(yard_before[m['source_stack']]) - 1) * PITCH
    else:
        b = containers[cid].block
        idx = [c for c in trucks_before if containers[c].block == b].index(cid) if cid in trucks_before else 0
        x0, y0 = truck_xy(b, idx); z0 = 0
    if m['target_stack']:
        x1, y1 = coords(m['target_stack'])
        z1 = len(yard_before[m['target_stack']]) * PITCH
    else:
        x1, y1, z1 = x0, VESSEL_Y - .4, 0
    return (x0, y0, z0), (x1, y1, z1)


def replay_figure(bundle, plan, steps, final_yard, focus, trucks_at, height=470, title_prefix=''):
    """실행 로그를 따라가는 애니메이션. 단계마다 '이동 전 → 이동 중 → 완료' 3개 장면.

    재생은 로그를 읽기만 하므로 다시 봐도 작업·이동 횟수가 늘지 않습니다.
    """
    from engine.yard import blockers as _b  # noqa: F401
    containers = bundle.containers
    frames, names = [], []
    static = _static_traces()
    k0 = len(static)
    for n, st in enumerate(steps, 1):
        m = st['move']
        yb = st['yard']
        trucks = trucks_at(m['start_at'])
        (x0, y0, z0), (x1, y1, z1) = move_path(containers, yb, m, trucks)
        lift = 3.0
        path = [(x0 + DX / 2, y0 + DY / 2, z0 + DZ), (x0 + DX / 2, y0 + DY / 2, lift), (x1 + DX / 2, y1 + DY / 2, lift),
                (x1 + DX / 2, y1 + DY / 2, z1 + DZ)]
        tgt = (m['target_stack'], len(yb[m['target_stack']]) + 1) if m['target_stack'] else None
        head = f'{n}/{len(steps)} · {st["label"]} · {m["container_id"]} {m["source_slot"] or "트럭"} → {m["target_slot"] or "본선"}'
        ya = {k: list(v) for k, v in yb.items()}
        if m['source_stack']:
            ya[m['source_stack']].remove(m['container_id'])
        if m['target_stack']:
            ya[m['target_stack']].append(m['container_id'])
        after_trucks = [c for c in trucks if c != m['container_id']]
        mid = ((x0 + x1) / 2, (y0 + y1) / 2, lift - DZ)
        for phase, data in (
                ('이동 전', scene_traces(containers, plan, yb, focus=focus, target=tgt, trucks=trucks, arrow=path)),
                ('이동 중', scene_traces(containers, plan, yb, focus=focus, target=tgt, trucks=trucks, arrow=path,
                                       moving=(m['container_id'], *mid))),
                ('완료', scene_traces(containers, plan, ya, focus=focus, trucks=after_trucks))):
            name = f'{n}-{phase}'
            frames.append(go.Frame(name=name, data=data, traces=list(range(k0, k0 + 8)),
                                   layout=dict(title=dict(text=f'{title_prefix}{head} · {phase}'))))
            names.append(name)
    if not frames:
        fig = go.Figure(static + scene_traces(containers, plan, final_yard, focus=focus))
        fig = _layout(fig, height)
        fig.update_layout(title=dict(text=f'{title_prefix}재생할 이동이 없습니다.'))
        return fig
    fig = go.Figure(static + list(frames[0].data), frames=frames)
    fig = _layout(fig, height)
    fig.update_layout(title=dict(text=frames[0].layout.title.text))

    def play(ms, label, from_start=False):
        return dict(label=label, method='animate',
                    args=[names if from_start else None,
                          dict(frame=dict(duration=ms, redraw=True), transition=dict(duration=0), fromcurrent=not from_start,
                               mode='immediate')])
    fig.update_layout(
        updatemenus=[dict(type='buttons', direction='right', x=0, y=-.02, xanchor='left', yanchor='top', showactive=False,
                          bgcolor='#1b2c40', bordercolor='#36506b', font=dict(color='#eaf3fb', size=12),
                          buttons=[play(900, '▶ 재생'),
                                   dict(label='⏸ 일시정지', method='animate',
                                        args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate')]),
                                   play(1800, '0.5×'), play(450, '2×'), play(900, '↺ 다시 보기', True)])],
        sliders=[dict(active=0, x=.36, y=-.02, len=.64, xanchor='left', yanchor='top', pad=dict(t=0, b=0),
                      currentvalue=dict(prefix='장면 ', font=dict(color='#a8bdd0', size=11)),
                      font=dict(color='#a8bdd0', size=9), bgcolor='#24384d', activebgcolor='#59e0ce',
                      steps=[dict(label=nm.split('-')[0] if nm.endswith('이동 전') else '', method='animate',
                                  args=[[nm], dict(mode='immediate', frame=dict(duration=0, redraw=True), transition=dict(duration=0))])
                             for nm in names])],
        margin=dict(l=0, r=0, t=36, b=60))
    return fig
