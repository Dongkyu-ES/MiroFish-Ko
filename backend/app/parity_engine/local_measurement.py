"""Local Graphiti candidate capture using the standalone engine."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from werkzeug.serving import make_server

from backend.app.parity_engine.baseline_capture import ZepBaselineCaptureRunner
from backend.app.parity_engine.contracts import BaselineSnapshot, CorpusItem
from backend.app.parity_engine.server import create_engine_app


@contextmanager
def running_local_engine(
    db_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8123,
    mode: str = "inline",
):
    os.environ["ENGINE_HOST"] = host
    os.environ["ENGINE_PORT"] = str(port)
    os.environ["ENGINE_BASE_URL"] = f"http://{host}:{port}"
    os.environ["GRAPHITI_DB_PATH"] = str(db_path)
    os.environ["GRAPHITI_EPISODE_INLINE"] = "true" if mode == "inline" else "false"
    app, _ = create_engine_app(testing=(mode == "inline"))
    server = make_server(host, port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield os.environ["ENGINE_BASE_URL"]
    finally:
        server.shutdown()
        thread.join(timeout=2)


class LocalEngineCandidateProbe:
    def __init__(self, fixtures_root: str | Path, mode: str = "inline"):
        os.environ["GRAPH_BACKEND"] = "local_primary"
        os.environ["GRAPHITI_ALLOW_LOCAL_EVAL"] = "true"
        self.mode = mode
        if self.mode == "provider":
            validate_provider_capture_env()

        from backend.app.services.graph_builder import GraphBuilderService
        from backend.app.services.oasis_profile_generator import OasisProfileGenerator
        from backend.app.services.zep_entity_reader import ZepEntityReader
        from backend.app.services.zep_tools import ZepToolsService

        self.fixtures_root = Path(fixtures_root)
        self.graph_builder = GraphBuilderService()
        self.entity_reader = ZepEntityReader()
        self.zep_tools = ZepToolsService()
        self.profile_generator = OasisProfileGenerator(api_key=os.environ.get("LLM_API_KEY", "dummy-key"))

    def capture_case(
        self,
        case: CorpusItem,
    ) -> tuple[BaselineSnapshot, dict[str, Any] | None, dict[str, Any] | None]:
        document_texts = [(self.fixtures_root / document).read_text(encoding="utf-8") for document in case.documents]
        ontology = case.ontology or self._build_default_ontology()
        combined_text = "\n\n".join(document_texts)

        graph_id = self.graph_builder.create_graph(f"Local Candidate {case.id}")
        self.graph_builder.set_ontology(graph_id, ontology)
        episode_uuids = self.graph_builder.add_text_batches(graph_id=graph_id, chunks=[combined_text], batch_size=1)
        self.graph_builder._wait_for_episodes(episode_uuids, timeout=120)

        graph_payload = self.graph_builder.get_graph_data(graph_id)
        search_payloads = [self._capture_search(graph_id, query) for query in case.queries]
        profile_payload = self._capture_profile(graph_id, ontology) if "profile" in case.expected_outputs else {}
        report_payload = self._capture_report(graph_id, case.queries) if "report" in case.expected_outputs else {}
        memory_payload = self._capture_memory_update(graph_id) if "memory_update" in case.expected_outputs else {}

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
                "memory_update": memory_payload or {"delta": {}, "episodes": []},
                "metadata": {
                    "graph_id": graph_id,
                    "provider": "local_engine",
                    "mode": self.mode,
                    "authoritative": self.mode == "provider",
                },
            }
        )
        raw_api_examples = {
            "graph.create": {"graph_id": graph_id, "name": f"Local Candidate {case.id}", "description": "Local candidate graph", "type": "Graph"},
            "graph.add_batch": {"count": len(episode_uuids), "episode_uuid": episode_uuids[-1] if episode_uuids else None, "processed_initial": False, "type": "Episode"},
        }
        return snapshot, {"provider": "local_engine", "graph_id": graph_id, "mode": self.mode, "authoritative": self.mode == "provider"}, raw_api_examples

    def _build_default_ontology(self) -> dict[str, Any]:
        return {
            "entity_types": [
                {"name": "Person", "description": "An individual human actor.", "attributes": []},
                {"name": "Company", "description": "A commercial company or startup.", "attributes": []},
                {"name": "Organization", "description": "An organization or institution.", "attributes": []},
                {"name": "Community", "description": "A community or collective group.", "attributes": []},
                {"name": "MediaOutlet", "description": "A media outlet.", "attributes": []},
            ],
            "edge_types": [
                {"name": "WORKS_FOR", "description": "Employment or work relationship.", "source_targets": [{"source": "Person", "target": "Company"}, {"source": "Person", "target": "Organization"}], "attributes": []},
                {"name": "LEADS", "description": "Leadership relationship.", "source_targets": [{"source": "Person", "target": "Company"}, {"source": "Person", "target": "Organization"}], "attributes": []},
                {"name": "COLLABORATES_WITH", "description": "Collaboration relationship.", "source_targets": [{"source": "Person", "target": "Person"}], "attributes": []},
                {"name": "FOLLOWS", "description": "Social following relationship.", "source_targets": [{"source": "Person", "target": "Person"}], "attributes": []},
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
        filtered = self.entity_reader.filter_defined_entities(graph_id=graph_id, defined_entity_types=defined_types, enrich_with_edges=True)
        entities = filtered.entities[:1]
        profiles = self.profile_generator.generate_profiles_from_entities(entities=entities, use_llm=False, graph_id=graph_id, parallel_count=1)
        return {
            "context": "\n\n".join(self.profile_generator._search_zep_for_entity(entity).get("context", "") for entity in entities),
            "profiles": [profile.to_dict() for profile in profiles],
            "metadata": {"entity_count": filtered.filtered_count, "entity_types": list(filtered.entity_types)},
        }

    def _capture_report(self, graph_id: str, queries: list[str]) -> dict[str, Any]:
        return {
            "tool_outputs": {
                "search": [self.zep_tools.search_graph(graph_id=graph_id, query=query).to_dict() for query in queries[:1]],
                "statistics": self.zep_tools.get_graph_statistics(graph_id),
            },
            "sections": [],
            "chat_responses": [],
        }

    def _capture_memory_update(self, graph_id: str) -> dict[str, Any]:
        before = self.graph_builder.get_graph_data(graph_id)
        episodes = self.graph_builder.add_text_batches(
            graph_id=graph_id,
            chunks=["Simulation memory update: Alice coordinated with Example Labs again."],
            batch_size=1,
        )
        self.graph_builder._wait_for_episodes(episodes, timeout=120)
        after = self.graph_builder.get_graph_data(graph_id)
        return {
            "delta": {
                "node_count_before": before["node_count"],
                "node_count_after": after["node_count"],
                "edge_count_before": before["edge_count"],
                "edge_count_after": after["edge_count"],
            },
            "episodes": episodes,
        }


def run_local_candidate_capture(
    manifest_path: str | Path,
    fixtures_root: str | Path,
    output_root: str | Path,
    db_path: str | Path,
    mode: str = "inline",
) -> dict[str, Any]:
    runner = ZepBaselineCaptureRunner(LocalEngineCandidateProbe(fixtures_root=fixtures_root, mode=mode))
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)
    case_paths = runner.capture_manifest(manifest_path, output_path)
    summary = {
        "captured_at": _utc_now(),
        "manifest_path": str(manifest_path),
        "output_root": str(output_path),
        "graphiti_db_path": str(db_path),
        "mode": mode,
        "authoritative": mode == "provider",
        "cases": {case_id: {name: str(path) for name, path in paths.items()} for case_id, paths in case_paths.items()},
    }
    (output_path / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def validate_provider_capture_env() -> None:
    required = {
        "GRAPHITI_LLM_API_KEY": os.environ.get("GRAPHITI_LLM_API_KEY"),
        "GRAPHITI_LLM_MODEL": os.environ.get("GRAPHITI_LLM_MODEL"),
        "GRAPHITI_EMBEDDING_MODEL": os.environ.get("GRAPHITI_EMBEDDING_MODEL"),
        "GRAPHITI_RERANK_MODEL": os.environ.get("GRAPHITI_RERANK_MODEL"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "provider capture requires configured Graphiti provider env vars: "
            + ", ".join(sorted(missing))
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
