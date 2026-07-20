"""AutoRun 実行結果レポート専用ページ（仕様15〜17）。

AutoRun は独立したシステムなので、結果も SPA のタブではなく専用ページで開く。

構造（仕様17）:
    ダッシュボード / QA仕様書 / 計画 / 分析 / 設計 / ケース / スクリプト / 実行結果

各セクションは既に生成済みの成果物を素材にする。存在しない成果物は
「未生成」として正直に示し、あたかも在るように見せない。
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, render_template, request

from web.config import OUTPUT_DIR
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from autorun.qf_schema import to_table  # noqa: E402
from autorun.stages import Pipeline, test_case_rows  # noqa: E402

logger = logging.getLogger(__name__)

bp = Blueprint("autorun_report", __name__)

MAX_TEXT_CHARS = 200_000


@dataclass(frozen=True)
class Section:
    """レポートのセクション定義（仕様17の構造）。"""

    key: str
    label: str
    description: str


SECTIONS: tuple[Section, ...] = (
    Section("dashboard", "ダッシュボード", "この実行で何が分かったかの要約"),
    Section("spec", "QA仕様書", "実測した画面仕様"),
    Section("plan", "計画", "テスト目的とテスト計画"),
    Section("analysis", "分析", "テスト分析とフィーチャー・観点"),
    Section("design", "設計", "テスト設計と適用した技法"),
    Section("cases", "ケース", "テストケース（QualityForward カラム）"),
    Section("script", "スクリプト", "生成した Playwright スクリプト"),
    Section("results", "実行結果", "テスト実行の結果と証跡"),
)


def _domain_dir(domain: str) -> Path:
    return scoped_output_dir(OUTPUT_DIR) / domain


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")[:MAX_TEXT_CHARS]
    except OSError as exc:
        logger.warning("読み込めません %s: %s", path, exc)
        return None


def _read_json(path: Path) -> Any | None:
    """JSON を読む。

    表示用テキストと違い **切り詰めてはいけない**。途中で切ると解析に失敗し、
    「データが無い」ように見えてしまう（実際には在る）。
    """
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("読み込めません %s: %s", path, exc)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("JSON として解釈できません %s: %s", path, exc)
        return None


def _pipeline(domain: str) -> Pipeline:
    data = _read_json(_domain_dir(domain) / "qa_process" / "stages.json")
    if isinstance(data, dict):
        return Pipeline.from_dict(data)
    return Pipeline.initial()


def _dashboard(
    domain: str,
    report: dict | None,
    results: dict | None,
    mutation_check: dict | None = None,
    nonfunctional: dict | None = None,
    coverage: dict | None = None,
) -> dict[str, Any]:
    screens = (report or {}).get("screens") or []
    forms = [f for s in screens for f in (s.get("forms") or [])]
    inputs = sum(len(f.get("fields") or f.get("inputs") or []) for f in forms)

    # playwright_report.json は total/passed/failed をトップレベルに持つ（{"summary": {...}} ではない）。
    # 従来はこのキー不一致により、実行済みでも「未実行」と表示されていた（監査で発覚・要修正）。
    results = results or {}
    summary = results.get("summary") or {}
    passed = summary.get("passed", results.get("passed"))
    failed = summary.get("failed", results.get("failed"))
    total = summary.get("total", results.get("total"))
    if total is None and isinstance(passed, int) and isinstance(failed, int):
        total = passed + failed

    pipeline = _pipeline(domain)
    approved = sum(1 for s in pipeline.stages if s.status in ("approved", "skipped"))

    mutation_check = mutation_check or {}
    self_check_score = (
        mutation_check.get("score") if mutation_check.get("applicable", True) else None
    )

    return {
        "screen_count": len(screens),
        "form_count": len(forms),
        "input_count": inputs,
        "test_total": total,
        "test_passed": passed,
        "test_failed": failed,
        "stages_approved": approved,
        "stages_total": len(pipeline.stages),
        # AutoRun自身が実行した自己検証（ミューテーションテスト）のスコア。
        # 生成テストが実際に欠陥を検出できるかを、毎回の実行で確認する。
        "self_check_score": self_check_score,
        "self_check_survivor_count": mutation_check.get("survivor_count"),
        # L4 非機能の合否判定（既存観測データの接続）。未実行なら None。
        "nonfunctional_overall": (nonfunctional or {}).get("overall"),
        "nonfunctional_judgements": (nonfunctional or {}).get("judgements") or [],
        # L0 観測の完全性。「どの範囲についての結論か」を必ず併記する。
        "observation_scope": (coverage or {}).get("scope_statement"),
        "observation_gaps": (coverage or {}).get("gaps") or [],
        # この製品の原則。数値だけを見て「問題なし」と読まれないようにする。
        "claim_scope": (
            "ここに示すのは自動で検出できた範囲の観測結果です。"
            "検証できていない領域は「未検証」であり、欠陥が無いことの証明ではありません。"
        ),
    }


def _section_payload(domain: str, key: str) -> dict[str, Any]:
    base = _domain_dir(domain)
    qa = base / "qa_process"

    if key == "dashboard":
        return {
            "kind": "dashboard",
            "data": _dashboard(
                domain,
                _read_json(base / "report.json"),
                _read_json(qa / "playwright_report.json"),
                _read_json(qa / "mutation_verification.json"),
                _read_json(qa / "nonfunctional_judgement.json"),
                _read_json(qa / "observation_coverage.json"),
            ),
        }
    if key == "spec":
        return {"kind": "markdown", "text": _read_text(base / "screens.md"), "source": "screens.md"}
    if key == "plan":
        return {"kind": "markdown", "text": _read_text(qa / "test_plan.md"), "source": "test_plan.md"}
    if key == "analysis":
        return {"kind": "markdown", "text": _read_text(qa / "test_analysis.md"), "source": "test_analysis.md"}
    if key == "design":
        return {"kind": "markdown", "text": _read_text(qa / "test_design.md"), "source": "test_design.md"}
    if key == "cases":
        rows = test_case_rows(_pipeline(domain))
        if rows:
            return {"kind": "table", "source": "stages.json", **to_table(rows)}
        # 段階パイプライン未実施なら、従来の生成物を出す
        return {"kind": "markdown", "text": _read_text(qa / "test_cases.md"), "source": "test_cases.md"}
    if key == "script":
        return {"kind": "code", "text": _read_text(qa / "autorun.spec.ts"), "source": "autorun.spec.ts"}
    if key == "results":
        return {
            "kind": "results",
            "data": _read_json(qa / "playwright_report.json"),
            "source": "playwright_report.json",
        }
    return {"kind": "unknown"}


@bp.get("/autorun/report/<domain>")
def autorun_report_page(domain: str) -> str:
    """実行結果レポートの専用ページ（仕様16）。"""
    if not _valid_domain(domain):
        abort(404)
    if not _domain_dir(domain).is_dir():
        abort(404)
    return render_template(
        "autorun-report.html",
        domain=domain,
        sections=[{"key": s.key, "label": s.label, "description": s.description} for s in SECTIONS],
    )


@bp.get("/api/autorun/report/<domain>")
def api_autorun_report(domain: str) -> tuple[dict, int] | dict:
    """レポートのセクション内容を返す。"""
    if not _valid_domain(domain):
        return {"error": "ドメインが不正です"}, 400
    if not _domain_dir(domain).is_dir():
        return {"error": "この対象の成果物が見つかりません"}, 404

    key = request.args.get("section", "dashboard")
    if key not in {s.key for s in SECTIONS}:
        return {"error": f"未知のセクションです: {key}"}, 400

    return {"domain": domain, "section": key, **_section_payload(domain, key)}
