"""Cutover gate helpers for local_primary activation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_PARITY_ARTIFACT_DIR = "./artifacts/parity"
DEFAULT_CUTOVER_STATUS_FILE = "cutover_status.json"


def get_parity_artifact_dir() -> Path:
    return Path(os.environ.get("GRAPHITI_PARITY_ARTIFACT_DIR", DEFAULT_PARITY_ARTIFACT_DIR))


def get_cutover_status_path() -> Path:
    return get_parity_artifact_dir() / DEFAULT_CUTOVER_STATUS_FILE


def load_cutover_status() -> dict[str, Any] | None:
    path = get_cutover_status_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def cutover_gate_passed(status: dict[str, Any] | None = None) -> bool:
    payload = load_cutover_status() if status is None else status
    if not payload:
        return False
    return (
        payload.get("verdict") == "eligible_for_local_primary"
        and bool(payload.get("hard_gates_passed"))
    )


def ensure_local_primary_cutover_allowed() -> dict[str, Any]:
    status = load_cutover_status()
    if not cutover_gate_passed(status):
        raise RuntimeError(
            "local_primary cutover gate is not satisfied; run live parity baseline and hard-gate verification first"
        )
    return status or {}
