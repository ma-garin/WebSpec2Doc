# Definition of Done（完了の定義）

**バージョン**: 1.0.0  
**準拠**: IEEE 730-2014, ISTQB Foundation Level  
**作成日**: 2026-06-03  
**適用**: WebSpec2Doc 全変更

---

## 原則

> **pytest が全テスト PASS であることは「完了」ではない。**  
> それは「コードが壊れていない」という L1/L2 レベルの確認にすぎない。  
> L3（システムテスト：ブラウザ確認）と L4（受け入れテスト：ユーザー確認）が完了して初めて「完了」である。

---

## 変更タイプ別 DoD

### Type A: バックエンド変更
**対象ファイル**: `src/**/*.py`, `web/**/*.py`, `app.py`

#### MANDATORY（自動チェック・スキップ不可）
- [ ] `make test` → 全 PASS + カバレッジ 80%+
- [ ] `python -m py_compile <変更ファイル>` → 構文エラーなし
- [ ] pre-commit hook が PASS

#### REQUIRED（人間によるチェック）
- [ ] code-reviewer エージェントを実行し HIGH 以上の指摘なし
- [ ] 変更理由・影響範囲をコミットメッセージに記載

---

### Type B: フロントエンド変更 ★ 最重要
**対象ファイル**: `static/**/*.js`, `static/**/*.css`, `templates/**/*.html`

#### MANDATORY（自動チェック・スキップ不可・pre-commit hook が強制）
- [ ] `make test` → 全 PASS
- [ ] `make verify-ui` → E2E 全テスト PASS（`.ui-verified` マーカー生成）
- [ ] `.ui-verified` が staged ファイルより新しいタイムスタンプを持つ

#### REQUIRED（人間によるチェック・省略禁止）
- [ ] **ブラウザで実際に変更した機能を操作して確認（1920×1080）**
- [ ] **1366×768 でレイアウト崩れがないことを確認**
- [ ] 変更した全ユーザーフローを最初から最後まで通して確認
- [ ] ブラウザコンソールにエラーなし
- [ ] ユーザーストーリー（受け入れ基準）を満たしていることを確認
- [ ] スクリーンショットを `tests/e2e/screenshots/` に保存

#### PROHIBITED（明示的禁止事項）
- `pytest` PASS のみで完了と判断すること
- ブラウザ確認なしにコミット・プッシュすること
- E2E テストをスキップして UI 変更をコミットすること
- 「動くはず」という推測で完了と宣言すること

---

### Type C: ドキュメント変更
**対象ファイル**: `docs/**/*.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`

- [ ] Markdown 構文チェック
- [ ] 内部リンク（相対パス）が有効であることを確認
- [ ] 古い情報を更新した場合、関連ドキュメントも合わせて更新

---

## 機械的ゲート（pre-commit hook）

```
┌─────────────────────────────────────┐
│         git commit 実行             │
└─────────────────┬───────────────────┘
                  ↓
        HTML/JS/CSS 変更あり？
          /              \
        NO               YES
         ↓                ↓
     通常の            .ui-verified
    pytest              確認
     チェック          /        \
         ↓         新しい      古い or 不在
      PASS/        /                \
      FAIL        PASS           BLOCKED
                               「make verify-ui を
                                実行してください」
```

`.ui-verified` は `make verify-ui` 実行時に生成される。  
UI ファイル変更時はこのマーカーなしにコミットできない。

---

## チェックリスト運用方法

コミット前に以下を実行・確認すること:

```bash
# Step 1: ユニット・統合テスト
make test

# Step 2: UI変更がある場合のみ
make verify-ui
# → ブラウザが起動してE2Eテスト実行
# → tests/e2e/screenshots/ にスクリーンショット保存
# → .ui-verified マーカー生成

# Step 3: コミット
git add <files>
git commit -m "feat: ..."
# → pre-commit hook が自動的にゲートチェックを実施
```

---

## 違反時の対応

DoD を満たさないままコミット・プッシュが判明した場合:
1. 即座にインシデントとして記録（`docs/INCIDENT_POSTMORTEM.md` 形式）
2. 問題のあるコミットを特定し、影響を評価
3. 修正を実施し DoD を完全に満たしてから再プッシュ
4. 再発防止措置を TESTING_STRATEGY.md に反映
