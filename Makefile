# =============================================================================
# Makefile — WebSpec2Doc 開発コマンド
#
# 使い方:
#   make help              コマンド一覧
#   make test              ユニット・統合テスト（L1/L2）
#   make verify-ui         E2E テスト（L3）+ .ui-verified マーカー生成
#   make quality-harness   機能契約・実行パス・未実装UIを検査
#   make verify-all        quality-harness + test + verify-ui
#   make setup-hooks       git フックのインストール
#   make coverage          カバレッジレポート生成
# =============================================================================

PYTHON     := venv/bin/python
PIP        := venv/bin/pip
PYTEST     := venv/bin/python -m pytest
E2E_DIR    := tests/e2e
SHOT_DIR   := tests/e2e/screenshots
MARKER     := .ui-verified

.PHONY: help test verify-ui quality-harness verify-all setup-hooks coverage lint clean check-venv

# デフォルトターゲット
help:
	@echo ""
	@echo "  WebSpec2Doc — 開発コマンド"
	@echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "  make quality-harness  L0: 機能契約・実行パス・未実装UI検査"
	@echo "  make test             L1/L2: ユニット・統合テスト実行"
	@echo "  make verify-ui        L3: E2E テスト実行（UI変更後は必須）"
	@echo "  make verify-all       L0-L3: ハーネス + test + verify-ui"
	@echo "  make coverage         カバレッジレポートを生成"
	@echo "  make setup-hooks      pre-commit hook をインストール"
	@echo "  make lint             ruff + mypy による静的解析"
	@echo "  make clean            生成ファイルを削除"
	@echo ""
	@echo "  Functional Integrity Gate: docs/process/functional-integrity-gate.md"
	@echo "  Definition of Done:         docs/DEFINITION_OF_DONE.md"
	@echo "  テスト戦略:                 docs/TESTING_STRATEGY.md"
	@echo ""

# =============================================================================
# ゲート確認
# =============================================================================
check-venv:
	@if [ ! -f "$(PYTHON)" ]; then \
		echo "エラー: venv が見つかりません。"; \
		echo "  python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"; \
		exit 1; \
	fi

# =============================================================================
# L0: 機能整合性ハーネス
# =============================================================================
quality-harness: check-venv
	@echo ""
	@echo "  ━━ L0: Functional Integrity Harness ━━━━━━━━━━━━━━━━━━━━━"
	$(PYTHON) scripts/quality_harness.py
	@echo ""

verify-all: quality-harness test verify-ui
	@echo ""
	@echo "  ✅ verify-all PASS（quality-harness + test + verify-ui）"
	@echo ""

# =============================================================================
# L1/L2: ユニット・統合テスト
# =============================================================================
test: check-venv
	@echo ""
	@echo "  ━━ L1/L2: ユニット・統合テスト ━━━━━━━━━━━━━━━━━━━━━━━━"
	$(PYTEST) tests/ --ignore=$(E2E_DIR) -q --tb=short
	@echo ""

# =============================================================================
# L1/L2: カバレッジ付きテスト
# =============================================================================
coverage: check-venv
	@echo ""
	@echo "  ━━ カバレッジ計測 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	$(PYTEST) tests/ --ignore=$(E2E_DIR) \
		--cov=src --cov=web \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		-q --tb=short
	@echo ""

# =============================================================================
# L3: E2E テスト（UI変更後の必須実行）
# =============================================================================
verify-ui: check-venv
	@echo ""
	@echo "  ━━ L3: E2E システムテスト（UI 検証）━━━━━━━━━━━━━━━━━━━━"
	@echo "  テスト対象: http://127.0.0.1:8765"
	@echo "  スクリーンショット保存先: $(SHOT_DIR)/"
	@echo ""
	@mkdir -p $(SHOT_DIR)
	$(PYTEST) $(E2E_DIR)/ -v \
		--screenshot=on \
		--output=$(SHOT_DIR) \
		--tb=short \
		--base-url=http://127.0.0.1:8765
	@git_head=$$(git rev-parse HEAD 2>/dev/null || echo "no-git"); \
	 ui_hash=$$($(PYTHON) scripts/ui-hash.py disk); \
	 ts=$$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S); \
	 printf "%s %s %s\n" "$$git_head" "$$ui_hash" "$$ts" > $(MARKER)
	@echo ""
	@echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  ✅ E2E テスト PASS"
	@echo "  ✅ $(MARKER) マーカーを生成しました（git hash + UI hash）"
	@echo "  📸 スクリーンショット: $(SHOT_DIR)/"
	@echo ""
	@echo "  次のステップ（DEFINITION_OF_DONE.md Type B）:"
	@echo "  □ ブラウザでスクリーンショットを目視確認"
	@echo "  □ 変更した機能のフロー全体を手動で通して確認"
	@echo "  □ 確認完了後に git commit"
	@echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# =============================================================================
# pre-commit hook インストール
# =============================================================================
setup-hooks:
	@echo "pre-commit hook をインストール中..."
	@cp .githooks/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "✅ .git/hooks/pre-commit をインストールしました"
	@echo ""
	@echo "動作確認:"
	@echo "  git commit でゲートが実行されます"
	@echo "  UI ファイル変更時は make verify-ui が必要です"

# =============================================================================
# セキュリティスキャン
# =============================================================================
security: check-venv
	@echo ""
	@echo "  ━━ セキュリティスキャン ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	venv/bin/pip install --quiet bandit pip-audit 2>/dev/null || true
	venv/bin/python -m bandit -r src web app.py -ll -q
	venv/bin/python -m pip_audit --requirement requirements.txt -q
	@echo "  ✅ セキュリティスキャン完了"

# =============================================================================
# 静的解析
# =============================================================================
lint: check-venv
	@echo ""
	@echo "  ━━ 静的解析 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	venv/bin/ruff check src/ web/ app.py --fix
	venv/bin/mypy src/ web/ app.py --ignore-missing-imports
	@echo ""

# =============================================================================
# クリーンアップ
# =============================================================================
clean:
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@find . -name ".coverage" -delete 2>/dev/null || true
	@rm -f $(MARKER)
	@echo "✅ クリーンアップ完了（$(MARKER) を削除しました）"
