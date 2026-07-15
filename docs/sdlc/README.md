# WebSpec2Doc SDLC 文書体系（V字モデル・as-built）

本体系は WebSpec2Doc 自身の開発ライフサイクル文書を、大手 SIer が整備する粒度で
**漏れなくダブりなく（MECE）** まとめたもの。作成方針は以下。

- **as-built**: 実装完了後の「現実のシステム」を正として記述する。テスト結果・件数・
  カバレッジは実測コマンドの出力を転記し、捏造しない（各文書に取得コマンドを併記）。
- **MECE**: 既に充実している既存文書は複製せず**リンク参照**する（下表「既存」）。
  不足分のみ本体系で新設する（下表「新設」）。
- **文書ID**: `WS2D-{種別}-{連番}`。要件IDは `quality/feature_contracts.yml` の
  `feature_id`（19 件）を主キーとする。
- **規格ハイブリッド**: 文書体系は SIer/IPA 共通フレーム流、テスト文書の中身は
  ISTQB / ISO・IEC・IEEE 29119 / ISO・IEC 25010 準拠。

## 実測サマリ（最終計測: 2026-07-16）

| 指標 | 値 | 取得コマンド |
|---|---|---|
| 機能契約（要件） | 19 | `python scripts/quality_harness.py` → validated_features=19 |
| 非E2Eテストファイル | 108 | `ls tests/test_*.py \| wc -l` |
| E2Eテストファイル | 32 | `ls tests/e2e/test_*.py \| wc -l` |
| テスト関数総数 | 1985 | `grep -rhE '^\s*def test_' tests/ \| wc -l` |
| L1/L2 テスト | 1,831 passed | `make test` |
| L3 E2E テスト | 200 passed / 0 skipped | `make verify-ui` |
| カバレッジ | 84.30%（閾値80%） | `make coverage` |
| Blueprint / エンドポイント | 17 / 121 | `grep -rhE '@.*\.(route\|get\|post…)' web/routes/*.py` |
| 品質ハーネス | PASS | `python scripts/quality_harness.py` |

## 文書一覧と既存資産マッピング

| 文書ID | 文書 | 区分 | 既存参照 |
|---|---|---|---|
| WS2D-RD-001 | [要件定義書](10_requirements/WS2D-RD-001_要件定義書.md) | 新設 | feature_contracts.yml / README.md |
| WS2D-NF-001 | [非機能要件定義書](10_requirements/WS2D-NF-001_非機能要件定義書.md) | 新設 | ISO 25010 / TESTING_STRATEGY §6 |
| WS2D-BD-001 | [基本設計書](20_design/WS2D-BD-001_基本設計書.md) | 新設 | docs/adr/* |
| WS2D-SD-001 | [画面設計書](20_design/WS2D-SD-001_画面設計書.md) | 新設 | CONTEXT.md / ui-redesign-plan.md |
| WS2D-IF-001 | [API設計書](20_design/WS2D-IF-001_API設計書.md) | 新設 | web/routes/*（as-built 抽出） |
| WS2D-DD-001 | [データ設計書](20_design/WS2D-DD-001_データ設計書.md) | 新設 | workspace-data-separation.md |
| WS2D-CS-001 | [コーディング規約](30_implementation/WS2D-CS-001_コーディング規約.md) | 新設 | specs/CONVENTIONS.md / pyproject.toml |
| WS2D-TP-001 | [テスト計画書](40_test/WS2D-TP-001_テスト計画書.md) | 新設 | **TESTING_STRATEGY.md** |
| WS2D-TV-001 | [テスト観点表](40_test/WS2D-TV-001_テスト観点表.md) | 新設 | data/viewpoint_templates/* |
| WS2D-UT-001 | [単体テスト仕様兼結果報告書](40_test/WS2D-UT-001_単体テスト仕様兼結果報告書.md) | 新設 | tests/（L1） |
| WS2D-IT-001 | [結合テスト仕様兼結果報告書](40_test/WS2D-IT-001_結合テスト仕様兼結果報告書.md) | 新設 | tests/（L2・test_client） |
| WS2D-ST-001 | [システムテスト仕様兼結果報告書](40_test/WS2D-ST-001_システムテスト仕様兼結果報告書.md) | 新設 | tests/e2e/（L3） |
| WS2D-AT-001 | [受入テスト仕様書](40_test/WS2D-AT-001_受入テスト仕様書.md) | 新設 | TESTING_STRATEGY UAT / archive ペルソナ |
| WS2D-TM-001 | [トレーサビリティマトリクス](40_test/WS2D-TM-001_トレーサビリティマトリクス.md) | 新設（機械生成） | feature_contracts.yml |
| WS2D-DL-001 | [不具合管理台帳](40_test/WS2D-DL-001_不具合管理台帳.md) | 新設 | INCIDENT_POSTMORTEM.md |
| WS2D-TR-001 | [テストサマリレポート](40_test/WS2D-TR-001_テストサマリレポート.md) | 新設 | （ISO 29119-3） |
| WS2D-OP-001 | [運用手順書](50_operation/WS2D-OP-001_運用手順書.md) | 新設 | userguide.md / Makefile |
| WS2D-RL-001 | [リリース手順書](50_operation/WS2D-RL-001_リリース手順書.md) | 新設 | spec-6-2 / .githooks |
| WS2D-QA-001 | [品質保証計画書](60_quality/WS2D-QA-001_品質保証計画書.md) | 新設 | DEFINITION_OF_DONE.md / functional-integrity-gate.md |

**用語定義書**は `CONTEXT.md`（ユビキタス言語）を、**障害報告テンプレ**は
`docs/INCIDENT_POSTMORTEM.md` を正とし、本体系からは参照する（複製しない）。

## 再現方法（監査者向け）

```bash
python scripts/quality_harness.py          # 要件契約の機械検証
make test                                  # L1/L2 単体・結合
make verify-ui                             # L3 E2E（要 Chromium）
make coverage                              # カバレッジ実測
python scripts/generate_traceability_doc.py --write   # WS2D-TM-001 の再生成
```
