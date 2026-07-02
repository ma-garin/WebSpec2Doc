# /doc-search — 技術ドキュメント特化検索

引数: $ARGUMENTS（例: `cc-sdd kiro commands`, `streamlit session_state`, `gemini api free limits`）

## 実行内容

code-doc-searchスキルのルールに従い、web_searchを最適化して実行します。

1. 引数からキーワードを3〜5語に整理
2. ターゲットが曖昧な場合は公式ドキュメント→GitHub→その他の優先順で検索
3. スニペットだけで不十分ならweb_fetchで全文取得
4. スキルのフォーマットで結果を出力（ソース・バージョン・要点・コード例）

引数が未指定の場合は何を調べるか確認する。
