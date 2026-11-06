from inku_server.build_info import build_number
from inku_server.request_timeout import request_timeout_seconds


def test_build_number_reads_the_selected_tree(tmp_path):
    assert build_number(tmp_path) is None
    (tmp_path / 'web').mkdir()
    (tmp_path / 'web' / 'BUILD_NUMBER').write_text('1402\n')
    assert build_number(tmp_path) == '1402'


def test_provider_deadline_default_and_override(monkeypatch):
    monkeypatch.delenv('INKU_LLM_REQUEST_TIMEOUT_SECONDS', raising=False)
    assert request_timeout_seconds() == 120
    monkeypatch.setenv('INKU_LLM_REQUEST_TIMEOUT_SECONDS', '23.5')
    assert request_timeout_seconds() == 23.5
