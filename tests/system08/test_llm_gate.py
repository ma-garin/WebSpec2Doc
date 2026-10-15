"""AC: 送信前検査（秘密・データ値の検出）・OpenAI 宛ての停止・記録は本文を持たずハッシュのみ。"""
from __future__ import annotations

import hashlib
import json

import pytest

from web.services.backendtest import llm_gate, redact, store

RECORD_KEYS = {"at", "stage", "purpose", "provider", "llm", "kinds", "sha256", "inspection", "sent"}


class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, provider, instructions, body):
        self.calls.append(provider)
        return "要約です。"


def _job(provider="openai"):
    return {**store.new("月次", "batch", "system"), "llm": {"provider": provider, "external_scope": "schema_spec"}}


def test_redact_scan_detects_secret_and_personal_values():
    hits = redact.scan("password=Hunter2xyz 連絡先 yamada@example.com")
    kinds = {h["kind"] for h in hits}
    assert redact.KIND_SECRET in kinds and redact.KIND_PERSONAL in kinds
    masked = redact.mask("password=Hunter2xyz", redact.scan("password=Hunter2xyz"))
    assert "Hunter2xyz" not in masked


def test_openai_with_personal_data_is_blocked_and_record_has_hash_only():
    """Given OpenAI 宛ての仕様に個人情報 / When 送信 / Then 送らず止め、記録は本文なしのハッシュと件数だけ。"""
    spy, payload = Spy(), {"spec": "顧客の連絡先は yamada@example.com とする"}
    with pytest.raises(llm_gate.GateBlocked) as exc:
        llm_gate.send(_job(), 2, "spec_summary", payload, "sen", transport=spy)
    rec = exc.value.record
    assert spy.calls == [] and rec["sent"] is False
    assert set(rec) == RECORD_KEYS
    assert rec["sha256"] == hashlib.sha256(llm_gate.build_body(payload).encode("utf-8")).hexdigest()
    assert rec["inspection"]["data_hits"] >= 1
    assert "yamada" not in json.dumps(rec, ensure_ascii=False)


def test_openai_with_imported_column_value_is_blocked():
    """Given 取り込んだデータの列値が仕様文に混入 / When OpenAI へ送信 / Then 止まる。"""
    values = llm_gate.column_values("order_id,customer_name\n1,山田花子\n2,佐藤一郎\n")
    assert "山田花子" in values
    spy = Spy()
    with pytest.raises(llm_gate.GateBlocked):
        llm_gate.send(_job(), 3, "viewpoints", {"spec": "山田花子 の注文を集計する"}, "sen",
                      data_values=values, transport=spy)
    assert spy.calls == []


def test_ollama_accepts_data_values_but_records_no_body():
    """Given ローカル LLM 指定で個人情報を含む / When 送信 / Then 送られ、記録には本文が残らない。"""
    spy = Spy()
    got = llm_gate.send(_job("ollama"), 5, "test_data", {"data": "yamada@example.com,山田花子"}, "sen",
                        transport=spy)
    assert spy.calls == ["ollama"] and got["record"]["sent"] is True
    assert set(got["record"]) == RECORD_KEYS
    assert "yamada" not in json.dumps(got["record"], ensure_ascii=False)


def test_data_payload_is_routed_to_ollama_even_if_openai_configured():
    spy = Spy()
    llm_gate.send(_job("openai"), 5, "test_data", {"data": "1,2,3"}, "sen", transport=spy)
    assert spy.calls == ["ollama"]


def test_entered_secret_blocks_even_for_ollama():
    """Given 実行時に入力した接続の秘密が本文に含まれる / When ローカル LLM へ送信 / Then 止まる。"""
    spy = Spy()
    with pytest.raises(llm_gate.GateBlocked) as exc:
        llm_gate.send(_job("ollama"), 6, "code_summary", {"spec": "接続は MyPw-98765zz で行う"}, "sen",
                      secrets=["MyPw-98765zz"], transport=spy)
    assert spy.calls == [] and exc.value.record["inspection"]["secret_hits"] >= 1
    assert "MyPw-98765zz" not in json.dumps(exc.value.record, ensure_ascii=False)


def test_unknown_payload_kind_is_rejected():
    with pytest.raises(store.StoreError):
        llm_gate.send(_job(), 2, "x", {"source_code": "print(1)"}, "sen", transport=Spy())
