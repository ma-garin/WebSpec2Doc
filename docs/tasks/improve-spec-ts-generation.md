# タスク: spec.ts 生成の段階的強化

**優先度**: P2→P3（段階実装）  
**背景**: `.spec.ts` エクスポートは存在するが、技法ケース雛形との連携・role-based ロケータ・Page Object 生成が未実装。3段階で強化する。

---

## Phase A（P2）: レポートから .spec.ts を直接エクスポート

**対象ファイル**: `web/routes/report.py`, `static/js/results.js`

エクスポートドロップダウンに「↓ .spec.ts」を追加する。

```python
# web/routes/report.py
"spec_ts": path_of("playwright_candidates.spec.ts"),
```

```js
// results.js の EXPORT_DEFS に追加
{ key: 'spec_ts', label: '↓ .spec.ts', ext: 'ts' },
```

**完了条件**:
- [ ] エクスポートドロップダウンに「↓ .spec.ts」が表示される
- [ ] クリックで playwright_candidates.spec.ts がダウンロードされる
- [ ] `python -m pytest tests/ -q` が全 PASS

---

## Phase B（P3）: 技法ケース雛形から test() ブロック自動生成

**対象ファイル**: `web/services/spec_ts_generator.py`, `tests/test_spec_ts_generator.py`

`technique_recommender` のケース雛形から Playwright `test()` ブロック骨格を生成する。

```python
def generate_technique_tests(screen: dict) -> str:
    """画面の技法ケース雛形から Playwright test() ブロック文字列を生成。"""
```

| 技法 | 生成ケース |
|------|----------|
| ep | 有効クラス1件 + 無効クラス1件 |
| bva | min/max/境界±1 の計4ケース |
| st | 正常遷移1件 + 異常遷移1件 |
| dt | 条件組み合わせ最大4ケース |

**完了条件**:
- [ ] ep/bva 技法のある画面で `test('P001 同値分割...', ...)` が出力される
- [ ] `python -m pytest tests/test_spec_ts_generator.py -v` が全 PASS

---

## Phase C（P3）: role-based ロケータ + Page Object 生成

**対象ファイル**: `web/services/spec_ts_generator.py`

- `page.locator('#id')` → `page.getByRole('button', { name: '...' })` に昇格
- 画面ごとに `class LoginPage { ... }` 形式の Page Object を生成

**完了条件**:
- [ ] ARIA role が取得できているフィールドで `getByRole()` が使われる
- [ ] 各画面に Page Object クラスが生成される
- [ ] `python -m pytest tests/ -q` が全 PASS

---

## スコープ外

- 生成した spec.ts の自動実行（AutoRun との連携は別タスク）
- ct/pw/uc/comb 技法の生成（Phase B では ep/bva/st/dt の4技法のみ）
