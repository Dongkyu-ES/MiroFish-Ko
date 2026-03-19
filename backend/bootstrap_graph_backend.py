"""Bootstrap local zep_cloud shim for local graph-backend modes."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from backend.app.parity_engine.cutover import ensure_local_primary_cutover_allowed

LOCAL_SHIM_MODES = {"local_primary"}


def bootstrap_graph_backend() -> str | None:
    graph_backend = os.environ.get("GRAPH_BACKEND", "zep")
    if graph_backend not in LOCAL_SHIM_MODES:
        return None

    if os.environ.get("GRAPHITI_ALLOW_LOCAL_EVAL", "false").lower() != "true":
        ensure_local_primary_cutover_allowed()

    shim_root = Path(__file__).resolve().parent / "shims" / "local_zep"
    shim_path = str(shim_root)
    if shim_path not in sys.path:
        sys.path.insert(0, shim_path)
    for module_name in list(sys.modules):
        if module_name == "zep_cloud" or module_name.startswith("zep_cloud."):
            sys.modules.pop(module_name, None)
    return shim_path
