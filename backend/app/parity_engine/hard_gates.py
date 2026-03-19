"""Automatic hard-gate evaluation for local_primary cutover."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_HARD_GATES = {
    "route_groups_passed",
    "response_schemas_passed",
    "state_transitions_passed",
    "output_files_passed",
    "engine_health_passed",
    "migration_runtime_passed",
    "multilingual_flow_passed",
}

REQUIRED_CASE_FILES = {
    "graph.json",
    "search.json",
    "profile.json",
    "report.json",
    "memory_update.json",
    "metadata.json",
    "raw_api_examples.json",
}


def evaluate_hard_gates(
    candidate_root: str | Path,
    verification_manifest_path: str | Path | None,
) -> dict[str, Any]:
    candidate_root = Path(candidate_root)
    checks = {
        "candidate_artifacts_complete": _candidate_artifacts_complete(candidate_root),
        "candidate_authoritative": _candidate_authoritative(candidate_root),
        "verification_manifest_present": False,
    }

    manifest_payload: dict[str, Any] = {}
    if verification_manifest_path is not None:
        manifest_path = Path(verification_manifest_path)
        if manifest_path.exists():
            checks["verification_manifest_present"] = True
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            gate_payload = manifest_payload.get("hard_gates", {})
            for gate in REQUIRED_HARD_GATES:
                checks[gate] = bool(gate_payload.get(gate))
        else:
            for gate in REQUIRED_HARD_GATES:
                checks[gate] = False
    else:
        for gate in REQUIRED_HARD_GATES:
            checks[gate] = False

    hard_gates_passed = all(checks.get(gate, False) for gate in REQUIRED_HARD_GATES) and checks["candidate_artifacts_complete"] and checks["candidate_authoritative"]
    return {
        "hard_gates_passed": hard_gates_passed,
        "checks": checks,
        "manifest": manifest_payload,
    }


def _candidate_artifacts_complete(candidate_root: Path) -> bool:
    case_dirs = [path for path in candidate_root.iterdir() if path.is_dir()] if candidate_root.exists() else []
    if not case_dirs:
        return False
    return all(REQUIRED_CASE_FILES.issubset({artifact.name for artifact in case_dir.iterdir() if artifact.is_file()}) for case_dir in case_dirs)


def _candidate_authoritative(candidate_root: Path) -> bool:
    case_dirs = [path for path in candidate_root.iterdir() if path.is_dir()] if candidate_root.exists() else []
    if not case_dirs:
        return False
    for case_dir in case_dirs:
        metadata_path = case_dir / "metadata.json"
        if not metadata_path.exists():
            return False
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not metadata.get("authoritative"):
            return False
    return True
