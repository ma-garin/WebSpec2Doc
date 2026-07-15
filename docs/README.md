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
| [GUIDE_ja.md](GUIDE_ja.md) | 非エンジニア向けガイド（何ができるか・使い方・FAQ／専門用語なし） |
| [GUIDE_en.md](GUIDE_en.md) | Non-engineer guide (English) |
| [userguide.md](userguide.md) | クイックスタートガイド（**正**） |
| [demo/DEMO_SCRIPT.md](demo/DEMO_SCRIPT.md) | 同梱デモの実演台本（5分/10分版） |
| [demo/sample_output/](demo/sample_output/) | 生成物のサンプル一式 |

## 開発ロードマップ

| 文書 | ステータス |
|------|-----------|
| [11_機能拡張ロードマップ_現新比較とUX検証.md](11_機能拡張ロードマップ_現新比較とUX検証.md) | 現行（機能拡張の開発ロードマップ・アイデアカタログ） |

> 事業計画・商用化戦略・大会準備などのビジネス文書（旧 01〜10・PITCH_OUTLINE）は、開発リポジトリの目的外のため Sprint 3 で撤去した（git 履歴に保存）。

## 記録（プロセス・意思決定）

| 文書 | 役割 |
|------|------|
| [sdlc/](sdlc/) | **SDLC 文書体系**（要件定義〜テストサマリ。V字・as-built・実測。入口は sdlc/README.md） |
| [adr/](adr/) | アーキテクチャ意思決定記録（ADR 0001〜0004） |
| [design/](design/) | 方式・設計ドキュメント（auth-tenant / ui-redesign / workspace-data-separation） |
| [INCIDENT_POSTMORTEM.md](INCIDENT_POSTMORTEM.md) | インシデント記録（現役の記録フォーマット） |
| [ux-audit/](ux-audit/) | UX 監査・インシデント調査の記録 |
| [tasks/](tasks/) | 過去の実装タスク指示書（Codex 向け・完了済み） |

## archive/ — 歴史文書（更新しない）

| 文書 | 廃止理由 |
|------|---------|
| [archive/USABILITY_TEST_REPORT.md](archive/USABILITY_TEST_REPORT.md) | 2026-06 時点の記録。指摘事項は対応済み |
| [archive/ACCEPTANCE_TEST_PERSONAS.md](archive/ACCEPTANCE_TEST_PERSONAS.md) | ペルソナ評価は評価手法として不採用（ユースケース記述として参照のみ） |
| [archive/userManuel.md](archive/userManuel.md) / [.html](archive/userManuel.html) | userguide.md に置き換え |

## 運用ルール

- 新しい文書を追加したら、この索引に1行追加する
- 文書を廃止するときは削除せず `archive/` へ移動し、後継文書を「廃止理由」に書く
- 機能拡張の検討は [11_機能拡張ロードマップ_現新比較とUX検証.md](11_機能拡張ロードマップ_現新比較とUX検証.md) に集約する（旧・番号付きビジネス文書 01〜10 は Sprint 3 で撤去済み）
