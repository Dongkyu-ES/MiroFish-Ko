from pathlib import Path

import pytest

from backend.bootstrap_graph_backend import bootstrap_graph_backend


def test_shadow_eval_does_not_bootstrap_local_shim(monkeypatch):
    monkeypatch.setenv("GRAPH_BACKEND", "shadow_eval")

    shim_path = bootstrap_graph_backend()

    assert shim_path is None


def test_local_primary_requires_passing_cutover_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("GRAPHITI_PARITY_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("GRAPHITI_ALLOW_LOCAL_EVAL", "false")

    with pytest.raises(RuntimeError, match="cutover gate"):
        bootstrap_graph_backend()


def test_local_primary_bootstraps_when_cutover_gate_passes(monkeypatch, tmp_path):
    artifact_dir = Path(tmp_path)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "cutover_status.json").write_text(
        '{"verdict":"eligible_for_local_primary","hard_gates_passed":true}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GRAPH_BACKEND", "local_primary")
    monkeypatch.setenv("GRAPHITI_PARITY_ARTIFACT_DIR", str(artifact_dir))

    shim_path = bootstrap_graph_backend()

    assert shim_path is not None
