from types import SimpleNamespace

import pytest

from backend.app.services.graph_builder import GraphBuilderService
from backend.app.services.zep_entity_reader import ZepEntityReader


def test_entity_reader_uses_sdk_get_edges_contract():
    reader = ZepEntityReader.__new__(ZepEntityReader)
    reader.client = SimpleNamespace(
        graph=SimpleNamespace(
            node=SimpleNamespace(
                get_edges=lambda node_uuid: [
                    SimpleNamespace(
                        uuid_="edge-1",
                        name="works_for",
                        fact="Alice works for Example Labs.",
                        source_node_uuid=node_uuid,
                        target_node_uuid="company-1",
                        attributes={},
                    )
                ]
            )
        )
    )

    edges = ZepEntityReader.get_node_edges(reader, "person-1")

    assert edges == [
        {
            "uuid": "edge-1",
            "name": "works_for",
            "fact": "Alice works for Example Labs.",
            "source_node_uuid": "person-1",
            "target_node_uuid": "company-1",
            "attributes": {},
        }
    ]


def test_wait_for_episodes_polls_task_status_when_available(monkeypatch):
    builder = GraphBuilderService.__new__(GraphBuilderService)

    task_states = iter(
        [
            SimpleNamespace(status="pending"),
            SimpleNamespace(status="completed"),
        ]
    )
    task_calls: list[str] = []
    episode_calls = 0

    def get_task(task_id: str):
        task_calls.append(task_id)
        return next(task_states)

    def get_episode(uuid_: str):
        nonlocal episode_calls
        episode_calls += 1
        return SimpleNamespace(uuid_=uuid_, processed=False, task_id="task-1")

    builder.client = SimpleNamespace(
        graph=SimpleNamespace(
            episode=SimpleNamespace(get=get_episode),
        ),
        task=SimpleNamespace(get=get_task),
    )

    monkeypatch.setattr("backend.app.services.graph_builder.time.sleep", lambda _: None)

    GraphBuilderService._wait_for_episodes(builder, ["episode-1"], timeout=5)

    assert task_calls == ["task-1", "task-1"]
    assert episode_calls >= 1


def test_wait_for_episodes_raises_on_task_failure(monkeypatch):
    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = SimpleNamespace(
        graph=SimpleNamespace(
            episode=SimpleNamespace(
                get=lambda uuid_: SimpleNamespace(uuid_=uuid_, processed=False, task_id="task-1")
            ),
        ),
        task=SimpleNamespace(
            get=lambda task_id: SimpleNamespace(
                status="failed",
                error=SimpleNamespace(message="ontology extraction failed"),
            )
        ),
    )

    monkeypatch.setattr("backend.app.services.graph_builder.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="ontology extraction failed"):
        GraphBuilderService._wait_for_episodes(builder, ["episode-1"], timeout=5)


def test_wait_for_episodes_raises_on_failed_episode_status(monkeypatch):
    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = SimpleNamespace(
        graph=SimpleNamespace(
            episode=SimpleNamespace(
                get=lambda uuid_: SimpleNamespace(
                    uuid_=uuid_,
                    processed=False,
                    task_id=None,
                    status="failed",
                    error="synthetic extraction failure",
                )
            ),
        ),
    )

    monkeypatch.setattr("backend.app.services.graph_builder.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="synthetic extraction failure"):
        GraphBuilderService._wait_for_episodes(builder, ["episode-1"], timeout=5)


def test_wait_for_episodes_raises_on_timeout(monkeypatch):
    builder = GraphBuilderService.__new__(GraphBuilderService)
    builder.client = SimpleNamespace(
        graph=SimpleNamespace(
            episode=SimpleNamespace(
                get=lambda uuid_: SimpleNamespace(uuid_=uuid_, processed=False, task_id=None)
            ),
        )
    )

    clock = iter([0.0, 10.0])
    monkeypatch.setattr("backend.app.services.graph_builder.time.time", lambda: next(clock))
    monkeypatch.setattr("backend.app.services.graph_builder.time.sleep", lambda _: None)

    with pytest.raises(TimeoutError, match="episode"):
        GraphBuilderService._wait_for_episodes(builder, ["episode-1"], timeout=5)
