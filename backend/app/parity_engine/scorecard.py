"""Scorecard assembly for parity metrics and cutover gating."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import ParityScorecard


DEFAULT_THRESHOLDS = {
    "node_count_delta": 0.10,
    "edge_count_delta": 0.15,
    "entity_label_f1": 0.90,
    "edge_type_f1": 0.85,
    "attribute_fill_rate_parity": 0.85,
    "top_10_edge_overlap": 0.80,
    "top_10_node_overlap": 0.80,
    "ndcg_at_10": 0.85,
    "fact_hit_rate": 0.85,
    "simulation_prepare_success_rate": 1.0,
    "profile_completeness_score": 0.90,
    "report_tool_usefulness_score": 4.0,
    "report_exception_rate": 0.0,
}

MAX_THRESHOLD_METRICS = {
    "node_count_delta",
    "edge_count_delta",
    "report_exception_rate",
}


def build_scorecard(metrics: dict[str, float], thresholds: dict[str, float] | None = None) -> ParityScorecard:
    """Build a parity scorecard and derive the cutover verdict."""

    effective_thresholds = thresholds or DEFAULT_THRESHOLDS
    verdict = evaluate_cutover_verdict(metrics, effective_thresholds)
    return ParityScorecard(
        verdict=verdict,
        metrics=metrics,
        thresholds=effective_thresholds,
    )


def evaluate_cutover_verdict(metrics: dict[str, float], thresholds: dict[str, float]) -> str:
    """Return the cutover verdict defined by the SSOT parity gates."""

    if not metrics:
        return "fail"

    missing = [metric for metric in thresholds if metric not in metrics]
    if missing:
        return "fail"

    if all(_metric_passes(name, metrics[name], thresholds[name]) for name in thresholds):
        return "eligible_for_local_primary"

    return "shadow_only"


def _metric_passes(name: str, value: float, threshold: float) -> bool:
    if name in MAX_THRESHOLD_METRICS:
        return value <= threshold
    return value >= threshold


def persist_cutover_status(
    output_dir: str | Path,
    scorecard: ParityScorecard,
    hard_gates_passed: bool,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "cutover_status.json"
    payload = {
        "verdict": scorecard.verdict,
        "hard_gates_passed": hard_gates_passed,
        "metrics": scorecard.metrics,
        "thresholds": scorecard.thresholds,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path
