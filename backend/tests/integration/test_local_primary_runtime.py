import importlib

import backend.app.config as config_module


def test_local_primary_does_not_require_zep_api_key(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")
    monkeypatch.delenv("ZEP_API_KEY", raising=False)
    importlib.reload(config_module)

    assert "ZEP_API_KEY가 설정되지 않았습니다." not in config_module.Config.validate()


def test_shadow_eval_still_requires_zep_api_key(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "shadow_eval")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("ZEP_API_KEY", "")
    importlib.reload(config_module)

    assert "ZEP_API_KEY가 설정되지 않았습니다." in config_module.Config.validate()
