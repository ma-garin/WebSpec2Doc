# reverse analysis（ローカル JS の静的候補と既存 snapshot の実測の対応付け）

ローカルにある配布済み JS を REA で静的解析し、既存クロールの snapshot に記録された API 実測と
**限定的に**並べて、`reverse_analysis.json` を 1 つ保存する明示モードです。クロールはしません。

> 実 REA（rea-agents 6.7.0）での動作と価値は**未検証**です。現時点の確認は、固定の Evidence を返す
> 偽の provider（fake）によるものだけです（[測定記録](../../tests/fixtures/reverse_analysis/VALUE_MEASUREMENT.md)）。

## 実行

```bash
venv/bin/python src/main.py --reverse-analysis \
  --js-input <ローカルの JS ディレクトリ> \
  --runtime-snapshot <既存クロールの snapshots/*.json> \
  --rea-command <導入済み rea 実行ファイルの絶対パス> \
  --output <reverse analysis 専用の空ディレクトリ>
```

- `--reverse-provider-evidence`（追加の指定）を付けると、`provider_evidence` を JSON の末尾に足します
  （route/API 候補の上流 node・observation と provider の状態、`imports` edge、source map の所見）。
  付けない場合の JSON のキーは従来と同じです。
- 4 つの引数はすべて必須です。`--url` `--urls` `--compare` `--ci` など他のモードとは併用できません。
- `--reverse-analysis` を付けない限り、REA の探索・起動、新しい出力は一切ありません。

## 入力の条件

| 入力 | 条件 |
|---|---|
| `--js-input` | 実在するローカルディレクトリ |
| `--runtime-snapshot` | 既存クロールの snapshot JSON |
| `--rea-command` | rea 6.7.0 の絶対パス |
| `--output` | 専用の空ディレクトリ |

- `--js-input`: 単体ファイル・ASAR・URL は不可。中に symlink・FIFO などがあると解析前に拒否します。
  source map は同じディレクトリ内のものだけを使い、HTTP で取りに行きません。
- `--rea-command`: 6.7.0 以外の版は `unsupported_provider_version` で止めます（自動で別の方法に切り替えません）。
  `npx`・install・update は行いません。
- `--output`: 入力ディレクトリの中・snapshot と同じディレクトリの中・symlink を経由する場所は拒否します。
  macOS の `/tmp` は `/private/tmp` への symlink なので、`/tmp/...` を指定すると拒否されます（`/private/tmp/...` を指定する）。
  `reverse_analysis.json` 以外のファイルがあるディレクトリも拒否します。
- 入力・snapshot・既存の report.json は読むだけで、書き換えません。

## status と終了コード

| status | 終了コード | 意味 |
|---|---|---|
| complete | 0 | 選択した入力の処理が完了 |
| partial | 2 | 確認できた範囲だけ保存 |
| unavailable | 2 | 静的解析を実行できず実測のみ |
| failed | 2 | 入力・応答の不正、timeout |
| cancelled | 130 | Ctrl-C などで取り消し |

- complete は「全システムを網羅した」「確定した仕様」という意味ではありません。
- 失敗・取り消しでも書き込めれば `reverse_analysis.json` を保存し、画面に理由と次の行動を出します。
  保存できなかったときは「成果物はありません」と次の行動を stderr に出し、出力先は表示しません。
- 解析の上限は 120 秒（版確認は 5 秒）、REA の出力は 32MiB まで。超えたら REA とその子プロセスを止め、
  途中までの出力は採用しません。

## 結果の読み方（4 つを区別する）

| 区分 | JSON の場所 | 言えること |
|---|---|---|
| 実測 | runtime_observations | snapshot に記録あり |
| 静的構文の事実 | static_candidates | JS 内に構文あり |
| 対応推論 | relations | 一致の可能性 |
| 未確認 | relations の unknown | 判断を保留 |

- **実測**は snapshot の API 記録数です。API の総数・呼び出し回数・網羅率ではありません。
  各記録は snapshot の SHA-256 と JSON pointer で元の位置へたどれます。接続先 origin と query は
  snapshot に保存されていないため `origin: null` です。画面の URL を API の接続先とはみなしません。
- **静的構文の事実**は「その構文が JS のその位置にある」ことだけです。実行された・API が存在する証明ではありません。
  位置は 1 始まりの行・0 始まりの UTF-16 列（終端は含まない）で、ファイルの相対 path と SHA-256 が付きます。
- **対応推論**: `matched` は現在の snapshot からは出ません（常に 0）。method と path が一致しても
  origin が記録されていないので、最大でも `inferred` です。複数の候補・観測がありうるものは `ambiguous` として全部残します。
- **未確認（unknown）**: 動的な式・method 不明・query に依存する候補、静的候補の無い実測は自動では対応付けません。
  「未観測」は「存在しない」「到達できない」という意味ではありません。

## 既知の制限（現在の slice）

- **REA 6.7.0 の endpoint は HTTP method を返しません**（実 REA で確認。`fetch(..., {method:"POST"})` や
  `xhr.open("PATCH", ...)` でも値が出ません）。そのため静的 API 候補と実測の対応は全部 `unknown` です。
  ダミーの method を補って対応を作ることはしません。
- **route 候補**: 実 REA は endpoint の `endpoint_kind=route` で画面ルートの宣言を返します。これを API ではなく
  `route` 候補にし、状態は `inferred`（provider の AST 構文としては observed。制限欄の
  `provider_syntax_state:observed` と `provider_evidence` で区別）にします。route は snapshot の API 実測とは
  比べず、同じ path が複数なら `ambiguous`、それ以外は `unknown` です。
- **module の依存関係**: `--reverse-provider-evidence` のときだけ、REA graph の `imports` edge を上流の
  node ID・kind・出典のまま `dependency_edges` に保存します（module 候補と独自に同一視しません）。
- source map:
  - 解析後に map が変わった・壊れた → `source_map_stale`＋`static_artifact_digest_mismatch`（partial）
  - map が無い → `source_map_stale`＋`static_artifact_not_verified`（partial）
  - REA が元ソースを解決できなかった → `source_map_unresolved`（status は変えない）
  - 実 REA が返す map の欠落（`resolution_status=not-found`）と解析失敗（`Source map is not valid JSON.`）は、
    REA の理由・状態・範囲をそのまま `provider_source_map_not_found`／`provider_source_map_parse_failed` の
    診断と coverage の制限に残します（解析失敗は partial・終了コード 2）。
  - 古い `sourcesContent` は REA も本ツールも検出しません。元ソース名と digest は記録しますが、
    鮮度と generated→original の行対応は未確認です（`source_map_freshness_not_verified`・
    `generated_to_original_range_not_provided`）。
  - map の中身は解釈せず digest だけを照合するため、「古い map」と「壊れた map」は区別しません。
    いずれも元ソース名を推測で埋めず、候補は `unknown` にします。
  - 検証範囲（AC6 は一部のみ）: 自動テストの old/broken は「provider の解析後に map を改変した」場合の検知だけです。
    解析前から古い・壊れた map を実 REA がどう扱うかは未検証です（実 REA を実行していません）。
  - coverage の欠測理由には、候補に実在する理由（`artifact_digest_mismatch`／`artifact_file_not_verified`）だけを載せます。
  - map に元ソースの本文が無い場合は、元ソース名だけを記録します（`original_source_content_unavailable`）。
- REA の未対応 node（`javascript-asset`・`source-map` など）は捨てずに、kind と出力内の位置を診断に残します。
- 同じ入力・同じ provider の応答からは同じバイト列の JSON になります。処理時間は JSON に入れません。

## 価値の確認状況

| 項目 | 状態 |
|---|---|
| fake provider での受入 | 確認済み |
| 実 REA での価値（AC10） | 確認済み（固定 8 問で Before 2 → After 7） |

実 REA 6.7.0 の測定は [REAL_REA_VALUE_MEASUREMENT.json](../research/reverse-analysis/REAL_REA_VALUE_MEASUREMENT.json)。
自己所有の controlled fixture（`tests/fixtures/reverse_analysis/real/app`）に対する固定質問集の正答数で、
製品全体の能力点ではありません。HTTP method の質問は Before/After とも未回答です。

fake provider の測定では、固定 snapshot（API 実測 3 件）に対して、実測に無い静的 Evidence が 3 件増えました
（別 origin の API・動的 path の呼び出し位置・map からの元ソース名）。実測と同じ path の候補 1 件は数えていません。
詳細と費用は [VALUE_MEASUREMENT.md](../../tests/fixtures/reverse_analysis/VALUE_MEASUREMENT.md)。
