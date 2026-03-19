import json

from backend.app.parity_engine.metrics import ndcg_at_k, overlap_at_k, relative_delta
from backend.app.parity_engine.scorecard import DEFAULT_THRESHOLDS, build_scorecard, persist_cutover_status


def test_overlap_at_k():
    assert overlap_at_k(["a", "b", "c"], ["b", "c", "d"], 3) == 2 / 3


def test_relative_delta():
    assert relative_delta(100, 110) == 0.10


def test_ndcg_at_k_is_one_for_identical_rankings():
    assert ndcg_at_k(["a", "b", "c"], ["a", "b", "c"], 3) == 1.0


def test_build_scorecard_returns_eligible_verdict_when_thresholds_are_met():
    scorecard = build_scorecard(
        metrics={
            "node_count_delta": 0.05,
            "edge_count_delta": 0.10,
            "entity_label_f1": 0.95,
            "edge_type_f1": 0.90,
            "attribute_fill_rate_parity": 0.90,
            "top_10_edge_overlap": 0.85,
            "top_10_node_overlap": 0.85,
            "ndcg_at_10": 0.90,
            "fact_hit_rate": 0.90,
            "profile_completeness_score": 0.95,
            "report_tool_usefulness_score": 4.5,
            "simulation_prepare_success_rate": 1.0,
            "report_exception_rate": 0.0,
        }
    )

    assert scorecard.verdict == "eligible_for_local_primary"
    assert scorecard.thresholds == DEFAULT_THRESHOLDS


def test_build_scorecard_returns_shadow_only_when_metrics_exist_but_gate_is_not_met():
    scorecard = build_scorecard(
        metrics={
            "node_count_delta": 0.20,
            "edge_count_delta": 0.10,
            "entity_label_f1": 0.95,
            "edge_type_f1": 0.90,
            "attribute_fill_rate_parity": 0.90,
            "top_10_edge_overlap": 0.85,
            "top_10_node_overlap": 0.85,
            "ndcg_at_10": 0.90,
            "fact_hit_rate": 0.90,
            "profile_completeness_score": 0.95,
            "report_tool_usefulness_score": 4.5,
            "simulation_prepare_success_rate": 1.0,
            "report_exception_rate": 0.0,
        }
    )

    assert scorecard.verdict == "shadow_only"


def test_persist_cutover_status_writes_gate_artifact(tmp_path):
    scorecard = build_scorecard(
        metrics={
            "node_count_delta": 0.05,
            "edge_count_delta": 0.10,
            "entity_label_f1": 0.95,
            "edge_type_f1": 0.90,
            "attribute_fill_rate_parity": 0.90,
            "top_10_edge_overlap": 0.85,
            "top_10_node_overlap": 0.85,
            "ndcg_at_10": 0.90,
            "fact_hit_rate": 0.90,
            "profile_completeness_score": 0.95,
            "report_tool_usefulness_score": 4.5,
            "simulation_prepare_success_rate": 1.0,
            "report_exception_rate": 0.0,
        }
    )
    path = persist_cutover_status(tmp_path, scorecard, hard_gates_passed=True)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["verdict"] == "eligible_for_local_primary"
    assert payload["hard_gates_passed"] is True
