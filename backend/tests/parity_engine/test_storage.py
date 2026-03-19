from backend.app.parity_engine.storage import MetadataStore


def test_metadata_store_persists_graph_episode_and_ontology(tmp_path):
    store = MetadataStore(tmp_path / "parity.sqlite3")
    graph_id = "mirofish_graph_01"
    episode_id = "episode_01"
    ontology = {"entity_types": [{"name": "Person"}], "edge_types": []}

    store.upsert_graph(graph_id=graph_id, name="Parity Test", description="desc")
    store.save_ontology(graph_id=graph_id, ontology=ontology)
    store.upsert_episode(
        episode_id=episode_id,
        graph_id=graph_id,
        body="Alice founded Example Labs.",
        status="queued",
    )

    assert store.get_graph(graph_id)["name"] == "Parity Test"
    assert store.get_ontology(graph_id) == ontology
    assert store.get_episode(episode_id)["status"] == "queued"
