from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_simulation_prepare_parity_requires_matching_success_and_files():
    evaluator = DownstreamParityEvaluator()
    score = evaluator.compare_simulation_prepare(
        {"success": True, "files": ["reddit_profiles.json", "twitter_profiles.csv"]},
        {"success": True, "files": ["reddit_profiles.json", "twitter_profiles.csv"]},
    )

    assert score == 1.0
