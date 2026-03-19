import time
from types import SimpleNamespace

from backend.app import create_app
from backend.app.services.oasis_profile_generator import OasisAgentProfile
from backend.app.services.zep_graph_memory_updater import AgentActivity, ZepGraphMemoryUpdater


def test_zep_entity_reader_supports_current_sdk_node_get_edges():
    from backend.app.services.zep_entity_reader import ZepEntityReader

    edge = SimpleNamespace(
        uuid_="edge-1",
        name="WORKS_FOR",
        fact="Alice works for Example Labs.",
        source_node_uuid="node-1",
        target_node_uuid="node-2",
        attributes={"since": "2026-01-01"},
    )

    reader = ZepEntityReader(api_key="dummy")
    reader.client = SimpleNamespace(
        graph=SimpleNamespace(
            node=SimpleNamespace(
                get_edges=lambda node_uuid: [edge],
            )
        )
    )

    edges = reader.get_node_edges("node-1")

    assert edges == [
        {
            "uuid": "edge-1",
            "name": "WORKS_FOR",
            "fact": "Alice works for Example Labs.",
            "source_node_uuid": "node-1",
            "target_node_uuid": "node-2",
            "attributes": {"since": "2026-01-01"},
        }
    ]


def test_generate_profiles_route_passes_graph_id_to_generator(monkeypatch):
    import backend.app.api.simulation as simulation_api

    captured: dict[str, object] = {}

    class FakeReader:
        def filter_defined_entities(self, graph_id, defined_entity_types=None, enrich_with_edges=True):
            captured["reader_graph_id"] = graph_id
            return SimpleNamespace(
                filtered_count=1,
                entity_types={"Person"},
                entities=[SimpleNamespace(name="Alice")],
            )

    class FakeGenerator:
        def __init__(self, graph_id=None, **kwargs):
            captured["generator_init_graph_id"] = graph_id

        def generate_profiles_from_entities(self, entities, use_llm=True, graph_id=None, **kwargs):
            captured["generator_graph_id"] = graph_id
            return [
                OasisAgentProfile(
                    user_id=0,
                    user_name="alice_001",
                    name="Alice",
                    bio="Person: Alice",
                    persona="Alice is active in the discussion.",
                )
            ]

    monkeypatch.setattr(simulation_api, "ZepEntityReader", FakeReader)
    monkeypatch.setattr(simulation_api, "OasisProfileGenerator", FakeGenerator)

    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/simulation/generate-profiles",
        json={
            "graph_id": "graph-1",
            "use_llm": False,
            "platform": "reddit",
        },
    )

    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert captured["reader_graph_id"] == "graph-1"
    assert captured["generator_init_graph_id"] == "graph-1"
    assert captured["generator_graph_id"] == "graph-1"


def test_graph_memory_updater_flushes_partial_batch_after_idle(monkeypatch):
    import backend.app.services.zep_graph_memory_updater as updater_module

    sent_payloads: list[dict[str, str]] = []

    class FakeGraph:
        def add(self, *, graph_id, type, data):
            sent_payloads.append(
                {
                    "graph_id": graph_id,
                    "type": type,
                    "data": data,
                }
            )
            return SimpleNamespace(uuid_="episode-1", processed=True)

    class FakeZep:
        def __init__(self, api_key):
            self.graph = FakeGraph()

    monkeypatch.setattr(updater_module, "Zep", FakeZep)

    updater = ZepGraphMemoryUpdater(graph_id="graph-1", api_key="dummy")
    updater.SEND_INTERVAL = 0.0
    updater.QUEUE_POLL_INTERVAL = 0.05
    updater.FLUSH_INTERVAL = 0.1
    updater.start()

    try:
        updater.add_activity(
            AgentActivity(
                platform="twitter",
                agent_id=1,
                agent_name="Alice",
                action_type="CREATE_POST",
                action_args={"content": "Hello world"},
                round_num=1,
                timestamp="2026-03-16T00:00:00",
            )
        )

        deadline = time.time() + 0.5
        while time.time() < deadline and not sent_payloads:
            time.sleep(0.02)

        assert len(sent_payloads) == 1
        assert sent_payloads[0]["graph_id"] == "graph-1"
        assert "Alice" in sent_payloads[0]["data"]
    finally:
        updater.stop()


def test_graph_memory_updater_waits_for_episode_processing(monkeypatch):
    import backend.app.services.zep_graph_memory_updater as updater_module

    episode_status_checks: list[str] = []

    class FakeEpisodeApi:
        def __init__(self):
            self._calls = 0

        def get(self, uuid_):
            episode_status_checks.append(uuid_)
            self._calls += 1
            return SimpleNamespace(processed=self._calls >= 2, task_id=None, uuid_=uuid_)

    fake_episode_api = FakeEpisodeApi()

    class FakeGraph:
        def __init__(self):
            self.episode = fake_episode_api

        def add(self, *, graph_id, type, data):
            return SimpleNamespace(uuid_="episode-1", processed=False, task_id=None)

    class FakeZep:
        def __init__(self, api_key):
            self.graph = FakeGraph()

    monkeypatch.setattr(updater_module, "Zep", FakeZep)

    updater = ZepGraphMemoryUpdater(graph_id="graph-1", api_key="dummy")
    updater.EPISODE_POLL_INTERVAL = 0.0
    updater.EPISODE_WAIT_TIMEOUT = 0.1

    updater._send_batch_activities(
        [
            AgentActivity(
                platform="twitter",
                agent_id=1,
                agent_name="Alice",
                action_type="CREATE_POST",
                action_args={"content": "Hello world"},
                round_num=1,
                timestamp="2026-03-16T00:00:00",
            )
        ],
        "twitter",
    )

    assert episode_status_checks == ["episode-1", "episode-1"]


def test_graph_memory_updater_retries_transient_poll_failures(monkeypatch):
    import backend.app.services.zep_graph_memory_updater as updater_module

    class TransientPollError(Exception):
        pass

    class FakeEpisodeApi:
        def __init__(self):
            self.calls = 0

        def get(self, uuid_):
            self.calls += 1
            if self.calls == 1:
                raise TransientPollError("temporary network issue")
            return SimpleNamespace(processed=True, task_id=None, uuid_=uuid_)

    fake_episode_api = FakeEpisodeApi()

    class FakeGraph:
        def __init__(self):
            self.episode = fake_episode_api

        def add(self, *, graph_id, type, data):
            return SimpleNamespace(uuid_="episode-1", processed=False, task_id=None)

    class FakeZep:
        def __init__(self, api_key):
            self.graph = FakeGraph()

    monkeypatch.setattr(updater_module, "Zep", FakeZep)

    updater = ZepGraphMemoryUpdater(graph_id="graph-1", api_key="dummy")
    updater.EPISODE_POLL_INTERVAL = 0.0
    updater.EPISODE_WAIT_TIMEOUT = 0.2

    updater._send_batch_activities(
        [
            AgentActivity(
                platform="twitter",
                agent_id=1,
                agent_name="Alice",
                action_type="CREATE_POST",
                action_args={"content": "Hello world"},
                round_num=1,
                timestamp="2026-03-16T00:00:00",
            )
        ],
        "twitter",
    )

    assert updater.get_stats()["failed_count"] == 0
