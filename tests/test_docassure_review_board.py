from web.services.docassure import confidence, evidence_guard as guard, review_board as rb

DOCS = [{"id": "D1", "text": "REQ-1 ユーザーはログインできる。連絡先は a@example.com とする。\n外部APIのタイムアウトは30秒とする。\n応答は速いこと。"}]
UNITS = [{"requirement_id": "REQ-1", "document_id": "D1", "raw_text": "ユーザーはログインできる。連絡先は a@example.com とする。",
          "location": {"document_id": "D1", "line_start": 1, "line_end": 1}}]


class Stub:
    def __init__(self, name, model, fn):
        self.name, self.model, self.fn, self.prompts = name, model, fn, []

    def request(self, prompt, schema_name, schema, timeout_sec):
        self.prompts.append(prompt)
        return self.fn(prompt)


def ev(q="ユーザーはログインできる", a=1, b=1):
    return {"document_id": "D1", "line_start": a, "line_end": b, "quote": q}


def finding(**kw):
    return {"finding": "異常系が未定義", "reason": "r", "severity": "medium", "confidence": 0.9, "question": "q",
            "recommended_action": "a", "evidence": [ev()], **kw}


def setup_function(_):
    rb.clear_cache()


def test_independence_and_both_provider_styles():
    for name in ("openai", "ollama"):
        rb.clear_cache()
        c = Stub(name, "m", lambda p: {"findings": [finding(finding=f"SECRET-{p.count('Security')}")]})
        r = rb.run(UNITS, DOCS, c, reviewers=["Security", "UX"])
        assert r["mode"] == "AI" and r["provider"]["name"] == name
        assert all(f["source"] == "ai" and f["status"] == "CANDIDATE" for f in r["findings"])
        assert len(c.prompts) == 2
        assert "SECRET" not in "".join(c.prompts)  # 他 Reviewer の出力はプロンプトに入らない


def test_masking_before_send():
    c = Stub("openai", "m", lambda p: {"findings": []})
    rb.run(UNITS, DOCS, c, reviewers=["UX"])
    assert "a@example.com" not in c.prompts[0]


def test_fabricated_quote_isolated():
    c = Stub("openai", "m", lambda p: {"findings": [finding(), finding(evidence=[ev("存在しない引用文")]), finding(evidence=[])]})
    r = rb.run(UNITS, DOCS, c, reviewers=["UX"])
    assert len(r["findings"]) == 1
    assert sorted(u["status"] for u in r["unsupported"]) == ["INVALID_EVIDENCE", "UNSUPPORTED"]
    assert r["findings"][0]["evidence"][0]["snippet_hash"] == guard.snippet_hash("ユーザーはログインできる")


def test_degraded_when_no_client_or_all_fail():
    assert rb.run(UNITS, DOCS, None) == {"mode": "DEGRADED", "reason": "semantic review unavailable", "findings": []}

    def boom(p):
        raise ConnectionError("x")
    r = rb.run(UNITS, DOCS, Stub("ollama", "m", boom), reviewers=["UX"])
    assert r["mode"] == "DEGRADED" and r["findings"] == []


def test_cache_hit():
    c = Stub("openai", "m", lambda p: {"findings": []})
    rb.run(UNITS, DOCS, c, reviewers=["UX"])
    r = rb.run(UNITS, DOCS, c, reviewers=["UX"])
    assert len(c.prompts) == 1 and r["cache_hits"] == 1


def test_disputed_kept_both():
    def fn(p):
        if "Security" in p.split("\n")[0]:
            return {"findings": [finding(stance="defect", severity="high")]}
        return {"findings": [finding(stance="acceptable", severity="low")]}
    r = rb.run(UNITS, DOCS, Stub("openai", "m", fn), reviewers=["Security", "UX"])
    assert len(r["findings"]) == 2
    assert all(f["dispute_status"] == "DISPUTED" and f["status"] == "CANDIDATE" for f in r["findings"])


def test_counter_evidence_dismisses():
    f = finding(finding="タイムアウト未定義", reason="外部APIのタイムアウトが定義されていない")
    c = Stub("openai", "m", lambda p: {"findings": [f]})
    r = rb.run(UNITS, DOCS, c, reviewers=["Reliability"])
    assert r["findings"] == [] and r["dismissed"][0]["dismissed_candidate"]
    assert r["dismissed"][0]["counter_evidence"][0]["line_start"] == 2


def test_confidence_not_self_reported():
    lo = confidence.calibrate({"confidence": 1.0}, {})
    hi = confidence.calibrate({"confidence": 0.0}, {"direct_evidence": True, "sources": 2, "rule_verified": True})
    assert lo <= 0.4 < hi
    assert confidence.calibrate({"confidence": 0}, {"direct_evidence": True, "contradictions": 2}) < \
        confidence.calibrate({"confidence": 0}, {"direct_evidence": True})
    assert confidence.calibrate_detail({}, {})["basis"]


def _many(n):
    return [{"requirement_id": f"R{i}", "document_id": "D1", "raw_text": f"要件{i}は処理できる。",
             "location": {"document_id": "D1", "line_start": 1, "line_end": 1}} for i in range(n)]


def test_send_cap_and_not_reviewed():
    c = Stub("openai", "m", lambda p: {"findings": []})
    r = rb.run(_many(200), DOCS, c)
    assert r["sends"] <= rb.MAX_SENDS and len(c.prompts) == rb.MAX_SENDS
    nr = r["not_reviewed"]
    assert nr["reason"] == "送信上限のため未レビュー"
    # 60 送信 = 5 要件 × 12 観点。途中で切れた要件も未レビューに数える（レビュー済みは満了した要件のみ）
    assert nr["count"] == 195 and len(nr["requirement_ids"]) == 195


def test_priority_order_and_cache_not_counted():
    units = _many(4)
    units[3]["findings"] = [{"x": 1}]
    c = Stub("openai", "m", lambda p: {"findings": []})
    rb.run(units, DOCS, c, reviewers=["UX"], max_sends=1)
    assert "要件3" in c.prompts[0]
    c2 = Stub("openai", "m", lambda p: {"findings": []})
    r = rb.run(units, DOCS, c2, reviewers=["UX"], max_sends=1)  # 要件3 はキャッシュ命中＝送信に数えない
    assert r["cache_hits"] == 1 and r["sends"] == 1 and r["not_reviewed"]["count"] == 2


def test_time_cap():
    c = Stub("openai", "m", lambda p: {"findings": []})
    r = rb.run(_many(3), DOCS, c, reviewers=["UX"], max_seconds=-1)
    assert not c.prompts and r["not_reviewed"]["count"] == 3 and "時間上限" in r["not_reviewed"]["reason"]
