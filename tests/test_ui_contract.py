"""UI 契約テスト（Flask テストクライアント / ブラウザ不要）。

E2E を 214 → 42 件に絞った際、「要素が存在するか」「初期値は何か」といった
**ブラウザ起動に値しない検証**を E2E から外した。その分をここで担保する。

方針（docs/research/test-speedup-survey.md）:
- ブラウザでしか壊れ方が見えないもの（レイアウト崩れ・重なり・キーボード操作）は E2E に残す
- サーバがレンダリングした HTML を読めば分かることは、ここで秒以下で検証する

**ここで担保できないもの（正直な明示）**:
JavaScript の実行が必要な振る舞い——タブ切替、フィルタ検索、ページャ、
表示/非表示のトグル——は、本ファイルでも E2E でも現在**未検証**である。
「未検証」であって「問題なし」ではない。担保するには JS のテスト基盤
（jsdom 等）の導入が必要で、それは未着手。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod


def _html(path: str) -> str:
    res = appmod.app.test_client().get(path)
    assert res.status_code == 200, f"{path} が {res.status_code} を返しました"
    return res.get_data(as_text=True)


@pytest.fixture(scope="module")
def spa() -> str:
    """SPA 本体（全ビューを内包する index.html）。"""
    return _html("/")


@pytest.fixture(scope="module")
def systems() -> str:
    """システム選択ハブ。"""
    return _html("/systems")


# ---------------------------------------------------------------- SPA の骨格


class TestViewsExist:
    """各ビューが SPA に含まれること（旧: test_ui_smoke の *_accessible 系）。"""

    @pytest.mark.parametrize(
        "view_id",
        [
            "view-dashboard",
            "view-generate",
            "view-auto-run",
            "view-testcases",
            "view-run-history",
            "view-qa-quality",
            "view-viewpoints",
            "view-user-guide",
            "view-references",
            "view-settings",
        ],
    )
    def test_view_section_present(self, spa: str, view_id: str) -> None:
        assert f'id="{view_id}"' in spa


class TestSystemScoping:
    """ナビの系（ドキュメント作成 / AutoRun / 共通）の宣言。"""

    @pytest.mark.parametrize(
        ("label", "system"),
        [
            ("ホーム", "docs"),
            ("新規解析", "docs"),
            ("テストケース", "docs"),
            ("品質観点", "docs"),
            ("観点管理", "docs"),
            ("AutoRun", "autorun"),
            ("実行履歴", "autorun"),
            ("ユーザーガイド", "common"),
            ("参考", "common"),
            ("設定", "common"),
        ],
    )
    def test_nav_item_declares_system(self, spa: str, label: str, system: str) -> None:
        """各ナビ項目が data-system を持つこと。system-scope.js の絞り込みの前提。"""
        pattern = re.compile(
            r'<button[^>]*data-system="' + system + r'"[^>]*>.*?' + re.escape(label) + r"</span>",
            re.DOTALL,
        )
        assert pattern.search(spa), f"ナビ「{label}」に data-system=\"{system}\" がありません"

    def test_new_analysis_button_is_docs_only(self, spa: str) -> None:
        """サイドバーの「新規解析」ボタンは AutoRun 側で隠れる必要がある。"""
        assert re.search(r'id="add-site-btn"[^>]*data-system="docs"', spa)

    def test_system_switcher_present(self, spa: str) -> None:
        assert 'id="sys-switcher-link"' in spa
        assert 'id="sys-current-name"' in spa


# ---------------------------------------------------------------- システム選択


class TestSystemSelect:
    """ログイン後のシステム選択ハブ。"""

    def test_offers_exactly_two_systems(self, systems: str) -> None:
        cards = re.findall(r'class="syscard syscard-(\w+)"', systems)
        assert sorted(cards) == ["doc", "run"]

    def test_links_to_each_system(self, systems: str) -> None:
        assert 'href="/generate"' in systems
        assert 'href="/auto-run"' in systems

    def test_names_both_systems(self, systems: str) -> None:
        assert "ドキュメント作成" in systems
        assert "AutoRun" in systems

    def test_declares_claim_scope_boundary(self, systems: str) -> None:
        """AutoRun カードは「不在を証明しない」姿勢を明示すること。"""
        assert "未検証" in systems and "証明しません" in systems


# ---------------------------------------------------------------- AutoRun 受付


class TestAutoRunIntake:
    """AutoRun の受付（旧: test_autorun_modal_e2e の存在・既定値チェック）。"""

    def test_url_and_start_controls_present(self, spa: str) -> None:
        assert 'id="autorun-url"' in spa
        assert 'id="autorun-start-btn"' in spa

    def test_depth_and_max_pages_default_to_full_site(self, spa: str) -> None:
        """既定は「サイト全体」。範囲を絞らないという方針の表れ。"""
        assert re.search(r'id="autorun-depth"[^>]*value="10"', spa)
        assert re.search(r'id="autorun-max-pages"[^>]*value="500"', spa)

    def test_form_is_inside_intake_so_it_hides_on_run(self, spa: str) -> None:
        """受付ごと実行ビューへ切り替わる構成（単一フロー）の前提。

        #autorun-form-area が #autorun-idle-msg の内側にあることで、
        既存の _autorunShowRunning() が idle を隠すだけでフォームも隠れる。
        """
        start = spa.index('id="autorun-idle-msg"')
        end = spa.index('id="autorun-steps"')
        assert 'id="autorun-form-area"' in spa[start:end]

    def test_intake_states_claim_scope(self, spa: str) -> None:
        """受付で「不在は証明しない」ことを宣言していること。"""
        start = spa.index('id="autorun-idle-msg"')
        end = spa.index('id="autorun-steps"')
        intake = spa[start:end]
        assert "未検証" in intake
        assert "欠陥が無いことの証明はしません" in intake

    def test_preflight_requires_explicit_click(self, spa: str) -> None:
        """URL を打っただけで対象サイトへアクセスしないこと。

        事前確認は明示操作（ボタン）でのみ実行する。相手先への無断アクセスを避ける。
        """
        assert 'id="autorun-preflight-btn"' in spa
        assert "押すまで対象サイトには一切アクセスしません" in spa

    def test_preflight_uses_the_same_scope_as_the_run(self, spa: str) -> None:
        """事前確認が独自に範囲を絞らないこと。

        浅い上限を設けると発見画面数が実態より小さく出て、対象範囲を
        過小に見せてしまう（「範囲を絞らない」方針にも反する）。
        """
        assert "本実行と同じ" in spa
        assert "深さ1・最大8画面" not in spa

    def test_review_gate_exists_before_execution(self, spa: str) -> None:
        """生成物を確認する前に実行設定モーダルを突きつけないこと。"""
        assert 'id="autorun-review-gate"' in spa

    def test_generation_modes_offered(self, spa: str) -> None:
        assert 'id="autorun-mode-url"' in spa
        assert 'id="autorun-mode-document"' in spa

    def test_url_mode_is_default(self, spa: str) -> None:
        assert re.search(r'id="autorun-mode-url"[^>]*checked', spa)


class TestAutoRunApprovalModal:
    """テスト実行設定モーダル（旧 E2E の存在・既定値チェック）。"""

    @pytest.mark.parametrize(
        "element_id",
        [
            "autorun-approval-modal",
            "arm-title",
            "arm-close",
            "arm-later-btn",
            "arm-approve-btn",
            "arm-view-testcases-btn",
            "arm-timeout",
        ],
    )
    def test_element_present(self, spa: str, element_id: str) -> None:
        assert f'id="{element_id}"' in spa

    @pytest.mark.parametrize("value", ["all", "smoke", "transition", "form"])
    def test_all_four_filters_offered(self, spa: str, value: str) -> None:
        assert re.search(r'name="arm-filter"[^>]*value="' + value + r'"', spa)

    def test_all_tests_selected_by_default(self, spa: str) -> None:
        assert re.search(r'name="arm-filter"[^>]*value="all"[^>]*checked', spa)

    def test_timeout_options_and_default(self, spa: str) -> None:
        for seconds in ("10", "30", "60", "120"):
            assert f'value="{seconds}"' in spa
        assert re.search(r'value="30"[^>]*selected', spa)

    def test_pc_device_is_default(self, spa: str) -> None:
        """PC 専用方針。PC が既定で選択されていること。"""
        assert re.search(r'name="arm-device"[^>]*value="pc"[^>]*checked', spa)


# ---------------------------------------------------------------- 他ビューの骨格


class TestOtherViewStructures:
    """旧 test_testcases_view / test_run_history / test_report_tabs の構造検証。"""

    @pytest.mark.parametrize(
        "element_id",
        ["tc-domain-select", "tc-status", "tc-content", "tc-output-links"],
    )
    def test_testcases_view_structure(self, spa: str, element_id: str) -> None:
        assert f'id="{element_id}"' in spa

    @pytest.mark.parametrize("element_id", ["rh-container", "rh-tbody", "rh-empty", "rh-pager"])
    def test_run_history_view_structure(self, spa: str, element_id: str) -> None:
        assert f'id="{element_id}"' in spa

    @pytest.mark.parametrize(
        "tab", ["overview", "screens", "test-design", "flow", "runs", "history"]
    )
    def test_report_tabs_present(self, spa: str, tab: str) -> None:
        assert f'data-tab="{tab}"' in spa


class TestReferencesView:
    """参考ビュー。依拠する標準を実際に列挙していること。"""

    @pytest.mark.parametrize(
        "standard",
        ["ISO/IEC/IEEE 29119", "ISTQB", "ISO/IEC 25010", "WCAG 2.2", "OWASP"],
    )
    def test_lists_standard(self, spa: str, standard: str) -> None:
        assert standard in spa

    def test_distinguishes_applied_from_referenced(self, spa: str) -> None:
        """「実装に反映」と「参考」を区別していること。"""
        assert "refs-badge-applied" in spa
        assert "refs-badge-ref" in spa

    def test_does_not_claim_conformance(self, spa: str) -> None:
        """標準への準拠を主張しないこと（claim_scope の原則）。"""
        assert "標準への準拠を主張するものではなく" in spa
