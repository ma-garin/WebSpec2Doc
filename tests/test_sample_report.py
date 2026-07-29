"""同梱サンプルレポート（P3-1 ゼロ待ちサンプル）のルート統合テスト。

初回の利用者にクロールを待たせずレポートを見せる導線。同梱物を自テナントの出力先へ
展開し、以降は通常のレポート経路で読む。利用者自身の解析結果と混ざらないことまで見る。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
from web.config import SAMPLE_DOMAIN

H = {"Host": "127.0.0.1"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """出力先をテスト用に隔離した Flask テストクライアント。"""
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr("web.routes.report.OUTPUT_DIR", out)
    monkeypatch.setattr("web.routes.history.OUTPUT_DIR", out)
    # _safe_output_path は web.validation 側の OUTPUT_DIR を基準に境界判定するため、
    # ここも差し替えないとテスト用の出力先が「範囲外」と判定される。
    monkeypatch.setattr("web.validation.OUTPUT_DIR", out)
    return appmod.app.test_client(), out


@pytest.fixture
def bundled_sample(tmp_path: Path, monkeypatch) -> Path:
    """同梱サンプルの最小構成（実物と同じ形）を用意する。"""
    source = tmp_path / "bundled"
    (source / "screenshots").mkdir(parents=True)
    (source / "report.json").write_text(
        json.dumps({"screens": [{"url": "http://example.test/", "title": "デモ"}]}),
        encoding="utf-8",
    )
    (source / "screenshots" / "P001.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr("web.routes.report.SAMPLE_REPORT_DIR", source)
    return source


class TestSampleReportEndpoint:
    def test_expands_bundled_sample_and_returns_domain(self, client, bundled_sample) -> None:
        c, out = client
        res = c.post("/api/sample-report", headers=H)
        assert res.status_code == 200
        assert res.get_json()["domain"] == SAMPLE_DOMAIN
        assert (out / SAMPLE_DOMAIN / "report.json").is_file()
        assert (out / SAMPLE_DOMAIN / "screenshots" / "P001.png").is_file()

    def test_is_idempotent(self, client, bundled_sample) -> None:
        """2 回押しても壊れない（毎回、同梱物で置き換える）。"""
        c, out = client
        assert c.post("/api/sample-report", headers=H).status_code == 200
        # 前回の展開物に混ざりものがあっても、同梱物が正本として復元される
        (out / SAMPLE_DOMAIN / "stale.txt").write_text("古い残骸", encoding="utf-8")
        assert c.post("/api/sample-report", headers=H).status_code == 200
        assert not (out / SAMPLE_DOMAIN / "stale.txt").exists()
        assert (out / SAMPLE_DOMAIN / "report.json").is_file()

    def test_missing_bundle_reports_error(self, client, tmp_path, monkeypatch) -> None:
        """同梱物が無い場合、黙って空のレポートを開かせず 404 で知らせる。"""
        c, _ = client
        monkeypatch.setattr("web.routes.report.SAMPLE_REPORT_DIR", tmp_path / "absent")
        res = c.post("/api/sample-report", headers=H)
        assert res.status_code == 404
        assert res.get_json()["error"]


class TestSampleIsDistinguishable:
    def test_result_marks_sample(self, client, bundled_sample) -> None:
        c, _ = client
        c.post("/api/sample-report", headers=H)
        data = c.get(f"/api/result?domain={SAMPLE_DOMAIN}", headers=H).get_json()
        assert data["is_sample"] is True

    def test_result_does_not_mark_user_sites(self, client, bundled_sample) -> None:
        c, out = client
        (out / "example.com").mkdir()
        data = c.get("/api/result?domain=example.com", headers=H).get_json()
        assert data["is_sample"] is False

    def test_history_excludes_sample(self, client, bundled_sample) -> None:
        """サンプルが解析履歴に混ざると、登録した覚えのないサイトとして誤解される。"""
        c, out = client
        (out / "example.com").mkdir()
        c.post("/api/sample-report", headers=H)
        items = c.get("/api/history", headers=H).get_json()["items"]
        domains = [item["domain"] for item in items]
        assert "example.com" in domains
        assert SAMPLE_DOMAIN not in domains


class TestSnapshotDiffSummary:
    """変更 0 件かどうかを機械可読に返す（P2-1）。

    差分レポート本体は HTML のため、これが無いと画面側で「変わっていない」のか
    「比較できていない」のかを区別できず、不在の証明になってしまう。
    """

    def _snapshot(self, out: Path, domain: str, snap_id: str, screens: list[dict]) -> None:
        snaps = out / domain / "snapshots"
        snaps.mkdir(parents=True, exist_ok=True)
        # スナップショットはトップレベルが画面の配列（save_snapshot と同じ形）
        (snaps / f"{snap_id}.json").write_text(
            json.dumps(screens, ensure_ascii=False), encoding="utf-8"
        )

    def _page(self, url: str, title: str = "画面") -> dict:
        return {
            "url": url,
            "title": title,
            "headings": [],
            "links": [],
            "forms": [],
            "screenshot_path": None,
            "buttons": [],
        }

    def test_reports_no_change_for_identical_snapshots(self, client) -> None:
        c, out = client
        self._snapshot(out, "example.com", "20260101-000000", [self._page("http://example.com/")])
        self._snapshot(out, "example.com", "20260102-000000", [self._page("http://example.com/")])
        res = c.get(
            "/api/snapshot-diff-summary?domain=example.com"
            "&from=20260101-000000&to=20260102-000000",
            headers=H,
        )
        assert res.status_code == 200
        assert res.get_json()["has_changes"] is False

    def test_reports_change_when_page_added(self, client) -> None:
        c, out = client
        self._snapshot(out, "example.com", "20260101-000000", [self._page("http://example.com/")])
        self._snapshot(
            out,
            "example.com",
            "20260102-000000",
            [self._page("http://example.com/"), self._page("http://example.com/new")],
        )
        data = c.get(
            "/api/snapshot-diff-summary?domain=example.com"
            "&from=20260101-000000&to=20260102-000000",
            headers=H,
        ).get_json()
        assert data["has_changes"] is True
        assert data["counts"]["added_pages"] == 1

    def test_missing_snapshot_is_404(self, client) -> None:
        """比較できないときに「変更なし」と誤って言わないよう、成功で返さない。"""
        c, _ = client
        res = c.get("/api/snapshot-diff-summary?domain=example.com&from=nope&to=nope", headers=H)
        assert res.status_code == 404
