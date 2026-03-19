"""Explicit OpenAI-compatible provider wiring for the parity engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.azure_openai_client import AzureOpenAILLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from openai import AsyncAzureOpenAI, AsyncOpenAI


ProviderName = Literal["openai", "openrouter", "ollama", "lm_studio", "lmstudio", "azure_openai"]


@dataclass(slots=True)
class ProviderSettings:
    provider: ProviderName
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    rerank_base_url: str
    rerank_api_key: str
    rerank_model: str
    api_version: str = "2024-10-21"


@dataclass(slots=True)
class ProviderBundle:
    provider: str
    llm_client: object
    embedding_client: object
    rerank_client: object
    graphiti_llm_client: object
    graphiti_embedder: object
    graphiti_reranker: object
    llm_model: str
    embedding_model: str
    rerank_model: str
    client_type: str
    api_version: str | None = None


def build_provider_bundle(settings: ProviderSettings) -> ProviderBundle:
    provider = "lm_studio" if settings.provider == "lmstudio" else settings.provider
    llm_api_key = settings.llm_api_key or "__local__"
    embedding_api_key = settings.embedding_api_key or "__local__"
    rerank_api_key = settings.rerank_api_key or "__local__"
    llm_model = settings.llm_model or "gpt-4.1-mini"
    embedding_model = settings.embedding_model or "text-embedding-3-small"
    rerank_model = settings.rerank_model or llm_model

    if provider == "azure_openai":
        llm_client = AsyncAzureOpenAI(
            azure_endpoint=settings.llm_base_url,
            api_key=llm_api_key,
            api_version=settings.api_version,
        )
        embedding_client = AsyncAzureOpenAI(
            azure_endpoint=settings.embedding_base_url,
            api_key=embedding_api_key,
            api_version=settings.api_version,
        )
        rerank_client = AsyncAzureOpenAI(
            azure_endpoint=settings.rerank_base_url,
            api_key=rerank_api_key,
            api_version=settings.api_version,
        )
        llm_config = LLMConfig(
            api_key=llm_api_key,
            model=llm_model,
            base_url=settings.llm_base_url,
        )
        embedding_config = OpenAIEmbedderConfig(
            api_key=embedding_api_key,
            base_url=settings.embedding_base_url,
            embedding_model=embedding_model,
        )
        rerank_config = LLMConfig(
            api_key=rerank_api_key,
            model=rerank_model,
            base_url=settings.rerank_base_url,
        )
        return ProviderBundle(
            provider=provider,
            llm_client=llm_client,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            graphiti_llm_client=AzureOpenAILLMClient(azure_client=llm_client, config=llm_config),
            graphiti_embedder=OpenAIEmbedder(config=embedding_config, client=embedding_client),
            graphiti_reranker=OpenAIRerankerClient(config=rerank_config, client=rerank_client),
            llm_model=llm_model,
            embedding_model=embedding_model,
            rerank_model=rerank_model,
            client_type="azure_openai",
            api_version=settings.api_version,
        )

    llm_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=llm_api_key)
    embedding_client = AsyncOpenAI(
        base_url=settings.embedding_base_url,
        api_key=embedding_api_key,
    )
    rerank_client = AsyncOpenAI(base_url=settings.rerank_base_url, api_key=rerank_api_key)
    llm_config = LLMConfig(
        api_key=llm_api_key,
        model=llm_model,
        base_url=settings.llm_base_url,
    )
    embedding_config = OpenAIEmbedderConfig(
        api_key=embedding_api_key,
        base_url=settings.embedding_base_url,
        embedding_model=embedding_model,
    )
    rerank_config = LLMConfig(
        api_key=rerank_api_key,
        model=rerank_model,
        base_url=settings.rerank_base_url,
    )
    return ProviderBundle(
        provider=provider,
        llm_client=llm_client,
        embedding_client=embedding_client,
        rerank_client=rerank_client,
        graphiti_llm_client=OpenAIGenericClient(config=llm_config, client=llm_client),
        graphiti_embedder=OpenAIEmbedder(config=embedding_config, client=embedding_client),
        graphiti_reranker=OpenAIRerankerClient(config=rerank_config, client=rerank_client),
        llm_model=llm_model,
        embedding_model=embedding_model,
        rerank_model=rerank_model,
        client_type="openai_compatible",
    )
