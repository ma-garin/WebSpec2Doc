"""端末から指揮者（O2）を回す入口。04「CLI・API」の一部。

    python -m web.services.cli_orchestration orchestrate \\
        --domain 127.0.0.1:8765 --goal daily --project-id P001

画面と同じ 1 本の流れ（目標 → 段の列）を端末から起こすためだけの薄い層で、
段の並びも進め方も持たない。持つのは「起こす・見る・人に見える形で出す」だけ。

**この入口は必ず終端まで待つ。**指揮者は段をスレッドで進めるので、待たずに
戻ると CLI プロセスの終了と一緒にそのスレッドが消え、実行は非終端の状態のまま
永続化されて残る（05 の場合、その接続先は「まだ動いている」と見え続け、
次の実行が二度と起きなくなる）。だから「待たない」選択肢は用意しない。
待てる上限だけを --timeout-sec で決める。

終了コード:
    0    すべての段が終わった（succeeded / skipped）
    1    段が失敗した・中止された（failed / cancelled）
    2    人の判断待ちで止まった（waiting_human）
    3    指定が誤っている・いま起こせない（引数エラー・前の実行が動いている）
    130  --timeout-sec を過ぎても終わらなかった
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from web.config import OUTPUT_DIR
from web.services.orchestration import conductor, goals
from web.services.orchestration.run_store import ConductorRun

#: 記録に残る出どころ。監視は "monitor"、画面は利用者名を使う。
ACTOR = "cli"

#: 指揮者を見に行く間隔（秒）と、待てる上限の既定。
POLL_INTERVAL_SEC = 10
DEFAULT_TIMEOUT_SEC = 7200

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WAITING_HUMAN = 2
EXIT_USAGE = 3
EXIT_TIMEOUT = 130

#: 実行の結末 → 終了コード。ここに無い状態で終わることはない（TERMINAL_STATUSES）。
_EXIT_BY_STATUS: dict[str, int] = {
    "succeeded": EXIT_OK,
    "skipped": EXIT_OK,
    "waiting_human": EXIT_WAITING_HUMAN,
    "failed": EXIT_FAILED,
    "cancelled": EXIT_FAILED,
}

#: 状態を人が読む 1 文にする。内部用語（run / step / handle）は出さない。
_STATUS_TEXT: dict[str, str] = {
    "queued": "受付しました",
    "running": "実行中",
    "succeeded": "終わりました",
    "skipped": "やることがありませんでした",
    "waiting_human": "人の判断待ちです",
    "failed": "失敗しました",
    "cancelled": "中止しました",
}

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_MAX_URL_LEN = 2000


# ─────────────────────────────────────────────────────────────────────────
# 出力
# ─────────────────────────────────────────────────────────────────────────


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _emit(message: str) -> None:
    print(f"[{_stamp()}] {message}", flush=True)


def _fail(message: str) -> None:
    """人が直せることだけを書く。標準エラーへ出し、標準出力の行と混ぜない。"""
    print(f"[{_stamp()}] {message}", file=sys.stderr, flush=True)


# ─────────────────────────────────────────────────────────────────────────
# 引数
# ─────────────────────────────────────────────────────────────────────────


class _Parser(argparse.ArgumentParser):
    """引数の誤りを 3 で返す。既定の 2 は「人の判断待ち」に使っているため。"""

    def error(self, message: str) -> Any:  # noqa: D102 - argparse の契約に従う
        self.print_usage(sys.stderr)
        _fail(f"引数の指定が誤っています: {message}")
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m web.services.cli_orchestration",
        description="1 本の流れ（目標）を端末から起こし、終わるまで待つ",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("orchestrate", help="目標を 1 本起こして終端まで待つ")
    run.add_argument("--domain", required=True, help="対象サイト（例: 127.0.0.1:8765）")
    run.add_argument(
        "--goal",
        default="daily",
        help="目標。使えるのは " + "・".join(sorted(goals.GOALS)) + "（既定: daily）",
    )
    run.add_argument("--project-id", default="", help="05 の接続先 ID（省略時はサイトで探す）")
    run.add_argument("--out-dir", default=str(OUTPUT_DIR), help="出力ルート（既定: output）")
    run.add_argument("--url", default="", help="観測の起点 URL（保守下に置く場合）")
    run.add_argument("--depth", type=int, default=None, help="観測の深さ 1〜3")
    run.add_argument("--max-pages", type=int, default=None, help="観測する画面数 1〜50")
    run.add_argument(
        "--timeout-sec",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"待てる上限（秒・既定: {DEFAULT_TIMEOUT_SEC}）",
    )
    return parser


def _params(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    """段へ渡す材料を検証する。合格した材料と、不合格なら理由（日本語）を返す。

    範囲は API（web/routes/orchestration.py）と揃える。入口ごとに違う範囲を
    許すと、画面では断られた指定が端末からは通る、という穴になる。
    """
    params: dict[str, Any] = {}
    url = str(args.url or "").strip()
    if url:
        if not _URL_RE.match(url) or len(url) > _MAX_URL_LEN:
            return {}, "--url は http:// か https:// で始まる 2000 字以内で指定してください"
        params["url"] = url
    if args.depth is not None:
        if not 1 <= args.depth <= 3:
            return {}, "--depth は 1〜3 の整数で指定してください"
        params["depth"] = args.depth
    if args.max_pages is not None:
        if not 1 <= args.max_pages <= 50:
            return {}, "--max-pages は 1〜50 の整数で指定してください"
        params["max_pages"] = args.max_pages
    return params, ""


# ─────────────────────────────────────────────────────────────────────────
# 実行
# ─────────────────────────────────────────────────────────────────────────


def _emit_steps(run: ConductorRun, seen: dict[str, str]) -> None:
    """前に出したときから変わった段だけを 1 行ずつ出す。

    まだ始まっていない段（queued）は出さない。段の並びは受付の 1 行で
    先に見せているので、同じことを毎段くり返すと本当の変化が埋もれる。
    """
    for record in run.steps:
        status = str(getattr(record, "status", "") or "")
        name = str(getattr(record, "name", "") or "")
        if not status or status == "queued" or seen.get(name) == status:
            continue
        seen[name] = status
        detail = (
            str(getattr(record, "summary", "") or "")
            or str(getattr(record, "error", "") or "")
            or _STATUS_TEXT.get(status, status)
        )
        _emit(f"{getattr(record, 'label', '') or name}: {detail}")


def _report(run: ConductorRun) -> int:
    """結末を人が読む形で出し、終了コードを返す。"""
    status = str(run.status or "")
    _emit(f"結果: {_STATUS_TEXT.get(status, status)}（{run.run_id}）")
    if run.human_action:
        _emit(f"やること: {run.human_action}")
    if run.error:
        _fail(f"エラー: {run.error}")
    return _EXIT_BY_STATUS.get(status, EXIT_FAILED)


def _follow(out_dir: Path, run_id: str, timeout_sec: int) -> int:
    """終端まで見続ける。段が変わるたびに 1 行出す。"""
    deadline = time.monotonic() + max(int(timeout_sec), 1)
    seen: dict[str, str] = {}
    while True:
        run = conductor.get(out_dir, run_id)
        if run is None:
            _fail(f"起こした指揮 {run_id} を見失いました")
            return EXIT_FAILED
        _emit_steps(run, seen)
        if str(run.status or "") in conductor.TERMINAL_STATUSES:
            return _report(run)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _fail(
                f"{timeout_sec} 秒で終わりませんでした。"
                "この入口が終わると指揮も止まります。"
                "--timeout-sec を延ばすか、画面から実行してください"
            )
            return EXIT_TIMEOUT
        time.sleep(min(POLL_INTERVAL_SEC, remaining))


def orchestrate(args: argparse.Namespace) -> int:
    params, params_error = _params(args)
    if params_error:
        _fail(params_error)
        return EXIT_USAGE

    domain = str(args.domain or "").strip()
    out_dir = Path(args.out_dir)
    try:
        # 確認と開始が一体になった関数で起こす。監視・画面・端末は別々に
        # 走るので、確認と開始が分かれていると同じサイトの指揮が二重に立つ。
        run = conductor.start_if_idle(
            out_dir=out_dir,
            domain=domain,
            goal=str(args.goal or "").strip(),
            project_id=str(args.project_id or "").strip(),
            actor=ACTOR,
            params=params,
        )
    except ValueError as exc:  # 目標・サイトの指定誤り。日本語のまま出す
        _fail(str(exc))
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - 落とさず、直せる形にして返す
        _fail(f"指揮を始められませんでした: {exc}")
        return EXIT_FAILED

    if run is None:
        _fail(
            f"{domain} は前の実行がまだ終わっていません。"
            "終わってからもう一度実行してください"
        )
        return EXIT_USAGE

    label = goals.GOAL_LABELS.get(run.goal, run.goal)
    plan = " → ".join(str(getattr(s, "label", "") or s.name) for s in run.steps)
    _emit(f"受付しました（目標: {label} / {run.run_id}）")
    _emit(f"段: {plan}")
    return _follow(out_dir, run.run_id, int(args.timeout_sec))


_COMMANDS: Mapping[str, Any] = {"orchestrate": orchestrate}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return int(_COMMANDS[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
