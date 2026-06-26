#!/bin/bash
# post-write-html.sh
# HTMLファイル保存後: サイズ確認・str_replace推奨の通知

FILE="$1"
if [ -z "$FILE" ] || [[ "$FILE" != *.html ]]; then exit 0; fi

SIZE=$(wc -c < "$FILE" 2>/dev/null || echo 0)
LINES=$(wc -l < "$FILE" 2>/dev/null || echo 0)
SIZE_KB=$((SIZE / 1024))

echo "=== [AIDD Hook: post-write HTML] ==="
echo "📄 $FILE — ${LINES}行 / ${SIZE_KB}KB"

# 500行超えたらstr_replace推奨
if [ "$LINES" -gt 500 ]; then
  echo "💡 500行超: 次回編集はstr_replaceで部分更新を推奨（トークン節約）"
fi

# localStorageスキーマの存在確認
if ! grep -q "localStorage" "$FILE" 2>/dev/null; then
  if grep -q "function\|class " "$FILE" 2>/dev/null; then
    echo "💡 データ永続化: localStorageが未使用です。必要であれば追加を検討"
  fi
fi

echo "====================================="
exit 0
