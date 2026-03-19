import json
from pathlib import Path

from backend.app.parity_engine.baseline_capture import (
    ZepBaselineCaptureRunner,
    build_artifact_paths,
    write_baseline_bundle,
)
from backend.app.parity_engine.contracts import BaselineSnapshot, CorpusItem


def test_build_artifact_paths_returns_stable_layout(tmp_path):
    paths = build_artifact_paths(tmp_path, "campus_case_01")

    assert paths["graph"].name == "graph.json"
    assert paths["search"].name == "search.json"
    assert paths["profile"].name == "profile.json"
    assert paths["report"].name == "report.json"
    assert paths["memory_update"].name == "memory_update.json"
    assert paths["metadata"].name == "metadata.json"
    assert paths["raw_api_examples"].name == "raw_api_examples.json"


def test_write_baseline_bundle_persists_expected_files(tmp_path):
    snapshot = BaselineSnapshot.model_validate(
        {
            "case_id": "campus_case_01",
            "graph": {
                "nodes": [{"uuid_": "node-1", "name": "Alice"}],
                "edges": [{"uuid_": "edge-1", "name": "WORKS_FOR"}],
            },
            "search": [
                {
                    "query": "alice employer",
                    "scope": "edges",
                    "edges": [{"uuid_": "edge-1"}],
                }
            ],
            "profile": {"context": "Alice works for Example Labs."},
            "report": {"tool_outputs": {"search": {"count": 1}}},
            "memory_update": {"delta": {"added_edges": 1}},
        }
    )

    paths = write_baseline_bundle(
        output_root=tmp_path,
        snapshot=snapshot,
        metadata={"provider": "zep"},
        raw_api_examples={"graph.create": {"graph_id": "campus_case_01"}},
    )

    assert paths["case_dir"] == tmp_path / "campus_case_01"
    graph_payload = json.loads(paths["graph"].read_text(encoding="utf-8"))
    metadata_payload = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    raw_examples_payload = json.loads(paths["raw_api_examples"].read_text(encoding="utf-8"))

    assert graph_payload["nodes"][0]["name"] == "Alice"
    assert metadata_payload["provider"] == "zep"
    assert raw_examples_payload["graph.create"]["graph_id"] == "campus_case_01"


def test_capture_runner_uses_probe_and_writes_canonical_artifacts(tmp_path):
    class FakeProbe:
        def capture_case(self, case):
            snapshot = BaselineSnapshot.model_validate(
                {
                    "case_id": case.id,
                    "graph": {"nodes": [{"uuid_": "node-1", "name": "Alice"}], "edges": []},
                    "search": [{"query": case.queries[0], "scope": "edges", "edges": []}],
                    "profile": {"context": "Alice context"},
                    "report": {"tool_outputs": {"search": []}},
                    "memory_update": {"delta": {"added_edges": 0}},
                }
            )
            return snapshot, {"provider": "zep"}, {"graph.create": {"graph_id": case.id}}

    runner = ZepBaselineCaptureRunner(FakeProbe())
    case = CorpusItem.model_validate(
        {
            "id": "campus_case_01",
            "documents": ["docs/a.md"],
            "simulation_requirement": "Analyze campus activism dynamics",
            "queries": ["student protest"],
            "expected_outputs": ["graph", "search", "profile", "report", "memory_update"],
        }
    )

    paths = runner.capture_case(case, tmp_path)

    assert (tmp_path / "campus_case_01" / "graph.json").exists()
    assert json.loads(paths["metadata"].read_text(encoding="utf-8"))["provider"] == "zep"
