from backend.app.parity_engine.provider_factory import ProviderSettings, build_provider_bundle


def test_openai_compatible_provider_uses_explicit_base_urls():
    bundle = build_provider_bundle(
        ProviderSettings(
            provider="ollama",
            llm_base_url="http://127.0.0.1:11434/v1",
            llm_api_key="ollama",
            llm_model="llama3.1",
            embedding_base_url="http://127.0.0.1:11434/v1",
            embedding_api_key="ollama",
            embedding_model="nomic-embed-text",
            rerank_base_url="http://127.0.0.1:11434/v1",
            rerank_api_key="ollama",
            rerank_model="bge-reranker-v2-m3",
        )
    )

    assert str(bundle.llm_client.base_url) == "http://127.0.0.1:11434/v1/"
    assert str(bundle.embedding_client.base_url) == "http://127.0.0.1:11434/v1/"
    assert str(bundle.rerank_client.base_url) == "http://127.0.0.1:11434/v1/"
    assert bundle.provider == "ollama"
