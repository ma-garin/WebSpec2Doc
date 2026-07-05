"""ユーザーガイドのスクロール根治強化の E2E テスト（R3-12）。

背景:
    「サイトを追加」画面（generate）の実行中のみ使う is-executing / is-reporting
    フラグが #app-content に残留したまま他画面へ遷移すると、その画面が
    overflow:hidden・height:100% に固定されスクロール不能になる不具合があった。
    switchView() 内の後始末（static/js/core.js）に加え、起動時のディープリンク
    復元経路（DOMContentLoaded ハンドラ）でも同じ後始末を明示的に行う二重防御を
    追加した（static/js/core.js）。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import os
import re

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


class TestGuideScrollAfterDeeplink:
    def test_guide_scrolls_after_deeplink_from_executing(self, page: Page) -> None:
        page.goto(BASE_URL)

        # 「サイトを追加」画面の実行中フラグが残留した状態を人工的に再現する。
        page.evaluate("document.getElementById('app-content').classList.add('is-executing')")

        # ディープリンク復元経路（起動時 DOMContentLoaded ハンドラ）を
        # ページ遷移なしで再現する: パスを /user-guide に変えて DOMContentLoaded を
        # 再発火させる（history.pushState はハッシュではなくパス遷移だが、
        # このハンドラが「起動時のディープリンク解決」を担う唯一の経路である）。
        page.evaluate(
            """() => {
                history.pushState({}, '', '/user-guide');
                window.dispatchEvent(new Event('DOMContentLoaded'));
            }"""
        )

        # 実行中フラグが解除されていること（残留していないこと）
        classes = page.evaluate("document.getElementById('app-content').className")
        assert "is-executing" not in classes, f"is-executing が残留している: {classes}"
        assert "is-reporting" not in classes, f"is-reporting が残留している: {classes}"

        # ユーザーガイド画面が実際に表示されていること
        expect(page.locator("#view-user-guide")).to_have_class(re.compile(r"is-active"))

        # ガイド本文がスクロール可能であること（overflow:hidden に固定されていないこと）
        scrollable = page.evaluate(
            """() => {
                const el = document.getElementById('app-content');
                return el.scrollHeight > el.clientHeight;
            }"""
        )
        assert scrollable, "ガイド画面がスクロール不能になっている（is-executing 残留の再発）"

        overflow = page.evaluate(
            "getComputedStyle(document.getElementById('app-content')).overflowY"
        )
        assert overflow in ("auto", "scroll"), f"#app-content が overflow:hidden のまま: {overflow}"
