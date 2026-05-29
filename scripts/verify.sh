#!/bin/zsh
# M0 検証レシピ: 変更後の回帰を一括チェック。
# 使い方: ./scripts/verify.sh
set -e
cd "$(dirname "$0")/.."
source venv/bin/activate

echo "== 1. py_compile =="
python -m py_compile app.py $(find src -name '*.py' -not -path '*__pycache__*')
echo "OK"

echo "== 2. pytest =="
python -m pytest tests/ -q

echo "== 3. スモークパイプライン (iana, --compare x2) =="
python src/main.py --url https://www.iana.org --depth 1 --max-pages 3 --format md,html --compare >/dev/null 2>&1
python src/main.py --url https://www.iana.org --depth 1 --max-pages 3 --format md,html --compare >/dev/null 2>&1
D=output/www.iana.org
for f in screens.md forms.md transition.mmd report.html diff_report.html; do
  [ -f "$D/$f" ] && echo "  $f OK" || { echo "  $f 欠落"; exit 1; }
done

echo ""
echo "ALL GREEN — 回帰なし"
