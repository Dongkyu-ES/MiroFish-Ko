import json
from pathlib import Path

from backend.app.parity_engine.contracts import BaselineSnapshot, CorpusItem


FIXTURES_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "corpus_manifest.json"
ROOT_REQUIREMENTS_PATH = Path(__file__).resolve().parents[3] / "requirements.txt"


def test_corpus_contract_has_required_sections():
    item = CorpusItem.model_validate(
        {
            "id": "campus_case_01",
            "documents": ["docs/a.md"],
            "simulation_requirement": "Analyze campus activism dynamics",
            "queries": ["student protest", "faculty reaction"],
            "expected_outputs": ["graph", "search", "profile", "report", "memory_update"],
        }
    )
    assert item.id == "campus_case_01"
    assert item.ontology_mode == "generate"


def test_manifest_contains_canonical_cases():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    items = [CorpusItem.model_validate(item) for item in manifest["cases"]]

    assert {item.id for item in items} == {
        "ko_alias_case",
        "en_temporal_case",
        "ko_report_case",
        "en_profile_case",
        "sim_memory_case",
    }
    assert {item.language for item in items} >= {"ko", "en"}
    assert all(item.documents for item in items)
    assert all(item.queries for item in items)
    assert all(item.expected_outputs for item in items)


def test_baseline_snapshot_has_required_sections():
    snapshot = BaselineSnapshot.model_validate(
        {
            "case_id": "ko_alias_case",
            "graph": {
                "nodes": [{"uuid_": "node-1", "name": "Alice"}],
                "edges": [{"uuid_": "edge-1", "name": "WORKS_FOR"}],
            },
            "search": [
                {
                    "query": "alice employer",
                    "scope": "edges",
                    "edges": [{"uuid_": "edge-1"}],
                    "nodes": [{"uuid_": "node-1"}],
                }
            ],
            "profile": {"context": "Alice works for Example Labs."},
            "report": {"tool_outputs": {"search": []}, "sections": []},
            "memory_update": {"delta": {"added_edges": 1}, "episodes": ["episode-1"]},
            "scorecard": {"verdict": "shadow_only", "metrics": {"top_10_edge_overlap": 0.8}},
        }
    )

    assert snapshot.graph.nodes[0]["uuid_"] == "node-1"
    assert snapshot.search[0].scope == "edges"
    assert snapshot.scorecard.verdict == "shadow_only"


def test_root_requirements_include_backend_and_graphiti_kuzu():
    requirements = ROOT_REQUIREMENTS_PATH.read_text(encoding="utf-8")

    assert "flask>=3.0.0" in requirements
    assert "zep-cloud==3.13.0" in requirements
    assert "graphiti-core[kuzu]" in requirements
