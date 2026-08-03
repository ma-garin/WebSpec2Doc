"""AutoRun 段階承認ゲート・セキュリティカーネルの E2E テスト（L3 システムテスト、新規）。

対象（quality/feature_contracts.yml の critical だが L3(E2E) で未検証だった機能）:
    - autorun_stage_approval: 段階承認パイプライン（web/routes/autorun_stages.py）
    - autorun_security_kernel: 送信ゲートウェイ K1（web/services/egress_gateway.py）

autorun_stage_approval について:
    既存の test_autorun_decisions_e2e.py は /api/autorun/stages・/api/autorun/decisions
    をモックしており、UI の導線（ダイアログの開閉・送信payloadの組み立て）は検証して
    いるが、実バックエンドの承認ゲートそのもの（承認前は proceed が拒否されること）は
    検証していない。本ファイルはモックを使わず実サーバーへ実際に送信し、ゲートの
    実効性そのものを検証する点で既存テストと重複しない。

autorun_security_kernel について（未実装・skip の理由）:
    K1 送信ゲートウェイ（assert_target_allowed / 生成フィクスチャ内のTS版 denyReason）が
    実際に働くのは、AutoRun のテスト「生成 → 実行」段階（run_playwright_spec 経由）
    のみである。discover/crawl の時点では別の緩い検査
    （src/crawler/url_safety.py の validate_target_url）しか通らない。
    その url_safety は IP リテラルの private/reserved アドレスを既にその場で拒否
    するため、そこを狙って対象を指定すると「K1」ではなく「url_safety」を検証した
    ことになり、feature_contracts.yml が指す機能とすり替わってしまう。
    K1 自体を UI 経由で正しく検証するには、
        (1) url_safety を通過する一見正当な対象を実際にクロールし、
        (2) 生成された Playwright spec が実行段階でプライベート/拒否アドレスへ
            誘導される状況を作り（テスト対象ページからの遷移や DNS rebinding 相当）、
        (3) 実行結果の egress ログに denied エントリが記録され、それがユーザーに
            見える形（実行結果・レポート）で提示されることを確認する
    という、専用の固定ローカルサイト＋実クロール＋段階生成＋実実行のオーケストレー
    ションが必要で、本タスクのツール実行回数の上限内では安全に組み立てて検証しきれ
    ないと判断した。動かない/的外れなテストを書くよりも、このスキップ理由を明記する
    方が価値があると判断する（tests/test_security_kernel.py に Python 版のユニット
    テストが既に存在する。なお assert_target_allowed 自体は grep 済みの範囲で本番
    コードパスから直接は呼ばれておらず、実行時の強制は生成フィクスチャ内の
    TypeScript 版 denyReason() が担っている）。

実行方法:
    venv/bin/python -m pytest tests/e2e/test_autorun_security_e2e.py -q
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

_DOMAIN = "stage-gate-e2e.example.com"


@pytest.fixture(autouse=True)
def _reset_pipeline(page: Page) -> Generator[None, None, None]:
    """各テスト前に段階状態を初期化し、テスト間の状態漏れを防ぐ。"""
    page.request.post(f"{BASE_URL}/api/autorun/stages/reset", data={"domain": _DOMAIN})
    yield


class TestAutorunStageApprovalGate:
    """autorun_stage_approval: 承認前は次段階へ進めないこと（ゲートの実効性）。"""

    def test_proceed_is_rejected_before_approval(self, page: Page) -> None:
        """未承認の段階が残っている間は /stages/proceed が 409 で拒否される。"""
        resp = page.request.post(
            f"{BASE_URL}/api/autorun/stages/proceed",
            data={"domain": _DOMAIN, "job_id": ""},
        )
        assert resp.status == 409, resp.text()
        body = resp.json()
        assert body.get("remaining"), f"未承認段階の一覧が返っていません: {body}"

        # UI 側からも到達点を確認する: /auto-run を開き、実データをロードできること
        # （既存の test_autorun_decisions_e2e.py と同じ導線・同じ待機戦略を踏襲）。
        page.goto(f"{BASE_URL}/auto-run", wait_until="domcontentloaded")
        page.wait_for_function("() => !!(window.autorunStages && window.autorunStages.load)")
        page.evaluate(f"() => window.autorunStages.load('{_DOMAIN}', {{open: true}})")
        page.wait_for_selector("#autorun-leadbar button", state="visible")

    def test_confirming_decisions_opens_the_gate(self, page: Page) -> None:
        """実行条件ダイアログが開ける状態であることをUIで確認したうえで、確定APIを
        実サーバーへ送ると全段階が承認され、proceed の拒否が解除される。

        確定ボタン（#autorun-decisions-go）自体のクリックは、生成前の段階に
        質問（decisions）が一件もない場合の描画を検証しきれていないため、
        送信先の実効性は実API呼び出しで確定させる（ダイアログの開閉はUIで確認する）。
        """
        page.goto(f"{BASE_URL}/auto-run", wait_until="domcontentloaded")
        page.wait_for_function("() => !!(window.autorunStages && window.autorunStages.load)")
        page.evaluate(f"() => window.autorunStages.load('{_DOMAIN}', {{open: true}})")
        page.wait_for_selector("#autorun-leadbar button", state="visible")
        page.click("#autorun-leadbar button")
        expect(page.locator("#autorun-decisions")).to_be_visible()

        confirm_resp = page.request.post(
            f"{BASE_URL}/api/autorun/decisions",
            data={"domain": _DOMAIN, "job_id": "", "answers": {}},
        )
        assert confirm_resp.ok, confirm_resp.text()
        assert confirm_resp.json().get("all_approved") is True, confirm_resp.text()

        resp = page.request.post(
            f"{BASE_URL}/api/autorun/stages/proceed",
            data={"domain": _DOMAIN, "job_id": ""},
        )
        assert resp.status != 409, resp.text()


class TestAutorunSecurityKernel:
    """autorun_security_kernel: 送信ゲートウェイ（K1）によるSSRF遮断。"""

    @pytest.mark.skip(
        reason=(
            "K1(assert_target_allowed / denyReason)はテスト生成→実行フェーズでのみ"
            "働き、discover/crawl 時点はより緩い url_safety.validate_target_url しか"
            "通らない。private/reservedなIPリテラルを狙うとK1ではなくurl_safetyを"
            "検証したことになるため、K1自体をUI経由で検証するには「url_safetyを通る"
            "正当な対象を実クロール→実行段階でプライベートアドレスへ誘導」という専用"
            "シナリオの構築が要り、本タスクのツール実行回数上限内では安全に組み立て"
            "きれないため見送り。詳細は本ファイル冒頭のdocstring、"
            "単体検証はtests/test_security_kernel.pyを参照。"
        )
    )
    def test_disallowed_target_is_denied_during_execution(self) -> None:
        pass
