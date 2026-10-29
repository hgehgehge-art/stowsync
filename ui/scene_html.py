"""3D 야드를 브라우저에서 직접 그려 마우스 강조와 적치 애니메이션을 붙입니다.

st.plotly_chart는 사용자 정의 마우스 이벤트를 받을 수 없어서, 이 화면만 Plotly.js를 iframe 안에서 그립니다.
- 커서를 올린 컨테이너: 밝은 외곽선 + 바닥 그림자로 선택 상태를 표시
- 적치 미리보기: 트럭 → 들어 올림 → 이동 → 내려놓기 순서로 자동 재생
"""
import shutil
import uuid
from pathlib import Path
import plotly
import plotly.graph_objects as go
import streamlit as st
from engine.yard import locate
from ui.scene import (_static_traces, _layout, scene_traces, arriving, coords, truck_xy, DX, DY, DZ, PITCH)

_HOVER_JS = r"""
(function(){
  const gd = document.getElementById('%(id)s');
  const base = gd.data.length;
  // 강조용 트레이스 2개(바닥 그림자, 외곽선)를 맨 뒤에 추가합니다. 애니메이션 프레임은 이 트레이스를 건드리지 않습니다.
  Plotly.addTraces(gd, [
    {type:'mesh3d', x:[0], y:[0], z:[0], i:[0], j:[0], k:[0], color:'#000000', opacity:0, hoverinfo:'skip', showscale:false},
    {type:'scatter3d', mode:'lines', x:[null], y:[null], z:[null], line:{color:'rgba(89,224,206,0.35)', width:26}, hoverinfo:'skip', showlegend:false},
    {type:'scatter3d', mode:'lines', x:[null], y:[null], z:[null], line:{color:'#F4FBFF', width:9}, hoverinfo:'skip', showlegend:false}
  ]);
  const SH = base, GLOW = base + 1, OUT = base + 2;
  const E = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
  let last = -1;
  function clear(){
    if (last < 0) return; last = -1;
    Plotly.restyle(gd, {opacity:[0]}, [SH]);
    Plotly.restyle(gd, {x:[[null],[null]], y:[[null],[null]], z:[[null],[null]]}, [GLOW, OUT]);
  }
  gd.on('plotly_hover', function(ev){
    const p = ev && ev.points && ev.points[0];
    if (!p) return;
    const tr = gd.data[p.curveNumber];
    if (!tr || tr.name !== 'boxes') { clear(); return; }
    let n = p.pointNumber; if (Array.isArray(n)) n = n[0];
    if (n === undefined || n === null) return;
    const b = Math.floor(n / 8);
    if (b === last) return; last = b;
    const xs = tr.x.slice(b*8, b*8+8), ys = tr.y.slice(b*8, b*8+8), zs = tr.z.slice(b*8, b*8+8);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), z0 = Math.min(...zs);
    const pad = .12, off = .18;
    // 바닥 그림자: 상자 아래쪽에 살짝 비껴 놓은 어두운 사각형
    Plotly.restyle(gd, {x:[[x0-pad+off, x1+pad+off, x1+pad+off, x0-pad+off]], y:[[y0-pad-off, y0-pad-off, y1+pad-off, y1+pad-off]],
                        z:[[-.17,-.17,-.17,-.17]], i:[[0,0]], j:[[1,2]], k:[[2,3]], opacity:[.55], color:['#000000']}, [SH]);
    const lx=[], ly=[], lz=[];
    E.forEach(function(e){ lx.push(xs[e[0]], xs[e[1]], null); ly.push(ys[e[0]], ys[e[1]], null); lz.push(zs[e[0]], zs[e[1]], null); });
    Plotly.restyle(gd, {x:[lx, lx], y:[ly, ly], z:[lz, lz]}, [GLOW, OUT]);
  });
  gd.on('plotly_unhover', clear);
  %(autoplay)s
})();
"""

_AUTOPLAY = """setTimeout(function(){ Plotly.animate(gd, null, {frame:{duration:%d, redraw:true}, transition:{duration:0}, mode:'immediate'}); }, 450);"""


_STATIC = Path(__file__).resolve().parents[1] / 'static' / 'plotly.min.js'


def _ensure_plotly_js():
    """Plotly.js를 앱의 정적 폴더(/app/static)에서 제공합니다. 외부 CDN에 의존하지 않습니다."""
    if not _STATIC.exists():
        _STATIC.parent.mkdir(exist_ok=True)
        shutil.copyfile(Path(plotly.__file__).parent / 'package_data' / 'plotly.min.js', _STATIC)


def render(fig, height, autoplay_ms=None):
    """fig를 iframe으로 그립니다. autoplay_ms가 있으면 프레임을 자동 재생합니다."""
    div = 'yard-' + uuid.uuid4().hex[:8]
    _ensure_plotly_js()
    body = fig.to_html(include_plotlyjs=False, full_html=False, div_id=div,
                       config={'displayModeBar': False, 'scrollZoom': False, 'responsive': True},
                       default_height=f'{height}px', default_width='100%')
    js = _HOVER_JS % {'id': div, 'autoplay': (_AUTOPLAY % autoplay_ms) if autoplay_ms else ''}
    page = ('<html><head><meta charset="utf-8"><script src="/app/static/plotly.min.js"></script>'
            '<style>html,body{margin:0;background:transparent;overflow:hidden}</style></head>'
            f'<body>{body}<script>{js}</script></body></html>')
    st.iframe(page, height=height + 8)


def placement_figure(o, cid, target, height=420, focus_only=False):
    """선택한 대안 위치로 컨테이너를 내려놓는 과정을 프레임으로 만듭니다(트럭 → 들어 올림 → 이동 → 내려놓기)."""
    static = _static_traces()
    k0 = len(static)
    trucks = arriving(o)
    captions = {c: '트럭 위 · 하차 대기' for c in trucks}
    if not target:
        fig = go.Figure(static + scene_traces(o.containers, o.plan, o.yard, o.statuses, cid, None, trucks,
                                              focus_only=focus_only, captions=captions))
        return _layout(fig, height)
    key, tier = target
    if cid in trucks:
        b = o.containers[cid].block
        idx = [c for c in trucks if o.containers[c].block == b].index(cid)
        x0, y0 = truck_xy(b, idx); z0 = 0.
    else:
        x0, y0 = coords(key); z0 = 3.0
    x1, y1 = coords(key); z1 = (tier - 1) * PITCH
    lift = 3.0
    path = []
    for t in (0, .5, 1):
        path.append((x0, y0, z0 + (lift - z0) * t))
    for t in (.2, .4, .6, .8, 1):
        path.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, lift))
    for t in (.3, .6, .85, 1):
        path.append((x1, y1, lift + (z1 - lift) * t))
    frames = []
    for n, (x, y, z) in enumerate(path):
        data = scene_traces(o.containers, o.plan, o.yard, o.statuses, cid, target, trucks, moving=(cid, x, y, z),
                            focus_only=focus_only, captions=captions)
        frames.append(go.Frame(name=f'f{n}', data=data, traces=list(range(k0, k0 + 8))))
    after = {k: list(v) for k, v in o.yard.items()}
    after.setdefault(key, []).append(cid)
    final = scene_traces(o.containers, o.plan, after, o.statuses, cid, None, [c for c in trucks if c != cid],
                         focus_only=focus_only, captions=captions)
    frames.append(go.Frame(name='done', data=final, traces=list(range(k0, k0 + 8))))
    # 처음 그릴 때는 현재 상태(트럭 위 + 추천 위치)를 보여 주고, 곧바로 적치 과정을 재생합니다.
    first = scene_traces(o.containers, o.plan, o.yard, o.statuses, cid, target, trucks, focus_only=focus_only, captions=captions)
    fig = go.Figure(static + first, frames=frames)
    fig = _layout(fig, height)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=44), updatemenus=[dict(
        type='buttons', direction='right', x=0, y=-.01, xanchor='left', yanchor='top', showactive=False,
        bgcolor='#1b2c40', bordercolor='#36506b', font=dict(color='#eaf3fb', size=12),
        buttons=[dict(label='↺ 적치 과정 다시 보기', method='animate',
                      args=[[f.name for f in frames], dict(frame=dict(duration=110, redraw=True), transition=dict(duration=0), mode='immediate')]),
                 dict(label='적치 전 상태', method='animate',
                      args=[['f0'], dict(frame=dict(duration=0, redraw=True), mode='immediate')])])])
    return fig
