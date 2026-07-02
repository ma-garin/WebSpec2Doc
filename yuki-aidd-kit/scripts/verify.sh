#!/bin/bash
# verify.sh — インストール確認
CLAUDE_DIR="$HOME/.claude"
OK=0; NG=0

check() {
  if [ -e "$2" ]; then echo "  ✅ $1"; OK=$((OK+1)); else echo "  ❌ $1（未配置: $2）"; NG=$((NG+1)); fi
}

echo "=== AIDD Kit インストール確認 ==="
echo "[グローバル設定]"
check "CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
check "settings.json" "$CLAUDE_DIR/settings.json"

echo "[スキル]"
for s in single-html-tool sdd-ecc-workflow qa-review-standards personal-pwa streamlit-rag-app code-doc-search design-system nfr-standards done-gate test-automation agent-eval retro; do
  check "$s" "$CLAUDE_DIR/skills/$s/SKILL.md"
done

echo "[コマンド]"
for c in new-pwa qa-review sdd-start token-check doc-search retro eval; do
  check "/$c" "$CLAUDE_DIR/commands/$c.md"
done

echo "[Hooks]"
for h in pre-write-check post-write-html session-summary; do
  check "$h.sh" "$CLAUDE_DIR/hooks/$h.sh"
done

echo ""
echo "結果: OK=$OK / NG=$NG"
[ "$NG" -eq 0 ] && echo "✅ 全て正常" || echo "⚠ 未配置あり。install.shを再実行してください"
