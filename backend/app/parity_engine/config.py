"""Configuration helpers for the standalone parity engine service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


ENGINE_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
_ENGINE_DOTENV_LOADED = False

@dataclass(slots=True)
class EngineSettings:
    host: str = "127.0.0.1"
    port: int = 8123
    base_url: str = "http://127.0.0.1:8123"
    timeout_seconds: int = 30
    graphiti_backend: str = "kuzu"
    graphiti_db_path: str = "./data/graphiti.kuzu"
    graphiti_stdout_logging: bool = True
    graphiti_log_level: str = "INFO"
    graphiti_default_languages: str = "ko,en"
    graphiti_episode_inline: bool = False

    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""

    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = ""

    rerank_base_url: str = "https://api.openai.com/v1"
    rerank_api_key: str = ""
    rerank_model: str = ""

    api_version: str = "2024-10-21"
    engine_shared_token: str = ""
    graphiti_parity_artifact_dir: str = "./artifacts/parity"

    def to_runtime_dict(self) -> dict[str, object]:
        runtime = asdict(self)
        runtime["HOST"] = runtime.pop("host")
        runtime["PORT"] = runtime.pop("port")
        runtime["ENGINE_BASE_URL"] = runtime.pop("base_url")
        runtime["ENGINE_TIMEOUT_SECONDS"] = runtime.pop("timeout_seconds")
        runtime["GRAPHITI_BACKEND"] = runtime.pop("graphiti_backend")
        runtime["GRAPHITI_DB_PATH"] = runtime.pop("graphiti_db_path")
        runtime["GRAPHITI_STDOUT_LOGGING"] = runtime.pop("graphiti_stdout_logging")
        runtime["GRAPHITI_LOG_LEVEL"] = runtime.pop("graphiti_log_level")
        runtime["GRAPHITI_DEFAULT_LANGUAGES"] = runtime.pop("graphiti_default_languages")
        runtime["GRAPHITI_EPISODE_INLINE"] = runtime.pop("graphiti_episode_inline")
        runtime["GRAPHITI_LLM_PROVIDER"] = runtime.pop("llm_provider")
        runtime["GRAPHITI_LLM_BASE_URL"] = runtime.pop("llm_base_url")
        runtime["GRAPHITI_LLM_API_KEY"] = runtime.pop("llm_api_key")
        runtime["GRAPHITI_LLM_MODEL"] = runtime.pop("llm_model")
        runtime["GRAPHITI_EMBEDDING_BASE_URL"] = runtime.pop("embedding_base_url")
        runtime["GRAPHITI_EMBEDDING_API_KEY"] = runtime.pop("embedding_api_key")
        runtime["GRAPHITI_EMBEDDING_MODEL"] = runtime.pop("embedding_model")
        runtime["GRAPHITI_RERANK_BASE_URL"] = runtime.pop("rerank_base_url")
        runtime["GRAPHITI_RERANK_API_KEY"] = runtime.pop("rerank_api_key")
        runtime["GRAPHITI_RERANK_MODEL"] = runtime.pop("rerank_model")
        runtime["GRAPHITI_API_VERSION"] = runtime.pop("api_version")
        runtime["ENGINE_SHARED_TOKEN"] = runtime.pop("engine_shared_token")
        runtime["GRAPHITI_PARITY_ARTIFACT_DIR"] = runtime.pop("graphiti_parity_artifact_dir")
        return runtime


def load_engine_settings() -> EngineSettings:
    load_engine_dotenv()
    base_url = os.environ.get("ENGINE_BASE_URL", "").strip()
    parsed = urlparse(base_url) if base_url else None

    host = os.environ.get("ENGINE_HOST") or (parsed.hostname if parsed and parsed.hostname else "127.0.0.1")
    port_value = os.environ.get("PORT") or os.environ.get("ENGINE_PORT")
    if not port_value and parsed and parsed.port:
        port_value = str(parsed.port)
    port = int(port_value or 8123)

    resolved_base_url = base_url or f"http://{host}:{port}"

    return EngineSettings(
        host=host,
        port=port,
        base_url=resolved_base_url,
        timeout_seconds=int(os.environ.get("ENGINE_TIMEOUT_SECONDS", "30")),
        graphiti_backend="kuzu",
        graphiti_db_path=os.environ.get("GRAPHITI_DB_PATH", "./data/graphiti.kuzu"),
        graphiti_stdout_logging=os.environ.get("GRAPHITI_STDOUT_LOGGING", "true").lower() == "true",
        graphiti_log_level=os.environ.get("GRAPHITI_LOG_LEVEL", "INFO").upper(),
        graphiti_default_languages=os.environ.get("GRAPHITI_DEFAULT_LANGUAGES", "ko,en"),
        graphiti_episode_inline=os.environ.get("GRAPHITI_EPISODE_INLINE", "false").lower() == "true",
        llm_provider=os.environ.get("GRAPHITI_LLM_PROVIDER", "openai"),
        llm_base_url=os.environ.get("GRAPHITI_LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=os.environ.get("GRAPHITI_LLM_API_KEY", ""),
        llm_model=os.environ.get("GRAPHITI_LLM_MODEL", ""),
        embedding_base_url=os.environ.get("GRAPHITI_EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
        embedding_api_key=os.environ.get("GRAPHITI_EMBEDDING_API_KEY", ""),
        embedding_model=os.environ.get("GRAPHITI_EMBEDDING_MODEL", ""),
        rerank_base_url=os.environ.get("GRAPHITI_RERANK_BASE_URL", "https://api.openai.com/v1"),
        rerank_api_key=os.environ.get("GRAPHITI_RERANK_API_KEY", ""),
        rerank_model=os.environ.get("GRAPHITI_RERANK_MODEL", ""),
        api_version=os.environ.get("GRAPHITI_API_VERSION", "2024-10-21"),
        engine_shared_token=os.environ.get("ENGINE_SHARED_TOKEN") or os.environ.get("SECRET_KEY", ""),
        graphiti_parity_artifact_dir=os.environ.get("GRAPHITI_PARITY_ARTIFACT_DIR", "./artifacts/parity"),
    )


def load_engine_dotenv(force_reload: bool = False) -> None:
    global _ENGINE_DOTENV_LOADED
    if _ENGINE_DOTENV_LOADED and not force_reload:
        return
    if ENGINE_ENV_PATH.exists():
        load_dotenv(ENGINE_ENV_PATH, override=False)
    else:
        load_dotenv(override=False)
    _ENGINE_DOTENV_LOADED = True
