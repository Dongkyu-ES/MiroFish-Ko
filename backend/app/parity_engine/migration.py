"""Project-level graph migration helpers with atomic rollback semantics."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Protocol

import httpx

from backend.app.models.project import Project, ProjectManager
from backend.app.services.graph_builder import GraphBuilderService
from backend.app.services.text_processor import TextProcessor
from backend.app.services.zep_tools import ZepToolsService


class ProjectGraphImporter(Protocol):
    def import_project_graph(self, project_id: str, graph_id: str):
        ...

    def rollback_project_graph(self, project_id: str, graph_id: str):
        ...


class ProjectGraphVerifier(Protocol):
    def verify_project_graph(self, project_id: str, graph_id: str) -> dict:
        ...


@dataclass(slots=True)
class ProjectMigrationService:
    importer: ProjectGraphImporter
    verifier: ProjectGraphVerifier

    def migrate_project(self, project_id: str) -> dict:
        project = ProjectManager.get_project(project_id)
        if project is None:
            raise ValueError(f"project not found: {project_id}")
        if not project.graph_id:
            raise ValueError(f"project has no graph_id: {project_id}")

        original = Project.from_dict(project.to_dict())
        graph_id = project.graph_id

        try:
            self.importer.import_project_graph(project.project_id, graph_id)
            verification = self.verifier.verify_project_graph(project.project_id, graph_id)
            if not verification.get("passed"):
                raise RuntimeError("migration verification failed")
            ProjectManager.save_project(project)
            return {
                "project_id": project.project_id,
                "graph_id": graph_id,
                "migration_status": "completed",
                "verification": verification,
            }
        except Exception:
            ProjectManager.save_project(original)
            self.importer.rollback_project_graph(project.project_id, graph_id)
            raise

    def get_migration_status(self, project_id: str) -> dict:
        project = ProjectManager.get_project(project_id)
        if project is None:
            raise ValueError(f"project not found: {project_id}")
        return {
            "project_id": project.project_id,
            "graph_id": project.graph_id,
            "migration_status": project.migration_status,
            "migration_error": project.migration_error,
            "local_primary_eligible": project.local_primary_eligible,
        }


class RuntimeProjectGraphImporter:
    def __init__(self):
        self.base_url = os.environ.get("ENGINE_BASE_URL", "http://127.0.0.1:8123").rstrip("/")
        self.timeout = int(os.environ.get("ENGINE_TIMEOUT_SECONDS", "30"))
        self.shared_token = os.environ.get("ENGINE_SHARED_TOKEN") or os.environ.get("SECRET_KEY", "")

    def import_project_graph(self, project_id: str, graph_id: str):
        project = ProjectManager.get_project(project_id)
        if project is None or not project.ontology:
            raise ValueError(f"project is missing ontology: {project_id}")
        extracted_text = ProjectManager.get_extracted_text(project_id)
        if not extracted_text:
            raise ValueError(f"project is missing extracted text: {project_id}")

        self._request("POST", "/v1/graphs", json={"graph_id": graph_id, "name": project.name, "description": "Migrated local-primary graph"})
        self._request("POST", f"/v1/graphs/{graph_id}/ontology", json=project.ontology)
        chunks = TextProcessor.split_text(extracted_text, project.chunk_size, project.chunk_overlap)
        self._request(
            "POST",
            f"/v1/graphs/{graph_id}/episodes/batch",
            json={"episodes": [{"type": "text", "data": chunk} for chunk in chunks]},
        )
        return {"project_id": project_id, "graph_id": graph_id}

    def rollback_project_graph(self, project_id: str, graph_id: str):
        self._request("DELETE", f"/v1/graphs/{graph_id}")

    def _request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.shared_token:
            headers["X-MiroFish-Engine-Token"] = self.shared_token
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()


class RuntimeProjectGraphVerifier:
    def verify_project_graph(self, project_id: str, graph_id: str) -> dict:
        project = ProjectManager.get_project(project_id)
        if project is None or not project.graph_id:
            raise ValueError(f"project not found: {project_id}")

        builder = GraphBuilderService(api_key=os.environ.get("ZEP_API_KEY"))
        zep_graph = builder.get_graph_data(graph_id)

        importer = RuntimeProjectGraphImporter()
        local_nodes = importer._request("GET", f"/v1/graphs/{graph_id}/nodes", params={"limit": 1000})
        local_edges = importer._request("GET", f"/v1/graphs/{graph_id}/edges", params={"limit": 1000})

        tools = ZepToolsService(api_key=os.environ.get("ZEP_API_KEY"))
        search = tools.search_graph(graph_id, project.simulation_requirement or project.name, limit=5, scope="edges")
        local_search = importer._request(
            "GET",
            f"/v1/graphs/{graph_id}/search",
            params={"query": project.simulation_requirement or project.name, "limit": 5, "scope": "edges"},
        )

        passed = bool(local_nodes) and bool(local_edges) and bool(local_search.get("edges")) and zep_graph["graph_id"] == graph_id
        return {
            "passed": passed,
            "graph_id": graph_id,
            "zep_node_count": zep_graph["node_count"],
            "local_node_count": len(local_nodes),
            "zep_edge_count": zep_graph["edge_count"],
            "local_edge_count": len(local_edges),
            "search_hits": len(search.edges),
            "local_search_hits": len(local_search.get("edges", [])),
        }
