import importlib


def test_local_primary_chunk_policy_uses_larger_chunks(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")

    import backend.app.services.graph_builder as graph_builder_module

    importlib.reload(graph_builder_module)

    chunk_size, chunk_overlap = graph_builder_module.GraphBuilderService.resolve_chunk_settings(500, 50)

    assert chunk_size == 1500
    assert chunk_overlap == 100


def test_zep_chunk_policy_preserves_requested_values(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "zep")

    import backend.app.services.graph_builder as graph_builder_module

    importlib.reload(graph_builder_module)

    chunk_size, chunk_overlap = graph_builder_module.GraphBuilderService.resolve_chunk_settings(500, 50)

    assert chunk_size == 500
    assert chunk_overlap == 50
