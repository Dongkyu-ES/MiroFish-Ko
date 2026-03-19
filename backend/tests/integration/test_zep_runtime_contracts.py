from __future__ import annotations

import types

import pytest

from backend.app.services.graph_builder import GraphBuilderService
from backend.app.services.zep_entity_reader import ZepEntityReader


def test_zep_entity_reader_supports_sdk_get_edges_only():
    edge = types.SimpleNamespace(
        uuid_="edge-1",
        name="works_for",
        fact="Alice works for Example Labs.",
        source_node_uuid="node-1",
        target_node_uuid="node-2",
        attributes={"confidence": "high"},
    )

    class NodeNamespace:
        def __init__(self):
            self.called_with: list[str] = []

        def get_edges(self, node_uuid: str):
            self.called_with.append(node_uuid)
            return [edge]

    reader = object.__new__(ZepEntityReader)
    reader.client = types.SimpleNamespace(
        graph=types.SimpleNamespace(node=NodeNamespace())
    )

    result = reader.get_node_edges("node-1")

    assert reader.client.graph.node.called_with == ["node-1"]
    assert result == [
        {
            "uuid": "edge-1",
            "name": "works_for",
            "fact": "Alice works for Example Labs.",
            "source_node_uuid": "node-1",
            "target_node_uuid": "node-2",
            "attributes": {"confidence": "high"},
        }
    ]


def test_wait_for_episodes_raises_when_processing_never_finishes():
    builder = object.__new__(GraphBuilderService)
    builder.client = types.SimpleNamespace(
        graph=types.SimpleNamespace(
            episode=types.SimpleNamespace(
                get=lambda uuid_: types.SimpleNamespace(processed=False)
            )
        )
    )

    with pytest.raises(TimeoutError, match="ep-1"):
        builder._wait_for_episodes(["ep-1"], timeout=0)


def test_wait_for_episodes_raises_on_permanent_poll_error():
    builder = object.__new__(GraphBuilderService)

    class PermanentEpisodeError(Exception):
        status_code = 404

    builder.client = types.SimpleNamespace(
        graph=types.SimpleNamespace(
            episode=types.SimpleNamespace(
                get=lambda uuid_: (_ for _ in ()).throw(PermanentEpisodeError("not found"))
            )
        )
    )

    with pytest.raises(PermanentEpisodeError, match="not found"):
        builder._wait_for_episodes(["ep-1"], timeout=1)


def test_local_primary_simulation_entities_route_does_not_require_zep_api_key(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("GRAPHITI_ALLOW_LOCAL_EVAL", "true")

    import backend.app as app_module
    import backend.app.api.simulation as simulation_api

    simulation_api.Config.GRAPH_BACKEND = "local_primary"
    simulation_api.Config.ZEP_API_KEY = None

    class DummyReader:
        def filter_defined_entities(self, graph_id, defined_entity_types=None, enrich_with_edges=True):
            return types.SimpleNamespace(
                to_dict=lambda: {
                    "entities": [],
                    "entity_types": [],
                    "total_count": 0,
                    "filtered_count": 0,
                }
            )

    monkeypatch.setattr(simulation_api, "ZepEntityReader", DummyReader)

    app = app_module.create_app()
    response = app.test_client().get("/api/simulation/entities/test-graph")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_local_primary_graph_data_route_does_not_require_zep_api_key(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("GRAPHITI_ALLOW_LOCAL_EVAL", "true")

    import backend.app as app_module
    import backend.app.api.graph as graph_api

    graph_api.Config.GRAPH_BACKEND = "local_primary"
    graph_api.Config.ZEP_API_KEY = None

    class DummyBuilder:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def get_graph_data(self, graph_id: str):
            return {
                "graph_id": graph_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
            }

    monkeypatch.setattr(graph_api, "GraphBuilderService", DummyBuilder)

    app = app_module.create_app()
    response = app.test_client().get("/api/graph/data/test-graph")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
