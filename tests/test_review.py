"""レビューワークフロー API のテスト"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.review as review_mod


def _client():
    return appmod.app.test_client()


def _write_candidates(base: Path, domain: str, cases: list[dict]) -> None:
    domain_dir = base / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    (domain_dir / "playwright_candidates.json").write_text(json.dumps(cases), encoding="utf-8")


# ---------- GET /review/cases ----------


def test_review_cases_returns_empty_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/review/cases?domain=nonexistent.com")
    assert res.status_code == 200
    data = res.get_json()
    assert data["cases"] == []
    assert data["domain"] == "nonexistent.com"


def test_review_cases_returns_cases_from_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    candidates = [
        {"id": "TC001", "title": "ログインテスト"},
        {"id": "TC002", "title": "検索テスト"},
    ]
    _write_candidates(tmp_path, "example.com", candidates)

    res = _client().get("/review/cases?domain=example.com")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["cases"]) == 2
    assert data["cases"][0]["id"] == "TC001"
    # 初期ステータスは draft
    assert data["cases"][0]["status"] == "draft"


def test_review_cases_merges_saved_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    candidates = [{"id": "TC001", "title": "ログインテスト"}]
    _write_candidates(tmp_path, "example.com", candidates)

    state = {
        "domain": "example.com",
        "cases": {
            "TC001": {
                "status": "approved",
                "comment": "確認済み",
                "version": 2,
                "reviewed_at": "2026-06-10T00:00:00",
            }
        },
    }
    domain_dir = tmp_path / "example.com"
    (domain_dir / "review_state.json").write_text(json.dumps(state), encoding="utf-8")

    data = _client().get("/review/cases?domain=example.com").get_json()
    assert data["cases"][0]["status"] == "approved"
    assert data["cases"][0]["version"] == 2
    assert data["cases"][0]["comment"] == "確認済み"


def test_review_cases_invalid_domain_returns_400(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/review/cases?domain=!!bad!!")
    assert res.status_code == 400


# ---------- POST /review/update ----------


def test_review_update_saves_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    (tmp_path / "example.com").mkdir(parents=True, exist_ok=True)

    res = _client().post(
        "/review/update",
        data=json.dumps(
            {
                "domain": "example.com",
                "case_id": "TC001",
                "status": "reviewing",
                "comment": "確認中",
            }
        ),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["status"] == "reviewing"

    state_file = tmp_path / "example.com" / "review_state.json"
    assert state_file.is_file()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["cases"]["TC001"]["status"] == "reviewing"
    assert state["cases"]["TC001"]["comment"] == "確認中"


def test_review_update_increments_version_on_frozen(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True, exist_ok=True)

    # 既存状態（version=1）を書いておく
    state = {
        "domain": "example.com",
        "cases": {
            "TC001": {
                "status": "approved",
                "comment": "",
                "version": 1,
                "reviewed_at": "2026-06-10T00:00:00",
            }
        },
    }
    (domain_dir / "review_state.json").write_text(json.dumps(state), encoding="utf-8")

    res = _client().post(
        "/review/update",
        data=json.dumps(
            {"domain": "example.com", "case_id": "TC001", "status": "frozen", "comment": ""}
        ),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["version"] == 2


def test_review_update_does_not_increment_version_on_other_status(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "domain": "example.com",
        "cases": {
            "TC001": {
                "status": "draft",
                "comment": "",
                "version": 1,
                "reviewed_at": "2026-06-10T00:00:00",
            }
        },
    }
    (domain_dir / "review_state.json").write_text(json.dumps(state), encoding="utf-8")

    res = _client().post(
        "/review/update",
        data=json.dumps(
            {"domain": "example.com", "case_id": "TC001", "status": "reviewing", "comment": ""}
        ),
        content_type="application/json",
    )
    assert res.get_json()["version"] == 1


def test_review_update_rejects_invalid_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/review/update",
        data=json.dumps(
            {"domain": "example.com", "case_id": "TC001", "status": "hacked", "comment": ""}
        ),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_review_update_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/review/update",
        data=json.dumps(
            {"domain": "../etc/passwd", "case_id": "TC001", "status": "draft", "comment": ""}
        ),
        content_type="application/json",
    )
    assert res.status_code == 400


# ---------- GET /review/export ----------


def test_review_export_filters_approved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    candidates = [
        {"id": "TC001", "title": "テスト1"},
        {"id": "TC002", "title": "テスト2"},
        {"id": "TC003", "title": "テスト3"},
    ]
    _write_candidates(tmp_path, "example.com", candidates)

    state = {
        "domain": "example.com",
        "cases": {
            "TC001": {
                "status": "approved",
                "comment": "",
                "version": 1,
                "reviewed_at": "2026-06-10T00:00:00",
            },
            "TC002": {
                "status": "frozen",
                "comment": "",
                "version": 2,
                "reviewed_at": "2026-06-10T00:00:00",
            },
            "TC003": {
                "status": "draft",
                "comment": "",
                "version": 1,
                "reviewed_at": "2026-06-10T00:00:00",
            },
        },
    }
    (tmp_path / "example.com" / "review_state.json").write_text(json.dumps(state), encoding="utf-8")

    res = _client().get("/review/export?domain=example.com&filter=approved")
    assert res.status_code == 200
    data = res.get_json()
    assert data["exported_count"] == 2
    ids = {c["id"] for c in data["cases"]}
    assert ids == {"TC001", "TC002"}
    # draft は含まれない
    assert "TC003" not in ids


def test_review_export_all_returns_all_cases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    candidates = [
        {"id": "TC001", "title": "テスト1"},
        {"id": "TC002", "title": "テスト2"},
    ]
    _write_candidates(tmp_path, "example.com", candidates)

    res = _client().get("/review/export?domain=example.com&filter=all")
    assert res.status_code == 200
    data = res.get_json()
    assert data["exported_count"] == 2


def test_review_export_returns_empty_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/review/export?domain=nonexistent.com&filter=approved")
    assert res.status_code == 200
    data = res.get_json()
    assert data["exported_count"] == 0
    assert data["cases"] == []


def test_review_export_invalid_domain_returns_400(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(review_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/review/export?domain=!!bad!!&filter=approved")
    assert res.status_code == 400
