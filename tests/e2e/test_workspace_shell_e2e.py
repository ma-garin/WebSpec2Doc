"""統合ワークスペース（workspace.html）のシェル E2E。

デザイン言語の契約（docs/plan の統合計画 Phase A）を実画面で担保する:

1. コンソールエラー 0 件（type == "error" と pageerror の両方）
2. 1440×900 / 1280×800 でページスクロールが出ない（縦・横とも）
3. レールの強調（`.rail [data-view].on`）がちょうど 1 個

「要素があるか」はブラウザ無しで分かるので tests/test_ui_contract.py が見る。
ここはブラウザでしか壊れ方が見えないもの（レイアウトのはみ出し・JS の実行時
エラー・レール強調の二重点灯）だけを見る。

実行:
    pytest tests/e2e/test_workspace_shell_e2e.py -q
    WEBSPEC2DOC_E2E_EXTERNAL=1 pytest tests/e2e/test_workspace_shell_e2e.py -q
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
import requests
from playwright.sync_api import Browser, ConsoleMessage, Page

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

# 解析済みサイトが 1 件必要。無い環境では /sites/<domain>/<ws> が "/" へ 302 され、
# 検証対象を開けない（その場合は緑にせず、理由を出して skip する）。
DOMAIN = os.environ.get("WEBSPEC2DOC_E2E_DOMAIN", "demomart")

WORKSPACES = ("spec", "tests", "changes", "schedule", "report", "team")
VIEWPORTS = ((1440, 900), (1280, 800))


def _paths() -> list[str]:
    return ["/"] + [f"/sites/{DOMAIN}/{ws}" for ws in WORKSPACES]


@pytest.fixture(scope="module", autouse=True)
def require_analyzed_site() -> None:
    """検証対象のサイトが解析済みであることを先に確かめる。

    未解析だと全ワークスペースがホームへ 302 され、ホームだけを 7 回見て
    「緑」になる（ゲートが形骸化する）。開ける状態でなければ skip する。
    """
    try:
        response = requests.get(f"{BASE_URL}/sites/{DOMAIN}/spec", timeout=5, allow_redirects=False)
    except requests.RequestException as exc:  # pragma: no cover - 環境依存
        pytest.skip(f"{BASE_URL} に接続できません: {exc}")
    if response.status_code != 200:
        pytest.skip(
            f"/sites/{DOMAIN}/spec が {response.status_code} を返しました"
            f"（解析済みサイトが必要）。WEBSPEC2DOC_E2E_DOMAIN で対象を指定してください。"
        )


@pytest.fixture(params=VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def sized_page(request: pytest.FixtureRequest, browser: Browser) -> Generator[Page, None, None]:
    """指定ビューポートのページ。親 conftest の page fixture は 1280×800 固定のため自前で作る。"""
    width, height = request.param
    context = browser.new_context(viewport={"width": width, "height": height}, locale="ja-JP")
    page = context.new_page()
    # driver.js のツアーはオーバーレイでクリックを遮り、レイアウト計測も歪める。
    page.add_init_script(
        "try { localStorage.setItem('webspec2doc.onboarding.tour-completed', '1'); }"
        " catch (e) { /* private mode 等では何もしない */ }"
    )
    page.set_default_timeout(45_000)
    page.set_default_navigation_timeout(60_000)
    try:
        yield page
    finally:
        context.close()


def _open(page: Page, path: str) -> list[str]:
    """path を開き、収集したエラー（console error / pageerror）を返す。"""
    errors: list[str] = []

    def _on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(f"console: {message.text}")

    page.on("console", _on_console)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.goto(f"{BASE_URL}{path}", wait_until="networkidle")
    page.wait_for_timeout(500)  # 遅延描画（API 応答後の描画）で出るエラーも拾う
    return errors


@pytest.mark.parametrize("path", _paths())
class TestWorkspaceShell:
    """全ワークスペースを 2 つのビューポートで開く。"""

    def test_no_console_errors(self, sized_page: Page, path: str) -> None:
        errors = _open(sized_page, path)
        assert not errors, f"{path} でエラー {len(errors)} 件: " + " | ".join(errors[:5])

    def test_page_does_not_scroll(self, sized_page: Page, path: str) -> None:
        """レール＋一覧＋作業面は画面内に収める（ページ自体はスクロールさせない）。

        はみ出しは実ブラウザでしか出ないため E2E に置く。中身のスクロールは
        各ペイン（.list / .pb）が内部で持つ。
        """
        _open(sized_page, path)
        metrics = sized_page.evaluate(
            "() => ({"
            " scrollHeight: document.documentElement.scrollHeight,"
            " innerHeight: window.innerHeight,"
            " scrollWidth: document.documentElement.scrollWidth,"
            " innerWidth: window.innerWidth })"
        )
        assert (
            metrics["scrollHeight"] <= metrics["innerHeight"]
        ), f"{path} が縦にはみ出した: {metrics['scrollHeight']} > {metrics['innerHeight']}"
        assert (
            metrics["scrollWidth"] <= metrics["innerWidth"]
        ), f"{path} が横にはみ出した: {metrics['scrollWidth']} > {metrics['innerWidth']}"

    def test_exactly_one_rail_item_is_active(self, sized_page: Page, path: str) -> None:
        """現在地の表示は 1 箇所だけ（二重点灯・消灯のどちらも不可）。"""
        _open(sized_page, path)
        active = sized_page.locator(".rail [data-view].on")
        assert active.count() == 1, f"{path} のレール強調が {active.count()} 個"
