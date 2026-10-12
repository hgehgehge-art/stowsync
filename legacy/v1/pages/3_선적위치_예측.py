"""4.3 선적위치 예측 — 반입 컨테이너 1개의 예상 선적 순서와 추천 슬롯."""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core.stacking import score_stacks
from ui.components import C, badge, callout, chart, hero, section
from ui.state import current_vessel, get_params, get_predictor, live

params = get_params()
pred = get_predictor()
L = live()
v = current_vessel()
yard = params["yard"]
rng = np.random.default_rng()

hero("선적위치 예측", "반입되는 순간 예상 선적 순서를 예측하고, 재조작이 가장 적은 슬롯 3곳을 추천합니다. 최종 결정은 플래너가 합니다.")

# ── 입력 ──
ss = st.session_state
ss.setdefault("in_pod", v.port_rotation[-1])
if ss.in_pod not in v.port_rotation:
    ss.in_pod = v.port_rotation[-1]
ss.setdefault("in_weight", 18.0)
ss.setdefault("in_size", "40ft")
ss.setdefault("in_dg", False)


def random_arrival():
    b = L["boxes"]
    pool = b[(b.vessel_id == v.vessel_id)]
    r = pool.iloc[int(rng.integers(len(pool)))]
    ss.in_pod = r.pod
    ss.in_weight = float(np.clip(round(r.declared_weight + rng.normal(0, 1.5), 1), 2, 30))
    ss.in_size = f"{int(r['size'])}ft"
    ss.in_dg = bool(rng.random() < 0.08)


left, right = st.columns([1, 2.1], gap="large")
with left:
    section("반입 컨테이너", f"{v.name} · 블록 {v.block}")
    with st.container(border=True):
        st.selectbox("양하항 (하역 순서)", v.port_rotation, key="in_pod",
                     format_func=lambda p: f"{v.port_rotation.index(p) + 1}. {p}")
        st.slider("신고 중량 (t)", 2.0, 30.0, step=0.5, key="in_weight")
        st.radio("규격", ["20ft", "40ft"], horizontal=True, key="in_size")
        st.toggle("위험물 (DG)", key="in_dg")
        st.button("🎲  랜덤 반입", on_click=random_arrival, use_container_width=True)
    st.caption(f"양하항 순서: {' → '.join(v.port_rotation)}  (뒤쪽 항구일수록 먼저 선적)")

pos = v.port_rotation.index(ss.in_pod)
pod_d = pos / max(len(v.port_rotation) - 1, 1)
size = 20 if ss.in_size == "20ft" else 40
ex = pred.explain(pod_d, ss.in_weight, size, ss.in_dg)
p = ex["pred_pct"]

with right:
    section("예상 선적 순서", "사례기반 추론 · FASTrak 방식")
    k1, k2 = st.columns([1, 1.6])
    with k1:
        groups = ["가벼움", "중간", "무거움", "매우 무거움"]
        st.markdown(
            f'<div class="ss-card ss-kpi"><div class="label"><span>예측 선적 백분위</span>{badge("FASTrak", "primary")}</div>'
            f'<div class="value">{p * 100:.0f}<span class="unit">백분위</span></div>'
            f'<div class="sub">80% 구간 {ex["pred_lo"] * 100:.0f}–{ex["pred_hi"] * 100:.0f} · 0 = 가장 먼저 선적<br>'
            f'중량 그룹(GMM): <b>{groups[ex["weight_group"]]}</b></div></div>', unsafe_allow_html=True)
    with k2:
        edges = np.linspace(0, 1, 6)
        hist = np.histogram(np.clip(ex["neighbor_pcts"], 0, 0.9999), bins=edges)[0]
        prob = hist / hist.sum()
        labels = ["0–20", "20–40", "40–60", "60–80", "80–100"]
        top = int(prob.argmax())
        fig = go.Figure(go.Bar(
            x=labels, y=prob, marker=dict(color=[C["primary"] if i == top else "#1F5F7A" for i in range(5)],
                                          cornerradius=4),
            text=[f"{q * 100:.0f}%" for q in prob], textposition="outside", textfont=dict(color=C["muted"]),
            hovertemplate="%{x}<br>확률 %{y:.0%}<extra></extra>"))
        fig.update_layout(yaxis=dict(tickformat=".0%", range=[0, max(prob) * 1.3 + .05], title="확률"),
                          xaxis=dict(title="선적 순서 구간 (백분위, 0 = 먼저)"),
                          margin=dict(l=50, r=10, t=14, b=46), showlegend=False)
        chart(fig, height=210)

    # ── 추천 슬롯 Top 3 ──
    section("추천 슬롯 Top 3", "StowSync 배치 기준 · 예상 재조작 기여도가 낮은 순")
    area = L["areas"][v.vessel_id]["B"]
    preds = L["preds"]
    nb = ex["neighbor_pcts"]
    cands = []
    for c in score_stacks(area, p, preds, yard["max_tiers"]):
        m = c["min_pred"]
        contrib = 0.0 if c["empty"] else float((nb > m).mean())
        fit = 0 if c["empty"] or m < p else (m - p)
        score = contrib + (0.12 if c["empty"] else 0) + 0.2 * fit + 0.002 * c["bay"]
        if c["empty"]:
            why = "빈 스택 · 충돌 없음 (단, 빈 스택 하나를 사용)"
        elif m >= p:
            why = f"아래 박스 중 가장 이른 선적 {m * 100:.0f}백분위 → 이 박스가 먼저 실림 · 충돌 없음"
        else:
            why = f"아래에 더 먼저 실릴 박스(최소 {m * 100:.0f}백분위) 있음 · 충돌 {c['conflicts']}개"
        cands.append({**c, "contrib": contrib, "score": score, "why": why})
    top3 = sorted(cands, key=lambda c: c["score"])[:3]

    def place(c):
        n = len(L["user_boxes"]) + 1
        cn = f"NEWU{n:07d}"
        L["areas"][v.vessel_id]["B"][c["bay"]][c["stack"]].append(cn)
        L["preds"][cn] = p
        L["user_boxes"].append({"cntr_no": cn, "vessel_id": v.vessel_id, "pod": ss.in_pod, "size": size,
                                "vgm_weight": ss.in_weight, "declared_weight": ss.in_weight, "is_dg": ss.in_dg,
                                "pred_pct": p, "weight_group": ex["weight_group"],
                                "slot": f"{v.block}-{c['bay'] + 1:02d}-{c['stack'] + 1}-{c['height'] + 1}"})
        st.session_state["_placed"] = (cn, f"{v.block}-{c['bay'] + 1:02d}-{c['stack'] + 1}-{c['height'] + 1}")

    cols = st.columns(3)
    for i, (col, c) in enumerate(zip(cols, top3)):
        loc = f"{v.block}-{c['bay'] + 1:02d}-{c['stack'] + 1}-{c['height'] + 1}"
        kind = "safe" if c["contrib"] < .15 else ("warn" if c["contrib"] < .4 else "danger")
        contrib_badge = badge(f"재조작 기여 +{c['contrib']:.2f}회", kind)
        with col:
            st.markdown(
                f'<div class="ss-card ss-slot {"top" if i == 0 else ""}" style="animation-delay:{i * .08}s">'
                f'<div class="rank">#{i + 1} {"· 최적" if i == 0 else ""}</div><div class="loc">{loc}</div>'
                f'<div style="margin:.2rem 0 .5rem">{contrib_badge}</div>'
                f'<div class="why">{c["why"]}</div><div class="sub" style="font-size:.72rem;color:#8BA3C7;margin-top:.4rem">'
                f'블록-베이-로우-단 · 현재 {c["height"]}단</div></div>', unsafe_allow_html=True)
            st.button("이 슬롯에 장치", key=f"place_{i}", on_click=place, args=(c,), use_container_width=True,
                      type="primary" if i == 0 else "secondary")

if "_placed" in st.session_state:
    cn, loc = st.session_state.pop("_placed")
    st.toast(f"{cn} → {loc} 장치 완료. 야드 3D 뷰에 반영했습니다.", icon="✅")
    callout(f"<b>{cn}</b> 을(를) <b>{loc}</b> 에 장치했습니다. 3D 뷰에서 흰색 박스로 확인하세요.")
    st.page_link("pages/2_야드_3D뷰.py", label="야드 3D 뷰에서 확인 →", icon=":material/view_in_ar:")

# ── 근거 ──
section("근거: 가장 비슷한 과거 사례 3건", "가중 거리 Σ wᵢ·|xᵢ − xᵢ'| — 양하항 위치·중량 그룹·중량·규격·위험물")
cases = ex["cases"]
rows = "".join(
    f"<tr><td>{r.voyage}</td><td>{r.pod} ({r.pod_pos + 1}/{r.n_pods}번째 하역)</td><td class='num'>{r.weight:.1f}t</td>"
    f"<td>{r['size']}ft{' · DG' if r.is_dg else ''}</td><td class='num'>{r.load_pct * 100:.0f}</td>"
    f"<td class='num'>{r.distance:.3f}</td></tr>" for _, r in cases.iterrows())
st.markdown('<div class="ss-card"><table class="ss-table"><thead><tr><th>과거 항차</th><th>양하항</th>'
            '<th class="num">중량</th><th>규격</th><th class="num">실제 선적 백분위</th><th class="num">거리 점수</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
st.caption(f"이웃 {len(ex['neighbor_pcts'])}건의 실제 선적 백분위 평균 = 예측값 · 과거 항차는 합성 이력(가정) · "
           "FASTrak 방식(사례기반 추론)을 참고해 구현")
