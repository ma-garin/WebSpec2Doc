# Yuki AIDD Kit

過去のAIDD実績から抽出した、Claude Code用パーソナライズドキット。

## 構成

```
yuki-aidd-kit/
├── CLAUDE.md.template          # グローバル設定（環境・トークン規律・QA観点）
├── claude-projects-setup.md    # Claude Projects「AIDDラボ」セットアップ手順
├── skills/
│   ├── single-html-tool/       # 単一HTMLツール開発（MD3・localStorage・JSON強制）
│   ├── sdd-ecc-workflow/       # SDD 10ステップ + ECC + cc-sdd（templatesあり）
│   ├── qa-review-standards/    # ISO 25010・ISTQB severity・Whittakerツアー
│   ├── personal-pwa/           # GitHub Pages PWA・Gemini無料枠・Fold5対応
│   └── streamlit-rag-app/      # PMOエージェント系（VeriRAG・16モジュール）
└── claude-code/
    ├── hooks/
    │   ├── settings.json       # Claude Code hookの設定ファイル
    │   ├── pre-write-check.sh  # 書き込み前: 秘密情報・外部分割を警告
    │   ├── post-write-html.sh  # HTML保存後: 行数・localStorage確認
    │   └── session-summary.sh  # セッション終了: コミット忘れ・implement.md確認
    └── commands/
        ├── new-pwa.md          # /new-pwa   — 新規PWA立ち上げ
        ├── qa-review.md        # /qa-review — ISO/ISTQB準拠レビュー実行
        ├── sdd-start.md        # /sdd-start — SDD 10ステップ起動
        └── token-check.md      # /token-check — トークン使用量確認と最適化
```

## 導入手順

```bash
# 1. グローバル設定
cp CLAUDE.md.template ~/.claude/CLAUDE.md

# 2. スキル（全プロジェクト共通）
cp -r skills/* ~/.claude/skills/

# 3. Hooks（hookスクリプトに実行権限を付与）
cp claude-code/hooks/settings.json ~/.claude/settings.json
cp claude-code/hooks/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh

# 4. スラッシュコマンド（全プロジェクト共通）
cp claude-code/commands/* ~/.claude/commands/
```

## Claude Projects セットアップ
`claude-projects-setup.md` を参照してclaud.ai上に「AIDDラボ」プロジェクトを作成する。

## 推奨MCP
- **Exa**（Web Search + Code Docs Search）: 技術ドキュメント・OSSコード検索用
- その他は現状不要（GitHub MCPはレジストリ未登録）
