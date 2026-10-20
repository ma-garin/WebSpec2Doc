# reverse_analysis fixture の出所

- `app/`・`real/app`・`real/missing`・`real/malformed`: 自己所有の小さな JS 入力（Native 静的解析の入力）。
- `runtime_snapshot.json`: 既存クロールの snapshot 形式で手組みした実測側の入力（API 2 件）。

外部ツール（旧 REA）の出力 fixture は撤去済み。解析結果の期待値はテストが Native 解析の結果から作る。
