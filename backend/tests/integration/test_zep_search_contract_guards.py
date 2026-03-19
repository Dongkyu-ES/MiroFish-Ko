from types import SimpleNamespace

import pytest


def test_search_graph_raises_on_remote_contract_error(monkeypatch):
    import backend.app.services.zep_tools as zep_tools_module

    class PermanentSearchError(Exception):
        status_code = 400

    service = zep_tools_module.ZepToolsService(api_key="dummy")
    service.client = SimpleNamespace(
        graph=SimpleNamespace(
            search=lambda **kwargs: (_ for _ in ()).throw(PermanentSearchError("bad request"))
        )
    )
    monkeypatch.setattr(zep_tools_module.Config, "GRAPH_BACKEND", "zep")

    with pytest.raises(PermanentSearchError, match="bad request"):
        service.search_graph("graph-1", "alice employer")
