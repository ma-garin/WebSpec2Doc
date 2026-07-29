#!/usr/bin/env python3
"""WebSpec2Doc CLI モード（画面なし）。

GUI の 3 系統をそのまま端末から使うための入口。

    python src/cli.py doc       --url https://example.com    # 01 ドキュメント作成
    python src/cli.py autorun   --url https://example.com    # 02 AutoRun（全自動）
    python src/cli.py test      --domain example.com         # テストケース実行
    python src/cli.py sites                                   # 解析済みサイト一覧
    python src/cli.py show      --domain example.com         # 成果物の場所と要約
    python src/cli.py viewpoints                              # 観点セット一覧

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


def cmd_test(args: argparse.Namespace, _extra: list[str]) -> int:
    from web.services.cli_runner import run_testcases

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
    """観点セットの一覧（GUI の観点管理に相当）。"""
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

    d = sub.add_parser(
        "doc", parents=[common], help="01 ドキュメント作成（クロールして仕様書を生成）"
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

    v = sub.add_parser("viewpoints", parents=[common], help="観点セットの一覧")
    v.set_defaults(func=cmd_viewpoints)

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
