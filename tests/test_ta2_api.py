"""TA2（テスト自動化 System 02）API のテスト。

契約: `docs/plan/ta2-contract.md` §3。ルート層だけを検証するため、永続化と導出
（`web/services/ta2_store.py` = BE-A 担当）は偽物に差し替える。Playwright も
偽物にして、実ブラウザ無しで「非同期実行 → 進捗 → 結果保存」を確認する。
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.ta2 as ta2_mod

DOMAIN = "example.com"
SKIP_REASON = "検証手順が無いため自動実行できません"
NO_FIX_REASON = "修正案がありません（要素辞書に同じラベルの要素が見つかりません）"

REPORT = {
    "meta": {"title": "サンプル店", "target_url": f"https://{DOMAIN}/"},
    "screens": [
        {
            "page_id": "P001",
            "url": f"https://{DOMAIN}/",
            "title": "トップ",
            "headings": ["トップ"],
            "buttons": ["注文する"],
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "url": f"https://{DOMAIN}/checkout.html",
            "title": "注文",
            "headings": ["注文"],
            "buttons": ["注文を確定する"],
            "forms": [{"fields": [{"name": "name", "field_type": "text", "locators": ["#name"]}]}],
            "transitions": {"to": [], "from": ["P001"]},
        },
    ],
}


def _test_row(test_id: str = "PW-0001", status: str = "fail") -> dict[str, Any]:
    return {
        "id": test_id,
        "case_id": "TC-0001",
        "screen": "P002",
        "name": "必須項目が空だと送信できない",
        "technique": "同値分割",
        "source": "table",
        "steps": [
            {"kind": "pre", "action": "開く", "target": "page", "arg": "/checkout.html"},
            {
                "kind": "act",
                "action": "押す",
                "target": "submit",
                "arg": "注文を確定する",
                "loc": 'button[name="submit_order"]',
                "issue": {"type": "timeout", "msg": "15.0s でタイムアウト", "fix": None},
                "fixed": False,
            },
        ],
        "status": status,
        "history": [1, 0],
        "last": {"dur_ms": 15000, "at": "2026-08-29T23:14:05", "step": 1, "run_id": "x"},
        "updated_at": "2026-08-29T23:14:05",
    }


class FakeStore:
    """契約 §8 の公開関数だけを持つ、メモリ上の偽ストア。"""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {"version": 1, "domain": DOMAIN, "tests": [_test_row()]}
        self.saved: list[dict[str, Any]] = []
        self.skip_ids: set[str] = set()
        self.derived = 0
        self.applied: list[tuple[str, str]] = []
        self.drift: Any = {"items": []}

    # --- 永続化 ---------------------------------------------------------
    def load(self, domain: str) -> dict[str, Any]:
        return json.loads(json.dumps(self.data))

    def save(self, domain: str, data: dict[str, Any]) -> dict[str, Any]:
        self.data = json.loads(json.dumps(data))
        self.saved.append(self.data)
        return self.data

    def derive_initial(self, domain: str, report: dict[str, Any]) -> dict[str, Any]:
        self.derived += 1
        return {"version": 1, "domain": domain, "tests": [_test_row("PW-0100", "new")]}

    # --- 導出 -----------------------------------------------------------
    def elements_of(self, report: dict[str, Any]) -> dict[str, Any]:
        return {"P002": {"name": {"key": "name", "loc": "#name", "stab": "high"}}}

    def screens_of(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"id": s["page_id"], "name": s["title"], "path": s["url"]} for s in report["screens"]
        ]

    def to_table_rows(
        self, tests: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        rows: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for t in tests:
            if t["id"] in self.skip_ids:
                skipped.append({"id": t["id"], "reason": SKIP_REASON})
                continue
            rows.append(
                {
                    "case_id": t["id"],
                    "name": t["name"],
                    "automation": "自動化可",
                    "actions": [],
                    "assertions": [],
                }
            )
        return rows, skipped

    def gaps_of(self, domain: str, report: dict[str, Any], tests: list) -> list[dict[str, Any]]:
        return [{"id": "P002:name:0", "screen": "P002", "title": "氏名の未入力", "steps": []}]

    # --- 変更操作 -------------------------------------------------------
    def generate_from_gaps(
        self, domain: str, report: dict, screen: str, gap_ids: list[str], name: str
    ) -> list[dict[str, Any]]:
        created = _test_row("PW-0200", "new")
        created["name"] = name or "生成されたテスト"
        created["screen"] = screen or "P001"
        self.data["tests"].append(created)
        return [created]

    def update_test(
        self, domain: str, test_id: str, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        for row in self.data["tests"]:
            if row["id"] == test_id:
                row.update(patch)
                if "status" not in patch:  # 明示された status は尊重する（除外理由の記録）
                    row["status"] = "fixed"
                return row
        return None

    def delete_test(self, domain: str, test_id: str) -> bool:
        before = len(self.data["tests"])
        self.data["tests"] = [r for r in self.data["tests"] if r["id"] != test_id]
        return len(self.data["tests"]) < before

    def duplicate(self, domain: str, test_id: str) -> dict[str, Any] | None:
        for row in self.data["tests"]:
            if row["id"] == test_id:
                copied = json.loads(json.dumps(row))
                copied["id"] = "PW-0300"
                self.data["tests"].append(copied)
                return copied
        return None

    def apply_fix(
        self, domain: str, test_id: str, step_index: int
    ) -> tuple[dict[str, Any] | None, str | None]:
        for row in self.data["tests"]:
            if row["id"] == test_id and 0 <= step_index < len(row["steps"]):
                step = row["steps"][step_index]
                if not step.get("issue"):
                    return row, NO_FIX_REASON
                step["fixed"] = True
                row["status"] = "fixed"
                return row, None
        return None, None

    def apply_run_result(self, domain: str, result: dict, run_id: str, at: str) -> None:
        self.applied.append((run_id, at))

    # --- 変更検知 -------------------------------------------------------
    def drift_items(self, domain: str) -> Any:
        return self.drift

    def drift_apply(self, domain: str, item_id: str) -> list[str]:
        return ["PW-0001"]

    def drift_dismiss(self, domain: str, item_id: str) -> bool:
        return True


class FakeProc:
    """`_terminate_proc` が触る最小限のプロセス互換オブジェクト。"""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0

    def kill(self) -> None:
        self.returncode = -9


@pytest.fixture()
def store(tmp_path, monkeypatch) -> FakeStore:
    domain_dir = tmp_path / DOMAIN
    domain_dir.mkdir(parents=True)
    (domain_dir / "report.json").write_text(json.dumps(REPORT, ensure_ascii=False), "utf-8")
    fake = FakeStore()
    monkeypatch.setattr(ta2_mod, "scoped_output_dir", lambda _base: tmp_path)
    monkeypatch.setattr(ta2_mod, "run_dir", lambda d: tmp_path / d / "ta2run")
    monkeypatch.setattr(ta2_mod, "load_run_result", lambda d: {"ran_at": "2026-08-30 09:00:00"})
    monkeypatch.setattr(ta2_mod, "store", fake)
    ta2_mod._RUNS.clear()
    (tmp_path / DOMAIN / "ta2run").mkdir(parents=True)
    yield fake
    ta2_mod._RUNS.clear()


@pytest.fixture()
def client(store):
    return appmod.app.test_client()


class TestSites:
    def test_lists_domains_that_have_a_report(self, client) -> None:
        body = client.get("/api/ta2/sites").get_json()
        assert [s["domain"] for s in body["sites"]] == [DOMAIN]
        site = body["sites"][0]
        assert site["name"] == "サンプル店"
        assert site["screens"] == 2
        assert site["tests"] == 1
        assert site["fails"] == 1
        assert site["last_run_at"] == "2026-08-30 09:00:00"


class TestTests:
    def test_get_derives_and_saves_when_empty(self, client, store) -> None:
        store.data = {"version": 1, "domain": DOMAIN, "tests": []}
        body = client.get(f"/api/ta2/tests?domain={DOMAIN}").get_json()
        assert store.derived == 1
        assert store.saved, "導出結果が保存されていない"
        assert [t["id"] for t in body["tests"]] == ["PW-0100"]
        assert body["domain"] == DOMAIN
        assert "P002" in body["elements"]
        assert [s["id"] for s in body["screens"]] == ["P001", "P002"]

    def test_get_keeps_existing_tests(self, client, store) -> None:
        body = client.get(f"/api/ta2/tests?domain={DOMAIN}").get_json()
        assert store.derived == 0
        assert [t["id"] for t in body["tests"]] == ["PW-0001"]

    def test_post_creates_manual_test(self, client) -> None:
        resp = client.post(
            "/api/ta2/tests", json={"domain": DOMAIN, "screen": "P001", "name": "手動テスト"}
        )
        created = resp.get_json()["created"]
        assert resp.status_code == 200
        assert created[0]["name"] == "手動テスト"
        assert created[0]["screen"] == "P001"

    def test_post_requires_screen_or_name(self, client) -> None:
        resp = client.post("/api/ta2/tests", json={"domain": DOMAIN})
        assert resp.status_code == 400
        assert resp.get_json()["error"]

    def test_put_updates_and_marks_fixed(self, client) -> None:
        resp = client.put("/api/ta2/tests/PW-0001", json={"domain": DOMAIN, "name": "名前を直した"})
        test = resp.get_json()["test"]
        assert test["name"] == "名前を直した"
        assert test["status"] == "fixed"

    def test_put_unknown_id_is_404(self, client) -> None:
        resp = client.put("/api/ta2/tests/PW-9999", json={"domain": DOMAIN, "name": "x"})
        assert resp.status_code == 404
        assert resp.get_json()["error"]

    def test_delete_removes_test(self, client, store) -> None:
        resp = client.delete(f"/api/ta2/tests/PW-0001?domain={DOMAIN}")
        assert resp.get_json() == {"ok": True}
        assert store.data["tests"] == []

    def test_duplicate_returns_new_test(self, client) -> None:
        test = client.post("/api/ta2/tests/PW-0001/duplicate", json={"domain": DOMAIN}).get_json()[
            "test"
        ]
        assert test["id"] == "PW-0300"
        assert test["name"] == "必須項目が空だと送信できない"

    def test_fix_marks_step_fixed(self, client) -> None:
        body = client.post(
            "/api/ta2/tests/PW-0001/fix", json={"domain": DOMAIN, "step": 1}
        ).get_json()
        assert body["applied"] is True
        assert body["test"]["steps"][1]["fixed"] is True
        assert body["test"]["status"] == "fixed"

    def test_fix_without_proposal_is_200_with_reason(self, client) -> None:
        """修正案が無いのは正常系。エラーにせず理由を返す（検証 B-2）。"""
        resp = client.post("/api/ta2/tests/PW-0001/fix", json={"domain": DOMAIN, "step": 0})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["applied"] is False
        assert body["reason"] == NO_FIX_REASON
        assert body["test"]["id"] == "PW-0001"

    def test_fix_unknown_test_is_404(self, client) -> None:
        resp = client.post("/api/ta2/tests/PW-9999/fix", json={"domain": DOMAIN, "step": 0})
        assert resp.status_code == 404
        assert resp.get_json()["error"]

    def test_store_error_becomes_its_own_japanese_message(self, client, store) -> None:
        """Ta2StoreError を汎用エラーに潰さない（検証 B-2）。"""

        def boom(domain, test_id, step_index):
            raise ta2_mod.Ta2StoreError("修正案がありません（要素が見つかりません）")

        store.apply_fix = boom
        resp = client.post("/api/ta2/tests/PW-0001/fix", json={"domain": DOMAIN, "step": 1})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "修正案がありません（要素が見つかりません）"

    def test_invalid_domain_is_400(self, client) -> None:
        resp = client.get("/api/ta2/tests?domain=../etc")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "domain が不正です"


def _install_fake_run(
    monkeypatch,
    gate: threading.Event,
    ready: threading.Event,
    proc: FakeProc | None = None,
):
    """spec 生成と Playwright 実行を偽物にする（進捗 NDJSON も書く）。"""

    def fake_generate_spec(rows, out_dir):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        spec = Path(out_dir) / "ta2.spec.ts"
        spec.write_text("// fake", encoding="utf-8")
        return {
            "spec_path": str(spec),
            "mapping": [
                {"test_title": f"{r['case_id']} {r['name']}", "case_id": r["case_id"]} for r in rows
            ],
        }

    def fake_run_playwright(spec_path, out_dir, **kwargs):
        if proc is not None and kwargs.get("on_proc"):
            kwargs["on_proc"](proc)
        progress = Path(out_dir) / "playwright_progress.ndjson"
        progress.write_text(
            json.dumps({"event": "begin", "total": 1})
            + "\n"
            + json.dumps(
                {
                    "event": "test",
                    "title": "PW-0001 必須項目が空だと送信できない",
                    "status": "passed",
                    "duration": 1200,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        ready.set()
        gate.wait(timeout=10)
        return {
            "ok": True,
            "passed": 1,
            "failed": 0,
            "total": 1,
            "duration_ms": 1200,
            "tests": [
                {
                    "title": "PW-0001 必須項目が空だと送信できない",
                    "status": "passed",
                    "duration_ms": 1200,
                    "error": "",
                }
            ],
        }

    monkeypatch.setattr(ta2_mod, "generate_spec", fake_generate_spec)
    monkeypatch.setattr(ta2_mod, "run_playwright", fake_run_playwright)


class TestRun:
    def test_run_is_async_and_reports_progress(self, client, store, monkeypatch) -> None:
        gate, ready = threading.Event(), threading.Event()
        _install_fake_run(monkeypatch, gate, ready)

        started = client.post("/api/ta2/run", json={"domain": DOMAIN}).get_json()
        assert ready.wait(timeout=10), "実行スレッドが進捗を書き出さなかった"
        assert started["run_id"]
        assert started["total"] == 1

        # 実行中は 409（契約 §3）
        second = client.post("/api/ta2/run", json={"domain": DOMAIN})
        assert second.status_code == 409
        assert second.get_json()["error"] == "実行中です"

        status = client.get(f"/api/ta2/run/status?domain={DOMAIN}").get_json()
        assert set(status) == {
            "running",
            "run_id",
            "total",
            "done",
            "passed",
            "failed",
            "current_id",
            "tests",
            "skipped",
        }
        assert status["running"] is True
        assert status["run_id"] == started["run_id"]
        assert status["done"] == 1
        assert status["tests"][0]["id"] == "PW-0001"
        assert status["tests"][0]["duration_ms"] == 1200

        gate.set()
        ta2_mod._RUNS[DOMAIN]["thread"].join(timeout=10)

        assert store.applied and store.applied[0][0] == started["run_id"]
        runs = client.get(f"/api/ta2/runs?domain={DOMAIN}").get_json()["runs"]
        assert len(runs) == 1
        assert runs[0]["run_id"] == started["run_id"]
        assert runs[0]["passed"] == 1
        assert runs[0]["total"] == 1
        assert client.get(f"/api/ta2/run/status?domain={DOMAIN}").get_json()["running"] is False

    def test_cancel_kills_the_process(self, client, monkeypatch) -> None:
        gate, ready = threading.Event(), threading.Event()
        proc = FakeProc()
        _install_fake_run(monkeypatch, gate, ready, proc)
        client.post("/api/ta2/run", json={"domain": DOMAIN})
        assert ready.wait(timeout=10), "実行スレッドが開始しなかった"

        assert client.post("/api/ta2/run/cancel", json={"domain": DOMAIN}).get_json() == {
            "ok": True
        }
        assert proc.terminated is True
        gate.set()
        ta2_mod._RUNS[DOMAIN]["thread"].join(timeout=10)

    def test_cancel_without_run_is_not_ok(self, client) -> None:
        assert client.post("/api/ta2/run/cancel", json={"domain": DOMAIN}).get_json() == {
            "ok": False
        }

    def test_run_excludes_and_explains_skipped_tests(self, client, store, monkeypatch) -> None:
        """spec に載らない行を黙って捨てない。total は実際に載った件数（検証 B-3）。"""
        gate, ready = threading.Event(), threading.Event()
        _install_fake_run(monkeypatch, gate, ready)
        store.data["tests"].append(_test_row("PW-0002", "new"))
        store.skip_ids = {"PW-0002"}

        started = client.post("/api/ta2/run", json={"domain": DOMAIN}).get_json()
        assert ready.wait(timeout=10), "実行スレッドが進捗を書き出さなかった"
        assert started["total"] == 1
        assert started["skipped"] == [{"id": "PW-0002", "reason": SKIP_REASON}]

        status = client.get(f"/api/ta2/run/status?domain={DOMAIN}").get_json()
        assert status["skipped"] == [{"id": "PW-0002", "reason": SKIP_REASON}]
        assert status["done"] == status["total"] == 1  # done が total に届く

        skipped_row = [t for t in store.data["tests"] if t["id"] == "PW-0002"][0]
        assert skipped_row["status"] == "new"
        assert skipped_row["last"]["error"] == SKIP_REASON

        gate.set()
        ta2_mod._RUNS[DOMAIN]["thread"].join(timeout=10)

    def test_run_with_only_skipped_tests_explains_why(self, client, store) -> None:
        store.skip_ids = {"PW-0001"}
        resp = client.post("/api/ta2/run", json={"domain": DOMAIN})
        assert resp.status_code == 400
        assert SKIP_REASON in resp.get_json()["error"]

    def test_run_without_tests_is_400(self, client, store) -> None:
        store.data = {"version": 1, "domain": DOMAIN, "tests": []}
        resp = client.post("/api/ta2/run", json={"domain": DOMAIN})
        assert resp.status_code == 400
        assert resp.get_json()["error"]


class TestMapAndDrift:
    def test_map_returns_screens_with_gaps_and_coverage(self, client) -> None:
        screens = client.get(f"/api/ta2/map?domain={DOMAIN}").get_json()["screens"]
        assert [s["id"] for s in screens] == ["P001", "P002"]
        p002 = screens[1]
        assert p002["tests"] == 1
        assert p002["fails"] == 1
        assert p002["coverage"] == 50  # テスト 1 件 / 穴 1 件
        assert p002["gaps"][0]["id"] == "P002:name:0"
        assert screens[0]["coverage"] == 0

    def test_drift_without_baseline_explains_why(self, client) -> None:
        body = client.get(f"/api/ta2/drift?domain={DOMAIN}").get_json()
        assert body["items"] == []
        assert body["reason"] == "比較の基準となる前回のクロールがありません"

    def test_drift_returns_items(self, client, store) -> None:
        store.drift = {
            "baseline_at": "2026-08-01",
            "current_at": "2026-08-30",
            "items": [{"id": "d1", "kind": "loc", "screen": "P002", "state": "open"}],
        }
        body = client.get(f"/api/ta2/drift?domain={DOMAIN}").get_json()
        assert body["items"][0]["id"] == "d1"
        assert "reason" not in body

    def test_drift_apply_and_dismiss(self, client) -> None:
        assert client.post("/api/ta2/drift/d1/apply", json={"domain": DOMAIN}).get_json() == {
            "applied": ["PW-0001"]
        }
        assert client.post("/api/ta2/drift/d1/dismiss", json={"domain": DOMAIN}).get_json() == {
            "ok": True
        }


def _make_run_artifacts(base: Path, test_id: str = "PW-0001") -> Path:
    """実レイアウト（test-results/testcases-<ID>-<名前>/…）を再現する。"""
    case_dir = base / "test-results" / f"testcases-{test_id}-必須項目が空だと送信できない"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "test-failed-1.png").write_bytes(b"\x89PNG\r\n\x1a\nfailed")
    (case_dir / "trace.zip").write_bytes(b"PK\x03\x04trace")
    return case_dir


class TestArtifacts:
    def test_artifact_missing_returns_404_json(self, client) -> None:
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&id=PW-0001&kind=trace")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "この実行の証跡はありません"

    def test_artifact_rejects_unknown_kind(self, client) -> None:
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&kind=secrets")
        assert resp.status_code == 400
        assert resp.get_json()["error"]

    def test_artifact_sends_the_report(self, client, tmp_path) -> None:
        report_dir = tmp_path / DOMAIN / "ta2run" / "playwright-report"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "index.html").write_text("<html>結果</html>", encoding="utf-8")
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&kind=report")
        assert resp.status_code == 200
        assert "結果" in resp.get_data(as_text=True)

    def test_artifact_sends_the_failure_screenshot(self, client, tmp_path) -> None:
        _make_run_artifacts(tmp_path / DOMAIN / "ta2run")
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&id=PW-0001&kind=screenshot")
        assert resp.status_code == 200
        assert resp.get_data().startswith(b"\x89PNG")

    def test_artifact_sends_the_trace(self, client, tmp_path) -> None:
        _make_run_artifacts(tmp_path / DOMAIN / "ta2run")
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&id=PW-0001&kind=trace")
        assert resp.status_code == 200
        assert resp.get_data().startswith(b"PK")

    def test_artifact_for_another_test_is_404(self, client, tmp_path) -> None:
        _make_run_artifacts(tmp_path / DOMAIN / "ta2run")
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&id=PW-0777&kind=screenshot")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "この実行の証跡はありません"

    def test_artifact_resolves_a_relative_run_dir(self, client, tmp_path, monkeypatch) -> None:
        """相対パスのまま send_file へ渡すと web/ 基準で解決され 400 になっていた（B-1）。"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ta2_mod, "run_dir", lambda d: Path(d) / "ta2run")
        report_dir = tmp_path / DOMAIN / "ta2run" / "playwright-report"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "index.html").write_text("<html>結果</html>", encoding="utf-8")
        resp = client.get(f"/api/ta2/artifact?domain={DOMAIN}&kind=report")
        assert resp.status_code == 200
        assert "結果" in resp.get_data(as_text=True)

    def test_screenshot_missing_returns_404_json(self, client) -> None:
        resp = client.get(f"/api/ta2/screenshot?domain={DOMAIN}&screen=P002")
        assert resp.status_code == 404
        assert resp.get_json()["error"]

    def test_screenshot_sends_png(self, client, tmp_path) -> None:
        shots = tmp_path / DOMAIN / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        (shots / "P002.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        resp = client.get(f"/api/ta2/screenshot?domain={DOMAIN}&screen=P002")
        assert resp.status_code == 200
        assert resp.get_data().startswith(b"\x89PNG")

    def test_screenshot_rejects_path_traversal(self, client) -> None:
        resp = client.get(f"/api/ta2/screenshot?domain={DOMAIN}&screen=../report")
        assert resp.status_code == 400
        assert resp.get_json()["error"]


class TestRecrawl:
    """再クロールはバックグラウンドのクロールジョブに委ねる（B2）。"""

    @pytest.fixture(autouse=True)
    def _clear_job_registry(self):
        """ジョブ台帳はモジュール共有なので、テストごとに空にする。

        残っていると「このサイトは再クロール中です」の 409 ガードが
        前のテストのジョブを見て発火し、無関係な失敗になる。
        """
        from web.services import job_queue

        job_queue._JOBS.clear()
        yield
        job_queue._JOBS.clear()

    @staticmethod
    def _patch_start(monkeypatch, calls: list) -> None:
        def fake_start(domain, site_url, **kwargs):
            calls.append({"domain": domain, "site_url": site_url, **kwargs})
            return "job-1"

        monkeypatch.setattr("web.services.job_queue.start_crawl_job", fake_start)

    def test_recrawl_starts_job_with_report_url(self, client, monkeypatch) -> None:
        calls: list = []
        self._patch_start(monkeypatch, calls)

        resp = client.post("/api/ta2/recrawl", json={"domain": DOMAIN})

        assert resp.status_code == 200
        assert resp.get_json()["job_id"] == "job-1"
        assert len(calls) == 1
        assert calls[0]["site_url"]
        assert calls[0]["formats"] == ["md", "html", "json"]
        assert calls[0]["compare"] is True
        assert calls[0]["output_dir"] is not None
        assert callable(calls[0]["on_done"])

    def test_recrawl_records_usage_when_completed(self, client, monkeypatch) -> None:
        calls: list = []
        self._patch_start(monkeypatch, calls)
        recorded: list = []
        monkeypatch.setattr(
            "web.routes.crawl._record_usage_safely",
            lambda domain, compare, out_dir: recorded.append((domain, compare, out_dir)),
        )
        client.post("/api/ta2/recrawl", json={"domain": DOMAIN})
        on_done = calls[0]["on_done"]

        on_done(SimpleNamespace(status="failed"))
        assert recorded == []

        on_done(SimpleNamespace(status="completed"))
        assert len(recorded) == 1
        assert recorded[0][0] == DOMAIN
        assert recorded[0][1] is True

    def test_recrawl_rejects_missing_target_url(self, client, monkeypatch) -> None:
        monkeypatch.setattr("web.routes.ta2._report", lambda domain: {"meta": {}, "screens": []})
        resp = client.post("/api/ta2/recrawl", json={"domain": DOMAIN})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "対象 URL が report.json にありません"

    def test_recrawl_rejects_bad_domain(self, client) -> None:
        resp = client.post("/api/ta2/recrawl", json={"domain": "../etc"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]


class TestRecrawlStatus:
    def test_status_returns_job_fields(self, client, monkeypatch) -> None:
        job = SimpleNamespace(
            status="completed",
            finished_at="2026-08-30T10:00:00",
            exit_code=0,
            log_tail="x" * 500,
        )
        monkeypatch.setattr("web.services.job_queue.get_job", lambda job_id: job)

        resp = client.get(f"/api/ta2/recrawl/status?domain={DOMAIN}&job_id=job-1")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["finished_at"] == "2026-08-30T10:00:00"
        assert data["exit_code"] == 0
        assert len(data["log_tail"]) == 300

    def test_status_requires_job_id(self, client) -> None:
        resp = client.get(f"/api/ta2/recrawl/status?domain={DOMAIN}")
        assert resp.status_code == 400
        assert resp.get_json()["error"]

    def test_status_unknown_job_is_404(self, client, monkeypatch) -> None:
        monkeypatch.setattr("web.services.job_queue.get_job", lambda job_id: None)
        resp = client.get(f"/api/ta2/recrawl/status?domain={DOMAIN}&job_id=nope")
        assert resp.status_code == 404
        assert resp.get_json()["error"]
