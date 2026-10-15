"""システムテスト L3: AutoRun（docs/process/quality/system_test_cases.csv ST-014〜ST-017）。

実行方法:
    make e2e-system

前提データについて（2026-08-23 / R-04c）:
    ST-014・ST-016・ST-017 は csv の前提「AutoRun 対象の設定が完了している」
    「承認待ちステップが存在する」を必要とするが、tests/e2e/system/conftest.py の
    ``system_server`` はテナントとユーザーしか作らない。
    17 ステップを実走させると LLM 実行が必要で現実的でないため、
    **実装が持つ公式な導線だけ**で前提を作る:

    - 成果物ディレクトリ: ``POST /api/sample-report``
      （web/routes/report.py:203-227 が同梱サンプルを自テナントの出力先へ展開する）
    - 承認待ちの前提項目: ``qa_process/stages.json``
      （web/routes/autorun_stages.py:66-67, 98-105 が読む唯一の入力）
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import MEMBER, login

ROOT = Path(__file__).resolve().parents[3]

# 判断 UI の質問は「置かれた前提」の item_id から作られる。
# 対応表 src/autorun/decisions.py:71-148 (_DECISION_SPECS) のキーだけが質問になり、
# それ以外は facts 扱いで質問にならない（同 149-170 build_decisions）。
_ASSUMED_ITEMS: tuple[dict[str, object], ...] = (
    {
        "item_id": "plan-assume-browser",
        "title": "前提: 対象ブラウザ",
        "detail": "指定が無いため Chromium（デスクトップ）を前提とする。",
        "assumed": True,
    },
    {
        "item_id": "plan-assume-auth",
        "title": "前提: 認証・権限",
        "detail": "指定が無いため、未認証で到達できる範囲を対象とする。",
        "assumed": True,
    },
)


def _seed_sample_domain(page: Page, base_url: str) -> str:
    """同梱サンプルを自テナントの出力先へ展開し、ドメインを返す。

    展開先は web/routes/report.py:218-222（``_out() / SAMPLE_DOMAIN``）。
    テナント別の保存先（output/tenants/{slug}/… ・ web/tenancy.py:51-56）は
    サーバー側で解決されるため、テストからはパスを組み立てない。
    """
    resp = page.request.post(f"{base_url}/api/sample-report")
    assert resp.ok, f"POST /api/sample-report 失敗: {resp.status} {resp.text()}"
    return str(resp.json()["domain"])


def _seed_pending_decisions(page: Page, base_url: str) -> str:
    """「人が決めるべき前提」が残った承認待ち状態を作り、ドメインを返す。

    手順（すべて実装の公式な経路）:
      1. GET /api/autorun/stages（web/routes/autorun_stages.py:131-138）で
         現行スキーマの初期パイプラインを取得する（保存はされない）。
         スキーマを手書きしないことで、構造が変わってもテストが嘘をつかない。
      2. POST /api/autorun/decisions（同 170-）が _save_pipeline（同 108-111）で
         ``output/tenants/{slug}/{domain}/qa_process/stages.json`` を作る。
         テナント slug は DB 由来のため決め打ちできないが、**ドメインを実行ごとに
         一意**にすることで、生成された 1 件だけを glob で確実に特定できる。
      3. その stages.json を、前提項目を足した初期パイプラインで置き換える。
    """
    domain = f"st-{uuid.uuid4().hex[:8]}.example.com"

    resp = page.request.get(f"{base_url}/api/autorun/stages?domain={domain}")
    assert resp.ok, f"GET /api/autorun/stages 失敗: {resp.status} {resp.text()}"
    pipeline = resp.json()
    pipeline.pop("domain", None)
    stages = list(pipeline.get("stages") or [])
    assert stages, f"段階が空です: {pipeline}"

    page.request.post(f"{base_url}/api/autorun/decisions", data={"domain": domain})
    matches = list(ROOT.glob(f"output/tenants/*/{domain}/qa_process/stages.json"))
    matches += [ROOT / "output" / domain / "qa_process" / "stages.json"]
    paths = [path for path in matches if path.is_file()]
    assert len(paths) == 1, f"stages.json の場所を特定できません: {paths}"

    first = dict(stages[0])
    first["items"] = [*(first.get("items") or []), *(dict(i) for i in _ASSUMED_ITEMS)]
    stages[0] = first
    paths[0].write_text(
        json.dumps({**pipeline, "stages": stages}, ensure_ascii=False), encoding="utf-8"
    )

    decisions = page.request.get(f"{base_url}/api/autorun/decisions?domain={domain}")
    assert decisions.ok, f"GET /api/autorun/decisions 失敗: {decisions.status}"
    assert decisions.json().get("decisions"), "前提を置いたのに判断項目が作られていません"
    return domain


def _open_autorun(page: Page, base_url: str) -> None:
    """AutoRun システムを開き、受付導線が出るまで待つ。

    旧実装の待受け `#autorun-leadbar button` は実行中しか描画されない
    （static/js/autorun-leadbar.js:34-36 が既定で display:none、描画は
    static/js/autorun.js:895 / autorun-stages.js:541 の実行時のみ）。
    受付の恒常要素は `#autorun-start-btn`（templates/partials/view-auto-run.html:108、
    存在は tests/test_ui_contract.py:156-157 が保証）。
    """
    login(page, base_url, MEMBER)
    page.goto(f"{base_url}/auto-run", wait_until="domcontentloaded")
    page.wait_for_selector("#autorun-start-btn", state="visible")


def _open_decisions_dialog(page: Page, domain: str) -> None:
    """判断 UI を開く。

    唯一の呼び出し元 static/js/autorun-stages.js:581-583 は実行中の承認待ちでしか
    発火しないため、同じ公開 API `window.autorunDecisions.open(domain, jobId)`
    （static/js/autorun-decisions.js:41, 281）を直接呼ぶ。
    ダイアログ内部の取得・描画・選択は実装そのものを通る。
    """
    page.wait_for_function("() => !!(window.autorunDecisions && window.autorunDecisions.open)")
    page.evaluate("(d) => window.autorunDecisions.open(d, '')", domain)


class TestStAutoRun:
    """段階承認 UI・ログ表示・実行結果ページ・承認待ち保持。"""

    def test_st014_approval_decisions_ui_is_operable(
        self, page: Page, system_server: str
    ) -> None:
        """ST-014: 段階承認の判断 UI が開き、推奨が事前選択され、選択を変更できる。

        17 ステップの完遂は LLM 実行を要するため、このサイクルでは承認 UI の
        操作性（表示・事前選択・再選択）までを検証範囲とする。
        """
        _open_autorun(page, system_server)
        domain = _seed_pending_decisions(page, system_server)
        _open_decisions_dialog(page, domain)

        expect(page.locator("#autorun-decisions")).to_be_visible()
        # 推奨が事前選択されている（static/js/autorun-decisions.js:53-56 で
        # answers の初期値に recommended を入れ、同 78 行が is-selected を付ける）
        expect(page.locator(".ard-choice.is-selected").first).to_be_visible()
        expect(page.locator(".ard-choice.is-selected .ard-tag").first).to_have_text("推奨")

        # 別の選択肢へ変更できる（クリックが遮られず、選択が移る）
        other = page.locator(".ard-choice:not(.is-selected)").first
        label = other.locator(".ard-choice-label").inner_text()
        other.click()
        expect(
            page.locator(".ard-choice.is-selected .ard-choice-label", has_text=label)
        ).to_have_count(1)

    def test_st015_log_area_is_not_collapsible(self, page: Page, system_server: str) -> None:
        """ST-015: 実行ログ領域が折りたたみ UI に包まれず常時表示の構造である。

        実行中のログ流入はサーバー実行を要するため、ログ要素が存在し
        <details> 等の折りたたみ配下に無いことを構造として検証する。
        """
        login(page, system_server, MEMBER)
        page.goto(f"{system_server}/auto-run", wait_until="domcontentloaded")
        log = page.locator("#autorun-log, #ar-log-section").first
        expect(log).to_be_attached()
        assert page.evaluate(
            "() => !document.querySelector('#autorun-log')?.closest('details')"
        ), "実行ログが折りたたみ（details）配下にあります"

    def test_st016_report_page_loads(self, page: Page, system_server: str) -> None:
        """ST-016: 実行結果専用ページが JS エラーなく表示される。

        入口は対象ドメイン付きの `/autorun/report/<domain>`
        （web/routes/autorun_report.py:217-229）。ドメイン非依存の `/autorun-report`
        は実装に存在せず 404 になる。成果物ディレクトリが無い場合も 404 のため、
        先に同梱サンプルを展開してから開く。
        """
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        login(page, system_server, MEMBER)
        domain = _seed_sample_domain(page, system_server)

        resp = page.goto(f"{system_server}/autorun/report/{domain}", wait_until="domcontentloaded")
        assert resp is not None and resp.ok, f"応答: {resp.status if resp else 'なし'}"
        expect(page.locator("#arep-main")).to_be_attached()
        assert not errors, f"JS エラー: {errors}"

    def test_st017_pending_approval_survives_navigation(
        self, page: Page, system_server: str
    ) -> None:
        """ST-017: 承認せずに画面を離れて戻っても、勝手に先へ進んでいない。"""
        _open_autorun(page, system_server)
        domain = _seed_pending_decisions(page, system_server)
        _open_decisions_dialog(page, domain)
        expect(page.locator("#autorun-decisions")).to_be_visible()

        # 承認（#autorun-decisions-go）を押さずに離脱して戻る
        page.goto(f"{system_server}/")
        page.goto(f"{system_server}/auto-run", wait_until="domcontentloaded")

        # 実行は始まっておらず、開始前の受付導線が再表示される
        page.wait_for_selector("#autorun-start-btn", state="visible")
        expect(page.locator("#autorun-decisions")).not_to_be_visible()

        # サーバー側も未確定のまま（確定すると全段階が承認され、前提は質問から消える。
        # web/routes/autorun_stages.py:170-215）
        resp = page.request.get(f"{system_server}/api/autorun/decisions?domain={domain}")
        assert resp.ok, f"GET /api/autorun/decisions 失敗: {resp.status}"
        assert resp.json().get("decisions"), "承認していないのに判断項目が消えています"
        stages = page.request.get(f"{system_server}/api/autorun/stages?domain={domain}").json()
        approved = [s for s in stages.get("stages", []) if s.get("status") == "approved"]
        assert not approved, f"承認していないのに承認済み段階があります: {approved}"
