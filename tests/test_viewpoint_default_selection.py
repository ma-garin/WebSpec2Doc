"""生成した観点セットが、通常のQA生成経路で選ばれることを検証する。

観点はこの製品のエンジンである。だが `select_snapshot` が引数なしで呼ばれたとき、
選ばれるのは「適用ルールに一致するセット」か「is_default=1 のセット」だけで、
生成したセットはどちらでもなかった。

既存の到達テスト（test_generated_viewpoints_reach_qa.py）は
`use_viewpoint_snapshot()` という手動オーバーライド経路でしか確認していない。
そのため「観点が届く」ことを2度報告しながら、通常経路では一度も届いていなかった。
ここでは自動選択の経路そのものを通す。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from web.services.viewpoint_store import ViewpointStore
from web.services.viewpoint_templates import create_set_from_template


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ViewpointStore:
    seed = tmp_path / "seed.csv"
    seed.write_text("summary_type,name,count\ncategory_l2,既定観点,1\n", encoding="utf-8")
    result = ViewpointStore(tmp_path / "viewpoints.db", seed)
    result.initialize()
    monkeypatch.setattr("web.services.viewpoint_templates.get_viewpoint_store", lambda: result)
    return result


class TestGeneratedSetIsSelectable:
    def test_generated_set_can_become_the_default(self, store: ViewpointStore) -> None:
        """生成セットを既定にすると、自動選択でそれが選ばれること。

        既定を切り替える手段が無いと、生成した観点は倉庫に積まれるだけで
        一度も使われない。
        """
        created = create_set_from_template("domain-01")
        store.update_set(
            created["set"]["id"],
            {"is_default": True, "revision": created["set"]["revision"]},
        )

        snapshot = store.select_snapshot({"url": "https://example.com"})

        assert snapshot["set_id"] == created["set"]["id"]
        assert snapshot["viewpoint_count"] == created["created_items"]

    def test_only_one_set_stays_default(self, store: ViewpointStore) -> None:
        """既定は常に1つだけであること。

        複数が既定になると、どれが使われるか優先度順の偶然で決まり、
        実行ごとに観点が変わりうる。
        """
        created = create_set_from_template("domain-01")
        store.update_set(
            created["set"]["id"],
            {"is_default": True, "revision": created["set"]["revision"]},
        )

        defaults = [s for s in store.list_sets() if s["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == created["set"]["id"]

    def test_assignment_rule_selects_generated_set(self, store: ViewpointStore) -> None:
        """適用ルールでも生成セットが選ばれること。

        既定は1つしか置けないため、対象サイトごとに使い分けるにはルールが要る。
        """
        created = create_set_from_template("domain-01")
        store.create_assignment(
            created["set"]["id"],
            {
                "rule": {
                    "condition": {
                        "field": "url",
                        "operator": "contains",
                        "value": "bank.example",
                    }
                },
                "priority": 10,
            },
        )

        snapshot = store.select_snapshot({"url": "https://bank.example/login"})

        assert snapshot["set_id"] == created["set"]["id"]
        assert "適用ルール" in snapshot["selection_reason"]

    def test_selected_snapshot_carries_expected_result_and_evidence(
        self, store: ViewpointStore
    ) -> None:
        """自動選択で得た観点が、期待結果と証跡を持つこと。

        選ばれても中身が空なら、テスト設計には使えない。
        既定セット（CSV移行）は summary_type/name/count の3列しか持たず、
        これらの列は常に空である。生成セットが選ばれて初めて中身が入る。
        """
        created = create_set_from_template("domain-01")
        store.update_set(
            created["set"]["id"],
            {"is_default": True, "revision": created["set"]["revision"]},
        )

        items = store.select_snapshot({"url": "https://example.com"})["items"]

        assert items
        assert all(item["expected_result"].strip() for item in items)
        assert all(item["evidence"].strip() for item in items)
        assert all(item["technique"].strip() for item in items)
