#!/bin/bash
# install.sh — AIDD Kitを ~/.claude へ導入
set -e
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "=== AIDD Kit インストール ==="
mkdir -p "$CLAUDE_DIR/skills" "$CLAUDE_DIR/commands" "$CLAUDE_DIR/hooks"

# グローバルCLAUDE.md（既存があればバックアップ）
if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
  cp "$CLAUDE_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md.bak"
  echo "⚠ 既存のCLAUDE.mdを CLAUDE.md.bak に退避（手動マージ推奨）"
fi
cp "$KIT_DIR/CLAUDE.md.template" "$CLAUDE_DIR/CLAUDE.md"

# スキル
cp -r "$KIT_DIR/skills/"* "$CLAUDE_DIR/skills/"
echo "✅ スキル: $(ls "$KIT_DIR/skills" | wc -l)個"

# コマンド
cp "$KIT_DIR/claude-code/commands/"*.md "$CLAUDE_DIR/commands/"
echo "✅ コマンド: $(ls "$KIT_DIR/claude-code/commands" | wc -l)個"

# Hooks
cp "$KIT_DIR/claude-code/hooks/"*.sh "$CLAUDE_DIR/hooks/"
chmod +x "$CLAUDE_DIR/hooks/"*.sh
if [ -f "$CLAUDE_DIR/settings.json" ]; then
  echo "⚠ settings.json が既存。hooks設定を手動でマージしてください（参照: claude-code/hooks/settings.json）"
else
  cp "$KIT_DIR/claude-code/hooks/settings.json" "$CLAUDE_DIR/settings.json"
fi
echo "✅ Hooks: 3個"

# Codex用
echo ""
echo "Codexを使う場合: AGENTS.md.template を ~/.codex/AGENTS.md にコピーしてください"
echo ""
echo "=== 完了 ==="
echo "確認: ./scripts/verify.sh"
