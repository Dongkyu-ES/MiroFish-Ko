from backend.bootstrap_graph_backend import bootstrap_graph_backend


def test_local_primary_bootstrap_prepends_local_zep_shim(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "cutover_status.json").write_text(
        '{"verdict":"eligible_for_local_primary","hard_gates_passed":true}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("GRAPHITI_PARITY_ARTIFACT_DIR", str(artifact_dir))
    bootstrap_graph_backend()

    import zep_cloud
    from zep_cloud.client import Zep

    assert "shims/local_zep" in zep_cloud.__file__
    assert Zep.__module__ == "zep_cloud.client"
