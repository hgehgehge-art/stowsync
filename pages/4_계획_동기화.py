"""4.4 계획 동기화 보드."""
from datetime import datetime, timedelta, timezone

import numpy as np
import streamlit as st

from core.events import EVENT_LABEL, apply_live_event
from core.relocation import INF, count_relocations
from core.stacking import copy_area, premarshal
from ui.components import C, badge, callout, hero, risk_badge, section
from ui.state import current_vessel, get_demo, get_params, get_predictor, live
from ui.yard_viz import bay_grid_html

params = get_params()
demo = get_demo()
scn = demo.scenario
L = live()
v = current_vessel()
tiers = params["yard"]["max_tiers"]
mpr = params["ops"]["minutes_per_relocation"]

hero("계획 동기화 보드", "선사 · 본선 · 야드가 같은 계획 버전을 봅니다. 계획이 바뀌면 야드 영향과 사전 재정렬 제안이 즉시 계산됩니다.")

ROLES3 = ["선사 플래너", "본선 플래너", "야드 플래너"]
ROLE_DESC = {"선사 플래너": "적재 계획(Stowage) 작성", "본선 플래너": "본선 작업 순서·크레인 배정",
             "야드 플래너": "야드 장치·반출 순서"}


def seq_pct(vid):
    b = L["boxes"]
    ld = b[(b.vessel_id == vid) & ~b.rolled]
    s = dict(zip(ld.cntr_no, ld.true_pct))
    s.update({u["cntr_no"]: u["pred_pct"] for u in L["user_boxes"] if u["vessel_id"] == vid})
    return s


# ── 이벤트 실행 ──
def fire(kind):
    rng = np.random.default_rng(params["seed"] * 1000 + L["event_count"])
    now = datetime.fromisoformat(params["base_date"]).replace(
        hour=datetime.now(timezone(timedelta(hours=9))).hour, minute=datetime.now(timezone(timedelta(hours=9))).minute)
    res = apply_live_event(kind, L, v, params, get_predictor(), rng, now)
    L["event_count"] += 1
    L["events"].append(res["event"])
    L["last_event"] = res
    L["versions"]["선사 플래너"] += 1
    L["acks"] = {"선사 플래너": True, "본선 플래너": False, "야드 플래너": False}
    # 사전 재정렬 제안 (StowSync 배치 사본에서 계산 → 승인 시 실제 반영)
    moves = premarshal(copy_area(L["areas"][v.vessel_id]["B"]), L["preds"], tiers, budget=8)
    L["suggestions"] = [{**m, "vessel_id": v.vessel_id, "status": "대기"} for m in moves]
    st.session_state["_toasts"] = kind


def ack(role):
    L["acks"][role] = True
    L["versions"][role] = L["versions"]["선사 플래너"]


def decide(i, ok):
    sgg = L["suggestions"][i]
    if ok:
        area = L["areas"][sgg["vessel_id"]]["B"]
        src = area[sgg["bay"]][sgg["from_stack"]]
        dst = area[sgg["to_bay"]][sgg["to_stack"]]
        if src and src[-1] == sgg["box"] and len(dst) < tiers:
            dst.append(src.pop())
            sgg["status"] = "승인"
            L.setdefault("approved", {}).setdefault(sgg["vessel_id"], 0)
            L["approved"][sgg["vessel_id"]] += 1
        else:
            sgg["status"] = "무효(배치 변경됨)"
    else:
        sgg["status"] = "거절"


# ── 상단: 역할별 3열 칸반 ──
section("역할별 계획 버전", f"{v.name} · 기준 버전 v{L['versions']['선사 플래너']}")
cols = st.columns(3, gap="medium")
pending_any = not all(L["acks"].values())
for col, role in zip(cols, ROLES3):
    ver, ok = L["versions"][role], L["acks"][role]
    status = badge("✓ 확인 완료", "safe") if ok else badge("! 확인 대기", "danger")
    last = L["events"][-1] if L["events"] else None
    with col:
        st.markdown(
            f'<div class="ss-card ss-col {"" if ok else "ss-pulse"}"><h4>{role}{status}</h4>'
            f'<div class="ver">v{ver}</div>'
            f'<div class="row"><span>역할</span><b>{ROLE_DESC[role]}</b></div>'
            f'<div class="row"><span>최근 변경</span><b>{(last.label + " " + last.time.strftime("%H:%M")) if last else "—"}</b></div>'
            f'<div class="row"><span>동기화</span><b>{"최신" if ver == L["versions"]["선사 플래너"] else "이전 버전"}</b></div></div>',
            unsafe_allow_html=True)
        if not ok:
            st.button(f"v{L['versions']['선사 플래너']} 확인", key=f"ack_{role}", on_click=ack, args=(role,),
                      use_container_width=True)

# ── 이벤트 버튼 ──
section("계획 변경 이벤트", "버튼을 누르면 선택 선박에 이벤트가 발생합니다")
b1, b2, b3 = st.columns(3)
b1.button("⛔  롤오버 발생", on_click=fire, args=("rollover",), use_container_width=True, type="primary")
b2.button("➕  막판 부킹 추가", on_click=fire, args=("add",), use_container_width=True)
b3.button("⚖️  VGM 중량 수정", on_click=fire, args=("weight_fix",), use_container_width=True)

if st.session_state.pop("_toasts", None):
    res = L["last_event"]
    e = res["event"]
    d_cur = res["after"]["current"] - res["before"]["current"]
    st.toast(f"**선사 플래너** · {v.name} {e.note} — 계획 v{L['versions']['선사 플래너']} 배포", icon="📦")
    st.toast(f"**본선 플래너** · 재조작 {d_cur:+d}회 예상 · 크레인 대기 {d_cur * mpr:+.0f}분", icon="🏗️")
    st.toast(f"**야드 플래너** · 영향 박스 {len(res['affected_B'])}개 · 사전 재정렬 제안 {len(L['suggestions'])}건",
             icon="🚧")

res = L.get("last_event")
if res and res["event"].vessel_id == v.vessel_id:
    e = res["event"]
    cur_d = res["after"]["current"] - res["before"]["current"]
    b_d = res["after"]["B"] - res["before"]["B"]
    callout(f'<b>{e.time:%H:%M} {v.name} {e.note}</b> → 영향 박스 <b>{len(res["affected_B"])}</b>개 · '
            f'재조작 증가: 현행 <b>{cur_d:+d}</b>회 / StowSync <b>{b_d:+d}</b>회 (재정렬 전)', "danger")
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        section("영향받는 박스", "빨강 깜빡임 = 변경 대상 · 주황 = 그 아래 깔린 박스 (StowSync 배치)")
        area = L["areas"][v.vessel_id]["B"]
        hit = set(e.affected_cntrs)
        under = set(res["affected_B"])
        bays = [b for b, stacks in area.items() if any(x in hit for s in stacks for x in s)]
        grids = "".join(bay_grid_html(area, b, v.block, tiers, hit, under) for b in bays[:8])
        st.markdown(f'<div class="ss-card"><div class="ss-bays">{grids or "현재 배치에 해당 박스가 없습니다."}</div></div>',
                    unsafe_allow_html=True)
        lst = L["boxes"].set_index("cntr_no")
        rows = "".join(
            f"<tr><td><code>{c}</code></td><td>{lst.at[c, 'pod']}</td><td class='num'>{lst.at[c, 'vgm_weight']:.1f}t</td>"
            f"<td>{int(lst.at[c, 'size'])}ft</td><td>{badge(e.label, 'danger' if e.type == 'rollover' else 'warn')}</td></tr>"
            for c in e.affected_cntrs[:12] if c in lst.index)
        st.markdown('<div class="ss-card" style="margin-top:10px"><table class="ss-table"><thead><tr><th>컨테이너</th>'
                    '<th>양하항</th><th class="num">VGM</th><th>규격</th><th>변경</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
    with right:
        section("사전 재정렬 제안", "유휴 시간에 미리 옮기면 선적 때 재조작이 줄어듭니다")
        sugg = [s for s in L["suggestions"] if s["vessel_id"] == v.vessel_id]
        if not sugg:
            st.markdown('<div class="ss-card">제안할 재정렬이 없습니다 — 현재 배치가 이미 정렬되어 있습니다.</div>',
                        unsafe_allow_html=True)
        for i, s in enumerate(L["suggestions"]):
            if s["vessel_id"] != v.vessel_id:
                continue
            frm = f"{v.block}-{s['bay'] + 1:02d}-{s['from_stack'] + 1}"
            to = f"{v.block}-{s['to_bay'] + 1:02d}-{s['to_stack'] + 1}"
            c1, c2, c3 = st.columns([2.6, 1, 1])
            kind = {"대기": "primary", "승인": "safe", "거절": "muted"}.get(s["status"], "warn")
            c1.markdown(f'<div style="padding-top:6px;font-size:.85rem"><code>{s["box"]}</code> '
                        f'<span style="color:#8BA3C7">{frm} → {to}</span> {badge(s["status"], kind)}</div>',
                        unsafe_allow_html=True)
            if s["status"] == "대기":
                c2.button("승인", key=f"ap_{i}", on_click=decide, args=(i, True), use_container_width=True)
                c3.button("거절", key=f"rj_{i}", on_click=decide, args=(i, False), use_container_width=True)
        seq = seq_pct(v.vessel_id)
        now_b = count_relocations(L["areas"][v.vessel_id]["B"], seq, tiers)
        st.markdown(f'<div class="ss-card" style="margin-top:10px">승인 반영 후 StowSync 예상 재조작 '
                    f'<b style="font-family:JetBrains Mono;color:{C["primary"]};font-size:1.3rem">{now_b}</b>회</div>',
                    unsafe_allow_html=True)
else:
    callout("위 버튼으로 계획 변경을 발생시켜 보세요. 영향받는 박스가 깜빡이고, 역할별 알림과 사전 재정렬 제안이 뜹니다.")

# ── 재조작 리스크 로드시트 ──
section("재조작 리스크 로드시트", "항공 로드시트처럼 한 장으로 요약")
rows = []
for vv in scn.vessels:
    b = L["boxes"]
    mine = b[b.vessel_id == vv.vessel_id]
    ld = mine[~mine.rolled]
    seq = seq_pct(vv.vessel_id)
    rc = count_relocations(L["areas"][vv.vessel_id]["current"], seq, tiers)
    rb = count_relocations(L["areas"][vv.vessel_id]["B"], seq, tiers)
    pm = demo.runs[(vv.vessel_id, "B")]["premarshal"] + L.get("approved", {}).get(vv.vessel_id, 0)
    evs = [e for e in scn.events + L["events"] if e.vessel_id == vv.vessel_id]
    last = max(evs, key=lambda e: e.time) if evs else None
    rate = rb / max(len(ld), 1)
    red = (rc - rb) / rc * 100 if rc else 0
    rows.append(
        f"<tr><td><b>{vv.name}</b><br><span style='color:#8BA3C7;font-size:.74rem'>블록 {vv.block} · ETA {vv.eta:%H:%M}</span></td>"
        f"<td class='num'>{len(ld)}</td><td class='num'>{int(ld['size'].sum() / 20)}</td><td class='num'>{int(mine.rolled.sum())}</td>"
        f"<td class='num'>{rc}</td><td class='num' style='color:{C['primary']}'>{rb}</td>"
        f"<td class='num' style='color:{C['safe']}'>▼{red:.0f}%</td><td class='num'>{pm}</td>"
        f"<td class='num'>{rb * mpr:.0f}분</td><td>{risk_badge(rate)}</td>"
        f"<td class='num'>v{L['versions']['선사 플래너'] if vv.vessel_id == v.vessel_id else 12}</td>"
        f"<td style='font-size:.78rem'>{(last.label + ' ' + last.time.strftime('%m-%d %H:%M')) if last else '—'}</td></tr>")
st.markdown(
    '<div class="ss-card"><table class="ss-table"><thead><tr><th>선박</th><th class="num">선적 박스</th><th class="num">TEU</th>'
    '<th class="num">롤오버</th><th class="num">재조작(현행)</th><th class="num">재조작(StowSync)</th><th class="num">감소</th>'
    '<th class="num">사전재정렬</th><th class="num">크레인 대기</th><th>위험도</th><th class="num">계획</th><th>최근 변경</th>'
    f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)
st.caption(f"재조작 1회 = 크레인 {mpr}분 지연(가정) · 위험도: 박스당 재조작 0.25 미만 낮음 / 0.5 미만 중간 / 이상 높음")
