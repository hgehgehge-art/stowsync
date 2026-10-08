"""StowSync — 수출 컨테이너 선적순서 예측 · 야드 장치 추천 · 계획 동기화 데모."""
import streamlit as st

st.set_page_config(page_title="StowSync · 해운 관제실", page_icon="🚢", layout="wide",
                   initial_sidebar_state="expanded")

from ui.components import inject_theme  # noqa: E402
from ui.state import sidebar, sidebar_footer  # noqa: E402

inject_theme()
sidebar()

pages = {
    "운영": [
        st.Page("pages/1_관제_대시보드.py", title="관제 대시보드", icon=":material/monitoring:", default=True),
        st.Page("pages/2_야드_3D뷰.py", title="야드 3D 뷰", icon=":material/view_in_ar:"),
        st.Page("pages/3_선적위치_예측.py", title="선적위치 예측", icon=":material/target:"),
        st.Page("pages/4_계획_동기화.py", title="계획 동기화", icon=":material/sync_alt:"),
    ],
    "분석": [
        st.Page("pages/5_시뮬레이션_실험실.py", title="시뮬레이션 실험실", icon=":material/science:"),
        st.Page("pages/6_화주_반입가이드.py", title="화주 반입가이드", icon=":material/local_shipping:"),
    ],
    "참고": [
        st.Page("pages/7_데이터_출처.py", title="데이터 출처", icon=":material/menu_book:"),
    ],
}
nav = st.navigation(pages, position="sidebar")
sidebar_footer()
nav.run()
