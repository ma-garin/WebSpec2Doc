# static/vendor/ — 同梱サードパーティ資産

CSP（`web/security.py` の `script-src 'self' 'unsafe-inline'`）は変更しない方針のため、
外部 JS は CDN から読み込まず、この配下に同梱して `'self'` 経由で配信する。

## Mermaid（解析HTML「テスト分析インプット」用・R3-18a）

2026-07-06 時点の取得試行結果:

- `curl -L -o static/vendor/mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js`
  を実行 → **サンドボックスのネットワークポリシーにより CDN (`cdn.jsdelivr.net`) への
  接続がブロックされ、HTTP 403 で失敗**（証跡: `curl: (22) The requested URL returned
  error: 403`）。ダミーファイル・偽の JS は作成していない（evidence-only 原則）。
- ただし本リポジトリには **既に検証済みの Mermaid 同梱資産が
  `static/vendor/mermaid/mermaid.min.js` に存在する**（コミット
  `b017716 feat: レポートUX刷新をセキュリティ強化付きで統合 (#25)` で追加済み。
  `static/js/view-transition.js` がアプリ内プレビューで既に読み込んでいる実績あり）。
  - バージョン: 10.9.3（`static/vendor/mermaid/ASSET.md` に記録）
  - SHA-256: `5a8ec91820bd55afef049068489369910e5d6ce70c8103952f27e29d3e76e8bc`
    （`shasum -a 256 static/vendor/mermaid/mermaid.min.js` で本セッションでも再検証し一致を確認済み）
  - 出典: `https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js`
  - ライセンス: `static/vendor/mermaid/LICENSE`（MIT）

上記の理由により、新規に重複した `mermaid@10.9.1` を取得・同梱することはせず、
**既存の検証済み資産 `static/vendor/mermaid/mermaid.min.js` を
`src/generator/html_reporter.py` の `_mermaid_script()` からも参照する**方針とした
（計画書 B-1 からの逸脱。理由: 同一資産の二重管理を避けるため）。

## `_mermaid_script()` の挙動（`src/generator/html_reporter.py`）

- アプリ内 `/preview`（Flask 経由・CSP 適用下）: `/static/vendor/mermaid/mermaid.min.js`
  を `'self'` から読み込み、`mermaid.initialize({startOnLoad:true, securityLevel:'strict'})`
  で初期化する。
- レポート単体をダウンロードしてローカルで直接開いた場合（Flask 非経由・CSP 非適用）:
  `/static/vendor/...` は解決できないため、`window.mermaid` が未定義であれば
  CDN (`cdn.jsdelivr.net`) からのフォールバック読み込みを試みる（`static/js/view-transition.js`
  はアプリ内専用のためこのフォールバックを持たないが、`report.html` はスタンドアロン
  配布物であるため必要）。
- `securityLevel:'strict'` を明示し、Mermaid 側の XSS 対策を有効化する。
- `web/security.py` の CSP 文字列はこの対応において変更していない。
