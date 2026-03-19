"""Standalone Flask service for the Graphiti-backed parity engine."""

from __future__ import annotations

import tempfile

from flask import Flask, jsonify, request

from .config import load_engine_settings
from .graphiti_client import GraphitiEngine
from .logging_config import configure_logging
from .provider_factory import ProviderSettings, build_provider_bundle


def create_engine_app(testing: bool = False) -> tuple[Flask, dict[str, object]]:
    settings = load_engine_settings()
    config = settings.to_runtime_dict()
    logger = configure_logging(
        logger_name="mirofish.parity",
        level=str(config["GRAPHITI_LOG_LEVEL"]),
        stdout_logging=bool(config["GRAPHITI_STDOUT_LOGGING"]),
    )

    app = Flask("mirofish_parity_engine")
    app.config["TESTING"] = testing
    app.config.update(config)
    app.config["PROVIDER_BUNDLE"] = build_provider_bundle(
        ProviderSettings(
            provider=str(config["GRAPHITI_LLM_PROVIDER"]),
            llm_base_url=str(config["GRAPHITI_LLM_BASE_URL"]),
            llm_api_key=str(config["GRAPHITI_LLM_API_KEY"]),
            llm_model=str(config["GRAPHITI_LLM_MODEL"]),
            embedding_base_url=str(config["GRAPHITI_EMBEDDING_BASE_URL"]),
            embedding_api_key=str(config["GRAPHITI_EMBEDDING_API_KEY"]),
            embedding_model=str(config["GRAPHITI_EMBEDDING_MODEL"]),
            rerank_base_url=str(config["GRAPHITI_RERANK_BASE_URL"]),
            rerank_api_key=str(config["GRAPHITI_RERANK_API_KEY"]),
            rerank_model=str(config["GRAPHITI_RERANK_MODEL"]),
            api_version=str(config["GRAPHITI_API_VERSION"]),
        )
    )
    engine_db_path = str(config["GRAPHITI_DB_PATH"])
    if testing:
        engine_db_path = f"{tempfile.mkdtemp(prefix='mirofish-parity-')}/graphiti.kuzu"
        app.config["GRAPHITI_DB_PATH"] = engine_db_path
    app.config["GRAPHITI_ENGINE"] = GraphitiEngine(db_path=engine_db_path)
    app.config["ENGINE_SHARED_TOKEN"] = str(config.get("ENGINE_SHARED_TOKEN") or "")

    @app.before_request
    def log_request() -> None:
        if request.path.startswith("/v1/") and not testing:
            required_token = app.config.get("ENGINE_SHARED_TOKEN", "")
            if not required_token:
                return jsonify({"error": "Engine token is required"}), 500
            if request.headers.get("X-MiroFish-Engine-Token") != required_token:
                return jsonify({"error": "Forbidden"}), 403
        logger.info(
            "engine request",
            extra={
                "mode": "local_primary" if not testing else "test",
                "route": request.path,
                "provider": config["GRAPHITI_LLM_PROVIDER"],
                "decision": "continue",
            },
        )

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "mirofish-parity-engine",
                "graphiti_backend": config["GRAPHITI_BACKEND"],
            }
        )

    @app.get("/ready")
    def ready():
        engine_ready = app.config["GRAPHITI_ENGINE"].is_ready()
        status_code = 200 if testing or (config["GRAPHITI_BACKEND"] == "kuzu" and engine_ready) else 503
        status = "ready" if status_code == 200 else "unready"
        return (
            jsonify(
                {
                    "status": status,
                    "service": "mirofish-parity-engine",
                    "graphiti_backend": config["GRAPHITI_BACKEND"],
                    "provider_ready": engine_ready,
                }
            ),
            status_code,
        )

    @app.post("/v1/graphs")
    def create_graph():
        payload = request.get_json(silent=True) or {}
        graph_id = app.config["GRAPHITI_ENGINE"].create_graph(
            graph_id=payload.get("graph_id"),
            name=payload.get("name", "MiroFish Graph"),
            description=payload.get("description", ""),
        )
        return jsonify(
            {
                "graph_id": graph_id,
                "name": payload.get("name", "MiroFish Graph"),
                "description": payload.get("description", ""),
                "type": "Graph",
            }
        )

    @app.post("/v1/graphs/<graph_id>/ontology")
    def set_ontology(graph_id: str):
        payload = request.get_json(silent=True) or {}
        app.config["GRAPHITI_ENGINE"].set_ontology(graph_id, payload)
        return jsonify({"graph_id": graph_id, "status": "ok"})

    @app.post("/v1/graphs/<graph_id>/episodes/batch")
    def add_batch(graph_id: str):
        payload = request.get_json(silent=True) or {}
        episodes = payload.get("episodes", [])
        episode_uuids: list[str] = []
        for episode in episodes:
            episode_uuids.append(
                app.config["GRAPHITI_ENGINE"].enqueue_episode(
                    graph_id=graph_id,
                    episode_body=episode.get("data", ""),
                )
            )
        return jsonify(
            {
                "count": len(episodes),
                "episode_uuid": episode_uuids[-1] if episode_uuids else None,
                "episode_uuids": episode_uuids,
                "processed_initial": False,
                "type": "Episode",
            }
        )

    @app.post("/v1/graphs/<graph_id>/episodes")
    def add_episode(graph_id: str):
        payload = request.get_json(silent=True) or {}
        episode_uuid = app.config["GRAPHITI_ENGINE"].add_episode(
            graph_id=graph_id,
            episode_body=payload.get("data", ""),
        )
        return jsonify(
            {
                "episode_uuid": episode_uuid,
                "processed": True,
                "type": "Episode",
            }
        )

    @app.get("/v1/graphs/<graph_id>/nodes")
    def list_nodes(graph_id: str):
        limit = int(request.args.get("limit", "100"))
        uuid_cursor = request.args.get("uuid_cursor")
        return jsonify(app.config["GRAPHITI_ENGINE"].list_nodes(graph_id, limit=limit, uuid_cursor=uuid_cursor))

    @app.get("/v1/graphs/<graph_id>/edges")
    def list_edges(graph_id: str):
        limit = int(request.args.get("limit", "100"))
        uuid_cursor = request.args.get("uuid_cursor")
        return jsonify(app.config["GRAPHITI_ENGINE"].list_edges(graph_id, limit=limit, uuid_cursor=uuid_cursor))

    @app.get("/v1/nodes/<node_uuid>")
    def get_node(node_uuid: str):
        return jsonify(app.config["GRAPHITI_ENGINE"].get_node(node_uuid))

    @app.get("/v1/nodes/<node_uuid>/edges")
    def get_node_edges(node_uuid: str):
        return jsonify(app.config["GRAPHITI_ENGINE"].get_node_edges(node_uuid))

    @app.get("/v1/episodes/<episode_uuid>")
    def get_episode(episode_uuid: str):
        episode = app.config["GRAPHITI_ENGINE"].get_episode(episode_uuid)
        return jsonify(
            {
                "episode_uuid": episode["episode_id"],
                "processed": episode["status"] == "processed",
                "status": episode["status"],
                "error": episode.get("error"),
                "type": "Episode",
            }
        )

    @app.get("/v1/graphs/<graph_id>/search")
    def search(graph_id: str):
        result = app.config["GRAPHITI_ENGINE"].search(
            graph_id=graph_id,
            query=request.args.get("query", ""),
            limit=int(request.args.get("limit", "10")),
            scope=request.args.get("scope", "edges"),
        )
        return jsonify(result)

    @app.delete("/v1/graphs/<graph_id>")
    def delete_graph(graph_id: str):
        app.config["GRAPHITI_ENGINE"].delete_graph(graph_id)
        return jsonify({"graph_id": graph_id, "deleted": True})

    logger.info(
        "engine boot configured",
        extra={
            "mode": "bootstrap",
            "provider": config["GRAPHITI_LLM_PROVIDER"],
            "decision": "continue",
        },
    )
    return app, config
