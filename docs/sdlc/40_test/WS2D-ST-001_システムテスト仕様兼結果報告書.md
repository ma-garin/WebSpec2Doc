# WS2D-ST-001 システムテスト仕様兼結果報告書（L3）

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISO/IEC/IEEE 29119 / ISTQB
- 定義: 実ブラウザ（Playwright Chromium）による UI→API→backend→出力→証跡の
  エンドツーエンド検証。`make verify-ui` で conftest がサーバを自動起動し実行。

## 1. 実施結果（実測）

| 指標 | 値 |
|---|---|
| E2E テストファイル | 32 |
| E2E テスト（`make verify-ui`） | **200 passed / 0 skipped** |
| quarantine（隔離） | **0 件**（Phase A で全解除） |
| ビジュアル回帰 | 6 ベースライン一致（1280/1366/1920・AutoRun idle・承認モーダル×2） |
| 証跡 | `tests/e2e/screenshots/`（失敗時自動保存）、`tests/e2e/snapshots/`（基準線） |

## 2. E2E テスト一覧（ファイル・件数）

- `test_auth_recorder_e2e.py`（2）, `test_autorun_modal_e2e.py`（48）,
  `test_broken_views_e2e.py`（11）, `test_capture_realbrowser_e2e.py`（1）,
  `test_comparison_e2e.py`（2）, `test_crawl_mode_e2e.py`（6）,
  `test_crawl_progress_e2e.py`（3）, `test_crawler_realbrowser_e2e.py`（4）,
  `test_dashboard_states_e2e.py`（1）, `test_discover_cancel_e2e.py`（4）,
  `test_discover_login_panel_e2e.py`（1）, `test_doc_fusion_ui_e2e.py`（4）,
  `test_finding_e2e.py`（2）, `test_flowchart_subtab_e2e.py`（3）,
  `test_frames_shadow_e2e.py`（6）, `test_info_tip_e2e.py`（4）,
  `test_markdown_preview_e2e.py`（2）, `test_report_tabs_e2e.py`（21）,
  `test_reverse_assets_e2e.py`（2）, `test_run_history_e2e.py`（5）,
  `test_shell_e2e.py`（6）, `test_sprint2_misc_e2e.py`（9）,
  `test_sprint3_ui_integration_e2e.py`（5）, `test_testcases_view_e2e.py`（5）,
  `test_traceability_view_e2e.py`（3）, `test_ui_smoke_e2e.py`（16）,
  `test_url_history_e2e.py`（3）, `test_user_guide_scroll_e2e.py`（1）,
  `test_ux_review_e2e.py`（4）, `test_viewpoint_management_e2e.py`（9）,
  `test_visual_regression_e2e.py`（6）, `test_xss_regression_e2e.py`（1）

## 3. UI 刷新で追加した E2E（本一連の作業）

| ファイル | 検証内容 |
|---|---|
| `test_shell_e2e.py` | クイック検索フィルタ→遷移・⌘K フォーカス・Esc・認証 OFF アバター非表示 |
| `test_run_history_e2e.py`（追記） | ページャ表示・2 ページ目遷移・単一ページ非表示 |
| `test_testcases_view_e2e.py`（追記） | 絞り込み（非一致→空→復元・一致行維持） |
| `test_traceability_view_e2e.py` | マトリクス行/バッジ class・生 hex 不在・カバレッジバー |
| `test_dashboard_states_e2e.py` | 履歴 API 失敗→.ui-error＋再試行→成功で復帰 |

## 4. 両テーマ巡回（Phase D 受入）

全 11 ビュー × light/dark を実機巡回し、生 hex による表示崩れが無いことを確認
（残る生 hex は PNG エクスポート下地の白のみ・テーマ非依存）。Console error ゼロ。

## 5. ドッグフーディング証跡

`WEBSPEC2DOC_ALLOW_LOCAL=1` で WebSpec2Doc 自身をクロールし、生成された画面仕様・
遷移図を自製品の自己検証証跡として保持（`WS2D-SD-001` §5）。

## 6. 再現方法
```bash
make verify-ui   # 200 passed / 0 skipped、.ui-verified マーカー生成
```
