from backend.app.utils.llm_client import LLMClient


class _FakeOpenAI:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.chat = type(
            "ChatNamespace",
            (),
            {
                "completions": type(
                    "CompletionsNamespace",
                    (),
                    {
                        "create": self._create,
                    },
                )()
            },
        )()

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": '{"ok": true}'})()},
                    )()
                ]
            },
        )()


def test_llm_client_uses_max_completion_tokens_for_gpt5(monkeypatch):
    fake_client = _FakeOpenAI()
    monkeypatch.setattr("backend.app.utils.llm_client.OpenAI", lambda **kwargs: fake_client)

    client = LLMClient(api_key="test-key", model="gpt-5-nano-2025-08-07")
    client.chat_json(messages=[{"role": "user", "content": "hello"}], max_tokens=123)

    payload = fake_client.calls[0]
    assert payload["max_completion_tokens"] == 123
    assert "max_tokens" not in payload
    assert "temperature" not in payload


def test_llm_client_uses_max_tokens_for_legacy_models(monkeypatch):
    fake_client = _FakeOpenAI()
    monkeypatch.setattr("backend.app.utils.llm_client.OpenAI", lambda **kwargs: fake_client)

    client = LLMClient(api_key="test-key", model="gpt-4o-mini")
    client.chat_json(messages=[{"role": "user", "content": "hello"}], max_tokens=456)

    payload = fake_client.calls[0]
    assert payload["max_tokens"] == 456
    assert "max_completion_tokens" not in payload
    assert payload["temperature"] == 0.3
