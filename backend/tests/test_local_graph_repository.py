import tempfile
from unittest.mock import Mock

from backend.app.config import Config
from backend.app.services.graph_builder import GraphBuilderService
from backend.app.services.local_graph_repository import LocalGraphRepository
from backend.app.services.zep_graph_memory_updater import AgentActivity, ZepGraphMemoryUpdater
from backend.app.services.zep_entity_reader import ZepEntityReader
from backend.app.services.zep_tools import ZepToolsService


def test_local_graph_repository_create_save_load_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = LocalGraphRepository(db_path=f"{tmpdir}/graphs.sqlite3")
        graph_id = repo.create_graph(name="Test Graph", description="desc")
        
        repo.save_ontology(graph_id, {
            "entity_types": [{"name": "Student"}],
            "edge_types": [{"name": "MENTIONS"}],
        })
        repo.replace_graph_data(
            graph_id,
            nodes=[
                {
                    "uuid": "n1",
                    "name": "Alice",
                    "labels": ["Entity", "Student"],
                    "summary": "Student node",
                    "attributes": {"year": "2"},
                    "created_at": "2026-03-17T00:00:00",
                },
                {
                    "uuid": "n2",
                    "name": "Campus TV",
                    "labels": ["Entity", "MediaOutlet"],
                    "summary": "Media node",
                    "attributes": {"channel": "tv"},
                    "created_at": "2026-03-17T00:00:01",
                },
            ],
            edges=[
                {
                    "uuid": "e1",
                    "name": "MENTIONS",
                    "fact": "Alice mentioned Campus TV",
                    "source_node_uuid": "n1",
                    "target_node_uuid": "n2",
                    "attributes": {"weight": 1},
                    "created_at": "2026-03-17T00:01:00",
                    "episodes": ["ep1"],
                }
            ],
        )
        
        graph = repo.get_graph(graph_id)
        assert graph is not None
        assert graph["name"] == "Test Graph"
        assert graph["ontology"]["entity_types"][0]["name"] == "Student"
        
        data = repo.get_graph_data(graph_id)
        assert data["node_count"] == 2
        assert data["edge_count"] == 1
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        
        info = repo.get_graph_info(graph_id)
        assert info.node_count == 2
        assert info.edge_count == 1
        assert info.entity_types == ["MediaOutlet", "Student"]
        
        assert repo.delete_graph(graph_id) is True
        assert repo.get_graph(graph_id) is None


def test_graph_builder_service_local_sqlite_metadata_methods():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_backend = Config.GRAPH_BACKEND
        original_db_path = Config.LOCAL_GRAPH_DB_PATH
        try:
            Config.GRAPH_BACKEND = 'local_sqlite'
            Config.LOCAL_GRAPH_DB_PATH = f"{tmpdir}/graphs.sqlite3"
            
            builder = GraphBuilderService()
            graph_id = builder.create_graph("Builder Graph")
            builder.set_ontology(graph_id, {"entity_types": [{"name": "Student"}], "edge_types": []})
            builder.local_repo.replace_graph_data(
                graph_id,
                nodes=[
                    {
                        "uuid": "n1",
                        "name": "Alice",
                        "labels": ["Entity", "Student"],
                        "summary": "Student",
                        "attributes": {},
                    }
                ],
                edges=[],
            )
            
            info = builder._get_graph_info(graph_id)
            assert info.graph_id == graph_id
            assert info.node_count == 1
            assert info.edge_count == 0
            assert info.entity_types == ["Student"]
            
            data = builder.get_graph_data(graph_id)
            assert data["graph_id"] == graph_id
            assert data["node_count"] == 1
            
            builder.delete_graph(graph_id)
            assert builder.local_repo.get_graph(graph_id) is None
        finally:
            Config.GRAPH_BACKEND = original_backend
            Config.LOCAL_GRAPH_DB_PATH = original_db_path


def test_graph_builder_service_local_sqlite_builds_graph_from_llm_extraction():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_backend = Config.GRAPH_BACKEND
        original_db_path = Config.LOCAL_GRAPH_DB_PATH
        try:
            Config.GRAPH_BACKEND = 'local_sqlite'
            Config.LOCAL_GRAPH_DB_PATH = f"{tmpdir}/graphs.sqlite3"

            fake_llm = Mock()
            fake_llm.chat_json.side_effect = [
                {
                    "nodes": [
                        {
                            "name": "Alice",
                            "labels": ["Entity", "Student"],
                            "summary": "Student leader",
                            "attributes": {"year": "2"},
                        },
                        {
                            "name": "Campus TV",
                            "labels": ["Entity", "MediaOutlet"],
                            "summary": "Local media account",
                            "attributes": {},
                        },
                    ],
                    "edges": [
                        {
                            "name": "MENTIONS",
                            "fact": "Alice mentioned Campus TV",
                            "source_node_name": "Alice",
                            "target_node_name": "Campus TV",
                            "attributes": {},
                        }
                    ],
                }
            ]

            builder = GraphBuilderService(llm_client=fake_llm)
            graph_id = builder.create_graph("LLM Graph")
            builder.set_ontology(
                graph_id,
                {
                    "entity_types": [{"name": "Student"}, {"name": "MediaOutlet"}],
                    "edge_types": [{"name": "MENTIONS"}],
                },
            )

            episode_ids = builder.add_text_batches(
                graph_id,
                chunks=["Alice posted about Campus TV."],
                batch_size=1,
            )

            assert len(episode_ids) == 1
            graph_data = builder.get_graph_data(graph_id)
            assert graph_data["node_count"] == 2
            assert graph_data["edge_count"] == 1
            assert sorted(graph_data["entity_types"]) == ["MediaOutlet", "Student"]
            assert graph_data["edges"][0]["name"] == "MENTIONS"
        finally:
            Config.GRAPH_BACKEND = original_backend
            Config.LOCAL_GRAPH_DB_PATH = original_db_path


def test_config_validate_does_not_require_zep_when_using_local_sqlite():
    original_backend = Config.GRAPH_BACKEND
    original_zep = Config.ZEP_API_KEY
    try:
        Config.GRAPH_BACKEND = 'local_sqlite'
        Config.ZEP_API_KEY = None
        errors = Config.validate()
        assert not any('ZEP_API_KEY' in err for err in errors)
    finally:
        Config.GRAPH_BACKEND = original_backend
        Config.ZEP_API_KEY = original_zep


def test_zep_entity_reader_supports_local_sqlite_graph():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_backend = Config.GRAPH_BACKEND
        original_db_path = Config.LOCAL_GRAPH_DB_PATH
        try:
            Config.GRAPH_BACKEND = 'local_sqlite'
            Config.LOCAL_GRAPH_DB_PATH = f"{tmpdir}/graphs.sqlite3"
            repo = LocalGraphRepository(db_path=Config.LOCAL_GRAPH_DB_PATH)
            graph_id = repo.create_graph("Reader Graph")
            repo.replace_graph_data(
                graph_id,
                nodes=[
                    {
                        "uuid": "n1",
                        "name": "Alice",
                        "labels": ["Entity", "Student"],
                        "summary": "Student actor",
                        "attributes": {"year": "2"},
                    },
                    {
                        "uuid": "n2",
                        "name": "Campus Voice",
                        "labels": ["Entity", "MediaOutlet"],
                        "summary": "Media actor",
                        "attributes": {},
                    },
                ],
                edges=[
                    {
                        "uuid": "e1",
                        "name": "MENTIONS",
                        "fact": "Alice mentioned Campus Voice",
                        "source_node_uuid": "n1",
                        "target_node_uuid": "n2",
                        "attributes": {"weight": 1},
                    }
                ],
            )

            reader = ZepEntityReader()
            filtered = reader.filter_defined_entities(
                graph_id=graph_id,
                defined_entity_types=["Student", "MediaOutlet"],
                enrich_with_edges=True,
            )

            assert filtered.total_count == 2
            assert filtered.filtered_count == 2
            assert sorted(filtered.entity_types) == ["MediaOutlet", "Student"]
            assert len(filtered.entities[0].related_edges) >= 1
            detailed = reader.get_entity_with_context(graph_id, "n1")
            assert detailed is not None
            assert detailed.uuid == "n1"
            assert len(detailed.related_edges) == 1
        finally:
            Config.GRAPH_BACKEND = original_backend
            Config.LOCAL_GRAPH_DB_PATH = original_db_path


def test_zep_tools_supports_local_sqlite_search_and_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_backend = Config.GRAPH_BACKEND
        original_db_path = Config.LOCAL_GRAPH_DB_PATH
        try:
            Config.GRAPH_BACKEND = 'local_sqlite'
            Config.LOCAL_GRAPH_DB_PATH = f"{tmpdir}/graphs.sqlite3"
            repo = LocalGraphRepository(db_path=Config.LOCAL_GRAPH_DB_PATH)
            graph_id = repo.create_graph("Search Graph")
            repo.replace_graph_data(
                graph_id,
                nodes=[
                    {
                        "uuid": "n1",
                        "name": "Alice",
                        "labels": ["Entity", "Student"],
                        "summary": "Student critic",
                        "attributes": {},
                    },
                    {
                        "uuid": "n2",
                        "name": "Campus Voice",
                        "labels": ["Entity", "MediaOutlet"],
                        "summary": "Media amplifier",
                        "attributes": {},
                    },
                ],
                edges=[
                    {
                        "uuid": "e1",
                        "name": "AMPLIFY",
                        "fact": "Campus Voice amplified Alice's criticism",
                        "source_node_uuid": "n2",
                        "target_node_uuid": "n1",
                        "attributes": {},
                    }
                ],
            )

            tools = ZepToolsService(api_key='unused')
            search = tools.search_graph(graph_id=graph_id, query='Alice criticism', limit=10)
            stats = tools.get_graph_statistics(graph_id)

            assert search.total_count >= 1
            assert stats["total_nodes"] == 2
            assert stats["total_edges"] == 1
            assert stats["entity_types"]["Student"] == 1
        finally:
            Config.GRAPH_BACKEND = original_backend
            Config.LOCAL_GRAPH_DB_PATH = original_db_path


def test_local_graph_repository_can_append_activity_batch():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = LocalGraphRepository(db_path=f"{tmpdir}/graphs.sqlite3")
        graph_id = repo.create_graph("Memory Graph")

        inserted = repo.append_activity_batch(
            graph_id,
            [
                {
                    "platform": "twitter",
                    "agent_id": 1,
                    "agent_name": "Alice",
                    "action_type": "FOLLOW",
                    "action_args": {"target_user_name": "Bob"},
                    "round_num": 3,
                    "timestamp": "2026-03-17T12:00:00",
                    "fact": "Alice: 사용자 'Bob'",
                }
            ],
        )

        data = repo.get_graph_data(graph_id)
        assert inserted == 1
        assert data["node_count"] == 2
        assert data["edge_count"] == 1


def test_zep_graph_memory_updater_supports_local_sqlite():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_backend = Config.GRAPH_BACKEND
        original_db_path = Config.LOCAL_GRAPH_DB_PATH
        original_zep = Config.ZEP_API_KEY
        try:
            Config.GRAPH_BACKEND = 'local_sqlite'
            Config.LOCAL_GRAPH_DB_PATH = f"{tmpdir}/graphs.sqlite3"
            Config.ZEP_API_KEY = None

            repo = LocalGraphRepository(db_path=Config.LOCAL_GRAPH_DB_PATH)
            graph_id = repo.create_graph("Updater Graph")

            updater = ZepGraphMemoryUpdater(graph_id=graph_id)
            updater.add_activity(
                AgentActivity(
                    platform="twitter",
                    agent_id=1,
                    agent_name="Alice",
                    action_type="FOLLOW",
                    action_args={"target_user_name": "Bob"},
                    round_num=1,
                    timestamp="2026-03-17T12:30:00",
                )
            )
            updater._flush_remaining()
            stats = updater.get_stats()
            data = repo.get_graph_data(graph_id)

            assert stats["batches_sent"] == 1
            assert stats["items_sent"] == 1
            assert data["node_count"] == 2
            assert data["edge_count"] == 1
            assert data["edges"][0]["name"] == "FOLLOW"
        finally:
            Config.GRAPH_BACKEND = original_backend
            Config.LOCAL_GRAPH_DB_PATH = original_db_path
            Config.ZEP_API_KEY = original_zep
