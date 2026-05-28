#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

if [[ $# -eq 0 ]]; then
  echo "使い方: ./run.sh <URL> [オプション]"
  echo ""
  echo "例:"
  echo "  ./run.sh https://example.com"
  echo "  ./run.sh https://example.com --depth 2 --max-pages 20"
  echo "  ./run.sh https://example.com --format md,html,excel"
  exit 1
fi

source venv/bin/activate
python src/main.py --format md,html "$@"
