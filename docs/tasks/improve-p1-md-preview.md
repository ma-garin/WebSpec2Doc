# タスク: P1-11 — techniques.md のブラウザ内 Markdown プレビュー

**優先度**: P1（今すぐ）  
**背景**: エクスポートに techniques.md を追加したが、`/preview?path=...` はプレーンテキストとして返す。Markdown を HTML に変換してプレビューできると品質確認が楽になる。

## ゴール

`/preview?path=...` で `.md` ファイルを開いたとき、Markdown が HTML にレンダリングされて表示される。

## 触るファイル

- `templates/preview.html`（または preview 用テンプレート） — `marked.js` を CDN から読み込み、`.md` の場合に変換
- `web/routes/preview.py`（または相当ルート） — `.md` か否かをフロントに伝える `is_markdown` フラグを追加

**変更禁止**:
- `src/` 以下の Python ファイル（バックエンド生成ロジックは変更しない）

## 実装の指針

### バックエンド変更（`web/routes/preview.py` 相当）

```python
is_markdown = path.suffix == '.md'
return render_template('preview.html', content=text, is_markdown=is_markdown)
```

### フロント変更（`templates/preview.html`）

```html
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js"
        integrity="sha384-948ahk4ZmxYVYOc+rxN1H2gM1EJ2Duhp7uHtZ4WSLkV4Vtx5MUqnV+l7u9B+jFv+"
        crossorigin="anonymous"></script>
<script>
  if ({{ is_markdown | tojson }}) {
    document.getElementById('preview-body').innerHTML =
      marked.parse(document.getElementById('preview-body').textContent);
  }
</script>
```

## 完了条件

- [ ] `techniques.md` を preview で開くと Markdown が HTML レンダリングされる
- [ ] `.json` / `.html` 等の非 Markdown ファイルはプレーンテキストのまま
- [ ] `python -m pytest tests/ -q` が全 PASS
- [ ] `make verify-ui` が PASS

## スコープ外

- marked.js のローカルバンドル（CDN で十分）
- シンタックスハイライト（コードブロック以外は不要）
- 他の `.md` ファイル（userguide.md 等）への適用（今回は preview 画面のみ）
