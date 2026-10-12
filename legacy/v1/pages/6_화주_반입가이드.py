"""4.6 화주 반입 가이드 (로드맵 미리보기)."""
import hashlib
from datetime import timedelta

import numpy as np
import streamlit as st

from ui.components import C, badge, callout, hero
from ui.state import get_demo, get_multi_seed_runs_boxes

demo = get_demo()
scn = demo.scenario

hero("화주 반입 가이드", "부킹 번호만 넣으면 재조작 위험이 낮은 반입 시간대를 알려주는 모바일 화면 목업입니다.",
     eyebrow="SHIPPER APP", badge="Roadmap · 미리보기")

left, right = st.columns([1, 1.25], gap="large")
with left:
    st.markdown(badge("Roadmap · 미리보기", "warn"), unsafe_allow_html=True)
    st.write("")
    bk = st.text_input("부킹 번호", value="BKG-2026-10481", max_chars=24)
    callout("시간대별 위험도는 <b>여러 시드의 현행 방식 시뮬레이션</b>에서, 그 시간대에 반입된 박스가 "
            "선적 때 재조작된 비율로 계산합니다. 실측치가 아닌 가정값 기반 결과입니다.")

h = int(hashlib.sha256(bk.encode()).hexdigest(), 16)
v = scn.vessels[h % len(scn.vessels)]
boxes = scn.boxes(v.vessel_id)
box = boxes.iloc[(h // 7) % len(boxes)]

d = get_multi_seed_runs_boxes()
d = d[(d.hours_before >= 0) & (d.hours_before < 24)]
d["h"] = d.hours_before.astype(int)
rate = d.groupby("h").moved.mean().reindex(range(24)).ffill().bfill().to_numpy()
rate_by_slot = rate[::-1]                                     # 왼쪽 = 마감 24시간 전 → 오른쪽 = 마감 직전
q1, q2 = np.quantile(rate_by_slot, [1 / 3, 2 / 3])
cols = [C["safe"] if r <= q1 else (C["warn"] if r <= q2 else C["danger"]) for r in rate_by_slot]
win = np.convolve(rate_by_slot, np.ones(3) / 3, mode="valid")
best = int(win.argmin())
start = v.cutoff - timedelta(hours=24)
best_from, best_to = start + timedelta(hours=best), start + timedelta(hours=best + 3)
hi_, lo_ = rate_by_slot.max(), rate_by_slot.min()
bars = "".join(
    f'<div class="{"best" if best <= i < best + 3 else ""}" title="{(start + timedelta(hours=i)):%H}시 · 재조작 {r:.0%}" '
    f'style="height:{25 + 75 * (r - lo_) / max(hi_ - lo_, 1e-9):.0f}%;background:{c}"></div>'
    for i, (r, c) in enumerate(zip(rate_by_slot, cols)))
err = abs(box.declared_weight - box.vgm_weight) / box.vgm_weight
score = int(np.clip(100 - err * 500, 0, 100))
score_c = C["safe"] if score >= 85 else (C["warn"] if score >= 60 else C["danger"])

with right:
    st.markdown(f"""
<div class="ss-phone"><div class="screen"><div class="notch"></div>
<div style="display:flex;justify-content:space-between;align-items:center">
  <div style="font-weight:800;font-size:1.05rem">Stow<span style="color:{C['primary']}">Sync</span></div>
  {badge("미리보기", "warn")}
</div>
<div style="color:{C['muted']};font-size:.75rem;margin-top:14px">부킹 번호</div>
<div style="font-family:JetBrains Mono;font-size:1.05rem;font-weight:700">{bk}</div>
<div class="ss-card" style="margin-top:12px;padding:12px 14px">
  <div style="display:flex;justify-content:space-between;font-size:.8rem;color:{C['muted']}"><span>선박</span><span>반입 마감</span></div>
  <div style="display:flex;justify-content:space-between;font-weight:700"><span>{v.name}</span>
  <span style="font-family:JetBrains Mono;color:{C['danger']}">{v.cutoff:%m-%d %H:%M}</span></div>
  <div style="font-size:.75rem;color:{C['muted']};margin-top:4px">{box.cntr_no} · {int(box['size'])}ft · {box.pod}</div>
</div>
<div style="margin-top:16px;font-weight:700;font-size:.92rem">추천 반입 시간대</div>
<div style="font-family:JetBrains Mono;font-size:1.5rem;font-weight:700;color:{C['primary']};text-shadow:0 0 14px rgba(0,212,255,.4)">
  {best_from:%H:%M} – {best_to:%H:%M}</div>
<div class="ss-hours">{bars}</div>
<div style="display:flex;justify-content:space-between;font-family:JetBrains Mono;font-size:.66rem;color:{C['muted']}">
  <span>{start:%H}시</span><span>마감 12h 전</span><span>마감</span></div>
<div class="ss-legend" style="margin-top:8px"><span><i style="background:{C['safe']}"></i>낮음</span>
  <span><i style="background:{C['warn']}"></i>중간</span><span><i style="background:{C['danger']}"></i>높음</span></div>
<div class="ss-card" style="margin-top:12px;padding:12px 14px;display:flex;align-items:center;gap:14px">
  <div style="width:62px;height:62px;border-radius:50%;display:grid;place-items:center;
    background:conic-gradient({score_c} {score * 3.6}deg,#1E3A5F 0);">
    <div style="width:50px;height:50px;border-radius:50%;background:{C['surface']};display:grid;place-items:center;
      font-family:JetBrains Mono;font-weight:700">{score}</div></div>
  <div><div style="font-weight:700;font-size:.9rem">VGM 정확도 점수</div>
  <div style="font-size:.74rem;color:{C['muted']}">신고 {box.declared_weight:.1f}t · VGM {box.vgm_weight:.1f}t<br>
  정확할수록 재조작 위험이 낮아집니다</div></div>
</div>
<div style="margin-top:14px;text-align:center;padding:11px;border-radius:12px;background:linear-gradient(135deg,#00D4FF,#00A3D9);
  color:#04101F;font-weight:800">이 시간대로 반입 예약</div>
</div></div>""", unsafe_allow_html=True)
