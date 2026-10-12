"""4.7 데이터 출처와 가정값."""
import pandas as pd
import streamlit as st
import yaml

from core.params import PARAMS_PATH
from ui.components import callout, hero, section
from ui.state import get_params

params = get_params()
hero("데이터 출처", "사용한 공공데이터 · 벤치마크 · 논문과 모든 가정값입니다.", eyebrow="REFERENCES")

callout("컨테이너 단위 실데이터는 공개되지 않아 <b>공개 통계로 보정할 합성 데이터</b>와 <b>BRLP 공개 벤치마크</b>를 씁니다. "
        "화면의 모든 숫자는 아래 가정값으로 만든 시뮬레이션 결과이며 실측치가 아닙니다.", "warn")

section("출처", "링크 · 사용처 · 상태")
src = [
    ("벤치마크", "BRLP 데이터셋 — Jovanovic et al. (2016)", "https://mail.ipb.ac.rs/~rakaj/brlp/brlp.htm",
     "시뮬레이션 실험실 · BRLP 탭", "수동 다운로드 후 data/brlp 에 배치"),
    ("공공데이터", "부산항 컨테이너 수송통계", "https://www.data.go.kr/",
     "20/40ft 비율 · 물동량 보정", "보정 예정 (현재 가정값)"),
    ("공공데이터", "입항선박 톤급별 통계", "https://www.data.go.kr/",
     "선박 규모(박스 수) 분포 보정", "보정 예정 (현재 가정값)"),
    ("논문", "Kim, Park & Ryu (2000) — Deriving decision rules to locate export containers in container yards, EJOR", "",
     "현행 장치 전략 (중량 그룹 기반)", "참고"),
    ("논문", "Park et al. (2023) — 중량 그룹 GMM", "",
     "predictor.py 중량 그룹", "참고 · 서지 정보 확인 필요"),
    ("방법론", "FASTrak 방식 사례기반 추론", "",
     "predictor.py 사례기반 선적순서 예측", "참고 · 서지 정보 확인 필요"),
]


def _link(u):
    return f'<br><a href="{u}" target="_blank" style="color:#00D4FF;font-size:.76rem">{u}</a>' if u else ""


rows = "".join(
    f"<tr><td>{k}</td><td><b>{t}</b>{_link(u)}</td>"
    f"<td>{use}</td><td style='color:#8BA3C7'>{s}</td></tr>" for k, t, u, use, s in src)
st.markdown('<div class="ss-card"><table class="ss-table"><thead><tr><th>구분</th><th>자료</th><th>사용처</th><th>상태</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)


def flatten(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from flatten(v, key + ".")
        else:
            yield key, v


section("가정값 목록", "config/params.yaml — 모두 '가정'")
c1, c2 = st.columns([1, 1.1], gap="large")
with c1:
    df = pd.DataFrame([(k, str(v)) for k, v in flatten(params)], columns=["항목", "값 (가정)"])
    st.dataframe(df, use_container_width=True, hide_index=True, height=560)
with c2:
    st.code(PARAMS_PATH.read_text(encoding="utf-8"), language="yaml", height=560)
