import pytest

from backend.app.parity_engine.runtime_checks import EngineUnavailableError, ensure_engine_ready
from backend.tests.integration._engine_test_server import running_engine_server


def test_ensure_engine_ready_succeeds_when_engine_is_running(tmp_path, monkeypatch):
    with running_engine_server(tmp_path) as base_url:
        monkeypatch.setenv("ENGINE_BASE_URL", base_url)

        status = ensure_engine_ready(timeout_seconds=1, poll_interval=0.1)

        assert status.ready is True
        assert status.engine_status == "ready"


def test_ensure_engine_ready_raises_explicit_error_when_engine_is_unavailable(monkeypatch):
    monkeypatch.setenv("ENGINE_BASE_URL", "http://127.0.0.1:1")

    with pytest.raises(EngineUnavailableError, match="Parity engine is unavailable"):
        ensure_engine_ready(timeout_seconds=1, poll_interval=0.1)
