"""履歴の集計が対検査（pair）系を取り込むこと。実行は保守者の要求時のみ。"""
from web.services.docverify import metrics


def _pair(n_total, n_fixed):
    fs = [{"id": f"F-{i:03d}", "status": "解消済み" if i < n_fixed else "要確認", "severity": "重大" if i == n_fixed else "警告"}
          for i in range(n_total)]
    return {"id": "r-test000001", "name": "テスト", "inspection_id": None, "findings": fs, "updated_at": "2026-10-24T00:00:00+00:00"}


def test_pair_findings_are_counted():
    m = metrics.overall([], pair_reviews=[_pair(15, 3)])
    assert m["findings"] == 15
    assert m["fixed"] == 3
    assert m["fix_rate"] == 0.2
    assert m["unresolved_critical"] == 1
    assert "density" not in m and "density" not in m["by_review"][0]
    assert m["by_review"][0]["updated_at"]


def test_no_findings_gives_none_not_zero():
    m = metrics.overall([], pair_reviews=[_pair(0, 0)])
    assert m["fix_rate"] is None
    assert m["by_review"][0]["fix_rate"] is None
