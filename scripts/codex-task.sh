#!/usr/bin/env bash
# Codex ハンドオフ・ラッパー — 決定的なタスク委任ループ。
#
#   ./scripts/codex-task.sh <task.md>
#
# 1) タスク指示書を codex exec に渡す (sandbox=workspace-write / git 操作不可)
# 2) Codex 終了直後に verify.sh を自動実行
# 3) pass/fail を表示。Codex は commit しない — Claude が diff レビュー後に commit する。
#
# 過去の Codex 失敗 (スタブ捏造 / 規約無視 / タスク迷子) は
# AGENTS.md (規約) + verify.sh (機械ゲート) + このラッパー (検証強制) で防ぐ。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }
bold()  { printf '\033[1m%s\033[0m\n' "$1"; }

TASK_FILE="${1:-}"
[ -n "$TASK_FILE" ] || { red "usage: $0 <task.md>"; exit 2; }
[ -f "$TASK_FILE" ] || { red "タスク指示書が見つからない: $TASK_FILE"; exit 2; }

command -v codex >/dev/null 2>&1 || { red "codex CLI が無い"; exit 2; }

LOG_DIR="$REPO_ROOT/.codex-runs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LAST_MSG="$LOG_DIR/$STAMP.last.md"

bold "==> Codex にタスクを委任: $TASK_FILE"
echo "    sandbox=workspace-write / model=config default / cwd=$REPO_ROOT"
echo ""

# AGENTS.md は codex が自動読込。タスク指示書を prompt として渡す。
# git 操作はタスク指示書側で禁止 + AGENTS.md で禁止しているため sandbox は workspace-write で十分。
set +e
codex exec \
  --cd "$REPO_ROOT" \
  --sandbox workspace-write \
  --output-last-message "$LAST_MSG" \
  - < "$TASK_FILE"
CODEX_EXIT=$?
set -e

echo ""
if [ "$CODEX_EXIT" -ne 0 ]; then
  red "==> Codex が非ゼロ終了 (exit=$CODEX_EXIT)。検証はスキップ。"
  echo "    最終メッセージ: $LAST_MSG"
  exit "$CODEX_EXIT"
fi

bold "==> Codex 完了。検証ゲートを実行..."
echo ""

set +e
"$REPO_ROOT/scripts/verify.sh"
VERIFY_EXIT=$?
set -e

echo ""
if [ "$VERIFY_EXIT" -eq 0 ]; then
  green "==> PASS: Codex の変更は verify.sh を通過。"
  bold  "    次のステップ: Claude が 'git diff' をレビューしてから commit すること。"
  echo  "    git status / git diff で変更内容を確認 →"
  git status --short
else
  red "==> FAIL: verify.sh が落ちた。Codex の変更を accept してはいけない。"
  echo "    'git diff' で問題箇所を確認し、Claude が修正方針を判断する。"
  echo "    変更を破棄する場合: git checkout -- . (慎重に)"
  exit "$VERIFY_EXIT"
fi
