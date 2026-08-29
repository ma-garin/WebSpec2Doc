#!/bin/bash
# T01 画面発見（discover）システムテスト実行スクリプト
# 使い方: ./t01_cases.sh part1 | part2 | all
# 前提: 本体 8765・モック 9101 稼働（02-test-environment.md）。証跡は ../evidence/ に出力。
set -u
BASE="http://127.0.0.1:8765"
MOCK="http://127.0.0.1:9101"
DIR="$(cd "$(dirname "$0")" && pwd)"
EV="$DIR/../evidence"
mkdir -p "$EV"
SUMMARY="$EV/summary.txt"

sse() { # sse <実行ID> [curl args...] — SSE 版
  local name="$1"; shift
  echo "[$(date +%H:%M:%S)] $name start" >>"$SUMMARY"
  curl -sN -m 120 -X POST "$BASE/api/discover-stream" "$@" \
    -o "$EV/$name.log" -w "$name HTTP=%{http_code} TIME=%{time_total}s SIZE=%{size_download}\n" >>"$SUMMARY"
}
sync_() { # sync_ <実行ID> [curl args...] — 同期版
  local name="$1"; shift
  echo "[$(date +%H:%M:%S)] $name start" >>"$SUMMARY"
  curl -s -m 120 -X POST "$BASE/api/discover" "$@" \
    -o "$EV/$name.json" -w "$name HTTP=%{http_code} TIME=%{time_total}s SIZE=%{size_download}\n" >>"$SUMMARY"
}

part1() {
  sse   C001  --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=5 -d parallelism=4
  sse   C002  --data-urlencode "url=$MOCK/" -d depth=2 -d max_pages=30 -d parallelism=4
  sync_ C003  --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=5
  sync_ C004a --data-urlencode "url=$MOCK/" -d depth=0 -d max_pages=40
  sync_ C004b --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=40
  sync_ C004c --data-urlencode "url=$MOCK/deep/1" -d depth=11 -d max_pages=20
  sync_ C004d --data-urlencode "url=$MOCK/deep/1" -d depth=10 -d max_pages=20
  sync_ C005a --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=0
  sync_ C005b --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=1
  sync_ C005c --data-urlencode "url=$MOCK/about" -d depth=1 -d max_pages=501
  sync_ C005d --data-urlencode "url=$MOCK/about" -d depth=1 -d max_pages=500
}

part2() {
  sse   C006a --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=10 -d parallelism=0
  sse   C006b --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=10 -d parallelism=9
  sync_ C007  -d "url="
  sse   C007s -d "url="
  sync_ C008  --data-urlencode "url=not-a-url" -d depth=1 -d max_pages=5
  sse   C008s --data-urlencode "url=not-a-url" -d depth=1 -d max_pages=5
  sync_ C009  --data-urlencode "url=ftp://x" -d depth=1 -d max_pages=5
  sync_ C010  --data-urlencode "url=http://" -d depth=1 -d max_pages=5
  sse   C011  --data-urlencode "url=$MOCK/" -d depth=1 -d max_pages=40 -d parallelism=4
  sse   C012  --data-urlencode "url=$MOCK/dashboard" -d depth=1 -d max_pages=5 -d parallelism=2
  sse   C013  --data-urlencode "url=$MOCK/private/secret" -d depth=1 -d max_pages=5 -d parallelism=2
  sse   C015a --data-urlencode "url=$MOCK/slow" -d depth=1 -d max_pages=5 -d parallelism=2
  sse   C015b --data-urlencode "url=$MOCK/huge" -d depth=1 -d max_pages=50 -d parallelism=8
  sync_ C016  --data-urlencode "url=$MOCK/unicode/日本語ページ" -d depth=1 -d max_pages=5
  sync_ C017  --data-urlencode "url=$MOCK/products/1?ref=qa&x=1" -d depth=1 -d max_pages=5
  sync_ C018  --data-urlencode "url=$MOCK/about#team" -d depth=1 -d max_pages=5
}

case "${1:-all}" in
  part1) part1 ;;
  part2) part2 ;;
  all) part1; part2 ;;
  *) echo "usage: $0 part1|part2|all" >&2; exit 2 ;;
esac
echo "[$(date +%H:%M:%S)] done" >>"$SUMMARY"
