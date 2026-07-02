# タスク: P3 — technique_recommender 精度向上 2本

**優先度**: P3（次スプリント）  
**背景**: `src/analyzer/technique_recommender.py` に2つの改善を加えて推奨精度と可視性を上げる。どちらも同一ファイルへの追加で干渉しない。

---

## 機能A: フォームの action URL 解析

フォームの `action` URL キーワードを検出し、業務重要度に応じて技法優先度を調整する。

```python
_ACTION_PRIORITY_BOOST: dict[str, tuple[str, ...]] = {
    'login': ('dt',),   'signin': ('dt',),   'auth': ('dt',),
    'checkout': ('dt', 'bva'),  'payment': ('dt', 'bva'),  'order': ('dt', 'bva'),
    'register': ('ep', 'bva'),  'signup': ('ep', 'bva'),
    'search': ('pw',),  'filter': ('pw',),
}

def _detect_action_boosts(screen: dict) -> frozenset[str]:
    boosts: set[str] = set()
    for form in screen.get('forms', []):
        action = str(form.get('action', '')).lower()
        for keyword, keys in _ACTION_PRIORITY_BOOST.items():
            if keyword in action:
                boosts.update(keys)
    return frozenset(boosts)
```

**完了条件**:
- [ ] `/login` action のフォームがある画面で `dt` が推奨される
- [ ] `/checkout` action で `dt` と `bva` が推奨される
- [ ] action なしの場合に既存ロジックと同一結果になる

---

## 機能B: テスト密度スコア（概要タブ表示）

技法数・フィールド数・遷移数からスコアを算出し、概要タブに「高リスク画面 N件」バッジを出す。

```python
def density_score(screen: dict) -> float:
    techs = screen.get('techniques', [])
    recommended_count = sum(1 for t in techs if t.get('recommended'))
    fields = len(screen.get('fields', []))
    links = len(screen.get('links', []))
    forms = len(screen.get('forms', []))
    return recommended_count * 2.0 + fields * 1.0 + links * 1.5 + forms * 1.0
```

スコア >= 10 を「高リスク」と定義。`json_reporter.py` で各 screen に `density_score` を追加し、`view-overview.js` で「高リスク画面: N件」バッジを表示する。

**完了条件**:
- [ ] `density_score()` が float を返す
- [ ] report.json の各 screen に `density_score` が含まれる
- [ ] 概要タブに高リスクバッジが表示される（N=0 なら非表示）

---

## 共通完了条件

- [ ] `python -m pytest tests/test_technique_recommender.py -v` が全 PASS
- [ ] `python -m pytest tests/ -q` が全 PASS（既存テスト影響なし）
- [ ] `make verify-ui` が PASS
