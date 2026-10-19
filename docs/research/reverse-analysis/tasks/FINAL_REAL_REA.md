# 実REA最終統合（Opus5.5限定）

必読: CLAUDE.md / AGENTS.md / docs/design/specs/CONVENTIONS.md / .claude/rules/functional-integrity.md / IMPLEMENTATION_PLAN.md / IMPLEMENTATION_REVIEW.md（同ディレクトリ）。
既存Task1〜4/190件PASSはやり直さない。利用者がREA6.7.0導入と実行、最小実装、局所テストと最終品質ゲートを承認した。
実REA executable: ~/.local/share/webspec2doc-tools/rea-6.7.0/bin/rea。Node24.11.0/REA6.7.0確認済み。実パッケージは同prefixのnode_modules/rea-agents。
この指示書には実測結果が後で追記される。追記されたWave A証拠のみを根拠に最小変更する。
許可: src/reverse_analysis/*.py、tests/test_reverse_analysis_*.py、tests/fixtures/reverse_analysis/、docs/guide/reverse-analysis.md、quality/feature_contracts.yml、docs/research/reverse-analysis/REAL_REA_VALUE_MEASUREMENT.json。実測fixture/scriptはこのfixtures配下に必要最小限追加可。src/main.pyは必要な明示CLI接続修正だけ可。
禁止: install/update/setup（REA導入はCodexが完了）、Ghidra/Android/GUI/System09/指揮、外部送信、無関係refactor、既存報告/入力の破壊、git操作commit/push/merge/pull、AC意味論の弱体化、推測でroute/module/methodを生成、別agent起動。
methodは実REA Evidenceに根拠がある時だけ保持し欠測GET禁止。静的構文のobservedと実行observedを区別、inferredをobservedへ昇格しない。route候補はinferred、関連不明unknown、複数ambiguous。runtime origin欠測ならmethod/path一致最大inferred。
module/importedgeはREAのsource/target/kind/evidence/location/provider/limitationsを実際に返した範囲で保存。既存schema互換は維持し、standalone reverse_analysis.jsonのみ。
realprovider互換の必要最小修正、実際に存在するroute/module/method Evidence保持、source map diagnostics保持、deterministic output、path/symlink/permission/cancel/atomic/flagOFFを維持。存在しないEvidenceは未取得と記録しADOPTを捏造しない。
最初は変更範囲の局所テストのみ。最後にreverse_analysis5tests+test_apispec_recovery.pyを1回、品質ゲートも最終段階1回にまとめる。全体pytestは時間がかかる場合ログを保存して完了まで待つ。CIや自動wake禁止。
最終品質: black（対象のみ）/ruff（対象のみ）/mypy（reverse_analysis＋必要範囲）/bandit（対象src）/quality_harness/既存tests非E2Eを実行可能な範囲で1回ずつ。既存の範囲外failureを勝手に修正しない。ログ/tmp/ws2d-real-final-*.log。ソース編集完了後の検証中は編集せず、FAIL修正が必要なら修正理由を明示して該当検査のみ再実行。
実REA Before/Afterは自己所有controlled fixtureと固定snapshot同条件。各候補kind/実測/関連/有用な新Evidence/誤抽出/追加wallを実測。根拠あり有用Evidence1件未満AC10Fail。相対スコアは明示した評価集合・同じ尺度と分母が実測できる場合だけBefore100/Afterを計算し、全製品能力点と称さない。未測定を勝手に点数化しない。
実REA原本出力のfixture（機密なし・相対化/正規化を行うなら加工内容明示）、実CLIのreverse_analysis.jsonと測定要約を残す。絶対root/生source全文を製品JSONへ入れない。
終了時: 変更files、テスト/各品質ゲート結果、実証artifact、AC判定の不足を短く報告。Codexが最終diffを独立レビューし最終判定する。

## Wave Aの実測（確定済み、再調査しない）

- A1: /private/tmp/ws2d-real-a1/summary.json、stdout.json、app.js/lib.js。実REA exit0 9.69s、route3 API7。routeはgraph.nodes kind=endpointのobservations[].properties.endpoint_kind='route'（/users,/users/:id,/settings）。現在の全endpoint→apiは誤分類。properties.value/mechanismとevidence/source-range/source_map_referenceを保持する。routeは候補意味論でinferredに下げ、upstreamのAST構文observedは別provenanceに保持して区別する。複数route候補関係ambiguous、不明unknown。routeをruntime APIへ比較しない。
- HTTPmethod: fetch明示POSTやXHR.open PATCHもverb値がEvidenceにない。semantic request.properties.method='fetch'は関数名でHTTPmethodでない。supplies-request-field field=methodの値POSTは未出力。axios.post/getのmechanismはmember構文のみ、receiver/HTTP意味論は未証明。今回はunknown維持が最小安全。method_missingテスト維持、method_present純粋テストを維持。既存CLAIM methodGET等捏造禁止。
- A3: /private/tmp/ws2d-real-a3/summary.json、stdout.json、fixture dirを同summary参照。実REA exit0 4.001s、current validate_evidence PASS。graph.edges imports=8（contains8/exposes6/calls1も有）。実edge keysはsource_node_id,target_node_id,relation:'imports',properties(kind:static-import/dynamic-import/require,specifier,resolved_path,resolution_status等),evidence(state inferred,authority static-relationship-inference,artifact,location source-range,extractor,coverage,limitations,evidence_ids),edge_id,identifier_strategy。sourceがexport-bindingもあるのでmoduleと独自同一化しない。upstream node ID/kind/identityを保った参照と出典を持つdependency_edges等として新JSONへ保存。graph/semantic重複を推測で合算しない（最小graph importsのみ可）。
- A2: /private/tmp/ws2d-real-a2/summary.json。各CASE.stdout.json、out-CASE/reverse_analysis.json、fixture pathはsummary参照。現adapterは実REA4ケース全て受入。normal REA exit0→complete/exit0、missing exit0→complete/exit0、stale exit0→complete/exit0、malformed exit0→partial/exit2。missingにmap resolution_status=not-found＋制限、malformedにunknown node『Source map is not valid JSON.』state unavailable/coverage partial。現normalizeが具体理由を捨ててunsupportedのみのためproducer診断/制限を意味そのまま保存。stale古いsourcesContentは検出されない→鮮度未確認と明記、WebSpec側で検出したと捏造しない。正常mapからsource名/digest/map参照あり、正確なgenerated→original range未確認（source location map artifact-pathのみ）。

## 実装の出口（急いで最小差分）
1. route/API分類修正、route inferredとsource provenance/map参照保持、route relation unknown/ambiguousの純粋ルール。
2. importsを捨てないdependency_edgesとsource/target upstream参照、現JSONschema1への追加は独立opt-inモードだけ。既存190テストの測定fixture hash/bytesがschema変更で変わる場合は根拠を記録して更新し、古い性能実測を新schemaでの実測と称さない。
3. source-map missing/malformed provider診断とstate/coverageを落とさず保存・CLI提示。元ソース名と正確な行mapping/鮮度保証を混同しない。
4. 実REAのcontrolled fixture（A1/A3/正常mapを自己所有dirにまとめてもよい）で実CLI→JSONを通しAC3/6/10と決定性/取消を実証。以前の実測4mapケースは再実行不要、変更したnormalizeへの保存・診断確認はrawを再利用可。実価値のBefore/Afterは新統合fixtureで最低限必要な回数のみ。
5. 実REA原本をfixtureとしてテスト、route/ambiguous/unknown/map/module/method欠測/誤JSON/決定性の局所回帰→最終関連回帰と品質ゲートを各1回。
6. REAL_REA_VALUE_MEASUREMENT.jsonへ実数/実出典/QA質問単位の有用性/追加wall/未検証を保存。相対スコアはcontrolled fixtureの固定QA質問集に根拠付きで答えられた数をBefore/After同尺度で計算できる場合だけ（製品全能力の点数と誤解させない）。最低1件の実有用根拠がなければAC10Fail。

レビュー記録はCodexが更新するため編集しない。短い段階報告をstreamへ出す。実装が終わったら必要ゲートを実行し、未検証/既存範囲外failureを短く返す。
