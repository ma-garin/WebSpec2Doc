# WS2D-CS-001 コーディング規約

- 版数: 1.0 / 作成日: 2026-07-16
- 実体は `pyproject.toml`（自動整形/静的解析）＋ `docs/specs/CONVENTIONS.md`（実装規約・
  既知の罠）＋ `.claude/rules/`（共通規約）。本書はその統合ビュー。

## 1. 自動整形・静的解析（`pyproject.toml`）

| ツール | 設定 | 実行 |
|---|---|---|
| black | line-length=100 / py312 | `black .` |
| ruff | select `E,F,W,I,UP,B` / ignore `E501` | `make lint`（`ruff check --fix`） |
| mypy | py3.12 / warn_unused_ignores 他 | `make lint` |
| bandit / pip-audit | セキュリティ | `make security` |

pytest 設定は警告を error 昇格（`PytestCollectionWarning`・Pillow 非推奨）＝警告ゼロ強制。

## 2. 構造規約

- **多数小ファイル > 少数巨大ファイル**。1 ファイル 800 行以内・関数 50 行以内目安。
- **イミュータブル**: 既存オブジェクトを破壊せず新オブジェクトを返す
  （`frozen=True` dataclass、`.with_xxx()` パターン）。
- **薄いルート**: `web/routes/*` は入力検証と委譲のみ。ロジックは `web/services/` `src/`。
- ドメイン中核（`src/`）は Flask 非依存。

## 3. エラー処理・入力検証

- 境界（ユーザー入力・API 応答・ファイル）で必ず検証。フェイルファスト。
- エラーを黙殺しない（例: バリデーション実測失敗は warning で可視化）。
- UI では利用者向けメッセージ、サーバ側は文脈付きログ。

## 4. フロントエンド

- 素の JS。DOM 生成の文字列連結では必ず `escHtml`（`core.js`）でエスケープ（XSS 防止）。
- 色は tokens 参照（生 hex 禁止・ダーク追従）。例外はエクスポート下地の白のみ。
- 共通部品を再利用（`ui-states.js` の状態、`core.js` の toast/dialog、`table-utils.js`）。

## 5. テスト規約

- TDD（失敗するテスト先行）。critical/high 機能は異常系（happy/failure/timeout/cancel）必須。
- E2E セレクタ安定のため既存 ID/class/data 属性を不用意に変えない。
- 詳細は `WS2D-TP-001`（テスト計画）／`docs/TESTING_STRATEGY.md`。

## 6. コミット・ゲート

- pre-commit（`.githooks/pre-commit`）: 構文 → `make test` → UI 変更時 `.ui-verified`
  マーカー照合。詳細は `WS2D-RL-001`（リリース手順）。
