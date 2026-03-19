from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_profile_parity_scores_high_for_matching_fact_sets():
    evaluator = DownstreamParityEvaluator()
    score = evaluator.compare_profile_outputs(
        {"facts": ["Alice leads the launch", "Bob owns analytics"]},
        {"facts": ["Alice leads the launch", "Bob owns analytics"]},
    )

    assert score >= 0.9
