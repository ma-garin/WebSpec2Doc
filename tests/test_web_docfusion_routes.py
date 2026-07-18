"""SPEC-1-5: Doc Fusion Web UI 統合のルート単体テスト（Flask テストクライアント）。

対象:
    - web/routes/crawl.py::upload_reference_docs (POST /api/reference-docs)
    - web/routes/crawl.py::api_doc_fusion (GET /api/doc-fusion)
    - web/routes/crawl.py::run の reference_docs パラメータ処理
    - web/validation.py::_safe_reference_doc_paths
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.crawl as crawl_mod
import web.routes.login as login_mod
import web.routes.report as report_mod
import web.routes.site as site_mod
import web.summary as summary_mod
from web.validation import _safe_reference_doc_paths


class _Popen:
    def __init__(self, cmd, stdout=None, stderr=None, text=None, bufsize=None) -> None:
        self.cmd = cmd
        self.stdout = iter(["クロールを開始しました\n", "クロール完了\n"])
        self.returncode = None

    def wait(self, timeout=None) -> int:
        self.returncode = 0
        return 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


def _client():
    return appmod.app.test_client()


def _patch_output_dirs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(crawl_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(report_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(site_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("web.validation.OUTPUT_DIR", tmp_path)


class TestUploadReferenceDocs:
    def test_upload_saves_supported_file(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        data = {
            "domain": "example.com",
            "files": (io.BytesIO(b"dummy yaml content"), "screens.yaml"),
        }
        res = _client().post("/api/reference-docs", data=data, content_type="multipart/form-data")
        body = res.get_json()
        assert res.status_code == 200
        assert body["ok"] is True
        assert body["saved"][0]["name"] == "screens.yaml"
        saved_path = Path(body["saved"][0]["path"])
        assert saved_path.is_file()
        assert saved_path.parent == (tmp_path / "example.com" / "reference_docs").resolve()

    def test_upload_rejects_unknown_suffix(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        data = {
            "domain": "example.com",
            "files": (io.BytesIO(b"MZ"), "malware.exe"),
        }
        res = _client().post("/api/reference-docs", data=data, content_type="multipart/form-data")
        body = res.get_json()
        assert res.status_code == 400
        assert body["ok"] is False
        assert "対応形式" in body["error"]
        assert not (tmp_path / "example.com" / "reference_docs" / "malware.exe").exists()

    def test_upload_rejects_legacy_xls(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        data = {
            "domain": "example.com",
            "files": (io.BytesIO(b"legacy"), "screens.xls"),
        }
        res = _client().post("/api/reference-docs", data=data, content_type="multipart/form-data")
        body = res.get_json()
        assert res.status_code == 400
        assert "変換してから" in body["error"]

    def test_upload_size_limit(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        oversized = io.BytesIO(b"0" * (20 * 1024 * 1024 + 1))
        data = {"domain": "example.com", "files": (oversized, "big.txt")}
        res = _client().post("/api/reference-docs", data=data, content_type="multipart/form-data")
        body = res.get_json()
        assert res.status_code == 400
        assert "上限" in body["error"]
        assert not (tmp_path / "example.com" / "reference_docs" / "big.txt").exists()

    def test_upload_rejects_invalid_domain(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        data = {"domain": "../etc", "files": (io.BytesIO(b"x"), "a.txt")}
        res = _client().post("/api/reference-docs", data=data, content_type="multipart/form-data")
        assert res.status_code == 400


class TestApiDocFusion:
    def test_doc_fusion_api_404_when_missing(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        res = _client().get("/api/doc-fusion?domain=example.com")
        assert res.status_code == 404

    def test_doc_fusion_api_returns_json(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        domain_dir = tmp_path / "example.com"
        domain_dir.mkdir(parents=True)
        payload = {
            "meta": {"field_gaps": 2, "matched_screens": 1},
            "screen_matches": [],
            "doc_only_screens": [],
            "crawl_only_page_ids": [],
            "field_gaps": [{"kind": "mismatch", "page_id": "P001", "field_name": "amount"}],
        }
        (domain_dir / "doc_fusion.json").write_text(json.dumps(payload), encoding="utf-8")
        res = _client().get("/api/doc-fusion?domain=example.com")
        assert res.status_code == 200
        assert res.get_json()["meta"]["field_gaps"] == 2

    def test_doc_fusion_api_invalid_domain(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        res = _client().get("/api/doc-fusion?domain=../etc")
        assert res.status_code == 404


class TestRunReferenceDocsWiring:
    def test_run_appends_reference_doc_args(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        domain_dir = tmp_path / "example.com" / "reference_docs"
        domain_dir.mkdir(parents=True)
        doc_path = domain_dir / "screens.yaml"
        doc_path.write_text("screens: []", encoding="utf-8")

        popen_calls = []

        def fake_popen(cmd, *args, **kwargs):
            popen_calls.append(cmd)
            return _Popen(cmd, *args, **kwargs)

        monkeypatch.setattr(crawl_mod.subprocess, "Popen", fake_popen)
        _client().post(
            "/run",
            data={
                "urls": "https://example.com/",
                "format": "md,html",
                "reference_docs": str(doc_path),
            },
        ).get_data(as_text=True)

        assert "--reference-doc" in popen_calls[0]
        assert str(doc_path.resolve()) in popen_calls[0]

    def test_run_ignores_traversal_path(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        popen_calls = []

        def fake_popen(cmd, *args, **kwargs):
            popen_calls.append(cmd)
            return _Popen(cmd, *args, **kwargs)

        monkeypatch.setattr(crawl_mod.subprocess, "Popen", fake_popen)
        _client().post(
            "/run",
            data={
                "urls": "https://example.com/",
                "format": "md,html",
                "reference_docs": "../../etc/passwd",
            },
        ).get_data(as_text=True)

        assert "--reference-doc" not in popen_calls[0]

    def test_run_ignores_other_domain_path(self, tmp_path: Path, monkeypatch) -> None:
        _patch_output_dirs(tmp_path, monkeypatch)
        other_dir = tmp_path / "other.com" / "reference_docs"
        other_dir.mkdir(parents=True)
        other_doc = other_dir / "screens.yaml"
        other_doc.write_text("screens: []", encoding="utf-8")

        popen_calls = []

        def fake_popen(cmd, *args, **kwargs):
            popen_calls.append(cmd)
            return _Popen(cmd, *args, **kwargs)

        monkeypatch.setattr(crawl_mod.subprocess, "Popen", fake_popen)
        _client().post(
            "/run",
            data={
                "urls": "https://example.com/",
                "format": "md,html",
                "reference_docs": str(other_doc),
            },
        ).get_data(as_text=True)

        assert "--reference-doc" not in popen_calls[0]


class TestSafeReferenceDocPaths:
    def test_filters_traversal_and_wrong_domain(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("web.validation.OUTPUT_DIR", tmp_path)
        good_dir = tmp_path / "example.com" / "reference_docs"
        good_dir.mkdir(parents=True)
        good_file = good_dir / "a.txt"
        good_file.write_text("x", encoding="utf-8")

        raw = f"{good_file},../../etc/passwd,{tmp_path / 'other.com' / 'reference_docs' / 'b.txt'}"
        result = _safe_reference_doc_paths(raw, "example.com")
        assert result == [str(good_file.resolve())]

    def test_empty_raw_returns_empty(self) -> None:
        assert _safe_reference_doc_paths("", "example.com") == []

    def test_invalid_domain_returns_empty(self, tmp_path: Path) -> None:
        assert _safe_reference_doc_paths(str(tmp_path / "a.txt"), "../etc") == []

    def test_list_payload_preserves_comma_in_valid_filename(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr("web.validation.OUTPUT_DIR", tmp_path)
        doc = tmp_path / "example.com" / "reference_docs" / "要件,補足.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# 要件", encoding="utf-8")

        assert _safe_reference_doc_paths([str(doc)], "example.com") == [str(doc.resolve())]
