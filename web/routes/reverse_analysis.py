"""リバース解析（System 01）の結果を画面向けに整形して返す read-only API。

reverse_analysis.json（``python -m main --reverse-analysis`` の出力）を読み、
状態の取り違え（静的候補を実測扱い・method 不明を GET 補完など）をしない形に変換する。
値はすべてファイルから取り、無いものは null（画面では「未確認」「未計測」）で返す。

置き場所: <出力>/<domain>/reverse_analysis/
  reverse_analysis.json     必須。解析結果
  value_measurement.json    任意。実行時のみ／＋リバース解析の比較測定
  source_map_checks.json    任意。source map の検証結果（ケースごとの終了状態）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, request

from web.config import OUTPUT_DIR
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

bp = Blueprint("reverse_analysis", __name__)

_DIR = "reverse_analysis"

_KIND_LABEL = {"route": "Route", "api": "API", "module": "Module", "source": "Source"}

_STATIC_STATE = {"observed": "static", "inferred": "inferred", "ambiguous": "ambiguous"}

_BASIS = {
    "route_static_only": "静的な宣言のみ。画面遷移の実測とは照合していない",
    "method_missing": "HTTP method が不明なため、実測 API と照合していない",
    "runtime_only": "実行時に観測。対応する静的候補は無い",
    "matched": "静的候補と実測が一致",
}

_LIMITATION = {
    "method_not_provided_by_provider": "HTTP method は解析結果に無い（不明のまま。補完しない）",
    "route_not_compared_to_runtime_api": "実測 API とは照合していない",
    "route_navigation_not_in_snapshot": "画面遷移の実測が記録に無い",
    "static_candidate_is_syntax_presence_only": "構文があることだけを示す。実行の証明ではない",
    "provider_endpoint_http_method_not_provided": "解析ツールは HTTP method を出していない",
    "observed_calls_only": "実行時に通った呼び出しだけを記録している",
    "runtime_origin_not_recorded": "実測の origin は記録されていない",
    "runtime_query_not_retained": "実測の query は保存していない",
}

_IMPORT_KIND = {"static-import": "静的 import", "dynamic-import": "動的 import", "require": "require"}

# source map の検証ケース。成功＝正常ではないので、意味を必ず併記する。
_SOURCE_MAP_CASES = {
    "normal": ("source map あり", "元ソース名は取得。生成コードとの正確な行対応は未確認"),
    "missing": ("source map なし", "解析は成功したが、元ソースへの対応付けはできない"),
    "stale": ("古い source map", "解析は成功したが、map の鮮度は保証されない（古さを検出できない）"),
    "malformed": ("壊れた source map", "一部のみ取得。読めなかった部分は利用不可"),
}


def _limitations(codes: list[str]) -> list[str]:
    out = []
    for code in codes or []:
        text = _LIMITATION.get(code)
        if text is None:
            prefix, _, rest = code.partition(":")
            text = _LIMITATION_PREFIX[prefix] + rest if rest and prefix in _LIMITATION_PREFIX else code
        out.append(text)
    return out


_LIMITATION.update(
    {
        "route_candidate_from_static_syntax": "静的な構文から見つけた route 候補（画面遷移の実測ではない）",
        "unsupported_nodes": "解析対象外の要素がある",
    }
)

# 「接頭辞:値」形式の制限。値はそのまま見せ、接頭辞だけ利用者の言葉に置き換える。
_LIMITATION_PREFIX = {
    "provider": "解析ツールの注記: ",
    "provider_syntax_state": "解析ツール上の状態（構文の有無。実行ではない）: ",
    "provider_authority": "根拠の種類: ",
    "provider_mechanism": "検出方法: ",
    "unsupported_nodes": "解析対象外の要素: ",
}


def _loc(path: str | None, line: int | None, col: int | None) -> str | None:
    if not path:
        return None
    return f"{path}:{line}:{col}" if line is not None else path


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _static_evidence(doc: dict, version: str | None) -> list[dict]:
    basis_by_id: dict[str, str] = {}
    for rel in doc.get("relations", []):
        for sid in rel.get("static_ids", []):
            basis_by_id[sid] = rel.get("basis", "")
    out = []
    for c in doc.get("static_candidates", []):
        kind = c.get("kind", "")
        loc = c.get("location") or {}
        value = c.get("path") or c.get("expression") or c.get("artifact_path") or "（値なし）"
        state = _STATIC_STATE.get(c.get("epistemic_state", ""), "unknown")
        if c.get("resolution") == "unavailable":
            state = "inferred" if state == "inferred" else "unavailable"
        claim = {
            "route": f"ソースに画面ルート「{value}」の宣言がある（到達は未確認）",
            "api": f"ソースに API 呼び出し「{value}」がある（実行は未確認）",
            "module": f"モジュール「{value}」がある",
            "source": f"source map の参照「{value}」がある",
        }.get(kind, value)
        basis = basis_by_id.get(c.get("id", ""))
        out.append(
            {
                "id": c.get("id"),
                "group": kind if kind in _KIND_LABEL else "source",
                "kind_label": _KIND_LABEL.get(kind, kind),
                "value": value,
                "state": state,
                "origin": "static",
                "method": c.get("method"),
                "location": _loc(
                    loc.get("artifact_path"), loc.get("start_line"), loc.get("start_column")
                ),
                "provider": "静的解析" + (f"（rea-agents {version}）" if version else ""),
                "claim": claim,
                "relation": _BASIS.get(basis or "", basis or "対応付けなし"),
                "limitations": _limitations(c.get("limitations", [])),
                "rea_version": version,
            }
        )
    return out


def _runtime_evidence(doc: dict) -> list[dict]:
    out = []
    for r in doc.get("runtime_observations", []):
        method, path = r.get("method"), r.get("path") or "（path なし）"
        out.append(
            {
                "id": r.get("id"),
                "group": "api",
                "kind_label": "API",
                "value": path,
                "state": "observed",
                "origin": "runtime",
                "method": method,
                "location": f"実行記録 {r.get('page_url') or ''}".strip(),
                "provider": "実行時観測（既存の解析記録）",
                "claim": f"実行時に {method or '不明'} {path} を観測（{r.get('status_code')}）",
                "relation": _BASIS["runtime_only"],
                "limitations": [],
                "rea_version": None,
            }
        )
    return out


def _dependencies(doc: dict) -> list[dict]:
    out = []
    for e in (doc.get("provider_evidence") or {}).get("dependency_edges", []):
        props = e.get("properties") or {}
        lv = ((e.get("location") or {}).get("value")) or {}
        start = lv.get("start") or {}
        source = lv.get("source") or "（位置なし）"
        external = props.get("resolution_status") == "external"
        out.append(
            {
                "source": source,
                "target": props.get("resolved_path") or props.get("specifier") or "（不明）",
                "relation_label": _IMPORT_KIND.get(props.get("kind", ""), props.get("kind") or "依存"),
                "state": _STATIC_STATE.get(e.get("provider_state", ""), "unknown"),
                "location": _loc(lv.get("source"), start.get("line"), start.get("column")),
                "external": external,
                "limitations": _limitations(e.get("provider_limitations", [])),
            }
        )
    return out


def _source_map(base: Path) -> list[dict]:
    path = base / "source_map_checks.json"
    if not path.is_file():
        return []
    out = []
    for case in _read_json(path):
        name = case.get("case", "")
        label, meaning = _SOURCE_MAP_CASES.get(name, (name, "結果の意味は未確認"))
        status = case.get("status")
        outcome = {"complete": "success", "partial": "partial"}.get(status or "", "failed")
        out.append({"case": name, "label": label, "outcome": outcome, "meaning": meaning})
    return out


def _diagnostics(items: list[dict]) -> list[dict]:
    """未対応 node の診断は内部 ID を含み件数も多いので、種類ごとの件数 1 行にまとめる。"""
    out = [
        {k: d.get(k, "") for k in ("severity", "message", "next_action")}
        for d in items
        if d.get("code") != "static_node_unsupported"
    ]
    unsupported = [d for d in items if d.get("code") == "static_node_unsupported"]
    if unsupported:
        kinds = sorted(
            {m.split("kind=", 1)[1].split()[0] for d in unsupported if "kind=" in (m := d.get("message", ""))}
        )
        out.append(
            {
                "severity": "info",
                "message": f"解析対象外の要素が {len(unsupported)} 件あり、候補にしていません（種類: {', '.join(kinds) or '不明'}）。",
                "next_action": "内容が必要な場合は、解析ツールの出力を直接確認してください。",
            }
        )
    return out


def _summary(doc: dict, measurement: dict | None) -> tuple[list[dict], float | None, bool]:
    if measurement:
        b = measurement.get("before", {}).get("metrics", {})
        a = measurement.get("after", {}).get("metrics", {})
        score = measurement.get("relative_score") or {}
        added = measurement.get("added_wall_seconds")
        once = (measurement.get("conditions") or {}).get("repetitions") == 1
    else:  # 比較測定が無い場合: 実行時のみの値は解析結果の実測件数だけ分かる
        b = {"runtime_observations": len(doc.get("runtime_observations", []))}
        s = doc.get("static_candidates", [])
        a = {
            "static_candidates": len(s),
            "route_candidates": sum(1 for c in s if c.get("kind") == "route"),
            "api_candidates": sum(1 for c in s if c.get("kind") == "api"),
            "module_dependency_edges": len(_dependencies(doc)),
            "runtime_observations": len(doc.get("runtime_observations", [])),
        }
        score, added, once = {}, None, False

    def row(key: str, label: str, mkey: str, note: str = "") -> dict:
        return {"key": key, "label": label, "before": b.get(mkey), "after": a.get(mkey), "note": note}

    rows = [
        row("static", "静的候補", "static_candidates", "ソースに構文がある候補。実行の証明ではない"),
        row("route", "Route", "route_candidates", "静的な宣言。到達は未確認"),
        row("api_static", "API 候補（静的）", "api_candidates", "HTTP method は不明のまま"),
        row("api_runtime", "API（実測）", "runtime_observations", "実行時の観測。リバース解析では増えない"),
        row("module_dep", "Module 依存", "module_dependency_edges", "import の関係"),
        {
            "key": "qa",
            "label": "QA に答えられる問い",
            "before": score.get("before_answered"),
            "after": score.get("after_answered"),
            "note": f"{score['total_questions']} 問中" if score.get("total_questions") else "未計測",
        },
    ]
    return rows, added, once


def _payload(domain: str) -> dict:
    base = scoped_output_dir(OUTPUT_DIR) / domain / _DIR
    target = base / "reverse_analysis.json"
    if not target.is_file():
        return {
            "state": "empty",
            "message": "このサイトにはリバース解析の結果がありません。",
            "next_action": "CLI モードでリバース解析を実行すると、ここに結果が表示されます。",
        }
    doc = _read_json(target)
    status = doc.get("status")
    if status in ("provider_unavailable", "unavailable"):
        return {
            "state": "provider_unavailable",
            "message": "静的解析ツールを実行できませんでした。",
            "next_action": "解析ツールの導入場所を確認して再実行してください。",
        }
    measurement_path = base / "value_measurement.json"
    measurement = _read_json(measurement_path) if measurement_path.is_file() else None
    producer = doc.get("producer") or {}
    version = producer.get("provider_version")
    summary, added, once = _summary(doc, measurement)
    coverage = doc.get("coverage") or {}
    return {
        "state": "ok",
        "status": status,
        "provider": {"name": "rea-agents", "version": version} if version else None,
        "input_label": (doc.get("inputs") or {}).get("static_root_label", ""),
        "summary": summary,
        "added_seconds": added,
        "measured_once": once,
        "evidence": _runtime_evidence(doc) + _static_evidence(doc, version),
        "dependencies": _dependencies(doc),
        "source_map": _source_map(base),
        "diagnostics": _diagnostics(doc.get("diagnostics", [])),
        "coverage_limitations": _limitations(
            (coverage.get("static") or {}).get("limitations", [])
            + (coverage.get("runtime") or {}).get("limitations", [])
        ),
    }


@bp.get("/api/reverse-analysis")
def api_reverse_analysis() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"state": "error", "message": "サイトの指定が正しくありません。",
                "next_action": "サイト一覧から開き直してください。"}, 400
    try:
        return _payload(domain)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        current_app.logger.warning("reverse_analysis の読み込みに失敗: %s (%s)", domain, exc)
        return {
            "state": "error",
            "message": "リバース解析の結果を読み込めませんでした（ファイルが壊れている可能性があります）。",
            "next_action": "同じ入力でリバース解析を再実行してください。",
        }
