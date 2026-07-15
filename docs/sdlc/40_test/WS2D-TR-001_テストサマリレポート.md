# WS2D-TR-001 テストサマリレポート

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISO/IEC/IEEE 29119-3（テスト完了レポート）
- **as-built・実測**: 数値は最終計測の実出力を転記。監査者は再現方法（§7）で照合可能。

## 1. テスト範囲

- 対象: WebSpec2Doc 全 17 機能（`quality/feature_contracts.yml`）。
- レベル: L0 契約 / L1 単体 / L2 結合 / L3 システム（E2E）/ 受入（手動）。

## 2. 実施結果サマリ（最終計測: 2026-07-16）

| 指標 | 目標 | 実測 | 判定 |
|---|---|---|---|
| L0 機能契約検証 | PASS | validated_features=17 | ✅ |
| L1/L2（`make test`） | 全 green | **1,794 passed** | ✅ |
| L3 E2E（`make verify-ui`） | 全 green・skip 0 | **200 passed / 0 skipped** | ✅ |
| カバレッジ（`make coverage`） | ≥80% | **84.32%** | ✅ |
| トレーサビリティ GAP | 0 | **0**（17/17 紐付け） | ✅ |
| quarantine | 0 | **0** | ✅ |

## 3. 品質改善の要点（本一連の作業）

- **当たり前品質の回復**: quarantine 中の 5 件を根本修正し隔離ゼロ化。E2E は
  180 passed/5 skipped → **200 passed/0 skipped**。最大の成果は日本語バリデーション
  実測の実バグ修正（DL-001、`--lang` 基底コード）。
- **外部/魅力的品質**: UI シェル（クイック検索・アバター）、データビュー（フィルタ・
  ページネーション・バッジのトークン化）、状態体系化（再試行導線）、ダーク完成。
- 追加 E2E: shell / run-history ページング / testcases 絞り込み / traceability /
  dashboard 状態（計 +18 相当）。

## 4. 残存リスク・既知事項

- 受入テスト（`WS2D-AT-001`）は実利用者による実施が未了（手順は精緻化済み）。
- ワークスペース別データ物理分離は未実装（設計のみ・`workspace-data-separation.md`）。
- 外部 IdP（Google 等）連携は将来要件（現状 UI にも未露出＝当たり前品質を満たす）。
- ビジュアル回帰ベースラインは環境ローカル（gitignore）。他環境では初回再生成が必要。

## 5. 逸脱（Deviations）

- quarantine 機構は残置するが登録 0 件（将来 flaky 用の受け皿）。過去の隔離 5 件は
  `WS2D-DL-001` に是正記録済み。

## 6. 品質評価とリリース推奨

全ゲート green・GAP ゼロ・カバレッジ 84.32%・表示崩れなし・Console error ゼロ。
**リリース可**と評価する（受入テストは配布先での実施を推奨）。

## 7. 再現方法（監査者向け）

```bash
python scripts/quality_harness.py            # validated_features=17
make test                                    # 1,794 passed
make verify-ui                               # 200 passed / 0 skipped
make coverage                                # Total coverage 84.32%
python scripts/generate_traceability_doc.py  # 要件17/GAP 0
```
