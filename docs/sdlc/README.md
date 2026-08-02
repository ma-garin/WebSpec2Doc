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

### 参考値（2026-07-16 計測。本改訂では再計測していない）

| 指標 | 値 |
|---|---|
| L1/L2 テスト | 1,831 passed |
| L3 E2E テスト | 200 passed / 0 skipped |
| カバレッジ | 84.30%（閾値 80%） |

動的な実行結果は再計測していない。テスト資産は前回計測から大幅に増えているため、
上表は現構成の結果ではない。再計測するには `make test` / `make verify-ui` / `make coverage` を実行する。

## 既知のリスク（納品前に判断が必要）

| # | 内容 | 該当文書 |
|---|---|---|
| 1 | **critical 機能 11 件のうち 9 件が、テストレベル L3（E2E）で検証されていない**。認証(account_auth)・テナントメンバーシップ・テナント分離・AutoRun段階承認・セキュリティカーネル等は L1/L2 のみ。E2E 20 ファイルを grep で実測して確認済み | WS2D-ST-001 §6 / WS2D-TM-001 |
| 2 | サブパッケージ間の循環依存 3 件 | WS2D-MD-001 |
| 3 | OSS ライセンスに UNKNOWN が残る。再配布判断には個別特定が必要 | WS2D-LI-001 |
| 4 | 承認者・配布先・問い合わせ先が未設定（Word の承認欄は空欄） | 全文書 |

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
