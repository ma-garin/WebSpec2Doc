"""撮影済みスクリーンショットから画面カタログ HTML を生成する。"""
from __future__ import annotations
import html, json, sys
from datetime import datetime
from pathlib import Path

SHOTS = Path(sys.argv[1])
OUT = Path("docs/screens/index.html")
recs = json.loads((SHOTS / "merged.json").read_text(encoding="utf-8"))

GROUP_ORDER = [
    ("認証・オンボーディング", "ログイン必須モード（WEBSPEC2DOC_AUTH_MODE=required）で撮影。初期セットアップ〜ログイン〜テナント選択までの導線。"),
    ("入口", "起動直後に到達する画面。認証オフ運用ではアプリ本体が直接開く。"),
    ("System 01 ドキュメント作成", "URL からQAドキュメント一式を生成する主機能。"),
    ("System 01 / 実行結果タブ", "実行結果画面（/runs/<domain>/<run_id>）の成果物タブ・サブタブ・図種別を全階層展開したもの。"),
    ("System 01 / テスト観点タブ", "観点ライブラリ画面のタブ。"),
    ("System 02 テスト活動支援", "ISTQB のテスト活動 12 工程。管理者のみ到達できる。"),
    ("共通", "システムをまたいで使う画面。"),
    ("共通 / 設定タブ", "設定画面の全タブ（URL 直リンク可能）。"),
    ("モーダル / オーバーレイ", "画面遷移を伴わない重ね表示。DOM の hidden を外して撮影している。"),
    ("共通UI状態", "同一画面のUI状態差分。"),
    ("レスポンシブ（モバイル幅）", "390×844（iPhone 相当）での表示。"),
]

by_group: dict[str, list[dict]] = {}
for r in recs:
    by_group.setdefault(r["group"], []).append(r)
for g in by_group:
    if g not in [x[0] for x in GROUP_ORDER]:
        GROUP_ORDER.append((g, ""))

def e(s) -> str:
    return html.escape(str(s if s is not None else ""))

total = len(recs)
ok = sum(1 for r in recs if r.get("ok"))
ng = total - ok
stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

nav_items = []
cards = []
for gi, (g, gdesc) in enumerate(GROUP_ORDER, start=1):
    items = by_group.get(g, [])
    if not items:
        continue
    gid = f"g{gi}"
    nav_items.append(
        f'<a class="nav-item" href="#{gid}"><span class="nav-name">{e(g)}</span>'
        f'<span class="nav-count">{len(items)}</span></a>'
    )
    cards.append(f'<section class="group" id="{gid}">')
    cards.append(f'<div class="group-head"><h2>{e(g)}</h2>'
                 f'<span class="badge badge-new">{len(items)} 画面</span></div>')
    if gdesc:
        cards.append(f'<p class="group-desc">{e(gdesc)}</p>')
    cards.append('<div class="shot-list">')
    for r in items:
        sid = r["id"]
        okf = r.get("ok")
        status = r.get("status")
        st_cls = "badge-low" if status == 200 else ("badge-medium" if status else "badge-critical")
        final = r.get("final_url") or ""
        redirect = ""
        path = r.get("path", "")
        if final and path and not path.startswith("/") is False and final not in (path,) and "→" not in path:
            if final.split("?")[0] != path.split("?")[0]:
                redirect = f'<span class="meta-chip">実際の遷移先 <code>{e(final)}</code></span>'
        img = (f'<a class="shot-frame" href="shots/{e(sid)}.webp" target="_blank" rel="noopener">'
               f'<img loading="lazy" src="shots/{e(sid)}.webp" alt="{e(r["name"])}"></a>'
               if okf else
               '<div class="shot-frame shot-failed">撮影に失敗（未取得）</div>')
        cards.append(f'''<article class="shot" id="{e(sid)}">
  <header class="shot-head">
    <span class="shot-id">{e(sid)}</span>
    <h3 class="shot-name">{e(r["name"])}</h3>
    <span class="badge {st_cls}">{e(status) if status else "撮影失敗"}</span>
  </header>
  <p class="shot-note">{e(r.get("note", ""))}</p>
  <div class="shot-meta"><span class="meta-chip">URL <code>{e(path)}</code></span>{redirect}
    <span class="meta-chip">title <code>{e(r.get("title", "-"))}</code></span></div>
  {img}
  {'' if okf else '<p class="shot-error">' + e(r.get("error", "")) + '</p>'}
</article>''')
    cards.append('</div></section>')

doc = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WebSpec2Doc 画面カタログ — 全 {total} 画面</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
:root {{
  --color-primary:#1976D2; --color-primary-light:#E3F2FD; --color-primary-dark:#0D47A1;
  --color-bg:#F8F9FA; --color-surface:#FFFFFF; --color-surface-2:#F1F3F4;
  --color-border:#E0E0E0; --color-divider:#F0F0F0;
  --color-text:#212121; --color-text-secondary:#616161; --color-text-disabled:#9E9E9E;
  --color-critical:#D32F2F; --color-high:#F57C00; --color-medium:#FBC02D;
  --color-low:#388E3C; --color-info:#0288D1;
  --color-critical-bg:#FFEBEE; --color-high-bg:#FFF3E0; --color-medium-bg:#FFFDE7;
  --color-low-bg:#E8F5E9; --color-info-bg:#E1F5FE;
  --font-main:'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif;
  --font-mono:'JetBrains Mono','Consolas',monospace;
  --text-xs:11px; --text-sm:13px; --text-base:14px; --text-md:16px;
  --text-lg:18px; --text-xl:22px; --text-2xl:28px;
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px;
  --space-6:24px; --space-8:32px; --space-12:48px;
  --radius-sm:4px; --radius-md:8px; --radius-lg:12px; --radius-full:9999px;
  --shadow-sm:0 1px 3px rgba(0,0,0,.08); --shadow-md:0 2px 8px rgba(0,0,0,.12);
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--color-bg); color:var(--color-text);
  font-family:var(--font-main); font-size:var(--text-base); line-height:1.7; }}
code {{ font-family:var(--font-mono); font-size:var(--text-xs); }}
.layout {{ display:grid; grid-template-columns:260px 1fr; min-height:100vh; }}
.sidenav {{ background:var(--color-surface-2); border-right:1px solid var(--color-border);
  padding:var(--space-4); position:sticky; top:0; height:100vh; overflow-y:auto; }}
.brand {{ font-weight:700; font-size:var(--text-md); margin-bottom:var(--space-1); }}
.brand small {{ display:block; font-weight:400; font-size:var(--text-xs);
  color:var(--color-text-secondary); }}
.nav-item {{ display:flex; justify-content:space-between; align-items:center; gap:var(--space-2);
  padding:8px 10px; margin-top:2px; border-radius:var(--radius-sm);
  color:var(--color-text); text-decoration:none; font-size:var(--text-sm); min-height:40px; }}
.nav-item:hover {{ background:var(--color-primary-light); color:var(--color-primary-dark); }}
.nav-count {{ background:var(--color-surface); border:1px solid var(--color-border);
  border-radius:var(--radius-full); padding:0 8px; font-size:var(--text-xs);
  color:var(--color-text-secondary); }}
main {{ padding:var(--space-8) var(--space-8) var(--space-12); max-width:1180px; }}
h1 {{ font-size:var(--text-2xl); margin:0 0 var(--space-2); }}
.lead {{ color:var(--color-text-secondary); font-size:var(--text-sm); margin:0 0 var(--space-6); }}
.stat-row {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
  gap:var(--space-4); margin-bottom:var(--space-6); }}
.stat {{ background:var(--color-surface); border:1px solid var(--color-border);
  border-radius:var(--radius-md); padding:var(--space-4); box-shadow:var(--shadow-sm); }}
.stat b {{ display:block; font-size:var(--text-2xl); line-height:1.2; }}
.stat span {{ font-size:var(--text-xs); color:var(--color-text-secondary); }}
.panel {{ background:var(--color-surface); border:1px solid var(--color-border);
  border-left:4px solid var(--color-info); border-radius:var(--radius-md);
  padding:var(--space-4) var(--space-6); margin-bottom:var(--space-6); }}
.panel h3 {{ margin:0 0 var(--space-2); font-size:var(--text-md); }}
.panel ul {{ margin:0; padding-left:1.2em; font-size:var(--text-sm);
  color:var(--color-text-secondary); }}
.panel.warn {{ border-left-color:var(--color-high); }}
.group {{ margin-bottom:var(--space-12); scroll-margin-top:var(--space-4); }}
.group-head {{ display:flex; align-items:center; gap:var(--space-3);
  border-bottom:2px solid var(--color-border); padding-bottom:var(--space-2);
  margin-bottom:var(--space-2); }}
.group-head h2 {{ font-size:var(--text-xl); margin:0; }}
.group-desc {{ color:var(--color-text-secondary); font-size:var(--text-sm);
  margin:0 0 var(--space-6); }}
.shot-list {{ display:flex; flex-direction:column; gap:var(--space-6); }}
.shot {{ background:var(--color-surface); border:1px solid var(--color-border);
  border-radius:var(--radius-md); padding:var(--space-6); box-shadow:var(--shadow-sm);
  scroll-margin-top:var(--space-4); }}
.shot-head {{ display:flex; align-items:center; gap:var(--space-3); flex-wrap:wrap; }}
.shot-id {{ font-family:var(--font-mono); font-size:var(--text-xs);
  background:var(--color-surface-2); border-radius:var(--radius-sm); padding:2px 8px;
  color:var(--color-text-secondary); }}
.shot-name {{ font-size:var(--text-lg); margin:0; flex:1 1 auto; }}
.shot-note {{ color:var(--color-text-secondary); font-size:var(--text-sm);
  margin:var(--space-2) 0 var(--space-3); }}
.shot-meta {{ display:flex; flex-wrap:wrap; gap:var(--space-2); margin-bottom:var(--space-4); }}
.meta-chip {{ background:var(--color-surface-2); border-radius:var(--radius-full);
  padding:3px 10px; font-size:var(--text-xs); color:var(--color-text-secondary); }}
.shot-frame {{ display:block; border:1px solid var(--color-border);
  border-radius:var(--radius-md); overflow:hidden; background:var(--color-surface-2); }}
.shot-frame img {{ display:block; width:100%; height:auto; }}
.shot-failed {{ padding:var(--space-8); text-align:center; color:var(--color-critical);
  background:var(--color-critical-bg); font-weight:700; }}
.shot-error {{ font-family:var(--font-mono); font-size:var(--text-xs);
  color:var(--color-critical); margin:var(--space-2) 0 0; }}
.badge {{ display:inline-flex; align-items:center; padding:2px 8px;
  border-radius:var(--radius-full); font-size:var(--text-xs); font-weight:600; }}
.badge-critical {{ background:var(--color-critical-bg); color:var(--color-critical); }}
.badge-high {{ background:var(--color-high-bg); color:var(--color-high); }}
.badge-medium {{ background:var(--color-medium-bg); color:#856404; }}
.badge-low {{ background:var(--color-low-bg); color:var(--color-low); }}
.badge-new {{ background:var(--color-primary-light); color:var(--color-primary); }}
footer {{ color:var(--color-text-disabled); font-size:var(--text-xs);
  border-top:1px solid var(--color-border); padding-top:var(--space-4); }}
@media (max-width:900px) {{
  .layout {{ grid-template-columns:1fr; }}
  .sidenav {{ position:static; height:auto; }}
  main {{ padding:var(--space-4); }}
}}
</style>
</head>
<body>
<div class="layout">
<nav class="sidenav">
  <div class="brand">WebSpec2Doc<small>画面カタログ / {stamp}</small></div>
  {"".join(nav_items)}
</nav>
<main>
  <h1>WebSpec2Doc 画面カタログ</h1>
  <p class="lead">稼働中のアプリケーションを実際に起動し、到達可能な画面・タブ・モーダル・UI 状態を
     省略せずキャプチャしたものです。合成画像や手描きのモックは 1 枚も含みません。</p>

  <div class="stat-row">
    <div class="stat"><b>{total}</b><span>掲載画面（状態を含む）</span></div>
    <div class="stat"><b>{ok}</b><span>撮影成功</span></div>
    <div class="stat"><b>{ng}</b><span>撮影失敗</span></div>
    <div class="stat"><b>{len([g for g,_ in GROUP_ORDER if by_group.get(g)])}</b><span>区分</span></div>
  </div>

  <div class="panel">
    <h3>撮影条件</h3>
    <ul>
      <li>対象: このリポジトリの作業ツリー（<code>e2eb61c</code> 時点）を <code>venv/bin/python app.py</code> で起動した実体。</li>
      <li>ブラウザ: Chromium 141.0.7390.37 / ビューポート 1440×900（モバイル区分のみ 390×844）。</li>
      <li>本体アプリ: <code>WEBSPEC2DOC_AUTH_MODE=off</code>（認証オフ運用・ゲスト表示）で <code>127.0.0.1:8765</code>。</li>
      <li>認証画面: <code>WEBSPEC2DOC_AUTH_MODE=required</code> + 空の認証DB で <code>127.0.0.1:8766</code> を別に起動し、
          初期セットアップ→ログイン→テナント選択の実フローを通して撮影。</li>
      <li>表示データ: リポジトリ同梱の <code>docs/demo/sample_output/</code>（同梱デモサイト DemoMart の実解析結果）を
          <code>output/demomart/</code> に置き、製品コードの <code>snapshot_run()</code> で実行回
          <code>20260828-143210</code> を作成。数値・表はすべてその実データ。</li>
      <li>スクリーンショットは元の PNG（1440px 幅）を WebP q82 に変換。リサイズ以外の加工はしていない。</li>
    </ul>
  </div>

  <div class="panel warn">
    <h3>この一覧に入っていないもの（明示）</h3>
    <ul>
      <li><strong>解析対象のデモサイト</strong>（<code>demo/site/</code>・<code>demo/verify_site/</code> の 20 ページ）—
          WebSpec2Doc が解析する側のサンプルサイトであり、本システムの画面ではないため除外。</li>
      <li><strong>GitHub Pages ショーケース</strong>（<code>pages/index.html</code> ほか）— 製品 UI ではなく公開用 LP のため除外。</li>
      <li><strong>ファイル配信エンドポイント</strong>（<code>/download</code>・<code>/download-zip</code>・<code>/open</code>・<code>/preview</code>）—
          HTML 画面ではなくファイルを返す経路。</li>
      <li><strong>リダイレクト専用の旧 URL</strong>（<code>/auth/account</code> → <code>/account</code>、
          <code>/admin/console</code> → <code>/user-management</code>）— 固有の画面を持たない。</li>
      <li><strong>API エンドポイント</strong>（<code>/api/**</code>・<code>/metrics</code> ほか）— 画面ではない。</li>
      <li><strong>実行中・エラー中の動的状態</strong>（クロール進行中の進捗表示、LLM 応答待ち、タイムアウト表示など）—
          外部サイトへの実クロールを伴うため<strong>未撮影</strong>。この一覧では確認していない。</li>
    </ul>
  </div>

  {"".join(cards)}

  <footer>WebSpec2Doc 画面カタログ — 自動生成（{stamp}）。
  再生成手順は <code>docs/screens/README.md</code> を参照。</footer>
</main>
</div>
</body>
</html>
'''
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(doc, encoding="utf-8")
print("wrote", OUT, len(doc), "bytes /", total, "screens")
