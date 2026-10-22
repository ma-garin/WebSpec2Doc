# System06 Document Assurance

要件定義書などの文書を、決定論の規則で分析し、品質・矛盾・追跡・準備状態を判定する。
AI（Review Board）は候補を足すだけで、スコアと準備状態は変えない。確定は人が行う。
この文書群は実コードを読んで書いた事実のみ。実装の無い機能は「未結線・未実装」に分けて載せた。

## 索引

| 文書 | 内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 既存資産の分類と新パッケージの構成 |
| [DOMAIN_MODEL.md](DOMAIN_MODEL.md) | Entity・出所と状態の区別・フィールド |
| [RULE_ENGINE.md](RULE_ENGINE.md) | rule pack・検出器・NOT_EVALUATED・固有語 |
| [TRACEABILITY.md](TRACEABILITY.md) | ノード・辺・孤立・coverage の段 |
| [AI_REVIEW.md](AI_REVIEW.md) | 独立 Reviewer・証拠検証・DISPUTED・送信と同意 |
| [QUALITY_MODEL.md](QUALITY_MODEL.md) | 次元・スコア・準備状態ゲート・decisions |
| [API_CONTRACT.md](API_CONTRACT.md) | 全エンドポイント |
| [USER_FLOW.md](USER_FLOW.md) | 利用者の流れと画面の文言 |
| [SECURITY_REVIEW.md](SECURITY_REVIEW.md) | セキュリティレビュー |
| [INDEPENDENT_REVIEW.md](INDEPENDENT_REVIEW.md) | 独立レビューの指摘 |

実装: `web/services/docassure/`（分析）・`web/routes/doc_assure.py`・`web/routes/doc_assure_extra.py`（API）・`static/js/docassure*.js`（画面）。
評価: `quality/docassure_eval/README.md`（ベンチ結果）。

## 未結線・未実装・既知の限界

### 他システムとの連携

| 項目 | 状態 | 根拠 |
|---|---|---|
| System02 へのテスト候補 | JSON を返すだけ。取り込み口は未結線 | `integrations.py` の `WIRED = False`、`GET /tests` の `wired=false` |
| System09 への影響ペイロード | 同上 | `integrations.impact_payload`、`GET /impact` |
| System01 との実装突合 | 同上（観測結果を渡すと突合 JSON を返すのみ） | `integrations.alignment`、`POST /alignment` の `wired=false` |

- 送信・登録は一切しない。連携先に届いたことを示す証跡も無い。

### 分析に反映されないもの

| 項目 | 状態 | 根拠 |
|---|---|---|
| 組織の policy | 保存・取得のみ。分析に反映されない | `policy.as_pack_extra` を呼ぶ箇所が `web/` に無い |
| pack_extra（固有語） | HTTP から渡せない | `doc_assure.py` の analyze が `pack_extra` を渡さない |
| 準備状態の policy 引数 | 画面・API から指定不可 | `pipeline.analyze(policy=...)` を analyze ルートが渡さない |
| 複数文書の画面指定 | 画面は 1 文書（D1）のみ | `docassure.js` は本文なしで analyze を呼ぶ |

### 追跡・評価

| 項目 | 状態 | 根拠 |
|---|---|---|
| テスト・実行 Evidence の取込 | 取込口なし。常に NOT_EVALUATED | `pipeline.py` が tests・evidence なしで `build` を呼ぶ |
| テスト設計 coverage | 常に 0 件（全要件が「テスト未発見」候補） | 同上 |
| Traceability・Consistency | 文書 1 本では評価不能 | `pipeline.run_derived_scores` |
| Clarity | default pack では常に評価不能 | `quality.RULE_DIM` が pack の rule_id に当たらない |
| pack の指摘の次元減点 | 次元スコアに効かない | 同上（実測で全 12 rule_id が None） |
| READY への到達 | default pack・単一文書では到達しない | `readiness.gate` が主要次元と trace coverage を要求 |

### AI レビュー

- 実 API（OpenAI・Ollama）での検証は未実施。確認できたのは stub を想定したコード経路のみ。根拠: `review_board.py`・`AI_REVIEW.md`。
- AI の結果はスコア・準備状態に入らない（`mode=DETERMINISTIC_ONLY`）。
- 12 役 × 要件数の送信になり、件数上限・進捗表示が無い。キャッシュはプロセス内のみ。

### ベンチ・評価の限界

- ベンチは自作 fixture 63 件（期待 47 項目、トラップ 16 件）。実文書への一般化や他製品との優劣は示さない。根拠: `quality/docassure_eval/README.md`。
- 未検出 1 件（REQ-ITEMS）。ミューテーションは 12 件中 6 件検出（条件の削除・異常系の削除は 0/3 ずつ未検出）。
- holdout（調整に使わない検証用の組）は `quality/docassure_eval/README.md` に記載が無く、件数・作り方は未確認（自作で件数が少ないと保守者から聞いているが、コード上の確認は未検証）。
- 目標値（precision 0.98 以上等）は参考値で、外部基準ではない。

### 画面の導線が無いもの

- baseline・feedback・policy・regression・alignment・テスト候補・影響範囲・書き換え提案・analyzers（状態遷移・判定表・CRUD・非機能）は API のみ。根拠: `static/js/docassure*.js` が呼んでいない。
- レポートの JSON 形式は API のみ。

### 抽出・検出の限界

- 要件単位の抽出は正規表現による決定論。state・acceptance_criteria の項目は作らない。
- 規則の PASS は、検査件数 0 でも hit が無ければ PASS になる（`rules/engine.py`）。`INDEPENDENT_REVIEW.md` が同じ点を要確認としている。
- 矛盾検出の重大度は high / medium のみで critical は生成されない。
- 既知のセキュリティ指摘（expiry の形式未検証・decisions の件数上限なし等）は `SECURITY_REVIEW.md` を参照。修正済みかは本文書では確認していない（未検証）。
