# タスク: P2-1 — Excel/CSV に技法列を追加

**優先度**: P2（今週中）  
**背景**: `spec.xlsx` にはテスト条件が入っているが、技法マトリクス・ケース雛形が含まれていない。QA担当が設計レビューで直接使える成果物にする。

## ゴール

`spec.xlsx`（および対応する CSV）の画面シートに `推奨技法` 列を追加する。
各行に ep/bva/st/dt/ct/pw/uc/comb のうち推奨される技法キーをカンマ区切りで出力する。

## 触るファイル

- `src/generator/csv_reporter.py` — 画面シートに技法列を追加
- `tests/test_csv_reporter.py` — 技法列が出力されることを確認するテストを追加

**変更禁止**:
- `src/analyzer/technique_recommender.py`（単一真実源。呼び出すだけ）
- `web/routes/report.py`

## 実装の指針

### `csv_reporter.py` の変更

```python
from src.analyzer.technique_recommender import techniques_for_screen

# 画面シートのヘッダーに追加
headers = [...既存..., '推奨技法', '推奨技法（詳細）']

# 各行に技法データを追加
techs = techniques_for_screen(screen)
recommended = [t['key'] for t in techs if t.get('recommended')]
row = [...既存..., ', '.join(recommended), _format_tech_detail(techs)]
```

## 完了条件

- [ ] `spec.xlsx` の画面シートに「推奨技法」列が追加される
- [ ] 列に ep, bva 等の技法キーがカンマ区切りで入っている
- [ ] `python -m pytest tests/test_csv_reporter.py -v` が全 PASS
- [ ] `python -m pytest tests/ -q` が全 PASS（既存テスト影響なし）

## スコープ外

- ケース雛形の全行展開（列が増えすぎるため）
- PDF レポートへの技法列追加（今回は xlsx/csv のみ）
