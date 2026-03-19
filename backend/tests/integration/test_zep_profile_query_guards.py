from types import SimpleNamespace


def test_profile_enrichment_uses_multiple_queries():
    import backend.app.services.oasis_profile_generator as profile_module

    queries = []

    class FakeGraph:
        def search(self, **kwargs):
            queries.append(kwargs["query"])
            return SimpleNamespace(edges=[], nodes=[])

    generator = object.__new__(profile_module.OasisProfileGenerator)
    generator.zep_client = SimpleNamespace(graph=FakeGraph())
    generator.graph_id = "graph-1"

    entity = SimpleNamespace(
        name="Alice Kim",
        uuid="node-1",
        summary="Launch lead at Example Labs",
        attributes={"alias": "AK"},
    )

    generator._search_zep_for_entity(entity)

    assert len(set(queries)) >= 2
    assert any("Alice Kim" in query for query in queries)
