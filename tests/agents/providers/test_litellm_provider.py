from types import SimpleNamespace

from miniclaw.agents.providers.litellm_provider import LiteLLMClient


def test_chat_success(monkeypatch):
    client = LiteLLMClient()

    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=" hello world "))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    def fake_completion(**kwargs):
        assert kwargs["stream"] is False
        return fake_response

    def fake_completion_cost(response):
        assert response is fake_response
        return 0.0012

    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion", fake_completion
    )
    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion_cost", fake_completion_cost
    )

    result = client.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
    )

    assert result.error is None
    assert result.content == "hello world"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15
    assert result.cost_usd == 0.0012


def test_chat_exception(monkeypatch):
    client = LiteLLMClient()

    def fake_completion(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion", fake_completion
    )

    result = client.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
    )

    assert result.content == ""
    assert "network down" in result.error


def test_stream_chat_success_with_finish_usage(monkeypatch):
    client = LiteLLMClient()

    chunk1 = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel"), finish_reason=None)]
    )
    chunk2 = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"), finish_reason=None)]
    )
    chunk3 = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=""), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3, total_tokens=10),
    )

    def fake_completion(**kwargs):
        assert kwargs["stream"] is True
        return iter([chunk1, chunk2, chunk3])

    def fake_completion_cost(chunk):
        assert chunk is chunk3
        return 0.0008

    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion", fake_completion
    )
    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion_cost", fake_completion_cost
    )

    chunks = list(
        client.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o-mini",
        )
    )

    assert len(chunks) == 3
    assert chunks[0].delta == "Hel" and chunks[0].finish is False
    assert chunks[1].delta == "lo" and chunks[1].finish is False

    assert chunks[2].finish is True
    assert chunks[2].prompt_tokens == 7
    assert chunks[2].completion_tokens == 3
    assert chunks[2].total_tokens == 10
    assert chunks[2].cost_usd == 0.0008
    assert chunks[2].error is None


def test_stream_chat_exception(monkeypatch):
    client = LiteLLMClient()

    def fake_completion(**kwargs):
        raise ValueError("bad request")

    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion", fake_completion
    )

    chunks = list(
        client.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o-mini",
        )
    )

    assert len(chunks) == 1
    assert chunks[0].finish is True
    assert chunks[0].delta == ""
    assert "bad request" in chunks[0].error


def test_stream_chat_finish_without_usage(monkeypatch):
    client = LiteLLMClient()

    chunk_finish_no_usage = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=""), finish_reason="stop")]
    )

    def fake_completion(**kwargs):
        return iter([chunk_finish_no_usage])

    monkeypatch.setattr(
        "miniclaw.agents.providers.litellm_provider.completion", fake_completion
    )

    chunks = list(
        client.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o-mini",
        )
    )

    # Locks current behavior: finish without usage currently yields finish=False.
    assert len(chunks) == 1
    assert chunks[0].finish is False
