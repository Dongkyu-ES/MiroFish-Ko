import importlib

import backend.app.config as config_module


def test_shadow_eval_mode_is_supported(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "shadow_eval")
    importlib.reload(config_module)

    assert config_module.Config.GRAPH_BACKEND == "shadow_eval"
