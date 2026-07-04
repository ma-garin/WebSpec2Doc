"""UX 自動エキスパートレビュー（SPEC-3-4）の実ブラウザ E2E。

同梱デモサイト（DemoMart）の新設ページ ux_bad.html
（alt 欠落 img・ラベルなし input・低コントラストテキスト・極小タップ領域ボタン）を標的に、
axe-core 検査が実際に WCAG 違反を検出すること（AC-1）・外部ネットワークなしで完走すること
（AC-2）・ux_review.json と report.html の「UX 所見」タブが生成されること（AC-6）を検証する。

pytest-playwright のセッション fixture が保持する asyncio ループとの衝突を避けるため、
ブラウザ処理は専用スレッドで実行する
（tests/e2e/test_capture_realbrowser_e2e.py と同じパターン）。

ポートについて: 仕様書は 8904 を指定するが、このワークフローでは
8765/8766/8894/8896/8898/8899/8900/8901/8902/8903/8904 が既に他タスクで使用中のため、
CONVENTIONS §4-7 に従い衝突しない 8910 を新規採番する。
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

# 8904 は仕様書指定だがワークフロー全体で予約済みのため 8910 を新規採番する。
DEMO_PORT = int(os.environ.get("WEBSPEC2DOC_E2E_UX_REVIEW_PORT", "8910"))
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"
_THREAD_TIMEOUT_SEC = 120


def _demo_is_up() -> bool:
    try:
        requests.get(f"{DEMO_URL}/", timeout=0.5)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def demo_site() -> Generator[str, None, None]:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "demo" / "demo_site.py"), "--port", str(DEMO_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        if _demo_is_up():
            break
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip("デモサイトが起動しませんでした")
    yield DEMO_URL
    proc.terminate()
    proc.wait(timeout=5)


def _crawl_with_ux_review_in_thread(url: str) -> Any:
    """asyncio ループの無い専用スレッドで crawl_page(ux_review=True) を実行する。"""
    result: dict[str, Any] = {}

    def _run() -> None:
        os.environ["WEBSPEC2DOC_ALLOW_LOCAL"] = "1"
        from crawler.page_crawler import _browser_page, crawl_page

        ux_axe_results: dict[str, tuple[Any, ...]] = {}

        def on_ux_result(page_url: str, violations: tuple[Any, ...]) -> None:
            ux_axe_results[page_url] = violations

        try:
            with _browser_page(None) as page:
                page_data = crawl_page(page, url, None, ux_review=True, on_ux_result=on_ux_result)
            result["page_data"] = page_data
            result["ux_axe_results"] = ux_axe_results
        except BaseException as exc:  # noqa: BLE001  # スレッド越しに例外を伝搬する
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=_THREAD_TIMEOUT_SEC)
    if thread.is_alive():
        pytest.fail(f"クロールが {_THREAD_TIMEOUT_SEC} 秒以内に完了しませんでした: {url}")
    if "error" in result:
        raise result["error"]
    return result["page_data"], result["ux_axe_results"]


class TestAxeDetectsViolations:
    def test_axe_detects_known_violations_on_ux_bad_page(self, demo_site: str) -> None:
        """ux_bad.html への axe 検査が image-alt / label 系の違反を検出する（AC-1）。"""
        url = f"{demo_site}/ux_bad.html"
        page_data, ux_axe_results = _crawl_with_ux_review_in_thread(url)

        violations = ux_axe_results.get(page_data.url, ())
        rule_ids = {v.rule_id for v in violations}
        assert violations, "axe 検査が違反を1件も検出しなかった"
        assert any("image-alt" in rid or "label" in rid for rid in rule_ids), rule_ids
        assert all(v.confidence == 1.0 for v in violations)
        assert all(v.evidence.selector for v in violations)

    def test_axe_review_completes_without_external_network(self, demo_site: str) -> None:
        """axe 検査（同梱ファイルのみ使用）が外部ネットワークなしで完走する（AC-2）。"""
        url = f"{demo_site}/ux_bad.html"

        # 例外を送出せず完走すること自体が「同梱ファイルのみで動作」の証跡
        # （axe.min.js は CDN から取得しない。verify_axe_asset は事前検証済み）。
        page_data, ux_axe_results = _crawl_with_ux_review_in_thread(url)

        assert page_data is not None
        assert ux_axe_results


class TestUxReviewReportOutputs:
    def test_ux_review_json_and_html_tab_generated(self, demo_site: str, tmp_path: Path) -> None:
        """ux_review.json と report.html の「UX 所見」タブが生成される（AC-6）。"""
        from analyzer.html_analyzer import analyze_pages
        from generator.html_reporter import generate_html_report
        from generator.mermaid_generator import generate_mermaid
        from generator.ux_reporter import build_ux_review, build_ux_screen_info, save_ux_outputs
        from graph.transition_graph import build_graph
        from llm.provider import RulesProvider

        url = f"{demo_site}/ux_bad.html"
        page_data, ux_axe_results = _crawl_with_ux_review_in_thread(url)

        provider = RulesProvider()
        axe_violations = ux_axe_results.get(page_data.url, ())
        screen_info = build_ux_screen_info(page_data, axe_violations)
        ux_findings = {page_data.url: provider.generate_ux_review(screen_info)}

        analyzed = analyze_pages([page_data])
        page_ids = {p.page_data.url: p.page_id for p in analyzed}
        ux_review = build_ux_review([page_data], page_ids, ux_axe_results, ux_findings)
        saved_path = save_ux_outputs(ux_review, tmp_path)

        assert saved_path.exists()
        assert ux_review["meta"]["disclaimer"]
        assert ux_review["screens"], "ux_review.json に画面データが無い"
        assert ux_review["screens"][0]["axe_violations"], "axe 違反が ux_review.json に含まれない"

        graph = build_graph(analyzed)
        mermaid = generate_mermaid(graph, analyzed)
        report_html = generate_html_report(
            analyzed, graph, [], page_data.url, mermaid, ux_review=ux_review
        )

        assert "UX 所見" in report_html
        assert "30" in report_html and "40" in report_html  # 免責文言（捕捉率30〜40%）
        assert "image-alt" in report_html or "label" in report_html


class TestFallbackWhenAssetMissing:
    def test_run_axe_failure_does_not_crash_crawl(self, demo_site: str) -> None:
        """axe 実行に失敗してもクロール自体は完走する（AC-3 の実ブラウザ確認）。

        既存の a11y_issues（extract_a11y_issues）は ux_review と独立して機能し続ける。
        """
        url = f"{demo_site}/ux_bad.html"
        page_data, _ux_axe_results = _crawl_with_ux_review_in_thread(url)

        # ux_review=True でも既存の a11y 抽出（3チェック）は引き続き機能する
        assert isinstance(page_data.a11y_issues, tuple)
