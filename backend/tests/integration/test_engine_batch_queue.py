import time

from backend.app.parity_engine.server import create_engine_app


def test_engine_batch_returns_all_episode_uuids_and_processes_them(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    monkeypatch.setenv("GRAPHITI_DB_PATH", str(tmp_path / "graphiti.kuzu"))
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "dummy-model")

    from backend.app.parity_engine.extractor import GraphitiExtractionOverlay

    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "en",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 2,
            "typed_entity_count": 2,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "Alice", "type": "Person", "attributes": {"name": "Alice"}},
                {"name": "Example Labs", "type": "Company", "attributes": {"name": "Example Labs"}},
            ],
            "edges": [
                {
                    "name": "WORKS_FOR",
                    "source": "Alice",
                    "target": "Example Labs",
                    "fact": text,
                }
            ],
        },
    )

    app, _ = create_engine_app(testing=True)
    client = app.test_client()
    graph_id = "graph_queue_test"

    create_response = client.post(
        "/v1/graphs",
        json={"graph_id": graph_id, "name": "Queue Test", "description": "desc"},
    )
    assert create_response.status_code == 200

    batch_response = client.post(
        f"/v1/graphs/{graph_id}/episodes/batch",
        json={
            "episodes": [
                {"type": "text", "data": "Alice works for Example Labs."},
                {"type": "text", "data": "Bob leads Example Labs."},
            ]
        },
    )

    payload = batch_response.get_json()
    assert batch_response.status_code == 200
    assert payload["count"] == 2
    assert len(payload["episode_uuids"]) == 2
    assert len(set(payload["episode_uuids"])) == 2

    deadline = time.time() + 3
    processed = False
    while time.time() < deadline:
        statuses = [
            client.get(f"/v1/episodes/{episode_uuid}").get_json()["processed"]
            for episode_uuid in payload["episode_uuids"]
        ]
        if all(statuses):
            processed = True
            break
        time.sleep(0.05)

    assert processed is True


def test_engine_batch_worker_continues_after_episode_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    monkeypatch.setenv("GRAPHITI_DB_PATH", str(tmp_path / "graphiti.kuzu"))
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "dummy-model")

    from backend.app.parity_engine.extractor import GraphitiExtractionOverlay

    calls = {"count": 0}

    def flaky_extract(self, text, ontology):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("synthetic extraction failure")
        return {
            "language": "en",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 2,
            "typed_entity_count": 2,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "Bob", "type": "Person", "attributes": {"name": "Bob"}},
                {"name": "Example Labs", "type": "Company", "attributes": {"name": "Example Labs"}},
            ],
            "edges": [
                {
                    "name": "WORKS_FOR",
                    "source": "Bob",
                    "target": "Example Labs",
                    "fact": text,
                }
            ],
        }

    monkeypatch.setattr(GraphitiExtractionOverlay, "extract", flaky_extract)

    app, _ = create_engine_app(testing=True)
    client = app.test_client()
    graph_id = "graph_queue_failure_test"

    assert client.post(
        "/v1/graphs",
        json={"graph_id": graph_id, "name": "Queue Failure Test", "description": "desc"},
    ).status_code == 200
    assert client.post(
        f"/v1/graphs/{graph_id}/ontology",
        json={
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
    ).status_code == 200

    batch_payload = client.post(
        f"/v1/graphs/{graph_id}/episodes/batch",
        json={
            "episodes": [
                {"type": "text", "data": "Alice works for Example Labs."},
                {"type": "text", "data": "Bob works for Example Labs."},
            ]
        },
    ).get_json()

    deadline = time.time() + 3
    statuses = {}
    while time.time() < deadline:
        statuses = {
            episode_uuid: client.get(f"/v1/episodes/{episode_uuid}").get_json()["status"]
            for episode_uuid in batch_payload["episode_uuids"]
        }
        if "failed" in statuses.values() and "processed" in statuses.values():
            break
        time.sleep(0.05)

    assert "failed" in statuses.values()
    assert "processed" in statuses.values()
