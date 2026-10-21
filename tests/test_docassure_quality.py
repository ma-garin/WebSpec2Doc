from web.services.docassure import boundary, completeness, quality, readiness, testability
from web.services.docassure.model import Field, Finding, Location, RequirementUnit, Score


def U(rid, text, fields=None, kind="functional"):
    return RequirementUnit(rid, "D1", Location("D1", snippet=text[:20], snippet_hash="h"), text,
                           fields or {}, kind)


def F(rid, rule, sev, result="FAIL"):
    return Finding(f"{rule}:{rid}:1", rule, "1", result, sev, "t", "w", "r", "h",
                   Location("D1", snippet="s", snippet_hash="h"), requirement_id=rid)


# --- testability ---
def test_vague_not_testable():
    r = testability.assess(U("R1", "高速に検索結果を表示する"))
    assert r["verdict"] == "NOT_TESTABLE"
    assert "閾値・単位" in r["missing"] and "対象データ量" in r["missing"]
    assert "提案（未承認" in r["rewrite_proposal"]


def test_can_test_and_dict_input():
    t = "ログイン失敗時はエラーを返す。10000件のデータで検索結果を2秒以内に表示する場合"
    assert testability.assess(U("R1", t))["verdict"] == "CAN_TEST"
    assert testability.assess(U("R1", t).to_dict())["verdict"] == "CAN_TEST"


def test_empty_unknown_and_inferred_ignored():
    assert testability.assess(U("R1", ""))["verdict"] == "UNKNOWN"
    u = U("R1", "検索結果を表示する", {"constraint": Field("2秒以内", "INFERRED")})
    assert "閾値・単位" in testability.assess(u)["missing"]


# --- boundary ---
def test_boundary_range():
    r = boundary.derive(U("R1", "パスワードは8文字以上20文字以下"))
    vals = {v["label"]: v["value"] for v in r["boundary_values"]}
    assert vals == {"min-1": 7, "min": 8, "min+1": 9, "max-1": 19, "max": 20, "max+1": 21}
    assert r["gap"] is None and "null" in r["special"]


def test_boundary_exclusive_and_gap():
    r = boundary.derive(U("R1", "100件未満"))
    assert r["ranges"]["max"] == 99 and r["ranges"]["max_inclusive"] is False
    assert boundary.derive(U("R2", "大量のデータを扱える"))["gap"] == "TESTABILITY_GAP"


# --- completeness ---
def test_completeness_candidates():
    out = completeness.check([U("R1", "ユーザーはログインできる")])
    items = {c["item"] for c in out}
    assert {"ロック", "試行上限"} <= items
    assert all(c["status"] == "CANDIDATE" and c["severity"] in ("low", "medium") for c in out)
    assert completeness.check([U("R2", "天気を表示する")]) == []


# --- quality ---
def test_zero_units_none_even_without_findings():
    s = quality.score_document([], [])
    assert all(v.value is None for v in s.values())
    assert s["Overall"].value is None


def test_findings_zero_not_100():
    s = quality.score_document([U("R1", "システムは使いやすい")], [])
    assert s["Consistency"].value is None  # ルール未実行は 100 にしない
    assert s["Testability"].value == 0


def test_score_with_findings_and_overall():
    us = [U("R1", "検索結果を2秒以内に表示する。失敗時はエラーを返す場合"), U("R2", "高速に表示する")]
    fs = [F("R1", "CONFLICT-1", "low", "PASS"), F("R2", "CONFLICT-1", "high")]
    s = quality.score_document(us, fs)
    assert s["Consistency"].value == 87.5 and s["Consistency"].coverage == 1.0
    assert s["Overall"].value is not None and s["Consistency"].explanation
    assert quality.score_document(us, fs, expected_dimensions=["Testability"])["Consistency"].value is None


def test_low_coverage_none():
    us = [U("R1", "高速に表示する"), U("R2", "a"), U("R3", "b"), U("R4", "c")]
    s = quality.score_document(us, [F("R1", "CONFLICT-1", "low", "PASS")])
    assert s["Consistency"].coverage == 0.25 and s["Consistency"].value is None


# --- readiness ---
def S(v, c=1.0, n="x"):
    return Score(n, v, c)


def good():
    d = {k: S(90, 1.0, k) for k in quality.DIMENSIONS}
    d["Overall"] = S(90, 1.0, "Overall")
    return d


def test_ready_and_reasons_numeric():
    r = readiness.gate(good(), [], [])
    assert r["state"] == "READY" and any("90" in x for x in r["reasons"])


def test_blocked_cases():
    assert readiness.gate(good(), [], [{"severity": "critical", "status": "OPEN"}])["state"] == "BLOCKED"
    assert readiness.gate(good(), [], [], {"required_sections": ["目的"]})["state"] == "BLOCKED"
    assert readiness.gate(good(), [], [], {"approval_required": True})["state"] == "BLOCKED"
    f = F("R1", "TESTAB-1", "critical")
    assert readiness.gate(good(), [f], [])["state"] == "BLOCKED"


def test_conditionally_ready():
    assert readiness.gate(good(), [F("R1", "AMBIG-1", "high")], [])["state"] == "CONDITIONALLY_READY"
    g = good(); g["Traceability"] = S(90, 0.4, "Traceability")
    r = readiness.gate(g, [], [])
    assert r["state"] == "CONDITIONALLY_READY" and "0.4" in r["reasons"][0]


def test_unevaluated_major_not_ready_and_draft():
    g = good(); g["Testability"] = S(None, 0.0, "Testability")
    assert readiness.gate(g, [], [])["state"] == "REVIEWABLE"
    assert readiness.gate(quality.score_document([], []), [], [])["state"] == "DRAFT"
