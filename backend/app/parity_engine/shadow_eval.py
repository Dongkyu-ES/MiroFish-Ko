"""Optional shadow-evaluation helpers for runtime mode handling."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


def is_shadow_eval_mode(graph_backend: str) -> bool:
    return graph_backend == "shadow_eval"


def should_collect_shadow_scorecards(graph_backend: str, enabled: bool) -> bool:
    return is_shadow_eval_mode(graph_backend) or enabled


class ShadowEvalCollector:
    def __init__(
        self,
        graph_backend: str,
        enabled: bool,
        base_url: str | None = None,
        artifact_dir: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.enabled = should_collect_shadow_scorecards(graph_backend, enabled)
        self.base_url = (base_url or os.environ.get("ENGINE_BASE_URL", "http://127.0.0.1:8123")).rstrip("/")
        self.timeout_seconds = timeout_seconds or int(os.environ.get("ENGINE_TIMEOUT_SECONDS", "30"))
        self.artifact_dir = Path(artifact_dir or os.environ.get("GRAPHITI_PARITY_ARTIFACT_DIR", "./artifacts/parity"))
        self.shared_token = os.environ.get("ENGINE_SHARED_TOKEN") or os.environ.get("SECRET_KEY", "")

    def ensure_graph(self, graph_id: str, name: str, description: str) -> None:
        if not self.enabled:
            return
        self._request("POST", "/v1/graphs", json={"graph_id": graph_id, "name": name, "description": description})

    def set_ontology(self, graph_id: str, ontology: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self._request("POST", f"/v1/graphs/{graph_id}/ontology", json=ontology)

    def add_text_batch(self, graph_id: str, chunks: list[str]) -> None:
        if not self.enabled:
            return
        self._request(
            "POST",
            f"/v1/graphs/{graph_id}/episodes/batch",
            json={"episodes": [{"type": "text", "data": chunk} for chunk in chunks]},
        )

    def capture_search(
        self,
        graph_id: str,
        query: str,
        limit: int,
        scope: str,
        source_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        local_payload = self._request(
            "GET",
            f"/v1/graphs/{graph_id}/search",
            params={"query": query, "limit": limit, "scope": scope},
        )
        self._write_artifact(
            graph_id,
            "search",
            {
                "query": query,
                "scope": scope,
                "source_of_truth": source_payload,
                "shadow_local": local_payload,
            },
        )
        return local_payload

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.shared_token:
            headers["X-MiroFish-Engine-Token"] = self.shared_token
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def _write_artifact(self, graph_id: str, artifact_name: str, payload: dict[str, Any]) -> Path:
        target_dir = self.artifact_dir / "shadow_eval" / graph_id
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{artifact_name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path
