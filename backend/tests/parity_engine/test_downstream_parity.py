from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_downstream_parity_evaluator_compares_profile_and_report_outputs():
    evaluator = DownstreamParityEvaluator()
    report = evaluator.compare(
        zep_profile={"facts": ["a"]},
        local_profile={"facts": ["a"]},
        zep_report={"tool_results": ["x"]},
        local_report={"tool_results": ["x"]},
    )
    assert "profile_score" in report
    assert "report_score" in report
