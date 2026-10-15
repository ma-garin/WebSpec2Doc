"""System 06 R2 の単体・結合テスト（WS2D-DD-006 R2 の 8 章。受入基準 RD-006 の G/W/T から導く）。

LLM はスタブ（OpenAICompatClient.request の差し替え）。Blueprint はテスト内で Flask アプリに登録する。
"""
from __future__ import annotations

import csv
import io
import threading
import time

import pytest
from flask import Flask, g

from web import config
from web.routes import doc_verify, doc_verify_r2
from web.services.docverify import audit, llm_assist, llm_settings, questions, store

EMAIL = "yamada.taro@example.co.jp"
PASSAGE = f"担当者（{EMAIL}）は適切に対応すること。"
LEAK = ("Traceback", "Exception", ".py", "/Users/", "/tmp/")


class Stub:
    """送られた (送信先 URL, プロンプト) を記録するスタブ。"""

    def __init__(self, interp=("A", "A", "A"), fail=None, delay=0.0):
        self.calls, self.interp, self.fail, self.delay = [], list(interp), fail, delay

    def __call__(self, client, prompt, schema_name, schema, timeout_sec):
        self.calls.append((client._base, prompt, schema_name))
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise self.fail
        if schema_name == "docverify_interpret":
            return {"interpretation": self.interp[(len(self.calls) - 2) % len(self.interp)]}
        return {"reason": "「適切に」は基準がない。人によって解釈が変わる。検証できない。4 文目は切る。",
                "rewrite": "担当者は 1 営業日以内に回答すること。", "open_questions": ["回答期限は何日か", "担当者は誰か"]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    app = Flask(__name__)
    app.config.update(TESTING=True, TEST_USER=None)
    app.register_blueprint(doc_verify.bp)
    app.register_blueprint(doc_verify_r2.bp)

    @app.before_request
    def _user():
        g.auth_user = app.config["TEST_USER"]
    stub = Stub()
    monkeypatch.setattr(llm_settings.OpenAICompatClient, "request",
                        lambda self, *a, **k: stub(self, *a, **k))
    monkeypatch.setattr(llm_settings, "check_ollama", lambda url, timeout=3.0: True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-not-real-000000")
    return {"app": app, "c": app.test_client(), "stub": stub, "mp": monkeypatch}


def _insp(participants=None) -> dict:
    insp = {**store.new("R2"), "participants": participants or [],
            "document": {"name": "要件.md", "format": "md", "passages": 1, "version": 1},
            "passages": [{"id": "P1", "location": "1 行", "text": PASSAGE}],
            "findings": [{"id": "F1", "rule": "VAGUE", "severity": "minor", "viewpoint": "曖昧さ",
                          "message": "曖昧語「適切に」", "location": "1 行", "passage_id": "P1", "quote": "適切に",
                          "certainty": "推定", "status": "candidate", "answer": None, "origin": "auto",
                          "checklist_item": None, "disposition": None}]}
    return store.save(insp)


def _use(env, dest="ollama", **kw):
    r = env["c"].post("/api/docverify/r2/llm-settings", json={"destination": dest, **kw})
    assert r.status_code == 200, r.get_json()


def _preview(env, iid, **body):
    return env["c"].post(f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/preview", json=body)


def _explain(env, iid, **pbody):
    token = _preview(env, iid, **pbody).get_json()["consent_token"]
    return env["c"].post(f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/explain", json={"consent_token": token})


# ---- 単体: 伏せ字（FR-06-113）----
EVAL = {
    "email": ["a@b.jp", "taro.y+qa@example.com", "x_y@sub.example.co.jp"],
    "phone": ["03-1234-5678", "090-1234-5678", "09012345678", "+81 3 1234 5678", "0312345678"],
    "postal": ["〒100-0001", "123-4567"],
    "url_query": ["https://ex.jp/p?token=abc123&id=99"],
    "api_key": ["sk-proj-abcdefghijklmnop1234", "ghp_abcdefghijklmnopqrstuvwxyz0123", "AKIAABCDEFGHIJKLMNOP",
                "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7"],
    "my_number": ["123456789012", "1234 5678 9012"],
    "card": ["4111 1111 1111 1111", "5500-0000-0000-0004", "4012888888881881"],
    "ip": ["192.168.0.1", "8.8.8.8", "10.0.0.255"],
}


@pytest.mark.parametrize("kind", llm_assist.KINDS)
def test_mask_recall_per_kind(kind):
    samples = EVAL[kind]
    hit = sum(1 for s in samples if any(x["kind"] == kind for x in llm_assist.find(f"連絡先は {s} です。")))
    assert hit / len(samples) >= 0.95


def test_mask_removes_email_and_marks_span():
    m = llm_assist.mask(PASSAGE)
    assert EMAIL not in m["text"] and "［メール］" in m["text"]
    s = m["spans"][0]
    assert m["text"][s["start"]:s["end"]] == "［メール］" and m["counts"]["email"] == 1


def test_card_requires_luhn_and_manual_range():
    assert not any(x["kind"] == "card" for x in llm_assist.find("番号 4111 1111 1111 1112"))
    m = llm_assist.mask("社名は山田商事です。", [[3, 7]])
    assert "山田商事" not in m["text"] and m["counts"]["manual"] == 1
    with pytest.raises(ValueError):
        llm_assist.mask("短い", [[0, 99]])


def test_wobble_split_and_not_split():
    assert llm_assist.judge_wobble(["期限は翌日", "担当者が決める", "画面に表示する"])["split"] is True
    assert llm_assist.judge_wobble(["期限は翌営業日まで", "期限は翌営業日まで。", "担当者が決める"])["split"] is False


def test_three_sentences_and_timeout_cancel():
    assert llm_assist.three_sentences("一。二。三。四。") == "一。二。三。"
    with pytest.raises(llm_assist.AssistTimeout):
        llm_assist.run_with_timeout(lambda: time.sleep(2), 0.2)
    ev = threading.Event()
    threading.Timer(0.1, ev.set).start()
    started = time.monotonic()
    with pytest.raises(llm_assist.AssistCancelled):
        llm_assist.run_with_timeout(lambda: time.sleep(3), 5, ev)
    assert time.monotonic() - started < 1.5


# ---- 単体: 接続先（NFR-06-23）・説明文（NFR-06-02）----
@pytest.mark.parametrize("url", ["http://169.254.169.254", "http://8.8.8.8:11434", "http://ollama.example.com",
                                 "http://172.32.0.1:11434", "http://127.0.0.1:8765", "file:///etc/passwd"])
def test_ollama_url_rejected(url):
    with pytest.raises(ValueError, match="10.0.0.0/8"):
        llm_settings.validate_ollama_url(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://10.1.2.3:11434",
                                 "http://172.16.5.5:11434", "http://192.168.1.10:11434"])
def test_ollama_url_allowed(url):
    assert llm_settings.validate_ollama_url(url) == url


def test_disclosure_override_needs_source(env, tmp_path):
    root = tmp_path / "docverify"
    root.mkdir(parents=True, exist_ok=True)
    (root / "_llm_disclosures.json").write_text(
        '{"openai": {"retention": "30 日", "source": "https://x", "retrieved": "2027-01-01"},'
        ' "ollama": {"retention": "出典なし"}}', encoding="utf-8")
    d = llm_settings.disclosures()
    assert d["openai"]["retention"] == "30 日" and d["openai"]["retrieved"] == "2027-01-01"
    assert d["ollama"]["retention"] != "出典なし"


# ---- 結合: 送信先（FR-06-111・NFR-06-01・02・20）----
def test_default_none_and_zero_sends(env):
    s = env["c"].get("/api/docverify/r2/llm-settings").get_json()
    assert s["settings"]["destination"] == "none"
    iid = _insp()["id"]
    r = _preview(env, iid)
    assert r.status_code == 409 and "使わない設定" in r.get_json()["error"]
    assert env["stub"].calls == [] and audit.count("llm_send") == 0


def test_settings_show_location_and_training_per_destination(env):
    for dest in ("openai", "ollama"):
        _use(env, dest)
        d = env["c"].get("/api/docverify/r2/llm-settings").get_json()["destination"]
        assert d["key"] == dest and d["location"] and d["training"] and d["source"] and d["retrieved"]
    assert "国外" in llm_settings.disclosures()["openai"]["location"]


def test_ollama_down_is_not_saved(env):
    env["mp"].setattr(llm_settings, "check_ollama", lambda url, timeout=3.0: False)
    r = env["c"].post("/api/docverify/r2/llm-settings", json={"destination": "ollama"})
    assert r.status_code == 400 and r.get_json()["error"] == llm_settings.OLLAMA_DOWN
    assert llm_settings.load()["destination"] == "none"


def test_link_local_rejected_and_loopback_saved(env):
    r = env["c"].post("/api/docverify/r2/llm-settings",
                      json={"destination": "ollama", "ollama_url": "http://169.254.169.254"})
    assert r.status_code == 400 and "192.168.0.0/16" in r.get_json()["error"]
    _use(env, "ollama", ollama_url="http://127.0.0.1:11434")
    assert llm_settings.load()["ollama_url"] == "http://127.0.0.1:11434"


def test_only_admin_can_change_destination(env):
    env["app"].config["TEST_USER"] = {"name": "鈴木", "role": "user"}
    r = env["c"].post("/api/docverify/r2/llm-settings", json={"destination": "openai"})
    assert r.status_code == 403 and "テナント管理者" in r.get_json()["error"]


# ---- 結合: 送信前確認・説明（FR-06-110・112・113・115・116、NFR-06-11）----
def test_preview_has_five_items_and_sends_nothing(env):
    _use(env, "openai")
    iid = _insp()["id"]
    p = _preview(env, iid).get_json()
    d = p["destination"]
    assert d["name"] and "国外" in d["location"] and d["training"] and d["retention"]
    assert EMAIL not in p["masked"]["text"] and p["masked"]["spans"]
    assert env["stub"].calls == []


def test_explain_with_ollama_only_and_state_unchanged(env):
    _use(env, "ollama")
    insp = _insp()
    r = _explain(env, insp["id"])
    assert r.status_code == 200
    ai = r.get_json()["ai"]
    assert ai["label"] == "AI の提案" and ai["provider"] == "ollama" and ai["rewrite"]
    assert ai["explanation"].count("。") <= 3
    assert all(c[0].startswith("http://127.0.0.1:11434") for c in env["stub"].calls)
    assert not any("api.openai.com" in c[0] for c in env["stub"].calls)
    assert all(EMAIL not in c[1] for c in env["stub"].calls)
    f = store.load(insp["id"])["findings"][0]
    assert f["status"] == "candidate" and f["ai"]["input_sha256"]


def test_consent_token_is_single_use(env):
    _use(env, "ollama")
    iid = _insp()["id"]
    token = _preview(env, iid).get_json()["consent_token"]
    url = f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/explain"
    assert env["c"].post(url, json={"consent_token": token}).status_code == 200
    r = env["c"].post(url, json={"consent_token": token})
    assert r.status_code == 400 and "やり直して" in r.get_json()["error"]
    assert env["c"].post(url, json={}).status_code == 400


def test_failure_degrades_and_other_ops_continue(env):
    _use(env, "ollama")
    env["stub"].fail = ConnectionRefusedError("down")
    iid = _insp()["id"]
    r = _explain(env, iid)
    body = r.get_json()
    assert r.status_code == 503 and body["error"].startswith("AI の説明を作れませんでした")
    assert not any(x in body["error"] for x in LEAK)
    ok = env["c"].post(f"/api/docverify/inspections/{iid}/findings/F1", json={"status": "adopted"})
    assert ok.status_code == 200 and store.load(iid)["findings"][0]["status"] == "adopted"
    assert audit.count("llm_send_failed") == 1


def test_timeout_is_user_readable(env):
    _use(env, "ollama")
    env["mp"].setattr(llm_assist, "TIMEOUT_SEC", 0.3)
    env["stub"].delay = 2
    r = _explain(env, _insp()["id"])
    assert r.status_code == 504 and "60 秒以内" in r.get_json()["error"]


def test_wobble_flag(env):
    _use(env, "ollama")
    env["stub"].interp = ["期限は翌日", "担当者が決める", "画面に表示する"]
    iid = _insp()["id"]
    p = _preview(env, iid, with_wobble=True).get_json()
    assert p["sends"] == 4
    r = env["c"].post(f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/explain",
                      json={"consent_token": p["consent_token"]})
    assert r.get_json()["ai"]["wobble"]["split"] is True and len(env["stub"].calls) == 4


# ---- 結合: 採否・質問票・元文書（FR-06-114・117・118、NFR-06-04）----
def test_adopt_records_and_keeps_original(env):
    _use(env, "ollama")
    insp = _insp()
    _explain(env, insp["id"])
    r = env["c"].post(f"/api/docverify/r2/inspections/{insp['id']}/findings/F1/ai/decision", json={"decision": "adopt"})
    f = r.get_json()["inspection"]["findings"][0]
    assert f["disposition"].startswith("AI 提案を採用") and f["ai"]["adopted"] is True
    after = store.load(insp["id"])
    assert after["passages"] == insp["passages"] and after["document"] == insp["document"]
    acts = [x["action"] for x in audit.read_all()]
    assert "llm_send" in acts and "ai_adopt" in acts
    row = next(x for x in audit.read_all() if x["action"] == "llm_send")
    assert row["at"] and row["user"] and row["target"].endswith("/F1") and row["detail"]["provider"] == "ollama"


def test_decision_without_ai_is_rejected(env):
    iid = _insp()["id"]
    r = env["c"].post(f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/decision", json={"decision": "adopt"})
    assert r.status_code == 400 and "AI の説明を見る" in r.get_json()["error"]


def test_send_one_question_adds_one_row(env):
    _use(env, "ollama")
    iid = _insp()["id"]
    _explain(env, iid)
    before = len(questions.build(store.load(iid)["findings"]))
    r = env["c"].post(f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/questions", json={"indexes": [0]})
    assert r.status_code == 201
    assert len(questions.build(store.load(iid)["findings"])) == before + 1
    again = env["c"].post(f"/api/docverify/r2/inspections/{iid}/findings/F1/ai/questions", json={"indexes": [0]})
    assert len(questions.build(store.load(iid)["findings"])) == before + 1 and again.status_code == 201


# ---- 結合: 監査ログ（NFR-06-25）----
def test_audit_filter_csv_and_permission(env):
    for i in range(20):
        audit.append("ai_adopt", "佐藤" if i % 2 else "田中", f"x/F{i}", {"provider": "ollama"})
    _insp(participants=[{"name": "承認 太郎", "role": "approver", "done": False}])
    env["app"].config["TEST_USER"] = {"name": "承認 太郎", "role": "user"}
    rows = env["c"].get("/api/docverify/r2/audit?user=佐藤").get_json()["rows"]
    assert len(rows) == 10
    text = env["c"].get("/api/docverify/r2/audit.csv?user=佐藤").get_data(as_text=True).lstrip("﻿")
    body = list(csv.reader(io.StringIO(text)))[1:]
    assert [b[3] for b in body] == [r["target"] for r in rows]
    env["app"].config["TEST_USER"] = {"name": "レビュアー", "role": "user"}
    r = env["c"].get("/api/docverify/r2/audit")
    assert r.status_code == 403 and "権限" in r.get_json()["error"]
    assert env["c"].get("/api/docverify/r2/audit.csv").status_code == 403


def test_audit_csv_formula_guard():
    rows = [{"at": "2026-10-15T00:00:00", "user": "=cmd", "action": "llm_send", "target": "t", "detail": {}}]
    assert "'=cmd" in audit.to_csv(rows)


def test_preview_extra_words_are_masked(env):
    _use(env, "ollama")
    iid = _insp()["id"]
    p = _preview(env, iid, extra_words=["担当者"]).get_json()
    assert "担当者" not in p["masked"]["text"] and p["masked"]["counts"]["manual"] >= 1
