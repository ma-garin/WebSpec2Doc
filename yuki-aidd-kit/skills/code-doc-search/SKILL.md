---
name: code-doc-search
description: 技術ドキュメント・OSSコード・APIリファレンスの検索を最適化するスキル。「〜のドキュメントを調べて」「〜の使い方を探して」「最新バージョンの変更点」「〜のAPIリファレンス」「〜のインストール方法」「ECC/cc-sdd/Playwright/Streamlit/Claude Code の仕様を確認したい」など、技術情報の検索依頼があった場合は必ずこのスキルを使用すること。web_searchを直接使うより精度が上がる。
---

# コードドキュメント特化検索

Claude組み込みのweb_searchを技術情報向けに最適化する。追加コストゼロ。

## クエリ構築ルール

### ターゲットドメイン別の検索パターン
| 目的 | クエリパターン |
|---|---|
| 公式ドキュメント | `{ライブラリ名} docs {バージョン or "latest"}` |
| GitHub README/リリース | `site:github.com {owner/repo} {キーワード}` は使わない → `{repo名} github README {機能名}` |
| npm パッケージ | `{パッケージ名} npm install usage` |
| PyPI パッケージ | `{パッケージ名} pypi python usage example` |
| APIリファレンス | `{サービス名} API reference {エンドポイント名}` |
| 変更履歴 | `{ライブラリ名} changelog {バージョン} breaking changes` |
| エラー解決 | `{エラーメッセージ} {ライブラリ名} {バージョン} fix` |

### AIDD特有の検索対象
- **Claude Code / ECC**: `everything-claude-code github`, `claude code docs`
- **cc-sdd**: `gotalab cc-sdd github`, `cc-sdd kiro commands`
- **Streamlit**: `streamlit docs {コンポーネント名}`
- **Playwright**: `playwright python docs {機能名}`
- **Gemini API（無料枠）**: `gemini api free tier limits {year}`

## 検索実行の手順

1. **キーワードを3〜5語に絞る**（長いクエリは精度が下がる）
2. **バージョンが重要な場合は年を含める**（例: `streamlit session_state 2026`）
3. **公式ドキュメントが見つかったらweb_fetchで全文取得**（スニペットだけでは不足する場合）
4. **複数ソースが必要な場合は並列検索**（最大3クエリまで同時実行）

## 出力フォーマット

```
## {ライブラリ名} — {検索した機能/概念}

**ソース**: {URL}（公式 / GitHub / Stack Overflow等を明記）
**バージョン**: {確認できた場合}

### 要点
{3〜5行でサマリー}

### コード例
{あれば}

### 注意点 / 既知の問題
{あれば}
```

evidence-onlyで出力する。確認できなかった仕様は「未確認」と明記する。
