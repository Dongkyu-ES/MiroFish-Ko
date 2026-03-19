from backend.app.parity_engine.shadow_eval import ShadowEvalCollector
from backend.tests.integration._engine_test_server import running_engine_server


def test_shadow_eval_collector_mirrors_to_local_engine_and_writes_artifact(monkeypatch, tmp_path):
    with running_engine_server(tmp_path) as base_url:
        monkeypatch.setenv("GRAPH_BACKEND", "shadow_eval")
        monkeypatch.setenv("ENGINE_SHADOW_EVAL_ENABLED", "true")
        monkeypatch.setenv("ENGINE_BASE_URL", base_url)
        monkeypatch.setenv("GRAPHITI_PARITY_ARTIFACT_DIR", str(tmp_path / "artifacts"))
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        collector = ShadowEvalCollector(
            graph_backend="shadow_eval",
            enabled=True,
            base_url=base_url,
            artifact_dir=str(tmp_path / "artifacts"),
        )
        collector.ensure_graph("shadow_graph_01", "Shadow Graph", "desc")
        collector.set_ontology(
            "shadow_graph_01",
            {
                "entity_types": [
                    {"name": "Person", "description": "A person", "attributes": []},
                    {"name": "Company", "description": "A company", "attributes": []},
                ],
                "edge_types": [
                    {
                        "name": "works_for",
                        "description": "Employment relationship",
                        "source_targets": [{"source": "Person", "target": "Company"}],
                        "attributes": [],
                    }
                ],
            },
        )
        collector.add_text_batch("shadow_graph_01", ["Alice works for Example Labs."])
        payload = collector.capture_search(
            "shadow_graph_01",
            "Alice employer",
            limit=5,
            scope="edges",
            source_payload={"facts": ["Alice works for Example Labs."]},
        )

        assert payload["edges"]
        assert (tmp_path / "artifacts" / "shadow_eval" / "shadow_graph_01" / "search.json").exists()
