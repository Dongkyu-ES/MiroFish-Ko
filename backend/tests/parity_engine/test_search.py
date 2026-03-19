from backend.app.parity_engine.search import HybridSearchOverlay


def test_hybrid_search_overlay_returns_ranked_edges_and_nodes():
    overlay = HybridSearchOverlay()
    result = overlay.rank(
        query="student protest",
        node_candidates=[
            {"uuid": "n1", "name": "Leader", "summary": "Student protest leader", "labels": ["Person"]},
        ],
        edge_candidates=[
            {
                "uuid": "e1",
                "name": "ORGANIZES",
                "fact": "Students organized a protest",
                "created_at": "2025-01-01T00:00:00Z",
                "valid_at": "2025-01-01T00:00:00Z",
                "invalid_at": None,
                "expired_at": None,
            }
        ],
    )
    assert "nodes" in result
    assert "edges" in result
    assert result["edges"][0]["uuid"] == "e1"
    assert result["nodes"][0]["uuid"] == "n1"
    assert result["edges"][0]["valid_at"] == "2025-01-01T00:00:00Z"


def test_hybrid_search_overlay_backfills_missing_node_summary():
    overlay = HybridSearchOverlay()
    result = overlay.rank(
        query="alice",
        node_candidates=[
            {"uuid": "n1", "name": "Alice", "labels": ["Person"], "attributes": {"role": "Organizer"}},
        ],
        edge_candidates=[],
    )

    assert result["nodes"][0]["summary"]


def test_hybrid_search_overlay_prefers_exact_phrase_match():
    overlay = HybridSearchOverlay()
    result = overlay.rank(
        query="도널드 트럼프",
        node_candidates=[],
        edge_candidates=[
            {
                "uuid": "e1",
                "name": "DECLARES_STATEMENT",
                "fact": "미국 대통령 도널드 트럼프는 주요 전투 작전 개시를 발표했다.",
                "created_at": "2025-01-01T00:00:00Z",
                "valid_at": "2025-01-01T00:00:00Z",
                "invalid_at": None,
                "expired_at": None,
            },
            {
                "uuid": "e2",
                "name": "REPORTS_ON",
                "fact": "미국 정부는 새로운 발표를 준비했다.",
                "created_at": "2025-01-01T00:00:00Z",
                "valid_at": "2025-01-01T00:00:00Z",
                "invalid_at": None,
                "expired_at": None,
            },
        ],
    )

    assert result["edges"][0]["uuid"] == "e1"
