from backend.app.parity_engine.evaluator import DownstreamParityEvaluator


def test_multilingual_flow_parity_scores_high_for_ko_and_en_success():
    evaluator = DownstreamParityEvaluator()
    score = evaluator.compare_multilingual_flow(
        zep_flow={"ko": {"success": True}, "en": {"success": True}},
        local_flow={"ko": {"success": True}, "en": {"success": True}},
    )

    assert score == 1.0
