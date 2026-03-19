import pytest

from backend.app.parity_engine.local_measurement import validate_provider_capture_env


def test_validate_provider_capture_env_requires_graphiti_provider_vars(monkeypatch):
    for key in (
        "GRAPHITI_LLM_API_KEY",
        "GRAPHITI_LLM_MODEL",
        "GRAPHITI_EMBEDDING_MODEL",
        "GRAPHITI_RERANK_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="provider capture"):
        validate_provider_capture_env()
