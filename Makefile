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
PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.runtime/ms-playwright
export PLAYWRIGHT_BROWSERS_PATH
E2E_DIR    := tests/e2e
SHOT_DIR   := tests/e2e/screenshots
MARKER     := .ui-verified

.PHONY: help setup setup-runtime check-runtime doctor test verify-ui quality-harness verify-all setup-hooks coverage lint clean check-venv demo security audit

# デフォルトターゲット
help:
	@echo ""
	@echo "  WebSpec2Doc — 開発コマンド"
	@echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "  make quality-harness  L0: 機能契約・実行パス・未実装UI検査"
	@echo "  make setup            Python依存・Chromium・git hookをセットアップ"
	@echo "  make setup-runtime    対応Chromiumを導入して実起動確認"
	@echo "  make check-runtime    Chromiumの実起動確認"
	@echo "  make doctor           環境不一致の一括診断（取得に失敗する時に実行）"
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

setup: check-venv
	$(PIP) install -r requirements-dev.txt
	$(PYTHON) scripts/manage_playwright_runtime.py install
	$(MAKE) setup-hooks

setup-runtime: check-venv
	$(PYTHON) scripts/manage_playwright_runtime.py install

check-runtime: check-venv
	$(PYTHON) scripts/manage_playwright_runtime.py check

doctor: check-venv
	$(PYTHON) src/doctor.py

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
# 対象URLは E2E_BASE_URL で上書きできる（既定ポートが他アプリに占有されている場合に使う）。
#   例: make verify-ui E2E_BASE_URL=http://127.0.0.1:8799
# =============================================================================
E2E_BASE_URL ?= http://127.0.0.1:8765
# 失敗が出たら即座に打ち切る（fail fast）。全件見たい時は E2E_MAXFAIL=0 で無制限。
E2E_MAXFAIL ?= 1
# conftest の flask_server は WEBSPEC2DOC_E2E_URL を見る。--base-url だけ変えても
# サーバ判定が既定ポートのままになるため、両方を同じ値に揃える。
export WEBSPEC2DOC_E2E_URL = $(E2E_BASE_URL)

verify-ui: check-venv
	@echo ""
	@echo "  ━━ L3: E2E システムテスト（UI 検証）━━━━━━━━━━━━━━━━━━━━"
	@echo "  テスト対象: $(E2E_BASE_URL)"
	@echo "  スクリーンショット保存先: $(SHOT_DIR)/"
	@echo ""
	@mkdir -p $(SHOT_DIR)
	$(PYTEST) $(E2E_DIR)/ -v \
		--screenshot=only-on-failure \
		--maxfail=$(E2E_MAXFAIL) \
		--output=$(SHOT_DIR) \
		--tb=short \
		--base-url=$(E2E_BASE_URL)
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
# 実機デモ（同梱デモサイト + 本体の同時起動）
# =============================================================================
demo: check-venv
	@bash scripts/demo.sh

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
# 依存脆弱性監査（R3-21）
# =============================================================================
audit: check-venv ## 依存脆弱性監査（Python + AutoRun npm env）
	venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt || true
	@if [ -d output/.playwright_env/node_modules ]; then \
	  cd output/.playwright_env && npm audit --audit-level=high || true; \
	fi
	@echo "audit done（critical/high は docs/security/ の記録に従い対応）"

# =============================================================================
# 静的解析
# =============================================================================
lint: check-venv
	@echo ""
	@echo "  ━━ 静的解析 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	venv/bin/ruff check src/ web/ app.py --fix
	venv/bin/mypy src/ web/ app.py --ignore-missing-imports
	$(PYTHON) scripts/check_e2e_conventions.py
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
