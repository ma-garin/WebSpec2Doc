"""商用品質の精度評価器（scripts/commercial_eval/）の採点ロジック。"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "commercial_eval"))

import evidence_eval  # noqa: E402
import routes_eval  # noqa: E402
import viewpoints_eval  # noqa: E402
from common import norm_path, prf  # noqa: E402


def test_prf_handles_empty_prediction():
    assert prf(0, 0, 3) == {"precision": None, "recall": 0.0, "f1": None, "tp": 0, "fp": 0, "fn": 3}
    assert prf(2, 2, 0)["precision"] == 0.5


def test_norm_path_unifies_dynamic_segments():
    assert norm_path("/products/:id/") == "/products/:param"
    assert norm_path("/api/items/${itemId}?q=1") == "/api/items/:param"
    assert norm_path("/orders/42") == "/orders/:param"


def test_routes_eval_counts_traps_and_misses():
    expected = {"cases": [
        {"kind": "route", "path": "/a", "should_detect": True},
        {"kind": "api", "path": "/api/x/:id", "should_detect": True},
        {"kind": "api", "path": "/api/legacy", "should_detect": False},
    ]}
    report = {"static_candidates": [{"kind": "api", "path": None, "expression": "`/api/x/${id}`"},
                                    {"kind": "api", "path": "/api/legacy"}, {"kind": "api", "path": None}]}
    out = routes_eval.evaluate(report, expected)
    assert out["all"]["tp"] == 1 and out["all"]["fp"] == 1 and out["all"]["fn"] == 1
    assert out["trap_hits"] == ["/api/legacy"]
    assert out["candidates_without_value"] == 1


def test_evidence_eval_counts_duplicates_and_hidden_text():
    expected = {"pages": {"p1.html": {"title": "T", "headings": ["見出し"], "buttons": ["削除", "削除"],
                                      "fields": [], "links": [], "must_not_appear": ["秘密"]}}}
    report = {"screens": [{"page_id": "P1", "url": "http://x/p1.html", "title": "T", "headings": ["見出し", "秘密"],
                           "buttons": ["削除"], "forms": [], "transitions": {"to": []}}]}
    out = evidence_eval.evaluate(report, expected)
    assert (out["all"]["tp"], out["all"]["fp"], out["all"]["fn"]) == (3, 1, 1)
    assert out["hidden_or_forbidden_extracted"] == ["p1.html: 秘密"]


def test_viewpoint_categories_from_technique_and_name():
    cats = viewpoints_eval.categories({"technique": "境界値分析", "name": "氏名: 上限超過（31文字）"})
    assert {"boundary", "abnormal"} <= cats
    assert viewpoints_eval.categories({"technique": "状態遷移テスト", "name": "申請中→承認済み"}) >= {"state_transition"}
    assert Counter(viewpoints_eval.categories({"technique": "画面遷移", "name": "一覧から詳細へ"})) == Counter()
