#!/bin/bash
# session-summary.sh
# セッション終了時: コミット忘れ防止・implement.md更新リマインド

UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l)

echo "=== [AIDD Hook: session-end] ==="

if [ "$UNCOMMITTED" -gt 0 ]; then
  echo "⚠ 未コミットファイル: ${UNCOMMITTED}件"
  git status --short 2>/dev/null | head -10
  echo "→ git add / git commit を忘れずに"
fi

# implement.mdの最終更新確認
if [ -f "implement.md" ]; then
  LAST=$(date -r implement.md "+%Y-%m-%d" 2>/dev/null || stat -c "%y" implement.md 2>/dev/null | cut -d' ' -f1)
  TODAY=$(date "+%Y-%m-%d")
  if [ "$LAST" != "$TODAY" ]; then
    echo "📝 implement.md が今日未更新 → 作業内容を記録してください"
  fi
fi

echo "================================="
exit 0
