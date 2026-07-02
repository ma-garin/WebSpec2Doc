# タスク: P3-12 — 再クロール後の品質サマリー差分通知

**優先度**: P3（次スプリント）  
**背景**: 再クロール完了後に「前回から新規画面2件・フォーム変更1件・推奨技法変化3件」をまとめて通知できると、QA担当が優先的に見直すべき箇所をすぐ把握できる。

## ゴール

再クロール完了後、ダッシュボードまたは実行完了画面に「品質サマリー差分」カードを表示する。

### 表示内容

```
── 前回との変化 ──────────────────────────
+ 新規画面: 2件（/new-page, /new-feature）
~ フォーム変更: 1件（/checkout — フィールド追加）
△ 推奨技法変化: 3画面（dt 追加, bva 削除 など）
─────────────────────────────────────────
```

## 触るファイル

- `src/diff/differ.py` — 技法変化の差分を検出する `diff_techniques(old_screens, new_screens)` 関数を追加
- `src/generator/diff_reporter.py` — 技法差分を差分レポートに含める
- `web/routes/crawl.py`（または実行完了ルート） — 再クロール完了時に差分サマリーを返す
- `static/js/results.js` または `wizard.js` — 差分サマリーカードを表示

**変更禁止**:
- `src/diff/snapshot.py`（スナップショット保存ロジックは変えない）

## 実装の指針

### `diff_techniques()` の仕様

```python
def diff_techniques(
    old_screens: list[dict],
    new_screens: list[dict],
) -> list[dict]:
    """技法推奨の変化を返す。
    
    Returns:
        [{'page_id': 'P001', 'added': ['dt'], 'removed': ['bva']}, ...]
    """
```

### 差分サマリー構造

```json
{
  "new_pages": ["/new-page"],
  "removed_pages": [],
  "changed_forms": [{"page_id": "P003", "url": "/checkout"}],
  "technique_changes": [{"page_id": "P001", "added": ["dt"], "removed": []}]
}
```

## 完了条件

- [ ] `diff_techniques()` が技法変化リストを返す
- [ ] 再クロール完了後、差分サマリーカードが表示される
- [ ] 前回クロールデータがない場合は差分表示をスキップする
- [ ] `python -m pytest tests/ -q` が全 PASS
- [ ] `make verify-ui` が PASS

## スコープ外

- Slack 通知との連携（既存の通知機能は変えない）
- 差分の CSV エクスポート（今回は UI 表示のみ）
