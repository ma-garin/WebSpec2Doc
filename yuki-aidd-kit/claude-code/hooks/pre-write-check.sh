#!/bin/bash
# pre-write-check.sh
# 書き込み前にスコープ違反・秘密情報混入を検出

FILE="$1"
if [ -z "$FILE" ]; then exit 0; fi

ERRORS=()

# APIキー・秘密情報パターン検出（ファイル名ベース）
if [[ "$FILE" =~ \.(env|pem|key|secret)$ ]]; then
  ERRORS+=("⚠ 秘密情報ファイルへの書き込み: $FILE")
fi

# 単一HTMLツールへの外部ファイル分割検出
if [[ "$FILE" =~ \.css$|\.js$ ]]; then
  PARENT=$(dirname "$FILE")
  if ls "$PARENT"/*.html &>/dev/null 2>&1; then
    ERRORS+=("⚠ 単一HTMLツール規約違反: CSS/JSの外部分割を検討しています。意図的ですか？ ($FILE)")
  fi
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
  echo "=== [AIDD Hook: pre-write] ==="
  for e in "${ERRORS[@]}"; do echo "$e"; done
  echo "=============================="
fi

exit 0  # 警告のみ、ブロックしない
