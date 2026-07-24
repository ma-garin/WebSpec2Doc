"""WebSpec2Doc 管理 CLI — 観点セット管理とテストケースレビューを端末から操作する。

GUI（`web/routes/viewpoints.py` / `web/routes/review.py`）でしか行えなかった
観点セットのライフサイクル操作とレビュー状態の更新を、Flask を起動せずに
サブコマンドで実行できるようにする。下位のストア／サービス層は Flask
リクエストコンテキストに非依存で、テナント解決はコンテキスト外では既定
（単一利用者）へフォールバックする。

使い方:

    python src/cli_manage.py viewpoints sets
    python src/cli_manage.py viewpoints export <set_id> -o vp.csv
    python src/cli_manage.py viewpoints import <set_id> vp.csv
    python src/cli_manage.py viewpoints publish <set_id> <version> --reason "..."
    python src/cli_manage.py review cases <domain>
    python src/cli_manage.py review update <domain> <case_id> --status approved

前提: カレントディレクトリはリポジトリルート（instance/viewpoints.db・output/ が
相対パスで解決されるため）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _ensure_web_importable() -> None:
    """`python src/cli_manage.py` 実行時に web パッケージを import 可能にする。"""
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if isinstance(value, list):
        for row in value:
            print(_format_row(row))
    elif isinstance(value, dict):
        print(_format_row(value))
    else:
        print(value)


def _format_row(row: Any) -> str:
    if not isinstance(row, dict):
        return str(row)
    # 主要キーを優先して1行に整形する（無ければ JSON へフォールバック）。
    for keys in (
        ("id", "name", "published_version", "draft_version"),
        ("version_number", "status", "change_reason"),
        ("id", "name", "category", "risk_weight", "enabled"),
        ("id", "title", "status", "version"),
        ("key", "name", "item_count"),
    ):
        if all(key in row for key in keys[:2]):
            return "  ".join(f"{key}={row.get(key)}" for key in keys if key in row)
    return json.dumps(row, ensure_ascii=False)


# ───────────────────────────── viewpoints ─────────────────────────────


def _cmd_viewpoints(args: argparse.Namespace) -> int:
    _ensure_web_importable()
    from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store

    store = get_viewpoint_store()
    as_json = bool(getattr(args, "json", False))
    try:
        return _dispatch_viewpoints(store, args, as_json)
    except ViewpointStoreError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"エラー: ファイルが見つかりません: {exc}", file=sys.stderr)
        return 1


def _dispatch_viewpoints(store: Any, args: argparse.Namespace, as_json: bool) -> int:
    action = args.vp_action
    if action == "sets":
        _emit(store.list_sets(include_deleted=bool(getattr(args, "include_deleted", False))), as_json=as_json)
        return 0
    if action == "show":
        _emit(store.get_set(args.set_id), as_json=as_json)
        return 0
    if action == "versions":
        _emit(store.list_versions(args.set_id), as_json=as_json)
        return 0
    if action == "items":
        _emit(store.list_items(args.set_id, args.version), as_json=as_json)
        return 0
    if action == "diff":
        _emit(store.version_diff(args.set_id, args.from_version, args.to_version), as_json=True)
        return 0
    if action == "export":
        csv_text = store.export_csv(args.set_id, args.version)
        if args.output:
            Path(args.output).write_text(csv_text, encoding="utf-8")
            print(f"エクスポートしました: {args.output}")
        else:
            sys.stdout.write(csv_text)
        return 0
    if action == "import":
        text = Path(args.csv_file).read_text(encoding="utf-8")
        result = store.import_csv(args.set_id, text)
        _emit(result, as_json=True)
        return 0
    if action == "publish":
        result = store.publish(
            args.set_id,
            args.version,
            revision=args.revision,
            change_reason=args.reason or "",
        )
        _emit(result, as_json=True)
        return 0
    if action == "rollback":
        result = store.rollback(args.set_id, args.version, args.reason or "")
        _emit(result, as_json=True)
        return 0
    if action == "templates":
        from web.services.viewpoint_templates import list_templates

        _emit(list_templates(), as_json=as_json)
        return 0
    if action == "apply-template":
        from web.services.viewpoint_templates import apply_template

        _emit(apply_template(args.set_id, args.template_key), as_json=True)
        return 0
    if action == "create-set":
        payload = {"name": args.name}
        if args.description:
            payload["description"] = args.description
        _emit(store.create_set(payload), as_json=True)
        return 0
    print(f"未知の viewpoints サブコマンド: {action}", file=sys.stderr)
    return 2


# ─────────────────────────────── review ───────────────────────────────


def _load_candidates(out_dir: Path, domain: str) -> list[dict]:
    """候補 JSON を寛容に読み込む（ドメイン直下→qa_process の順・形式差を吸収）。

    review 機能は `output/<domain>/playwright_candidates.json`（リスト形式）を
    前提とするが、QA 生成は `output/<domain>/qa_process/playwright_candidates.json`
    （{"candidates":[...]} 形式）へ書き出す。CLI では両経路・両形式を吸収する。
    """
    for path in (
        out_dir / domain / "playwright_candidates.json",
        out_dir / domain / "qa_process" / "playwright_candidates.json",
    ):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return list(data.get("candidates", []))
        if isinstance(data, list):
            return data
    return []


def _cmd_review(args: argparse.Namespace) -> int:
    _ensure_web_importable()
    from web.routes import review as review_mod
    from web.validation import _valid_domain

    if args.output:
        review_mod.OUTPUT_DIR = Path(args.output)
    out_dir = Path(args.output) if args.output else review_mod.OUTPUT_DIR

    domain = str(args.domain).strip()
    if not _valid_domain(domain):
        print(f"エラー: 不正なドメインです: {domain}", file=sys.stderr)
        return 1

    action = args.review_action
    candidates = _load_candidates(out_dir, domain)
    state = review_mod._load_review_state(domain)
    as_json = bool(getattr(args, "json", False))

    if action == "cases":
        cases = review_mod._merge_candidates_with_state(candidates, state)
        _emit({"domain": domain, "cases": cases} if as_json else cases, as_json=as_json)
        return 0

    if action == "export":
        all_cases = review_mod._merge_candidates_with_state(candidates, state)
        if args.filter == "approved":
            all_cases = [c for c in all_cases if c["status"] in ("approved", "frozen")]
        payload = {"domain": domain, "exported_count": len(all_cases), "cases": all_cases}
        if args.export_file:
            Path(args.export_file).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"エクスポートしました: {args.export_file}（{len(all_cases)}件）")
        else:
            _emit(payload, as_json=True)
        return 0

    if action == "update":
        valid = review_mod._VALID_STATUSES
        if args.status not in valid:
            print(f"エラー: 不正な status: {args.status}（{sorted(valid)}）", file=sys.stderr)
            return 1
        lock = review_mod._get_review_lock(domain)
        with lock:
            state = review_mod._load_review_state(domain)
            cases: dict = state.setdefault("cases", {})
            existing = cases.get(args.case_id, {})
            prev_version = existing.get("version", 1)
            new_version = prev_version + 1 if args.status == "frozen" else prev_version
            cases[args.case_id] = {
                "status": args.status,
                "comment": args.comment or "",
                "version": new_version,
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            }
            state["domain"] = domain
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            review_mod._save_review_state(domain, state)
        _emit(
            {"ok": True, "case_id": args.case_id, "status": args.status, "version": new_version},
            as_json=True,
        )
        return 0

    print(f"未知の review サブコマンド: {action}", file=sys.stderr)
    return 2


# ─────────────────────────────── parser ───────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli_manage",
        description="WebSpec2Doc 管理 CLI（観点セット管理・テストケースレビュー）",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    vp = sub.add_parser("viewpoints", help="観点セット管理")
    vp.add_argument("--json", action="store_true", help="結果を JSON で出力")
    vp_sub = vp.add_subparsers(dest="vp_action", required=True)

    p = vp_sub.add_parser("sets", help="観点セット一覧")
    p.add_argument("--include-deleted", action="store_true")
    vp_sub.add_parser("show", help="観点セット詳細").add_argument("set_id")
    vp_sub.add_parser("versions", help="版一覧").add_argument("set_id")

    p = vp_sub.add_parser("items", help="観点項目一覧")
    p.add_argument("set_id")
    p.add_argument("--version", type=int, default=None, help="版番号（未指定は既定）")

    p = vp_sub.add_parser("diff", help="版間差分")
    p.add_argument("set_id")
    p.add_argument("--from", dest="from_version", type=int, required=True)
    p.add_argument("--to", dest="to_version", type=int, required=True)

    p = vp_sub.add_parser("export", help="CSV エクスポート")
    p.add_argument("set_id")
    p.add_argument("--version", type=int, default=None)
    p.add_argument("-o", "--output", default="", help="出力先ファイル（未指定は標準出力）")

    p = vp_sub.add_parser("import", help="CSV インポート（新規 draft 版を作成）")
    p.add_argument("set_id")
    p.add_argument("csv_file")

    p = vp_sub.add_parser("publish", help="版を公開")
    p.add_argument("set_id")
    p.add_argument("version", type=int)
    p.add_argument("--reason", default="", help="変更理由")
    p.add_argument("--revision", type=int, default=None, help="楽観ロック用リビジョン（省略可）")

    p = vp_sub.add_parser("rollback", help="公開履歴のある版へロールバック")
    p.add_argument("set_id")
    p.add_argument("version", type=int)
    p.add_argument("--reason", default="")

    vp_sub.add_parser("templates", help="観点テンプレート一覧")
    p = vp_sub.add_parser("apply-template", help="テンプレートを適用")
    p.add_argument("set_id")
    p.add_argument("template_key")

    p = vp_sub.add_parser("create-set", help="観点セットを新規作成")
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")

    vp.set_defaults(func=_cmd_viewpoints)

    rv = sub.add_parser("review", help="テストケースレビュー")
    rv.add_argument("--json", action="store_true", help="結果を JSON で出力")
    rv.add_argument("--output", default="", help="出力ルート（既定 output/）")
    rv_sub = rv.add_subparsers(dest="review_action", required=True)

    rv_sub.add_parser("cases", help="レビュー対象ケース一覧").add_argument("domain")

    p = rv_sub.add_parser("update", help="ケースのレビュー状態を更新")
    p.add_argument("domain")
    p.add_argument("case_id")
    p.add_argument(
        "--status", required=True, help="draft/reviewing/approved/frozen"
    )
    p.add_argument("--comment", default="")

    p = rv_sub.add_parser("export", help="レビュー結果をエクスポート")
    p.add_argument("domain")
    p.add_argument("--filter", default="all", choices=("all", "approved"))
    p.add_argument("-o", "--export-file", default="", help="出力先ファイル（未指定は標準出力）")

    rv.set_defaults(func=_cmd_review)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
