"""AC25〜27: 意味レビューの Ollama / OpenAI / AI 不可の各経路を、偽の OpenAI 互換サーバで実行検証する。

実 API は呼ばない。接続先が 127.0.0.1 だけであることをソケット層で確認する。
"""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from web.services.docassure import pipeline, review_board as rb
from web.services.docverify import llm_settings

EMAIL, PHONE, KEY = "taro.yamada@example.com", "03-1234-5678", "sk-proj-ABCDEFGHIJKLMNOP1234567890"
OUTSIDE = "OUTSIDE-CHUNK-MARKER"
DOC_TEXT = (f"REQ-1 ユーザーはログインできる。連絡先は {EMAIL} と {PHONE} とする。\n"
            f"REQ-2 外部連携のキーは {KEY} とする。\n"
            f"REQ-3 {OUTSIDE} 監査ログを保存する。")
DOCS = [{"id": "D1", "name": "d", "type": "requirements", "text": DOC_TEXT}]
UNITS = [
    {"requirement_id": "REQ-1", "document_id": "D1", "raw_text": DOC_TEXT.splitlines()[0],
     "location": {"document_id": "D1", "line_start": 1, "line_end": 1}},
    {"requirement_id": "REQ-2", "document_id": "D1", "raw_text": DOC_TEXT.splitlines()[1],
     "location": {"document_id": "D1", "line_start": 2, "line_end": 2}},
]
ROLES = ["Security", "UX", "Reliability"]


def _finding(role, quote, a):
    return {"finding": f"CONCLUSION-{role}", "reason": "r", "severity": "medium", "confidence": 0.8,
            "question": "q", "recommended_action": "a",
            "evidence": [{"document_id": "D1", "line_start": a, "line_end": a, "quote": quote}]}


class Fake:
    """偽 OpenAI 互換サーバ。mode: ok / bad_json / http500 / slow / fail_security。"""

    def __init__(self):
        self.mode, self.bodies, self.lock = "ok", [], threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.loads(raw)
                with fake.lock:
                    fake.bodies.append({"path": self.path, "raw": raw.decode(), "json": body})
                prompt = "".join(m["content"] for m in body["messages"])
                mode = fake.mode
                if mode == "fail_security":
                    mode = "http500" if "Security 専門" in prompt else "ok"
                try:
                    if mode == "http500":
                        self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
                    if mode == "slow":
                        time.sleep(2.0)
                    if mode == "bad_json":
                        content = "{not json"
                    else:
                        role = prompt.split("あなたは ")[1].split(" 専門")[0] if "あなたは " in prompt else "?"
                        items = []
                        if "lines=1-1" in prompt:
                            items = [_finding(role, "ユーザーはログインできる", 1),
                                     _finding(role, "この引用は文書に存在しない", 1)]
                        content = json.dumps({"findings": items}, ensure_ascii=False)
                    out = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers(); self.wfile.write(out)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def count(self):
        return len(self.bodies)

    def prompts(self):
        return ["".join(m["content"] for m in b["json"]["messages"]) for b in self.bodies]


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.srv.shutdown(); f.srv.server_close()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    rb.clear_cache()
    for k in ("WEBSPEC2DOC_LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for mod in ("llm.openai_client", "src.llm.openai_client"):
        try:
            m = __import__(mod, fromlist=["x"])
            monkeypatch.setattr(m, "record_llm_activity", lambda **kw: None)
        except ImportError:
            pass
    yield
    rb.clear_cache()


@pytest.fixture
def sockets(monkeypatch):
    seen = []
    real = socket.socket.connect

    def guard(self, addr):
        if self.family == socket.AF_INET:
            seen.append(addr[0])
            assert addr[0] == "127.0.0.1", f"外部へ接続しようとした: {addr}"
        return real(self, addr)

    monkeypatch.setattr(socket.socket, "connect", guard)
    return seen


def make_client(dest, fake, monkeypatch):
    if dest == "ollama":
        return llm_settings.client_for({"destination": "ollama", "ollama_url": f"http://127.0.0.1:{fake.port}",
                                        "ollama_model": "qwen-test"})
    monkeypatch.setenv("WEBSPEC2DOC_LLM_API_KEY", "sk-test-dummy-0000")
    orig = llm_settings.OpenAICompatClient.__init__

    def redirected(self, name, model, base_url, api_key):
        assert base_url == "https://api.openai.com/v1"  # 本物の設定が OpenAI を指していること
        orig(self, name, model, f"http://127.0.0.1:{fake.port}/v1", api_key)

    monkeypatch.setattr(llm_settings.OpenAICompatClient, "__init__", redirected)
    return llm_settings.client_for({"destination": "openai", "openai_model": "gpt-test"})


@pytest.fixture(params=["ollama", "openai"])
def provider(request, fake, monkeypatch, sockets):
    return request.param, make_client(request.param, fake, monkeypatch)


# (1)(2)(5)(AC25/26)
def test_both_providers_return_candidates_with_provider(provider, fake, sockets):
    name, client = provider
    assert client.name == name
    r = rb.run(UNITS, DOCS, client, reviewers=ROLES)
    assert r["mode"] == "AI" and r["provider"]["name"] == name
    assert r["findings"], "finding が返らない"
    assert all(f["status"] == "CANDIDATE" and f["source"] == "ai" and f["provider"]["name"] == name
               for f in r["findings"])
    assert fake.count == len(ROLES) * len(UNITS)
    assert set(sockets) == {"127.0.0.1"}


def test_masking_and_chunk_only(provider, fake):
    _, client = provider
    rb.run(UNITS, DOCS, client, reviewers=ROLES)
    sent = "\n".join(b["raw"] + "".join(m["content"] for m in b["json"]["messages"]) for b in fake.bodies)
    for secret in (EMAIL, PHONE, KEY, "ABCDEFGHIJKLMNOP1234567890"):
        assert secret not in sent, f"生値が送信された: {secret}"
    assert "［メール］" in sent and "［電話］" in sent and "［API キー］" in sent
    assert OUTSIDE not in sent, "該当チャンク以外（全文）が送信された"
    assert all(b["path"].endswith("/chat/completions") for b in fake.bodies)


def test_invalid_evidence_quarantined(provider):
    _, client = provider
    r = rb.run(UNITS, DOCS, client, reviewers=["UX"])
    assert any(u["status"] == "INVALID_EVIDENCE" for u in r["unsupported"])
    assert all(e["quote"] != "この引用は文書に存在しない" for f in r["findings"] for e in f["evidence"])
    assert r["findings"] and all(f["evidence"][0]["quote"] == "ユーザーはログインできる" for f in r["findings"])


def test_reviewers_independent(provider, fake):
    _, client = provider
    rb.run(UNITS, DOCS, client, reviewers=ROLES)
    prompts = fake.prompts()
    assert prompts and all("CONCLUSION-" not in p for p in prompts), "他レビュアーの結論がプロンプトに入った"
    for role in ROLES:
        mine = [p for p in prompts if f"あなたは {role} 専門" in p]
        assert len(mine) == len(UNITS)
        assert all(not any(f"あなたは {o} 専門" in p for o in ROLES if o != role) for p in mine)


# (6)
def test_cache_hit_on_same_chunk(provider, fake):
    _, client = provider
    r1 = rb.run(UNITS, DOCS, client, reviewers=ROLES)
    n = fake.count
    assert r1["sends"] == n and r1["cache_hits"] == 0
    r2 = rb.run(UNITS, DOCS, client, reviewers=ROLES)
    assert fake.count == n, "2 回目で偽サーバへの呼び出しが増えた"
    assert r2["sends"] == 0 and r2["cache_hits"] == n
    assert [f["finding"] for f in r2["findings"]] == [f["finding"] for f in r1["findings"]]


# (3)(AC27)
def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()
                if not any(t in k for t in ("sec", "timing", "elapsed", "generated_at", "duration", "cache_"))}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def _strip(d):
    return json.dumps(_clean(d), sort_keys=True, ensure_ascii=False, default=str)


@pytest.mark.parametrize("mode", ["bad_json", "http500", "slow"])
def test_failure_modes_degrade_without_touching_deterministic(mode, provider, fake):
    _, client = provider
    before = pipeline.analyze(DOCS)
    fake.mode = mode
    r = rb.run(UNITS, DOCS, client, reviewers=["UX", "Security"], timeout=0.5)
    assert r["mode"] == "DEGRADED" or r.get("failures", 0) > 0
    assert r["mode"] == "DEGRADED" and r["findings"] == [] and r["failures"] == fake.count
    after = pipeline.analyze(DOCS)
    assert _strip(before) == _strip(after)


def test_partial_failure_recorded_and_ok_findings_kept(provider, fake):
    _, client = provider
    fake.mode = "fail_security"
    r = rb.run(UNITS, DOCS, client, reviewers=["Security", "UX"])
    assert r["mode"] == "AI" and r["failures"] == len(UNITS)
    assert r["findings"] and all(f["reviewer"] == "UX" for f in r["findings"])


# (4)
def test_no_client_degrades_for_none_and_keyless_openai(monkeypatch):
    assert llm_settings.client_for({"destination": "none"}) is None
    assert llm_settings.client_for({"destination": "openai"}) is None  # キー無し
    before = pipeline.analyze(DOCS)
    for cl in (None, llm_settings.client_for({"destination": "openai"})):
        r = rb.run(UNITS, DOCS, cl)
        assert r["mode"] == "DEGRADED" and r["findings"] == []
    assert _strip(before.get("findings")) == _strip(pipeline.analyze(DOCS).get("findings"))
