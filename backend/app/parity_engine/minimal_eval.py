"""Ultra-light parity evaluation for quick iteration before full cutover review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .metrics import overlap_at_k, relative_delta


MINIMAL_THRESHOLDS = {
    "node_count_delta": 0.10,
    "edge_count_delta": 0.15,
    "top_10_edge_overlap": 0.80,
}

MAX_THRESHOLD_METRICS = {"node_count_delta", "edge_count_delta"}


def run_minimal_evaluation(
    baseline_root: str | Path,
    candidate_root: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    baseline_root = Path(baseline_root)
    candidate_root = Path(candidate_root)
    case_ids = sorted(
        path.name
        for path in baseline_root.iterdir()
        if path.is_dir() and (candidate_root / path.name).is_dir()
    )

    case_summaries: dict[str, Any] = {}
    for case_id in case_ids:
        case_summaries[case_id] = evaluate_case(
            baseline_root / case_id,
            candidate_root / case_id,
        )

    overall = {
        "candidate_for_full_eval": all(
            case["candidate_for_full_eval"] for case in case_summaries.values()
        ),
        "thresholds": MINIMAL_THRESHOLDS,
        "case_count": len(case_summaries),
    }
    summary = {"overall": overall, "cases": case_summaries}

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return summary


def evaluate_case(baseline_case_dir: str | Path, candidate_case_dir: str | Path) -> dict[str, Any]:
    baseline = _load_case_bundle(baseline_case_dir)
    candidate = _load_case_bundle(candidate_case_dir)

    baseline_node_ids = _extract_ids(baseline["graph"].get("nodes", []))
    candidate_node_ids = _extract_ids(candidate["graph"].get("nodes", []))
    baseline_edge_ids = _extract_ids(baseline["graph"].get("edges", []))
    candidate_edge_ids = _extract_ids(candidate["graph"].get("edges", []))
    baseline_search_edge_ids = _extract_search_edge_ids(baseline["search"])
    candidate_search_edge_ids = _extract_search_edge_ids(candidate["search"])

    metrics = {
        "node_count_delta": relative_delta(len(baseline_node_ids), len(candidate_node_ids)),
        "edge_count_delta": relative_delta(len(baseline_edge_ids), len(candidate_edge_ids)),
        "top_10_edge_overlap": overlap_at_k(baseline_search_edge_ids, candidate_search_edge_ids, 10),
    }
    candidate_for_full_eval = all(
        _passes_metric(name, value, MINIMAL_THRESHOLDS[name]) for name, value in metrics.items()
    )
    return {
        "metrics": metrics,
        "candidate_for_full_eval": candidate_for_full_eval,
    }


def _load_case_bundle(case_dir: str | Path) -> dict[str, Any]:
    case_dir = Path(case_dir)
    bundle = {}
    for name in ("graph", "search"):
        bundle[name] = json.loads((case_dir / f"{name}.json").read_text(encoding="utf-8"))
    return bundle


def _extract_ids(records: list[dict[str, Any]]) -> list[str]:
    ids = []
    for record in records:
        record_id = record.get("uuid") or record.get("uuid_") or record.get("episode_uuid")
        if record_id:
            ids.append(str(record_id))
    return ids


def _extract_search_edge_ids(search_payload: Any) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    if not isinstance(search_payload, list):
        return ids
    for item in search_payload:
        if not isinstance(item, dict):
            continue
        for edge in item.get("edges", []):
            if not isinstance(edge, dict):
                continue
            edge_id = edge.get("uuid") or edge.get("uuid_")
            if edge_id and str(edge_id) not in seen:
                ids.append(str(edge_id))
                seen.add(str(edge_id))
    return ids


def _passes_metric(name: str, value: float, threshold: float) -> bool:
    if name in MAX_THRESHOLD_METRICS:
        return value <= threshold
    return value >= threshold
