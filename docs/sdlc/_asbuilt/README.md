# _asbuilt — 機械抽出された as-built 設計情報

本ディレクトリは **SDLC 文書の入力データ**であり、それ自体は納品文書ではない。
`scripts/extract_asbuilt.py` がソースコード・SQLite スキーマ・パッケージメタデータから
機械的に生成する。

## なぜ機械抽出するか

エンドポイントは実測 196 本、モジュールは 237 本ある。この規模を手書きで設計書に写すと
必ず取りこぼしが出る。さらに、手書きの一覧はコードが変わった瞬間に嘘になる。
**as-built 文書はコードを正とし、再生成できる形で維持する。**

実際、`docs/sdlc/README.md` は「エンドポイント 121 本」と記録していたが、
実測は 196 本だった。この乖離が手書き台帳の限界を示している。

## 生成方法

```bash
venv/bin/python scripts/extract_asbuilt.py
```

## ファイル

| ファイル | 内容 | 抽出元 | 参照する文書 |
|---|---|---|---|
| `routes.json` | Flask エンドポイント一覧（blueprint / method / path / 関数 / 概要） | `web/routes/*.py` を AST 解析 | WS2D-IF-001, WS2D-SD-001 |
| `modules.json` | src・web のモジュール / クラス / 公開関数 / 内部依存 | `src/**/*.py`, `web/**/*.py` を AST 解析 | WS2D-MD-001 |
| `schema.sql` | SQLite 物理スキーマ（DDL） | `instance/*.db` の `sqlite_master` | WS2D-PD-001, WS2D-DD-001 |
| `licenses.json` | 依存 OSS のライセンス | `importlib.metadata` + `npm ls` | WS2D-LI-001 |
| `templates.json` | Jinja2 テンプレートと extends / include 関係 | `templates/**/*.html` | WS2D-SD-001 |

`instance/*.e2e.db`（テスト専用 DB）はスキーマ抽出から除外している。

## 更新のタイミング

ルート追加・モジュール追加・スキーマ変更・依存追加を行ったら再実行し、
差分が出た文書を更新する。設計書とコードの乖離は、この差分で検出できる。
