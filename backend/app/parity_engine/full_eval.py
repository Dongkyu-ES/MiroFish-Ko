"""Full parity scorecard evaluation between baseline and local candidate artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from .evaluator import DownstreamParityEvaluator
from .hard_gates import evaluate_hard_gates
from .metrics import attribute_fill_rate, f1_from_sets, ndcg_at_k, overlap_at_k, relative_delta
from .scorecard import build_scorecard, persist_cutover_status


def run_full_parity_evaluation(
    baseline_root: str | Path,
    candidate_root: str | Path,
    output_root: str | Path,
    verification_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    baseline_root = Path(baseline_root)
    candidate_root = Path(candidate_root)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    case_ids = sorted(
        path.name
        for path in baseline_root.iterdir()
        if path.is_dir() and (candidate_root / path.name).is_dir()
    )
    evaluator = DownstreamParityEvaluator()
    case_reports: dict[str, Any] = {}
    aggregate_inputs: list[dict[str, float]] = []

    for case_id in case_ids:
        report = evaluate_case(
            baseline_root / case_id,
            candidate_root / case_id,
            evaluator=evaluator,
        )
        case_reports[case_id] = report
        aggregate_inputs.append(report["metrics"])
        case_dir = output_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "scorecard.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    aggregate_metrics = aggregate_metrics_worst_case(aggregate_inputs)
    scorecard = build_scorecard(aggregate_metrics)
    hard_gate_result = evaluate_hard_gates(candidate_root, verification_manifest_path)
    cutover_path = persist_cutover_status(output_root, scorecard, hard_gates_passed=hard_gate_result["hard_gates_passed"])
    summary = {
        "cases": case_reports,
        "aggregate": {
            "metrics": aggregate_metrics,
            "scorecard": scorecard.model_dump(mode="json"),
            "hard_gates": hard_gate_result,
            "cutover_status_path": str(cutover_path),
        },
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def evaluate_case(
    baseline_case_dir: str | Path,
    candidate_case_dir: str | Path,
    evaluator: DownstreamParityEvaluator,
) -> dict[str, Any]:
    baseline = _load_case_bundle(baseline_case_dir)
    candidate = _load_case_bundle(candidate_case_dir)

    baseline_nodes = baseline["graph"].get("nodes", [])
    candidate_nodes = candidate["graph"].get("nodes", [])
    baseline_edges = baseline["graph"].get("edges", [])
    candidate_edges = candidate["graph"].get("edges", [])

    baseline_node_ids = _extract_ids(baseline_nodes)
    candidate_node_ids = _extract_ids(candidate_nodes)
    baseline_edge_ids = _extract_ids(baseline_edges)
    candidate_edge_ids = _extract_ids(candidate_edges)

    metrics = {
        "node_count_delta": relative_delta(len(baseline_node_ids), len(candidate_node_ids)),
        "edge_count_delta": relative_delta(len(baseline_edge_ids), len(candidate_edge_ids)),
        "entity_label_f1": _label_f1(baseline_nodes, candidate_nodes),
        "edge_type_f1": f1_from_sets(_extract_edge_types(baseline_edges), _extract_edge_types(candidate_edges)),
        "attribute_fill_rate_parity": _attribute_fill_rate_parity(baseline_nodes, candidate_nodes, baseline_edges, candidate_edges),
        "top_10_edge_overlap": _search_overlap(baseline["search"], candidate["search"], "edges"),
        "top_10_node_overlap": _search_overlap(baseline["search"], candidate["search"], "nodes"),
        "ndcg_at_10": _search_ndcg(baseline["search"], candidate["search"], "edges"),
        "fact_hit_rate": _fact_hit_rate(baseline["search"], candidate["search"]),
        "simulation_prepare_success_rate": _simulation_prepare_rate(candidate["profile"], candidate["report"], candidate["memory_update"]),
        "profile_completeness_score": evaluator.compare_profile_outputs(baseline["profile"], candidate["profile"]),
        "report_tool_usefulness_score": 5.0 * evaluator.compare_report_outputs(baseline["report"], candidate["report"]),
        "report_exception_rate": 0.0 if "tool_outputs" in candidate["report"] else 1.0,
    }
    return {
        "metrics": metrics,
        "scorecard": build_scorecard(metrics).model_dump(mode="json"),
    }


def aggregate_metrics_worst_case(case_metrics: list[dict[str, float]]) -> dict[str, float]:
    if not case_metrics:
        return {}
    keys = case_metrics[0].keys()
    aggregate: dict[str, float] = {}
    for key in keys:
        values = [item[key] for item in case_metrics]
        if key in {"node_count_delta", "edge_count_delta", "report_exception_rate"}:
            aggregate[key] = max(values)
        else:
            aggregate[key] = min(values)
    return aggregate


def _load_case_bundle(case_dir: str | Path) -> dict[str, Any]:
    case_dir = Path(case_dir)
    bundle = {}
    for name in ("graph", "search", "profile", "report", "memory_update"):
        bundle[name] = json.loads((case_dir / f"{name}.json").read_text(encoding="utf-8"))
    return bundle


def _extract_ids(records: list[dict[str, Any]]) -> list[str]:
    ids = []
    for record in records:
        record_id = record.get("uuid") or record.get("uuid_") or record.get("episode_uuid")
        if record_id:
            ids.append(str(record_id))
    return ids


def _extract_labels(nodes: list[dict[str, Any]]) -> list[str]:
    labels = []
    for node in nodes:
        labels.extend(node.get("labels", []))
    return labels


def _label_f1(baseline_nodes: list[dict[str, Any]], candidate_nodes: list[dict[str, Any]]) -> float:
    return f1_from_sets(_extract_labels(baseline_nodes), _extract_labels(candidate_nodes))


def _extract_edge_types(edges: list[dict[str, Any]]) -> list[str]:
    return [str(edge.get("name", "")) for edge in edges if edge.get("name")]


def _attribute_fill_rate_parity(
    baseline_nodes: list[dict[str, Any]],
    candidate_nodes: list[dict[str, Any]],
    baseline_edges: list[dict[str, Any]],
    candidate_edges: list[dict[str, Any]],
) -> float:
    node_fields = ["summary", "attributes"]
    edge_fields = ["fact", "attributes", "valid_at"]
    baseline_score = mean(
        [
            attribute_fill_rate(baseline_nodes, node_fields),
            attribute_fill_rate(baseline_edges, edge_fields),
        ]
    )
    candidate_score = mean(
        [
            attribute_fill_rate(candidate_nodes, node_fields),
            attribute_fill_rate(candidate_edges, edge_fields),
        ]
    )
    if baseline_score == 0:
        return 1.0 if candidate_score == 0 else 0.0
    return min(candidate_score / baseline_score, 1.0)


def _search_overlap(baseline_search: list[dict[str, Any]], candidate_search: list[dict[str, Any]], key: str) -> float:
    overlaps = []
    for baseline_item, candidate_item in zip(baseline_search, candidate_search):
        overlaps.append(
            overlap_at_k(
                _extract_ids(baseline_item.get(key, [])),
                _extract_ids(candidate_item.get(key, [])),
                10,
            )
        )
    return mean(overlaps) if overlaps else 0.0


def _search_ndcg(baseline_search: list[dict[str, Any]], candidate_search: list[dict[str, Any]], key: str) -> float:
    scores = []
    for baseline_item, candidate_item in zip(baseline_search, candidate_search):
        scores.append(
            ndcg_at_k(
                _extract_ids(baseline_item.get(key, [])),
                _extract_ids(candidate_item.get(key, [])),
                10,
            )
        )
    return mean(scores) if scores else 0.0


def _fact_hit_rate(baseline_search: list[dict[str, Any]], candidate_search: list[dict[str, Any]]) -> float:
    scores = []
    for baseline_item, candidate_item in zip(baseline_search, candidate_search):
        baseline_facts = set(baseline_item.get("facts", []))
        candidate_facts = set(candidate_item.get("facts", []))
        if not baseline_facts:
            scores.append(1.0 if not candidate_facts else 0.0)
        else:
            scores.append(len(baseline_facts & candidate_facts) / len(baseline_facts))
    return mean(scores) if scores else 0.0


def _simulation_prepare_rate(profile_payload: dict[str, Any], report_payload: dict[str, Any], memory_payload: dict[str, Any]) -> float:
    return 1.0 if profile_payload.get("profiles") is not None and report_payload.get("tool_outputs") is not None and memory_payload.get("delta") is not None else 0.0
