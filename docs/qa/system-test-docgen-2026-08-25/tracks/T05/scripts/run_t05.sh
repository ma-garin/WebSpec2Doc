#!/usr/bin/env bash
# T05 参考資料アップロード・doc_fusion システムテスト実行スクリプト（evidence-only 再現用）
# 前提: 本体8765稼働・モック9105稼働・output/127.0.0.1:9105 を事前クロール済み。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
FX="$HERE/fixtures"
EV="$(cd "$HERE/.." && pwd)/evidence"
B=http://127.0.0.1:8765; D=127.0.0.1:9105
run(){ curl -s -w "\n[HTTP %{http_code}]\n" "$@"; }
# 正常系・形式系・legacy・unsupported → normal_and_format.log
# サイズ境界 → size_boundary.log
# パストラバーサル（Path().name + allowlist の効き。保存先を find で客観判定）→ path_traversal.log
# 不正domain・missing_file → domain_and_missing.log
# doc-fusion（候補ファイル無し = candidates_file_missing_or_corrupt 相当 404）→ doc_fusion.log
# 詳細コマンドは execution-log.md 各ケース欄を参照（本ファイルは再現の入口）。
echo "See execution-log.md for the full command matrix; fixtures live in $FX."
