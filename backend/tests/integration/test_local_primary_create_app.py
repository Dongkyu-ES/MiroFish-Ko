import importlib
from pathlib import Path


def test_create_app_bootstraps_local_shim_in_local_primary(monkeypatch, tmp_path):
    artifact_dir = Path(tmp_path) / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "cutover_status.json").write_text(
        '{"verdict":"eligible_for_local_primary","hard_gates_passed":true}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("GRAPHITI_PARITY_ARTIFACT_DIR", str(artifact_dir))
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    import backend.app as app_module
    import backend.app.services.graph_builder as graph_builder_module

    importlib.reload(app_module)
    importlib.reload(graph_builder_module)

    app = app_module.create_app()

    assert app is not None
    assert "shims/local_zep" in graph_builder_module.Zep.__module__ or graph_builder_module.Zep.__module__ == "zep_cloud.client"
    assert "local_zep" in importlib.import_module("zep_cloud.client").__file__
