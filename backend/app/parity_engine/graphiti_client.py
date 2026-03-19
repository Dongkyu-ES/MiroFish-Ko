from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import queue
import shutil
import threading
import time
from uuid import uuid4

from .config import load_engine_settings
from .extractor import GraphitiExtractionOverlay
from .graphiti_ontology_adapter import build_graphiti_extraction_config
from .provider_factory import ProviderSettings, build_provider_bundle
from .resolver import EntityResolver
from .search import HybridSearchOverlay
from .storage import MetadataStore

KUZU_DB_MAGIC = b"KUZU'"
logger = logging.getLogger("mirofish.parity.graphiti")


def _run_sync(coro):
    return asyncio.run(coro)


class GraphitiEngine:
    EPISODE_MAX_RETRIES = 3
    EPISODE_RETRY_DELAY_SECONDS = 2.0
    EPISODE_RETRY_BACKOFF = 2.0

    def __init__(
        self,
        db_path: str | Path,
        metadata_path: str | Path | None = None,
        storage_path: str | Path | None = None,
        episode_inline: bool | None = None,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_file = (
            Path(storage_path or metadata_path)
            if (storage_path or metadata_path) is not None
            else self.db_path.with_suffix(".sqlite3")
        )
        self.store = MetadataStore(metadata_file)
        self.storage = self.store
        self.settings = load_engine_settings()
        self.episode_inline = (
            self.settings.graphiti_episode_inline if episode_inline is None else episode_inline
        )
        self.resolver = EntityResolver()
        self.search_overlay = HybridSearchOverlay()
        self.provider_bundle = build_provider_bundle(
            ProviderSettings(
                provider=str(self.settings.llm_provider),
                llm_base_url=str(self.settings.llm_base_url),
                llm_api_key=str(self.settings.llm_api_key),
                llm_model=str(self.settings.llm_model),
                embedding_base_url=str(self.settings.embedding_base_url),
                embedding_api_key=str(self.settings.embedding_api_key),
                embedding_model=str(self.settings.embedding_model),
                rerank_base_url=str(self.settings.rerank_base_url),
                rerank_api_key=str(self.settings.rerank_api_key),
                rerank_model=str(self.settings.rerank_model),
                api_version=str(self.settings.api_version),
            )
        )
        self.extractor = GraphitiExtractionOverlay(
            llm_client=self.provider_bundle.llm_client,
            model=self.provider_bundle.llm_model,
            default_languages=self.settings.graphiti_default_languages,
        )
        self._episode_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._episode_worker = threading.Thread(target=self._episode_worker_loop, daemon=True)
        self._episode_worker.start()
        self.graphiti = self._build_graphiti()
        _run_sync(self._initialize_graphiti_indices())

    def create_graph(self, name: str, description: str, graph_id: str | None = None) -> str:
        resolved_graph_id = graph_id or f"mirofish_{uuid4().hex[:12]}"
        self.store.upsert_graph(graph_id=resolved_graph_id, name=name, description=description)
        return resolved_graph_id

    def delete_graph(self, graph_id: str) -> None:
        self.store.delete_graph(graph_id)

    def set_ontology(self, graph_id: str, ontology: dict) -> None:
        self.store.save_ontology(graph_id=graph_id, ontology=ontology)

    def create_episode(self, graph_id: str, episode_body: str, source_description: str = "mirofish") -> str:
        episode_id = self._register_episode(graph_id=graph_id, episode_body=episode_body)
        self.process_episode(episode_id, source_description=source_description)
        return episode_id

    def add_episode(self, graph_id: str, episode_body: str, source_description: str = "mirofish") -> str:
        return self.create_episode(graph_id, episode_body, source_description=source_description)

    def enqueue_episode(self, graph_id: str, episode_body: str, source_description: str = "mirofish") -> str:
        episode_id = self._register_episode(graph_id=graph_id, episode_body=episode_body)
        self._episode_queue.put((episode_id, source_description))
        return episode_id

    def process_episode(self, episode_id: str, source_description: str = "mirofish") -> None:
        episode = self.store.get_episode(episode_id)
        self.store.update_episode_status(episode_id, "processing")
        attempt = 0
        delay = self.EPISODE_RETRY_DELAY_SECONDS
        while True:
            try:
                self._process_episode_once(episode, episode_id, source_description)
            except Exception as exc:
                attempt += 1
                if not self._is_retryable_episode_error(exc) or attempt >= self.EPISODE_MAX_RETRIES:
                    self.store.update_episode_status(
                        episode_id,
                        "failed",
                        error=str(exc),
                    )
                    raise
                logger.warning(
                    "graphiti episode retrying after transient provider error",
                    extra={
                        "episode_id": episode_id,
                        "graph_id": episode["graph_id"],
                        "attempt": attempt,
                        "max_retries": self.EPISODE_MAX_RETRIES,
                        "delay_seconds": delay,
                        "error": str(exc),
                    },
                )
                time.sleep(delay)
                delay *= self.EPISODE_RETRY_BACKOFF
                continue

            self.store.update_episode_status(episode_id, "processed")
            return

    def _process_episode_once(self, episode: dict, episode_id: str, source_description: str) -> None:
        if not self.episode_inline:
            if not self._has_live_provider_config():
                raise RuntimeError(
                    "Graphiti provider configuration is required for non-inline episode ingestion"
                )
            ontology = self.store.get_ontology(episode["graph_id"])
            extraction_config = build_graphiti_extraction_config(ontology)
            logger.info(
                "graphiti extraction config prepared",
                extra={
                    "graph_id": episode["graph_id"],
                    "entity_type_count": len(extraction_config.entity_types),
                    "edge_type_count": len(extraction_config.edge_types),
                    "edge_signature_count": len(extraction_config.edge_type_map),
                    "instruction_chars": len(extraction_config.custom_extraction_instructions),
                },
            )
            if not hasattr(self.driver, "_database"):
                self.driver._database = episode["graph_id"]
            else:
                self.driver._database = episode["graph_id"]
            result = _run_sync(
                self.graphiti.add_episode(
                    name=f"episode:{episode_id}",
                    episode_body=episode["body"],
                    source_description=source_description,
                    reference_time=datetime.now(timezone.utc),
                    group_id=episode["graph_id"],
                    entity_types=extraction_config.entity_types,
                    edge_types=extraction_config.edge_types,
                    edge_type_map=extraction_config.edge_type_map,
                    custom_extraction_instructions=extraction_config.custom_extraction_instructions,
                )
            )
            logger.info(
                "graphiti episode processed",
                extra={
                    "graph_id": episode["graph_id"],
                    "episode_id": episode_id,
                    "node_result_count": len(getattr(result, "nodes", []) or []),
                    "edge_result_count": len(getattr(result, "edges", []) or []),
                },
            )
            self._persist_graphiti_result(episode["graph_id"], episode_id, result)
            return

        if not self._has_inline_llm_config():
            raise RuntimeError("provider configuration is required for inline llm extraction")
        self._persist_extraction(episode["graph_id"], episode_id, episode["body"])

    def is_ready(self) -> bool:
        return self._has_inline_llm_config() if self.episode_inline else self._has_live_provider_config()

    def get_nodes(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None):
        return self.store.list_nodes(graph_id, limit=limit, uuid_cursor=uuid_cursor)

    def get_edges(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None):
        return self.store.list_edges(graph_id, limit=limit, uuid_cursor=uuid_cursor)

    def list_nodes(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None):
        return [self._node_to_dict(node) for node in self.get_nodes(graph_id, limit=limit, uuid_cursor=uuid_cursor)]

    def list_edges(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None):
        return [self._edge_to_dict(edge) for edge in self.get_edges(graph_id, limit=limit, uuid_cursor=uuid_cursor)]

    def get_node(self, uuid_: str):
        return self._node_to_dict(self.store.get_node(uuid_))

    def get_node_edges(self, node_uuid: str):
        return [self._edge_to_dict(edge) for edge in self.store.get_node_edges(node_uuid)]

    def get_episode(self, episode_id: str):
        return self.store.get_episode(episode_id)

    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges") -> dict:
        ranked = self.search_overlay.rank(
            query=query,
            node_candidates=[self._node_to_dict(node) for node in self.get_nodes(graph_id, limit=1000)],
            edge_candidates=[self._edge_to_dict(edge) for edge in self.get_edges(graph_id, limit=1000)],
        )
        if scope == "nodes":
            ranked["edges"] = []
            ranked["nodes"] = ranked["nodes"][:limit]
        elif scope == "edges":
            ranked["nodes"] = []
            ranked["edges"] = ranked["edges"][:limit]
        else:
            ranked["nodes"] = ranked["nodes"][:limit]
            ranked["edges"] = ranked["edges"][:limit]
        return ranked

    def _persist_extraction(self, graph_id: str, episode_id: str, body: str) -> None:
        try:
            ontology = self.store.get_ontology(graph_id)
        except KeyError:
            return

        extraction = self.extractor.extract(body, ontology)
        logger.info(
            "inline extraction summary",
            extra={
                "graph_id": graph_id,
                "episode_id": episode_id,
                "sentence_count": extraction.get("sentence_count", 0),
                "candidate_count": extraction.get("candidate_count", 0),
                "typed_entity_count": extraction.get("typed_entity_count", 0),
                "edge_count": len(extraction.get("edges", [])),
                "dropped_candidate_count": extraction.get("dropped_candidate_count", 0),
            },
        )
        entity_uuid_map: dict[str, str] = {}
        resolver = self.resolver

        existing_nodes = self.get_nodes(graph_id, limit=1000)
        for entity in extraction.get("entities", []):
            entity_name = resolver.promote_display_name(entity["name"])
            normalized_entity = {
                **entity,
                "name": entity_name,
                "attributes": {
                    **(entity.get("attributes") or {}),
                    "name": entity_name,
                },
            }
            existing = self._find_existing_node(existing_nodes, normalized_entity)
            node_uuid = existing.uuid_ if existing else f"node_{uuid4().hex[:12]}"
            existing_summary = existing.summary if existing else ""
            summary = body if not existing_summary or body not in existing_summary else existing_summary
            labels = [normalized_entity.get("type", "Entity")]
            attributes = normalized_entity.get("attributes") or {"name": entity_name}
            node_name = entity_name

            if existing is not None:
                node_name = self.resolver.preferred_name(existing.name, entity["name"])
                labels = self._merge_labels(list(existing.labels), labels)
                attributes = self._merge_attributes(dict(existing.attributes), attributes)
                summary = self._merge_summary(existing.summary, body)

            node_record = self.store.upsert_node(
                graph_id=graph_id,
                uuid_=node_uuid,
                name=node_name,
                labels=labels,
                summary=summary,
                attributes=attributes,
            )
            self._upsert_inline_existing_node(existing_nodes, node_record)
            entity_uuid_map[entity["name"]] = node_uuid
            entity_uuid_map[entity_name] = node_uuid

        timestamp = datetime.now(timezone.utc).isoformat()
        for edge in extraction.get("edges", []):
            source_uuid = entity_uuid_map.get(edge["source"])
            target_uuid = entity_uuid_map.get(edge["target"])
            if not source_uuid or not target_uuid:
                continue
            self.store.upsert_edge(
                graph_id=graph_id,
                uuid_=f"edge_{uuid4().hex[:12]}",
                name=edge["name"],
                fact=edge["fact"],
                source_node_uuid=source_uuid,
                target_node_uuid=target_uuid,
                attributes={
                    "edge_type": edge["name"],
                    "fact": edge["fact"],
                },
                valid_at=timestamp,
                invalid_at=None,
                expired_at=None,
                episodes=[episode_id],
            )

    def _persist_graphiti_result(self, graph_id: str, episode_id: str, result) -> None:
        nodes = getattr(result, "nodes", []) or []
        edges = getattr(result, "edges", []) or []
        existing_nodes = self.get_nodes(graph_id, limit=1000)
        existing_by_uuid = {node.uuid_: node for node in existing_nodes}
        known_nodes = [self._resolver_entry_from_record(node) for node in existing_nodes]
        known_keys = {
            self.resolver.canonical_entity_key(entry["name"], entry["type"]): entry["uuid_"]
            for entry in known_nodes
        }
        merged_nodes: dict[str, dict] = {}
        canonical_uuid_map: dict[str, str] = {}

        for node in nodes:
            node_payload = self._graphiti_node_to_payload(graph_id, node)
            raw_uuid = node_payload["uuid_"]
            canonical_uuid = self._resolve_canonical_node_uuid(
                node_payload=node_payload,
                known_nodes=known_nodes,
                known_keys=known_keys,
            )
            canonical_uuid_map[raw_uuid] = canonical_uuid

            base_payload = merged_nodes.get(canonical_uuid)
            if base_payload is None:
                existing = existing_by_uuid.get(canonical_uuid)
                base_payload = (
                    self._payload_from_existing_node(existing)
                    if existing is not None
                    else dict(node_payload, uuid_=canonical_uuid)
                )

            merged_payload = self._merge_node_payload(base_payload, node_payload, canonical_uuid)
            merged_nodes[canonical_uuid] = merged_payload
            self._upsert_known_node(known_nodes, merged_payload)
            known_keys[
                self.resolver.canonical_entity_key(
                    merged_payload["name"],
                    merged_payload["labels"][0] if merged_payload["labels"] else "Entity",
                )
            ] = canonical_uuid

        for payload in merged_nodes.values():
            self.store.upsert_node(
                graph_id=graph_id,
                uuid_=payload["uuid_"],
                name=payload["name"],
                labels=payload["labels"],
                summary=payload["summary"],
                attributes=payload["attributes"],
            )

        for edge in edges:
            edge_uuid = getattr(edge, "uuid", None) or getattr(edge, "uuid_", None) or f"edge_{uuid4().hex[:12]}"
            source_uuid = canonical_uuid_map.get(str(getattr(edge, "source_node_uuid", "") or ""), str(getattr(edge, "source_node_uuid", "") or ""))
            target_uuid = canonical_uuid_map.get(str(getattr(edge, "target_node_uuid", "") or ""), str(getattr(edge, "target_node_uuid", "") or ""))
            self.store.upsert_edge(
                graph_id=graph_id,
                uuid_=str(edge_uuid),
                name=str(getattr(edge, "name", "") or ""),
                fact=str(getattr(edge, "fact", "") or ""),
                source_node_uuid=source_uuid,
                target_node_uuid=target_uuid,
                attributes=getattr(edge, "attributes", None) or {},
                valid_at=str(getattr(edge, "valid_at", "") or "") or None,
                invalid_at=str(getattr(edge, "invalid_at", "") or "") or None,
                expired_at=str(getattr(edge, "expired_at", "") or "") or None,
                episodes=[str(item) for item in (getattr(edge, "episodes", None) or getattr(edge, "episode_ids", None) or [episode_id])],
            )

    def _graphiti_node_to_payload(self, graph_id: str, node) -> dict:
        node_uuid = getattr(node, "uuid", None) or getattr(node, "uuid_", None) or f"node_{uuid4().hex[:12]}"
        labels = list(getattr(node, "labels", []) or [])
        if not labels:
            node_type = getattr(node, "entity_type", None) or getattr(node, "type", None)
            if node_type:
                labels = [str(node_type)]
        return {
            "graph_id": graph_id,
            "uuid_": str(node_uuid),
            "name": str(getattr(node, "name", "") or ""),
            "labels": [str(label) for label in labels] or ["Entity"],
            "summary": str(getattr(node, "summary", "") or ""),
            "attributes": getattr(node, "attributes", None) or {},
        }

    def _payload_from_existing_node(self, node) -> dict:
        return {
            "graph_id": node.graph_id,
            "uuid_": node.uuid_,
            "name": node.name,
            "labels": list(node.labels),
            "summary": node.summary,
            "attributes": dict(node.attributes),
        }

    def _resolve_canonical_node_uuid(
        self,
        node_payload: dict,
        known_nodes: list[dict],
        known_keys: dict[str, str],
    ) -> str:
        node_type = node_payload["labels"][0] if node_payload["labels"] else "Entity"
        key = self.resolver.canonical_entity_key(node_payload["name"], node_type)
        if key and key in known_keys:
            return known_keys[key]

        matching = self._find_matching_known_node(known_nodes, node_payload["name"], node_type)
        if matching is not None:
            return matching["uuid_"]

        known_keys[key] = node_payload["uuid_"]
        return node_payload["uuid_"]

    def _find_matching_known_node(self, known_nodes: list[dict], name: str, node_type: str) -> dict | None:
        candidate = {"name": name, "type": node_type}
        for known in known_nodes:
            if self.resolver.should_merge(candidate, {"name": known["name"], "type": known["type"]}):
                return known
        return None

    def _merge_node_payload(self, base: dict, incoming: dict, canonical_uuid: str) -> dict:
        merged = dict(base)
        merged["uuid_"] = canonical_uuid
        merged["graph_id"] = incoming["graph_id"]
        merged["name"] = merged["name"] or incoming["name"]
        merged["labels"] = self._merge_labels(merged.get("labels", []), incoming.get("labels", []))
        merged["summary"] = self._merge_summary(merged.get("summary", ""), incoming.get("summary", ""))
        merged["attributes"] = self._merge_attributes(merged.get("attributes", {}), incoming.get("attributes", {}))
        return merged

    def _merge_labels(self, left: list[str], right: list[str]) -> list[str]:
        return list(dict.fromkeys([*left, *right])) or ["Entity"]

    def _merge_summary(self, left: str, right: str) -> str:
        left = left.strip()
        right = right.strip()
        if not left:
            return right
        if not right or right in left:
            return left
        return f"{left}\n{right}"

    def _merge_attributes(self, left: dict, right: dict) -> dict:
        merged = dict(left)
        for key, value in right.items():
            if key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = value
        return merged

    def _resolver_entry_from_record(self, node) -> dict:
        return {
            "uuid_": node.uuid_,
            "name": node.name,
            "type": node.labels[0] if node.labels else "Entity",
        }

    def _upsert_known_node(self, known_nodes: list[dict], payload: dict) -> None:
        payload_type = payload["labels"][0] if payload["labels"] else "Entity"
        for known in known_nodes:
            if known["uuid_"] == payload["uuid_"]:
                known["name"] = payload["name"]
                known["type"] = payload_type
                return
        known_nodes.append(
            {
                "uuid_": payload["uuid_"],
                "name": payload["name"],
                "type": payload_type,
            }
        )

    def _upsert_inline_existing_node(self, existing_nodes: list, node_record) -> None:
        for index, existing in enumerate(existing_nodes):
            if existing.uuid_ == node_record.uuid_:
                existing_nodes[index] = node_record
                return
        existing_nodes.append(node_record)

    def _find_existing_node(self, existing_nodes, entity: dict):
        for node in existing_nodes:
            if self.resolver.should_merge(
                {"name": entity["name"], "type": entity.get("type", "Entity")},
                {
                    "name": node.name,
                    "type": node.labels[0] if node.labels else "Entity",
                },
            ):
                return node
        return None

    def _node_to_dict(self, node) -> dict:
        return {
            "uuid": node.uuid_,
            "uuid_": node.uuid_,
            "name": node.name,
            "labels": node.labels,
            "summary": node.summary,
            "attributes": node.attributes,
            "created_at": node.created_at.isoformat(),
        }

    def _edge_to_dict(self, edge) -> dict:
        return {
            "uuid": edge.uuid_,
            "uuid_": edge.uuid_,
            "name": edge.name,
            "fact": edge.fact,
            "source_node_uuid": edge.source_node_uuid,
            "target_node_uuid": edge.target_node_uuid,
            "attributes": edge.attributes,
            "created_at": edge.created_at.isoformat(),
            "valid_at": edge.valid_at.isoformat() if edge.valid_at else None,
            "invalid_at": edge.invalid_at.isoformat() if edge.invalid_at else None,
            "expired_at": edge.expired_at.isoformat() if edge.expired_at else None,
            "episodes": edge.episodes,
        }

    def _has_live_provider_config(self) -> bool:
        return all(
            [
                bool(self.settings.llm_api_key),
                bool(self.settings.llm_model),
                bool(self.settings.embedding_model),
                bool(self.settings.rerank_model),
            ]
        )

    def _has_inline_llm_config(self) -> bool:
        return all(
            [
                bool(self.settings.llm_api_key),
                bool(self.settings.llm_model),
            ]
        )

    @staticmethod
    def _extract_status_code(error: Exception) -> int | None:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    @classmethod
    def _is_retryable_episode_error(cls, error: Exception) -> bool:
        if isinstance(error, (ConnectionError, TimeoutError, OSError)):
            return True

        status_code = cls._extract_status_code(error)
        if status_code == 429:
            return True
        if isinstance(status_code, int) and status_code >= 500:
            return True

        message = str(error).lower()
        retryable_markers = (
            "connection error",
            "connect error",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "server error",
            "connection reset",
            "connection aborted",
        )
        return any(marker in message for marker in retryable_markers)

    def _build_graphiti(self):
        from graphiti_core.driver.kuzu_driver import KuzuDriver
        from graphiti_core.graphiti import Graphiti

        had_existing_db = self.db_path.exists()
        if had_existing_db and not self._is_likely_valid_kuzu_db(self.db_path):
            self._quarantine_invalid_database()
            had_existing_db = False

        try:
            self.driver = KuzuDriver(db=str(self.db_path))
        except RuntimeError:
            if not had_existing_db:
                raise
            self._quarantine_invalid_database()
            self.driver = KuzuDriver(db=str(self.db_path))
        return Graphiti(
            graph_driver=self.driver,
            llm_client=self.provider_bundle.graphiti_llm_client,
            embedder=self.provider_bundle.graphiti_embedder,
            cross_encoder=self.provider_bundle.graphiti_reranker,
        )

    async def _initialize_graphiti_indices(self) -> None:
        await self.graphiti.build_indices_and_constraints()

    def _register_episode(self, graph_id: str, episode_body: str) -> str:
        episode_id = f"episode_{uuid4().hex[:12]}"
        self.store.upsert_episode(
            episode_id=episode_id,
            graph_id=graph_id,
            body=episode_body,
            status="queued",
        )
        return episode_id

    def _episode_worker_loop(self) -> None:
        while True:
            episode_id, source_description = self._episode_queue.get()
            try:
                self.process_episode(episode_id, source_description=source_description or "mirofish")
            except Exception:
                logger.exception(
                    "graphiti episode worker failed",
                    extra={"episode_id": episode_id},
                )
            finally:
                self._episode_queue.task_done()

    def _is_likely_valid_kuzu_db(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            if path.stat().st_size < len(KUZU_DB_MAGIC):
                return False
            with path.open("rb") as handle:
                return handle.read(len(KUZU_DB_MAGIC)) == KUZU_DB_MAGIC
        except OSError:
            return False

    def _quarantine_invalid_database(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        quarantine_path = self.db_path.with_name(f"{self.db_path.name}.corrupt-{timestamp}")
        self._move_if_exists(self.db_path, quarantine_path)
        self._move_if_exists(
            self.db_path.with_name(f"{self.db_path.name}.wal"),
            quarantine_path.with_name(f"{quarantine_path.name}.wal"),
        )

        metadata_path = self.store.db_path
        metadata_quarantine_path = metadata_path.with_name(f"{metadata_path.name}.corrupt-{timestamp}")
        self._move_if_exists(metadata_path, metadata_quarantine_path)
        self._move_if_exists(
            metadata_path.with_name(f"{metadata_path.name}-wal"),
            metadata_quarantine_path.with_name(f"{metadata_quarantine_path.name}-wal"),
        )
        self._move_if_exists(
            metadata_path.with_name(f"{metadata_path.name}-shm"),
            metadata_quarantine_path.with_name(f"{metadata_quarantine_path.name}-shm"),
        )

        # Recreate the SQLite metadata sidecar so subsequent store operations use a clean schema.
        self.store = MetadataStore(metadata_path)
        self.storage = self.store

    def _move_if_exists(self, source: Path, target: Path) -> None:
        if source.exists():
            shutil.move(str(source), str(target))
