import json

from backend.app.parity_engine.minimal_eval import run_minimal_evaluation


def _write_case(root, case_id, payload):
    case_dir = root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    for name, value in payload.items():
        (case_dir / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def test_minimal_eval_reports_candidate_for_full_eval_when_core_metrics_pass(tmp_path):
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    payload = {
        "graph": {
            "nodes": [{"uuid": "n1"}, {"uuid": "n2"}],
            "edges": [{"uuid": "e1"}, {"uuid": "e2"}],
        },
        "search": [
            {"query": "q1", "edges": [{"uuid": "e1"}], "nodes": [{"uuid": "n1"}]},
            {"query": "q2", "edges": [{"uuid": "e2"}], "nodes": [{"uuid": "n2"}]},
        ],
        "profile": {"profiles": [{"name": "Alice"}], "context": "Alice context"},
        "report": {"tool_outputs": {"search": ["fact"]}},
        "memory_update": {"delta": {"edge_count_after": 3}, "episodes": ["ep1"]},
    }
    _write_case(baseline_root, "case_01", payload)
    _write_case(candidate_root, "case_01", payload)

    summary = run_minimal_evaluation(baseline_root, candidate_root, tmp_path / "minimal_eval.json")

    assert summary["overall"]["candidate_for_full_eval"] is True
    assert summary["cases"]["case_01"]["metrics"]["node_count_delta"] == 0.0


def test_minimal_eval_flags_iteration_when_core_metrics_fail(tmp_path):
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    _write_case(
        baseline_root,
        "case_01",
        {
            "graph": {"nodes": [{"uuid": "n1"}], "edges": [{"uuid": "e1"}]},
            "search": [{"query": "q1", "edges": [{"uuid": "e1"}], "nodes": [{"uuid": "n1"}]}],
            "profile": {"profiles": [{"name": "Alice"}], "context": "Alice context"},
            "report": {"tool_outputs": {"search": ["fact"]}},
            "memory_update": {"delta": {"edge_count_after": 2}, "episodes": ["ep1"]},
        },
    )
    _write_case(
        candidate_root,
        "case_01",
        {
            "graph": {"nodes": [{"uuid": "n9"}, {"uuid": "n10"}], "edges": []},
            "search": [{"query": "q1", "edges": [], "nodes": []}],
            "profile": {"profiles": [], "context": ""},
            "report": {"tool_outputs": {}},
            "memory_update": {"delta": {"edge_count_after": 0}, "episodes": []},
        },
    )

    summary = run_minimal_evaluation(baseline_root, candidate_root)

    assert summary["overall"]["candidate_for_full_eval"] is False
    assert summary["cases"]["case_01"]["metrics"]["top_10_edge_overlap"] == 0.0
