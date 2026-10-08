# StowSync — 해운 관제실 데모 (Streamlit)

수출 컨테이너가 반입되는 순간 예상 선적 순서를 예측해 야드 장치 위치를 추천하고,
선사·터미널·야드가 같은 계획을 보게 해 **재조작(리핸들링)** 을 줄이는 플랫폼의 데모입니다.
명세: [SPEC.md](SPEC.md)

> 모든 숫자는 `config/params.yaml` 의 **가정값으로 만든 시드 고정 합성 데이터**입니다. 실측치가 아닙니다.
> 외부 API 키 없이 오프라인으로 동작합니다 (웹폰트만 CDN, 실패 시 시스템 폰트로 대체).

## 실행 방법

```bash
cd stowsync
python3 -m venv .venv && source .venv/bin/activate   # 선택
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 http://localhost:8501 이 열립니다. 테스트:

```bash
python3 -m pytest -q
```

- Python 3.11 이상 (3.13.5에서 확인), Streamlit 1.45 이상
- 반드시 `stowsync/` 폴더에서 실행하세요 (`.streamlit/config.toml` 다크 테마가 적용됩니다)

## 3분 데모 순서

| # | 페이지 | 보여줄 것 |
|---|---|---|
| 1 | 관제 대시보드 | 선박 3척 스케줄, KPI 4개(현행 대비 ▼%), 블록×베이 위험 히트맵, 이벤트 피드 |
| 2 | 야드 3D 뷰 | 현행 ↔ StowSync 나란히, 빨간 박스 = 재조작 대상, 마우스를 올리면 상세 정보 |
| 3 | 선적위치 예측 | 🎲 랜덤 반입 → 예측 백분위·확률 막대 → 추천 슬롯 Top 3 → "이 슬롯에 장치" (3D 뷰에 흰색 박스로 표시) |
| 4 | 계획 동기화 | ⛔ 롤오버 발생 → 박스 깜빡임, 역할별 알림 3개, 확인 대기 버전, 사전 재정렬 승인/거절, 로드시트 |
| 5 | 시뮬레이션 실험실 | 현행 vs A vs B 평균·95% 구간, 박스플롯, CSV 다운로드, BRLP 탭 |

## 화면 스크린샷

`docs/screenshots/` 폴더에 있습니다. 개발 중에 찍은 화면이며, 제안서에 넣기 전에 최종 화면으로 다시 찍는 것을 권장합니다.

| 파일 | 화면 |
|---|---|
| `docs/screenshots/1_dashboard.jpg` | 관제 대시보드 |
| `docs/screenshots/2_yard3d.jpg` | 야드 3D 뷰 비교 모드 (테마 CSS 적용 전 캡처) |
| `docs/screenshots/4_sync.jpg` | 계획 동기화 (이벤트 직후, 확인 대기 상태) |
| `docs/screenshots/5_lab.jpg` | 시뮬레이션 실험실 |

## 결과 요약 (기본 가정값, 시드 1000~1009, 3척 합계)

| 전략 | 평균 재조작 | 현행 대비 |
|---|---|---|
| 현행 (중량 그룹 장치, Kim et al. 2000) | 274.0회 | — |
| A · 예측 공유 | 123.7회 | −55% |
| B · A + 실시간 변경 | 113.9회 (+ 사전 재정렬 5.8회 별도) | −58% (총 이동 기준 −56%) |

- B와 A의 차이는 계획 변경 비율이 커질수록 벌어집니다 (변경 0%면 동일, 25%면 A 148.6회 vs B 128.9회).
- 숫자는 조정하지 않았습니다. 결과가 나빠지는 설정에서는 실험실에 경고가 표시됩니다.

## 구조

```text
app.py                  st.navigation, 테마 주입, 사이드바
config/params.yaml      모든 가정값 ('가정' 주석)
core/generator.py       합성 선박·컨테이너·반입 스트림, 과거 항차 이력
core/events.py          롤오버 / 막판 부킹 / VGM 수정 (시나리오 + 동기화 보드 버튼)
core/predictor.py       GMM 중량 그룹 + 사례기반(FASTrak 방식) 선적순서 예측
core/stacking.py        장치 전략 현행 / A / B, 사전 재정렬
core/relocation.py      재조작 횟수 계산 (tests/test_relocation.py)
core/simulation.py      같은 데이터로 3전략 실행
core/brlp_loader.py     BRLP .pro 파서와 평가
ui/components.py        히어로 헤더, KPI 카드, 배지, Plotly 템플릿
ui/yard_viz.py          Mesh3d 야드 3D, 베이 단면
ui/state.py             캐시·세션 상태·사이드바
pages/1~7               페이지
```

## 주요 가정과 단순화

- 선박마다 전용 블록 1개, 슬롯 1개에 박스 1개 (20/40ft 물리적 차이는 무시하고 길이만 다르게 그림)
- 선적 시 재조작: 같은 베이 안에서 옮김 (SPEC 5.4). 방식 B의 사전 재정렬은 같은 베이를 우선하고 없으면 같은 블록 안에서 옮김
- 크레인 대기 = 재조작 1회당 2.5분 (가정)
- 실제 적재 순서 = 먼 양하항 먼저, 무거운 박스 먼저 + 잡음 (VGM 기준)

## BRLP 벤치마크

`data/brlp/README.md` 를 참고해 `data.zip` 을 직접 내려받아 `data/brlp/` 에 두면 실험실의 BRLP 탭에서 자동으로 읽습니다.
지금 들어 있는 `SAMPLE_selfmade_format_example.pro` 는 **자체 작성한 형식 예시**이며, 파서는 데이터셋 페이지 설명을 기준으로 작성했습니다.
실제 파일로 형식을 다시 확인해야 합니다.

## 남은 일

- [ ] 시뮬레이션 실험실 결과를 캡처해 공모전 제안서 근거로 삽입
- [ ] params.yaml 가정값을 공공데이터포털 통계로 보정
- [ ] BRLP 실제 파일로 파서 형식 확인
- [ ] Park et al. 2023, FASTrak 서지 정보 확인 (데이터 출처 페이지)
- [ ] 데모 영상 녹화 (3분)
