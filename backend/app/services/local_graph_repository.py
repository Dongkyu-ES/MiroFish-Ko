"""
SQLite 기반 로컬 그래프 저장소.

ZEP 제거를 위한 1차 저장 계층으로 사용한다.
이번 단계에서는 그래프 메타데이터/온톨로지/노드/엣지 snapshot 저장을 담당한다.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config import Config


@dataclass
class LocalGraphInfo:
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class LocalGraphRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or Config.LOCAL_GRAPH_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
    
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS graphs (
                    graph_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    ontology_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS nodes (
                    uuid TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    name TEXT,
                    labels_json TEXT NOT NULL,
                    summary TEXT,
                    attributes_json TEXT NOT NULL,
                    created_at TEXT,
                    FOREIGN KEY(graph_id) REFERENCES graphs(graph_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS edges (
                    uuid TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    name TEXT,
                    fact TEXT,
                    source_node_uuid TEXT NOT NULL,
                    target_node_uuid TEXT NOT NULL,
                    attributes_json TEXT NOT NULL,
                    created_at TEXT,
                    valid_at TEXT,
                    invalid_at TEXT,
                    expired_at TEXT,
                    episodes_json TEXT,
                    FOREIGN KEY(graph_id) REFERENCES graphs(graph_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_graph_id ON nodes(graph_id);
                CREATE INDEX IF NOT EXISTS idx_edges_graph_id ON edges(graph_id);
                """
            )
    
    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = f"local_{uuid.uuid4().hex[:16]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO graphs (graph_id, name, description) VALUES (?, ?, ?)",
                (graph_id, name, description),
            )
        return graph_id
    
    def get_graph(self, graph_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT graph_id, name, description, ontology_json, created_at, updated_at FROM graphs WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()
        if row is None:
            return None
        ontology = json.loads(row["ontology_json"]) if row["ontology_json"] else None
        return {
            "graph_id": row["graph_id"],
            "name": row["name"],
            "description": row["description"],
            "ontology": ontology,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    
    def save_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE graphs
                SET ontology_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE graph_id = ?
                """,
                (json.dumps(ontology, ensure_ascii=False), graph_id),
            )
    
    def replace_graph_data(
        self,
        graph_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM nodes WHERE graph_id = ?", (graph_id,))
            conn.execute("DELETE FROM edges WHERE graph_id = ?", (graph_id,))
            
            conn.executemany(
                """
                INSERT INTO nodes (uuid, graph_id, name, labels_json, summary, attributes_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        node["uuid"],
                        graph_id,
                        node.get("name"),
                        json.dumps(node.get("labels", []), ensure_ascii=False),
                        node.get("summary", ""),
                        json.dumps(node.get("attributes", {}), ensure_ascii=False),
                        node.get("created_at"),
                    )
                    for node in nodes
                ],
            )
            
            conn.executemany(
                """
                INSERT INTO edges (
                    uuid, graph_id, name, fact, source_node_uuid, target_node_uuid,
                    attributes_json, created_at, valid_at, invalid_at, expired_at, episodes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        edge["uuid"],
                        graph_id,
                        edge.get("name"),
                        edge.get("fact", ""),
                        edge["source_node_uuid"],
                        edge["target_node_uuid"],
                        json.dumps(edge.get("attributes", {}), ensure_ascii=False),
                        edge.get("created_at"),
                        edge.get("valid_at"),
                        edge.get("invalid_at"),
                        edge.get("expired_at"),
                        json.dumps(edge.get("episodes", []), ensure_ascii=False),
                    )
                    for edge in edges
                ],
            )

    def append_activity_batch(self, graph_id: str, activities: List[Dict[str, Any]]) -> int:
        inserted = 0
        with self._connect() as conn:
            for activity in activities:
                agent_name = (activity.get("agent_name") or "").strip()
                if not agent_name:
                    continue

                source_uuid = self._ensure_node(
                    conn=conn,
                    graph_id=graph_id,
                    name=agent_name,
                    labels=["Entity", "SimulationAgent"],
                    summary=f"Simulation agent on {activity.get('platform', 'unknown')}",
                    attributes={
                        "platform": activity.get("platform"),
                        "agent_id": activity.get("agent_id"),
                    },
                )

                target_name = self._extract_target_name(activity.get("action_args") or {})
                if target_name:
                    target_uuid = self._ensure_node(
                        conn=conn,
                        graph_id=graph_id,
                        name=target_name,
                        labels=["Entity", "ObservedActor"],
                        summary="Observed actor from simulation memory updates",
                        attributes={},
                    )
                else:
                    target_uuid = source_uuid

                conn.execute(
                    """
                    INSERT INTO edges (
                        uuid, graph_id, name, fact, source_node_uuid, target_node_uuid,
                        attributes_json, created_at, valid_at, invalid_at, expired_at, episodes_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"local_edge_{uuid.uuid4().hex[:12]}",
                        graph_id,
                        activity.get("action_type", "ACTED"),
                        activity.get("fact", ""),
                        source_uuid,
                        target_uuid,
                        json.dumps(
                            {
                                "platform": activity.get("platform"),
                                "round_num": activity.get("round_num"),
                                "timestamp": activity.get("timestamp"),
                                "action_args": activity.get("action_args", {}),
                            },
                            ensure_ascii=False,
                        ),
                        activity.get("timestamp"),
                        None,
                        None,
                        None,
                        json.dumps([], ensure_ascii=False),
                    ),
                )
                inserted += 1
        return inserted

    def _ensure_node(
        self,
        conn: sqlite3.Connection,
        graph_id: str,
        name: str,
        labels: List[str],
        summary: str,
        attributes: Dict[str, Any],
    ) -> str:
        row = conn.execute(
            "SELECT uuid FROM nodes WHERE graph_id = ? AND lower(name) = lower(?) LIMIT 1",
            (graph_id, name),
        ).fetchone()
        if row:
            return row["uuid"]

        node_uuid = f"local_node_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO nodes (uuid, graph_id, name, labels_json, summary, attributes_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_uuid,
                graph_id,
                name,
                json.dumps(labels, ensure_ascii=False),
                summary,
                json.dumps(attributes, ensure_ascii=False),
                None,
            ),
        )
        return node_uuid

    @staticmethod
    def _extract_target_name(action_args: Dict[str, Any]) -> Optional[str]:
        candidates = [
            action_args.get("post_author_name"),
            action_args.get("original_author_name"),
            action_args.get("target_user_name"),
            action_args.get("comment_author_name"),
            action_args.get("target_user"),
            action_args.get("user_id"),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            text = str(candidate).strip()
            if text:
                return text
        return None
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            nodes_rows = conn.execute(
                "SELECT * FROM nodes WHERE graph_id = ? ORDER BY rowid ASC",
                (graph_id,),
            ).fetchall()
            edges_rows = conn.execute(
                "SELECT * FROM edges WHERE graph_id = ? ORDER BY rowid ASC",
                (graph_id,),
            ).fetchall()
        
        nodes = [
            {
                "uuid": row["uuid"],
                "name": row["name"],
                "labels": json.loads(row["labels_json"]),
                "summary": row["summary"] or "",
                "attributes": json.loads(row["attributes_json"]),
                "created_at": row["created_at"],
            }
            for row in nodes_rows
        ]
        edges = [
            {
                "uuid": row["uuid"],
                "name": row["name"],
                "fact": row["fact"] or "",
                "source_node_uuid": row["source_node_uuid"],
                "target_node_uuid": row["target_node_uuid"],
                "attributes": json.loads(row["attributes_json"]),
                "created_at": row["created_at"],
                "valid_at": row["valid_at"],
                "invalid_at": row["invalid_at"],
                "expired_at": row["expired_at"],
                "episodes": json.loads(row["episodes_json"]) if row["episodes_json"] else [],
            }
            for row in edges_rows
        ]
        entity_types = sorted({
            label
            for node in nodes
            for label in node.get("labels", [])
            if label not in ["Entity", "Node"]
        })
        return {
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "entity_types": entity_types,
            "nodes": nodes,
            "edges": edges,
        }
    
    def get_graph_info(self, graph_id: str) -> LocalGraphInfo:
        data = self.get_graph_data(graph_id)
        entity_types = set()
        for node in data["nodes"]:
            for label in node.get("labels", []):
                if label not in ["Entity", "Node"]:
                    entity_types.add(label)
        return LocalGraphInfo(
            graph_id=graph_id,
            node_count=len(data["nodes"]),
            edge_count=len(data["edges"]),
            entity_types=sorted(entity_types),
        )
    
    def delete_graph(self, graph_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM nodes WHERE graph_id = ?", (graph_id,))
            conn.execute("DELETE FROM edges WHERE graph_id = ?", (graph_id,))
            cur = conn.execute("DELETE FROM graphs WHERE graph_id = ?", (graph_id,))
            return cur.rowcount > 0
