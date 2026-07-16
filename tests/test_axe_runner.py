"""axe-core 検査（rules 層）のユニットテスト。

axe.min.js 資産の整合性検証・注入実行・violations 変換・失敗時フォールバックを検証する。
実ブラウザは使わず、フェイク Page（evaluate/eval_on_selector を模擬）で完結させる。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ux.axe_runner import (
    AXE_ASSET_SHA256,
    AxeAssetError,
    axe_violation_to_dict,
    run_axe,
    verify_axe_asset,
)

ROOT = Path(__file__).parent.parent
ASSET_MD = ROOT / "src" / "ux" / "assets" / "ASSET.md"
AXE_JS = ROOT / "src" / "ux" / "assets" / "axe.min.js"


class _FakeAxePage:
    """axe_runner.run_axe が必要とする Page API 最小限のフェイク。"""

    def __init__(
        self,
        *,
        already_injected: bool = True,
        run_result: Any = None,
        run_error: Exception | None = None,
        bbox_result: Any = None,
        bbox_error: bool = False,
    ) -> None:
        self.already_injected = already_injected
        self.run_result = run_result if run_result is not None else {"violations": []}
        self.run_error = run_error
        self.bbox_result = bbox_result
        self.bbox_error = bbox_error
        self.injected_source = False
        self._checked_injection = False

    def evaluate(self, script: str, *args: Any) -> Any:
        # run_axe の axe.run 呼び出しのみタイムアウト ms を第2引数で渡す。
        # axe.min.js の実ソース内に偶然 "axe.run" 等の文字列が含まれるため、
        # 呼び出しシーケンス（引数の有無）で判別する（文字列一致は使わない）。
        if args:
            if self.run_error is not None:
                raise self.run_error
            return self.run_result
        if not self._checked_injection:
            self._checked_injection = True
            return self.already_injected
        # 注入スクリプト本体（axe.min.js のソース）実行
        self.injected_source = True
        return None

    def eval_on_selector(self, _selector: str, _script: str) -> Any:
        if self.bbox_error:
            raise RuntimeError("bbox 取得に失敗しました（フェイク）")
        return self.bbox_result


class TestAxeAsset:
    def test_axe_asset_sha256_matches_manifest(self) -> None:
        """同梱 axe.min.js の SHA-256 が ASSET.md 記載値と一致する（AC-2）。"""
        manifest = ASSET_MD.read_text(encoding="utf-8")
        match = re.search(r"SHA-256:\s*`([0-9a-f]{64})`", manifest)
        assert match is not None, "ASSET.md に SHA-256 の記載が見つかりません"
        documented_hash = match.group(1)

        import hashlib

        actual_hash = hashlib.sha256(AXE_JS.read_bytes()).hexdigest()

        assert actual_hash == documented_hash
        assert actual_hash == AXE_ASSET_SHA256
        verify_axe_asset()  # 例外を送出しないこと

    def test_verify_axe_asset_raises_on_missing_file(self, tmp_path: Path, monkeypatch) -> None:
        """axe.min.js が欠落している場合は AxeAssetError を送出する（§5-4）。"""
        import ux.axe_runner as axe_runner

        missing_path = tmp_path / "axe.min.js"
        monkeypatch.setattr(axe_runner, "_AXE_ASSET_PATH", missing_path)
        try:
            axe_runner.verify_axe_asset()
            raise AssertionError("AxeAssetError が送出されるはずです")
        except AxeAssetError:
            pass

    def test_verify_axe_asset_raises_on_tampered_content(self, tmp_path: Path, monkeypatch) -> None:
        """axe.min.js が改竄されている（SHA-256 不一致）場合は AxeAssetError を送出する（§5-4）。"""
        import ux.axe_runner as axe_runner

        tampered = tmp_path / "axe.min.js"
        tampered.write_text("// tampered", encoding="utf-8")
        monkeypatch.setattr(axe_runner, "_AXE_ASSET_PATH", tampered)
        try:
            axe_runner.verify_axe_asset()
            raise AssertionError("AxeAssetError が送出されるはずです")
        except AxeAssetError:
            pass


class TestRunAxe:
    def test_run_axe_failure_returns_empty(self) -> None:
        """axe 実行が例外を送出しても、空タプルを返しクロールを継続する（AC-3）。"""
        page = _FakeAxePage(run_error=RuntimeError("axe 実行失敗（フェイク）"))

        result = run_axe(page)  # type: ignore[arg-type]

        assert result == ()

    def test_run_axe_injects_source_when_not_already_present(self) -> None:
        """window.axe が未定義の場合のみ axe.min.js を注入する。"""
        page = _FakeAxePage(already_injected=False, run_result={"violations": []})

        run_axe(page)  # type: ignore[arg-type]

        assert page.injected_source is True

    def test_run_axe_skips_injection_when_already_present(self) -> None:
        """window.axe が既に存在する場合は再注入しない。"""
        page = _FakeAxePage(already_injected=True, run_result={"violations": []})

        run_axe(page)  # type: ignore[arg-type]

        assert page.injected_source is False

    def test_axe_violation_has_evidence_and_confidence(self) -> None:
        """violations が rule_id・impact・selector・WCAGタグ・confidence 1.0 で記録される（AC-1）。"""
        page = _FakeAxePage(
            run_result={
                "violations": [
                    {
                        "id": "image-alt",
                        "impact": "critical",
                        "description": "Images must have alternate text",
                        "helpUrl": "https://dequeuniversity.com/rules/axe/image-alt",
                        "tags": ["wcag2a", "wcag111", "cat.text-alternatives"],
                        "nodes": [{"target": ["img.hero"]}],
                    }
                ]
            },
            bbox_result=[10, 20, 30, 40],
        )

        result = run_axe(page, screenshot_path="/tmp/shot.png")  # type: ignore[arg-type]

        assert len(result) == 1
        violation = result[0]
        assert violation.rule_id == "image-alt"
        assert violation.impact == "critical"
        assert violation.evidence.selector == "img.hero"
        assert violation.evidence.screenshot_path == "/tmp/shot.png"
        assert violation.evidence.bbox == (10, 20, 30, 40)
        assert "wcag2a" in violation.wcag_tags
        assert "wcag111" in violation.wcag_tags
        assert "cat.text-alternatives" not in violation.wcag_tags
        assert violation.help_url == "https://dequeuniversity.com/rules/axe/image-alt"
        assert violation.confidence == 1.0

    def test_axe_violation_bbox_none_when_unavailable(self) -> None:
        """bbox 取得に失敗した場合は None（未取得と明示）で継続する。"""
        page = _FakeAxePage(
            run_result={
                "violations": [
                    {
                        "id": "label",
                        "impact": "serious",
                        "description": "Form elements must have labels",
                        "tags": ["wcag2a", "wcag412"],
                        "nodes": [{"target": ["#unlabeled"]}],
                    }
                ]
            },
            bbox_error=True,
        )

        result = run_axe(page)  # type: ignore[arg-type]

        assert result[0].evidence.bbox is None

    def test_run_axe_multiple_nodes_produce_multiple_violations(self) -> None:
        """1 ルールに複数の対象ノードがある場合はノードごとに 1 件ずつ記録する。"""
        page = _FakeAxePage(
            run_result={
                "violations": [
                    {
                        "id": "label",
                        "impact": "serious",
                        "description": "Form elements must have labels",
                        "tags": ["wcag2a"],
                        "nodes": [{"target": ["#a"]}, {"target": ["#b"]}],
                    }
                ]
            },
            bbox_result=None,
        )

        result = run_axe(page)  # type: ignore[arg-type]

        assert {v.evidence.selector for v in result} == {"#a", "#b"}


class TestAxeViolationToDict:
    def test_axe_violation_to_dict_roundtrip(self) -> None:
        """AxeViolation を JSON 化可能な dict に変換できる。"""
        page = _FakeAxePage(
            run_result={
                "violations": [
                    {
                        "id": "image-alt",
                        "impact": "critical",
                        "description": "desc",
                        "helpUrl": "https://dequeuniversity.com/rules/axe/image-alt",
                        "tags": ["wcag2a"],
                        "nodes": [{"target": ["img"]}],
                    }
                ]
            }
        )
        violation = run_axe(page)[0]  # type: ignore[arg-type]

        data = axe_violation_to_dict(violation)

        assert data["rule_id"] == "image-alt"
        assert data["help_url"] == "https://dequeuniversity.com/rules/axe/image-alt"
        assert data["confidence"] == 1.0
        assert data["evidence"]["selector"] == "img"
