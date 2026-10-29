from html import escape
from pathlib import Path
import streamlit as st

CSS = """
<style>
:root { /* 주황·흰 테마 토큰. 주황(#ED6B2C)은 면·테두리, 글자에는 대비 4.5:1을 넘는 #B4532A를 씁니다. */
  --primary:#ED6B2C; --primary-ink:#B4532A; --primary-soft:#FFF3EC; --rust:#C06443; --ink:#2A3449; --indigo:#3C3E90;
  --text:#424242; --muted:#5F6368; --line:#E2E2E7; --bg:#FFFFFF; --surface:#F5F5F7; --divider:#EEEEEE; --on-primary:#1A1A1A; }
html,body,.stApp {font-family: -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;}
.stApp {background:#FFFFFF;color:#2A3449;}
header[data-testid="stHeader"] {background:transparent; height:2.1rem;}
[data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {display:none;}
[data-testid="stSidebar"][aria-expanded="false"] {width:0!important;min-width:0!important;max-width:0!important;}
.block-container {padding:2.15rem 2.3rem 2rem;max-width:1800px;}
[data-testid="stSidebar"] {background:#F5F5F7;border-right:1px solid #E2E2E7;width:240px!important;min-width:240px!important;max-width:240px!important;}
[data-testid="stSidebar"]>div:first-child {padding-top:0;}
[data-testid="stSidebarHeader"] {height:38px;min-height:38px;padding-top:4px;padding-bottom:4px;}
[data-testid="stSidebarUserContent"] {padding:0 16px 16px;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:.35rem;}
[data-testid="stSidebar"] .stButton button {border:0;background:transparent;color:#424242;text-align:left;justify-content:flex-start;padding:12px 16px;font-size:14px;}
[data-testid="stSidebar"] .stButton button[kind="primary"] {background:#FFF3EC;color:#B4532A;border:1px solid #ED6B2C;box-shadow:inset 3px 0 #ED6B2C;}
[data-testid="stSidebar"] .stButton button:hover {background:#F5F5F7;color:#3C3E90;}
.stButton button, .stDownloadButton button {border-radius:8px;font-weight:550;min-height:40px;border-color:#E2E2E7;}
.stButton button[kind="primary"] {color:#1A1A1A;background:#ED6B2C;border-color:#ED6B2C;}
.stButton button[kind="primary"]:hover {background:#ED6B2C;color:#1A1A1A;}
.stSelectbox label,.stSlider label,.stRadio label,.stTextInput label {color:#424242;font-size:12px;}
div[data-testid="stVerticalBlock"] {gap:.72rem;}
.st-key-canvas, .st-key-focus, .st-key-arrivals, .st-key-arrival-evidence, .st-key-events, .st-key-chart, .st-key-review, .st-key-eta_chart, .st-key-stack {border:1px solid #E2E2E7;border-radius:13px;background:#F5F5F7;padding:18px 20px;}
.st-key-arrival-evidence .app-table td {white-space:normal;line-height:1.65;vertical-align:top;}
.st-key-focus {background:linear-gradient(155deg,#FFF3EC,#F5F5F7 60%);border-color:#E2E2E7;}
.st-key-canvas {background:radial-gradient(ellipse at 55% 60%,#E2E2E7 0%,#F5F5F7 63%);}
.brand {display:flex;align-items:center;gap:11px;padding:0 4px 13px;}
.brand-symbol {width:38px;height:38px;background:#FFF3EC;border:1px solid #ED6B2C;border-radius:10px;display:grid;place-items:center;color:#B4532A;font-size:28px;}
.brand-name {font-size:24px;letter-spacing:-.9px;font-weight:750;line-height:1.2;}
.brand-sub {font-size:8.5px;letter-spacing:2.1px;color:#5F6368;margin-top:6px;}
.side-label {font-size:10px;letter-spacing:1.8px;color:#5F6368;margin:13px 10px 5px;}
.side-card {border-top:1px solid #E2E2E7;margin-top:22px;padding:20px 12px 8px;}
.side-card strong {font-size:13px;font-weight:600;}
.side-card p {color:#424242;font-size:11px;line-height:1.8;margin-top:7px;}
.side-stamp {display:inline-block;border:1px solid #CFCFD6;border-radius:5px;color:#424242;font-size:9px;letter-spacing:1px;padding:3px 7px;}
.eyebrow {font-size:10px;font-weight:600;letter-spacing:2.2px;color:#424242;margin-bottom:10px;}
.page-head {display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:18px;}
.page-head h1 {font-size:29px;letter-spacing:-1.3px;line-height:1.3;padding:0;margin:0;font-weight:680;color:#3C3E90;}
.page-head p {color:#424242;font-size:12px;margin:10px 0 0;line-height:1.7;}
.head-right {text-align:right;min-width:165px;}
.head-time {font-size:26px;font-weight:350;letter-spacing:1px;color:#2A3449;font-variant-numeric:tabular-nums;}
.head-date {font-size:10px;color:#5F6368;margin-top:5px;letter-spacing:.4px;}
.pill {display:inline-flex;align-items:center;gap:6px;border:1px solid #E2E2E7;border-radius:5px;padding:4px 8px;color:#B4532A;font-size:10px;white-space:nowrap;}
.pill.amber {color:#8A5A00;border-color:#E2E2E7;background:#F5F5F71c;}
.pill.coral {color:#B42318;border-color:#CFCFD6;}
.pill.blue {color:#3C3E90;border-color:#CFCFD6;}
.source-strip {display:flex;align-items:center;gap:12px;padding:13px 17px;border:1px solid #E2E2E7;border-radius:9px;background:#F5F5F7;margin:14px 0 15px;font-size:11px;color:#424242;}
.source-strip b {color:#2A3449;font-weight:550;}
.source-strip em {font-style:normal;color:#5F6368;margin-left:5px;font-size:10px;}
.source-strip .arrow {color:#5F6368;font-size:15px;}
.source-strip .right {margin-left:auto;color:#B4532A;font-size:10px;}
.metric-card {padding:17px 19px;background:linear-gradient(120deg,#F5F5F7,#F5F5F7);border:1px solid #E2E2E7;border-radius:11px;min-height:121px;position:relative;overflow:hidden;}
.metric-card:after {content:"";position:absolute;right:-16px;bottom:-38px;width:110px;height:110px;border:1px solid #CFCFD633;border-radius:50%;}
.metric-top {display:flex;align-items:center;justify-content:space-between;color:#424242;font-size:11px;letter-spacing:.2px;}
.metric-number {font-size:33px;font-weight:600;letter-spacing:-1.2px;margin-top:9px;line-height:1.18;font-variant-numeric:tabular-nums;}
.metric-number small {font-size:12px;font-weight:400;letter-spacing:0;margin-left:5px;color:#424242;}
.metric-note {font-size:10px;color:#5F6368;margin-top:8px;}
.teal {color:#B4532A;} .coral {color:#B42318;} .amber {color:#8A5A00;} .blue {color:#3C3E90;}
.panel-head {display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px;}
.panel-head h3 {font-size:15px;font-weight:600;letter-spacing:-.3px;padding:0;margin:0;}
.panel-head span {font-size:9px;letter-spacing:1.2px;color:#5F6368;}
.panel-sub {font-size:11px;color:#5F6368;margin:7px 0 5px;line-height:1.7;}
.legend {display:flex;gap:19px;font-size:10px;color:#424242;align-items:center;flex-wrap:wrap;}
.dot {display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;background:#ED6B2C;}
.dot.coral {background:#D7263D;} .dot.blue {background:#6c94d7;} .dot.amber {background:#F2B544;}
.focus-kicker {font-size:9px;letter-spacing:1.8px;color:#B4532A;margin-bottom:13px;}
.focus-title {font-size:21px;letter-spacing:-.7px;font-weight:600;line-height:1.5;margin:8px 0;color:#B4532A;}
.focus-copy {font-size:11px;color:#424242;line-height:1.85;margin-bottom:14px;}
.focus-id {font-size:12px;color:#424242;font-variant-numeric:tabular-nums;margin:12px 0 15px;}
.detail-row {display:flex;justify-content:space-between;gap:15px;padding:9px 0;border-bottom:1px solid #E2E2E766;font-size:11px;}
.detail-row span {color:#424242;} .detail-row b {color:#2A3449;font-weight:500;}
.focus-route {background:#F5F5F7;border:1px solid #E2E2E7;border-radius:7px;padding:13px 12px;margin:16px 0 8px;display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#5F6368;}
.focus-route strong {color:#B4532A;font-size:15px;letter-spacing:.5px;}
.small-note {font-size:10px;line-height:1.7;color:#5F6368;}
.app-table {width:100%;border-collapse:collapse;font-size:11px;margin:9px 0 3px;}
.app-table th {color:#5F6368;font-weight:500;font-size:10px;text-align:left;padding:10px 9px;border-bottom:1px solid #E2E2E7;}
.app-table td {color:#2A3449;padding:12px 9px;border-bottom:1px solid #E2E2E7;white-space:nowrap;}
.app-table td:first-child {color:#2A3449;font-size:11px;font-weight:500;}
.app-table tr:last-child td {border-bottom:0;}
.app-table .pill {padding:3px 6px;font-size:9px;}
.event {display:flex;gap:12px;padding:12px 0;border-bottom:1px solid #E2E2E7;}
.event:last-child {border:0;}
.event-time {font-size:10px;color:#5F6368;min-width:34px;padding-top:2px;font-variant-numeric:tabular-nums;}
.event-title {font-size:11px;color:#2A3449;margin-bottom:5px;}
.event-copy {font-size:10px;color:#424242;line-height:1.6;}
.footer {border-top:1px solid #E2E2E7;padding-top:13px;margin-top:15px;display:flex;justify-content:space-between;font-size:9px;color:#5F6368;letter-spacing:.2px;gap:15px;}
.candidate {padding:19px 18px;border:1px solid #E2E2E7;border-radius:11px;background:#F5F5F7;min-height:231px;}
.candidate.best {border-color:#CFCFD6;background:linear-gradient(130deg,#FFF3EC,#F5F5F7);}
.candidate-rank {color:#424242;font-size:10px;letter-spacing:1.5px;}
.candidate-slot {font-size:21px;font-weight:600;letter-spacing:-.5px;margin:12px 0 16px;}
.candidate-fact {font-size:11px;line-height:2;color:#424242;}
.candidate-fact b {color:#2A3449;font-weight:500;float:right;}
.reason {font-size:10px;line-height:1.7;color:#B4532A;padding-top:12px;border-top:1px solid #E2E2E7;margin-top:10px;}
.steps {display:flex;gap:8px;margin:12px 0 16px;}
.step {flex:1;padding:14px 12px;background:#F5F5F7;border:1px solid #E2E2E7;border-radius:8px;font-size:11px;color:#424242;}
.step.active {background:#FFF3EC;border-color:#CFCFD6;color:#B4532A;}
.step small {display:block;color:#5F6368;margin-top:7px;font-size:9px;}
.section-note {padding:15px 18px;border-left:2px solid #ED6B2C;background:#F5F5F7;border-radius:0 8px 8px 0;font-size:11px;line-height:1.85;color:#424242;margin:12px 0;}
.stack-grid {display:flex;gap:8px;align-items:flex-end;padding:18px 0 8px;}
.stack-column {flex:1;display:flex;flex-direction:column;gap:5px;}
.stack-cell {height:37px;border:1px solid #CFCFD6;background:#E2E2E7;border-radius:4px;text-align:center;padding-top:11px;font-size:9px;color:#2A3449;}
.stack-cell.empty {background:#F5F5F7;border:1px dashed #E2E2E7;color:#5F6368;}
.stack-cell.risk {background:#E2E2E7;border-color:#CFCFD6;color:#B42318;}
.stack-cell.target {background:#FFF3EC;border-color:#ED6B2C;color:#B4532A;}
.stack-label {text-align:center;font-size:9px;color:#424242;margin-top:5px;}
.integration {border:1px solid #E2E2E7;background:#F5F5F7;border-radius:11px;padding:23px;min-height:210px;}
.integration h3 {font-size:18px;padding:8px 0;color:#3C3E90;}
.integration p {font-size:12px;line-height:1.8;color:#424242;}
.integration .num {font-size:10px;letter-spacing:2px;color:#B4532A;}
.export-banner {padding:17px 21px;border:1px solid #E2E2E7;border-radius:10px;background:#F5F5F7;font-size:12px;line-height:1.8;color:#424242;}
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

# Workflow cards retain the same navy / teal visual system.
CSS = CSS.replace('</style>', '''
.st-key-eta_inputs,.st-key-connections {border:1px solid #E2E2E7;border-radius:13px;background:#F5F5F7;padding:20px;margin-top:10px;}
.quadrant-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:8px 0 20px;}
.quadrant{background:linear-gradient(130deg,#F5F5F7,#F5F5F7);border:1px solid #E2E2E7;border-radius:12px;padding:22px;min-height:180px;}
.quadrant.selected{background:linear-gradient(130deg,#FFF3EC,#F5F5F7);border:1px solid #ED6B2C;box-shadow:inset 3px 0 #ED6B2C;}
.quadrant h3{font-size:19px;padding:4px 0 9px;margin:0;color:#2A3449;}
.quadrant p{font-size:12px;line-height:1.9;color:#424242;margin-bottom:14px;}
.quadrant span{font-size:10px;color:#B4532A;}
.cargo-alert{border:1px solid #CFCFD6;border-left:3px solid #F2B544;background:#F5F5F7;border-radius:9px;padding:15px 19px;margin:4px 0;}
.cargo-alert p{font-size:12px;line-height:1.8;color:#2A3449;margin:10px 0 0;}
.phone{max-width:370px;background:linear-gradient(155deg,#FFF3EC,#F5F5F7 55%);border:6px solid #E2E2E7;border-radius:32px;padding:24px;box-shadow:0 25px 70px #2A34491F;margin:16px auto;}
.phone-bar{font-size:10px;color:#424242;display:flex;justify-content:space-between;margin-bottom:36px;}
.phone-title{font-size:25px;color:#2A3449;letter-spacing:-1px;font-weight:650;line-height:1.4;}
.phone p{font-size:12px;color:#424242;line-height:1.8;}
.phone-container{font-size:12px;padding:13px 0;color:#424242;border-bottom:1px solid #E2E2E7;}
.phone-slot{font-size:64px;letter-spacing:-3px;color:#B4532A;padding:14px 0 0;font-weight:650;}
.phone-slot small{font-size:11px;letter-spacing:2px;margin-left:13px;color:#424242;}
.phone-destination{font-size:15px;color:#B4532A;padding:8px 0 23px;}
.phone-route{background:#FFF3EC;border-radius:8px;padding:15px;font-size:11px;color:#424242;margin-bottom:18px;}
.phone-status{background:#ED6B2C;color:#1A1A1A;border-radius:9px;padding:14px 9px;text-align:center;font-size:12px;font-weight:600;margin-top:20px;}
.notice-card{padding:20px;border:1px solid #E2E2E7;border-radius:10px;background:#F5F5F7;margin:10px 0 2px;}
.notice-card span{font-size:10px;color:#424242;}.notice-card h3{font-size:16px;margin:10px 0;padding:0;}.notice-card p{font-size:12px;color:#424242;}
.app-table{display:table;}.st-key-connections .app-table td{white-space:normal;}.candidate{min-height:270px;}
@media(max-width:700px){.quadrant-grid{grid-template-columns:1fr;}.phone{width:100%;}.app-table{display:block;overflow-x:auto;}}
</style>''')

# 대표 사례 흐름 · 3D 범례 · 체크리스트
CSS = CSS.replace('</style>', '''
.case-bar{display:flex;flex-wrap:wrap;gap:6px 22px;align-items:center;padding:12px 16px;border:1px solid #F2B544;border-radius:11px;background:linear-gradient(90deg,#FFF6E0,#F5F5F7 55%);margin:10px 0 12px;}
.case-bar>div{display:flex;flex-direction:column;min-width:96px;}
.case-bar span{font-size:10px;color:#424242;letter-spacing:.3px;}
.case-bar b{font-size:14px;color:#2A3449;font-weight:620;}
.case-bar .case-tag{background:#ED6B2C;color:#1A1A1A;font-weight:750;font-size:11px;padding:4px 9px;border-radius:5px;min-width:auto;}
.checklist{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:2px 0 12px;}
.checklist>i{color:#5F6368;font-style:normal;}
.check{display:flex;align-items:center;gap:8px;padding:7px 11px;border:1px solid #E2E2E7;border-radius:9px;background:#F5F5F7;font-size:12px;color:#2A3449;}
.check span{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;border:1px solid #CFCFD6;font-size:11px;color:#424242;}
.check small{display:block;font-size:10px;color:#5F6368;}
.check.done{border-color:#ED6B2C;}.check.done span{background:#ED6B2C;color:#1A1A1A;border-color:#ED6B2C;}
.check.hold{border-color:#F2B544;}.check.hold span{background:#F2B544;color:#1A1A1A;border-color:#F2B544;}
.legend3d{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:11.5px;color:#2A3449;margin-top:6px;}
.legend3d i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;border:1px solid #E2E2E7;}
.why{border:1px solid #E2E2E7;border-left:3px solid #ED6B2C;background:#F5F5F7;border-radius:9px;padding:11px 13px;font-size:12.5px;line-height:1.75;color:#2A3449;margin:8px 0;}
.why.danger{border-left-color:#D7263D;background:#F5F5F7;}
.why .muted{color:#424242;font-size:11px;}
.opt{border:1px solid #E2E2E7;border-radius:10px;padding:10px 12px;margin:7px 0;background:#F5F5F7;}
.opt.best{border-color:#ED6B2C;}.opt.sel{box-shadow:0 0 0 2px #2A34491F;}
.opt-head{display:flex;gap:8px;align-items:center;font-size:12.5px;}.opt-head span{margin-left:auto;font-family:ui-monospace,monospace;color:#2A3449;}
.opt-what{font-size:12px;color:#2A3449;margin-top:5px;}.opt-why{font-size:11.5px;color:#424242;margin-top:3px;}
.opt-nums{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;color:#424242;margin-top:6px;}.opt-nums b{color:#2A3449;}
.st-key-focus .app-table td{white-space:normal;line-height:1.55;}
.src-card{border:1px solid #E2E2E7;border-left:4px solid var(--src);border-radius:10px;background:#F5F5F7;padding:9px 12px 8px;margin:8px 0;}
.src-head{display:flex;align-items:baseline;gap:8px;margin-bottom:5px;}
.src-head b{color:var(--src);font-size:13px;letter-spacing:.2px;}
.src-head span{color:#424242;font-size:11px;}
.src-head em{margin-left:auto;font-style:normal;font-size:9.5px;color:#5F6368;border:1px solid #E2E2E7;border-radius:4px;padding:1px 6px;}
.src-row{display:flex;justify-content:space-between;gap:12px;font-size:12px;padding:3px 0;border-top:1px solid #E2E2E7;color:#424242;}
.src-row b{color:#2A3449;font-weight:600;text-align:right;}
.src-note{font-size:11px;color:#424242;margin-top:5px;line-height:1.55;}
.src-tag{font-style:normal;font-size:9px;color:var(--src);border:1px solid var(--src);border-radius:4px;padding:0 4px;margin-left:3px;opacity:.9;}
.phone.mini{max-width:260px;padding:16px;border-width:4px;border-radius:24px;margin:6px auto;}
.phone.mini .phone-title{font-size:18px;}
.phone.mini .phone-bar{margin-bottom:14px;}
.focus-row{color:#B4532A!important;}
.app-table .good{color:#B4532A;font-weight:600;}.app-table .bad{color:#B42318;font-weight:600;}
</style>''')

# 처리 순서 3분할 화면(대기 리스트 · 장치장 2D 미리보기)
CSS = CSS.replace('</style>', '''
.wq-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:4px 0 6px}
.wq{border:1px solid rgba(128,128,128,.35);border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.5}
.wq.focus{border:2px solid #ED6B2C}
.wq-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.wq-l{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:6px;background:#2A3449;color:#fff;font-weight:700}
.wq-v{margin-top:4px}.wq-row{display:flex;gap:10px;flex-wrap:wrap;opacity:.85}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px;background:var(--c,#999);border:1px solid rgba(0,0,0,.25)}
.sw.stripe,.yc.stripe{background:repeating-linear-gradient(45deg,var(--c) 0 4px,#fff 4px 6px)}
.sw.dots,.yc.dots{background:radial-gradient(#fff 1.4px,var(--c) 1.6px) 0 0/6px 6px}
.sw.cross,.yc.cross{background:repeating-linear-gradient(0deg,var(--c) 0 4px,#fff 4px 5px),var(--c)}
.sw.plan{background:transparent;border:2px dashed #ED6B2C}.sw.blk{background:transparent;border:2px solid #D7263D}
.opt-why{margin:6px 0 2px 16px;padding:0;font-size:12.5px}.opt-why li{margin-bottom:4px}.opt-why span{opacity:.8}
.opt-nums small{opacity:.7}
.ygrid{display:flex;gap:16px;flex-wrap:wrap}
.yb-name{font-weight:700;font-size:13px;margin-bottom:4px}
.yb-cols{display:flex;gap:4px}
.ys-cells{display:flex;flex-direction:column;gap:3px}
.ys-name{font-size:11px;text-align:center;opacity:.75;margin-top:2px}
.yc{width:36px;height:26px;border-radius:4px;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff;
    background:var(--c);text-shadow:0 0 2px #000,0 0 2px #000}
.yc.empty{background:transparent;border:1px solid rgba(128,128,128,.3)}
.yc.plan{background:transparent;border:2px dashed var(--c);color:inherit;text-shadow:none}
.yc.blk{outline:3px solid #D7263D;outline-offset:-1px}
.ylegend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;margin-top:8px}
</style>''')

# 주황·흰 테마 보정: Streamlit 기본 위젯
CSS = CSS.replace('</style>', '''
.stButton button[kind="primary"],.stFormSubmitButton button[kind="primaryFormSubmit"]{background:#ED6B2C;border-color:#ED6B2C;color:#1A1A1A;}
.stButton button[kind="primary"]:hover{background:#F08550;border-color:#F08550;color:#1A1A1A;}
.stButton button[kind="secondary"]{background:#FFFFFF;color:#2A3449;border-color:#CFCFD6;}
[data-testid="stSidebar"] .stButton button[kind="primary"]{background:#FFF3EC;color:#B4532A;border:1px solid #ED6B2C;box-shadow:inset 3px 0 #ED6B2C;}
[data-testid="stSidebar"] .stButton button[kind="secondary"]{background:transparent;color:#424242;border:0;}
[data-testid="stSidebar"] .stButton button:hover{background:#EEEEEE;color:#2A3449;}
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"]{background:#FFF3EC;color:#B4532A;border-color:#ED6B2C;}
.page-head h1,.panel-head h3{color:#2A3449;}
a{color:#B4532A;}
:focus-visible{outline:2px solid #ED6B2C!important;outline-offset:2px;}
''')
