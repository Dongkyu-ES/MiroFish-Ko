"""Baseline artifact layout and persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .contracts import BaselineSnapshot, CorpusItem


ARTIFACT_FILENAMES = {
    "graph": "graph.json",
    "search": "search.json",
    "profile": "profile.json",
    "report": "report.json",
    "memory_update": "memory_update.json",
    "metadata": "metadata.json",
    "raw_api_examples": "raw_api_examples.json",
}


class BaselineCaptureProbe(Protocol):
    def capture_case(
        self,
        case: CorpusItem,
    ) -> tuple[BaselineSnapshot, dict[str, Any] | None, dict[str, Any] | None]:
        ...


class ZepBaselineCaptureRunner:
    def __init__(self, probe: BaselineCaptureProbe):
        self.probe = probe

    def capture_case(self, case: CorpusItem, output_root: str | Path) -> dict[str, Path]:
        snapshot, metadata, raw_api_examples = self.probe.capture_case(case)
        return write_baseline_bundle(
            output_root=output_root,
            snapshot=snapshot,
            metadata=metadata,
            raw_api_examples=raw_api_examples,
        )

    def capture_manifest(self, manifest_path: str | Path, output_root: str | Path) -> dict[str, dict[str, Path]]:
        cases = load_corpus_manifest(manifest_path)
        return {case.id: self.capture_case(case, output_root) for case in cases}


class MiroFishZepBaselineProbe:
    """Best-effort live Zep baseline probe using current MiroFish services."""

    def __init__(self, fixtures_root: str | Path):
        from backend.app.services.graph_builder import GraphBuilderService
        from backend.app.services.oasis_profile_generator import OasisProfileGenerator
        from backend.app.services.ontology_generator import OntologyGenerator
        from backend.app.services.zep_entity_reader import ZepEntityReader
        from backend.app.services.zep_tools import ZepToolsService

        self.fixtures_root = Path(fixtures_root)
        self.graph_builder = GraphBuilderService()
        self.ontology_generator = OntologyGenerator()
        self.entity_reader = ZepEntityReader()
        self.zep_tools = ZepToolsService()
        self.profile_generator = OasisProfileGenerator()

    def capture_case(
        self,
        case: CorpusItem,
    ) -> tuple[BaselineSnapshot, dict[str, Any] | None, dict[str, Any] | None]:
        document_texts = self._load_documents(case.documents)
        ontology = case.ontology or self.ontology_generator.generate(
            document_texts=document_texts,
            simulation_requirement=case.simulation_requirement,
        )
        combined_text = "\n\n".join(document_texts)

        graph_id = self.graph_builder.create_graph(f"Baseline {case.id}")
        self.graph_builder.set_ontology(graph_id, ontology)
        episodes = self.graph_builder.add_text_batches(graph_id=graph_id, chunks=[combined_text], batch_size=1)
        self.graph_builder._wait_for_episodes(episodes)  # existing MiroFish polling contract

        graph_payload = self.graph_builder.get_graph_data(graph_id)
        search_payloads = [self._capture_search(graph_id, query) for query in case.queries]
        profile_payload = self._capture_profile(graph_id, ontology)
        report_payload = self._capture_report(graph_id, case.queries)
        memory_update_payload = self._capture_memory_update(graph_id)

        snapshot = BaselineSnapshot.model_validate(
            {
                "case_id": case.id,
                "captured_at": _utc_now(),
                "graph": {
                    "nodes": graph_payload.get("nodes", []),
                    "edges": graph_payload.get("edges", []),
                },
                "search": search_payloads,
                "profile": profile_payload,
                "report": report_payload,
                "memory_update": memory_update_payload,
                "metadata": {
                    "graph_id": graph_id,
                    "language": case.language,
                    "documents": case.documents,
                },
            }
        )
        raw_api_examples = {
            "graph.create": {
                "graph_id": graph_id,
                "name": f"Baseline {case.id}",
                "description": "MiroFish baseline capture graph",
                "type": "Graph",
            },
            "graph.add_batch": {
                "count": len(episodes),
                "episode_uuid": episodes[-1] if episodes else None,
                "processed_initial": False,
                "type": "Episode",
            },
        }
        metadata = {
            "provider": "zep",
            "graph_id": graph_id,
            "captured_at": snapshot.captured_at,
        }
        return snapshot, metadata, raw_api_examples

    def _load_documents(self, documents: list[str]) -> list[str]:
        resolved = []
        for document in documents:
            path = self.fixtures_root / document
            resolved.append(path.read_text(encoding="utf-8"))
        return resolved

    def _capture_search(self, graph_id: str, query: str) -> dict[str, Any]:
        edge_result = self.zep_tools.search_graph(graph_id=graph_id, query=query, limit=10, scope="edges")
        node_result = self.zep_tools.search_graph(graph_id=graph_id, query=query, limit=10, scope="nodes")
        return {
            "query": query,
            "scope": "hybrid",
            "edges": edge_result.edges,
            "nodes": node_result.nodes,
            "facts": edge_result.facts or node_result.facts,
        }

    def _capture_profile(self, graph_id: str, ontology: dict[str, Any]) -> dict[str, Any]:
        defined_types = [entity["name"] for entity in ontology.get("entity_types", [])]
        filtered = self.entity_reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=defined_types,
            enrich_with_edges=True,
        )
        profiles = self.profile_generator.generate_profiles_from_entities(
            entities=filtered.entities[:3],
            use_llm=False,
            graph_id=graph_id,
            parallel_count=1,
        )
        return {
            "context": "\n\n".join(
                self.profile_generator._search_zep_for_entity(entity).get("context", "")
                for entity in filtered.entities[:3]
            ),
            "profiles": [profile.to_dict() for profile in profiles],
            "metadata": {
                "entity_count": filtered.filtered_count,
                "entity_types": list(filtered.entity_types),
            },
        }

    def _capture_report(self, graph_id: str, queries: list[str]) -> dict[str, Any]:
        tool_outputs = {
            "search": [self.zep_tools.search_graph(graph_id=graph_id, query=query).to_dict() for query in queries[:2]],
            "statistics": self.zep_tools.get_graph_statistics(graph_id),
        }
        return {
            "tool_outputs": tool_outputs,
            "sections": [],
            "chat_responses": [],
        }

    def _capture_memory_update(self, graph_id: str) -> dict[str, Any]:
        before = self.graph_builder.get_graph_data(graph_id)
        episode_uuid = self.graph_builder.add_text_batches(
            graph_id=graph_id,
            chunks=["Simulation memory update: Alice coordinated with Example Labs again."],
            batch_size=1,
        )
        self.graph_builder._wait_for_episodes(episode_uuid)
        after = self.graph_builder.get_graph_data(graph_id)
        return {
            "delta": {
                "node_count_before": before["node_count"],
                "node_count_after": after["node_count"],
                "edge_count_before": before["edge_count"],
                "edge_count_after": after["edge_count"],
            },
            "episodes": episode_uuid,
        }


def load_corpus_manifest(manifest_path: str | Path) -> list[CorpusItem]:
    """Load and validate corpus items from the manifest JSON file."""

    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    cases = payload["cases"] if isinstance(payload, dict) else payload
    return [CorpusItem.model_validate(item) for item in cases]


def build_artifact_paths(output_root: str | Path, case_id: str) -> dict[str, Path]:
    """Return the stable artifact layout for one baseline case."""

    case_dir = Path(output_root) / case_id
    paths = {"case_dir": case_dir}
    for key, filename in ARTIFACT_FILENAMES.items():
        paths[key] = case_dir / filename
    return paths


def write_baseline_bundle(
    output_root: str | Path,
    snapshot: BaselineSnapshot,
    metadata: dict[str, Any] | None = None,
    raw_api_examples: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Persist a baseline snapshot and companion artifacts using the canonical layout."""

    paths = build_artifact_paths(output_root, snapshot.case_id)
    paths["case_dir"].mkdir(parents=True, exist_ok=True)

    _write_json(paths["graph"], snapshot.graph.model_dump(mode="json"))
    _write_json(paths["search"], [item.model_dump(mode="json") for item in snapshot.search])
    _write_json(
        paths["profile"],
        snapshot.profile.model_dump(mode="json") if snapshot.profile else {},
    )
    _write_json(
        paths["report"],
        snapshot.report.model_dump(mode="json") if snapshot.report else {},
    )
    _write_json(
        paths["memory_update"],
        snapshot.memory_update.model_dump(mode="json") if snapshot.memory_update else {},
    )
    _write_json(paths["metadata"], metadata or snapshot.metadata)
    _write_json(paths["raw_api_examples"], raw_api_examples or snapshot.raw_api_examples)

    return paths


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
