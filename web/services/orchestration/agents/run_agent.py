"""03 AutoRun を指揮者から呼ぶためのアダプタ（テスト実行）。

02 が作ったテストを回して、通ったか落ちたかを返すだけ。実行そのものは
playwright_executor が持っており、ここは呼び方を monitor.py::run_now に
揃える以上のことをしない。同じ実行を 2 通りの呼び方で持つと、
結果の置き場所がずれて「実行結果」画面から見えなくなる。

同期で終わるが handle は返す。中身は結果ファイル（out_dir からの相対パス）と
その更新時刻で、status() は指定されたファイルだけを読み、更新時刻が合わなければ
「あとの実行に上書きされた」と答える。「そのドメインの最新の結果」を返す作りだと、
同じドメインで 2 回目を回した後に 1 回目の handle で追いかけたとき、
無関係な結果を「その実行の結果」として返してしまう。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.services.orchestration.ports import (
    Context,
    Readiness,
    StepResult,
    StepStatus,
)

#: 回すテストファイル。02 が作ったものを優先し、無ければ 03 のものを使う。
#: monitor.py::_spec_path と同じ順序。
_SPEC_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("testcases", "testcases.spec.ts"),
    ("qa_process", "autorun.spec.ts"),
)

_NO_SPEC = "02 テスト自動化でこのサイトのテストを作ってください"
_NO_HANDLE = "実行の記録がありません"
_NO_TESTS = "テストが 1 件も実行されませんでした。テストファイルを確認してください"
_UNREADABLE = "テスト結果を読めませんでした（{path}）"


def _spec_path(out_dir: Path, domain: str) -> Path | None:
    for parts in _SPEC_CANDIDATES:
        candidate = out_dir / domain / Path(*parts)
        if candidate.is_file():
            return candidate
    return None


def _report_relpath(domain: str) -> str:
    """結果ファイルの out_dir からの相対パス。画面もこのファイルを読む。"""
    return f"{domain}/qa_process/playwright_report.json"


#: handle の中で「どの実行か」を表す部分の区切り。
_HANDLE_SEP = "@"

#: 追いかけている実行の結果が、あとの実行に上書きされていたときの説明。
_OVERWRITTEN = "この実行の結果は、あとの実行に上書きされました。最新の結果を見てください"


def _make_handle(domain: str, report_path: Path) -> str:
    """結果ファイルの相対パスに、その時点の更新時刻を添えたもの。

    同じサイトの結果は毎回同じファイルへ上書きされる。パスだけを handle に
    すると、2 回目を回したあとに 1 回目の handle で status() を追いかけたとき、
    別の実行の結果を「その実行の結果」として返してしまう（実測で確認済み）。
    更新時刻を添えておき、合わなければ「上書きされた」と正直に言う。
    """
    relative = _report_relpath(domain)
    try:
        return f"{relative}{_HANDLE_SEP}{report_path.stat().st_mtime_ns}"
    except OSError:
        return relative


def _split_handle(handle: str) -> tuple[str, int | None]:
    """handle を (相対パス, 実行を表す更新時刻) に分ける。

    更新時刻が付いていない handle（artifacts["report"] のパスそのもの）も
    受け付ける。その場合は「どの実行か」を問わず、今ある結果を読む。
    """
    text = str(handle or "").strip()
    path, sep, stamp = text.rpartition(_HANDLE_SEP)
    if not sep or not stamp.isdigit():
        return text, None
    return path, int(stamp)


def _resolve_report(out_dir: Path, handle: str) -> Path | None:
    """handle（out_dir からの相対パス）を実ファイルへ解決する。

    絶対パスや上位への参照は受け付けない。handle は外から渡ってくる文字列で、
    そのまま結合すると out_dir の外を読ませられる。
    """
    text = str(handle or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return out_dir / candidate


def _read_report(report_path: Path) -> tuple[dict[str, Any] | None, str]:
    """保存された結果を読む。読めなければ (None, 人が読む理由)。

    「読めなかった」を 0 件として返してはいけない。0 件は「全部通った」と
    同じ形になり、結果が壊れている事実が消える（実測で、壊れた JSON を
    「0 件中 0 件失敗・succeeded」と報告していた）。
    """
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # JSONDecodeError は ValueError の一種
        return None, _UNREADABLE.format(path=report_path)
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        return None, _UNREADABLE.format(path=report_path)
    return data, ""


def _report_data(result: Any, report_path: Path) -> tuple[dict[str, Any] | None, str]:
    """実行の戻り値を優先し、壊れていたら保存された JSON を読み直す。"""
    if isinstance(result, dict) and isinstance(result.get("tests"), list):
        return result, ""
    return _read_report(report_path)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _judge(data: dict[str, Any]) -> tuple[str, str, str]:
    """読めた結果から (状態, 人が読む 1 文, エラー) を決める。

    run() と status() が別々の判断を持つと、同じ結果ファイルに対して
    片方だけが失敗を見つける（実際に status() 側にだけ防御が無かった）。
    """
    error = str(data.get("error") or "")
    tests = data.get("tests") or []
    total = _int(data.get("total")) or len(tests)
    failed = _int(data.get("failed"))
    if total == 0:
        # 0 件を succeeded にすると「テストが 1 件も無い」と「全部通った」が
        # 同じ報告になる。前者はテストが壊れている合図なので、区別して失敗にする。
        if error:
            return "failed", "実行結果を読み取れませんでした", error
        return "failed", _NO_TESTS, _NO_TESTS
    return "succeeded", f"{total} 件中 {failed} 件失敗", error


class RunAgent:
    """03: 作ってあるテストを 1 回まわす。"""

    name = "run"
    label = "テスト実行"

    def ready(self, ctx: Context) -> Readiness:
        spec = _spec_path(ctx.out_dir, ctx.domain)
        if spec is None:
            return Readiness(
                ok=False,
                human_action=_NO_SPEC,
                detail=f"{ctx.domain} に回せるテストがありません",
            )
        return Readiness(ok=True, detail=f"テスト: {spec.name}")

    def run(self, ctx: Context) -> StepResult:
        spec = _spec_path(ctx.out_dir, ctx.domain)
        if spec is None:
            return StepResult(
                status="waiting_human", summary="回せるテストがありません",
                human_action=_NO_SPEC,
            )

        # 実行結果は 03 と同じ場所へ置く。画面の「実行結果」からも同じものが見える。
        from web.services.playwright_executor import run_playwright

        output_dir = ctx.out_dir / ctx.domain / "qa_process"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "playwright_report.json"
        ctx.log(f"テストを実行します（{spec.name}）")
        try:
            result = run_playwright(spec_path=spec, output_dir=output_dir)
        except Exception as exc:  # noqa: BLE001 - 例外は握らず結果として返す
            return StepResult(
                status="failed", summary="テストを実行できませんでした",
                error=f"テストの実行に失敗しました: {exc}",
            )

        data, read_error = _report_data(result, report_path)
        if data is None:
            return StepResult(
                status="failed", summary="テスト結果を読めませんでした", error=read_error,
                artifacts=self._artifacts(ctx, report_path),
                evidence=self._evidence(output_dir),
                handle=self._handle(ctx, report_path),
            )

        state, summary, error = _judge(data)
        ctx.log(summary)
        return StepResult(
            status=state,
            summary=summary,
            artifacts=self._artifacts(ctx, report_path),
            evidence=self._evidence(output_dir),
            handle=self._handle(ctx, report_path),
            error=error,
        )

    def status(self, ctx: Context, handle: str) -> StepStatus:
        """handle が指す結果ファイルを読んで返す（同期なので保存済みが全て）。"""
        relative, stamp = _split_handle(handle)
        report_path = _resolve_report(ctx.out_dir, relative)
        if report_path is None or not report_path.is_file():
            return StepStatus(
                state="failed", label="実行の記録なし",
                summary=_NO_HANDLE, error=_NO_HANDLE,
            )
        if stamp is not None and report_path.stat().st_mtime_ns != stamp:
            # 別の実行が同じファイルへ上書きした。最新の結果を、指定された
            # 実行の結果として返すと、無関係な成否を報告することになる。
            return StepStatus(
                state="failed", label="結果が残っていません",
                summary=_OVERWRITTEN, error=_OVERWRITTEN,
                artifacts={"report": relative},
            )
        data, read_error = _read_report(report_path)
        if data is None:
            return StepStatus(
                state="failed", label="結果を読めません",
                summary="テスト結果を読めませんでした", error=read_error,
                artifacts={"report": relative},
            )
        state, summary, error = _judge(data)
        return StepStatus(
            state=state,
            label="テスト実行 完了" if state == "succeeded" else "テスト実行 失敗",
            summary=summary,
            artifacts={"report": relative},
            error=error,
        )

    def _handle(self, ctx: Context, report_path: Path) -> str:
        """status() で追うための handle。結果ファイルが無ければ空。"""
        return _make_handle(ctx.domain, report_path) if report_path.is_file() else ""

    def _artifacts(self, ctx: Context, report_path: Path) -> dict[str, str]:
        if not report_path.is_file():
            return {}
        return {"report": _report_relpath(ctx.domain)}

    def _evidence(self, output_dir: Path) -> tuple[str, ...]:
        results_dir = output_dir / "test-results"
        return (str(results_dir),) if results_dir.is_dir() else ()
