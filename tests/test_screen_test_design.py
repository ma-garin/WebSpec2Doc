"""画面別テスト設計 API（GET /api/test-design/by-screen）のテスト"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.qa_process as qa_mod

API = "/api/test-design/by-screen"
DOMAIN = "example.com"
COND_CLASSES = {"cc-req", "cc-bound", "cc-format", "cc-opt", "cc-other"}
SERVICE_MODULE = "web.services.screen_test_design"


def _client():
    return appmod.app.test_client()


def _patch_output_dir(monkeypatch: pytest.MonkeyPatch, base: Path) -> None:
    """出力先を tmp_path に差し替える（実データ output/ に依存させない）。

    helpers._output_dir が web.routes.qa_process.OUTPUT_DIR を参照するため
    そこを差し替える。サービス側が独自に OUTPUT_DIR を持つ場合も合わせて差し替える。
    """
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", base)
    if importlib.util.find_spec(SERVICE_MODULE) is not None:
        service = importlib.import_module(SERVICE_MODULE)
        if hasattr(service, "OUTPUT_DIR"):
            monkeypatch.setattr(service, "OUTPUT_DIR", base)


def _write_report(base: Path, domain: str = DOMAIN) -> Path:
    """フォームなし画面(P001)とフォームあり画面(P002)を持つ report.json を作る。"""
    domain_dir = base / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": {"target_url": f"https://{domain}/", "page_count": 2, "crawled_at": "2026-07-01"},
        "screens": [
            {
                "page_id": "P001",
                "url": f"https://{domain}/",
                "title": "トップ",
                "headings": ["ようこそ", "お知らせ"],
                "buttons": ["ログイン", "検索"],
                "forms": [],
                "transitions": {"to": ["P002"], "from": []},
            },
            {
                "page_id": "P002",
                "url": f"https://{domain}/contact",
                "title": "お問い合わせ",
                "headings": ["お問い合わせ"],
                "buttons": ["送信"],
                "forms": [
                    {
                        "action": "/contact",
                        "method": "post",
                        "fields": [
                            {
                                "name": "email",
                                "element_id": "email",
                                "field_type": "email",
                                "required": True,
                                "maxlength": "100",
                                "placeholder": "メールアドレス",
                                "test_conditions": ["必須入力", "メール形式", "最大長100"],
                            },
                            {
                                "name": "message",
                                "element_id": "message",
                                "field_type": "textarea",
                                "required": False,
                                "test_conditions": ["任意入力"],
                            },
                        ],
                    }
                ],
                "transitions": {"to": [], "from": ["P001"]},
            },
        ],
    }
    (domain_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    return domain_dir


@pytest.fixture
def report_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _patch_output_dir(monkeypatch, tmp_path)
    return _write_report(tmp_path)


def _get(params: str) -> tuple[int, Any]:
    res = _client().get(f"{API}?{params}")
    return res.status_code, res.get_json()


def test_list_returns_screens(report_dir: Path) -> None:
    """一覧（page_id 省略）は 200 で screens をリストで返す。"""
    status, data = _get(f"domain={DOMAIN}")

    assert status == 200
    assert data["domain"] == DOMAIN
    assert isinstance(data["screens"], list)
    assert len(data["screens"]) == 2
    for screen in data["screens"]:
        for key in ("page_id", "title", "element_count", "condition_count"):
            assert key in screen, f"一覧の必須キー {key} がない: {screen}"
        assert isinstance(screen["element_count"], int)
        assert isinstance(screen["condition_count"], int)
    assert [s["page_id"] for s in data["screens"]] == ["P001", "P002"]


def test_detail_has_required_keys(report_dir: Path) -> None:
    """詳細（page_id 指定）は 200 で契約どおりのキーをすべて返す。"""
    status, data = _get(f"domain={DOMAIN}&page_id=P002")

    assert status == 200
    for key in ("page_id", "title", "url", "summary", "conditions", "unapplied"):
        assert key in data, f"詳細の必須キー {key} がない: {sorted(data)}"
    assert data["page_id"] == "P002"
    assert data["title"] == "お問い合わせ"
    assert data["url"].endswith("/contact")

    summary = data["summary"]
    for key in ("element_count", "condition_count", "applied_techniques", "unapplied_techniques"):
        assert key in summary, f"summary の必須キー {key} がない: {sorted(summary)}"
    assert summary["condition_count"] == len(data["conditions"])

    for cond in data["conditions"]:
        for key in ("no", "condition", "source_kind", "source_name", "technique", "cond_class"):
            assert key in cond, f"conditions の必須キー {key} がない: {cond}"

    assert isinstance(data["unapplied"], list)
    for item in data["unapplied"]:
        assert "technique" in item and "reason" in item


def test_condition_no_is_sequential_from_one(report_dir: Path) -> None:
    """no は 1 始まりの連番であること。"""
    for page_id in ("P001", "P002"):
        status, data = _get(f"domain={DOMAIN}&page_id={page_id}")

        assert status == 200
        numbers = [cond["no"] for cond in data["conditions"]]
        assert numbers == list(
            range(1, len(numbers) + 1)
        ), f"{page_id} の no が連番でない: {numbers}"


def test_cond_class_is_known_value(report_dir: Path) -> None:
    """cond_class は既定の5種のいずれかであること。"""
    for page_id in ("P001", "P002"):
        status, data = _get(f"domain={DOMAIN}&page_id={page_id}")

        assert status == 200
        for cond in data["conditions"]:
            assert cond["cond_class"] in COND_CLASSES, f"未知の cond_class: {cond}"


def test_screen_without_form_still_has_conditions(report_dir: Path) -> None:
    """フォームを持たない画面でも、見出し・ボタン等から条件が出ること（本機能の核）。"""
    status, data = _get(f"domain={DOMAIN}&page_id=P001")

    assert status == 200
    conditions = data["conditions"]
    assert conditions, "フォームなし画面(P001)の conditions が空になっている"
    assert data["summary"]["condition_count"] == len(conditions)
    kinds = {cond["source_kind"] for cond in conditions}
    assert kinds - {"field"}, f"フォーム項目以外の由来の条件がない: {kinds}"
    names = {cond["source_name"] for cond in conditions}
    assert names & {
        "ようこそ",
        "お知らせ",
        "ログイン",
        "検索",
    }, f"見出し・ボタン由来がない: {names}"


def test_invalid_domain_returns_404(report_dir: Path) -> None:
    """不正なドメイン名（パストラバーサル等）は 404。"""
    status, _ = _get("domain=../etc/passwd")

    assert status == 404


def test_unknown_page_id_returns_404(report_dir: Path) -> None:
    """存在しない page_id は 404。"""
    status, _ = _get(f"domain={DOMAIN}&page_id=P999")

    assert status == 404
