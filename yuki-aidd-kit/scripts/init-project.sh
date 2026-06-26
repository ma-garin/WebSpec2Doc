#!/bin/bash
# init-project.sh — 新規AIDDプロジェクトのスキャフォールド
# 使い方: ./init-project.sh <project-name> [pwa|html|streamlit]

set -e
NAME="${1:-}"
TYPE="${2:-pwa}"
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "$NAME" ]; then
  echo "使い方: ./init-project.sh <project-name> [pwa|html|streamlit]"
  exit 1
fi

mkdir -p "$NAME"
cd "$NAME"
git init -q 2>/dev/null || true

# --- .gitignore（秘密情報の混入防止）---
cat > .gitignore << 'EOF'
# 秘密情報
.env
.env.*
*.key
*.pem
config/secrets.*
# データ・ログ
*.log
*.csv
data/
# OS / エディタ
.DS_Store
.vscode/
__pycache__/
*.pyc
EOF

# --- プロジェクト用 CLAUDE.md ---
cat > CLAUDE.md << EOF
# CLAUDE.md（プロジェクト: $NAME）

## このプロジェクトの概要
<!-- 一文で目的を書く -->

## 種別
$TYPE

## 対象ファイル / 対象外ファイル
- 対象:
- 対象外（読まない）:

## 使用技術・制約
<!-- nfr-standardsスキルの $TYPE 用NFRを参照 -->

## 現在のタスク
CURRENT_STATE.md と tasks.md を参照
EOF

# --- CURRENT_STATE.md ---
cp "$KIT_DIR/templates/CURRENT_STATE.md" ./CURRENT_STATE.md 2>/dev/null || true
sed -i.bak "s|<!-- 例: business_agent_app.*-->|$NAME|" CURRENT_STATE.md 2>/dev/null && rm -f CURRENT_STATE.md.bak

# --- 種別別スキャフォールド ---
case "$TYPE" in
  pwa)
    mkdir -p docs
    cat > docs/manifest.json << EOF
{
  "name": "$NAME",
  "short_name": "$NAME",
  "start_url": "./index.html",
  "display": "standalone",
  "background_color": "#F8F9FA",
  "theme_color": "#1976D2",
  "icons": []
}
EOF
    echo "<!-- index.html: /new-pwa コマンドまたはdesign-systemスキルで生成 -->" > docs/index.html
    echo "✅ PWAスキャフォールド作成: docs/ に配置（GitHub Pages = docs/ を公開）"
    ;;
  html)
    echo "<!-- $NAME.html: single-html-tool + design-system スキルで生成 -->" > "$NAME.html"
    echo "✅ 単一HTMLツール スキャフォールド作成"
    ;;
  streamlit)
    cat > requirements.txt << EOF
streamlit
EOF
    echo "# $NAME — business_agent系。streamlit-rag-appスキル参照" > app.py
    echo "✅ Streamlitスキャフォールド作成"
    ;;
esac

# --- SDDファイルの空テンプレート ---
echo "# $NAME 仕様（sdd-ecc-workflowスキルのtemplates.md参照）" > spec.md
echo "# 実装計画" > plan.md
echo "# タスク" > tasks.md

echo ""
echo "=== $NAME 作成完了 ==="
echo "次の指示例:"
echo "  /sdd-start $NAME - [一文で目的]"
