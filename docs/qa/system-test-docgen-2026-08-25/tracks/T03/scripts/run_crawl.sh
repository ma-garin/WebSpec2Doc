#!/usr/bin/env bash
# T03 crawl driver: POST /run を text stream で受け、証跡ファイルに保存する。
# 使い方: run_crawl.sh <out_file> <curl -m 秒> <form arg...>
# 例(selected): run_crawl.sh ev/c001.txt 120 -F 'urls=http://127.0.0.1:9103/,http://127.0.0.1:9103/about' -F 'parallelism=1'
# 例(auto):     run_crawl.sh ev/c010.txt 120 -F 'urls=http://127.0.0.1:9103/' -F 'crawl_mode=auto' -F 'depth=2' -F 'max_pages=10'
set -u
OUT="$1"; TMO="$2"; shift 2
BASE="http://127.0.0.1:8765"
curl -sN -m "$TMO" -X POST "$BASE/run" "$@" | tee "$OUT"
echo "--- exit=$? ---" | tee -a "$OUT"
