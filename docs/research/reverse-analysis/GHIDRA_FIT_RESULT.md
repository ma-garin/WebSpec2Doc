# Ghidra 適合性 Phase A 結果（2026-10-20）

判定: **LATER**（製品コードは変更しない）

## 実測（A-1〜A-3）
| 項目 | 結果 |
|---|---|
| REA | 6.7.0（`rea --version`）。Node 24.11.0（REA 同梱）、ホストの node は v25.6.0 |
| host | Darwin arm64（macOS 27.0.1） |
| JDK | OpenJDK 23.0.2（Homebrew）。REA の Ghidra 既知 baseline は JDK 21 |
| Ghidra | **未導入**（/Applications・~・Homebrew に無し、`GHIDRA_INSTALL_DIR` 未設定） |
| provider | `rea doctor`: ghidra = `missing_analysis_engine`（「Ghidra 12.1.x を展開し GHIDRA_INSTALL_DIR を設定」）→ **provider_unavailable** |
| REA の対応 | capabilities に provider `ghidra` あり。同梱 bridge（`bridge/ghidra`）・Ghidra 12.1.4 のライセンス文書あり。native 用コマンド: analyze（--provider）、function、decompile、inspect-native-api / -instruction / -load-image / -data-type、inspect-managed-native-boundaries 等 |

## GO 条件の評価
| 条件 | 結果 | 根拠 |
|---|---|---|
| GO-1 provider 利用可能 | 不成立 | Ghidra 未導入。導入は利用者の承認が必要（本タスクでは導入しない） |
| GO-2 fixture で関数・アドレス・xref | 未実施 | GO-1 不成立のため実行不能 |
| GO-3 Evidence へ正規化 | 未評価 | 実出力が無い |
| GO-4 既存に無い QA 情報 | 可能性のみ | native export・関数呼び出し関係は既存の JS 解析では取れないが、未実測 |
| GO-5 実利用シナリオ | 不成立 | 現在の対象は Web サイト（demo.realworld.show 等）。Electron .node addon・native helper・デスクトップアプリの対象が無い。System01 app は試作（実解析なし） |
| GO-6 追加コスト | 未測定 | 起動・初回解析・メモリは Ghidra 無しでは測れない |

## LATER の理由
1. 実行環境が無い（Ghidra 12.1.x・JDK 21 系が未導入）
2. 価値を生む対象（ネイティブ成果物）が今の利用に無い
3. 既存の REA JavaScript 解析で、現在の対象（Web）の route・API・module 依存は取れている

## 再開の条件（どれか 1 つ＋環境）
- Electron アプリ・.node addon・native helper を QA 対象にする具体案件が出た
- System01 app を試作から実解析へ進める（APK/.app の native 部分）
- 上記に加え、利用者が Ghidra 12.1.x と JDK 21 の導入を承認

再開時は本書の GO-2〜GO-6（controlled fixture・性能・Product Truth）から始める。製品側の設計方針（REA 経由・opt-in・`native_analysis` を別キー・decompile は reconstructed）は指示書 v2 に従う。
