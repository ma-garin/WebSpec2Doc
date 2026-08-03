# WebSpec2Doc SDLC 文書体系（V字モデル・as-built）

WebSpec2Doc 自身の開発ライフサイクル文書を、SIer が納品時に整備する粒度でまとめたもの。

## 作成方針

- **as-built**: 実装完了後の「現実のシステム」を正として記述する。件数・カバレッジは実測
  コマンドの出力を転記し、捏造しない（各文書に取得コマンドを併記）。
- **MECE**: 既に充実している既存文書は複製せず**リンク参照**する。不足分のみ本体系で新設する。
- **機械抽出を正とする**: エンドポイント・モジュール・スキーマ・OSS ライセンスは
  `scripts/extract_asbuilt.py` がコードから抽出する（`_asbuilt/` 配下）。手書き台帳は
  コードが変わった瞬間に嘘になるため、再生成できる形で維持する。
- **文書ID**: `WS2D-{種別}-{連番}`。要件IDは `quality/feature_contracts.yml` の
  `feature_id` を主キーとする。
- **規格ハイブリッド**: 体系は SIer / IPA 共通フレーム流、テスト文書の中身は
  ISTQB / ISO・IEC・IEEE 29119 / ISO・IEC 25010、構成管理は IEEE 828、
  非機能は IPA 非機能要求グレードに準拠。

## 実測サマリ（最終計測: 2026-08-02）

| 指標 | 値 | 取得コマンド |
|---|---|---|
| 機能契約（要件） | **51**（critical 11 / high 20 / medium 18 / low 2） | `grep -c 'feature_id' quality/feature_contracts.yml` |
| エンドポイント / Blueprint | **200 / 26** | `venv/bin/python scripts/extract_asbuilt.py` → routes.json |
| アプリケーションモジュール | **237**（src 147 / web 90） | 同上 → modules.json |
| アプリケーション行数 | **57,140行**（src 32,467 / web 24,673） | 同上 |
| クラス | **202** | 同上 |
| DB テーブル | **11**（auth.db 6 / viewpoints.db 5） | 同上 → schema.sql |
| Jinja2 テンプレート | **30**（3,526行） | 同上 → templates.json |
| 依存 OSS | **74** | 同上 → licenses.json |
| **サブパッケージ間の循環依存** | **3件**（`web.routes` ⇄ `web.services` 系） | 同上 → dependency_cycles.json |
| テストファイル総数 | **213**（非E2E 193 / E2E 20） | `find tests -name 'test_*.py' \| wc -l` |
| テスト関数総数 | **3,026**（うち E2E 62） | `grep -rhE '^\s*def test_' tests/ \| wc -l` |

### テスト実行結果（すべて 2026-08-03 に現構成で実測）

| 指標 | 値 | 取得コマンド |
|---|---|---|
| L1/L2 テスト | **3,239 passed / 0 failed**（31 秒） | `make test` |
| L3 E2E テスト | **94 passed / 1 skipped**（2 分 23 秒） | `make verify-ui` |
| カバレッジ | **84%**（閾値 80%） | `make coverage` |
| 機能契約検証 | **PASS**（validated_features=51） | `python scripts/quality_harness.py` |
| 静的解析 | **PASS** | `make lint` |

前回計測（2026-07-16）の 1,831 passed から 1,408 件増えている。
テスト関数の実測は 3,026 件だが passed が 3,239 件なのは、`parametrize` で
1 関数が複数ケースに展開されるため。関数数と実行ケース数は別の指標である。

E2E の 1 skipped は `autorun_security_kernel`。送信ゲートウェイがテスト生成・実行段階
でのみ有効で、クロール段階は別の検査（`src/crawler/url_safety.py`）を通る構造のため、
素直に書くと別機能を検証してしまう。理由を `tests/e2e/test_autorun_security_e2e.py`
に明記した上で skip している。

**E2E 実行時の注意**: ポート 8765 で開発用 DB のサーバーが動いていると、
`make verify-ui` は DB 汚染を避けるために停止する。サーバーを止めたくない場合は
`env -u WEBSPEC2DOC_E2E_URL venv/bin/python -m pytest tests/e2e/ -q` を使うと、
conftest が別ポートに隔離サーバーを立てて実行する。

## 品質状況

### 解消済み（2026-08-03）

| # | 内容 | 対応 |
|---|---|---|
| 1 | critical 機能の L3（E2E）未検証 | 認証(account_auth)・テナントメンバーシップ・テナント分離・AutoRun 段階承認の E2E を追加（`tests/e2e/test_auth_tenant_e2e.py`, `test_autorun_security_e2e.py`） |
| 2 | サブパッケージ間の循環依存 3 経路 | **0 経路 / 原因 import 0 本**。AutoRun パイプライン 886 行を `web/services/auto_run_pipeline.py` へ移設し、`web.services -> web.routes` の逆依存を解消 |
| 3 | OSS ライセンスの UNKNOWN 26 件 | **0 件**。PEP 639 の `License-Expression` に対応。MPL-2.0 が 3 件、GPL・LGPL・AGPL は該当なし |

### 残る要対応事項

| # | 内容 | 理由 |
|---|---|---|
| 1 | 承認者・配布先・問い合わせ先が未設定（Word の承認欄は空欄） | 実在しない氏名・連絡先を書くのは捏造にあたるため空欄のまま。納品時に記入する |
| 2 | `autorun_security_kernel` の E2E が 1 件 skip | 送信ゲートウェイがテスト生成・実行段階でのみ有効で、クロール段階は別検査を通る構造。素直に書くと別機能を検証することになる。理由をテストに明記済み |

## 文書一覧

### 10_requirements — 要件定義

| 文書ID | 文書 |
|---|---|
| WS2D-RD-001 | [要件定義書](10_requirements/WS2D-RD-001_要件定義書.md) |
| WS2D-NF-001 | [非機能要件定義書](10_requirements/WS2D-NF-001_非機能要件定義書.md) |
| WS2D-BF-001 | [業務フロー図](10_requirements/WS2D-BF-001_業務フロー図.md) |
| WS2D-GL-001 | [用語集](10_requirements/WS2D-GL-001_用語集.md) |

### 20_design — 基本設計（外部設計）

| 文書ID | 文書 |
|---|---|
| WS2D-BD-001 | [基本設計書](20_design/WS2D-BD-001_基本設計書.md) |
| WS2D-SD-001 | [画面設計書](20_design/WS2D-SD-001_画面設計書.md) |
| WS2D-IF-001 | [API設計書](20_design/WS2D-IF-001_API設計書.md) |
| WS2D-DD-001 | [データ設計書（論理）](20_design/WS2D-DD-001_データ設計書.md) |
| WS2D-OD-001 | [帳票出力設計書](20_design/WS2D-OD-001_帳票出力設計書.md) |

### 30_implementation — 詳細設計（内部設計）・実装

| 文書ID | 文書 |
|---|---|
| WS2D-MD-001 | [モジュール設計書](30_implementation/WS2D-MD-001_モジュール設計書.md) |
| WS2D-PD-001 | [DB物理設計書](30_implementation/WS2D-PD-001_DB物理設計書.md) |
| WS2D-BA-001 | [バッチ設計書](30_implementation/WS2D-BA-001_バッチ設計書.md) |
| WS2D-CS-001 | [コーディング規約](30_implementation/WS2D-CS-001_コーディング規約.md) |

### 40_test — テスト

| 文書ID | 文書 |
|---|---|
| WS2D-TP-001 | [テスト計画書](40_test/WS2D-TP-001_テスト計画書.md) |
| WS2D-TV-001 | [テスト観点表](40_test/WS2D-TV-001_テスト観点表.md) |
| WS2D-UT-001 | [単体テスト仕様兼結果報告書](40_test/WS2D-UT-001_単体テスト仕様兼結果報告書.md) |
| WS2D-IT-001 | [結合テスト仕様兼結果報告書](40_test/WS2D-IT-001_結合テスト仕様兼結果報告書.md) |
| WS2D-ST-001 | [システムテスト仕様兼結果報告書](40_test/WS2D-ST-001_システムテスト仕様兼結果報告書.md) |
| WS2D-AT-001 | [受入テスト仕様書](40_test/WS2D-AT-001_受入テスト仕様書.md) |
| WS2D-TM-001 | [トレーサビリティマトリクス](40_test/WS2D-TM-001_トレーサビリティマトリクス.md) |
| WS2D-DL-001 | [不具合管理台帳](40_test/WS2D-DL-001_不具合管理台帳.md) |
| WS2D-TR-001 | [テストサマリレポート](40_test/WS2D-TR-001_テストサマリレポート.md) |
| WS2D-TS-050 | [想定ユースケース検証](40_test/WS2D-TS-050_想定ユースケース検証.md) |
| WS2D-TS-051 | [CLI想定ユースケース検証](40_test/WS2D-TS-051_CLI想定ユースケース検証.md) |

### 50_operation — 移行・運用

| 文書ID | 文書 |
|---|---|
| WS2D-EN-001 | [環境構築手順書](50_operation/WS2D-EN-001_環境構築手順書.md) |
| WS2D-MG-001 | [移行計画書](50_operation/WS2D-MG-001_移行計画書.md) |
| WS2D-MG-002 | [移行手順書](50_operation/WS2D-MG-002_移行手順書.md) |
| WS2D-OP-001 | [運用手順書](50_operation/WS2D-OP-001_運用手順書.md) |
| WS2D-TS-001 | [障害対応手順書](50_operation/WS2D-TS-001_障害対応手順書.md) |
| WS2D-RL-001 | [リリース手順書](50_operation/WS2D-RL-001_リリース手順書.md) |
| WS2D-UM-001 | [ユーザーマニュアル](50_operation/WS2D-UM-001_ユーザーマニュアル.md) |

### 60_quality — 品質・構成管理

| 文書ID | 文書 |
|---|---|
| WS2D-QA-001 | [品質保証計画書](60_quality/WS2D-QA-001_品質保証計画書.md) |
| WS2D-CM-001 | [構成管理計画書](60_quality/WS2D-CM-001_構成管理計画書.md) |
| WS2D-CR-001 | [変更管理台帳](60_quality/WS2D-CR-001_変更管理台帳.md) |

### 70_delivery — 納品

| 文書ID | 文書 |
|---|---|
| WS2D-DL-002 | [納品物一覧](70_delivery/WS2D-DL-002_納品物一覧.md) |
| WS2D-LI-001 | [OSSライセンス一覧](70_delivery/WS2D-LI-001_OSSライセンス一覧.md) |

## 納品形式

各文書は Markdown を正本とし、同じディレクトリに Word（`.docx`）を並べて置く。
一覧・マトリクス系は Excel（`.xlsx`）も併産する。Office ファイルは**生成物**であり、
手で編集しない。編集すると正本と乖離し、次回生成で失われる。

```bash
venv/bin/python scripts/extract_asbuilt.py      # コードから as-built 情報を抽出
venv/bin/python scripts/build_delivery_docs.py  # Word / Excel を生成
```

Word には表紙・機密区分・文書管理情報・承認欄・目次・図目次／表目次・
図表番号（図 N-M / 表 N-M）・ページヘッダー・ページ番号が入る。
mermaid 図は PNG に変換して埋め込まれる（`mermaid-cli` が必要）。

## 再現方法（監査者向け）

```bash
python scripts/quality_harness.py          # 要件契約の機械検証
make test                                  # L1/L2 単体・結合
make verify-ui                             # L3 E2E（要 Chromium）
make coverage                              # カバレッジ実測
venv/bin/python scripts/extract_asbuilt.py # as-built 情報の再抽出（差分で乖離を検出）
```

## 参照する既存文書（本体系からは複製しない）

| 内容 | 正本 |
|---|---|
| 障害報告フォーマット | `docs/INCIDENT_POSTMORTEM.md` |
| テスト戦略の詳細 | `docs/TESTING_STRATEGY.md` / `docs/TEST_LEVEL_POLICY.md` |
| 完了定義 | `docs/DEFINITION_OF_DONE.md` |
| 機能整合ゲート | `docs/process/functional-integrity-gate.md` |
| 設計判断の記録 | `docs/adr/*.md` |
| 認証・テナント方式 | `docs/AUTH_TENANCY.md` |
| バックアップ運用 | `docs/OPERATIONS_BACKUP.md` |
