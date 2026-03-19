"""HTTP-backed compatibility adapter that preserves the zep_cloud contract surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os

import httpx

from . import InternalServerError

from backend.app.parity_engine.ontology import normalize_ontology


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class GraphResponse:
    graph_id: str
    name: str
    description: str
    type: str = "Graph"


@dataclass(slots=True)
class EpisodeResponse:
    uuid_: str
    processed: bool = True
    type: str = "Episode"
    status: str | None = None
    error: str | None = None
    task_id: str | None = None

    @property
    def episode_uuid(self) -> str:
        return self.uuid_


@dataclass(slots=True)
class NodeResponse:
    uuid_: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict
    created_at: str


@dataclass(slots=True)
class EdgeResponse:
    uuid_: str
    name: str
    fact: str
    fact_type: str | None
    source_node_uuid: str
    target_node_uuid: str
    attributes: dict
    created_at: str
    valid_at: str | None = None
    invalid_at: str | None = None
    expired_at: str | None = None
    episodes: list[str] = field(default_factory=list)

    @property
    def episode_ids(self) -> list[str]:
        return self.episodes


@dataclass(slots=True)
class SearchResponse:
    edges: list[EdgeResponse] = field(default_factory=list)
    nodes: list[NodeResponse] = field(default_factory=list)


class LocalGraphAdapter:
    def __init__(self, base_url: str | None = None, timeout_seconds: int | None = None):
        self.base_url = base_url or os.environ.get("ENGINE_BASE_URL", "http://127.0.0.1:8123")
        self.timeout_seconds = timeout_seconds or int(os.environ.get("ENGINE_TIMEOUT_SECONDS", "30"))
        self.shared_token = os.environ.get("ENGINE_SHARED_TOKEN") or os.environ.get("SECRET_KEY", "")
        self.client = httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds)
        self._last_graph_id: str | None = None

    def create_graph(self, graph_id: str, name: str, description: str) -> GraphResponse:
        self._last_graph_id = graph_id
        payload = self._request(
            "POST",
            "/v1/graphs",
            json={
                "graph_id": graph_id,
                "name": name,
                "description": description,
            },
        )
        return GraphResponse(
            graph_id=payload["graph_id"],
            name=payload.get("name", name),
            description=payload.get("description", description),
            type=payload.get("type", "Graph"),
        )

    def set_ontology(self, graph_ids: list[str], entities: dict | None, edges: dict | None) -> None:
        ontology = normalize_ontology(
            {
                "entity_types": self._serialize_entities(entities or {}),
                "edge_types": self._serialize_edges(edges or {}),
            }
        )
        for graph_id in graph_ids:
            self._last_graph_id = graph_id
            self._request("POST", f"/v1/graphs/{graph_id}/ontology", json=ontology)

    def add_batch(self, graph_id: str, episodes: list) -> list[EpisodeResponse]:
        self._last_graph_id = graph_id
        payload = self._request(
            "POST",
            f"/v1/graphs/{graph_id}/episodes/batch",
            json={
                "episodes": [
                    {
                        "data": episode.data,
                        "type": episode.type,
                    }
                    for episode in episodes
                ]
            },
        )
        episode_uuids = payload.get("episode_uuids") or []
        if not episode_uuids and payload.get("episode_uuid"):
            episode_uuids = [payload["episode_uuid"]]
        processed = bool(payload.get("processed_initial", False))
        if not episode_uuids:
            return []
        return [
            EpisodeResponse(
                uuid_=episode_uuid,
                processed=processed,
                type=payload.get("type", "Episode"),
            )
            for episode_uuid in episode_uuids
        ]

    def add(self, graph_id: str, type: str, data: str) -> EpisodeResponse:
        self._last_graph_id = graph_id
        payload = self._request(
            "POST",
            f"/v1/graphs/{graph_id}/episodes",
            json={"type": type, "data": data},
        )
        return EpisodeResponse(
            uuid_=payload.get("episode_uuid", ""),
            processed=payload.get("processed", True),
            type=payload.get("type", "Episode"),
        )

    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges", reranker=None) -> SearchResponse:
        self._last_graph_id = graph_id
        payload = self._request(
            "GET",
            f"/v1/graphs/{graph_id}/search",
            params={
                "query": query,
                "limit": limit,
                "scope": scope,
                "reranker": reranker,
            },
        )
        return SearchResponse(
            edges=[self._dict_to_edge(edge) for edge in payload.get("edges", [])],
            nodes=[self._dict_to_node(node) for node in payload.get("nodes", [])],
        )

    def delete_graph(self, graph_id: str) -> None:
        self._last_graph_id = graph_id
        self._request("DELETE", f"/v1/graphs/{graph_id}")

    def get_nodes(self, graph_id: str, limit: int, uuid_cursor: str | None = None) -> list[NodeResponse]:
        self._last_graph_id = graph_id
        payload = self._request(
            "GET",
            f"/v1/graphs/{graph_id}/nodes",
            params={"limit": limit, "uuid_cursor": uuid_cursor},
        )
        return [self._dict_to_node(node) for node in payload]

    def get_node(self, uuid_: str) -> NodeResponse:
        payload = self._request("GET", f"/v1/nodes/{uuid_}")
        return self._dict_to_node(payload)

    def get_node_edges(self, node_uuid: str) -> list[EdgeResponse]:
        payload = self._request("GET", f"/v1/nodes/{node_uuid}/edges")
        return [self._dict_to_edge(edge) for edge in payload]

    def get_edges(self, graph_id: str, limit: int, uuid_cursor: str | None = None) -> list[EdgeResponse]:
        self._last_graph_id = graph_id
        payload = self._request(
            "GET",
            f"/v1/graphs/{graph_id}/edges",
            params={"limit": limit, "uuid_cursor": uuid_cursor},
        )
        return [self._dict_to_edge(edge) for edge in payload]

    def get_episode(self, uuid_: str) -> EpisodeResponse:
        payload = self._request("GET", f"/v1/episodes/{uuid_}")
        return EpisodeResponse(
            uuid_=payload.get("episode_uuid", uuid_),
            processed=payload.get("processed", True),
            type=payload.get("type", "Episode"),
            status=payload.get("status"),
            error=payload.get("error"),
            task_id=payload.get("task_id"),
        )

    def _request(self, method: str, path: str, **kwargs):
        try:
            headers = dict(kwargs.pop("headers", {}) or {})
            if self.shared_token:
                headers.setdefault("X-MiroFish-Engine-Token", self.shared_token)
            response = self.client.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise InternalServerError("Parity engine is unavailable") from exc
        except httpx.HTTPError as exc:
            raise InternalServerError(str(exc)) from exc

    def _serialize_entities(self, entities: dict) -> list[dict]:
        serialized = []
        for name, entity_class in entities.items():
            model_fields = getattr(entity_class, "model_fields", {})
            attributes = [
                {"name": field_name, "description": field.description or field_name}
                for field_name, field in model_fields.items()
            ]
            serialized.append(
                {
                    "name": name,
                    "description": getattr(entity_class, "__doc__", None) or f"{name} entity",
                    "attributes": attributes,
                }
            )
        return serialized

    def _serialize_edges(self, edges: dict) -> list[dict]:
        serialized = []
        for edge_name, edge_def in edges.items():
            edge_class, source_targets = edge_def
            model_fields = getattr(edge_class, "model_fields", {})
            attributes = [
                {"name": field_name, "description": field.description or field_name}
                for field_name, field in model_fields.items()
            ]
            serialized.append(
                {
                    "name": edge_name,
                    "description": getattr(edge_class, "__doc__", None) or f"{edge_name} relationship",
                    "source_targets": [
                        {"source": item.source, "target": item.target} for item in source_targets
                    ],
                    "attributes": attributes,
                }
            )
        return serialized

    def _dict_to_node(self, payload: dict) -> NodeResponse:
        return NodeResponse(
            uuid_=payload.get("uuid_") or payload.get("uuid", ""),
            name=payload.get("name", ""),
            labels=payload.get("labels", []),
            summary=payload.get("summary", ""),
            attributes=payload.get("attributes", {}),
            created_at=payload.get("created_at", _utc_now()),
        )

    def _dict_to_edge(self, payload: dict) -> EdgeResponse:
        return EdgeResponse(
            uuid_=payload.get("uuid_") or payload.get("uuid", ""),
            name=payload.get("name", ""),
            fact=payload.get("fact", ""),
            fact_type=payload.get("fact_type"),
            source_node_uuid=payload.get("source_node_uuid", ""),
            target_node_uuid=payload.get("target_node_uuid", ""),
            attributes=payload.get("attributes", {}),
            created_at=payload.get("created_at", _utc_now()),
            valid_at=payload.get("valid_at"),
            invalid_at=payload.get("invalid_at"),
            expired_at=payload.get("expired_at"),
            episodes=payload.get("episodes", []),
        )
