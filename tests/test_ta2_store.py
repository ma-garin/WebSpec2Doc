"""TA2（テスト自動化 System 02）の永続化・導出ロジックのテスト。

実データ（`docs/demo/sample_output/report.json`）を種に、契約 `docs/plan/ta2-contract.md`
の §2.1 導出・§2.2 要素辞書・§3.1 実行結果反映・§4 穴と生成 を機械的に検証する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
import web.routes.qa_process as qa_mod
from web.services import ta2_store as store
from web.services.testcase_spec_generator import generate_spec

DOMAIN = "ta2-demo.example.com"
DEMO_REPORT = (
    Path(__file__).resolve().parent.parent / "docs" / "demo" / "sample_output" / "report.json"
)

# フォームを持つ画面（demo report の実データ。ここが導出の最低ライン）
FORM_SCREENS = ("P003", "P004", "P005")


def _report() -> dict:
    return json.loads(DEMO_REPORT.read_text(encoding="utf-8"))


@pytest.fixture()
def output_dir(tmp_path: Path, monkeypatch) -> Path:
    """出力先を tmp_path に固定し、report.json を実データで置く。"""
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / DOMAIN
    domain_dir.mkdir(parents=True, exist_ok=True)
    (domain_dir / "report.json").write_text(
        json.dumps(_report(), ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


# =========================================================================
# §2.1 初期導出
# =========================================================================
class TestDeriveInitial:
    def test_creates_tests_for_every_screen_with_forms(self, output_dir: Path) -> None:
        data = store.derive_initial(DOMAIN, _report())
        assert data["version"] == store.VERSION
        assert data["domain"] == DOMAIN
        assert len(data["tests"]) > 0
        screens = {t["screen"] for t in data["tests"]}
        for page_id in FORM_SCREENS:
            assert page_id in screens, f"{page_id} のテストが導出されていない"

    def test_ids_are_unique_and_formatted(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        ids = [t["id"] for t in tests]
        assert len(ids) == len(set(ids))
        assert all(t["id"].startswith("PW-") and len(t["id"]) == 7 for t in tests)

    def test_every_test_has_contract_fields(self, output_dir: Path) -> None:
        for test in store.derive_initial(DOMAIN, _report())["tests"]:
            assert set(test) >= {
                "id",
                "case_id",
                "screen",
                "name",
                "technique",
                "source",
                "steps",
                "status",
                "history",
                "last",
                "updated_at",
            }
            assert test["status"] == "new"
            assert test["source"] == "table"
            assert test["case_id"].startswith("TC-")

    def test_steps_use_only_the_contract_vocabulary(self, output_dir: Path) -> None:
        for test in store.derive_initial(DOMAIN, _report())["tests"]:
            for step in test["steps"]:
                assert step["action"] in store.ACTION_VOCABULARY, step
                assert step["kind"] in {"pre", "act", "ver"}

    def test_first_step_opens_a_concrete_url(self, output_dir: Path) -> None:
        for test in store.derive_initial(DOMAIN, _report())["tests"]:
            if not test["steps"]:
                continue
            first = test["steps"][0]
            assert first["action"] == store.ACT_OPEN
            assert first["arg"].startswith("http")

    def test_load_returns_empty_before_derivation(self, output_dir: Path) -> None:
        assert store.load(DOMAIN) == {}
        store.derive_initial(DOMAIN, _report())
        assert store.load(DOMAIN)["tests"]
        assert store.tests_path(DOMAIN).is_file()

    def test_save_is_atomic_and_leaves_no_tmp(self, output_dir: Path) -> None:
        store.derive_initial(DOMAIN, _report())
        assert list(store.base_dir(DOMAIN).glob("*.tmp")) == []


# =========================================================================
# §2.2 要素辞書
# =========================================================================
class TestElements:
    def test_fields_buttons_hero_and_alert(self, output_dir: Path) -> None:
        elements = store.elements_of(_report())
        checkout = elements["P004"]
        assert checkout["card_number"]["loc"] == "#card-number"
        assert checkout["card_number"]["stab"] == "high"
        assert checkout["card_number"]["label"] == "card_number"  # placeholder を名前にしない
        assert checkout["card_number"]["placeholder"] == "1111 2222 3333 4444"
        assert checkout["btn_0"]["loc"] == "text=この内容で支払う"
        assert checkout["btn_0"]["stab"] == "mid"
        assert checkout["hero"]["loc"] == "h1"
        assert checkout["alert"]["loc"] == '[role="alert"]'

    def test_alert_exists_on_every_screen(self, output_dir: Path) -> None:
        for page_id, elements in store.elements_of(_report()).items():
            assert "alert" in elements, page_id

    def test_screens_of_returns_id_name_path(self, output_dir: Path) -> None:
        screens = store.screens_of(_report())
        p004 = next(s for s in screens if s["id"] == "P004")
        assert p004["path"] == "/checkout.html"
        assert p004["name"] == "DemoMart - お支払い・決済"

    @pytest.mark.parametrize(
        ("locator", "expected"),
        [
            ('[data-testid="place-order"]', "high"),
            ("#card-number", "high"),
            ('[role="alert"]', "high"),
            ('input[name="q"]', "mid"),
            ("text=送信する", "mid"),
            ("div > form > input:nth-child(3)", "low"),
            ("", "low"),
        ],
    )
    def test_locator_stability(self, locator: str, expected: str) -> None:
        assert store.locator_stability(locator) == expected


# =========================================================================
# §3.1 spec 生成への往復
# =========================================================================
class TestTableRoundTrip:
    def test_to_table_rows_generates_spec_without_error(
        self, output_dir: Path, tmp_path: Path
    ) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        rows, skipped = store.to_table_rows(tests)
        assert any(r["automation"] == "自動化可" for r in rows)
        assert skipped == []
        # 実行対象から黙って消えるテストがない（除外されるなら理由付きで返る）
        assert len(rows) + len(skipped) == len(tests)

        result = generate_spec(rows, tmp_path / "spec")
        assert result["test_count"] > 0
        spec = Path(result["spec_path"]).read_text(encoding="utf-8")
        assert "page.goto" in spec
        assert "未対応の操作のためスキップ" not in spec
        assert "未対応の検証のためスキップ" not in spec

    def test_row_case_id_is_the_test_id(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        rows, _ = store.to_table_rows(tests)
        assert rows[0]["case_id"] == tests[0]["id"]
        assert rows[0]["source_case_id"] == tests[0]["case_id"]

    def test_actions_survive_the_round_trip(self, output_dir: Path) -> None:
        from web.services.testcase_table_store import compose

        original = {r["case_id"]: r for r in compose(DOMAIN, _report())["rows"]}
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        for row in store.to_table_rows(tests)[0]:
            source = original[row["source_case_id"]]
            kept = [a for a in source["actions"] if a.get("type") != "wait_load"]
            assert [a["type"] for a in row["actions"]] == [a["type"] for a in kept]
            if row["implicit_assertion"]:
                # 検証手順が無い行にだけ「エラー表示なし」を補う
                assert not source["assertions"]
                assert row["assertions"] == [{"type": "expect_no_error"}]
            else:
                assert [a["type"] for a in row["assertions"]] == [
                    a["type"] for a in source["assertions"]
                ]


# =========================================================================
# §3.1 実行結果の反映
# =========================================================================
class TestApplyRunResult:
    def _seed(self) -> list[dict]:
        return store.derive_initial(DOMAIN, _report())["tests"]

    def test_pass_updates_status_history_and_last(self, output_dir: Path) -> None:
        tests = self._seed()
        target = tests[0]["id"]
        data = store.apply_run_result(
            DOMAIN,
            {"cases": {target: {"status": "passed", "duration_ms": 1234, "error": ""}}},
            run_id="run-1",
            at="2026-08-30T10:00:00",
        )
        updated = next(t for t in data["tests"] if t["id"] == target)
        assert updated["status"] == "pass"
        assert updated["history"] == [1]
        assert updated["last"]["dur_ms"] == 1234
        assert updated["last"]["run_id"] == "run-1"
        assert updated["last"]["at"] == "2026-08-30T10:00:00"
        assert updated["last"]["step"] is None

    def test_history_accumulates_and_is_capped(self, output_dir: Path) -> None:
        tests = self._seed()
        target = tests[0]["id"]
        for index in range(store.HISTORY_LIMIT + 3):
            status = "passed" if index % 2 == 0 else "failed"
            store.apply_run_result(DOMAIN, {"cases": {target: {"status": status}}}, "r", "t")
        updated = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == target)
        assert len(updated["history"]) == store.HISTORY_LIMIT
        assert updated["history"][-1] == 1  # 最後の実行は passed
        assert updated["history"][-2] == 0

    def test_failure_marks_step_and_adds_timeout_issue(self, output_dir: Path) -> None:
        tests = self._seed()
        target = next(t for t in tests if any(s.get("loc") == "#card-number" for s in t["steps"]))
        error = 'Timeout 15000ms exceeded.\nwaiting for locator("#card-number")'
        data = store.apply_run_result(
            DOMAIN, {"cases": {target["id"]: {"status": "failed", "error": error}}}
        )
        updated = next(t for t in data["tests"] if t["id"] == target["id"])
        assert updated["status"] == "fail"
        assert updated["history"] == [0]
        index = updated["last"]["step"]
        assert index is not None
        assert updated["steps"][index]["loc"] == "#card-number"
        assert updated["steps"][index]["issue"]["type"] == "missing"
        assert updated["steps"][index]["fixed"] is False

    def test_raw_playwright_result_is_accepted(self, output_dir: Path) -> None:
        tests = self._seed()
        target = tests[0]["id"]
        data = store.apply_run_result(
            DOMAIN,
            {"tests": [{"title": f"{target} なにか", "status": "passed", "duration_ms": 7}]},
        )
        assert next(t for t in data["tests"] if t["id"] == target)["status"] == "pass"

    def test_unknown_case_leaves_tests_untouched(self, output_dir: Path) -> None:
        self._seed()
        before = store.load(DOMAIN)["tests"]
        after = store.apply_run_result(DOMAIN, {"cases": {"PW-9999": {"status": "failed"}}})[
            "tests"
        ]
        assert [t["status"] for t in after] == [t["status"] for t in before]


# =========================================================================
# §2 issue.type ごとの修正
# =========================================================================
class TestApplyFix:
    def _with_issue(self, issue: dict, step_extra: dict | None = None) -> str:
        step = {
            "kind": "act",
            "action": store.ACT_CLICK,
            "target": "submit",
            "arg": "この内容で支払う",
            "loc": 'button[name="submit_order"]',
            "stab": "mid",
            "issue": issue,
            "fixed": False,
        }
        step.update(step_extra or {})
        store.save(
            DOMAIN,
            {
                "version": 1,
                "domain": DOMAIN,
                "next_seq": 2,
                "tests": [
                    {
                        "id": "PW-0001",
                        "case_id": "",
                        "screen": "P004",
                        "name": "修正の対象",
                        "technique": "生成",
                        "source": "manual",
                        "steps": [step],
                        "status": "fail",
                        "history": [0],
                        "last": {},
                        "updated_at": "",
                    }
                ],
            },
        )
        return "PW-0001"

    def test_missing_replaces_locator(self, output_dir: Path) -> None:
        test_id = self._with_issue(
            {
                "type": "missing",
                "msg": "要素が見つからない",
                "detail": "",
                "fix": '[data-testid="place-order"]',
                "fix_stab": "high",
                "key": "submit",
            }
        )
        test, reason = store.apply_fix(DOMAIN, test_id, 0)
        assert reason is None
        assert test["steps"][0]["loc"] == '[data-testid="place-order"]'
        assert test["steps"][0]["stab"] == "high"
        assert test["steps"][0]["fixed"] is True
        assert test["status"] == "fixed"

    def test_timeout_extends_wait(self, output_dir: Path) -> None:
        test_id = self._with_issue(
            {"type": "timeout", "msg": "", "detail": "", "fix": None, "key": "submit"}
        )
        test, reason = store.apply_fix(DOMAIN, test_id, 0)
        assert reason is None
        assert test["steps"][0]["wait_ms"] == store.DEFAULT_WAIT_MS * 2
        assert test["steps"][0]["fixed"] is True

    def test_timeout_wait_is_capped(self, output_dir: Path) -> None:
        test_id = self._with_issue(
            {"type": "timeout", "msg": "", "detail": "", "fix": None, "key": "submit"},
            {"wait_ms": store.MAX_WAIT_MS},
        )
        assert store.apply_fix(DOMAIN, test_id, 0)[0]["steps"][0]["wait_ms"] == store.MAX_WAIT_MS

    def test_expect_updates_arg(self, output_dir: Path) -> None:
        test_id = self._with_issue(
            {
                "type": "expect",
                "msg": "",
                "detail": "",
                "fix": "必須項目を入力してください",
                "key": "alert",
            }
        )
        assert (
            store.apply_fix(DOMAIN, test_id, 0)[0]["steps"][0]["arg"]
            == "必須項目を入力してください"
        )

    def test_flaky_replaces_locator_and_extends_wait(self, output_dir: Path) -> None:
        test_id = self._with_issue(
            {
                "type": "flaky",
                "msg": "",
                "detail": "",
                "fix": "#place-order",
                "fix_stab": "high",
                "key": "submit",
            }
        )
        step = store.apply_fix(DOMAIN, test_id, 0)[0]["steps"][0]
        assert step["loc"] == "#place-order"
        assert step["wait_ms"] == store.DEFAULT_WAIT_MS * 2

    def test_missing_without_fix_returns_reason_and_keeps_test(self, output_dir: Path) -> None:
        """修正案なしは正常系。例外にせず理由を返し、テストは変えない（B-2）。"""
        test_id = self._with_issue(
            {"type": "missing", "msg": "", "detail": "", "fix": None, "key": "submit"}
        )
        test, reason = store.apply_fix(DOMAIN, test_id, 0)
        assert reason == store.NO_FIX_MISSING_REASON
        assert test["status"] == "fail"
        assert test["steps"][0]["fixed"] is False
        assert store.load(DOMAIN)["tests"][0]["status"] == "fail"

    def test_expect_without_fix_returns_reason(self, output_dir: Path) -> None:
        test_id = self._with_issue(
            {"type": "expect", "msg": "", "detail": "", "fix": None, "key": "alert"}
        )
        _, reason = store.apply_fix(DOMAIN, test_id, 0)
        assert reason == store.NO_FIX_EXPECT_REASON

    def test_unknown_issue_type_returns_reason(self, output_dir: Path) -> None:
        test_id = self._with_issue({"type": "なにか", "fix": None})
        _, reason = store.apply_fix(DOMAIN, test_id, 0)
        assert reason and "未知の問題の種類" in reason

    def test_step_without_issue_returns_reason(self, output_dir: Path) -> None:
        store.derive_initial(DOMAIN, _report())
        first = store.load(DOMAIN)["tests"][0]
        test, reason = store.apply_fix(DOMAIN, first["id"], 0)
        assert reason == store.NO_ISSUE_REASON
        assert test["id"] == first["id"]

    def test_unknown_test_is_rejected(self, output_dir: Path) -> None:
        store.derive_initial(DOMAIN, _report())
        with pytest.raises(store.Ta2StoreError):
            store.apply_fix(DOMAIN, "PW-9999", 0)

    def test_out_of_range_step_is_rejected(self, output_dir: Path) -> None:
        test_id = self._with_issue({"type": "timeout", "fix": None})
        for bad in (5, -1, "x"):
            with pytest.raises(store.Ta2StoreError):
                store.apply_fix(DOMAIN, test_id, bad)  # type: ignore[arg-type]


# =========================================================================
# §4 穴と生成
# =========================================================================
class TestGaps:
    def test_gaps_exclude_conditions_already_covered(self, output_dir: Path) -> None:
        """同じ項目でも「未入力」と「値を入れる」は別の条件として数える（B-8）。"""
        report = _report()
        tests = store.derive_initial(DOMAIN, report)["tests"]
        gaps = store.gaps_of(DOMAIN, report, tests)
        covered = {
            (t["screen"], s.get("target"), store._MODE_BY_ACTION.get(s.get("action")))
            for t in tests
            for s in t["steps"]
            if s.get("kind") == "act"
        }
        for gap in gaps:
            if gap["kind"] != "condition":
                continue
            mode = store.condition_mode(gap["title"].split(": ", 1)[-1])
            assert (gap["screen"], gap["field"], mode) not in covered, gap["id"]

    def test_real_data_has_at_least_one_gap(self, output_dir: Path) -> None:
        """導出直後でも穴はゼロにならない（100% 網羅は常に真の指標になり得ない）。"""
        report = _report()
        tests = store.derive_initial(DOMAIN, report)["tests"]
        gaps = store.gaps_of(DOMAIN, report, tests)
        assert gaps, "実データで穴が 0 件になっている"
        assert {g["kind"] for g in gaps} <= {"condition", "transition", "button"}

    def test_button_gap_is_detected_and_closed(self, output_dir: Path) -> None:
        report = _report()
        gaps = store.gaps_of(DOMAIN, report, [])
        button = next(g for g in gaps if g["kind"] == "button")
        assert button["id"].split(":")[1] == "button"
        assert [s["action"] for s in button["steps"]][:2] == [store.ACT_OPEN, store.ACT_CLICK]
        store.generate_from_gaps(DOMAIN, report, button["screen"], [button["id"]])
        assert button["id"] not in {g["id"] for g in store.gaps_of(DOMAIN, report)}

    def test_gaps_appear_when_no_tests_exist(self, output_dir: Path) -> None:
        gaps = store.gaps_of(DOMAIN, _report(), [])
        ids = {g["id"] for g in gaps}
        assert "P004:card_number:0" in ids
        conditions = [g for g in gaps if g["kind"] == "condition"]
        assert conditions and all(g["title"] and g["detail"] and g["steps"] for g in conditions)

    def test_gap_id_format(self, output_dir: Path) -> None:
        for gap in store.gaps_of(DOMAIN, _report(), []):
            assert gap["id"].count(":") == 2

    def test_gap_steps_follow_the_contract_shape(self, output_dir: Path) -> None:
        gap = next(
            g for g in store.gaps_of(DOMAIN, _report(), []) if g["id"] == "P004:card_number:0"
        )
        actions = [s["action"] for s in gap["steps"]]
        assert actions[0] == store.ACT_OPEN
        assert store.ACT_CLICK in actions
        assert actions[-1] == store.ACT_SHOWN
        assert gap["steps"][1]["action"] == store.ACT_CLEAR  # 「未入力で送信」の条件

    def test_transition_gap_is_detected(self, output_dir: Path) -> None:
        gaps = store.gaps_of(DOMAIN, _report(), [])
        assert any(g["kind"] == "transition" for g in gaps)

    def test_generate_from_gaps_creates_tests(self, output_dir: Path) -> None:
        report = _report()
        # tests.json が空の状態＝すべての条件が穴。generate 側と同じ数え方になる
        gap = next(g for g in store.gaps_of(DOMAIN, report) if g["kind"] == "condition")
        created = store.generate_from_gaps(DOMAIN, report, gap["screen"], [gap["id"]])
        assert len(created) == 1
        assert created[0]["source"] == "gap"
        assert created[0]["status"] == "new"
        assert created[0]["steps"] == gap["steps"]
        assert created[0]["id"] in {t["id"] for t in store.load(DOMAIN)["tests"]}

    def test_generated_test_closes_the_gap(self, output_dir: Path) -> None:
        report = _report()
        gap = next(g for g in store.gaps_of(DOMAIN, report) if g["kind"] == "condition")
        store.generate_from_gaps(DOMAIN, report, gap["screen"], [gap["id"]])
        assert gap["id"] not in {g["id"] for g in store.gaps_of(DOMAIN, report)}

    def test_generate_manual_test_from_name(self, output_dir: Path) -> None:
        report = _report()
        store.derive_initial(DOMAIN, report)
        created = store.generate_from_gaps(DOMAIN, report, "P005", None, "手で足したテスト")
        assert created[0]["source"] == "manual"
        assert created[0]["name"] == "手で足したテスト"
        assert len(created[0]["steps"]) == 1
        assert created[0]["steps"][0]["arg"] == "http://127.0.0.1:8766/contact.html"

    def test_generate_rejects_empty_name_and_unknown_gap(self, output_dir: Path) -> None:
        report = _report()
        with pytest.raises(store.Ta2StoreError):
            store.generate_from_gaps(DOMAIN, report, "P005", None, "  ")
        with pytest.raises(store.Ta2StoreError):
            store.generate_from_gaps(DOMAIN, report, "P005", ["no:such:0"])


# =========================================================================
# §3 変更検知（drift）
# =========================================================================
def _snapshot(base: Path, stamp: str, element_id: str, buttons: list[str]) -> None:
    snaps = base / DOMAIN / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    page = {
        "url": "http://127.0.0.1:8766/contact.html",
        "title": "DemoMart - お問い合わせ",
        "headings": ["お問い合わせ"],
        "links": [],
        "buttons": buttons,
        "screenshot_path": None,
        "forms": [
            {
                "action": "/contact/send",
                "method": "post",
                "fields": [
                    {
                        "field_type": "text",
                        "name": "name",
                        "placeholder": "山田 太郎",
                        "required": True,
                        "element_id": element_id,
                    }
                ],
            }
        ],
    }
    (snaps / f"{stamp}.json").write_text(json.dumps([page], ensure_ascii=False), encoding="utf-8")


class TestDrift:
    def test_no_snapshot_returns_reason(self, output_dir: Path) -> None:
        result = store.drift_items(DOMAIN)
        assert result["items"] == []
        assert result["reason"] == store.NO_BASELINE_REASON

    def test_single_snapshot_returns_reason(self, output_dir: Path) -> None:
        _snapshot(output_dir, "20260801-100000", "name", ["送信する"])
        result = store.drift_items(DOMAIN)
        assert result["items"] == []
        assert result["reason"] == store.NO_BASELINE_REASON

    def test_locator_change_is_detected_and_applied(self, output_dir: Path) -> None:
        report = _report()
        store.derive_initial(DOMAIN, report)
        _snapshot(output_dir, "20260801-100000", "name", ["送信する"])
        _snapshot(output_dir, "20260802-100000", "name-v2", ["送信する"])

        result = store.drift_items(DOMAIN)
        assert "reason" not in result
        assert result["baseline_at"] == "2026-08-01T10:00:00"
        item = next(i for i in result["items"] if i["kind"] == "locator")
        assert item["old"] == "#name"
        assert item["now"] == "#name-v2"
        assert item["state"] == "open"
        assert item["impact"], "影響テストが特定できていない"
        assert item["fix"]["stab"] == "high"

        applied = store.drift_apply(DOMAIN, item["id"])
        assert applied["applied"] == item["impact"]
        touched = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == applied["applied"][0])
        assert touched["status"] == "fixed"
        assert any(s["loc"] == "#name-v2" for s in touched["steps"])
        assert all(s["loc"] != "#name" for s in touched["steps"])
        assert store.drift_items(DOMAIN)["items"][0]["state"] in {"applied", "open"}

    def test_button_text_change_is_detected(self, output_dir: Path) -> None:
        _snapshot(output_dir, "20260801-100000", "name", ["送信する"])
        _snapshot(output_dir, "20260802-100000", "name", ["送信"])
        item = next(i for i in store.drift_items(DOMAIN)["items"] if i["kind"] == "text")
        assert item["old"] == "text=送信する"
        assert item["now"] == "text=送信"

    def test_dismiss_is_persisted(self, output_dir: Path) -> None:
        _snapshot(output_dir, "20260801-100000", "name", ["送信する"])
        _snapshot(output_dir, "20260802-100000", "name-v2", ["送信する"])
        item_id = store.drift_items(DOMAIN)["items"][0]["id"]
        assert store.drift_dismiss(DOMAIN, item_id) == {"ok": True}
        assert store.drift_path(DOMAIN).is_file()
        again = next(i for i in store.drift_items(DOMAIN)["items"] if i["id"] == item_id)
        assert again["state"] == "dismissed"

    def test_apply_unknown_item_is_rejected(self, output_dir: Path) -> None:
        _snapshot(output_dir, "20260801-100000", "name", ["送信する"])
        _snapshot(output_dir, "20260802-100000", "name-v2", ["送信する"])
        with pytest.raises(store.Ta2StoreError):
            store.drift_apply(DOMAIN, "no-such-item")


# =========================================================================
# §3 テスト単体の操作
# =========================================================================
class TestCrud:
    def test_duplicate_creates_a_fresh_copy(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        source = next(t for t in tests if t["steps"])
        copied = store.duplicate(DOMAIN, source["id"])
        assert copied["id"] != source["id"]
        assert copied["name"].endswith("（複製）")
        assert copied["steps"] == source["steps"]
        assert copied["status"] == "new"
        assert copied["history"] == []
        assert len(store.load(DOMAIN)["tests"]) == len(tests) + 1

    def test_duplicate_does_not_mutate_the_source(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        source = dict(tests[0])
        store.duplicate(DOMAIN, source["id"])
        after = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == source["id"])
        assert after == source

    def test_update_renames_and_marks_fixed(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        target = tests[0]["id"]
        store.apply_run_result(DOMAIN, {"cases": {target: {"status": "failed", "error": "x"}}})
        updated = store.update_test(DOMAIN, target, {"name": "名前を直した"})
        assert updated["name"] == "名前を直した"
        assert updated["status"] == "fixed"

    def test_update_keeps_new_status(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        updated = store.update_test(DOMAIN, tests[0]["id"], {"name": "x"})
        assert updated["status"] == "new"

    def test_update_steps_validates_the_vocabulary(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        test_id = tests[0]["id"]
        good = [
            {
                "kind": "pre",
                "action": store.ACT_OPEN,
                "target": "page",
                "arg": "http://x/",
                "loc": "page.goto",
            }
        ]
        assert len(store.update_test(DOMAIN, test_id, {"steps": good})["steps"]) == 1
        with pytest.raises(store.Ta2StoreError):
            store.update_test(DOMAIN, test_id, {"steps": [{"action": "クリックする"}]})
        with pytest.raises(store.Ta2StoreError):
            store.update_test(DOMAIN, test_id, {"steps": "文字列"})

    def test_delete_removes_only_the_target(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        target = tests[0]["id"]
        assert store.delete_test(DOMAIN, target)["ok"] is True
        remaining = store.load(DOMAIN)["tests"]
        assert len(remaining) == len(tests) - 1
        assert all(t["id"] != target for t in remaining)
        with pytest.raises(store.Ta2StoreError):
            store.delete_test(DOMAIN, target)


# =========================================================================
# 実行対象の除外・編集したロケータ・失敗ステップ（B-3 / B-5 / B-6）
# =========================================================================
def _manual_test(steps: list[dict], test_id: str = "PW-0001") -> dict:
    return {
        "id": test_id,
        "case_id": "",
        "screen": "P004",
        "name": "手で作ったテスト",
        "technique": "手動",
        "source": "manual",
        "steps": steps,
        "status": "new",
        "history": [],
        "last": {},
        "updated_at": "",
    }


def _seed(tests: list[dict]) -> None:
    store.save(DOMAIN, {"version": 1, "domain": DOMAIN, "next_seq": 9, "tests": tests})


class TestSkippedAndImplicitAssertion:
    def test_test_without_actions_is_reported_not_dropped(self, output_dir: Path) -> None:
        tests = [_manual_test([])]
        rows, skipped = store.to_table_rows(tests)
        assert rows == []
        assert skipped == [
            {"id": "PW-0001", "name": "手で作ったテスト", "reason": store.NO_ACTION_REASON}
        ]

    def test_test_without_verification_gets_implicit_assertion(
        self, output_dir: Path, tmp_path: Path
    ) -> None:
        tests = [
            _manual_test(
                [
                    {
                        "kind": "pre",
                        "action": store.ACT_OPEN,
                        "target": "page",
                        "arg": "http://127.0.0.1:8766/checkout.html",
                        "loc": "page.goto",
                        "op": "goto",
                    },
                    {
                        "kind": "act",
                        "action": store.ACT_FILL,
                        "target": "cvc",
                        "arg": "123",
                        "loc": "#cvc",
                        "op": "fill",
                    },
                ]
            )
        ]
        rows, skipped = store.to_table_rows(tests)
        assert skipped == []
        assert rows[0]["implicit_assertion"] is True
        assert rows[0]["assertions"] == [{"type": "expect_no_error"}]
        assert rows[0]["automation"] == "自動化可"
        result = generate_spec(rows, tmp_path / "spec-implicit")
        assert result["test_count"] == 1
        assert result["skipped_count"] == 0

    def test_table_rows_only_is_backward_compatible(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        assert store.table_rows_only(tests) == store.to_table_rows(tests)[0]


class TestEditedLocatorRuns:
    def _click_step(self, loc: str, op: str = "click_text", **extra) -> dict:
        step = {
            "kind": "act",
            "action": store.ACT_CLICK,
            "target": "submit",
            "arg": "この内容で支払う",
            "loc": loc,
            "op": op,
        }
        step.update(extra)
        return step

    def test_default_locator_keeps_label_click(self, output_dir: Path) -> None:
        action = store._step_to_action(self._click_step("text=この内容で支払う"))
        assert action == {"type": "click_text", "text": "この内容で支払う"}

    def test_default_locator_keeps_link_click(self, output_dir: Path) -> None:
        step = self._click_step(
            "text=この内容で支払う", op="click_link_to", href="/products.html"
        )
        action = store._step_to_action(step)
        assert action["type"] == "click_link_to"
        assert action["url"] == "/products.html"

    def test_edited_locator_wins_for_label_click(self, output_dir: Path) -> None:
        action = store._step_to_action(self._click_step('button[name="submit_order"]'))
        assert action == {
            "type": "click",
            "locator": 'button[name="submit_order"]',
            "text": "この内容で支払う",
        }

    def test_edited_locator_wins_for_link_click(self, output_dir: Path) -> None:
        step = self._click_step(
            '[data-testid="go-products"]', op="click_link_to", href="/products.html"
        )
        assert store._step_to_action(step)["locator"] == '[data-testid="go-products"]'

    def test_edited_locator_reaches_the_generated_spec(
        self, output_dir: Path, tmp_path: Path
    ) -> None:
        tests = [
            _manual_test(
                [
                    {
                        "kind": "pre",
                        "action": store.ACT_OPEN,
                        "target": "page",
                        "arg": "http://127.0.0.1:8766/checkout.html",
                        "loc": "page.goto",
                        "op": "goto",
                    },
                    self._click_step('button[name="submit_order"]'),
                    {
                        "kind": "ver",
                        "action": store.ACT_SHOWN,
                        "target": "alert",
                        "arg": "エラー表示なし",
                        "loc": '[role="alert"]',
                        "check": "expect_no_error",
                    },
                ]
            )
        ]
        rows, _ = store.to_table_rows(tests)
        spec = Path(generate_spec(rows, tmp_path / "spec-loc")["spec_path"]).read_text(
            encoding="utf-8"
        )
        assert "await page.locator(" in spec
        assert "submit_order" in spec
        assert "未対応の操作のためスキップ" not in spec
        # テスト本体はラベル一致に落ちない（編集したロケータがそのまま走る）
        assert "clickByLabel(page," not in spec.split("test(")[-1]


class TestFailedStepIndex:
    def test_label_click_failure_sets_last_step(self, output_dir: Path) -> None:
        """ラベル一致クリックの失敗でも last.step が赤いステップを指す（B-6）。"""
        steps = [
            {
                "kind": "pre",
                "action": store.ACT_OPEN,
                "target": "page",
                "arg": "http://127.0.0.1:8766/checkout.html",
                "loc": "page.goto",
                "op": "goto",
            },
            {
                "kind": "act",
                "action": store.ACT_CLICK,
                "target": "btn_x",
                "arg": "存在しないボタン",
                "loc": "text=存在しないボタン",
                "op": "click_text",
            },
        ]
        _seed([_manual_test(steps)])
        error = "Timeout 15000ms exceeded.\nwaiting for getByText('存在しないボタン')"
        data = store.apply_run_result(
            DOMAIN, {"cases": {"PW-0001": {"status": "failed", "error": error}}}
        )
        updated = data["tests"][0]
        assert updated["last"]["step"] == 1
        assert updated["steps"][1]["issue"]["type"] == "missing"

    def test_last_step_matches_the_issue_step(self, output_dir: Path) -> None:
        """error からステップを特定できない失敗でも issue と last.step は同じ場所を指す。"""
        steps = [
            {
                "kind": "pre",
                "action": store.ACT_OPEN,
                "target": "page",
                "arg": "http://127.0.0.1:8766/checkout.html",
                "loc": "page.goto",
                "op": "goto",
            },
            {
                "kind": "act",
                "action": store.ACT_FILL,
                "target": "cvc",
                "arg": "123",
                "loc": "#cvc",
                "op": "fill",
            },
        ]
        _seed([_manual_test(steps)])
        data = store.apply_run_result(
            DOMAIN,
            {"cases": {"PW-0001": {"status": "failed", "error": "Timeout 5000ms exceeded."}}},
        )
        updated = data["tests"][0]
        index = updated["last"]["step"]
        assert index == 1
        assert updated["steps"][index]["issue"]["type"] == "timeout"

    def test_unmatched_failure_leaves_step_null(self, output_dir: Path) -> None:
        """判定材料が無ければ推測しない（step は null のまま）。"""
        steps = [
            {
                "kind": "pre",
                "action": store.ACT_OPEN,
                "target": "page",
                "arg": "http://127.0.0.1:8766/checkout.html",
                "loc": "page.goto",
                "op": "goto",
            }
        ]
        _seed([_manual_test(steps)])
        data = store.apply_run_result(
            DOMAIN, {"cases": {"PW-0001": {"status": "failed", "error": "unknown failure"}}}
        )
        assert data["tests"][0]["last"]["step"] is None


# =========================================================================
# B5 再同期（表の変更を取り込む）
# =========================================================================
class TestResync:
    def _seed(self) -> dict:
        return store.derive_initial(DOMAIN, _report())

    def _table(self):
        from web.services import testcase_table_store as tstore

        return tstore

    def test_unchanged_table_reports_only_kept(self, output_dir: Path) -> None:
        seeded = self._seed()
        out = store.resync(DOMAIN, _report())
        assert out["added"] == []
        assert out["renamed"] == []
        assert out["orphaned"] == []
        assert out["kept"] == len(seeded["tests"])

    def test_is_idempotent(self, output_dir: Path) -> None:
        self._seed()
        store.resync(DOMAIN, _report())
        first = json.dumps(store.load(DOMAIN), ensure_ascii=False, sort_keys=True)
        second_result = store.resync(DOMAIN, _report())
        assert second_result["added"] == []
        assert second_result["renamed"] == []
        assert json.dumps(store.load(DOMAIN), ensure_ascii=False, sort_keys=True) == first

    def test_new_row_is_added_and_run_history_is_kept(self, output_dir: Path) -> None:
        seeded = self._seed()
        target = seeded["tests"][0]["id"]
        store.apply_run_result(DOMAIN, {"cases": {target: {"status": "passed"}}}, "r1", "t1")
        added_row = self._table().add_row(DOMAIN, _report())

        out = store.resync(DOMAIN, _report())

        assert len(out["added"]) == 1
        created = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == out["added"][0])
        assert created["case_id"] == added_row["row"]["case_id"]
        assert created["source"] == "table"
        assert created["status"] == "new"
        kept = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == target)
        assert kept["history"] == [1]
        assert kept["last"]["run_id"] == "r1"

    def test_table_rename_updates_the_test_name(self, output_dir: Path) -> None:
        seeded = self._seed()
        target = next(t for t in seeded["tests"] if t["case_id"])
        self._table().update_cell(DOMAIN, _report(), target["case_id"], "name", "表で直した名前")

        out = store.resync(DOMAIN, _report())

        assert target["id"] in out["renamed"]
        updated = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == target["id"])
        assert updated["name"] == "表で直した名前"
        assert updated["steps"] == target["steps"]

    def test_user_renamed_test_is_not_overwritten(self, output_dir: Path) -> None:
        seeded = self._seed()
        target = next(t for t in seeded["tests"] if t["case_id"])
        store.update_test(DOMAIN, target["id"], {"name": "私がつけた名前"})
        self._table().update_cell(DOMAIN, _report(), target["case_id"], "name", "表で直した名前")

        out = store.resync(DOMAIN, _report())

        assert target["id"] not in out["renamed"]
        updated = next(t for t in store.load(DOMAIN)["tests"] if t["id"] == target["id"])
        assert updated["name"] == "私がつけた名前"
        assert updated["name_edited"] is True

    def test_row_removed_from_table_is_marked_orphan_not_deleted(self, output_dir: Path) -> None:
        seeded = self._seed()
        target = next(t for t in seeded["tests"] if t["case_id"])
        self._table().delete_row(DOMAIN, target["case_id"])

        out = store.resync(DOMAIN, _report())

        assert target["id"] in out["orphaned"]
        tests = store.load(DOMAIN)["tests"]
        assert len(tests) == len(seeded["tests"])  # 削除しない
        assert next(t for t in tests if t["id"] == target["id"])["orphan"] is True

    def test_restored_row_clears_the_orphan_mark(self, output_dir: Path) -> None:
        seeded = self._seed()
        target = next(t for t in seeded["tests"] if t["case_id"])
        self._table().delete_row(DOMAIN, target["case_id"])
        store.resync(DOMAIN, _report())
        self._table().restore_row(DOMAIN, target["case_id"])

        out = store.resync(DOMAIN, _report())

        assert target["id"] not in out["orphaned"]
        assert "orphan" not in next(
            t for t in store.load(DOMAIN)["tests"] if t["id"] == target["id"]
        )


# =========================================================================
# B6 失敗ステップの確実な特定
# =========================================================================
class TestFailedStepFromReporter:
    def test_reporter_step_title_wins(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        target = next(t for t in tests if len(t["steps"]) > 3)
        data = store.apply_run_result(
            DOMAIN,
            {
                "cases": {
                    target["id"]: {
                        "status": "failed",
                        "error": "Error: なにかが起きた",
                        "failed_step": "S3",
                    }
                }
            },
        )
        assert next(t for t in data["tests"] if t["id"] == target["id"])["last"]["step"] == 3

    def test_out_of_range_step_falls_back(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        target = next(t for t in tests if any(s.get("loc") == "#card-number" for s in t["steps"]))
        error = 'Timeout 15000ms exceeded.\nwaiting for locator("#card-number")'
        data = store.apply_run_result(
            DOMAIN,
            {"cases": {target["id"]: {"status": "failed", "error": error, "failed_step": "S999"}}},
        )
        updated = next(t for t in data["tests"] if t["id"] == target["id"])
        index = updated["last"]["step"]
        assert index is not None
        assert updated["steps"][index]["loc"] == "#card-number"

    def test_raw_playwright_result_carries_failed_step(self, output_dir: Path) -> None:
        tests = store.derive_initial(DOMAIN, _report())["tests"]
        target = next(t for t in tests if len(t["steps"]) > 2)
        data = store.apply_run_result(
            DOMAIN,
            {
                "tests": [
                    {
                        "title": f"{target['id']} なにか",
                        "status": "failed",
                        "error": "Error",
                        "failed_step": "S2",
                    }
                ]
            },
        )
        assert next(t for t in data["tests"] if t["id"] == target["id"])["last"]["step"] == 2
