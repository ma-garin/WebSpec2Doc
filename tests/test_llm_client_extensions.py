from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from llm import openai_client as c


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(monkeypatch, payload):
    sent = []

    def fake(request, timeout=None):
        sent.append(request)
        return _Resp(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return sent


def test_embeddings_sorted_by_index(monkeypatch):
    sent = _capture(
        monkeypatch,
        {"data": [{"index": 1, "embedding": [2]}, {"index": 0, "embedding": [1]}]},
    )
    out = c.request_embeddings(["a", "b"], "m", base_url="http://127.0.0.1:11434/v1", api_key="k")
    assert out == [[1.0], [2.0]]
    assert sent[0].full_url == "http://127.0.0.1:11434/v1/embeddings"


def test_embeddings_count_mismatch_and_refused(monkeypatch):
    _capture(monkeypatch, {"data": [{"index": 0, "embedding": [1]}]})
    with pytest.raises(c.LLMResponseError):
        c.request_embeddings(["a", "b"], "m", base_url="http://x/v1", api_key="k")

    def refuse(request, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(c.LLMUnavailableError):
        c.request_embeddings(["a"], "m", base_url="http://x/v1", api_key="k")


def test_system_max_tokens_headers(monkeypatch):
    sent = _capture(monkeypatch, {"choices": [{"message": {"content": "{}"}}]})
    c.request_structured_json(
        "k", "m", "P", "n", {"type": "object"}, base_url="http://x/v1",
        system="S", max_tokens=99, extra_headers={"OpenAI-Organization": "o"},
    )
    body = json.loads(sent[0].data)
    assert body["messages"] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "P"},
    ]
    assert body["max_tokens"] == 99
    assert sent[0].get_header("Openai-organization") == "o"


def test_default_payload_unchanged(monkeypatch):
    sent = _capture(monkeypatch, {"choices": [{"message": {"content": "{}"}}]})
    c.request_structured_json("k", "m", "P", "n", {"type": "object"}, base_url="http://x/v1")
    body = json.loads(sent[0].data)
    assert body["messages"] == [{"role": "user", "content": "P"}]
    assert body["max_tokens"] == c.MAX_OUTPUT_TOKENS


def test_resolve_endpoint_env_param(monkeypatch):
    monkeypatch.setenv(c.ENV_BASE_URL, "https://example.invalid/v1")
    ep = c.resolve_endpoint(env={c.ENV_BASE_URL: "http://localhost:11434/v1"})
    assert ep.base_url == "http://localhost:11434/v1" and ep.is_local and ep.api_key == "local"
