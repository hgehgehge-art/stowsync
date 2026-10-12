from html import escape
from pathlib import Path
import streamlit as st

CSS = """
<style>
:root { --ink:#e6edf5; --muted:#91a2b8; --line:#26354a; --teal:#59e0ce; }
html,body,.stApp {font-family: -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;}
.stApp {background:radial-gradient(ellipse at 82% 0%,#15304066 0%,transparent 36%),#09121f;}
header[data-testid="stHeader"] {background:transparent; height:2.1rem;}
[data-testid="stToolbar"] {display:none;}
.block-container {padding:2.15rem 2.3rem 2rem;max-width:1800px;}
[data-testid="stSidebar"] {background:#0b1625;border-right:1px solid #203046;width:240px!important;min-width:240px!important;max-width:240px!important;}
[data-testid="stSidebar"]>div:first-child {padding-top:0;}
[data-testid="stSidebarHeader"] {height:38px;min-height:38px;padding-top:4px;padding-bottom:4px;}
[data-testid="stSidebarUserContent"] {padding:0 16px 16px;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:.35rem;}
[data-testid="stSidebar"] .stButton button {border:0;background:transparent;color:#9cacc1;text-align:left;justify-content:flex-start;padding:12px 16px;font-size:14px;}
[data-testid="stSidebar"] .stButton button[kind="primary"] {background:#173737;color:#75eadb;border:1px solid #2c625b;box-shadow:inset 3px 0 #59e0ce;}
[data-testid="stSidebar"] .stButton button:hover {background:#16263a;color:#edf5ff;}
.stButton button, .stDownloadButton button {border-radius:8px;font-weight:550;min-height:40px;border-color:#304358;}
.stButton button[kind="primary"] {color:#08231f;background:#59e0ce;border-color:#59e0ce;}
.stButton button[kind="primary"]:hover {background:#7eecdd;color:#08231f;}
.stSelectbox label,.stSlider label,.stRadio label,.stTextInput label {color:#9eafc3;font-size:12px;}
div[data-testid="stVerticalBlock"] {gap:.72rem;}
.st-key-canvas, .st-key-focus, .st-key-arrivals, .st-key-arrival-evidence, .st-key-events, .st-key-chart, .st-key-review, .st-key-eta_chart, .st-key-stack {border:1px solid #26354a;border-radius:13px;background:#101d2d;padding:18px 20px;}
.st-key-arrival-evidence .app-table td {white-space:normal;line-height:1.65;vertical-align:top;}
.st-key-focus {background:linear-gradient(155deg,#173034,#112231 60%);border-color:#2b514f;}
.st-key-canvas {background:radial-gradient(ellipse at 55% 60%,#1a3447 0%,#101c2c 63%);}
.brand {display:flex;align-items:center;gap:11px;padding:0 4px 13px;}
.brand-symbol {width:38px;height:38px;background:#183a3c;border:1px solid #36776e;border-radius:10px;display:grid;place-items:center;color:#73f1d9;font-size:28px;}
.brand-name {font-size:24px;letter-spacing:-.9px;font-weight:750;line-height:1.2;}
.brand-sub {font-size:8.5px;letter-spacing:2.1px;color:#819bad;margin-top:6px;}
.side-label {font-size:10px;letter-spacing:1.8px;color:#637c93;margin:13px 10px 5px;}
.side-card {border-top:1px solid #25364a;margin-top:22px;padding:20px 12px 8px;}
.side-card strong {font-size:13px;font-weight:600;}
.side-card p {color:#8da3b7;font-size:11px;line-height:1.8;margin-top:7px;}
.side-stamp {display:inline-block;border:1px solid #3c5061;border-radius:5px;color:#9eafc1;font-size:9px;letter-spacing:1px;padding:3px 7px;}
.eyebrow {font-size:10px;font-weight:600;letter-spacing:2.2px;color:#91aab9;margin-bottom:10px;}
.page-head {display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:18px;}
.page-head h1 {font-size:29px;letter-spacing:-1.3px;line-height:1.3;padding:0;margin:0;font-weight:680;color:#eff5fc;}
.page-head p {color:#8fa3b9;font-size:12px;margin:10px 0 0;line-height:1.7;}
.head-right {text-align:right;min-width:165px;}
.head-time {font-size:26px;font-weight:350;letter-spacing:1px;color:#d9e7ee;font-variant-numeric:tabular-nums;}
.head-date {font-size:10px;color:#7e97ae;margin-top:5px;letter-spacing:.4px;}
.pill {display:inline-flex;align-items:center;gap:6px;border:1px solid #2d5352;border-radius:5px;padding:4px 8px;color:#81ded1;font-size:10px;white-space:nowrap;}
.pill.amber {color:#eec274;border-color:#634f33;background:#342d221c;}
.pill.coral {color:#ee99a4;border-color:#644354;}
.pill.blue {color:#9abcfa;border-color:#3c516e;}
.source-strip {display:flex;align-items:center;gap:12px;padding:13px 17px;border:1px solid #24364a;border-radius:9px;background:#111e2d;margin:14px 0 15px;font-size:11px;color:#a4b8cb;}
.source-strip b {color:#d6e4ef;font-weight:550;}
.source-strip em {font-style:normal;color:#667e94;margin-left:5px;font-size:10px;}
.source-strip .arrow {color:#466279;font-size:15px;}
.source-strip .right {margin-left:auto;color:#71cabc;font-size:10px;}
.metric-card {padding:17px 19px;background:linear-gradient(120deg,#142336,#111d2d);border:1px solid #293a50;border-radius:11px;min-height:121px;position:relative;overflow:hidden;}
.metric-card:after {content:"";position:absolute;right:-16px;bottom:-38px;width:110px;height:110px;border:1px solid #35526833;border-radius:50%;}
.metric-top {display:flex;align-items:center;justify-content:space-between;color:#a9bbcd;font-size:11px;letter-spacing:.2px;}
.metric-number {font-size:33px;font-weight:600;letter-spacing:-1.2px;margin-top:9px;line-height:1.18;font-variant-numeric:tabular-nums;}
.metric-number small {font-size:12px;font-weight:400;letter-spacing:0;margin-left:5px;color:#96abc0;}
.metric-note {font-size:10px;color:#8098b0;margin-top:8px;}
.teal {color:#6de5d1;} .coral {color:#f18b9c;} .amber {color:#edc17b;} .blue {color:#89aef5;}
.panel-head {display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px;}
.panel-head h3 {font-size:15px;font-weight:600;letter-spacing:-.3px;padding:0;margin:0;}
.panel-head span {font-size:9px;letter-spacing:1.2px;color:#7f99ac;}
.panel-sub {font-size:11px;color:#829aaf;margin:7px 0 5px;line-height:1.7;}
.legend {display:flex;gap:19px;font-size:10px;color:#9ab1c6;align-items:center;flex-wrap:wrap;}
.dot {display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;background:#56c5be;}
.dot.coral {background:#e77d93;} .dot.blue {background:#6c94d7;} .dot.amber {background:#e9bd76;}
.focus-kicker {font-size:9px;letter-spacing:1.8px;color:#79c9bb;margin-bottom:13px;}
.focus-title {font-size:21px;letter-spacing:-.7px;font-weight:600;line-height:1.5;margin:8px 0;color:#eaf5f7;}
.focus-copy {font-size:11px;color:#9eb4c5;line-height:1.85;margin-bottom:14px;}
.focus-id {font-size:12px;color:#a9cfcf;font-variant-numeric:tabular-nums;margin:12px 0 15px;}
.detail-row {display:flex;justify-content:space-between;gap:15px;padding:9px 0;border-bottom:1px solid #31505a66;font-size:11px;}
.detail-row span {color:#91a9b9;} .detail-row b {color:#e0ebf2;font-weight:500;}
.focus-route {background:#0b1925;border:1px solid #2d4b55;border-radius:7px;padding:13px 12px;margin:16px 0 8px;display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#87aaa9;}
.focus-route strong {color:#6de5d1;font-size:15px;letter-spacing:.5px;}
.small-note {font-size:10px;line-height:1.7;color:#8298ad;}
.app-table {width:100%;border-collapse:collapse;font-size:11px;margin:9px 0 3px;}
.app-table th {color:#718ba4;font-weight:500;font-size:10px;text-align:left;padding:10px 9px;border-bottom:1px solid #2b3c52;}
.app-table td {color:#c2d1df;padding:12px 9px;border-bottom:1px solid #203146;white-space:nowrap;}
.app-table td:first-child {color:#dde7ef;font-size:11px;font-weight:500;}
.app-table tr:last-child td {border-bottom:0;}
.app-table .pill {padding:3px 6px;font-size:9px;}
.event {display:flex;gap:12px;padding:12px 0;border-bottom:1px solid #26384b;}
.event:last-child {border:0;}
.event-time {font-size:10px;color:#829ab0;min-width:34px;padding-top:2px;font-variant-numeric:tabular-nums;}
.event-title {font-size:11px;color:#d3e2ed;margin-bottom:5px;}
.event-copy {font-size:10px;color:#839ab0;line-height:1.6;}
.footer {border-top:1px solid #253549;padding-top:13px;margin-top:15px;display:flex;justify-content:space-between;font-size:9px;color:#6f879d;letter-spacing:.2px;gap:15px;}
.candidate {padding:19px 18px;border:1px solid #2e4159;border-radius:11px;background:#142236;min-height:231px;}
.candidate.best {border-color:#42857b;background:linear-gradient(130deg,#163937,#142334);}
.candidate-rank {color:#829cb2;font-size:10px;letter-spacing:1.5px;}
.candidate-slot {font-size:21px;font-weight:600;letter-spacing:-.5px;margin:12px 0 16px;}
.candidate-fact {font-size:11px;line-height:2;color:#adbfce;}
.candidate-fact b {color:#e7eff8;font-weight:500;float:right;}
.reason {font-size:10px;line-height:1.7;color:#79cbbb;padding-top:12px;border-top:1px solid #35525d;margin-top:10px;}
.steps {display:flex;gap:8px;margin:12px 0 16px;}
.step {flex:1;padding:14px 12px;background:#132334;border:1px solid #2c3e53;border-radius:8px;font-size:11px;color:#8b9fb6;}
.step.active {background:#183635;border-color:#396c64;color:#85e3d1;}
.step small {display:block;color:#7c96a9;margin-top:7px;font-size:9px;}
.section-note {padding:15px 18px;border-left:2px solid #68cdbc;background:#12262e;border-radius:0 8px 8px 0;font-size:11px;line-height:1.85;color:#b2c7d5;margin:12px 0;}
.stack-grid {display:flex;gap:8px;align-items:flex-end;padding:18px 0 8px;}
.stack-column {flex:1;display:flex;flex-direction:column;gap:5px;}
.stack-cell {height:37px;border:1px solid #325474;background:#203e5c;border-radius:4px;text-align:center;padding-top:11px;font-size:9px;color:#c1d6e9;}
.stack-cell.empty {background:#102033;border:1px dashed #2b4158;color:#60768c;}
.stack-cell.risk {background:#4f3346;border-color:#ad6079;color:#ffc2cd;}
.stack-cell.target {background:#204b48;border-color:#6ddccc;color:#b2fff1;}
.stack-label {text-align:center;font-size:9px;color:#879db1;margin-top:5px;}
.integration {border:1px solid #2c4159;background:#112236;border-radius:11px;padding:23px;min-height:210px;}
.integration h3 {font-size:18px;padding:8px 0;color:#e8f2fc;}
.integration p {font-size:12px;line-height:1.8;color:#9eb6c9;}
.integration .num {font-size:10px;letter-spacing:2px;color:#6fcbbb;}
.export-banner {padding:17px 21px;border:1px solid #33465e;border-radius:10px;background:#152437;font-size:12px;line-height:1.8;color:#b1c5d6;}
@media(max-width:1050px) {.block-container{padding:2rem 1rem;} .page-head h1{font-size:24px;} .source-strip{flex-wrap:wrap;} .source-strip .right{margin-left:0;} }
@media(max-width:700px) {.head-right{display:none;} .metric-card{min-height:110px;} .app-table{font-size:10px;} .source-strip em{display:none;} .steps{flex-wrap:wrap;} .step{min-width:40%;} }
</style>
"""

def inject(): st.html(CSS)

def html(s): st.html(s)

def badge(text, color=""): return f'<span class="pill {escape(color)}">{escape(str(text))}</span>'

def panel(title, tag="", subtitle=""):
    html(f'<div class="panel-head"><h3>{escape(title)}</h3><span>{escape(tag)}</span></div>' + (f'<div class="panel-sub">{escape(subtitle)}</div>' if subtitle else ''))

def metric(label, value, unit="", note="", color="", code=""):
    html(f'<div class="metric-card"><div class="metric-top">{escape(label)}<span class="{color}">{escape(code)}</span></div><div class="metric-number {color}">{escape(str(value))}<small>{escape(unit)}</small></div><div class="metric-note">{escape(note)}</div></div>')

def table(headers, rows):
    # Cells are assembled by trusted UI functions; caller escapes user-provided text.
    html('<table class="app-table"><thead><tr>'+''.join(f'<th>{escape(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{c}</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>')

def tm(seconds):
    m = int(seconds)//60 + 9*60
    return f'{m//60:02d}:{m%60:02d}'

def mins(seconds): return '—' if seconds is None else f'{seconds/60:.1f}'

def footer():
    html('<div class="footer"><span>StowSync · 부산항 수출 FCL 의사결정 지원 제안</span><span>DEMO / 합성 데이터 · 모의 승인 · 실제 시스템 미연계</span></div>')
