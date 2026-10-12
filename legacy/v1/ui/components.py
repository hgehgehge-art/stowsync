"""공통 UI: 테마 주입, 히어로 헤더, KPI 카드, 배지, Plotly 템플릿."""
from __future__ import annotations

import html
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent

C = {
    "bg": "#0A1628", "surface": "#111F38", "border": "#1E3A5F", "primary": "#00D4FF",
    "safe": "#2EE6A6", "warn": "#FFB547", "danger": "#FF4D6D", "text": "#E6EDF7", "muted": "#8BA3C7",
}
# 선박 범주색 (어두운 표면에서 검증: 밝기 밴드·색각이상 분리 통과, 범례 병기)
VESSEL_COLORS = ["#0098BD", "#B8862E", "#8F6FE6"]
# 전략색: 현행 = 회색 기준선, A = 보라, B(StowSync) = 시안
STRATEGY_COLORS = {"current": "#6B7F9E", "A": "#8F6FE6", "B": "#00D4FF"}
STRATEGY_SHORT = {"current": "현행", "A": "방식 A", "B": "방식 B"}
RISK_SCALE = [[0, "#13233F"], [0.35, "#4A2A4F"], [1, "#FF4D6D"]]

SHIP_SVG = ('<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#00D4FF" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M2 20c1.5 1 3 1 4.5 0s3-1 4.5 0 3 1 4.5 0 3-1 4.5 0"/>'
            '<path d="M4 17l-1-5h18l-2 5"/><rect x="7" y="7" width="4" height="5" rx=".5"/><rect x="11" y="4" width="4" height="8" rx=".5"/>'
            '<rect x="15" y="8" width="3" height="4" rx=".5"/></svg>')


# ── 테마 ──────────────────────────────────────────────
def inject_theme():
    css = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")
    register_plotly_template()


def register_plotly_template():
    if "stowsync" in pio.templates:
        return
    t = go.layout.Template()
    t.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Pretendard Variable, Pretendard, Apple SD Gothic Neo, sans-serif", color=C["text"], size=13),
        colorway=VESSEL_COLORS,
        xaxis=dict(gridcolor=C["border"], linecolor=C["border"], zerolinecolor=C["border"], tickcolor=C["border"],
                   tickfont=dict(color=C["muted"]), title=dict(font=dict(color=C["muted"], size=12))),
        yaxis=dict(gridcolor=C["border"], linecolor=C["border"], zerolinecolor=C["border"], tickcolor=C["border"],
                   tickfont=dict(color=C["muted"]), title=dict(font=dict(color=C["muted"], size=12))),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=C["muted"], size=12), orientation="h", y=1.08, x=0),
        hoverlabel=dict(bgcolor=C["surface"], bordercolor=C["primary"],
                        font=dict(family="JetBrains Mono, monospace", color=C["text"], size=12)),
        margin=dict(l=48, r=18, t=36, b=40),
        title=dict(font=dict(size=14, color=C["text"]), x=0.01),
        bargap=0.25,
    )
    pio.templates["stowsync"] = t
    pio.templates.default = "stowsync"


PLOTLY_CONFIG = {"displayModeBar": False, "displaylogo": False}


def chart(fig, height=None, key=None):
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, key=key)


# ── 히어로 헤더 (실시간 시계) ──────────────────────────
def hero(title: str, subtitle: str, eyebrow: str = "STOWSYNC CONTROL", badge: str | None = None):
    badge_html = (f'<span class="badge">{html.escape(badge)}</span>' if badge else "")
    components.html(f"""
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700&display=swap">
<style>
 html,body{{margin:0;background:transparent;font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",sans-serif;color:#E6EDF7;overflow:hidden}}
 .hero{{position:relative;box-sizing:border-box;height:118px;border-radius:16px;padding:18px 24px;
   background:linear-gradient(120deg,#0A1628 0%,#0F2A4A 100%);border:1px solid #1E3A5F;overflow:hidden;
   display:flex;justify-content:space-between;align-items:center;gap:16px;animation:f .45s ease-out both}}
 .hero:before{{content:"";position:absolute;inset:0;background:
   repeating-linear-gradient(90deg,rgba(0,212,255,.05) 0 1px,transparent 1px 56px),
   radial-gradient(500px 160px at 90% 0%,rgba(0,212,255,.16),transparent 70%);pointer-events:none}}
 .hero:after{{content:"";position:absolute;left:-30%;top:0;width:30%;height:100%;
   background:linear-gradient(90deg,transparent,rgba(0,212,255,.08),transparent);animation:scan 6s linear infinite}}
 .eyebrow{{font-family:"JetBrains Mono",monospace;font-size:11px;letter-spacing:.22em;color:#00D4FF;opacity:.9;display:flex;gap:10px;align-items:center}}
 .live{{width:7px;height:7px;border-radius:50%;background:#2EE6A6;box-shadow:0 0 10px #2EE6A6;animation:blink 1.6s infinite}}
 h1{{margin:6px 0 4px;font-size:28px;font-weight:800;letter-spacing:-.02em}}
 p{{margin:0;color:#8BA3C7;font-size:14px}}
 .badge{{font-family:"JetBrains Mono",monospace;font-size:11px;border:1px solid #FFB547;color:#FFB547;padding:2px 9px;border-radius:999px;letter-spacing:.05em;margin-left:6px}}
 .clock{{text-align:right;font-family:"JetBrains Mono",monospace;position:relative;z-index:1}}
 .clock .t{{font-size:30px;font-weight:700;color:#E6EDF7;letter-spacing:.02em;text-shadow:0 0 18px rgba(0,212,255,.35)}}
 .clock .d{{font-size:11px;color:#8BA3C7;letter-spacing:.14em}}
 .left{{position:relative;z-index:1;min-width:0}}
 @keyframes f{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1}}}}
 @keyframes scan{{to{{left:130%}}}}
 @keyframes blink{{50%{{opacity:.3}}}}
 @media(max-width:640px){{h1{{font-size:21px}}.clock .t{{font-size:20px}}p{{font-size:12px}}.hero{{padding:14px 16px}}}}
</style>
<div class="hero">
  <div class="left">
    <div class="eyebrow"><span class="live"></span>{html.escape(eyebrow)}</div>
    <h1>{html.escape(title)}{badge_html}</h1>
    <p>{html.escape(subtitle)}</p>
  </div>
  <div class="clock"><div class="t" id="t">--:--:--</div><div class="d" id="d">BUSAN · KST</div></div>
</div>
<script>
 const pad=n=>String(n).padStart(2,'0');
 function tick(){{const n=new Date(Date.now()+ (new Date().getTimezoneOffset()+540)*60000);
   document.getElementById('t').textContent=pad(n.getHours())+':'+pad(n.getMinutes())+':'+pad(n.getSeconds());
   document.getElementById('d').textContent=n.getFullYear()+'.'+pad(n.getMonth()+1)+'.'+pad(n.getDate())+' · BUSAN KST';}}
 tick();setInterval(tick,1000);
</script>""", height=124)


# ── 작은 조각들 ────────────────────────────────────────
def badge(text: str, kind: str = "primary") -> str:
    return f'<span class="ss-badge {kind}">{html.escape(str(text))}</span>'


def section(title: str, hint: str = ""):
    st.markdown(f'<div class="ss-section"><h3>{html.escape(title)}</h3><span class="hint">{html.escape(hint)}</span></div>',
                unsafe_allow_html=True)


def callout(text_html: str, kind: str = ""):
    st.markdown(f'<div class="ss-callout {kind}">{text_html}</div>', unsafe_allow_html=True)


def legend(items: list[tuple[str, str]]):
    st.markdown('<div class="ss-legend">' + "".join(
        f'<span><i style="background:{c}"></i>{html.escape(t)}</span>' for t, c in items) + "</div>",
        unsafe_allow_html=True)


def sparkline(values, color=C["primary"], w=220, h=34) -> str:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = [(i * (w - 4) / (len(vals) - 1) + 2, h - 4 - (v - lo) / rng * (h - 8)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"2,{h} " + line + f" {w - 2},{h}"
    gid = f"g{abs(hash((tuple(vals), color))) % 10**8}"
    lx, ly = pts[-1]
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity=".35"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="{area}" fill="url(#{gid})"/><polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="{color}"/></svg>')


def kpi_card(label: str, value: str, unit: str = "", delta: float | None = None, delta_label: str = "현행 대비",
             lower_is_better: bool = True, spark=None, sub: str = "", accent: str = C["primary"], delay: float = 0) -> str:
    b = ""
    if delta is not None:
        good = (delta < 0) == lower_is_better if delta != 0 else True
        arrow = "▼" if delta < 0 else ("▲" if delta > 0 else "■")
        b = badge(f"{delta_label} {arrow}{abs(delta):.0f}%", "safe" if good else "danger")
    return (f'<div class="ss-card ss-kpi" style="--accent:{accent};animation-delay:{delay:.2f}s">'
            f'<div class="label"><span>{html.escape(label)}</span>{b}</div>'
            f'<div class="value">{value}<span class="unit">{html.escape(unit)}</span></div>'
            f'<div class="sub">{sub}</div>{sparkline(spark, accent) if spark is not None else ""}</div>')


def kpi_row(cards: list[str]):
    st.markdown('<div class="ss-kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def risk_badge(rate: float) -> str:
    if rate < 0.25:
        return badge("● 낮음", "safe")
    if rate < 0.5:
        return badge("● 중간", "warn")
    return badge("● 높음", "danger")
