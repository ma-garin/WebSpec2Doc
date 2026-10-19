# reverse_analysis fixture の出所

`rea_6_7_0_application_evidence.json` は実 REA の実行結果ではない。rea-agents 6.7.0 固定タグの
schema に沿って手で組み、commitment（`ev_` / `jag_` / `jag_node_` / `jag_observation_` /
`jag_edge_`）を `src/reverse_analysis/rea_adapter.py` の正規 JSON で計算したもの。
`app/` の 3 ファイル（自己所有）の SHA-256 と一致する。

## 形の根拠（https://github.com/morluto/rea/tree/rea-agents-6.7.0）

| 部分 | 根拠ファイル |
|---|---|
| Evidence の外枠・evidence_id | src/domain/evidence.ts |
| provider id/name/version | src/application/InvestigationProviders.ts |
| predicate・authority・confidence | src/application/javascript/JavaScriptApplicationEvidenceGraph.ts |
| normalized_result・summary・statistics | src/domain/javascript/javascriptApplicationAnalysis.ts |
| graph・node・observation・edge | src/domain/javascript/javascriptApplicationGraphSchemas.ts |
| evidence・identity・coverage・location | src/domain/javascript/javascriptApplicationEvidenceSchemas.ts |
| source_map_reference | src/domain/javascript/javascriptSourceMapPaths.ts |
| ID の計算・正規 JSON | javascriptApplicationGraph.ts・src/domain/canonicalDigest.ts |
| endpoint の properties | docs/javascript-application-workflows.md・javascriptStaticAnalysis.partialEndpoints.test.ts |
| semantic_graph の形・`jsrg_` 系 ID | src/domain/javascript/javascriptSemanticGraph{,Schemas}.ts |
| CLI の argv・`--json` の出力枠 | src/cli/electronCommands.ts・src/cliCommandNames.ts・scripts/rea.mjs・src/cliOutput.ts・src/cli/cliResultOutput.ts |
| `--version` の出力（`6.7.0\n` のみ） | src/cli.ts（`Cli.create` の version）・incur 0.6.1 の src/Cli.ts と e2e.test.ts |

## 一次 test vector との照合

- 正規 JSON: 6.7.0 の src/domain/canonicalDigest.test.ts の固定入力のうち JSON で表せる 3 件を
  `test_canonical_json_matches_upstream_canonical_digest_vectors` で照合（期待値は上流が比較する
  JSON.stringify・`Object.keys().sort()` の規則から導出）。
- ID（`jag_*`・`jsrg_*`・`ev_`）: 6.7.0 のテストに ID のリテラル期待値は無い（javascriptApplicationGraph.test.ts・
  canonicalDigest.test.ts を確認）。自前計算の ID を一次の値で照合することはできておらず未検証。

## 一次情報で確定できず、schema の許す範囲で置いた値

- `semantic_graph`: 上流 schema の全キーを持つ最小グラフ（`module` node 1 個・relation/fingerprint/
  unknown 0 件・12 family すべて complete）。node の `role_key`・`label`、coverage の値は schema の
  許す範囲で置いた値で、実 REA が同じ入力で出す内容かは未確認。`/tmp/ws2d-task02/build_sg.py`
  （リポジトリ外）で生成し、`recommit` で commitment を計算し直した。
- `root_artifact_sha256`・`inventory_*`: directory digest の算法は未確認のため任意の digest。
- endpoint identity の `namespace`/`key`、`extractor` の文字列、`parameters`、source-map の
  `declared_url_sha256` の計算対象。
- 実 REA の出力でこの fixture と同じ commitment が出るかは未検証（実 provider 未実行）。
