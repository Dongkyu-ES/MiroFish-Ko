import json

from backend.app.parity_engine.hard_gates import evaluate_hard_gates


def _write_case(root, case_id):
    case_dir = root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    for name in ("graph", "search", "profile", "report", "memory_update", "metadata", "raw_api_examples"):
        payload = {"provider": "local_engine", "authoritative": True} if name == "metadata" else {}
        (case_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_hard_gate_evaluator_requires_authoritative_candidate_and_manifest(tmp_path):
    candidate_root = tmp_path / "candidate"
    _write_case(candidate_root, "ko_alias_case")
    _write_case(candidate_root, "en_profile_case")
    manifest_path = tmp_path / "verification.json"
    manifest_path.write_text(
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

    result = evaluate_hard_gates(candidate_root, manifest_path)

    assert result["hard_gates_passed"] is True


def test_hard_gate_evaluator_fails_without_manifest(tmp_path):
    candidate_root = tmp_path / "candidate"
    _write_case(candidate_root, "ko_alias_case")
    result = evaluate_hard_gates(candidate_root, tmp_path / "missing.json")
    assert result["hard_gates_passed"] is False
