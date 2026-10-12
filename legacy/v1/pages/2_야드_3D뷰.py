"""4.2 야드 3D 뷰."""
import pandas as pd
import streamlit as st

from core.relocation import blocking_count, count_relocations
from ui.components import C, VESSEL_COLORS, badge, callout, chart, hero, legend, section
from ui.state import current_vessel, display_seq, get_demo, get_params, live
from ui.yard_viz import RISK_COLORS, WG_COLORS, yard_figure

params = get_params()
demo = get_demo()
scn = demo.scenario
L = live()
yard = params["yard"]

hero("야드 3D 뷰", "블록을 돌려보며 재조작 위험 스택을 찾습니다. 박스에 마우스를 올리면 상세 정보가 나옵니다.")

c1, c2, c3 = st.columns([1.3, 1.2, 1])
with c1:
    color_label = st.segmented_control("색 기준", ["재조작 위험", "목적 선박", "중량 그룹"], default="재조작 위험",
                                       key="color_mode")
with c2:
    scope = st.segmented_control("범위", ["선택 선박 블록", "전체 블록"], default="선택 선박 블록", key="yard_scope")
with c3:
    compare = st.toggle("현행 ↔ StowSync 비교", value=True, key="compare")
color_mode = {"재조작 위험": "risk", "목적 선박": "vessel", "중량 그룹": "weight"}[color_label or "재조작 위험"]

if color_mode == "risk":
    legend([("안전", RISK_COLORS["safe"]), ("위에 방해 박스 있음", RISK_COLORS["warn"]),
            ("재조작 대상(아래 박스를 막음)", RISK_COLORS["danger"]), ("롤오버(선적 안 함)", RISK_COLORS["rolled"]),
            ("방금 장치한 박스", RISK_COLORS["user"])])
elif color_mode == "vessel":
    legend([(v.name, VESSEL_COLORS[i]) for i, v in enumerate(scn.vessels)])
else:
    legend([("가벼움", WG_COLORS[0]), ("중간", WG_COLORS[1]), ("무거움", WG_COLORS[2])])

info = L["boxes"].set_index("cntr_no")
if L["user_boxes"]:
    ub = pd.DataFrame(L["user_boxes"]).set_index("cntr_no")
    info = pd.concat([info, ub[[c for c in ub.columns if c in info.columns]]])
seq = display_seq(L)
users = {u["cntr_no"] for u in L["user_boxes"]}
vsel = current_vessel()
vessels = scn.vessels if scope == "전체 블록" else [vsel]


def blocks_for(skey):
    return [{"name": v.block, "area": L["areas"][v.vessel_id][skey], "vessel_idx": scn.vessels.index(v)}
            for v in vessels]


def stats(skey):
    tot_rel, tot_risk = 0, 0
    for v in vessels:
        area = L["areas"][v.vessel_id][skey]
        tot_rel += count_relocations(area, seq, yard["max_tiers"])
        tot_risk += sum(blocking_count(s, seq) for s in area.values())
    return tot_rel, tot_risk


h = 560 if not compare else 520
if compare:
    a, b = st.columns(2, gap="small")
    for col, skey, title, kind in [(a, "current", "현행 배치", "muted"), (b, "B", "StowSync 배치", "primary")]:
        with col:
            rel, risk = stats(skey)
            st.markdown(f'<div class="ss-section"><h3>{title}</h3>{badge(f"재조작 {rel}회", kind)}'
                        f'{badge(f"위험 박스 {risk}개", "danger" if skey == "current" else "safe")}</div>',
                        unsafe_allow_html=True)
            chart(yard_figure(blocks_for(skey), info, seq, color_mode, users, yard["max_tiers"],
                              yard["rows_per_bay"], height=h), key=f"y3d_{skey}")
else:
    rel, risk = stats("B")
    st.markdown(f'<div class="ss-section"><h3>StowSync 배치</h3>{badge(f"재조작 {rel}회")}'
                f'{badge(f"위험 박스 {risk}개", "safe")}</div>', unsafe_allow_html=True)
    chart(yard_figure(blocks_for("B"), info, seq, color_mode, users, yard["max_tiers"], yard["rows_per_bay"],
                      height=640), key="y3d_single")

if users:
    callout(f"선적위치 예측에서 장치한 박스 <b>{len(users)}개</b>가 흰색으로 표시됩니다: "
            + ", ".join(f"<code>{u}</code>" for u in sorted(users)))
st.caption("드래그로 회전 · 스크롤로 확대 · 블록 = 선박별 전용 장치 구역(가정) · 20ft 박스는 슬롯 절반 길이로 표시")
