from backend.app.parity_engine.shadow_eval import should_collect_shadow_scorecards


def test_zep_mode_can_enable_shadow_eval_sidecar():
    assert should_collect_shadow_scorecards("zep", True) is True
    assert should_collect_shadow_scorecards("shadow_eval", False) is True
    assert should_collect_shadow_scorecards("zep", False) is False
