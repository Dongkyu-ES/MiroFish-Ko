from pydantic import Field

from backend.bootstrap_graph_backend import bootstrap_graph_backend
from backend.tests.integration._engine_test_server import running_engine_server


def test_existing_graph_id_coexistence_preserves_graph_id(monkeypatch, tmp_path):
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
            graph_id="preexisting_graph_99",
            name="Imported Graph",
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
        client.graph.add(graph_id=graph.graph_id, type="text", data="Alice works for Example Labs.")

        nodes = client.graph.node.get_by_graph_id("preexisting_graph_99", limit=10)

        assert graph.graph_id == "preexisting_graph_99"
        assert nodes
