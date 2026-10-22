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


# ---- ネットワークに出ない契約（urlopen・名前解決を捕捉。実送信 0） ----
import io
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def wire(monkeypatch):
    """urlopen を捕捉して偽応答を返す。名前解決・接続の宛先も記録し、実接続は全て拒否する。"""
    rec = {"reqs": [], "resolved": [], "connected": []}

    def fake_urlopen(req, timeout=None, **kw):
        rec["reqs"].append({"url": req.full_url, "headers": {k.lower(): v for k, v in req.header_items()},
                            "json": json.loads(req.data.decode())})
        content = json.dumps({"findings": []})
        return _Resp(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    def no_resolve(host, *a, **k):
        rec["resolved"].append(host)
        raise AssertionError(f"実名前解決が起きた: {host}")

    def no_connect(addr, *a, **k):
        rec["connected"].append(addr)
        raise AssertionError(f"実接続が起きた: {addr}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(socket, "getaddrinfo", no_resolve)
    monkeypatch.setattr(socket, "create_connection", no_connect)
    return rec


def _run(client):
    return rb.run(UNITS, DOCS, client, reviewers=["Security"])


def test_openai_destination_wire_contract(wire, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_LLM_API_KEY", "sk-test-dummy-0000")
    client = llm_settings.client_for({"destination": "openai", "openai_model": "gpt-contract"})
    _run(client)
    assert wire["reqs"], "リクエストが構築されていない"
    for r in wire["reqs"]:
        u = urlsplit(r["url"])
        assert (u.scheme, u.hostname) == ("https", "api.openai.com")
        assert u.path == "/v1/chat/completions"
        assert r["headers"]["authorization"] == "Bearer sk-test-dummy-0000"
        assert r["json"]["model"] == "gpt-contract"
    assert wire["resolved"] == [] and wire["connected"] == []


def test_ollama_destination_never_touches_openai(wire, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-leak-1111")
    monkeypatch.setenv("WEBSPEC2DOC_LLM_API_KEY", "sk-must-not-leak-2222")
    client = llm_settings.client_for({"destination": "ollama", "ollama_url": "http://192.168.1.50:11434",
                                      "ollama_model": "qwen-contract"})
    _run(client)
    assert wire["reqs"]
    for r in wire["reqs"]:
        u = urlsplit(r["url"])
        assert (u.scheme, u.hostname, u.port) == ("http", "192.168.1.50", 11434)
        assert u.path == "/v1/chat/completions"
        assert r["json"]["model"] == "qwen-contract"
        assert "sk-must-not-leak" not in json.dumps(r["headers"]) + json.dumps(r["json"])
    assert not any("openai" in h for h in map(str, wire["resolved"] + wire["connected"]))
    assert wire["resolved"] == [] and wire["connected"] == []


@pytest.mark.parametrize("url", [
    "https://api.openai.com", "http://evil.example.com:11434", "http://8.8.8.8:11434",
    "http://169.254.169.254", "http://169.254.169.254/latest/meta-data", "http://[::1]:11434",
    "ftp://127.0.0.1:11434", "file:///etc/passwd", "gopher://127.0.0.1:11434", "javascript:alert(1)",
    "http://user:pw@127.0.0.1:11434", "http://127.0.0.1:8765", "", "127.0.0.1:11434",
    "http://127.0.0.1.evil.com:11434", "http://100.64.0.1:11434"])
def test_validate_ollama_url_rejects(url):
    with pytest.raises(ValueError):
        llm_settings.validate_ollama_url(url)
    with pytest.raises(ValueError):
        llm_settings.client_for({"destination": "ollama", "ollama_url": url})


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://localhost:11434",
                                 "http://10.1.2.3:11434", "http://172.16.0.5", "http://192.168.0.9:11434"])
def test_validate_ollama_url_accepts_internal(url):
    assert llm_settings.validate_ollama_url(url).startswith("http://")


def test_none_and_keyless_openai_degrade_without_any_request(wire):
    before = pipeline.analyze(DOCS)
    for cfg in ({"destination": "none"}, {"destination": "openai"}):
        cl = llm_settings.client_for(cfg)
        assert cl is None
        r = rb.run(UNITS, DOCS, cl)
        assert r["mode"] == "DEGRADED"
    assert wire["reqs"] == [] and wire["resolved"] == [] and wire["connected"] == []
    assert _strip(before.get("findings")) == _strip(pipeline.analyze(DOCS).get("findings"))


@pytest.mark.parametrize("dest", ["openai", "ollama"])
def test_payload_masks_pii_on_wire(dest, wire, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_LLM_API_KEY", "sk-test-dummy-0000")
    cfg = {"destination": dest, "ollama_url": "http://127.0.0.1:11434"}
    _run(llm_settings.client_for(cfg))
    sent = "\n".join(json.dumps(r["json"], ensure_ascii=False) + r["url"] for r in wire["reqs"])
    assert wire["reqs"]
    for secret in (EMAIL, PHONE, KEY, "ABCDEFGHIJKLMNOP1234567890"):
        assert secret not in sent, f"生値が送信された: {secret}"
    assert "［メール］" in sent and "［電話］" in sent
    assert OUTSIDE not in sent


def test_system06_code_has_no_direct_openai():
    root = Path(__file__).resolve().parent.parent
    files = list((root / "web/services/docassure").rglob("*.py")) + list((root / "web/routes").glob("doc_assure*.py"))
    assert files
    pat = re.compile(r"api\.openai\.com|^\s*(import|from)\s+openai\b|OPENAI_API_KEY", re.M | re.I)
    bad = [f"{f.relative_to(root)}: {m.group(0).strip()}" for f in files
           for m in pat.finditer(f.read_text(encoding="utf-8"))]
    assert not bad, bad
