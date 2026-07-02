---
name: design-system
description: YukiのAIDDツール群に一貫したビジュアルデザインを適用するスキル。HTMLツール・PWA・Streamlitアプリのデザインを決める際、「デザインどうする」「色は」「レイアウトは」「Material Design」「UIを作る」「コンポーネントを実装する」という言及があれば必ずこのスキルを使うこと。UX Reviewer・QA Lens・PMOエージェント・my-accounting-app等の既存ツールと統一感を保つためにも必ず参照する。
---

# Yuki Design System（MD3 Lightベース）

過去ツール群（UX Reviewer v3〜v5 / QA Lens / my-accounting-app）から抽出した統一デザイン言語。迷ったらここの値をそのまま使う。

## カラーパレット（CSS変数）

```css
:root {
  /* Primary */
  --color-primary:       #1976D2;  /* メインアクション・アクティブ状態 */
  --color-primary-light: #E3F2FD;  /* 選択背景・ホバー */
  --color-primary-dark:  #0D47A1;  /* ホバー時のアクション */

  /* Surface */
  --color-bg:            #F8F9FA;  /* ページ背景 */
  --color-surface:       #FFFFFF;  /* カード・モーダル */
  --color-surface-2:     #F1F3F4;  /* 入れ子カード・サイドナビ背景 */

  /* Border & Divider */
  --color-border:        #E0E0E0;
  --color-divider:       #F0F0F0;

  /* Text */
  --color-text:          #212121;  /* 本文 */
  --color-text-secondary:#616161;  /* 補足・メタ情報 */
  --color-text-disabled: #9E9E9E;

  /* Status（ISTQB severity対応） */
  --color-critical:      #D32F2F;  /* Critical / エラー */
  --color-high:          #F57C00;  /* High / 警告 */
  --color-medium:        #FBC02D;  /* Medium / 注意 */
  --color-low:           #388E3C;  /* Low / 成功 */
  --color-info:          #0288D1;  /* 情報 */

  /* Severity背景（バッジ用）*/
  --color-critical-bg:   #FFEBEE;
  --color-high-bg:       #FFF3E0;
  --color-medium-bg:     #FFFDE7;
  --color-low-bg:        #E8F5E9;
  --color-info-bg:       #E1F5FE;
}
```

## タイポグラフィ

```css
:root {
  --font-main: 'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', sans-serif;
  --font-mono: 'JetBrains Mono', 'Consolas', monospace;

  /* スケール */
  --text-xs:   11px;  /* ラベル・バッジ */
  --text-sm:   13px;  /* メタ情報・補足 */
  --text-base: 14px;  /* 本文（デフォルト） */
  --text-md:   16px;  /* セクション本文 */
  --text-lg:   18px;  /* カードタイトル */
  --text-xl:   22px;  /* ページタイトル */
  --text-2xl:  28px;  /* ヒーロー数値 */

  /* 行間 */
  --leading-tight:  1.4;
  --leading-normal: 1.7;
  --leading-loose:  2.0;
}
```

## スペーシング・形状

```css
:root {
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-6:  24px;
  --space-8:  32px;
  --space-12: 48px;

  --radius-sm: 4px;   /* バッジ・チップ */
  --radius-md: 8px;   /* カード */
  --radius-lg: 12px;  /* モーダル・大カード */
  --radius-xl: 16px;  /* 検索バー */
  --radius-full: 9999px; /* ピル型バッジ */

  --shadow-sm: 0 1px 3px rgba(0,0,0,.08);
  --shadow-md: 0 2px 8px rgba(0,0,0,.12);
  --shadow-lg: 0 4px 16px rgba(0,0,0,.15);
}
```

## レイアウトパターン

### 2ペイン（サイドナビ + メイン）- デスクトップツール既定
```css
.layout-2pane {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
}
.sidenav {
  background: var(--color-surface-2);
  border-right: 1px solid var(--color-border);
  padding: var(--space-4);
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
```

### カードグリッド - ダッシュボード・一覧系
```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--space-4);
}
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-6);
  box-shadow: var(--shadow-sm);
}
```

## コンポーネント

### バッジ（severity / status）
```html
<span class="badge badge-critical">Critical</span>
<span class="badge badge-high">High</span>
<span class="badge badge-medium">Medium</span>
<span class="badge badge-low">Low</span>
<span class="badge badge-new">NEW</span>
```
```css
.badge {
  display: inline-flex; align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs); font-weight: 600;
}
.badge-critical { background: var(--color-critical-bg); color: var(--color-critical); }
.badge-high     { background: var(--color-high-bg);     color: var(--color-high); }
.badge-medium   { background: var(--color-medium-bg);   color: #856404; }
.badge-low      { background: var(--color-low-bg);      color: var(--color-low); }
.badge-new      { background: var(--color-primary-light); color: var(--color-primary); }
```

### スコアカード（ISO 25010用）
```html
<div class="score-card">
  <div class="score-value">82</div>
  <div class="score-label">使用性</div>
  <div class="score-bar"><div class="score-fill" style="width:82%"></div></div>
</div>
```

## Fold5対応レスポンシブ

```css
/* カバー画面: ~360px */
@media (max-width: 360px) {
  .layout-2pane { grid-template-columns: 1fr; }
  .sidenav { display: none; }  /* ハンバーガーで開閉 */
  .card-grid { grid-template-columns: 1fr; }
}
/* メイン画面: 768px〜 */
@media (min-width: 768px) {
  .card-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
}
/* タッチターゲット */
button, a, [role="button"] { min-height: 44px; min-width: 44px; }
```

## Googleフォント読み込み（HTMLのhead内）
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
```
