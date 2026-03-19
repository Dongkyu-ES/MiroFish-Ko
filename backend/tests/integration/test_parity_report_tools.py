from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_report_tool_parity_scores_high_for_matching_outputs():
    evaluator = DownstreamParityEvaluator()
    score = evaluator.compare_report_outputs(
        {"tool_results": ["fact_a", "fact_b"]},
        {"tool_results": ["fact_a", "fact_b"]},
    )

    assert score >= 0.9
