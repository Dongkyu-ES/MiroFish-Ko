import time

from pydantic import Field

from backend.bootstrap_graph_backend import bootstrap_graph_backend
from backend.tests.integration._engine_test_server import running_engine_server


def test_local_primary_adapter_exposes_zep_contract(monkeypatch, tmp_path):
    with running_engine_server(tmp_path) as base_url:
        monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
        monkeypatch.setenv("ENGINE_BASE_URL", base_url)
        bootstrap_graph_backend()

        from zep_cloud import EntityEdgeSourceTarget
        from zep_cloud.client import Zep
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel

        class Person(EntityModel):
            name: EntityText | None = Field(default=None, description="person name")

        class Company(EntityModel):
            name: EntityText | None = Field(default=None, description="company name")

        class WorksFor(EdgeModel):
            fact: str | None = Field(default=None, description="employment fact")

        Person.__doc__ = "A person"
        Company.__doc__ = "A company"
        WorksFor.__doc__ = "Employment relationship"

        client = Zep(api_key="__local__")
        graph = client.graph.create(
            graph_id="legacy_graph_01",
            name="Parity Test",
            description="desc",
        )
        client.graph.set_ontology(
            graph_ids=[graph.graph_id],
            entities={"Person": Person, "Company": Company},
            edges={
                "works_for": (
                    WorksFor,
                    [EntityEdgeSourceTarget(source="Person", target="Company")],
                )
            },
        )
        batch = client.graph.add_batch(
            graph_id=graph.graph_id,
            episodes=[
                type("Episode", (), {"data": "Alice works for Example Labs.", "type": "text"})(),
                type("Episode", (), {"data": "Bob works for Example Labs.", "type": "text"})(),
            ],
        )
        assert len(batch) == 2
        assert len({item.uuid_ for item in batch}) == 2

        for episode in batch:
            for _ in range(20):
                current = client.graph.episode.get(uuid_=episode.uuid_)
                if current.processed:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("episode did not finish processing in time")

        nodes = client.graph.node.get_by_graph_id(graph.graph_id, limit=10)
        search = client.graph.search(
            graph_id=graph.graph_id,
            query="Alice employer",
            limit=10,
            scope="edges",
            reranker="cross_encoder",
        )

        assert hasattr(client.graph, "search")
        assert hasattr(client.graph.node, "get_by_graph_id")
        assert hasattr(client.graph.node, "get_entity_edges")
        assert graph.graph_id == "legacy_graph_01"
        assert nodes
        assert search.edges
