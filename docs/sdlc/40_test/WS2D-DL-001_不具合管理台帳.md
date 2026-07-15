# WS2D-DL-001 不具合管理台帳

- 版数: 1.0 / 作成日: 2026-07-16
- 関連: 障害の詳細ポストモーテムは `docs/INCIDENT_POSTMORTEM.md`（本台帳は一覧・追跡）。
- 初期レコードは、本一連の品質改善（Phase A）で quarantine を解除する際に根本修正した
  実 5 件。各件は「起票→原因→対策→検証→クローズ」まで実記録。

## 台帳

| ID | 起票日 | 事象 | 重要度 | 原因分類 | 対策 | 検証 | 状態 |
|---|---|---|---|---|---|---|---|
| DL-001 | 2026-07-15 | 日本語サイトの必須未入力バリデーション実測が空（`observed=={}`）。全 JP サイトで機能不全 | 重大（実装バグ） | Chromium は `validationMessage` を UI 言語バンドルの**基底コード**で解決。`--lang=ja-JP` では空文字（en-US は可） | `page_crawler` に `BROWSER_UI_LANG`（基底 `ja`）を導入し `--lang` に使用。context locale は `ja-JP` 維持。`_dry_run_form_validation` を堅牢化（click 失敗でも `:invalid` 収集・failure を warning 可視化） | `test_crawl_page_contact_measures_validation` green。回帰防止 `test_auth.py` を修正後挙動へ更新 | Closed |
| DL-002 | 2026-07-15 | 承認モーダルの制限時間ドロップダウン（`#arm-timeout`）が 1280×800 で隠れる | 中（UX 劣化） | R3-02 実行デバイス選択追加で本文が縦長化し、スクロール下に埋没（IntersectionObserver 非可視） | `arm-section`/`arm-summary`/`arm-filter-opt` を圧縮（本文 713→633px）。フッタ固定は維持 | `test_timeout_dropdown_not_obscured` / `test_modal_does_not_overflow_viewport` green | Closed |
| DL-003 | 2026-07-15 | 履歴 diff ボタンのローディング状態テストが flaky | 低（テスト不安定） | sync Playwright の route ハンドラ内 `time.sleep` が driver スレッドをブロックし中間状態を取り逃す＋change/click 二重発火＋キャッシュ | 同期設定される loading 状態を同一 JS 実行内（fetch await 前）で捕捉する決定的テストへ変更 | 単体 10/10 安定 | Closed |
| DL-004 | 2026-07-15 | 承認モーダルの visual regression（1280×800）不一致（diff 0.0523） | 低（基準陳腐化） | ベースラインが R3-02 追加・圧縮に未追随 | ベースライン再生成（現行モーダル） | `test_autorun_approval_modal` green | Closed |
| DL-005 | 2026-07-15 | 同上（1366×768、diff 0.0413） | 低（基準陳腐化） | 同上 | 同上 | `test_autorun_approval_modal_1366x768` green | Closed |

## 補足

- A-5「Google ログインボタン撤去」は対象なし（アプリ `templates/auth/login.html` は
  当初からクリーン。Google ボタンは使い捨てモックのみに存在）と確認。不具合ではない。
- 上記 5 件の解除により E2E は 180 passed/5 skipped → **200 passed/0 skipped** に是正。
- quarantine 機構（`tests/e2e/conftest.py`）は残置し登録 0 件（将来 flaky 用の枠）。
