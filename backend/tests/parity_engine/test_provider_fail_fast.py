import pytest

from backend.app.parity_engine.graphiti_client import GraphitiEngine


def test_graphiti_engine_fails_fast_without_provider_config_when_not_inline(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_MODEL", "")
    monkeypatch.setenv("GRAPHITI_RERANK_MODEL", "")
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "false")
    monkeypatch.setattr(GraphitiEngine, "_build_graphiti", lambda self: object())

    async def _noop_initialize(self):
        return None

    monkeypatch.setattr(GraphitiEngine, "_initialize_graphiti_indices", _noop_initialize)

    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu", episode_inline=False)
    graph_id = engine.create_graph("Parity Test", "desc")

    with pytest.raises(RuntimeError, match="provider configuration"):
        engine.add_episode(graph_id, "Alice founded Example Labs.")


def test_graphiti_engine_fails_fast_without_provider_config_when_inline_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "")
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    monkeypatch.setattr(GraphitiEngine, "_build_graphiti", lambda self: object())

    async def _noop_initialize(self):
        return None

    monkeypatch.setattr(GraphitiEngine, "_initialize_graphiti_indices", _noop_initialize)

    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu", episode_inline=True)
    graph_id = engine.create_graph("Inline Parity Test", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [{"name": "Person", "description": "A person.", "attributes": []}],
            "edge_types": [],
        },
    )

    with pytest.raises(RuntimeError, match="inline llm extraction"):
        engine.add_episode(graph_id, "Alice founded Example Labs.")
