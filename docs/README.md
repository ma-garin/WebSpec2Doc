# ドキュメントインデックス

このディレクトリの全文書の索引。**「正」= 現在の正式文書 / 「歴史」= 過去の経緯として保存（更新しない）**。
矛盾がある場合は必ず「正」の文書が優先される。

## まず読む（開発に着手する人向け）

| 文書 | 役割 |
|------|------|
| [DEVELOPMENT.md](DEVELOPMENT.md) | 開発者向けハンドブック（セットアップ・構成・規約） |
| [process/claude-entrypoint.md](process/claude-entrypoint.md) | AI エージェントの作業エントリポイント |
| [process/functional-integrity-gate.md](process/functional-integrity-gate.md) | 完了判定ゲート（実行パス検証の必須手順） |
| [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) | 完了の定義（DoD） |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | テスト戦略（L1〜L3 の層構造） |

## 利用者向け

| 文書 | 役割 |
|------|------|
| [userguide.md](userguide.md) | クイックスタートガイド（**正**） |
| [demo/DEMO_SCRIPT.md](demo/DEMO_SCRIPT.md) | 同梱デモの実演台本（5分/10分版） |
| [demo/sample_output/](demo/sample_output/) | 生成物のサンプル一式 |

## 事業・戦略

| 文書 | ステータス |
|------|-----------|
| [09_事業計画_統合版.md](09_事業計画_統合版.md) | **正**（唯一の最新事業計画。旧文書との矛盾はここで解消済み） |
| [10_社内ベンチャー準備タスク.md](10_社内ベンチャー準備タスク.md) | 現行（大会 Ask・体制・準備チェックリスト） |
| [11_機能拡張ロードマップ_現新比較とUX検証.md](11_機能拡張ロードマップ_現新比較とUX検証.md) | 現行（機能拡張の全体ロードマップ・アイデアカタログ） |
| [demo/PITCH_OUTLINE.md](demo/PITCH_OUTLINE.md) | 現行（発表構成） |
| [07_商用化戦略_1MARR.md](07_商用化戦略_1MARR.md) / [.html](07_商用化戦略_1MARR.html) | 歴史（価格帯は 09 に継承） |
| [08_プロダクト機能戦略_10M.md](08_プロダクト機能戦略_10M.md) | 歴史（機能案は 11 に継承） |
| [01_企画書.html](01_企画書.html) 〜 [06_プロジェクトWiki.html](06_プロジェクトWiki.html) | 歴史（初期企画・要件・設計。[index.html](index.html) が閲覧ポータル） |

## 記録（プロセス・意思決定）

| 文書 | 役割 |
|------|------|
| [adr/](adr/) | アーキテクチャ意思決定記録（ADR 0001〜0003） |
| [INCIDENT_POSTMORTEM.md](INCIDENT_POSTMORTEM.md) | インシデント記録（現役の記録フォーマット） |
| [ux-audit/](ux-audit/) | UX 監査・インシデント調査の記録 |
| [tasks/](tasks/) | 過去の実装タスク指示書（Codex 向け・完了済み） |

## archive/ — 歴史文書（更新しない）

| 文書 | 廃止理由 |
|------|---------|
| [archive/plan.txt](archive/plan.txt) | 初期の商業化ロードマップ。09 に統合 |
| [archive/SELLABLE_PRODUCT_PLAN.md](archive/SELLABLE_PRODUCT_PLAN.md) | 完成度評価は 09 で再評価済み |
| [archive/USABILITY_TEST_REPORT.md](archive/USABILITY_TEST_REPORT.md) | 2026-06 時点の記録。指摘事項は対応済み |
| [archive/ACCEPTANCE_TEST_PERSONAS.md](archive/ACCEPTANCE_TEST_PERSONAS.md) | ペルソナ評価は評価手法として不採用（ユースケース記述として参照のみ） |
| [archive/userManuel.md](archive/userManuel.md) / [.html](archive/userManuel.html) | userguide.md に置き換え |

## 運用ルール

- 新しい文書を追加したら、この索引に1行追加する
- 文書を廃止するときは削除せず `archive/` へ移動し、後継文書を「廃止理由」に書く
- 番号付き文書（01〜）は追記式。次は 12
