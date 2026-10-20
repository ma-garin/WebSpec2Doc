"""リバース解析（System 01）の結果表示と実行の API。

GET  /api/reverse-analysis?domain=        結果を画面向けに整形して返す（読み取りのみ）
POST /api/sites/<domain>/reverse-analysis/run   CLI と同じ service で解析して保存する

状態の取り違え（静的候補を実測扱い・method 不明を GET 補完など）をしない形に変換する。
値はすべてサイトの保存物から取り、無いものは null（画面では「未確認」「未計測」）で返す。
結果は run.json（対象サイト・snapshot digest）と一致するときだけ表示する（別サイトの結果を混ぜない）。
置き場所は web/services/reverse_analysis_run.py を参照。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, request

from reverse_analysis.normalize import expression_path_pattern
from web.config import OUTPUT_DIR
from web.services import reverse_analysis_run as runner
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

bp = Blueprint("reverse_analysis", __name__)


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
        "provider_route_nodes_not_provided": "provider（REA）から route を取得できない（route が 0 件という意味ではない）",
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
        # path を解決できなかった呼び出しは、式から path パターンを作って見せる（推論。候補としてだけ扱う）
        value = (c.get("path") or c.get("path_pattern") or expression_path_pattern(c.get("expression"))
                 or c.get("expression"))
        if not value:  # route / API の値が無いときにファイル名を値として見せない
            value = c.get("artifact_path") if kind in ("module", "source") else None
        value = value or "（値を特定できない）"
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


def _source_map(run: dict, doc: dict) -> list[dict]:
    """このサイトで取得した source map の状況。成功しても「正常」とは書かない。"""
    maps = int(run.get("source_maps") or 0)
    unavailable = any(
        "source-map" in d.get("message", "") and d.get("code") == "static_node_unsupported"
        for d in doc.get("diagnostics", [])
    )
    if maps == 0:
        row = ("source map なし", "success", "解析は成功したが、元ソースへの対応付けはできない")
    elif doc.get("status") == "partial":
        row = ("source map 一部のみ", "partial", "一部のみ取得。読めなかった部分は利用不可")
    else:
        note = "（一部は解析対象外）" if unavailable else ""
        row = ("source map あり", "success", f"取得はできたが、鮮度と正確な行対応は保証されない{note}")
    return [{"case": "site", "label": row[0], "outcome": row[1], "meaning": f"{row[2]}（取得 {maps} 件）"}]


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


def _summary(run: dict) -> list[dict]:
    b, a = run.get("before") or {}, run.get("after") or {}

    def row(key: str, label: str, mkey: str, note: str = "") -> dict:
        return {"key": key, "label": label, "before": b.get(mkey), "after": a.get(mkey), "note": note}

    # REA が route 宣言を出さなかったときは「取得不可」。0 件（見つからなかった）とは区別して画面に渡す。
    route_unavailable = bool(a) and a.get("route_candidates") is None
    route = row("route", "Route", "route_candidates",
                "provider（REA）から取得不可: route 宣言が出力されなかった（ルートが 0 件という意味ではない）"
                if route_unavailable else "静的な宣言。到達は未確認")  # fmt: skip
    route["unavailable"] = route_unavailable
    return [
        row("static", "静的候補", "static_candidates", "ソースに構文がある候補。実行の証明ではない"),
        route,
        row("api_static", "API 候補（静的）", "api_candidates", "HTTP method は不明のまま"),
        row("api_runtime", "API（実測）", "runtime_observations", "実行時の観測。リバース解析では増えない"),
        row("module_dep", "Module 依存", "module_dependency_edges", "import の関係"),
        row("source_map", "Source map 根拠", "source_mapped_evidence", "鮮度は保証されない"),
        {"key": "qa", "label": "QA に答えられる問い", "before": None, "after": None,
         "note": "未計測（このサイトの正解集合が無い）"},
    ]  # fmt: skip


def _run_meta(domain: str, run: dict | None) -> dict:
    provider = runner.provider_status()
    running = runner.is_running(domain)
    snapshot = runner.latest_snapshot(_base(), domain)
    reason = nxt = None
    if running:
        reason, nxt = "このサイトのリバース解析を実行中です。", "完了すると結果が自動で更新されます。"
    elif snapshot is None:
        reason, nxt = "このサイトの実行時記録がありません。", "先にドキュメント作成でサイトを解析してください。"
    elif not provider.available:
        reason, nxt = provider.reason, provider.next_action
    last = None
    if run:
        last = {k: run.get(k) for k in ("finished_at", "seconds", "js_files", "source_maps")}
        last["status"] = {"complete": "complete", "partial": "partial"}.get(run.get("status") or "", "failed")
    return {
        "site": {"domain": domain},
        "provider_status": {
            "available": provider.available, "version": provider.version,
            "reason": provider.reason, "next_action": provider.next_action,
        },
        "last_run": last,
        "running": running,
        "can_run": reason is None,
        "cannot_run_reason": reason,
        "cannot_run_next": nxt,
    }  # fmt: skip


def _base() -> Path:
    return scoped_output_dir(OUTPUT_DIR)


def _payload(domain: str) -> dict:
    root = runner.site_dir(_base(), domain)
    target = root / runner.RESULT_DIR / runner.RESULT_FILE
    run_path = root / runner.RUN_FILE
    run = _read_json(run_path) if run_path.is_file() else None
    meta = _run_meta(domain, run)
    if not target.is_file():
        return {**meta, "state": "empty",
                "message": "このサイトのリバース解析結果はまだありません。",
                "next_action": "「リバース解析を実行」を押すと、このサイトの JavaScript を解析します。"}  # fmt: skip
    doc = _read_json(target)
    sha = (doc.get("inputs") or {}).get("runtime_snapshot_sha256")
    if not run or run.get("domain") != domain or run.get("snapshot_sha256") != sha:
        return {**meta, "state": "mismatch",
                "message": "保存されている結果の対象を、このサイトの実行記録で確かめられませんでした。",
                "next_action": "「リバース解析を実行」で、このサイトの結果を作り直してください。"}  # fmt: skip
    producer = doc.get("producer") or {}
    version = producer.get("provider_version")
    diagnostics = _diagnostics(doc.get("diagnostics", []))
    latest = runner.latest_snapshot(_base(), domain)
    if latest is not None and latest.name != run.get("snapshot"):
        diagnostics.insert(0, {
            "severity": "warning",
            "message": "この結果は最新のサイト解析より前の実行時記録で作られています。",
            "next_action": "最新の記録で比べるには、リバース解析を再実行してください。",
        })  # fmt: skip
    coverage = doc.get("coverage") or {}
    return {
        **meta,
        "state": "ok",
        "status": doc.get("status"),
        "provider": {"name": "rea-agents", "version": version} if version else None,
        "input_label": domain,
        "summary": _summary(run),
        "added_seconds": run.get("seconds"),
        "measured_once": run.get("repetitions") == 1,
        "evidence": _runtime_evidence(doc) + _static_evidence(doc, version),
        "dependencies": _dependencies(doc),
        "source_map": _source_map(run, doc),
        "diagnostics": diagnostics,
        "coverage_limitations": _limitations(
            (coverage.get("static") or {}).get("limitations", [])
            + (coverage.get("runtime") or {}).get("limitations", [])
        ),
    }


def site_evidence(domain: str) -> dict:
    """他システム（System 02・09）向けの読み出し口。画面 API と同じ整形・同じ対象確認を通す。

    state が "ok" のときだけ evidence / dependencies / summary を持つ。
    それ以外（empty / mismatch / error）は結果を使わず、未確認として扱うこと。
    """
    if not _valid_domain(domain):
        return {"state": "error", "message": "サイトの指定が正しくありません。"}
    try:
        return _payload(domain)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"state": "error", "message": "リバース解析の結果を読み込めませんでした。"}


_BAD_SITE = {"state": "error", "message": "サイトの指定が正しくありません。",
             "next_action": "サイト一覧から開き直してください。"}  # fmt: skip


@bp.get("/api/reverse-analysis")
def api_reverse_analysis() -> tuple[dict, int] | dict:
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return _BAD_SITE, 400
    try:
        return _payload(domain)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        current_app.logger.warning("reverse_analysis の読み込みに失敗: %s (%s)", domain, exc)
        return {
            "state": "error",
            "message": "リバース解析の結果を読み込めませんでした（ファイルが壊れている可能性があります）。",
            "next_action": "リバース解析を再実行してください。",
        }


_HTTP = {"success": 200, "partial": 200, "busy": 409, "no_runtime": 422,
         "provider_unavailable": 422, "error": 500}  # fmt: skip


@bp.post("/api/sites/<domain>/reverse-analysis/run")
def api_reverse_analysis_run(domain: str) -> tuple[dict, int]:
    """対象サイトの最新 snapshot と、そのページの JS で解析する。入力は domain だけ。"""
    if not _valid_domain(domain) or not (_base() / domain).is_dir():
        return {"result": "error", "message": _BAD_SITE["message"], "next_action": _BAD_SITE["next_action"]}, 404
    try:
        res = runner.run_for_site(_base(), domain)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        current_app.logger.warning("reverse_analysis の実行に失敗: %s (%s)", domain, exc)
        res = runner.RunResult("error", "リバース解析を完了できませんでした。結果は更新していません。",
                               "時間をおいて再実行してください。")  # fmt: skip
    return {"result": res.result, "message": res.message, "next_action": res.next_action}, _HTTP[res.result]
