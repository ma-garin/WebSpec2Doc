# 自 UI の機械 UX 監査（P0-2・ドッグフーディング）

- 実施日: 2026-07-29 ／ 方法: **製品自身の `--ux-review`**（axe-core による WCAG 検査 ＋ Nielsen 10 原則のルールベース評価）を自 UI（`http://127.0.0.1:8765/`）へ適用
- コマンド: `WEBSPEC2DOC_ALLOW_LOCAL=1 venv/bin/python src/main.py --url http://127.0.0.1:8765/ --depth 1 --max-pages 10 --ux-review --output output/self-ux-audit`
- 対象: P001 ダッシュボード（SPA ルート）／ P002 システム選択

> 自動検出可能な範囲の観測に限る。キーボード操作・スクリーンリーダー・代替テキストの妥当性など、
> 人の判断を要する検査の代替にはならない（`ux_review.json` の meta と同じ but 明示）。

---

## 1. 最大の収穫: 監査が製品自身の欠陥で 3 件止まった

**自 UI を監査しようとして、製品側の不具合で監査自体が失敗した。**いずれも利用者のサイトを解析するときにも同じ症状が出る実害のあるもので、ドッグフーディングでなければ発見できなかった。

### D-1 ログイン壁の誤検知（重大・**クロールが 0 件で終わる**）

- 症状: 自 UI をクロールすると `ログインウォールによりスキップしました` となり **1 ページも取得できず終了**
- 原因: `detect_login_wall` が「`<input type=password>` が 1 つでもあれば」他の根拠なしにログイン壁と断定（`src/analyzer/login_wall.py`）。自 UI には API キー・Slack Webhook・運用エンドポイントを伏せるための password 欄が非表示 SPA ビュー内に 4 つある
- **利用者への影響**: API キーやトークンを `type="password"` で伏せる設定画面を持つ対象サイトは、**解析結果が 0 件になる**
- 対処: 判定を「**表示されている**パスワード欄が、**同一フォーム内の ID／メール欄と対**で存在する」に精密化（`src/crawler/link_extractor.py` の `has_password_field`）
- 検証: 自 UI → `login_required=False`（誤検知解消）／ 検証用ログインサイト（302 → `/login`）→ `login_required=True`, reasons `['redirect_to_login', 'password_field']`（真陽性は維持）

### D-2 UX 所見の誤検知（`<label>` 入れ子を認識しない）

- 症状: 「入力欄に可視ラベル・aria-label のいずれもない」（Nielsen N6・high）が **5 件**報告されたが、対象は `<label class="checkbox-chip"><input id="crawl-mode-selected"> 選択したURLのみ</label>` のように**ラベルで包まれた正しいマークアップ**
- 原因: `has_visible_label` が `label[for=id]` ・ `aria-label` ・ `aria-labelledby` しか見ておらず、入れ子 `<label>` を見落としていた
- **利用者への影響**: 対象サイトに**存在しないアクセシビリティ不備を報告する**（偽陽性で信頼性を損なう）
- 対処: `field.closest('label')` にテキストがあれば可視ラベルありとみなす
- 検証: N6 high **5 件 → 1 件**（残る 1 件は `#vp-item-id` で、実際にラベルが無い真の指摘）

### D-3 API エンドポイントを「画面」として解析

- 症状: `http://127.0.0.1:8765/api/admin/backup-guide`（`content-type: text/markdown`）が画面 P003 として一覧に載り、axe 違反 5 件（`document-title` / `html-has-lang` / `landmark-one-main` / `page-has-heading-one` / `region`）を計上していた
- **利用者への影響**: 画面数が水増しされ、仕様書・テスト設計・テスト条件に**画面でないものが混入**する
- 対処: レスポンスの `content-type` に `html` を含まない場合は画面一覧から除外（`_is_html_response`）。content-type が取得できない場合は誤除外を避けるため HTML とみなす（fail open）
- 検証: 自 UI の discover が **3 件 → 2 件**（API が除外され、`/` と `/systems` のみ）

---

## 2. 監査結果（修正後）

| 指標 | 監査前 | 修正後 |
|---|---|---|
| axe **critical** | 0 | **0** |
| axe serious | 11 | 9（すべて `color-contrast`） |
| axe moderate | 5 | 3（すべて除外済み API 由来だったもの→0。残りは P003 消滅により消失） |
| UX 所見 high（N6） | 5 | **1** |

### P001 ダッシュボード（実 UI）

| 重大度 | ルール | 件数 | 処置 |
|---|---|---|---|
| serious | `color-contrast` | 9 | **保留（承認待ち）** — §3 参照 |
| moderate | `landmark-no-duplicate-banner` | 1 → **0** | 修正済み（§2.1） |
| moderate | `landmark-unique` | 1 → **0** | 修正済み（§2.1） |
| high (N6) | 可視ラベルなし | 5 → **1** | D-2 で 4 件が偽陽性と判明。残 1 件 `#vp-item-id` は真の指摘（§3） |
| medium (N5) | placeholder のみのラベル | 1 | **保留（承認待ち）** — §3 参照 |

### P002 システム選択

違反 0 件。

### 2.1 banner ランドマークの重複（修正済み）

- 原因は 2 つあった。
  1. `autorun-modal-head` / `autorun-chat-head` / `vp-commandbar` / `vp-editor-head` の 4 つがコンポーネント見出しなのに `<header>` で書かれていた。セクショニング要素の外にある `<header>` は banner ランドマークになる → `<div>` へ変更（**CSS はクラスセレクタのみを使用しており見た目は不変**）
  2. 同梱ライブラリ **driver.js**（操作ツアー）がポップオーバーのタイトルを `<header>` で描画していた → `onPopoverRender` フックで `role="presentation"` を付与（見た目は不変・ツアー表示中のみ発生していた）
- 検証: 実行時 DOM の実質 banner ランドマーク数 **2 → 1**

---

## 3. 未処置（**ユーザー承認待ち**・見た目が変わるため先回りしない）

プラン §2-1「UI 変更は実装前に HTML デザイン案 → 承認必須」に従い、以下は**着手していない**。

| # | 指摘 | 対象 | 必要な変更 |
|---|---|---|---|
| A-1 | `color-contrast` × 9 | `.app-brand-text > span` / `.sys-switcher-label` / `.sys-switcher-swap` / `#topbar-breadcrumb > span:nth-child(3)` / `.onboarding-eyebrow` / `.stat-card-sub` × 4 | 淡色テキストのコントラスト比を WCAG AA（4.5:1）まで引き上げる。**`--text-muted` 系トークンの変更＝全画面の見た目に影響** |
| A-2 | N6 high × 1 | `#vp-item-id`（観点管理） | 可視ラベルまたは `aria-label` の付与。ラベルを足すとレイアウトが変わる |
| A-3 | N5 medium × 1 | placeholder のみをラベルにしている入力欄 | 可視ラベルの追加。同上 |

**A-1 が最も影響が大きい。** トークンを変えると全画面の淡色文字が濃くなるため、承認前の実装は禁止。

---

## 4. 再現手順

```bash
# 1. アプリを起動（ローカル解析を許可）
WEBSPEC2DOC_ALLOW_LOCAL=1 venv/bin/python app.py --no-browser &

# 2. 製品自身の UX レビューを自 UI に適用
WEBSPEC2DOC_ALLOW_LOCAL=1 venv/bin/python src/main.py \
  --url http://127.0.0.1:8765/ --depth 1 --max-pages 10 \
  --ux-review --output output/self-ux-audit

# 3. 集計
venv/bin/python - <<'PY'
import json, collections
from pathlib import Path
d = json.loads(Path("output/self-ux-audit/127.0.0.1:8765/ux_review.json").read_text(encoding="utf-8"))
tot, ux = collections.Counter(), collections.Counter()
for s in d["screens"]:
    for x in (s.get("axe_violations") or []): tot[(x["impact"], x["rule_id"])] += 1
    for f in (s.get("ux_findings") or []): ux[(f["severity"], f["principle"])] += 1
print(dict(tot)); print(dict(ux))
PY
```

## 5. 受入判定

プラン P0-2 の受入は「監査結果ファイル ＋ **Critical 0 件**までの修正 PR」。

- **axe critical: 0 件 → 達成**
- 併せて、監査を阻んでいた製品欠陥 3 件（D-1〜D-3）と、見た目を変えないランドマーク修正を実施
- serious（`color-contrast` × 9）は**見た目が変わるため承認待ち**として §3 に分離

## 6. 弱点

1. 監査対象は `depth=1` で到達した 2 画面のみ。**AutoRun・テストケース・観点管理・設定などの主要ビューは SPA 内のタブ切替でしか到達できず、この方法では監査できていない**（クロールは URL 単位のため）。それらの監査には `/auto-run` 等の直接 URL を個別に指定した追加実行が要る
2. `color-contrast` の 9 件は axe の自動判定で、実際の可読性は環境（ディスプレイ・ダークモード）に依存する。**AA 未達であることは事実だが、利用者が読みにくいと感じているかは未確認**
3. D-1 の修正は「表示中のパスワード欄＋同一フォーム内の ID 欄」を条件にしたため、**ID 欄を持たないパスワードのみのログイン画面（2 段階認証の 2 画面目など）は検出できない**。リダイレクトや 401/403 があれば従来どおり検出できるが、それらが無い場合は取り逃す
