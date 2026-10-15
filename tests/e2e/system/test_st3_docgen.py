"""システムテスト L3: ドキュメント作成（docs/process/quality/system_test_cases.csv ST-010〜ST-013)。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import MEMBER, open_docs_system

ROOT = Path(__file__).resolve().parents[3]


def open_generate_view(page: Page) -> None:
    """ドキュメント作成システムの生成ビュー（#view-generate）を開く。

    `#url-input` は `#view-generate` の中にあり（templates/partials/view-generate.html:2,33）、
    `/` の初期表示（dashboard）では非表示のまま。サイドバーの主要アクション
    `#add-site-btn`（templates/index.html:46・data-system="docs"）が
    `openAddSite()` → `switchView('generate')` を行う（static/js/core.js:312-321）。
    """
    page.locator("#add-site-btn").click()
    expect(page.locator("#view-generate")).to_be_visible()
    expect(page.locator("#url-input")).to_be_visible()


def seed_past_crawl_run(page: Page, base_url: str) -> str:
    """実行履歴の前提データ（過去の crawl 実行）を製品と同じ書式で作る。

    `POST /api/sample-report` は同梱成果物を出力先へ展開するだけで、利用実績
    （usage_log.jsonl）を一切書かない（web/routes/report.py:203-227）。一方、実行履歴
    `GET /api/history/runs` の出所は usage_log.jsonl と実行中ジョブのみ
    （web/routes/auto_run.py:198-211 → web/services/usage_tracker.build_run_history:465-477）。
    つまりサンプルレポートの展開だけでは実行履歴に行は増えない（実装どおりの挙動）。
    そこで、製品自身の記録関数 `record_usage`（usage_tracker.py:87-136）で 1 件を追加する。

    出力先はテナントスコープ済み（web/tenancy.py:51-56 の `output/tenants/<slug>`）。
    slug の生成規則に依存しないよう、直前に展開したサンプルの位置から実測で特定する。
    """
    from web.config import OUTPUT_DIR, SAMPLE_DOMAIN
    from web.services.usage_tracker import record_usage

    resp = page.request.post(f"{base_url}/api/sample-report")
    assert resp.ok, f"サンプルレポート作成失敗: {resp.status} {resp.text()}"

    output_root = OUTPUT_DIR if Path(OUTPUT_DIR).is_absolute() else ROOT / OUTPUT_DIR
    # 直前の展開先＝作り直された（inode が新しい）ディレクトリ。
    # mtime では特定できない: shutil.copytree が同梱元の更新時刻を複製先へ複写するため
    # （web/routes/report.py:224 の copytree → copystat）。作成時刻 ctime で選ぶ。
    deployed = sorted(
        Path(output_root).glob(f"**/{SAMPLE_DOMAIN}"), key=lambda p: p.stat().st_ctime
    )
    assert deployed, f"サンプルの展開先が見つかりません: {output_root}/**/{SAMPLE_DOMAIN}"
    scoped_out = deployed[-1].parent

    log_path = record_usage(
        scoped_out,
        event="crawl",
        domain=SAMPLE_DOMAIN,
        screen_count=3,
        test_condition_count=2,
        document_count=1,
    )
    assert log_path is not None, f"利用実績の記録に失敗しました: {scoped_out}"
    return str(SAMPLE_DOMAIN)


class TestStDocGen:
    """URL 指定の生成ウィザード・実行履歴・成果物参照。"""

    def test_st010_generate_starts_with_valid_url(self, page: Page, system_server: str) -> None:
        """ST-010: 有効な URL で探索を開始すると進捗（または次段階）が現れる。

        クロール対象はサーバー自身のログインページ（WEBSPEC2DOC_ALLOW_LOCAL=1）。
        成果物の完成までは待たず、「実行が開始された」ことの肯定的な目印
        （進捗表示・発見画面の逐次表示 or 第1ステップの完了）までを検証する。
        """
        open_docs_system(page, system_server, MEMBER)
        open_generate_view(page)
        page.locator("#url-input").fill(f"{system_server}/auth/login")
        page.locator("#discover-btn").click()
        # 押下直後に進捗が動き出す（static/js/wizard.js:427-434 で
        # #discover-loading を表示し、#discover-status を初期化する）
        expect(page.locator("#discover-loading")).to_be_visible()
        page.wait_for_function(
            """() => {
                const feed = document.querySelector('#discover-live-feed');
                const status = document.querySelector('#discover-status');
                const msg = document.querySelector('#url-input-message');
                const p1 = document.querySelector('#wizard-p1');
                return (feed && feed.children.length > 0)
                    || (status && status.textContent.trim().length > 0)
                    || (msg && msg.textContent.trim().length > 0)
                    || (p1 && p1.offsetParent === null);
            }""",
            timeout=60_000,
        )
        # 失敗表示（wizard.js:429 の discover-status-error）を「開始した」に数えない
        expect(page.locator("#discover-status")).not_to_have_class(
            re.compile("discover-status-error")
        )

    def test_st011_invalid_url_shows_validation_message(
        self, page: Page, system_server: str
    ) -> None:
        """ST-011: 不正な URL では検証メッセージが出て、ウィザードは進まない。"""
        open_docs_system(page, system_server, MEMBER)
        open_generate_view(page)
        page.locator("#url-input").fill("これはURLではない")
        page.locator("#discover-btn").click()
        # 実装は URL_FORMAT_RE で弾き、#url-input-message に文言を出す
        # （static/js/wizard.js:11-19, 23-26。discoverUrls は wizard.js:420 で中断）
        expect(page.locator("#url-input-message")).to_contain_text(re.compile(r"\S"))
        expect(page.locator("#wizard-p1")).to_be_visible()

    def test_st012_run_history_shows_past_run(self, page: Page, system_server: str) -> None:
        """ST-012: 実行履歴に過去の実行が表示される（前提データはテスト内で作る）。"""
        open_docs_system(page, system_server, MEMBER)
        domain = seed_past_crawl_run(page, system_server)

        page.goto(f"{system_server}/")
        page.locator(
            "#nav-docs-run-history-btn:visible, #nav-run-history-btn:visible"
        ).first.click()
        expect(page.locator("#view-run-history")).to_be_visible()
        # crawl は docs 系の実行履歴に含まれる種別（static/js/view-run-history.js:16-19）
        expect(page.locator("#view-run-history")).to_contain_text(domain)

    def test_st013_file_preview(self, page: Page, system_server: str) -> None:
        """ST-013: 成果物ファイルのプレビュー表示。"""
        pytest.skip(
            "ST-013: プレビューを開く導線のセレクタが実測未確定のためサイクル1では未実装"
            "（モーダル自体は #file-preview-modal として存在を確認済み）"
        )
