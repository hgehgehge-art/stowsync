from html import escape
from pathlib import Path
import streamlit as st

CSS = """
<style>
:root { --ink:#e6edf5; --muted:#91a2b8; --line:#26354a; --teal:#59e0ce; }
html,body,.stApp {font-family: -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;}
.stApp {background:radial-gradient(ellipse at 82% 0%,#15304066 0%,transparent 36%),#09121f;}
header[data-testid="stHeader"] {background:transparent; height:2.1rem;}
[data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {display:none;}
[data-testid="stSidebar"][aria-expanded="false"] {width:0!important;min-width:0!important;max-width:0!important;}
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
.footer {border-top:1px solid #253549;padding-top:13px;margin-top:15px;display:flex;justify-content:space-between;font-size:11px;color:#8ea3b6;letter-spacing:.2px;gap:15px;}
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
    """tag(영문 장식 라벨)는 화면에 표시하지 않습니다. 호출부 호환을 위해 인자만 남깁니다."""
    html(f'<div class="panel-head"><h3>{escape(title)}</h3></div>' + (f'<div class="panel-sub">{escape(subtitle)}</div>' if subtitle else ''))

def metric(label, value, unit="", note="", color="", code=""):
    html(f'<div class="metric-card"><div class="metric-top">{escape(label)}</div><div class="metric-number {color}">{escape(str(value))}<small>{escape(unit)}</small></div><div class="metric-note">{escape(note)}</div></div>')

def table(headers, rows):
    # Cells are assembled by trusted UI functions; caller escapes user-provided text.
    html('<table class="app-table"><thead><tr>'+''.join(f'<th>{escape(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{c}</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>')

def tm(seconds):
    m = int(seconds)//60 + 9*60
    return f'{m//60:02d}:{m%60:02d}'

def mins(seconds): return '—' if seconds is None else f'{seconds/60:.1f}'

DATA_NOTE = '모든 데이터는 가상 값으로 생성한 시뮬레이션 결과이며, 실제 시스템과 연결되어 있지 않습니다.'

def footer():
    html(f'<div class="footer"><span>StowSync · 부산항 수출 FCL 하차 순서·적치 위치 의사결정 지원</span><span>{DATA_NOTE}</span></div>')

def allcone(text):
    """올컨e 앱 연동 표시: 주황 박스."""
    return f'<span class="allcone">{escape(text)}</span>'

# Workflow cards retain the same navy / teal visual system.
CSS = CSS.replace('</style>', '''
.st-key-eta_inputs,.st-key-connections {border:1px solid #26354a;border-radius:13px;background:#101d2d;padding:20px;margin-top:10px;}
.quadrant-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:8px 0 20px;}
.quadrant{background:linear-gradient(130deg,#132538,#101d2d);border:1px solid #2e4259;border-radius:12px;padding:22px;min-height:180px;}
.quadrant.selected{background:linear-gradient(130deg,#18423f,#122933);border:1px solid #63dcca;box-shadow:inset 3px 0 #63dcca;}
.quadrant h3{font-size:19px;padding:4px 0 9px;margin:0;color:#e3f1f6;}
.quadrant p{font-size:12px;line-height:1.9;color:#a1b7ca;margin-bottom:14px;}
.quadrant span{font-size:10px;color:#74d6c7;}
.cargo-alert{border:1px solid #775142;border-left:3px solid #f2b775;background:#2d2726;border-radius:9px;padding:15px 19px;margin:4px 0;}
.cargo-alert p{font-size:12px;line-height:1.8;color:#d8c7b9;margin:10px 0 0;}
.phone{max-width:370px;background:linear-gradient(155deg,#143734,#0f1e2e 55%);border:6px solid #2b3c4c;border-radius:32px;padding:24px;box-shadow:0 25px 70px #02091180;margin:16px auto;}
.phone-bar{font-size:10px;color:#8eb5b8;display:flex;justify-content:space-between;margin-bottom:36px;}
.phone-title{font-size:25px;color:#f0f8fb;letter-spacing:-1px;font-weight:650;line-height:1.4;}
.phone p{font-size:12px;color:#a3b9cb;line-height:1.8;}
.phone-container{font-size:12px;padding:13px 0;color:#9bcac5;border-bottom:1px solid #35545b;}
.phone-slot{font-size:64px;letter-spacing:-3px;color:#78e8d4;padding:14px 0 0;font-weight:650;}
.phone-slot small{font-size:11px;letter-spacing:2px;margin-left:13px;color:#8ba7b7;}
.phone-destination{font-size:15px;color:#e2f1f4;padding:8px 0 23px;}
.phone-route{background:#17343b;border-radius:8px;padding:15px;font-size:11px;color:#a8d2d0;margin-bottom:18px;}
.phone-status{background:#63dbc9;color:#102a29;border-radius:9px;padding:14px 9px;text-align:center;font-size:12px;font-weight:600;margin-top:20px;}
.notice-card{padding:20px;border:1px solid #2b4257;border-radius:10px;background:#102333;margin:10px 0 2px;}
.notice-card span{font-size:10px;color:#84a6bb;}.notice-card h3{font-size:16px;margin:10px 0;padding:0;}.notice-card p{font-size:12px;color:#b0c7d7;}
.app-table{display:table;}.st-key-connections .app-table td{white-space:normal;}.candidate{min-height:270px;}
@media(max-width:700px){.quadrant-grid{grid-template-columns:1fr;}.phone{width:100%;}.app-table{display:block;overflow-x:auto;}}
</style>''')

# 대표 시나리오 · 3D 범례 · 체크리스트
CSS = CSS.replace('</style>', '''
.case-bar{display:flex;flex-wrap:wrap;gap:6px 22px;align-items:center;padding:12px 16px;border:1px solid #6b5a1f;border-radius:11px;background:linear-gradient(90deg,#2a2610,#111e2d 55%);margin:10px 0 12px;}
.case-bar>div{display:flex;flex-direction:column;min-width:96px;}
.case-bar span{font-size:10px;color:#9fb0c3;letter-spacing:.3px;}
.case-bar b{font-size:14px;color:#f3f6fa;font-weight:620;}
.case-bar .case-tag{background:#FFD12E;color:#1b1600;font-weight:750;font-size:11px;padding:4px 9px;border-radius:5px;min-width:auto;}
.checklist{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:2px 0 12px;}
.checklist>i{color:#46607a;font-style:normal;}
.check{display:flex;align-items:center;gap:8px;padding:7px 11px;border:1px solid #2a3c52;border-radius:9px;background:#101d2d;font-size:12px;color:#c9d6e3;}
.check span{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;border:1px solid #47607a;font-size:11px;color:#8ea5bb;}
.check small{display:block;font-size:10px;color:#7f97ad;}
.check.done{border-color:#2f6b5f;}.check.done span{background:#59e0ce;color:#08231f;border-color:#59e0ce;}
.check.hold{border-color:#7a6230;}.check.hold span{background:#e6b877;color:#2a1d05;border-color:#e6b877;}
.legend3d{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:11.5px;color:#c4d2df;margin-top:6px;}
.legend3d i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;border:1px solid #05080d;}
.why{border:1px solid #2b4a5e;border-left:3px solid #59e0ce;background:#0f2130;border-radius:9px;padding:11px 13px;font-size:12.5px;line-height:1.75;color:#dbe6ef;margin:8px 0;}
.why.danger{border-left-color:#E0474C;background:#2a1520;}
.why .muted{color:#8ea3b6;font-size:11px;}
.opt{border:1px solid #2a3c52;border-radius:10px;padding:10px 12px;margin:7px 0;background:#0f1b2a;}
.opt.best{border-color:#2f6b5f;}.opt.sel{box-shadow:0 0 0 2px #3DDC9766;}
.opt-head{display:flex;gap:8px;align-items:center;font-size:12.5px;}.opt-head span{margin-left:auto;font-family:ui-monospace,monospace;color:#e9f1f8;}
.opt-what{font-size:12px;color:#cfe0ee;margin-top:5px;}.opt-why{font-size:11.5px;color:#93a9bd;margin-top:3px;}
.opt-nums{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;color:#9fb3c6;margin-top:6px;}.opt-nums b{color:#f1f6fb;}
.st-key-focus .app-table td{white-space:normal;line-height:1.55;}
.src-card{border:1px solid #2a3c52;border-left:4px solid var(--src);border-radius:10px;background:#0f1b2a;padding:9px 12px 8px;margin:8px 0;}
.src-head{display:flex;align-items:baseline;gap:8px;margin-bottom:5px;}
.src-head b{color:var(--src);font-size:13px;letter-spacing:.2px;}
.src-head span{color:#9fb3c6;font-size:11px;}
.src-head em{margin-left:auto;font-style:normal;font-size:9.5px;color:#7f97ad;border:1px solid #33475d;border-radius:4px;padding:1px 6px;}
.src-row{display:flex;justify-content:space-between;gap:12px;font-size:12px;padding:3px 0;border-top:1px solid #1f2f42;color:#9fb3c6;}
.src-row b{color:#eaf2f9;font-weight:600;text-align:right;}
.src-note{font-size:11px;color:#8ea3b6;margin-top:5px;line-height:1.55;}
.src-tag{font-style:normal;font-size:9px;color:var(--src);border:1px solid var(--src);border-radius:4px;padding:0 4px;margin-left:3px;opacity:.9;}
.phone.mini{max-width:260px;padding:16px;border-width:4px;border-radius:24px;margin:6px auto;}
.phone.mini .phone-title{font-size:18px;}
.phone.mini .phone-bar{margin-bottom:14px;}
.focus-row{color:#FFD12E!important;}
.app-table .good{color:#59e0ce;font-weight:600;}.app-table .bad{color:#ee99a4;font-weight:600;}
</style>''')

# 처리 순서 3분할 화면(대기 리스트 · 장치장 2D 미리보기)
CSS = CSS.replace('</style>', '''
.wq-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:4px 0 6px}
.wq{border:1px solid rgba(128,128,128,.35);border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.5}
.wq.focus{border:2px solid #FFD12E}
.wq-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.wq-l{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:6px;background:#26354a;color:#fff;font-weight:700}
.wq-v{margin-top:4px}.wq-row{display:flex;gap:10px;flex-wrap:wrap;opacity:.85}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px;background:var(--c,#999);border:1px solid rgba(0,0,0,.25)}
.sw.stripe,.yc.stripe{background:repeating-linear-gradient(45deg,var(--c) 0 4px,#fff 4px 6px)}
.sw.dots,.yc.dots{background:radial-gradient(#fff 1.4px,var(--c) 1.6px) 0 0/6px 6px}
.sw.cross,.yc.cross{background:repeating-linear-gradient(0deg,var(--c) 0 4px,#fff 4px 5px),var(--c)}
.sw.plan{background:transparent;border:2px dashed #FFB547}.sw.blk{background:transparent;border:2px solid #D7263D}
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

# 올컨e 연동 강조(주황 박스) · 통합 관제 배치 화면
CSS = CSS.replace('</style>', '''
.allcone{display:inline-flex;align-items:center;gap:6px;border:1.5px solid #FF8A3D;background:#3a210f;color:#FFB27A;border-radius:6px;padding:3px 9px;font-weight:650;font-size:12px;white-space:nowrap;}
.allcone-box{border:1.5px solid #FF8A3D;background:linear-gradient(90deg,#3a210f,#1a1a1f 70%);border-radius:10px;padding:10px 14px;color:#ffd9bd;font-size:12.5px;line-height:1.7;margin:6px 0;}
.allcone-box b{color:#FFB27A;}
.source-strip .src-allcone{border:1.5px solid #FF8A3D;background:#3a210f;border-radius:7px;padding:5px 10px;}
.source-strip .src-allcone b{color:#FFB27A;}.source-strip .src-allcone em{color:#e9a477;}
.src-card.allcone-card{border:1.5px solid #FF8A3D;border-left:4px solid #FF8A3D;background:#24170f;}
.phone{border-color:#FF8A3D!important;}
.phone-brand{display:inline-block;background:#FF8A3D;color:#2a1405;font-weight:800;font-size:11px;border-radius:5px;padding:2px 8px;margin-bottom:10px;}
.cand-opt{border:1px solid #2e4159;border-radius:11px;background:#142236;padding:14px 16px;height:100%;}
.cand-opt.sel{border:2px solid #59e0ce;box-shadow:0 0 0 3px #59e0ce22;}
.cand-opt .cand-head{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#9fb3c6;}
.cand-opt .cand-slot{font-size:22px;font-weight:650;color:#eef5fb;margin:6px 0 10px;}
.cand-opt .cand-row{display:flex;justify-content:space-between;font-size:12px;color:#adbfce;line-height:1.95;}
.cand-opt .cand-row b{color:#e7eff8;font-weight:550;}
.cand-opt .cand-why{font-size:11.5px;color:#93a9bd;margin-top:6px;}
.mini-stack{display:flex;flex-direction:column-reverse;gap:3px;margin-top:10px;}
.mini-stack .ms{height:24px;border-radius:4px;display:flex;align-items:center;justify-content:space-between;padding:0 8px;font-size:11px;background:#203e5c;border:1px solid #325474;color:#d6e4ef;}
.mini-stack .ms.new{background:#FFD12E;color:#1b1600;border-color:#FFD12E;font-weight:700;}
.mini-stack .ms.risk{background:#4f3346;border-color:#ad6079;color:#ffc2cd;}
.mini-stack .ms.empty{background:transparent;border:1px dashed #2b4158;color:#60768c;}
.integration.allcone-int{border:1.5px solid #FF8A3D;background:linear-gradient(160deg,#3a210f,#121d2b 70%);}.integration.allcone-int h3{color:#FFB27A;}
.mini-cap{font-size:10.5px;color:#7f97ad;margin-top:4px;}
.mini-flag{font-size:11.5px;margin-top:6px;}.mini-flag.ok{color:#59e0ce;}.mini-flag.bad{color:#ee99a4;}
</style>''')

# 대표 시나리오 · 단계 표시
CSS = CSS.replace('</style>', '''
.story-intro{font-size:13.5px;color:#d6e4ef;line-height:1.7;border-left:3px solid #59e0ce;padding:4px 0 4px 12px;}
.story-intro b{color:#7eecdd;font-weight:600;}
.stepper{display:flex;align-items:stretch;gap:6px;flex-wrap:wrap;margin:6px 0 4px;}
.stepper .arr{color:#46607a;align-self:center;font-size:18px;}
.phase{flex:1;min-width:190px;border:1px solid #26354a;border-radius:10px;background:#0f1b2a;padding:8px 10px;}
.phase.on{border-color:#59e0ce;background:#10272b;}
.phase-name{font-size:11.5px;color:#9fb3c6;font-weight:600;margin-bottom:6px;}
.phase.on .phase-name{color:#7eecdd;}
.phase-steps{display:flex;flex-wrap:wrap;gap:5px;}
.stp{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:#8ea5bb;border:1px solid #2a3c52;border-radius:14px;padding:2px 9px 2px 3px;}
.stp i{font-style:normal;display:grid;place-items:center;width:18px;height:18px;border-radius:50%;background:#1b2c40;font-size:10.5px;}
.stp.done{color:#bfeee6;border-color:#2f6b5f;}.stp.done i{background:#59e0ce;color:#08231f;}
.stp.cur{color:#08231f;background:#FFD12E;border-color:#FFD12E;font-weight:700;}.stp.cur i{background:#1b1600;color:#FFD12E;}
.stage-help{font-size:12.5px;color:#c9d6e3;margin:4px 0 2px;}
.stage-help b{color:#FFD12E;}
</style>''')

# 대표 시나리오 · 단계 버튼 · 대안 카드 · 클릭형 장치장 · 호버/선택 상태
CSS = CSS.replace('</style>', '''
[class*="st-key-scnstep-"] button{min-height:44px;font-size:13px;border-radius:9px;transition:background .15s,border-color .15s}
[class*="st-key-scnstep-done"] button{border-color:#2f6b5f;color:#9ff0e2}
[class*="st-key-scnstep-cur"] button{background:#173737;border:2px solid #59e0ce;color:#e9fffb;font-weight:700}
[class*="st-key-scnstep-"] button:hover:not(:disabled){background:#1b2c40}
[class*="st-key-scnstep-"] button:disabled{opacity:.45}
.scn-guide{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:6px 0 12px}
.scn-guide>div{border:1px solid #26354a;border-radius:10px;padding:10px 14px;background:#101d2d}
.scn-guide span{display:block;font-size:11px;color:#8fa3b9;margin-bottom:3px}.scn-guide b{font-size:13.5px;color:#e6edf5;font-weight:600}
[class*="st-key-altcard-"]{border:1px solid #2a3c52;border-radius:12px;padding:12px 14px;background:#0f1b2a;transition:background .15s,border-color .15s,box-shadow .15s}
[class*="st-key-altcard-"]:hover{background:#15243a;border-color:#3d536e}
[class*="st-key-altcard-sel"]{border:2px solid #59e0ce;background:#12302f;box-shadow:0 0 0 3px rgba(89,224,206,.15)}
[class*="st-key-altcard-sel"]:hover{background:#163735}
.alt-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:14px}.alt-pos{font-size:12px;color:#9fb3c6;margin:6px 0}
.alt-big{font-size:28px;font-weight:700;color:#eaf3fb}.alt-big small{font-size:13px;margin-left:3px;color:#9fb3c6}
.alt-big span{display:block;font-size:12px;font-weight:500;color:#59e0ce}
.opt,.cand-opt,.wq,.src-card,.integration,.quadrant{transition:background .15s,border-color .15s}
.opt:hover,.cand-opt:hover,.wq:hover,.quadrant:hover{background:#15243a;border-color:#3d536e}
.cand-opt.sel,.opt.sel{box-shadow:0 0 0 2px rgba(89,224,206,.45)}
.app-table tbody tr{transition:background .12s}.app-table tbody tr:hover{background:rgba(255,255,255,.045)}
[class*="st-key-ycell-"] button{min-height:30px;height:30px;padding:0;font-size:12px;font-weight:700;border-radius:5px;color:#fff;transition:filter .12s,box-shadow .12s}
[class*="st-key-ycell-v0"] button{background:#3f74c9;border-color:#5b8de0}
[class*="st-key-ycell-v1"] button{background:repeating-linear-gradient(45deg,#7d63c9 0 5px,#9b85e0 5px 8px);border-color:#a78bfa}
[class*="st-key-ycell-v2"] button{background:#2f8f80;border-color:#59e0ce}
[class*="st-key-ycell-blk"] button{background:#b8394a;border-color:#ff8a98}
[class*="st-key-ycell-new"] button{background:transparent;border:2px dashed #FFB547;color:#FFD12E}
[class*="st-key-ycell-sel"] button{background:#FFD12E;border:2px solid #fff;color:#1b1600;box-shadow:0 0 0 3px rgba(255,209,46,.45)}
[class*="st-key-ycell-"] button:hover{filter:brightness(1.18);box-shadow:0 0 0 2px rgba(255,255,255,.25)}
.ycell-empty{height:30px;border:1px solid rgba(128,128,128,.25);border-radius:5px;margin-bottom:8px;display:grid;place-items:center;color:#FFD12E;font-size:18px}
.ycell-empty.arrow{border-color:#FFD12E;animation:scnbob 1s ease-in-out infinite}
.yarrow{height:18px;text-align:center;color:#FFD12E;font-size:18px;line-height:18px}.yarrow.on{animation:scnbob 1s ease-in-out infinite}
@keyframes scnbob{0%,100%{transform:translateY(0)}50%{transform:translateY(3px)}}
.ycell-name{font-size:11px;text-align:center;color:#8fa3b9}
.sw.v0{background:#3f74c9}.sw.v1{background:#9b85e0}.sw.newk{background:transparent;border:2px dashed #FFB547}.sw.selk{background:#FFD12E}
.pgrid{display:flex;gap:18px;flex-wrap:wrap}.pb-name{font-weight:700;font-size:13px;margin-bottom:4px}.pb-cols{display:flex;gap:4px}
.ps-cells{display:flex;flex-direction:column;gap:3px}.ps-name{font-size:11px;text-align:center;opacity:.75;margin-top:2px}
.pc{width:38px;height:26px;border-radius:4px;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff;transition:all .3s}
.pc.v0{background:#3f74c9}.pc.v1{background:#8a72d6}.pc.v2{background:#2f8f80}.pc.empty{border:1px solid rgba(128,128,128,.25)}
.pc.new{outline:2px dashed #FFB547;outline-offset:-2px}.pc.hl{background:#FFD12E;color:#1b1600;box-shadow:0 0 0 3px rgba(255,209,46,.5)}
.sim-now{margin-top:10px;font-size:13px;color:#cfe0ee}
.done-banner{border:1px solid #2f6b5f;background:#12302f;border-radius:11px;padding:12px 16px;font-size:17px;font-weight:700;color:#9ff0e2;margin:4px 0 10px}
.done-banner span{display:block;font-size:12.5px;font-weight:500;color:#b8d8d4;margin-top:3px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:8px 0}.kpis>div{border:1px solid #26354a;border-radius:9px;padding:8px 10px}
.kpis span{display:block;font-size:11px;color:#8fa3b9}.kpis b{font-size:20px}.kpis .hl{border-color:#59e0ce}.kpis .hl b{color:#59e0ce}
@media(max-width:900px){.scn-guide{grid-template-columns:1fr}}
</style>''')
