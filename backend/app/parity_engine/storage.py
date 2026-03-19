from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .episodes import validate_status_transition
from .models import EdgeRecord, GraphRecord, NodeRecord


class MetadataStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def upsert_graph(self, graph_id: str, name: str, description: str) -> GraphRecord:
        created_at = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO graphs (graph_id, name, description, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(graph_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description
                """,
                (graph_id, name, description, created_at),
            )
        return self.get_graph(graph_id)

    def get_graph(self, graph_id: str) -> GraphRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT graph_id, name, description, created_at FROM graphs WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()
        if row is None:
            raise KeyError(graph_id)
        return GraphRecord(
            graph_id=row["graph_id"],
            name=row["name"],
            description=row["description"],
            created_at=_parse_dt(row["created_at"]),
        )

    def delete_graph(self, graph_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM ontologies WHERE graph_id = ?", (graph_id,))
            conn.execute("DELETE FROM episodes WHERE graph_id = ?", (graph_id,))
            conn.execute("DELETE FROM nodes WHERE graph_id = ?", (graph_id,))
            conn.execute("DELETE FROM edges WHERE graph_id = ?", (graph_id,))
            conn.execute("DELETE FROM graphs WHERE graph_id = ?", (graph_id,))

    def save_ontology(self, graph_id: str, ontology: dict[str, Any]) -> None:
        payload = json.dumps(ontology, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ontologies (graph_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(graph_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (graph_id, payload, _utcnow()),
            )

    def get_ontology(self, graph_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM ontologies WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()
        if row is None:
            raise KeyError(graph_id)
        return json.loads(row["payload"])

    def upsert_episode(self, episode_id: str, graph_id: str, body: str, status: str) -> None:
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (episode_id, graph_id, body, status, created_at, updated_at, error)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(episode_id) DO UPDATE SET
                    graph_id = excluded.graph_id,
                    body = excluded.body,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    error = NULL
                """,
                (episode_id, graph_id, body, status, now, now),
            )

    def update_episode_status(self, episode_id: str, next_status: str, error: str | None = None) -> None:
        current = self.get_episode(episode_id)
        validate_status_transition(current["status"], next_status)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE episodes
                SET status = ?, updated_at = ?, error = ?
                WHERE episode_id = ?
                """,
                (next_status, _utcnow(), error, episode_id),
            )

    def get_episode(self, episode_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT episode_id, graph_id, body, status, created_at, updated_at, error
                FROM episodes
                WHERE episode_id = ?
                """,
                (episode_id,),
            ).fetchone()
        if row is None:
            raise KeyError(episode_id)
        return dict(row)

    def upsert_node(
        self,
        graph_id: str,
        uuid_: str,
        name: str,
        labels: list[str],
        summary: str,
        attributes: dict[str, Any],
    ) -> NodeRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO nodes (uuid_, graph_id, name, labels, summary, attributes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uuid_) DO UPDATE SET
                    name = excluded.name,
                    labels = excluded.labels,
                    summary = excluded.summary,
                    attributes = excluded.attributes
                """,
                (
                    uuid_,
                    graph_id,
                    name,
                    json.dumps(labels, ensure_ascii=False),
                    summary,
                    json.dumps(attributes, ensure_ascii=False, sort_keys=True),
                    _utcnow(),
                ),
            )
        return self.get_node(uuid_)

    def list_nodes(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None) -> list[NodeRecord]:
        query = """
            SELECT uuid_, graph_id, name, labels, summary, attributes, created_at
            FROM nodes
            WHERE graph_id = ?
        """
        params: list[Any] = [graph_id]
        if uuid_cursor:
            query += " AND uuid_ > ?"
            params.append(uuid_cursor)
        query += " ORDER BY uuid_ LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_node(row) for row in rows]

    def get_node(self, uuid_: str) -> NodeRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT uuid_, graph_id, name, labels, summary, attributes, created_at
                FROM nodes
                WHERE uuid_ = ?
                """,
                (uuid_,),
            ).fetchone()
        if row is None:
            raise KeyError(uuid_)
        return self._row_to_node(row)

    def upsert_edge(
        self,
        graph_id: str,
        uuid_: str,
        name: str,
        fact: str,
        source_node_uuid: str,
        target_node_uuid: str,
        attributes: dict[str, Any],
        valid_at: str | None,
        invalid_at: str | None,
        expired_at: str | None,
        episodes: list[str],
    ) -> EdgeRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO edges (
                    uuid_, graph_id, name, fact, source_node_uuid, target_node_uuid,
                    attributes, created_at, valid_at, invalid_at, expired_at, episodes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uuid_) DO UPDATE SET
                    name = excluded.name,
                    fact = excluded.fact,
                    source_node_uuid = excluded.source_node_uuid,
                    target_node_uuid = excluded.target_node_uuid,
                    attributes = excluded.attributes,
                    valid_at = excluded.valid_at,
                    invalid_at = excluded.invalid_at,
                    expired_at = excluded.expired_at,
                    episodes = excluded.episodes
                """,
                (
                    uuid_,
                    graph_id,
                    name,
                    fact,
                    source_node_uuid,
                    target_node_uuid,
                    json.dumps(attributes, ensure_ascii=False, sort_keys=True),
                    _utcnow(),
                    valid_at,
                    invalid_at,
                    expired_at,
                    json.dumps(episodes, ensure_ascii=False),
                ),
            )
        return self.get_edge(uuid_)

    def list_edges(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None) -> list[EdgeRecord]:
        query = """
            SELECT uuid_, graph_id, name, fact, source_node_uuid, target_node_uuid,
                   attributes, created_at, valid_at, invalid_at, expired_at, episodes
            FROM edges
            WHERE graph_id = ?
        """
        params: list[Any] = [graph_id]
        if uuid_cursor:
            query += " AND uuid_ > ?"
            params.append(uuid_cursor)
        query += " ORDER BY uuid_ LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def get_edge(self, uuid_: str) -> EdgeRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT uuid_, graph_id, name, fact, source_node_uuid, target_node_uuid,
                       attributes, created_at, valid_at, invalid_at, expired_at, episodes
                FROM edges
                WHERE uuid_ = ?
                """,
                (uuid_,),
            ).fetchone()
        if row is None:
            raise KeyError(uuid_)
        return self._row_to_edge(row)

    def get_node_edges(self, node_uuid: str) -> list[EdgeRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT uuid_, graph_id, name, fact, source_node_uuid, target_node_uuid,
                       attributes, created_at, valid_at, invalid_at, expired_at, episodes
                FROM edges
                WHERE source_node_uuid = ? OR target_node_uuid = ?
                ORDER BY uuid_
                """,
                (node_uuid, node_uuid),
            ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graphs (
                    graph_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ontologies (
                    graph_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    uuid_ TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    labels TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    uuid_ TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    source_node_uuid TEXT NOT NULL,
                    target_node_uuid TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    valid_at TEXT,
                    invalid_at TEXT,
                    expired_at TEXT,
                    episodes TEXT NOT NULL
                )
                """
            )

    def _row_to_node(self, row: sqlite3.Row) -> NodeRecord:
        return NodeRecord(
            uuid_=row["uuid_"],
            graph_id=row["graph_id"],
            name=row["name"],
            labels=json.loads(row["labels"]),
            summary=row["summary"],
            attributes=json.loads(row["attributes"]),
            created_at=_parse_dt(row["created_at"]),
        )

    def _row_to_edge(self, row: sqlite3.Row) -> EdgeRecord:
        return EdgeRecord(
            uuid_=row["uuid_"],
            graph_id=row["graph_id"],
            name=row["name"],
            fact=row["fact"],
            source_node_uuid=row["source_node_uuid"],
            target_node_uuid=row["target_node_uuid"],
            attributes=json.loads(row["attributes"]),
            created_at=_parse_dt(row["created_at"]),
            valid_at=_parse_optional_dt(row["valid_at"]),
            invalid_at=_parse_optional_dt(row["invalid_at"]),
            expired_at=_parse_optional_dt(row["expired_at"]),
            episodes=json.loads(row["episodes"]),
        )


MetadataStorage = MetadataStore


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_optional_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
