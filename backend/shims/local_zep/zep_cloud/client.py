"""zep_cloud client compatibility surface backed by the local adapter."""

from __future__ import annotations

from ._adapter import LocalGraphAdapter


class _NodeNamespace:
    def __init__(self, adapter: LocalGraphAdapter):
        self._adapter = adapter

    def get_by_graph_id(self, graph_id: str, limit: int, uuid_cursor: str | None = None):
        return self._adapter.get_nodes(graph_id, limit=limit, uuid_cursor=uuid_cursor)

    def get(self, uuid_: str):
        return self._adapter.get_node(uuid_)

    def get_edges(self, node_uuid: str):
        return self._adapter.get_node_edges(node_uuid)

    def get_entity_edges(self, node_uuid: str):
        return self.get_edges(node_uuid)


class _EdgeNamespace:
    def __init__(self, adapter: LocalGraphAdapter):
        self._adapter = adapter

    def get_by_graph_id(self, graph_id: str, limit: int, uuid_cursor: str | None = None):
        return self._adapter.get_edges(graph_id, limit=limit, uuid_cursor=uuid_cursor)


class _EpisodeNamespace:
    def __init__(self, adapter: LocalGraphAdapter):
        self._adapter = adapter

    def get(self, uuid_: str):
        return self._adapter.get_episode(uuid_)


class _GraphNamespace:
    def __init__(self, adapter: LocalGraphAdapter):
        self._adapter = adapter
        self.node = _NodeNamespace(adapter)
        self.edge = _EdgeNamespace(adapter)
        self.episode = _EpisodeNamespace(adapter)

    @property
    def _last_graph_id(self):
        return self._adapter._last_graph_id

    def create(self, graph_id: str, name: str, description: str):
        return self._adapter.create_graph(graph_id=graph_id, name=name, description=description)

    def set_ontology(self, graph_ids, entities=None, edges=None):
        return self._adapter.set_ontology(graph_ids=graph_ids, entities=entities, edges=edges)

    def add_batch(self, graph_id: str, episodes: list):
        return self._adapter.add_batch(graph_id=graph_id, episodes=episodes)

    def add(self, graph_id: str, type: str, data: str):
        return self._adapter.add(graph_id=graph_id, type=type, data=data)

    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges", reranker=None):
        return self._adapter.search(graph_id=graph_id, query=query, limit=limit, scope=scope, reranker=reranker)

    def delete(self, graph_id: str):
        return self._adapter.delete_graph(graph_id)


class Zep:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self._adapter = LocalGraphAdapter(base_url=base_url)
        self.graph = _GraphNamespace(self._adapter)
