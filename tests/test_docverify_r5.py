"""System 06 R5 テスト（WS2D-DD-006 R5 8 章。RD-006 FR-06-170〜174・SCR-06-10 の G/W/T）。

Blueprint は共有の web/__init__.py へ未結線のため、テスト用の Flask アプリに登録して確かめる。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import docverify_eval as ev  # noqa: E402
from web.routes import doc_verify_r5  # noqa: E402
from web.services.docverify import accuracy as acc  # noqa: E402

LEAK = re.compile(r"Traceback|Exception|\.py\b|/Users/|/tmp/|/private/")


def _rule(p, r, n=10, gold=5, pred=5):
    return {"n": n, "n_gold": gold, "n_predicted": pred, "tp": 0, "fp": 0, "fn": 0, "precision": p, "recall": r}


def _write(tmp_path, data) -> Path:
    p = tmp_path / "result.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__, template_folder=str(ROOT / "templates"))
    app.register_blueprint(doc_verify_r5.bp)
    return app, app.test_client()


# --- 評価セット（FR-06-171） ---
def test_dataset_has_80_or_more_sentences_with_valid_labels():
    rows = ev.load_dataset(ev.DEFAULT_DATASET)
    assert len(rows) >= 80
    assert len({r["id"] for r in rows}) == len(rows)
    assert any(r["labels"] == [] for r in rows)          # 空集合（欠陥なし）を含む
    assert {lab for r in rows for lab in r["labels"]} == set(ev.RULES)


def test_dataset_rejects_unknown_label(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps({"id": "X", "text": "文。", "labels": ["NOPE"], "method": "injected"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ev.load_dataset(p)


# --- 測定（FR-06-170・173・174） ---
def test_score_counts_tp_fp_fn_per_rule(monkeypatch):
    monkeypatch.setattr(ev, "predict", lambda t: {"REQ.AND_OR"} if "A" in t else set())
    rows = [{"text": "A", "labels": ["REQ.AND_OR"]}, {"text": "A", "labels": []}, {"text": "B", "labels": ["REQ.AND_OR"]}]
    r = ev.score(rows)["REQ.AND_OR"]
    assert (r["tp"], r["fp"], r["fn"], r["n"]) == (1, 1, 1, 3)
    assert (r["precision"], r["recall"]) == (0.5, 0.5)
    assert ev.score(rows)["REQ.UNIVERSAL"]["precision"] is None   # 検出 0 件は値を出さない


def test_eval_is_deterministic_and_records_regression(tmp_path):
    out = tmp_path / "r.json"
    args = ["--out", str(out), "--date", "2026-10-15"]
    assert ev.main(args) == 0
    first = out.read_text(encoding="utf-8")
    assert ev.main(args) == 0
    assert out.read_text(encoding="utf-8") == first                 # 決定的
    data = json.loads(first)
    assert data["previous"] is None and data["delta"] is None
    assert data["scope"].endswith("（LLM は対象外）")
    assert set(data["rules"]) == set(ev.RULES)
    assert all({"precision", "recall", "n"} <= set(r) for r in data["rules"].values())
    assert data["by_method"]["real"] is None and data["by_method"]["injected"]["n"] > 0
    # 規則を変更（版が変わる）→ 前回値と差が並ぶ
    old = dict(data, rules_version="old000000000",
               rules={k: dict(v, precision=0.5, recall=0.5) for k, v in data["rules"].items()})
    out.write_text(json.dumps(old), encoding="utf-8")
    assert ev.main(args) == 0
    new = json.loads(out.read_text(encoding="utf-8"))
    assert new["previous"]["rules_version"] == "old000000000"
    rid = "REQ.AND_OR"
    assert new["delta"][rid]["precision"] == round(new["rules"][rid]["precision"] - 0.5, 3)


def test_cli_runs_with_venv_python(tmp_path):
    out = tmp_path / "r.json"
    res = subprocess.run([sys.executable, str(ROOT / "scripts/docverify_eval.py"), "--out", str(out), "--date", "2026-10-15"],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert res.returncode == 0, res.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["dataset"]["n"] >= 80


# --- 精度ページ（FR-06-170・172・174） ---
def test_low_precision_rule_is_disabled_with_reason(tmp_path):
    p = _write(tmp_path, {"rules": {"REQ.UNIVERSAL": _rule(0.6, 0.9), "REQ.AND_OR": _rule(0.9, 0.9)}})
    rows = {r["rule"]: r for r in acc.page(p)["rules"]}
    assert rows["REQ.UNIVERSAL"]["enabled_by_default"] is False
    assert "0.600" in rows["REQ.UNIVERSAL"]["reason"] and "無効" in rows["REQ.UNIVERSAL"]["reason"]
    assert rows["REQ.AND_OR"]["enabled_by_default"] is True
    assert acc.disabled_rules(p) == frozenset({"REQ.UNIVERSAL"})


def test_three_measured_two_unmeasured(tmp_path):
    rules = {k: _rule(0.8, 0.7) for k in ("REQ.AND_OR", "REQ.UNIVERSAL", "REQ.INCOMPLETE")}
    rows = acc.page(_write(tmp_path, {"rules": rules}))["rules"]
    measured = [r for r in rows if r["measured"]]
    assert len(measured) == 3 and all(r["precision"] == "0.800" for r in measured)
    unmeasured = [r for r in rows if not r["measured"]]
    assert len(unmeasured) >= 2 and all(r["precision"] == "未測定" and r["recall"] == "未測定" for r in unmeasured)


def test_methods_are_separate_columns(tmp_path):
    data = {"rules": {"REQ.AND_OR": _rule(0.8, 0.8)},
            "by_method": {"injected": {"n": 4, "rules": {"REQ.AND_OR": _rule(1.0, 0.5, n=4)}}, "real": None}}
    page = acc.page(_write(tmp_path, data))
    assert [m["key"] for m in page["methods"]] == ["injected", "authored", "real"]
    bm = next(r for r in page["rules"] if r["rule"] == "REQ.AND_OR")["by_method"]
    assert bm["injected"]["precision"] == "1.000" and bm["real"]["precision"] == "未測定"


def test_no_result_file_shows_unmeasured(tmp_path):
    page = acc.page(tmp_path / "none.json")
    assert page["measured"] is False and page["measured_on"] == "未測定"
    assert all(r["precision"] == "未測定" for r in page["rules"])
    assert acc.disabled_rules(tmp_path / "none.json") == frozenset()


def test_zero_detections_not_disabled(tmp_path):
    p = _write(tmp_path, {"rules": {"REQ.MULTIPLE_REQUIREMENTS": _rule(None, 0.0, pred=0)}})
    row = next(r for r in acc.page(p)["rules"] if r["rule"] == "REQ.MULTIPLE_REQUIREMENTS")
    assert row["enabled_by_default"] is True and row["precision"] == "未測定" and "0 件" in row["reason"]


# --- API（SCR-06-10） ---
def test_api_returns_page(client, tmp_path, monkeypatch):
    _, c = client
    rules = {"REQ.AND_OR": _rule(0.9, 0.8)}
    monkeypatch.setattr(acc, "RESULT_PATH", _write(tmp_path, {"measured_on": "2026-10-15", "rules": rules,
                                                              "limits": ["限界の文"]}))
    r = c.get("/api/docverify/accuracy")
    assert r.status_code == 200
    d = r.get_json()
    assert d["measured_on"] == "2026-10-15" and d["limits"] == ["限界の文"]


def test_api_broken_file_returns_user_message(client, tmp_path, monkeypatch):
    _, c = client
    bad = tmp_path / "result.json"
    bad.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(acc, "RESULT_PATH", bad)
    r = c.get("/api/docverify/accuracy")
    assert r.status_code == 500
    msg = r.get_json()["error"]
    assert msg == acc.MSG_BROKEN and not LEAK.search(msg)


def test_committed_result_matches_dataset():
    data = json.loads((ROOT / "quality/docverify_eval/result.json").read_text(encoding="utf-8"))
    assert data["dataset"]["n"] == len(ev.load_dataset(ev.DEFAULT_DATASET))
    assert data["dataset"]["sha256"] == ev._sha([ev.DEFAULT_DATASET])


def test_partial_has_dom_contract(client):
    app, _ = client
    with app.app_context():
        html = app.jinja_env.get_template("docverify/_r5.html").render()
    for i in ("dvAccMeta", "dvAccTable", "dvAccMethods", "dvAccLimits", "dvAccReload"):
        assert f'id="{i}"' in html
    assert 'data-view="accuracy"' in html
