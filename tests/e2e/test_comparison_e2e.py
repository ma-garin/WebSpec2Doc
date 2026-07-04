"""現新比較モード（SPEC-3-3）の実ブラウザ E2E。

demo/site（現行）と demo/site_v2（新）を 2 つのデモサーバーで同時配信し、
run_old_new_comparison で AC-1〜5 を実測検証する。

- AC-1: 2 ターゲットクロールが動き、old/new サブディレクトリにスナップショットが保存される
- AC-2: パス一致で画面が対応付けられる（index/contact/products）
- AC-3: 新側 contact.html の email required 消失が breaking 属性差分として検出される
- AC-4: clock 領域を動的マスクで除外すると画像差分が非有意になる
- AC-5: 新側の存在しないリンクがリンク切れとして検出される

pytest-playwright のセッション fixture が保持する asyncio ループとの衝突を避けるため、
ブラウザ処理は専用スレッドで実行する（tests/e2e/test_capture_realbrowser_e2e.py と同じパターン）。

ポート: spec-3-3_old_new_comparison.md §6-2 の指定どおり 8902（現行）/8903（新）を既定値とする
（環境変数 WEBSPEC2DOC_E2E_COMPARE_OLD_PORT / _NEW_PORT で上書き可能）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

OLD_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_COMPARE_OLD_PORT", "8902"))
NEW_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_COMPARE_NEW_PORT", "8903"))
OLD_URL = f"http://127.0.0.1:{OLD_PORT}"
NEW_URL = f"http://127.0.0.1:{NEW_PORT}"
_THREAD_TIMEOUT_SEC = 150


def _site_is_up(url: str) -> bool:
    try:
        requests.get(f"{url}/", timeout=0.5)
        return True
    except Exception:
        return False


def _start_demo(site_dir: str, port: int) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "demo" / "demo_site.py"),
            "--port",
            str(port),
            "--site-dir",
            site_dir,
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(20):
        if _site_is_up(url):
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip(f"デモサイトが起動しませんでした: {url}")
    return proc


@pytest.fixture(scope="module")
def demo_sites() -> Generator[tuple[str, str], None, None]:
    old_proc = _start_demo("site", OLD_PORT)
    new_proc = _start_demo("site_v2", NEW_PORT)
    yield OLD_URL, NEW_URL
    old_proc.terminate()
    new_proc.terminate()
    old_proc.wait(timeout=5)
    new_proc.wait(timeout=5)


def _run_in_thread(target: Any) -> dict[str, Any]:
    """asyncio ループのない専用スレッドでブラウザ処理を実行する。"""
    result: dict[str, Any] = {}

    def _run() -> None:
        os.environ["WEBSPEC2DOC_ALLOW_LOCAL"] = "1"
        try:
            result["value"] = target()
        except BaseException as exc:  # noqa: BLE001  # スレッド越しに例外を伝搬する
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=_THREAD_TIMEOUT_SEC)
    if thread.is_alive():
        pytest.fail("ブラウザ処理がタイムアウトしました")
    if "error" in result:
        raise result["error"]
    return result


class TestOldNewComparisonE2E:
    def test_ac1_to_ac5(self, demo_sites: tuple[str, str], tmp_path: Path) -> None:
        """AC-1〜AC-5 を実ブラウザで一括検証する。"""
        old_base, new_base = demo_sites

        def _scenario() -> dict[str, Any]:
            from diff.comparison import CATEGORY_INOPERABLE, run_old_new_comparison

            result = run_old_new_comparison(
                [
                    f"{old_base}/index.html",
                    f"{old_base}/contact.html",
                    f"{old_base}/products.html",
                ],
                [
                    f"{new_base}/index.html",
                    f"{new_base}/contact.html",
                    f"{new_base}/products.html",
                ],
                tmp_path,
            )
            return {
                "pairs": result.pairs,
                "findings": result.findings,
                "added": result.added_page_ids,
                "removed": result.removed_page_ids,
                "category_inoperable": CATEGORY_INOPERABLE,
            }

        outcome = _run_in_thread(_scenario)["value"]

        # AC-1: old/new サブディレクトリにスナップショット・スクリーンショットが保存される
        assert (tmp_path / "old" / "screenshots").is_dir()
        assert (tmp_path / "new" / "screenshots").is_dir()
        assert any((tmp_path / "old" / "screenshots").glob("*.png"))
        assert any((tmp_path / "new" / "screenshots").glob("*.png"))

        # AC-2: パス一致で 3 画面（index/contact/products）が対応付く
        assert len(outcome["pairs"]) == 3
        path_methods = {p.method for p in outcome["pairs"]}
        assert "path" in path_methods
        assert outcome["added"] == ()
        assert outcome["removed"] == ()

        findings = outcome["findings"]

        # AC-3: 新側 contact.html の email required 消失が breaking な操作不可として検出される
        required_loss = [
            f
            for f in findings
            if f.category == outcome["category_inoperable"] and "required" in f.detail.lower()
        ]
        assert required_loss, f"required 消失が検出されていない: {[f.detail for f in findings]}"
        assert required_loss[0].severity == "breaking"
        assert required_loss[0].old_evidence is not None
        assert required_loss[0].new_evidence is not None

        # AC-5: 存在しないリンク（/missing-campaign.html）がリンク切れとして検出される
        broken_links = [
            f
            for f in findings
            if f.category == outcome["category_inoperable"] and "リンク切れ" in f.detail
        ]
        assert broken_links, f"リンク切れが検出されていない: {[f.detail for f in findings]}"
        assert any("missing-campaign" in f.detail for f in broken_links)

    def test_ac4_dynamic_mask_suppresses_clock_diff(
        self, demo_sites: tuple[str, str], tmp_path: Path
    ) -> None:
        """clock 領域を動的マスクで除外すると、その分だけ contact 画面の画像差分が減る（AC-4）。

        contact.html は old/new で clock 以外にも本物の差分（AC-3 の required 消失・AC-5 の
        リンク切れに紐づく可視テキスト差）を意図的に持つ。そのため「マスク適用後は
        is_significant=False（絶対閾値未満）」という判定は、実行環境のフォント描画差（CI と
        ローカルサンドボックスでインストール済みフォントが異なり、日本語グリフの
        アンチエイリアシングがページ全体で変わる）によって環境依存で揺れる
        （CONVENTIONS.md 既知の罠 §3: 環境不変の性質を検証すべき）。
        代わりに「マスクを外すと差分が増える／マスクを掛けると減る」という
        環境非依存の相対関係を検証する。絶対閾値でのAC-4検証は
        tests/test_screenshot_diff.py::TestCompareScreenshotsMasked（決定論的な合成画像）が担う。
        """
        old_base, new_base = demo_sites

        def _scenario() -> dict[str, Any]:
            from diff.comparison import run_old_new_comparison

            masked = run_old_new_comparison(
                [f"{old_base}/contact.html"],
                [f"{new_base}/contact.html"],
                tmp_path / "masked",
                mask_selectors=("#clock",),
            )
            unmasked = run_old_new_comparison(
                [f"{old_base}/contact.html"],
                [f"{new_base}/contact.html"],
                tmp_path / "unmasked",
                mask_selectors=(),
            )
            return {
                "masked_diffs": masked.screenshot_diffs,
                "unmasked_diffs": unmasked.screenshot_diffs,
            }

        outcome = _run_in_thread(_scenario)["value"]
        masked_diffs = outcome["masked_diffs"]
        unmasked_diffs = outcome["unmasked_diffs"]
        assert masked_diffs and unmasked_diffs, "画像差分が計算されていない（screenshot_path 欠落の可能性）"
        # clock マスクにより、時刻表示分の差分が確実に減ることを検証する（環境非依存の相対比較）
        assert masked_diffs[0].diff_ratio < unmasked_diffs[0].diff_ratio, (
            f"clock マスクが差分を減らしていない: "
            f"masked={masked_diffs[0].diff_ratio} unmasked={unmasked_diffs[0].diff_ratio}"
        )
