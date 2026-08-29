#!/bin/bash
# T04-C001/C002: 9104 の 4 URL を selected モードでクロールし、ストリームを証跡保存する
OUT=docs/qa/system-test-docgen-2026-08-25/tracks/T04/evidence
date +%H:%M:%S > "$OUT/${1:-c001}_time.txt"
curl -N -s --max-time 420 -X POST http://127.0.0.1:8765/run \
  --data-urlencode "urls=http://127.0.0.1:9104/,http://127.0.0.1:9104/products,http://127.0.0.1:9104/contact,http://127.0.0.1:9104/dashboard" \
  --data-urlencode "depth=1" --data-urlencode "max_pages=10" \
  --data-urlencode "format=md,html,json" --data-urlencode "crawl_mode=selected" \
  --data-urlencode "parallelism=2" > "$OUT/${1:-c001}_run_stream.txt"
date +%H:%M:%S >> "$OUT/${1:-c001}_time.txt"
grep -E "RUN_ID:|REPORT_PATH:|SUMMARY:" "$OUT/${1:-c001}_run_stream.txt" | head -5
