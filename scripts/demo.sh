#!/usr/bin/env bash
# =============================================================================
# WebSpec2Doc 実機デモ ワンコマンド起動
#
#   make demo   または   bash scripts/demo.sh
#
# 同梱デモサイト（DemoMart, ポート8766）と WebSpec2Doc 本体（ポート8765）を
# 同時起動する。本体の URL 欄に http://127.0.0.1:8766/ を入力すればデモ開始。
# OpenAI API キーは不要（ルールベース生成のみで完走する）。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/venv/bin/python"
if [ ! -f "${PYTHON}" ]; then
  PYTHON="$(command -v python3)"
fi

DEMO_SITE_PORT="${DEMO_SITE_PORT:-8766}"

# ローカルアドレスのクロールを許可（同梱デモサイトを解析するため）
export WEBSPEC2DOC_ALLOW_LOCAL=1

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  WebSpec2Doc 実機デモ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

"${PYTHON}" "${ROOT}/demo/demo_site.py" --port "${DEMO_SITE_PORT}" &
DEMO_SITE_PID=$!
trap 'kill "${DEMO_SITE_PID}" 2>/dev/null || true' EXIT

# デモサイトの起動を待つ
for _ in $(seq 1 20); do
  if curl -s -o /dev/null "http://127.0.0.1:${DEMO_SITE_PORT}/"; then
    break
  fi
  sleep 0.5
done

echo ""
echo "  デモ対象サイト : http://127.0.0.1:${DEMO_SITE_PORT}/"
echo "  WebSpec2Doc    : http://127.0.0.1:8765/"
echo ""
echo "  → 本体の URL 欄に http://127.0.0.1:${DEMO_SITE_PORT}/ を入力してください"
echo "  → 台本: docs/demo/DEMO_SCRIPT.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exec_app() {
  "${PYTHON}" "${ROOT}/app.py"
}
exec_app
