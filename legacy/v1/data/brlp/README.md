# BRLP 벤치마크 파일 위치

1. https://mail.ipb.ac.rs/~rakaj/brlp/brlp.htm 에서 `data.zip` 을 직접 내려받습니다 (Jovanovic et al. 2016).
2. 압축을 풀어 `.pro` 파일을 이 폴더(하위 폴더 가능)에 둡니다.
3. 시뮬레이션 실험실 → "BRLP 벤치마크" 탭에서 자동으로 읽습니다.

`SAMPLE_selfmade_format_example.pro` 는 **자체 작성한 형식 예시**이며 BRLP 데이터가 아닙니다.
실제 파일을 받은 뒤 형식이 다르면 `core/brlp_loader.py` 의 `parse_brlp` 를 맞춰 주세요.
