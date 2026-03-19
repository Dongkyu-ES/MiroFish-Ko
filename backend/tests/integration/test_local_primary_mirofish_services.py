import importlib

from pydantic import Field

from backend.tests.integration._engine_test_server import running_engine_server


def test_mirofish_services_work_against_local_primary_engine(monkeypatch, tmp_path):
    with running_engine_server(tmp_path) as base_url:
        monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
        monkeypatch.setenv("ENGINE_BASE_URL", base_url)
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.delenv("ZEP_API_KEY", raising=False)

        import backend.app.config as config_module
        import backend.app.services.graph_builder as graph_builder_module
        import backend.app.services.zep_entity_reader as zep_entity_reader_module
        import backend.app.services.zep_tools as zep_tools_module

        importlib.reload(config_module)
        importlib.reload(graph_builder_module)
        importlib.reload(zep_entity_reader_module)
        importlib.reload(zep_tools_module)

        GraphBuilderService = graph_builder_module.GraphBuilderService
        ZepEntityReader = zep_entity_reader_module.ZepEntityReader
        ZepToolsService = zep_tools_module.ZepToolsService
        from zep_cloud import EntityEdgeSourceTarget
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

        builder = GraphBuilderService()
        graph_id = builder.create_graph("Compatibility Graph")
        builder.set_ontology(
            graph_id,
            {
                "entity_types": [
                    {"name": "Person", "description": "A person", "attributes": []},
                    {"name": "Company", "description": "A company", "attributes": []},
                ],
                "edge_types": [
                    {
                        "name": "works_for",
                        "description": "Employment relationship",
                        "source_targets": [
                            {"source": "Person", "target": "Company"},
                        ],
                        "attributes": [],
                    }
                ],
            },
        )
        episodes = builder.add_text_batches(
            graph_id,
            [
                "Alice works for Example Labs.",
                "Bob works for Example Labs.",
            ],
            batch_size=2,
        )
        assert len(episodes) == 2
        assert len(set(episodes)) == 2
        builder._wait_for_episodes(episodes)
        graph_data = builder.get_graph_data(graph_id)

        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(graph_id, ["Person", "Company"], enrich_with_edges=True)

        tools = ZepToolsService()
        search = tools.search_graph(graph_id, "Alice employer", limit=5, scope="edges")

        assert graph_data["node_count"] >= 2
        assert graph_data["edge_count"] >= 1
        assert filtered.filtered_count >= 1
        assert search.edges
