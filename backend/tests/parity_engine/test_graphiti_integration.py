from pathlib import Path

import graphiti_core.driver.kuzu_driver as kuzu_driver_module
import graphiti_core.graphiti as graphiti_module

from backend.app.parity_engine.extractor import GraphitiExtractionOverlay
from backend.app.parity_engine.graphiti_client import GraphitiEngine


def _set_inline_llm_env(monkeypatch):
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "dummy-model")


def test_graphiti_engine_creates_graph_and_episode(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    _set_inline_llm_env(monkeypatch)
    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "en",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 2,
            "typed_entity_count": 2,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "Alice", "type": "Person", "attributes": {"name": "Alice"}},
                {"name": "Example Labs", "type": "Company", "attributes": {"name": "Example Labs"}},
            ],
            "edges": [],
        },
    )
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Parity Test", "desc")
    episode_id = engine.create_episode(graph_id, "Alice founded Example Labs.")

    assert graph_id.startswith("mirofish_")
    assert episode_id


def test_graphiti_engine_recovers_from_invalid_existing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    db_path = tmp_path / "graphiti.kuzu"
    db_path.write_bytes(b"not-a-kuzu-db")

    engine = GraphitiEngine(db_path=db_path)
    graph_id = engine.create_graph("Recovered Graph", "desc")

    assert graph_id.startswith("mirofish_")
    assert db_path.exists()
    assert list(tmp_path.glob("graphiti.kuzu.corrupt-*"))


def test_graphiti_engine_reuses_existing_database_without_recreating_indices(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    db_path = tmp_path / "graphiti.kuzu"

    GraphitiEngine(db_path=db_path)
    engine = GraphitiEngine(db_path=db_path)
    graph_id = engine.create_graph("Second Boot", "desc")

    assert graph_id.startswith("mirofish_")


def test_graphiti_engine_quarantines_metadata_sidecar_with_invalid_database(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    db_path = tmp_path / "graphiti.kuzu"

    engine = GraphitiEngine(db_path=db_path)
    graph_id = engine.create_graph("Before Recovery", "desc")
    metadata_path = engine.store.db_path
    wal_path = metadata_path.with_name(f"{metadata_path.name}-wal")
    shm_path = metadata_path.with_name(f"{metadata_path.name}-shm")
    wal_path.write_text("wal", encoding="utf-8")
    shm_path.write_text("shm", encoding="utf-8")
    db_path.write_bytes(b"not-a-kuzu-db")

    recovered = GraphitiEngine(db_path=db_path)

    assert db_path.exists()
    assert list(tmp_path.glob("graphiti.kuzu.corrupt-*"))
    assert list(tmp_path.glob("graphiti.sqlite3.corrupt-*"))
    assert not wal_path.exists()
    assert not shm_path.exists()
    try:
        recovered.store.get_graph(graph_id)
    except KeyError:
        pass
    else:
        raise AssertionError("expected metadata sidecar to be reset during recovery")


def test_graphiti_engine_quarantines_invalid_header_before_open(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    db_path = tmp_path / "graphiti.kuzu"
    db_path.write_bytes(b"not-a-kuzu-db")
    observed = {}

    class FakeKuzuDriver:
        def __init__(self, db: str):
            observed["exists_on_entry"] = Path(db).exists()

    class FakeGraphiti:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def build_indices_and_constraints(self, delete_existing: bool = False):
            return None

    monkeypatch.setattr(kuzu_driver_module, "KuzuDriver", FakeKuzuDriver)
    monkeypatch.setattr(graphiti_module, "Graphiti", FakeGraphiti)

    GraphitiEngine(db_path=db_path)

    assert observed["exists_on_entry"] is False
    assert list(tmp_path.glob("graphiti.kuzu.corrupt-*"))


def test_graphiti_engine_recovers_from_existing_db_open_failure_without_message_match(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    db_path = tmp_path / "graphiti.kuzu"
    db_path.write_bytes(b"KUZU'" + (b"\x00" * 32))
    calls = {"count": 0}

    class FakeKuzuDriver:
        def __init__(self, db: str):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("generic open failure")
            self.db = db

    class FakeGraphiti:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def build_indices_and_constraints(self, delete_existing: bool = False):
            return None

    monkeypatch.setattr(kuzu_driver_module, "KuzuDriver", FakeKuzuDriver)
    monkeypatch.setattr(graphiti_module, "Graphiti", FakeGraphiti)

    GraphitiEngine(db_path=db_path)

    assert calls["count"] == 2
    assert list(tmp_path.glob("graphiti.kuzu.corrupt-*"))


def test_graphiti_engine_merges_duplicate_provider_nodes_by_canonical_name(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    monkeypatch.setattr(GraphitiEngine, "_build_graphiti", lambda self: object())

    async def _noop_initialize(self):
        return None

    monkeypatch.setattr(GraphitiEngine, "_initialize_graphiti_indices", _noop_initialize)
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Merge Test", "desc")

    node_one = type(
        "Node",
        (),
        {
            "uuid": "node_1",
            "name": "미국",
            "labels": ["Country"],
            "summary": "첫 번째 요약",
            "attributes": {"name": "미국"},
        },
    )()
    node_two = type(
        "Node",
        (),
        {
            "uuid": "node_2",
            "name": "미국",
            "labels": ["Country"],
            "summary": "두 번째 요약",
            "attributes": {"alias": "US"},
        },
    )()
    edge = type(
        "Edge",
        (),
        {
            "uuid": "edge_1",
            "name": "ALLIES_WITH",
            "fact": "미국은 미국과 동맹이다.",
            "source_node_uuid": "node_1",
            "target_node_uuid": "node_2",
            "attributes": {},
            "valid_at": None,
            "invalid_at": None,
            "expired_at": None,
            "episodes": ["episode_1"],
        },
    )()

    engine._persist_graphiti_result(
        graph_id,
        "episode_1",
        type("Result", (), {"nodes": [node_one], "edges": []})(),
    )
    engine._persist_graphiti_result(
        graph_id,
        "episode_2",
        type("Result", (), {"nodes": [node_two], "edges": [edge]})(),
    )

    nodes = engine.list_nodes(graph_id, limit=10)
    edges = engine.list_edges(graph_id, limit=10)

    assert len(nodes) == 1
    assert "첫 번째 요약" in nodes[0]["summary"]
    assert "두 번째 요약" in nodes[0]["summary"]
    assert nodes[0]["attributes"]["alias"] == "US"
    assert len(edges) == 1
    assert edges[0]["source_node_uuid"] == nodes[0]["uuid_"]
    assert edges[0]["target_node_uuid"] == nodes[0]["uuid_"]


def test_graphiti_engine_passes_ontology_config_into_provider_backed_add_episode(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "false")
    captured = {}

    class FakeDriver:
        _database = None

    class FakeGraphiti:
        async def build_indices_and_constraints(self, delete_existing: bool = False):
            return None

        async def add_episode(self, **kwargs):
            captured.update(kwargs)
            return type("Result", (), {"nodes": [], "edges": []})()

    def fake_build_graphiti(self):
        self.driver = FakeDriver()
        return FakeGraphiti()

    monkeypatch.setattr(GraphitiEngine, "_build_graphiti", fake_build_graphiti)

    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu", episode_inline=False)
    graph_id = engine.create_graph("Ontology Passthrough", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "Country", "description": "A sovereign country.", "attributes": []},
                {"name": "Person", "description": "A person.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "supports",
                    "description": "Support relationship.",
                    "source_targets": [
                        {"source": "Country", "target": "Country"},
                        {"source": "Person", "target": "Country"},
                    ],
                    "attributes": [],
                }
            ],
        },
    )
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "key")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "model")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_MODEL", "embed")
    monkeypatch.setenv("GRAPHITI_RERANK_MODEL", "rerank")
    engine.settings.llm_api_key = "key"
    engine.settings.llm_model = "model"
    engine.settings.embedding_model = "embed"
    engine.settings.rerank_model = "rerank"

    engine.add_episode(graph_id, "미국은 이스라엘을 지원한다.")

    assert set(captured["entity_types"].keys()) == {"Country", "Person"}
    assert set(captured["edge_types"].keys()) == {"SUPPORTS"}
    assert captured["edge_type_map"][("Country", "Country")] == ["SUPPORTS"]
    assert captured["edge_type_map"][("Person", "Country")] == ["SUPPORTS"]
    assert "SUPPORTS" in captured["custom_extraction_instructions"]


def test_graphiti_engine_retries_retryable_provider_episode_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "false")
    monkeypatch.setenv("GRAPHITI_LLM_API_KEY", "key")
    monkeypatch.setenv("GRAPHITI_LLM_MODEL", "model")
    monkeypatch.setenv("GRAPHITI_EMBEDDING_MODEL", "embed")
    monkeypatch.setenv("GRAPHITI_RERANK_MODEL", "rerank")
    calls = {"count": 0}

    class FakeDriver:
        _database = None

    class FakeGraphiti:
        async def build_indices_and_constraints(self, delete_existing: bool = False):
            return None

        async def add_episode(self, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("Connection error.")
            return type("Result", (), {"nodes": [], "edges": []})()

    def fake_build_graphiti(self):
        self.driver = FakeDriver()
        return FakeGraphiti()

    monkeypatch.setattr(GraphitiEngine, "_build_graphiti", fake_build_graphiti)
    monkeypatch.setattr("backend.app.parity_engine.graphiti_client.time.sleep", lambda _: None)

    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu", episode_inline=False)
    engine.settings.llm_api_key = "key"
    engine.settings.llm_model = "model"
    engine.settings.embedding_model = "embed"
    engine.settings.rerank_model = "rerank"
    graph_id = engine.create_graph("Retry Test", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "Country", "description": "A sovereign country.", "attributes": []},
                {"name": "Person", "description": "A person.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "supports",
                    "description": "Support relationship.",
                    "source_targets": [{"source": "Person", "target": "Country"}],
                    "attributes": [],
                }
            ],
        },
    )

    episode_id = engine.add_episode(graph_id, "Alice supports the United States.")

    assert calls["count"] == 2
    assert engine.get_episode(episode_id)["status"] == "processed"


def test_graphiti_engine_inline_merges_full_form_and_acronym_in_same_episode(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    _set_inline_llm_env(monkeypatch)
    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "ko",
            "ontology": ontology,
            "sentence_count": 2,
            "candidate_count": 3,
            "typed_entity_count": 3,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "국제원자력기구(IAEA)", "type": "InternationalOrganization", "attributes": {"name": "국제원자력기구(IAEA)"}},
                {"name": "IAEA", "type": "InternationalOrganization", "attributes": {"name": "IAEA"}},
                {"name": "나탄즈 농축시설", "type": "Target", "attributes": {"name": "나탄즈 농축시설"}},
            ],
            "edges": [
                {
                    "name": "REPORTS_ON",
                    "source": "국제원자력기구(IAEA)",
                    "target": "나탄즈 농축시설",
                    "fact": text,
                }
            ],
        },
    )
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Alias Merge", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "InternationalOrganization", "description": "International organization.", "attributes": []},
                {"name": "Target", "description": "Target facility.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "reports_on",
                    "description": "Organization reports on a target.",
                    "source_targets": [{"source": "InternationalOrganization", "target": "Target"}],
                    "attributes": [],
                }
            ],
        },
    )
    engine.add_episode(
        graph_id,
        "국제원자력기구(IAEA)는 나탄즈 농축시설 피해를 보고했다. IAEA는 추가 브리핑을 발표했다.",
    )

    nodes = engine.list_nodes(graph_id, limit=20)
    node_names = [node["name"] for node in nodes]

    assert "국제원자력기구(IAEA)" in node_names
    assert "IAEA" not in node_names


def test_graphiti_engine_inline_merges_korean_org_and_acronym_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    _set_inline_llm_env(monkeypatch)
    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "ko",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 5,
            "typed_entity_count": 5,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "유럽연합(EU)", "type": "InternationalOrganization", "attributes": {"name": "유럽연합(EU)"}},
                {"name": "EU", "type": "InternationalOrganization", "attributes": {"name": "EU"}},
                {"name": "걸프협력회의(GCC)", "type": "InternationalOrganization", "attributes": {"name": "걸프협력회의(GCC)"}},
                {"name": "GCC", "type": "InternationalOrganization", "attributes": {"name": "GCC"}},
                {"name": "걸프협력회의", "type": "InternationalOrganization", "attributes": {"name": "걸프협력회의"}},
            ],
            "edges": [],
        },
    )
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Org Alias Merge", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "InternationalOrganization", "description": "International organization.", "attributes": []},
                {"name": "MilitaryForce", "description": "Military actor.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "informs",
                    "description": "Organization informs a military actor.",
                    "source_targets": [{"source": "InternationalOrganization", "target": "MilitaryForce"}],
                    "attributes": [],
                }
            ],
        },
    )
    engine.add_episode(
        graph_id,
        "유럽연합(EU)과 GCC는 공동성명에서 이란의 공격을 규탄했고, 걸프협력회의(GCC)는 추가 입장을 밝혔다.",
    )

    node_names = [node["name"] for node in engine.list_nodes(graph_id, limit=30)]

    assert "유럽연합(EU)" in node_names
    assert "EU" not in node_names
    assert "걸프협력회의(GCC)" in node_names
    assert "GCC" not in node_names
    assert "걸프협력회의" not in node_names


def test_graphiti_engine_inline_merges_humanitarian_org_alias_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    _set_inline_llm_env(monkeypatch)
    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "ko",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 4,
            "typed_entity_count": 4,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "유엔 인권최고대표사무소(OHCHR)", "type": "InternationalOrganization", "attributes": {"name": "유엔 인권최고대표사무소(OHCHR)"}},
                {"name": "OHCHR", "type": "InternationalOrganization", "attributes": {"name": "OHCHR"}},
                {"name": "적신월사(IRCS)", "type": "InternationalOrganization", "attributes": {"name": "적신월사(IRCS)"}},
                {"name": "IRCS", "type": "InternationalOrganization", "attributes": {"name": "IRCS"}},
            ],
            "edges": [],
        },
    )
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Humanitarian Alias Merge", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "InternationalOrganization", "description": "International organization.", "attributes": []},
                {"name": "CivilianPerson", "description": "Civilian person.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "assists",
                    "description": "Organization assists civilians.",
                    "source_targets": [{"source": "InternationalOrganization", "target": "CivilianPerson"}],
                    "attributes": [],
                }
            ],
        },
    )
    engine.add_episode(
        graph_id,
        "유엔 인권최고대표사무소(OHCHR)와 적신월사(IRCS)는 민간인 피해를 보고했다. OHCHR는 추가 브리핑을 했고, IRCS도 구호 활동을 언급했다.",
    )

    node_names = [node["name"] for node in engine.list_nodes(graph_id, limit=30)]

    assert "유엔 인권최고대표사무소(OHCHR)" in node_names
    assert "OHCHR" not in node_names
    assert "적신월사(IRCS)" in node_names
    assert "IRCS" not in node_names


def test_graphiti_engine_inline_prefers_clean_display_names(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    _set_inline_llm_env(monkeypatch)
    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "ko",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 4,
            "typed_entity_count": 4,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "미국 대통령 도널드 트럼프", "type": "PoliticalLeader", "attributes": {"name": "미국 대통령 도널드 트럼프", "aliases": ["도널드 트럼프"]}},
                {"name": "도널드 트럼프", "type": "PoliticalLeader", "attributes": {"name": "도널드 트럼프"}},
                {"name": "GCC", "type": "InternationalOrganization", "attributes": {"name": "GCC"}},
                {"name": "걸프협력회의(GCC)", "type": "InternationalOrganization", "attributes": {"name": "걸프협력회의(GCC)"}},
            ],
            "edges": [],
        },
    )
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Display Name Merge", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "PoliticalLeader", "description": "Political leader.", "attributes": []},
                {"name": "InternationalOrganization", "description": "International organization.", "attributes": []},
            ],
            "edge_types": [],
        },
    )
    engine.add_episode(graph_id, "도널드 트럼프와 GCC 관련 문장")

    node_names = [node["name"] for node in engine.list_nodes(graph_id, limit=20)]

    assert "도널드 트럼프" in node_names
    assert "미국 대통령 도널드 트럼프" not in node_names
    assert "걸프협력회의(GCC)" in node_names
    assert "GCC" not in node_names


def test_graphiti_engine_inline_promotes_full_form_orgs_and_trims_quantities(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHITI_EPISODE_INLINE", "true")
    _set_inline_llm_env(monkeypatch)
    monkeypatch.setattr(
        GraphitiExtractionOverlay,
        "extract",
        lambda self, text, ontology: {
            "language": "ko",
            "ontology": ontology,
            "sentence_count": 1,
            "candidate_count": 4,
            "typed_entity_count": 4,
            "dropped_candidate_count": 0,
            "entities": [
                {"name": "유럽연합", "type": "InternationalOrganization", "attributes": {"name": "유럽연합"}},
                {"name": "걸프협력회의", "type": "InternationalOrganization", "attributes": {"name": "걸프협력회의"}},
                {"name": "이란 해군 선박 50척 이상", "type": "MilitaryForce", "attributes": {"name": "이란 해군 선박 50척 이상"}},
                {"name": "이란 최고지도자 알리 하메네이", "type": "PoliticalLeader", "attributes": {"name": "이란 최고지도자 알리 하메네이"}},
            ],
            "edges": [],
        },
    )
    engine = GraphitiEngine(db_path=tmp_path / "graphiti.kuzu")
    graph_id = engine.create_graph("Display Name Polish", "desc")
    engine.set_ontology(
        graph_id,
        {
            "entity_types": [
                {"name": "PoliticalLeader", "description": "Political leader.", "attributes": []},
                {"name": "InternationalOrganization", "description": "International organization.", "attributes": []},
                {"name": "MilitaryForce", "description": "Military actor.", "attributes": []},
            ],
            "edge_types": [],
        },
    )
    engine.add_episode(graph_id, "표시명 정리 테스트")

    node_names = [node["name"] for node in engine.list_nodes(graph_id, limit=20)]

    assert "유럽연합(EU)" in node_names
    assert "걸프협력회의(GCC)" in node_names
    assert "이란 해군 선박" in node_names
    assert "이란 최고지도자 알리 하메네이" not in node_names
    assert "알리 하메네이" in node_names
