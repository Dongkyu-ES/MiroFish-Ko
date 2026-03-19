"""Live Zep baseline measurement with strict API-call budgeting."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import httpx

from .baseline_capture import ZepBaselineCaptureRunner, write_baseline_bundle
from .contracts import BaselineSnapshot, CorpusItem


class ApiCallBudgetExceeded(RuntimeError):
    pass


@dataclass(slots=True)
class ApiCallRecord:
    index: int
    method: str
    url: str


@dataclass(slots=True)
class ApiCallBudget:
    max_calls: int
    calls: list[ApiCallRecord]

    @property
    def used(self) -> int:
        return len(self.calls)

    @property
    def remaining(self) -> int:
        return self.max_calls - self.used

    def register(self, method: str, url: str) -> None:
        if self.used >= self.max_calls:
            raise ApiCallBudgetExceeded(
                f"Zep API call budget exceeded: {self.used}/{self.max_calls}"
            )
        self.calls.append(ApiCallRecord(index=self.used + 1, method=method.upper(), url=url))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "used": self.used,
            "remaining": self.remaining,
            "calls": [
                {
                    "index": record.index,
                    "method": record.method,
                    "url": record.url,
                }
                for record in self.calls
            ],
        }


@contextmanager
def enforce_httpx_budget(max_calls: int):
    budget = ApiCallBudget(max_calls=max_calls, calls=[])
    original_client_request = httpx.Client.request
    original_async_request = httpx.AsyncClient.request

    def wrapped_client_request(self, method, url, *args, **kwargs):
        budget.register(str(method), str(url))
        return original_client_request(self, method, url, *args, **kwargs)

    async def wrapped_async_request(self, method, url, *args, **kwargs):
        budget.register(str(method), str(url))
        return await original_async_request(self, method, url, *args, **kwargs)

    httpx.Client.request = wrapped_client_request
    httpx.AsyncClient.request = wrapped_async_request
    try:
        yield budget
    finally:
        httpx.Client.request = original_client_request
        httpx.AsyncClient.request = original_async_request


class BudgetFriendlyZepProbe:
    """Live baseline probe that avoids non-essential external calls."""

    def __init__(self, fixtures_root: str | Path):
        os.environ["GRAPH_BACKEND"] = "zep"

        from backend.app.services.graph_builder import GraphBuilderService
        from backend.app.services.oasis_profile_generator import OasisProfileGenerator
        from backend.app.services.zep_entity_reader import ZepEntityReader
        from backend.app.services.zep_tools import ZepToolsService

        self.fixtures_root = Path(fixtures_root)
        self.graph_builder = GraphBuilderService()
        self.entity_reader = ZepEntityReader()
        self.zep_tools = ZepToolsService()
        self.profile_generator = OasisProfileGenerator()

    def capture_case(
        self,
        case: CorpusItem,
    ) -> tuple[BaselineSnapshot, dict[str, Any] | None, dict[str, Any] | None]:
        document_texts = self._load_documents(case.documents)
        ontology = case.ontology or self._build_default_ontology(case)
        combined_text = "\n\n".join(document_texts)

        graph_id = self.graph_builder.create_graph(f"Live Baseline {case.id}")
        self.graph_builder.set_ontology(graph_id, ontology)
        episode_uuids = self.graph_builder.add_text_batches(graph_id=graph_id, chunks=[combined_text], batch_size=1)
        self.graph_builder._wait_for_episodes(episode_uuids, timeout=120)

        graph_payload = self.graph_builder.get_graph_data(graph_id)
        search_payloads = [self._capture_search(graph_id, query) for query in case.queries]
        profile_payload = self._capture_profile(graph_id, ontology) if "profile" in case.expected_outputs else {}
        report_payload = self._capture_report(graph_id, case.queries) if "report" in case.expected_outputs else {}
        memory_update_payload = self._capture_memory_update(graph_id) if "memory_update" in case.expected_outputs else {}

        snapshot = BaselineSnapshot.model_validate(
            {
                "case_id": case.id,
                "captured_at": _utc_now(),
                "graph": {
                    "nodes": graph_payload.get("nodes", []),
                    "edges": graph_payload.get("edges", []),
                },
                "search": search_payloads,
                "profile": profile_payload or {"context": "", "profiles": [], "metadata": {}},
                "report": report_payload or {"tool_outputs": {}, "sections": [], "chat_responses": []},
                "memory_update": memory_update_payload or {"delta": {}, "episodes": []},
                "metadata": {
                    "graph_id": graph_id,
                    "language": case.language,
                    "documents": case.documents,
                    "expected_outputs": case.expected_outputs,
                },
            }
        )
        metadata = {
            "provider": "zep",
            "graph_id": graph_id,
            "captured_at": snapshot.captured_at,
            "case_id": case.id,
        }
        raw_api_examples = {
            "graph.create": {
                "graph_id": graph_id,
                "name": f"Live Baseline {case.id}",
                "description": "Live Zep baseline capture graph",
                "type": "Graph",
            },
            "graph.add_batch": {
                "count": len(episode_uuids),
                "episode_uuid": episode_uuids[-1] if episode_uuids else None,
                "processed_initial": False,
                "type": "Episode",
            },
            "graph.search.edges": search_payloads[0] if search_payloads else {},
        }
        return snapshot, metadata, raw_api_examples

    def _load_documents(self, documents: list[str]) -> list[str]:
        return [(self.fixtures_root / document).read_text(encoding="utf-8") for document in documents]

    def _build_default_ontology(self, case: CorpusItem) -> dict[str, Any]:
        return {
            "entity_types": [
                {"name": "Person", "description": "An individual human actor.", "attributes": []},
                {"name": "Company", "description": "A commercial company or startup.", "attributes": []},
                {"name": "Organization", "description": "An organization or institution.", "attributes": []},
                {"name": "Community", "description": "A community or collective group.", "attributes": []},
                {"name": "MediaOutlet", "description": "A media or communications outlet.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "WORKS_FOR",
                    "description": "Employment or formal work relationship.",
                    "source_targets": [
                        {"source": "Person", "target": "Company"},
                        {"source": "Person", "target": "Organization"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "LEADS",
                    "description": "Leadership relationship.",
                    "source_targets": [
                        {"source": "Person", "target": "Company"},
                        {"source": "Person", "target": "Organization"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "PARTNERS_WITH",
                    "description": "Partnership or alliance relationship.",
                    "source_targets": [
                        {"source": "Company", "target": "Company"},
                        {"source": "Organization", "target": "Organization"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "COLLABORATES_WITH",
                    "description": "Collaboration relationship.",
                    "source_targets": [
                        {"source": "Person", "target": "Person"},
                        {"source": "Person", "target": "Organization"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "FOLLOWS",
                    "description": "Social following relationship.",
                    "source_targets": [
                        {"source": "Person", "target": "Person"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "LIKES",
                    "description": "Positive reaction relationship.",
                    "source_targets": [
                        {"source": "Person", "target": "Person"},
                        {"source": "Person", "target": "Community"},
                    ],
                    "attributes": [],
                },
            ],
        }

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
        entities = filtered.entities[:1]
        profiles = self.profile_generator.generate_profiles_from_entities(
            entities=entities,
            use_llm=False,
            graph_id=graph_id,
            parallel_count=1,
        )
        contexts = [self.profile_generator._search_zep_for_entity(entity).get("context", "") for entity in entities]
        return {
            "context": "\n\n".join(contexts),
            "profiles": [profile.to_dict() for profile in profiles],
            "metadata": {
                "entity_count": filtered.filtered_count,
                "entity_types": list(filtered.entity_types),
            },
        }

    def _capture_report(self, graph_id: str, queries: list[str]) -> dict[str, Any]:
        tool_outputs = {
            "search": [self.zep_tools.search_graph(graph_id=graph_id, query=query).to_dict() for query in queries[:1]],
            "statistics": self.zep_tools.get_graph_statistics(graph_id),
        }
        return {
            "tool_outputs": tool_outputs,
            "sections": [],
            "chat_responses": [],
        }

    def _capture_memory_update(self, graph_id: str) -> dict[str, Any]:
        before = self.graph_builder.get_graph_data(graph_id)
        episode_uuids = self.graph_builder.add_text_batches(
            graph_id=graph_id,
            chunks=["Simulation memory update: Alice coordinated with Example Labs again."],
            batch_size=1,
        )
        self.graph_builder._wait_for_episodes(episode_uuids, timeout=120)
        after = self.graph_builder.get_graph_data(graph_id)
        return {
            "delta": {
                "node_count_before": before["node_count"],
                "node_count_after": after["node_count"],
                "edge_count_before": before["edge_count"],
                "edge_count_after": after["edge_count"],
            },
            "episodes": episode_uuids,
        }


def run_live_zep_baseline_capture(
    manifest_path: str | Path,
    fixtures_root: str | Path,
    output_root: str | Path,
    max_calls: int = 100,
) -> dict[str, Any]:
    probe = BudgetFriendlyZepProbe(fixtures_root=fixtures_root)
    runner = ZepBaselineCaptureRunner(probe)
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)

    with enforce_httpx_budget(max_calls=max_calls) as budget:
        case_paths = runner.capture_manifest(manifest_path, output_path)

    summary = {
        "captured_at": _utc_now(),
        "manifest_path": str(manifest_path),
        "output_root": str(output_path),
        "cases": {case_id: {name: str(path) for name, path in paths.items()} for case_id, paths in case_paths.items()},
        "budget": budget.to_dict(),
    }
    (output_path / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def recover_live_zep_run_summary(output_root: str | Path, max_calls: int) -> dict[str, Any]:
    output_path = Path(output_root)
    cases: dict[str, dict[str, str]] = {}
    for case_dir in sorted(path for path in output_path.iterdir() if path.is_dir()):
        cases[case_dir.name] = {
            artifact.name: str(artifact)
            for artifact in sorted(case_dir.iterdir())
            if artifact.is_file()
        }
    summary = {
        "captured_at": _utc_now(),
        "output_root": str(output_path),
        "cases": cases,
        "budget": {
            "max_calls": max_calls,
            "used": "<=100 (guard enforced during live run)",
            "remaining": "unknown",
            "calls": [],
        },
    }
    (output_path / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
