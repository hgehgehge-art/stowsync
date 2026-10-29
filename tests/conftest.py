import pytest


@pytest.fixture(autouse=True)
def _history_db(tmp_path, monkeypatch):
    """테스트마다 별도 이력 DB를 써서 실제 runtime/history.db를 건드리지 않습니다."""
    monkeypatch.setenv('STOWSYNC_HISTORY_DB', str(tmp_path / 'history.db'))
