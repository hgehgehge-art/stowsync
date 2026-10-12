"""야드 3D 뷰 (Plotly Mesh3d) 와 베이 단면 HTML."""
from __future__ import annotations

import html
import math

import numpy as np
import plotly.graph_objects as go

from core.relocation import INF, blockers_above
from ui.components import C, VESSEL_COLORS

BAY_PITCH, ROW_PITCH, TIER_H = 3.1, 1.4, 1.3
LEN40, LEN20, WIDTH, HEIGHT = 2.85, 1.38, 1.22, 1.18
WG_COLORS = ["#1D5E78", "#0098BD", "#7FE9FF"]          # 중량 그룹: 가벼움 → 무거움 (밝을수록 무거움)
RISK_COLORS = {"safe": C["safe"], "warn": C["warn"], "danger": C["danger"], "rolled": "#5B6B8C", "user": "#FFFFFF"}

# 단위 큐브 (plotly 문서 표준 인덱스)
_CX = np.array([0, 0, 1, 1, 0, 0, 1, 1])
_CY = np.array([0, 1, 1, 0, 0, 1, 1, 0])
_CZ = np.array([0, 0, 0, 0, 1, 1, 1, 1])
_I = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
_J = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
_K = [0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6]
_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]


def box_risk(stack, idx, seq) -> str:
    s = seq.get(stack[idx], INF)
    if s == INF or (isinstance(s, float) and math.isnan(s)):
        return "rolled"
    below = min((seq.get(b, INF) for b in stack[:idx]), default=INF)
    if s > below:
        return "danger"       # 이 박스가 아래 박스를 막음 → 재조작 대상
    if blockers_above(stack, idx, seq) > 0:
        return "warn"         # 위에 방해 박스가 있음
    return "safe"


def yard_figure(blocks: list[dict], info, seq: dict, color_mode: str, user_boxes: set = frozenset(),
                max_tiers: int = 5, rows: int = 6, height: int = 560, show_labels: bool = True) -> go.Figure:
    """blocks: [{"name": "A1", "area": {...}, "vessel_idx": 0}], info: cntr_no 를 index 로 하는 DataFrame."""
    X, Y, Z, I, J, K, FC, TXT = [], [], [], [], [], [], [], []
    ex, ey, ez = [], [], []
    gx, gy, gz = [], [], []
    lab_x, lab_y, lab_z, lab_t = [], [], [], []
    n = 0
    for bi, blk in enumerate(blocks):
        y0 = bi * (rows * ROW_PITCH + 3.2)
        area = blk["area"]
        nb = len(area)
        lab_x.append(-2.2)
        lab_y.append(y0 + rows * ROW_PITCH / 2)
        lab_z.append(0.2)
        lab_t.append(f"<b>{blk['name']}</b>")
        # 바닥 슬롯 격자
        for b in range(nb):
            for r in range(rows):
                x0, yy = b * BAY_PITCH, y0 + r * ROW_PITCH
                for (a, c) in [((x0, yy), (x0 + LEN40, yy)), ((x0 + LEN40, yy), (x0 + LEN40, yy + WIDTH)),
                               ((x0 + LEN40, yy + WIDTH), (x0, yy + WIDTH)), ((x0, yy + WIDTH), (x0, yy))]:
                    gx += [a[0], c[0], None]
                    gy += [a[1], c[1], None]
                    gz += [0, 0, None]
        for b, stacks in area.items():
            for r, st in enumerate(stacks):
                for t, cn in enumerate(st):
                    row = info.loc[cn] if cn in info.index else None
                    size = int(row["size"]) if row is not None else 40
                    ln = LEN40 if size == 40 else LEN20
                    x0 = b * BAY_PITCH + (LEN40 - ln) / 2
                    yy = y0 + r * ROW_PITCH
                    zz = t * TIER_H
                    vx = x0 + _CX * ln
                    vy = yy + _CY * WIDTH
                    vz = zz + _CZ * HEIGHT
                    X += vx.tolist()
                    Y += vy.tolist()
                    Z += vz.tolist()
                    I += [i + n for i in _I]
                    J += [j + n for j in _J]
                    K += [k + n for k in _K]
                    for a, c in _EDGES:
                        ex += [vx[a], vx[c], None]
                        ey += [vy[a], vy[c], None]
                        ez += [vz[a], vz[c], None]
                    risk = box_risk(st, t, seq)
                    if cn in user_boxes:
                        col = RISK_COLORS["user"]
                    elif color_mode == "risk":
                        col = RISK_COLORS[risk]
                    elif color_mode == "vessel":
                        col = VESSEL_COLORS[blk["vessel_idx"] % len(VESSEL_COLORS)]
                    else:
                        wg = int(row["weight_group"]) if row is not None and "weight_group" in row else 1
                        col = WG_COLORS[min(wg, 2)]
                    FC += [col] * 12
                    sq = seq.get(cn, INF)
                    seq_txt = "선적 안 함(롤오버)" if sq == INF or (isinstance(sq, float) and math.isnan(sq)) else f"{sq * 100:.0f} 백분위"
                    blk_n = blockers_above(st, t, seq)
                    if row is not None:
                        tip = (f"<b>{cn}</b>{' · NEW' if cn in user_boxes else ''}<br>"
                               f"위치 {blk['name']}-{b + 1:02d}-{r + 1}-{t + 1}<br>"
                               f"중량 {row['vgm_weight']:.1f}t · {size}ft{' · DG' if row['is_dg'] else ''}<br>"
                               f"양하항 {row['pod']}<br>예상 선적 순서 {seq_txt}<br>위에 쌓인 방해 박스 {blk_n}개")
                    else:
                        tip = cn
                    TXT += [tip] * 8
                    n += 8
    fig = go.Figure()
    fig.add_trace(go.Scatter3d(x=gx, y=gy, z=gz, mode="lines", line=dict(color="rgba(30,58,95,.75)", width=1.5),
                               hoverinfo="skip", showlegend=False))
    if X:
        fig.add_trace(go.Mesh3d(x=X, y=Y, z=Z, i=I, j=J, k=K, facecolor=FC, flatshading=True, opacity=1,
                                text=TXT, hovertemplate="%{text}<extra></extra>",
                                lighting=dict(ambient=.62, diffuse=.75, specular=.25, roughness=.6, fresnel=.1),
                                lightposition=dict(x=100, y=-200, z=300), showscale=False))
        fig.add_trace(go.Scatter3d(x=ex, y=ey, z=ez, mode="lines", line=dict(color="rgba(10,22,40,.85)", width=2),
                                   hoverinfo="skip", showlegend=False))
    if show_labels:
        fig.add_trace(go.Scatter3d(x=lab_x, y=lab_y, z=lab_z, mode="text", text=lab_t,
                                   textfont=dict(color=C["primary"], size=14, family="JetBrains Mono"),
                                   hoverinfo="skip", showlegend=False))
    axis = dict(visible=False, showbackground=False)
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        scene=dict(xaxis=axis, yaxis=axis, zaxis=dict(axis, range=[0, max_tiers * TIER_H + .5]),
                   aspectmode="data", bgcolor="rgba(0,0,0,0)",
                   camera=dict(eye=dict(x=-1.25, y=-1.55, z=1.05), center=dict(x=0, y=0, z=-.15))),
        uirevision="yard")
    return fig


def bay_grid_html(area: dict, bay: int, block: str, max_tiers: int, hit: set, under: set) -> str:
    """베이 단면: 로우 × 단. hit = 깜빡이는 박스(변경 대상), under = 영향받는 박스."""
    stacks = area[bay]
    cols = len(stacks)
    cells = []
    for t in range(max_tiers - 1, -1, -1):
        for r in range(cols):
            st = stacks[r]
            if t < len(st):
                b = st[t]
                cls = "hit" if b in hit else ("under" if b in under else "box")
                cells.append(f'<div class="cell {cls}" title="{html.escape(b)}"></div>')
            else:
                cells.append('<div class="cell"></div>')
    return (f'<div class="ss-bay"><div class="cap">{block}-{bay + 1:02d}</div>'
            f'<div class="grid" style="grid-template-columns:repeat({cols},30px)">{"".join(cells)}</div></div>')
