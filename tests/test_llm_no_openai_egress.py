"""LLM 呼び出し箇所の宛先の contract test。

Ollama 構成では全対象が Ollama の base URL にだけ通信し、api.openai.com へ 0 件であること。
OpenAI 構成では api.openai.com 宛てであること。urllib.request.urlopen を差し替えて記録する。
"""
from __future__ import annotations

import io
import json
import urllib.request

import pytest

from llm.screen_classifier import classify_screen_with_llm
from web.services import openai_qa
from web.services.backendtest import llm_gate
from web.services.docverify.pair import semantic
from web.services.openai_qa import QA_ARTIFACT_SCHEMA, generate_openai_qa
from web.services.viewpoint_proposals import generate_viewpoint_proposals

OLLAMA = "http://127.0.0.1:11434/v1"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _content() -> dict:
    body = {k: "x" for k in QA_ARTIFACT_SCHEMA.get("required", [])}
    body.update(
        proposals=[],
        screen_type="form",
        confidence=0.9,
        keywords=["k"],
        test_priority="high",
    )
    return body


@pytest.fixture
def urls(monkeypatch, tmp_path):
    seen: list[str] = []

    def fake(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        seen.append(url)
        if url.endswith("/embeddings"):
            payload = {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}
        elif url.endswith("/chat/completions"):
            payload = {"choices": [{"message": {"content": json.dumps(_content())}}]}
        else:
            payload = {"output_text": json.dumps(_content())}
        return _Resp(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    for target in (openai_qa, llm_gate):
        monkeypatch.setattr(target, "_read_env", lambda: {})
    monkeypatch.setattr("web.env_store._read_env", lambda: {})
    monkeypatch.setattr(semantic, "_cache_dir", lambda: tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return seen


def _call_all() -> None:
    generate_openai_qa("example.com", {"pages": []}, [])
    generate_viewpoint_proposals({"url": "https://example.com"}, [])
    classify_screen_with_llm("t", ("h",), ["a"], "")
    assert semantic.embed(["x"]) is not None
    llm_gate._configured_base_is_local()
    assert llm_gate.route({"llm": {"provider": "openai"}}, {"schema": "s"}) == llm_gate.PROVIDER_OLLAMA


def test_ollama_config_sends_only_to_ollama(urls, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_LLM_BASE_URL", OLLAMA)
    _call_all()
    assert len(urls) == 4
    assert all(u.startswith("http://127.0.0.1:11434") for u in urls), urls
    assert not [u for u in urls if "api.openai.com" in u]


def test_openai_config_sends_to_openai(urls, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(openai_qa, "_read_env", lambda: {"OPENAI_API_KEY": "sk-test"})
    monkeypatch.setattr("web.env_store._read_env", lambda: {"OPENAI_API_KEY": "sk-test"})
    generate_openai_qa("example.com", {"pages": []}, [])
    generate_viewpoint_proposals({"url": "https://example.com"}, [])
    classify_screen_with_llm("t", ("h",), ["a"], "sk-test")
    assert semantic.embed(["x"]) is not None
    assert len(urls) == 4
    assert all(u.startswith("https://api.openai.com/v1/") for u in urls), urls


def test_no_key_nonlocal_does_not_communicate(urls):
    assert openai_qa.has_openai_api_key() is False
    result = classify_screen_with_llm("決済", ("h",), [], "")
    assert result.screen_type == "payment"
    assert semantic.embed(["x"]) is None
    assert urls == []
