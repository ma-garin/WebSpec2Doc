#!/usr/bin/env python3
"""WebSpec2Doc CLI モード（画面なし）。

GUI の 3 系統をそのまま端末から使うための入口。

    python src/cli.py doc       --url https://example.com    # 01 ドキュメント作成
    python src/cli.py autorun   --url https://example.com    # 02 AutoRun（全自動）
    python src/cli.py test      --domain example.com         # テストケース実行
    python src/cli.py sites                                   # 解析済みサイト一覧
    python src/cli.py show      --domain example.com         # 成果物の場所と要約
    python src/cli.py viewpoints                              # 観点セット一覧
    python src/cli.py viewpoints export <set_id>              # 観点を CSV で持ち出す
    python src/cli.py review cases <domain>                   # レビュー対象の一覧

終了コードは自動化から判定できるように揃えてある。
    0   正常終了
    1   完了したが失敗を含む（テスト失敗・ドリフト検出）
    2   実行エラー
    130 中止（タイムアウト・シグナル）

GUI を起動する必要はない。CLI は Flask のリクエストコンテキストを使わない。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUTPUT = Path("output")


# ────────────────────────────── 表示 ──────────────────────────────


def _emit(payload: dict, as_json: bool) -> None:
    """人が読む形と機械が読む形を切り替える。既定は人が読む形。"""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in payload.get("_lines", []):
        print(line)


def _rule(title: str) -> str:
    return f"\n{title}\n" + "─" * max(20, len(title) * 2)


# ────────────────────────── 01 ドキュメント作成 ──────────────────────────


def cmd_doc(args: argparse.Namespace, extra: list[str]) -> int:
    """既存のクロール CLI（src/main.py）へそのまま委譲する。

    オプションを二重に定義すると本体と乖離するため、ここでは受け取った引数を
    そのまま渡す。`--help` も本体のものが出る。
    """
    import runpy

    argv = ["main.py"] + extra
    if args.url:
        argv += ["--url", args.url]
    if args.output:
        argv += ["--output", str(args.output)]
    old = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(ROOT / "src" / "main.py"), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = old
    return 0


# ────────────────────────────── 02 AutoRun ──────────────────────────────


def cmd_autorun(args: argparse.Namespace, _extra: list[str]) -> int:
    from web.services.cli_runner import run_autorun

    def on_log(line: str) -> None:
        if args.quiet:
            return
        # --json のときは標準出力を JSON だけにする。ログを混ぜると
        # そのままパイプで渡せず、自動化から読めなくなる（実行ログは標準エラーへ）。
        print(line, flush=True, file=sys.stderr if args.json else sys.stdout)

    result = run_autorun(
        args.url,
        output_dir=args.output,
        depth=args.depth,
        max_pages=args.max_pages,
        auth_path=args.auth or "",
        viewpoint_set_id=args.viewpoint_set or "",
        viewpoint_version=args.viewpoint_version,
        login_user=args.login_user or "",
        login_password=args.login_pass or "",
        login_skip=not args.require_login,
        approve=args.approve,
        timeout_sec=args.timeout,
        on_log=on_log,
    )

    lines = [
        _rule("AutoRun の結果"),
        f"  状態      : {result.status}",
        f"  対象      : {result.url}",
        f"  ドメイン  : {result.domain or '(未確定)'}",
        f"  所要      : {result.elapsed_sec} 秒",
    ]
    if result.error:
        lines.append(f"  エラー    : {result.error}")
    if result.auto_handled:
        lines.append("  自動で通した判断（人は確認していない）:")
        lines += [f"    - {x}" for x in result.auto_handled]
    if result.unverified:
        lines.append("  未確認として記録された項目:")
        lines += [f"    - {x}" for x in result.unverified]
    if result.domain:
        lines.append(f"  成果物    : {args.output / result.domain}")

    _emit(
        {
            "command": "autorun",
            "status": result.status,
            "ok": result.ok,
            "job_id": result.job_id,
            "url": result.url,
            "domain": result.domain,
            "elapsed_sec": result.elapsed_sec,
            "auto_handled": result.auto_handled,
            "unverified": result.unverified,
            "error": result.error,
            "_lines": lines,
        },
        args.json,
    )
    return result.exit_code()


# ────────────────────────────── テスト実行 ──────────────────────────────


def _reject_bad_domain(args: argparse.Namespace, command: str) -> int | None:
    """ドメイン名として扱えない指定を弾く。

    空文字は `output / ""` が出力先そのものを指してしまい、成果物が無いのに
    一覧が出て成功したように見える。パス区切りは出力先の外を指しうる。
    """
    raw = str(getattr(args, "domain", "") or "")
    bad = (not raw.strip()) or any(x in raw for x in ("/", "\\", "..")) or raw.startswith(".")
    if not bad:
        return None
    _emit(
        {
            "command": command,
            "error": "invalid domain",
            "_lines": [f"ドメイン名として扱えません: {raw!r}"],
        },
        args.json,
    )
    return 2


def cmd_test(args: argparse.Namespace, _extra: list[str]) -> int:
    from web.services.cli_runner import run_testcases

    rejected = _reject_bad_domain(args, "test")
    if rejected is not None:
        return rejected

    result = run_testcases(
        args.domain,
        output_dir=args.output,
        case_ids=args.case_id or None,
    )
    lines = [
        _rule("テスト実行の結果"),
        f"  対象      : {result.domain}",
        f"  合計      : {result.total} 件",
        f"  PASS      : {result.passed} 件",
        f"  FAIL      : {result.failed} 件",
        f"  SKIP      : {result.skipped} 件",
        f"  所要      : {result.duration_ms / 1000:.1f} 秒",
    ]
    if result.error:
        lines.append(f"  エラー    : {result.error}")
    _emit(
        {
            "command": "test",
            "ok": result.ok,
            "domain": result.domain,
            "total": result.total,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "duration_ms": result.duration_ms,
            "error": result.error,
            "_lines": lines,
        },
        args.json,
    )
    return result.exit_code()


# ────────────────────────────── 参照系 ──────────────────────────────


def cmd_sites(args: argparse.Namespace, _extra: list[str]) -> int:
    """解析済みサイトの一覧（GUI の解析履歴に相当）。"""
    out = args.output
    if not out.is_dir():
        _emit(
            {"command": "sites", "sites": [], "_lines": [f"出力先がありません: {out}"]}, args.json
        )
        return 0
    sites = []
    for d in sorted(p for p in out.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if d.name in {"tenants"}:
            continue
        report = d / "report.json"
        screens = fields = 0
        if report.is_file():
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
                screens = len(data.get("screens") or [])
                fields = sum(
                    len(f.get("fields") or [])
                    for s in (data.get("screens") or [])
                    for f in (s.get("forms") or [])
                )
            except (OSError, json.JSONDecodeError):
                pass
        snaps = len(list((d / "snapshots").glob("*.json"))) if (d / "snapshots").is_dir() else 0
        sites.append({"domain": d.name, "screens": screens, "fields": fields, "snapshots": snaps})

    lines = [
        _rule(f"解析済みサイト（{len(sites)} 件）"),
        f"  {'ドメイン':<34} {'画面':>5} {'項目':>5} {'履歴':>5}",
    ]
    lines += [
        f"  {s['domain']:<34} {s['screens']:>5} {s['fields']:>5} {s['snapshots']:>5}" for s in sites
    ]
    if not sites:
        lines.append("  （まだ解析していません）")
    _emit({"command": "sites", "sites": sites, "_lines": lines}, args.json)
    return 0


def cmd_show(args: argparse.Namespace, _extra: list[str]) -> int:
    """1 サイトの成果物の場所と要約（GUI のレポート概要に相当）。"""
    rejected = _reject_bad_domain(args, "show")
    if rejected is not None:
        return rejected
    d = args.output / args.domain
    if not d.is_dir():
        _emit(
            {"command": "show", "error": "not found", "_lines": [f"見つかりません: {d}"]}, args.json
        )
        return 2
    known = [
        ("report.html", "HTML レポート"),
        ("report.json", "JSON（機械可読）"),
        ("report.pdf", "PDF"),
        ("spec.xlsx", "Excel"),
        ("screens.md", "画面一覧（Markdown）"),
        ("forms.md", "フォーム（Markdown）"),
        ("transition.mmd", "遷移図（Mermaid）"),
        ("doc_fusion.md", "文書突合"),
        ("testcases/run_result.json", "テスト実行結果"),
    ]
    files = [{"path": str(d / n), "label": label, "exists": (d / n).exists()} for n, label in known]
    lines = [_rule(f"成果物: {args.domain}")]
    lines += [f"  {'✓' if f['exists'] else '—'} {f['label']:<24} {f['path']}" for f in files]

    run = d / "testcases" / "run_result.json"
    summary: dict = {}
    if run.is_file():
        try:
            summary = json.loads(run.read_text(encoding="utf-8")).get("summary") or {}
        except (OSError, json.JSONDecodeError):
            summary = {}
    if summary:
        lines.append(
            f"  テスト実行: PASS {summary.get('passed', 0)} / "
            f"FAIL {summary.get('failed', 0)} / 全 {summary.get('total', 0)} 件"
        )
    _emit(
        {
            "command": "show",
            "domain": args.domain,
            "files": files,
            "testcase_run": summary,
            "_lines": lines,
        },
        args.json,
    )
    return 0


def cmd_viewpoints(args: argparse.Namespace, _extra: list[str]) -> int:
    """観点セットの一覧と、版のライフサイクル操作（GUI の観点管理に相当）。

    アクション未指定は一覧。以前からの `python src/cli.py viewpoints` は
    そのまま一覧として動く。
    """
    action = getattr(args, "vp_action", "") or "list"
    if action != "list":
        return _viewpoints_action(args, action)

    from web.services.viewpoint_store import get_viewpoint_store

    try:
        sets = get_viewpoint_store().list_sets()
    except Exception as exc:  # noqa: BLE001  観点DBの例外型は複数ある
        _emit(
            {
                "command": "viewpoints",
                "error": str(exc),
                "_lines": [f"観点セットを取得できません: {exc}"],
            },
            args.json,
        )
        return 2
    items = [
        {
            "set_id": s.get("set_id") or s.get("id"),
            "name": s.get("name"),
            "published_version": s.get("published_version"),
            "viewpoint_count": s.get("viewpoint_count"),
        }
        for s in (sets or [])
    ]
    lines = [_rule(f"観点セット（{len(items)} 件）"), f"  {'名称':<38} {'公開版':>6} {'観点数':>6}"]
    lines += [
        f"  {str(i['name']):<38} {str(i['published_version'] or '—'):>6} "
        f"{str(i['viewpoint_count'] or '—'):>6}"
        for i in items
    ]
    _emit({"command": "viewpoints", "sets": items, "_lines": lines}, args.json)
    return 0


def _dump(payload: dict, as_json: bool, lines: list[str]) -> None:
    _emit({**payload, "_lines": lines}, as_json)


def _viewpoints_action(args: argparse.Namespace, action: str) -> int:
    """観点セットの版操作。GUI でしか行えなかった経路を端末から使えるようにする。"""
    from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store

    store = get_viewpoint_store()
    try:
        if action == "show":
            data = store.get_set(args.set_id)
            _dump({"command": "viewpoints show", "set": data}, args.json, [json_line(data)])
        elif action == "versions":
            rows = store.list_versions(args.set_id) or []
            _dump(
                {"command": "viewpoints versions", "versions": rows},
                args.json,
                [_rule(f"版（{len(rows)} 件）"), *[json_line(r) for r in rows]],
            )
        elif action == "items":
            rows = store.list_items(args.set_id, args.version) or []
            _dump(
                {"command": "viewpoints items", "items": rows},
                args.json,
                [_rule(f"観点項目（{len(rows)} 件）"), *[json_line(r) for r in rows]],
            )
        elif action == "diff":
            data = store.version_diff(args.set_id, args.from_version, args.to_version)
            _dump({"command": "viewpoints diff", "diff": data}, args.json, [json_line(data)])
        elif action == "export":
            csv_text = store.export_csv(args.set_id, args.version)
            if args.file:
                Path(args.file).write_text(csv_text, encoding="utf-8")
                _dump(
                    {"command": "viewpoints export", "file": str(args.file)},
                    args.json,
                    [f"エクスポートしました: {args.file}"],
                )
            else:
                # 標準出力へ流すときは CSV そのものを出す（--json は付けない前提）
                sys.stdout.write(csv_text)
        elif action == "import":
            path = Path(args.file)
            if not path.is_file():
                _dump(
                    {"command": "viewpoints import", "error": "file not found"},
                    args.json,
                    [f"ファイルが見つかりません: {path}"],
                )
                return 2
            data = store.import_csv(args.set_id, path.read_text(encoding="utf-8"))
            _dump({"command": "viewpoints import", "result": data}, args.json, [json_line(data)])
        elif action == "publish":
            data = store.publish(
                args.set_id, args.version, revision=args.revision, change_reason=args.reason
            )
            _dump({"command": "viewpoints publish", "result": data}, args.json, [json_line(data)])
        elif action == "rollback":
            data = store.rollback(args.set_id, args.version, args.reason)
            _dump({"command": "viewpoints rollback", "result": data}, args.json, [json_line(data)])
        elif action == "templates":
            from web.services.viewpoint_templates import list_templates

            rows = list_templates() or []
            _dump(
                {"command": "viewpoints templates", "templates": rows},
                args.json,
                [_rule(f"テンプレート（{len(rows)} 件）"), *[json_line(r) for r in rows]],
            )
        elif action == "apply-template":
            from web.services.viewpoint_templates import apply_template

            data = apply_template(args.set_id, args.template_key)
            _dump(
                {"command": "viewpoints apply-template", "result": data},
                args.json,
                [json_line(data)],
            )
        elif action == "create":
            payload = {"name": args.name}
            if args.description:
                payload["description"] = args.description
            data = store.create_set(payload)
            _dump({"command": "viewpoints create", "set": data}, args.json, [json_line(data)])
        else:  # pragma: no cover  argparse の choices で弾かれる
            _dump(
                {"command": "viewpoints", "error": f"unknown action: {action}"},
                args.json,
                [f"知らない操作です: {action}"],
            )
            return 2
    except ViewpointStoreError as exc:
        _dump(
            {"command": f"viewpoints {action}", "error": str(exc)},
            args.json,
            [f"観点セットを操作できません: {exc}"],
        )
        return 2
    except (OSError, ValueError, KeyError) as exc:
        _dump(
            {"command": f"viewpoints {action}", "error": str(exc)},
            args.json,
            [f"失敗しました: {exc}"],
        )
        return 2
    return 0


def json_line(row: object) -> str:
    """1 件を 1 行で読める形にする。列構成がまちまちなので JSON をそのまま出す。"""
    return "  " + json.dumps(row, ensure_ascii=False, default=str)


# ────────────────────────── テストケースレビュー ──────────────────────────


def _review_candidates(out_dir: Path, domain: str) -> list[dict]:
    """レビュー候補を読む。書き出し先が 2 箇所・形式が 2 通りあるため両方を吸収する。"""
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


def cmd_review(args: argparse.Namespace, _extra: list[str]) -> int:
    """テストケースのレビュー状態を端末から見る・更新する（GUI のレビューに相当）。"""
    from datetime import datetime

    from web.routes import review as review_mod

    rejected = _reject_bad_domain(args, "review")
    if rejected is not None:
        return rejected

    domain = str(args.domain).strip()
    out_dir = Path(args.output)
    review_mod.OUTPUT_DIR = out_dir

    action = args.review_action
    if action == "cases":
        cases = review_mod._merge_candidates_with_state(
            _review_candidates(out_dir, domain), review_mod._load_review_state(domain)
        )
        lines = [_rule(f"レビュー対象（{len(cases)} 件）"), *[json_line(c) for c in cases]]
        if not cases:
            lines = [
                _rule("レビュー対象（0 件）"),
                "  候補がありません。先に AutoRun か QA 生成を実行してください。",
            ]
        _emit(
            {"command": "review cases", "domain": domain, "cases": cases, "_lines": lines},
            args.json,
        )
        return 0

    if action == "export":
        cases = review_mod._merge_candidates_with_state(
            _review_candidates(out_dir, domain), review_mod._load_review_state(domain)
        )
        if args.filter == "approved":
            cases = [c for c in cases if c.get("status") in ("approved", "frozen")]
        payload = {"domain": domain, "exported_count": len(cases), "cases": cases}
        if args.file:
            Path(args.file).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _emit(
                {
                    "command": "review export",
                    **payload,
                    "file": str(args.file),
                    "_lines": [f"エクスポートしました: {args.file}（{len(cases)} 件）"],
                },
                args.json,
            )
        else:
            _emit(
                {"command": "review export", **payload, "_lines": [json_line(payload)]},
                args.json,
            )
        return 0

    # update
    if args.status not in review_mod._VALID_STATUSES:
        _emit(
            {
                "command": "review update",
                "error": "invalid status",
                "_lines": [
                    f"指定できない状態です: {args.status}"
                    f"（指定できるのは {', '.join(sorted(review_mod._VALID_STATUSES))}）"
                ],
            },
            args.json,
        )
        return 2

    with review_mod._get_review_lock(domain):
        state = review_mod._load_review_state(domain)
        cases_state: dict = state.setdefault("cases", {})
        prev = cases_state.get(args.case_id, {}).get("version", 1)
        # frozen は「この内容で確定した」印なので版を進める。それ以外は据え置く。
        version = prev + 1 if args.status == "frozen" else prev
        now = datetime.now().isoformat(timespec="seconds")
        cases_state[args.case_id] = {
            "status": args.status,
            "comment": args.comment or "",
            "version": version,
            "reviewed_at": now,
        }
        state["domain"] = domain
        state["updated_at"] = now
        review_mod._save_review_state(domain, state)

    _emit(
        {
            "command": "review update",
            "domain": domain,
            "case_id": args.case_id,
            "status": args.status,
            "version": version,
            "_lines": [f"{args.case_id} を {args.status} にしました（版 {version}）"],
        },
        args.json,
    )
    return 0


# ────────────────────────────── 引数 ──────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python src/cli.py",
        description="WebSpec2Doc CLI モード（画面なし）。GUI と同じ機能を端末から使う。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python src/cli.py doc --url https://example.com --format html,md,json\n"
            "  python src/cli.py autorun --url https://example.com --approve auto\n"
            "  python src/cli.py test --domain example.com\n"
            "  python src/cli.py sites\n"
            "  python src/cli.py show --domain example.com\n"
            "\n終了コード: 0=正常 / 1=失敗を含む完了 / 2=実行エラー / 130=中止\n"
        ),
    )
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="出力先（既定: output）")
    p.add_argument("--json", action="store_true", help="結果を JSON で出す（自動化向け）")

    # 共通オプションはサブコマンドの後ろに置くのが自然な書き方（`sites --json`）なので、
    # 各サブパーサでも受け取れるようにする。default=SUPPRESS にしておくと、
    # 指定が無いときにサブパーサ側の既定値が親の指定（`--json sites`）を上書きしない。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--output", type=Path, default=argparse.SUPPRESS, help="出力先（既定: output）"
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="結果を JSON で出す（自動化向け）",
    )

    sub = p.add_subparsers(dest="command", required=True)

    # doc は本体 CLI へ委譲するため、--help も本体のものを見せる。
    # add_help=False にしないと argparse がここで自前のヘルプを出して終わり、
    # 実際に使える --format / --compare / --auth などが一切分からなかった。
    d = sub.add_parser(
        "doc",
        parents=[common],
        add_help=False,
        help="01 ドキュメント作成（クロールして仕様書を生成）",
    )
    d.add_argument("--url", help="解析対象 URL")
    d.set_defaults(func=cmd_doc)

    a = sub.add_parser(
        "autorun", parents=[common], help="02 AutoRun（解析からテスト実行まで全自動）"
    )
    a.add_argument("--url", required=True, help="解析対象 URL")
    a.add_argument("--depth", type=int, default=2, help="リンクを追う深さ（既定 2）")
    a.add_argument("--max-pages", type=int, default=30, help="取得する画面数の上限（既定 30）")
    a.add_argument("--auth", default="", help="auth.json のパス（保存済みログインを使う）")
    a.add_argument("--viewpoint-set", default="", help="使う観点セット ID（既定は公開版）")
    a.add_argument("--viewpoint-version", type=int, default=None, help="観点セットの版番号")
    a.add_argument("--login-user", default="", help="ログインが要る場合のユーザー名")
    a.add_argument("--login-pass", default="", help="ログインが要る場合のパスワード")
    a.add_argument(
        "--require-login",
        action="store_true",
        help="ログインが必要なのに資格情報が無いとき、スキップせず中止する",
    )
    a.add_argument(
        "--approve",
        choices=["auto", "skip"],
        default="auto",
        help="段階承認の扱い（auto=内容を生成して承認 / skip=素通り）",
    )
    a.add_argument("--timeout", type=int, default=3600, help="全体の制限時間（秒・既定 3600）")
    a.add_argument("--quiet", action="store_true", help="実行ログを出さない")
    a.set_defaults(func=cmd_autorun)

    t = sub.add_parser("test", parents=[common], help="テストケース表から Playwright を実行する")
    t.add_argument("--domain", required=True, help="対象ドメイン（output 配下の名前）")
    t.add_argument("--case-id", action="append", help="実行するケース ID（複数指定可）")
    t.set_defaults(func=cmd_test)

    s = sub.add_parser("sites", parents=[common], help="解析済みサイトの一覧")
    s.set_defaults(func=cmd_sites)

    sh = sub.add_parser("show", parents=[common], help="1 サイトの成果物と要約")
    sh.add_argument("--domain", required=True, help="対象ドメイン")
    sh.set_defaults(func=cmd_show)

    v = sub.add_parser("viewpoints", parents=[common], help="観点セットの一覧と版の操作")
    v.set_defaults(func=cmd_viewpoints)
    vs = v.add_subparsers(dest="vp_action", metavar="操作")
    # 操作を省いたときは従来どおり一覧。argparse は set_defaults より
    # サブパーサの既定（None）を優先するため、アクション側に持たせる。
    vs.default = "list"
    vs.add_parser("show", parents=[common], help="1 セットの詳細").add_argument("set_id")
    vs.add_parser("versions", parents=[common], help="版の一覧").add_argument("set_id")

    vp = vs.add_parser("items", parents=[common], help="観点項目の一覧")
    vp.add_argument("set_id")
    vp.add_argument("--version", type=int, default=None, help="版番号（既定は公開版）")

    vp = vs.add_parser("diff", parents=[common], help="版どうしの差分")
    vp.add_argument("set_id")
    vp.add_argument("--from", dest="from_version", type=int, required=True)
    vp.add_argument("--to", dest="to_version", type=int, required=True)

    vp = vs.add_parser("export", parents=[common], help="CSV で書き出す")
    vp.add_argument("set_id")
    vp.add_argument("--version", type=int, default=None)
    vp.add_argument("--file", default="", help="書き出し先（省略で標準出力）")

    vp = vs.add_parser("import", parents=[common], help="CSV を読み込んで下書き版を作る")
    vp.add_argument("set_id")
    vp.add_argument("file", help="読み込む CSV")

    vp = vs.add_parser("publish", parents=[common], help="版を公開する")
    vp.add_argument("set_id")
    vp.add_argument("version", type=int)
    vp.add_argument("--reason", default="", help="変更理由")
    vp.add_argument("--revision", type=int, default=None, help="競合検知用のリビジョン")

    vp = vs.add_parser("rollback", parents=[common], help="公開済みの版へ戻す")
    vp.add_argument("set_id")
    vp.add_argument("version", type=int)
    vp.add_argument("--reason", default="")

    vs.add_parser("templates", parents=[common], help="テンプレートの一覧")
    vp = vs.add_parser("apply-template", parents=[common], help="テンプレートを適用する")
    vp.add_argument("set_id")
    vp.add_argument("template_key")

    vp = vs.add_parser("create", parents=[common], help="観点セットを新規作成する")
    vp.add_argument("--name", required=True)
    vp.add_argument("--description", default="")

    r = sub.add_parser("review", parents=[common], help="テストケースのレビュー状態")
    r.set_defaults(func=cmd_review)
    rs = r.add_subparsers(dest="review_action", metavar="操作", required=True)
    rs.add_parser("cases", parents=[common], help="レビュー対象の一覧").add_argument("domain")

    rp = rs.add_parser("update", parents=[common], help="1 ケースの状態を更新する")
    rp.add_argument("domain")
    rp.add_argument("case_id")
    rp.add_argument(
        "--status", required=True, help="draft / reviewing / approved / frozen のいずれか"
    )
    rp.add_argument("--comment", default="")

    rp = rs.add_parser("export", parents=[common], help="レビュー結果を書き出す")
    rp.add_argument("domain")
    rp.add_argument("--filter", default="all", choices=("all", "approved"))
    rp.add_argument("--file", default="", help="書き出し先（省略で標準出力）")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    # doc は本体 CLI へ委譲するため、未知のオプションはそのまま渡す。
    # それ以外のサブコマンドで未知のオプションを黙って捨てると、指定した条件が
    # 効いていないのに成功したように見えるため、明示的に弾く。
    if extra and args.command != "doc":
        parser.error(f"知らないオプションです: {' '.join(extra)}")
    try:
        return int(args.func(args, extra))
    except KeyboardInterrupt:
        print("\n中止しました。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    os.environ.setdefault("WEBSPEC2DOC_CLI", "1")
    sys.exit(main())
