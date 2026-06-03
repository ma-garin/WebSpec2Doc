#!/usr/bin/env bash
# WebSpec2Doc 検証ゲート — 「正しさ」の単一の真実。
# Codex はタスク完了前に必ずこれを green にする。Claude は commit 前に必ず実行する。
#
#   py_compile 全ソース → pytest 全件 → example.com スモーク(--compare 2回) → 成果物存在チェック
#
# 終了コード 0 かつ末尾 "ALL GREEN" のときのみ合格。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV_PY="$REPO_ROOT/venv/bin/python"
VENV_BIN="$REPO_ROOT/venv/bin"
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ws2d_verify.XXXXXX")"
SMOKE_URL="https://example.com"
COVERAGE_MIN=80

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }
step()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

fail() {
  red "FAILED: $1"
  rm -rf "$SMOKE_DIR"
  exit 1
}

trap 'rm -rf "$SMOKE_DIR"' EXIT

# --- 0. 環境チェック ---
step "0. 環境チェック (python3.12 venv)"
[ -x "$VENV_PY" ] || fail "venv が無い。'python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt' を実行"
PYVER="$("$VENV_PY" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[ "$PYVER" = "3.12" ] || fail "venv が python$PYVER。3.12 で再構築が必要 (greenlet が 3.13 でビルド失敗するため)"
"$VENV_PY" -c 'import playwright' 2>/dev/null || fail "playwright 未インストール。'pip install -r requirements.txt' を実行"
for tool in ruff black mypy; do
  [ -x "$VENV_BIN/$tool" ] || fail "$tool 未インストール。'pip install -r requirements-dev.txt' を実行"
done
green "OK: python$PYVER + playwright + ruff/black/mypy"

# --- 1. py_compile 全ソース ---
step "1. py_compile (構文チェック)"
PY_FILES=()
while IFS= read -r f; do PY_FILES+=("$f"); done < <(find src web app.py -name '*.py' 2>/dev/null)
"$VENV_PY" -m py_compile "${PY_FILES[@]}" || fail "py_compile エラー"
green "OK: ${#PY_FILES[@]} ファイル"

# --- 1b. 800行ガード ---
# Phase 1 分割対象の既知違反は一時除外（分割完了次第リストから削除する）
PHASE1_ALLOWED=(
  "web/routes/qa_process.py"   # Phase 1b: web/services/qa/ へ分割予定
  "templates/index.html"       # Phase 1c: templates/partials/ へ分割予定
)
step "1b. 800行ガード (.py/.js/.css/.html)"
OVER800=()
while IFS= read -r f; do
  lines=$(wc -l < "$f" | tr -d ' ')
  if [ "$lines" -gt 800 ]; then
    rel="${f#$REPO_ROOT/}"
    allowed=false
    for exc in "${PHASE1_ALLOWED[@]}"; do
      [ "$rel" = "$exc" ] && allowed=true && break
    done
    "$allowed" || OVER800+=("$rel ($lines 行)")
  fi
done < <(
  find src web app.py tests static templates \
    -not -path '*/output/*' -not -path '*/__pycache__/*' \
    \( -name '*.py' -o -name '*.js' -o -name '*.css' -o -name '*.html' \) 2>/dev/null
)
if [ ${#OVER800[@]} -gt 0 ]; then
  for item in "${OVER800[@]}"; do red "  800行超過: $item"; done
  fail "800行ガード違反 (${#OVER800[@]} ファイル)"
fi
if [ ${#PHASE1_ALLOWED[@]} -gt 0 ]; then
  printf '\033[33m  ⚠ 一時除外 (Phase 1 分割待ち): %s\033[0m\n' "${PHASE1_ALLOWED[@]}"
fi
green "OK: 新規ファイル全て 800行以内 (除外 ${#PHASE1_ALLOWED[@]} 件)"

# --- 2. lint + フォーマット + 型チェック ---
step "2. lint / format / 型チェック (ruff / black / mypy)"
"$VENV_BIN/ruff" check src app.py tests web || fail "ruff 違反"
"$VENV_BIN/black" --check src app.py tests web >/dev/null 2>&1 || fail "black 未整形 ('black src app.py tests web' で整形)"
"$VENV_BIN/mypy" || fail "mypy 型エラー"
green "OK: ruff + black + mypy"

# --- 3. pytest 全件 + カバレッジゲート ---
step "3. pytest (全テスト + カバレッジ ${COVERAGE_MIN}%)"
"$VENV_PY" -m pytest tests/ -q --cov=src --cov-report=term-missing --cov-fail-under="$COVERAGE_MIN" \
  || fail "pytest 失敗 or カバレッジ ${COVERAGE_MIN}% 未満"
green "OK: pytest pass + カバレッジ ${COVERAGE_MIN}%+"

# --- 4. スモーク: 実クロール2回 + 差分 ---
step "4. スモーク (example.com を --compare で2回)"
"$VENV_PY" src/main.py --url "$SMOKE_URL" --depth 1 --max-pages 2 \
  --format html,md --compare --output "$SMOKE_DIR" >/dev/null 2>&1 \
  || fail "1回目のクロールが失敗 (スタブが本物のクラッシュを隠していないか確認)"
"$VENV_PY" src/main.py --url "$SMOKE_URL" --depth 1 --max-pages 2 \
  --format html,md --compare --output "$SMOKE_DIR" >/dev/null 2>&1 \
  || fail "2回目のクロール(差分比較)が失敗"
green "OK: クロール2回成功"

# --- 5. 成果物の存在チェック ---
step "5. 成果物チェック"
DOMAIN_DIR="$SMOKE_DIR/example.com"
for artifact in report.html screens.md transition.mmd diff_report.html; do
  [ -s "$DOMAIN_DIR/$artifact" ] || fail "成果物が空/欠落: $artifact"
done
SNAP_COUNT="$(find "$DOMAIN_DIR/snapshots" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
[ "$SNAP_COUNT" -ge 2 ] || fail "スナップショットが2件未満 ($SNAP_COUNT 件)"
green "OK: 全成果物生成 + スナップショット ${SNAP_COUNT}件"

step "RESULT"
green "ALL GREEN"
