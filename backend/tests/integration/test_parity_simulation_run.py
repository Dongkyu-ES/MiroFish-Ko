from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_simulation_run_parity_scores_high_for_matching_state_transitions():
    evaluator = DownstreamParityEvaluator()
    score = evaluator.compare_simulation_run(
        {"statuses": ["preparing", "ready", "running", "completed"]},
        {"statuses": ["preparing", "ready", "running", "completed"]},
    )

    assert score == 1.0
