#!/bin/sh
# $1: カンマ区切り URL, $2: 出力先ストリームファイル, $3: login_urls（省略可）
curl -s -N --max-time 600 -X POST http://127.0.0.1:8765/run \
  --data-urlencode "urls=$1" \
  --data-urlencode "login_urls=${3:-}" \
  --data-urlencode "depth=1" \
  --data-urlencode "max_pages=50" \
  --data-urlencode "format=md,html,json" \
  --data-urlencode "crawl_mode=selected" \
  --data-urlencode "parallelism=2" > "$2" 2>&1
echo "exit=$?"; tail -4 "$2"
