"""기획서 2.6과 화면 표기가 어긋나지 않는지 확인합니다."""
from types import SimpleNamespace

from services.robustness import summarize
from ui.scenario_page import saved_text
from ui.workflows import gain_text, is_harmful


def test_robustness_summary_matches_proposal_numbers():
    r = summarize()
    assert r and r['conditions'] == 120
    wait, delay, moves = r['rows']
    assert (wait['less'], round(wait['pct'], 1)) == (91, -6.7)        # 평균 트럭 대기 91개 조건 감소, −6.7%
    assert (delay['less'], round(delay['pct'], 1)) == (82, -5.1)      # 평균 인출 지연 82개 조건 감소, −5.1%
    assert (moves['less'], moves['same'], moves['more']) == (50, 17, 53)  # 총 추가 이동은 일관된 감소 없음


def test_saving_labels_read_as_words_not_signs():
    assert saved_text(2.42) == '2.4분 단축'
    assert saved_text(-0.3) == '0.3분 증가'
    assert saved_text(0.0) == '변화 없음'
    assert gain_text(965.0) == '965.0점 개선' and gain_text(-12.0) == '12.0점 악화'


def test_premarshal_that_adds_total_moves_is_flagged():
    rec = SimpleNamespace(keep_rehandles=15.0)
    assert is_harmful(rec, SimpleNamespace(rehandles=15.0, premarshals=1.0))      # 16 > 15 → 보류 권장
    assert not is_harmful(rec, SimpleNamespace(rehandles=14.0, premarshals=1.0))  # 15 = 15 → 검토 가능
