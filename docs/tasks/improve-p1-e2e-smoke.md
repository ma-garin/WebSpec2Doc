# タスク: P1-10 — 技法タブのE2Eスモークテスト追加

**優先度**: P1（今すぐ）  
**背景**: 技法タブが summaryモードで消えるインシデントがあった（2026-06-14）。E2Eがあれば即検知できた。

## ゴール

`tests/e2e/` に以下の2本を追加し、同様のリグレッションを自動検知できるようにする:

1. **サマリーモードで設計・技法詳細タブが表示されること**
2. **技法マトリクスにバッジ（推奨/非推奨）が出ること**

## 触るファイル

- `tests/e2e/test_technique_tabs.py` — 新規作成

**変更禁止**:
- `static/js/results.js`（SUMMARY_HIDE_TABS 定数は現行のまま）
- 既存 E2E テストファイル

## テスト実装の指針

```python
# テスト1: サマリーモードで設計・技法詳細タブが表示される
# - report.json を持つサイトを使い、レポートビューを開く
# - #view-mode-summary がデフォルト active であることを確認
# - [data-tab="design"] タブが display:none でないことを確認
# - [data-tab="technique-detail"] タブが display:none でないことを確認

# テスト2: 技法マトリクスにバッジが出る
# - 設計タブを開く
# - .technique-badge 要素が1件以上存在することを確認
```

## 完了条件

- [ ] `tests/e2e/test_technique_tabs.py` が存在する
- [ ] `make verify-ui` が PASS する
- [ ] CI でも PASS する（`.ui-verified` マーカーが更新される）

## スコープ外

- 新機能の追加
- 既存 E2E の変更
