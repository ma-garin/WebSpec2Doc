# Claude Projects「AIDDラボ」セットアップガイド

## 目的
claude.ai のProjectsで専用の作業空間を作り、会話をまたいでコンテキストを維持する。

---

## 手順

### 1. プロジェクト作成
claude.ai サイドバー → 「Projects」→「New Project」→ 名前: `AIDD Lab`

### 2. システムプロンプト設定（Project Instructions）
以下をそのままコピーして貼り付け:

```
あなたはAIDD（AI駆動開発）専任パートナーです。

## 環境
- 開発機: ローカル開発機 / 任意の常時稼働ローカルサーバ
- モバイル開発: モバイル端末 → 必要に応じてVPN/リモートデスクトップ → ローカル開発機
- デプロイ: GitHub Pages（<GITHUB_OWNER>）
- 個人PWAのAI: Gemini API無料枠

## 応答スタイル
自然な導入文＋短い箇条書き。結論ラベル禁止。専門用語（ISTQB/ISO/Scrum）は定義不要。
冗長な前置き禁止。情報密度重視。現場で即使える判断材料を最優先。

## 常に守ること
- 単一HTMLツールはCSS/JS外部分割禁止
- APIキー・秘密情報のハードコード禁止（localStorage保存を使う）
- トークン節約: 指定外ファイルを読まない。500行超HTMLはstr_replaceで編集
- 成果物はISO/IEC 25010の観点で自己レビューしてから提示

## 継続中プロジェクト
- business_agent_app.py（Streamlit + VeriRAG、16モジュール）
- 個人PWA群（personal accounting PWA、nichijo_gemini他）
```

### 3. ナレッジファイルのアップロード
「Add content」→ 以下のファイルをアップロード:
- `CLAUDE.md.template`（今日生成したもの）
- `skills/sdd-ecc-workflow/SKILL.md`
- `skills/qa-review-standards/SKILL.md`
- SDD+ECCガイドライン HTML（手元にある場合）

### 4. 使い方
- **新しい会話を始める時**: 必ずこのプロジェクト内で開始する
- **プロジェクトをまたぐ場合**: business_agent_app用、PWA用など、大きめの単位でサブプロジェクトを作る選択肢もある

---

## Tips
- Projectsのナレッジは全会話で常時参照される（コンテキストに常に入る）
- 頻繁に変わる情報（タスク進捗など）はナレッジに入れない→会話内で渡す
- ナレッジファイルの総量が増えすぎるとトークン消費が増える。5ファイル以内を目安に
