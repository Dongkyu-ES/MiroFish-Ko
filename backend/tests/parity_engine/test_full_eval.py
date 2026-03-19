import json

from backend.app.parity_engine.full_eval import run_full_parity_evaluation


def _write_case(root, case_id, payload):
    case_dir = root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    for name, value in payload.items():
        (case_dir / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def test_full_eval_writes_summary_and_cutover_status(tmp_path):
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    payload = {
        "graph": {
            "nodes": [{"uuid": "n1", "labels": ["Person"], "summary": "Alice", "attributes": {"name": "Alice"}}],
            "edges": [{"uuid": "e1", "name": "WORKS_FOR", "fact": "Alice works for Example Labs.", "attributes": {"fact": "Alice works for Example Labs."}, "valid_at": "2026-01-01T00:00:00Z"}],
        },
        "search": [{"query": "q1", "edges": [{"uuid": "e1"}], "nodes": [{"uuid": "n1"}], "facts": ["Alice works for Example Labs."]}],
        "profile": {"profiles": [{"name": "Alice"}], "context": "Alice context"},
        "report": {"tool_outputs": {"search": ["fact"]}},
        "memory_update": {"delta": {"edge_count_after": 2}, "episodes": ["ep1"]},
    }
    _write_case(baseline, "case_01", payload)
    _write_case(candidate, "case_01", payload)
    (candidate / "case_01" / "metadata.json").write_text(
        json.dumps({"provider": "local_engine", "authoritative": True}),
        encoding="utf-8",
    )
    manifest = tmp_path / "verification_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "hard_gates": {
                    "route_groups_passed": True,
                    "response_schemas_passed": True,
                    "state_transitions_passed": True,
                    "output_files_passed": True,
                    "engine_health_passed": True,
                    "migration_runtime_passed": True,
                    "multilingual_flow_passed": True,
                }
            }
        ),
        encoding="utf-8",
    )

    summary = run_full_parity_evaluation(
        baseline_root=baseline,
        candidate_root=candidate,
        output_root=tmp_path / "full",
        verification_manifest_path=manifest,
    )

    assert summary["aggregate"]["scorecard"]["verdict"] == "eligible_for_local_primary"
    assert (tmp_path / "full" / "cutover_status.json").exists()
