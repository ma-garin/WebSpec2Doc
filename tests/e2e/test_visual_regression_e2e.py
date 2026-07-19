"""ビジュアルリグレッションテスト（L3 システムテスト）。

目的:
    INC-2026-001 の根本原因（スタイル崩れ・z-index・余白不正）を
    機械的に検出する。スクリーンショットをベースラインと比較し、
    視覚的変化を自動で検知する。

ベースライン管理:
    初回実行: pytest tests/e2e/test_visual_regression_e2e.py --update-snapshots
    更新時:   pytest tests/e2e/test_visual_regression_e2e.py --update-snapshots
    通常実行: pytest tests/e2e/test_visual_regression_e2e.py (比較モード)

実行方法:
    make verify-ui
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import pytest
from playwright.sync_api import Page

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# ビジュアル差分の許容閾値（0.0-1.0）
# 0.03 = ピクセル平均輝度差が 3% 以内ならば PASS
VISUAL_THRESHOLD = 0.03


def _assert_visual_match(page: Page, name: str, threshold: float = VISUAL_THRESHOLD) -> None:
    """スクリーンショットをベースラインと比較する。

    - ベースラインが存在しない場合: 作成して pytest.skip（次回から比較）
    - ベースラインが存在する場合: ピクセル比較、差分 > threshold で FAIL
    - pytest --update-snapshots フラグがある場合: ベースラインを強制更新
    """
    baseline_path = SNAPSHOTS_DIR / f"{name}.png"
    page.add_style_tag(
        content="""
        *, *::before, *::after {
            animation: none !important;
            transition: none !important;
            caret-color: transparent !important;
        }
        """
    )
    current_bytes = page.screenshot(full_page=False, animations="disabled", caret="hide")

    update_mode = "--update-snapshots" in str(
        pytest.ini_options if hasattr(pytest, "ini_options") else ""
    )

    if not baseline_path.exists() or update_mode:
        baseline_path.write_bytes(current_bytes)
        if update_mode:
            return  # 更新モードでは比較しない
        pytest.skip(
            f"ビジュアルベースラインを作成しました: {baseline_path.name}\n"
            "次回実行時から比較モードになります。"
        )
        return

    baseline_bytes = baseline_path.read_bytes()

    # バイト完全一致（最速チェック）
    if baseline_bytes == current_bytes:
        return

    # Pillow が使える場合: ピクセルレベル差分比較
    try:
        import numpy as np  # type: ignore[import]
        from PIL import Image  # type: ignore[import]

        img_base = Image.open(io.BytesIO(baseline_bytes)).convert("RGB")
        img_curr = Image.open(io.BytesIO(current_bytes)).convert("RGB")

        if img_base.size != img_curr.size:
            # サイズ違いはリグレッション確定
            diff_path = SNAPSHOTS_DIR / f"{name}_current.png"
            diff_path.write_bytes(current_bytes)
            pytest.fail(
                f"ビジュアルリグレッション（サイズ変化）: "
                f"baseline={img_base.size}, current={img_curr.size}\n"
                f"現在画像: {diff_path}"
            )

        arr_base = np.array(img_base, dtype=float)
        arr_curr = np.array(img_curr, dtype=float)
        diff_ratio = float(np.abs(arr_base - arr_curr).mean()) / 255.0

        if diff_ratio > threshold:
            diff_path = SNAPSHOTS_DIR / f"{name}_current.png"
            diff_path.write_bytes(current_bytes)
            pytest.fail(
                f"ビジュアルリグレッション検出: diff={diff_ratio:.4f} (閾値: {threshold})\n"
                f"  ベースライン: {baseline_path}\n"
                f"  現在:         {diff_path}\n"
                f"  ベースライン更新: pytest tests/e2e/ --update-snapshots"
            )

    except ImportError:
        # Pillow/numpy 未インストール: SHA256 ハッシュ比較
        base_hash = hashlib.sha256(baseline_bytes).hexdigest()[:16]
        curr_hash = hashlib.sha256(current_bytes).hexdigest()[:16]
        if base_hash != curr_hash:
            diff_path = SNAPSHOTS_DIR / f"{name}_current.png"
            diff_path.write_bytes(current_bytes)
            pytest.fail(
                f"ビジュアルリグレッション検出（ハッシュ比較）\n"
                f"  baseline: {base_hash}, current: {curr_hash}\n"
                f"  現在画像: {diff_path}\n"
                f"  Pillow をインストールするとピクセルレベル比較が有効になります: pip install Pillow numpy"
            )


class TestVisualRegressionAppLoad:
    """アプリ読み込み画面のビジュアルリグレッション。"""

    def test_app_initial_state_1280x800(self, page: Page) -> None:
        """初期状態 1280×800 のビジュアルをベースラインと比較する。"""
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        _assert_visual_match(page, "app_initial_1280x800")

    def test_app_initial_state_1366x768(self, page: Page) -> None:
        """初期状態 1366×768 のビジュアルをベースラインと比較する。"""
        page.set_viewport_size({"width": 1366, "height": 768})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        _assert_visual_match(page, "app_initial_1366x768")

    def test_app_initial_state_1920x1080(self, page: Page) -> None:
        """初期状態 1920×1080 のビジュアルをベースラインと比較する。"""
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        _assert_visual_match(page, "app_initial_1920x1080")


class TestVisualRegressionAutoRun:
    """AutoRun ビューのビジュアルリグレッション。"""

    def _navigate_to_autorun(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        autorun_nav = page.locator(".app-nav-item").filter(has_text="AutoRun").first
        if autorun_nav.count() > 0:
            autorun_nav.click()
            page.wait_for_selector("#view-auto-run", state="attached")

    def test_autorun_idle_state(self, page: Page) -> None:
        """AutoRun アイドル状態のビジュアル。"""
        page.set_viewport_size({"width": 1280, "height": 800})
        self._navigate_to_autorun(page)
        _assert_visual_match(page, "autorun_idle_1280x800")

    def test_autorun_approval_modal(self, page: Page) -> None:
        """承認モーダル表示状態のビジュアル（INC-2026-001 防止の核心）。"""
        page.set_viewport_size({"width": 1280, "height": 800})
        self._navigate_to_autorun(page)
        # モーダルをJSで開き、視覚的状態を検証
        page.evaluate(
            """() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }"""
        )
        page.wait_for_selector("#autorun-approval-modal", state="visible")
        _assert_visual_match(page, "autorun_approval_modal_1280x800", threshold=0.04)

    def test_autorun_approval_modal_1366x768(self, page: Page) -> None:
        """承認モーダル 1366×768 でのビジュアル（モーダルオーバーフロー検知）。"""
        page.set_viewport_size({"width": 1366, "height": 768})
        self._navigate_to_autorun(page)
        page.evaluate(
            """() => {
            const modal = document.getElementById('autorun-approval-modal');
            if (modal) modal.style.display = 'flex';
        }"""
        )
        page.wait_for_selector("#autorun-approval-modal", state="visible")
        _assert_visual_match(page, "autorun_approval_modal_1366x768", threshold=0.04)
