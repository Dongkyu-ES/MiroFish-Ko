from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REQUIRED_TESTS = [
    "backend/tests/integration/test_engine_service_boot.py",
    "backend/tests/integration/test_engine_health_ready.py",
    "backend/tests/integration/test_local_primary_mirofish_services.py",
    "backend/tests/integration/test_project_migration_routes.py",
    "backend/tests/integration/test_existing_graph_id_coexistence.py",
    "backend/tests/integration/test_parity_multilingual_flow.py",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run automatic hard-gate checks")
    parser.add_argument("--output", default="artifacts/parity/hard_gate_manifest.json")
    args = parser.parse_args()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *REQUIRED_TESTS, "-q"],
        capture_output=True,
        text=True,
    )
    hard_gates = {
        "route_groups_passed": result.returncode == 0,
        "response_schemas_passed": result.returncode == 0,
        "state_transitions_passed": result.returncode == 0,
        "output_files_passed": result.returncode == 0,
        "engine_health_passed": result.returncode == 0,
        "migration_runtime_passed": result.returncode == 0,
        "multilingual_flow_passed": result.returncode == 0,
    }
    payload = {
        "hard_gates": hard_gates,
        "pytest_returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
