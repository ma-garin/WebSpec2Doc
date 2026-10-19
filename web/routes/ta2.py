"""テスト自動化（System 02 / TA2）の API。

契約は `docs/plans/ta2/ta2-contract.md` §3。ここはルーティングと入出力の整形だけを持ち、
永続化と導出ロジックは `web/services/ta2_store.py` に委ねる（契約 §1）。

方針:
- すべて JSON。エラーは `{"error": "<日本語の理由>"}` と 4xx。500 は返さない。
- 実行（run）は非同期。スレッドで Playwright を走らせ、進捗は既存の
  `playwright_progress.ndjson` を読む（テストケース表の実行と同じ仕組み）。
"""

from __future__ import annotations

import functools
import json
import logging
import re
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, request, send_file

from crawler.url_safety import _local_targets_allowed
from web.config import OUTPUT_DIR
from web.process import _RUNNING_PROCS, _terminate_proc
from web.services.egress_gateway import EgressPolicy
from web.services.playwright_executor import _read_progress_ndjson, run_playwright
from web.services.testcase_spec_generator import SpecGenerationError, generate_spec
from web.services.testcase_table_store import load_run_result, run_dir
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

try:  # BE-A が並行実装中。未配置でもアプリ全体が落ちないようにする
    from web.services import ta2_store as store
except Exception:  # noqa: BLE001 - 取り込み失敗の理由は API 応答で返す
    store = None  # type: ignore[assignment]

try:  # ストアが送出する業務エラー（利用者に見せる日本語の理由を持つ）
    from web.services.ta2_store import Ta2StoreError
except Exception:  # noqa: BLE001

    class Ta2StoreError(ValueError):  # type: ignore[no-redef]
        """ta2_store を読み込めないときの代替。"""

logger = logging.getLogger(__name__)

bp = Blueprint("ta2", __name__)

# domain → {run_id, thread, started, total, cancelled, ids, out_dir}
_RUNS: dict[str, dict[str, Any]] = {}

_SCREEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ARTIFACT_KINDS = ("trace", "screenshot", "report")
_NO_BASELINE = "比較の基準となる前回のクロールがありません"
_NO_ARTIFACT = "この実行の証跡はありません"
_GENERIC_ERROR = "処理に失敗しました。サーバーのログを確認してください。"
# 内部メッセージを利用者へ漏らさないための判定（日本語を含むものだけそのまま見せる）
_JA_RE = re.compile(r"[ぁ-んァ-ヶ一-龥]")


def _reason_of(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message and _JA_RE.search(message) else _GENERIC_ERROR


class Ta2Error(ValueError):
    """利用者に見せる日本語の理由と HTTP ステータスを持つエラー。"""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    """例外を 4xx の JSON に畳む。500 を返さないための最後の壁。"""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Ta2Error as exc:
            return {"error": str(exc)}, exc.status
        except SpecGenerationError as exc:
            return {"error": str(exc)}, 400
        except Ta2StoreError as exc:
            # ストアの業務エラーは理由がそのまま利用者向けの文言（検証 B-2）
            logger.info("TA2 API: %s: %s", request.path, exc)
            return {"error": _reason_of(exc)}, 400
        except ValueError as exc:
            logger.warning("TA2 API で入力エラー: %s", request.path, exc_info=True)
            return {"error": _reason_of(exc)}, 400
        except Exception:  # noqa: BLE001
            logger.exception("TA2 API でエラーが発生しました: %s", request.path)
            return {"error": _GENERIC_ERROR}, 400

    return wrapper


def _store() -> Any:
    if store is None:
        raise Ta2Error("テスト定義の保存モジュール（ta2_store）が読み込めません", 400)
    return store


def _out() -> Path:
    return scoped_output_dir(OUTPUT_DIR)


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _domain() -> str:
    body = _body()
    raw = request.args.get("domain") or request.form.get("domain") or body.get("domain") or ""
    domain = str(raw).strip()
    if not _valid_domain(domain):
        raise Ta2Error("domain が不正です", 400)
    return domain


def _report(domain: str) -> dict[str, Any]:
    path = _out() / domain / "report.json"
    if not path.is_file():
        raise Ta2Error("このサイトの解析結果（report.json）がありません", 404)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Ta2Error("report.json を読み取れません", 400) from exc
    if not isinstance(data, dict):
        raise Ta2Error("report.json の形式が不正です", 400)
    return data


def _split_fix(result: Any) -> tuple[dict[str, Any] | None, str]:
    """`apply_fix` の戻り `(test, reason|None)` を畳む（旧実装の test 単体も受ける）。"""
    if isinstance(result, tuple):
        test = result[0] if result else None
        reason = str(result[1] or "") if len(result) > 1 else ""
    else:
        test, reason = result, ""
    return (test if isinstance(test, dict) else None), reason


def _split_rows(result: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """`to_table_rows` の戻り `(rows, skipped)` を畳む（旧実装の rows 単体も受ける）。"""
    if isinstance(result, tuple):
        raw_rows = result[0] if result else []
        raw_skipped = result[1] if len(result) > 1 else []
    else:
        raw_rows, raw_skipped = result, []
    rows = [r for r in (raw_rows or []) if isinstance(r, dict)]
    skipped = [
        {"id": str(s.get("id") or ""), "reason": str(s.get("reason") or "")}
        for s in (raw_skipped or [])
        if isinstance(s, dict) and s.get("id")
    ]
    return rows, skipped


def _tests_of(domain: str) -> list[dict[str, Any]]:
    data = _store().load(domain) or {}
    tests = data.get("tests")
    return list(tests) if isinstance(tests, list) else []


def _ta2_dir(domain: str) -> Path:
    return _out() / domain / "ta2"


def _runs_path(domain: str) -> Path:
    return _ta2_dir(domain) / "runs.json"


def _resolved_run_dir(domain: str) -> Path:
    """実行と証跡の置き場。**必ず絶対パスへ畳む。**

    `run_dir()` は相対パスを返すことがあり、そのまま `send_file` へ渡すと Blueprint の
    `root_path`（`web/`）基準で解決されて `web/output/...` を探し、FileNotFoundError で
    500 相当の 400 になっていた（検証 B-1）。
    """
    return Path(run_dir(domain)).resolve()


def _load_runs(domain: str) -> list[dict[str, Any]]:
    path = _runs_path(domain)
    if not path.is_file():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [r for r in loaded if isinstance(r, dict)] if isinstance(loaded, list) else []


def _last_run_at(domain: str) -> str:
    """TA2 自身の履歴（runs.json）を正とし、無ければ旧 run_result.json を見る。"""
    runs = _load_runs(domain)
    if runs:
        return str(runs[0].get("at") or "")
    return str((load_run_result(domain) or {}).get("ran_at") or "")


# =========================================================================
# サイト・テスト定義
# =========================================================================
@bp.get("/api/ta2/sites")
@_guard
def api_ta2_sites() -> dict:
    root = _out()
    sites: list[dict[str, Any]] = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name == "tenants":
                continue
            if not (entry / "report.json").is_file():
                continue
            domain = entry.name
            try:
                report = _report(domain)
            except Ta2Error:
                continue
            tests: list[dict[str, Any]] = []
            try:
                tests = _tests_of(domain)
            except Exception:  # noqa: BLE001 - 一覧は 1 サイトの失敗で止めない
                logger.warning("TA2: %s のテスト定義を読めません", domain, exc_info=True)
            meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
            sites.append(
                {
                    "domain": domain,
                    "name": str(meta.get("title") or meta.get("site_name") or domain),
                    "screens": len(report.get("screens") or []),
                    "tests": len(tests),
                    "fails": sum(1 for t in tests if t.get("status") == "fail"),
                    "last_run_at": _last_run_at(domain),
                }
            )
    return {"sites": sites}


@bp.get("/api/ta2/tests")
@_guard
def api_ta2_tests() -> dict:
    domain = _domain()
    report = _report(domain)
    st = _store()
    data = st.load(domain) or {}
    if not data.get("tests"):
        data = st.derive_initial(domain, report) or {}
        st.save(domain, data)
    return {
        "domain": domain,
        "tests": list(data.get("tests") or []),
        "elements": st.elements_of(report),
        "screens": st.screens_of(report),
    }


@bp.post("/api/ta2/tests")
@_guard
def api_ta2_tests_create() -> dict:
    domain = _domain()
    report = _report(domain)
    body = _body()
    screen = str(body.get("screen") or "")
    name = str(body.get("name") or "")
    gap_ids = body.get("gap_ids") or []
    if not isinstance(gap_ids, list):
        raise Ta2Error("gap_ids は配列で指定してください", 400)
    if not screen and not name:
        raise Ta2Error("screen か name のどちらかが必要です", 400)
    created = _store().generate_from_gaps(domain, report, screen, [str(g) for g in gap_ids], name)
    if isinstance(created, dict):
        created = created.get("created") or []
    return {"created": list(created or [])}


@bp.put("/api/ta2/tests/<test_id>")
@_guard
def api_ta2_tests_update(test_id: str) -> dict:
    domain = _domain()
    body = _body()
    patch: dict[str, Any] = {}
    if "name" in body:
        patch["name"] = str(body.get("name") or "")
    if "steps" in body:
        steps = body.get("steps")
        if not isinstance(steps, list):
            raise Ta2Error("steps は配列で指定してください", 400)
        patch["steps"] = steps
    if not patch:
        raise Ta2Error("更新する内容（name か steps）がありません", 400)
    test = _store().update_test(domain, test_id, patch)
    if not test:
        raise Ta2Error("指定のテストが見つかりません", 404)
    return {"test": test}


@bp.delete("/api/ta2/tests/<test_id>")
@_guard
def api_ta2_tests_delete(test_id: str) -> dict:
    domain = _domain()
    if not _store().delete_test(domain, test_id):
        raise Ta2Error("指定のテストが見つかりません", 404)
    return {"ok": True}


@bp.post("/api/ta2/tests/<test_id>/duplicate")
@_guard
def api_ta2_tests_duplicate(test_id: str) -> dict:
    domain = _domain()
    test = _store().duplicate(domain, test_id)
    if not test:
        raise Ta2Error("指定のテストが見つかりません", 404)
    return {"test": test}


@bp.post("/api/ta2/tests/resync")
@_guard
def api_ta2_tests_resync() -> dict:
    """テストケース表の変更をテスト一覧へ取り込む。

    既存テストの手順・実行結果・履歴は保つ。利用者が名前を変えたテストは
    名前も変えない（`name_edited`）。表から消えた行は削除せず `orphan` を立てる。
    消してしまうと、実行実績ごと失われて取り返しがつかないため。
    """
    domain = _domain()
    return _store().resync(domain, _report(domain))


@bp.post("/api/ta2/tests/<test_id>/fix")
@_guard
def api_ta2_tests_fix(test_id: str) -> dict:
    domain = _domain()
    body = _body()
    raw_step = body.get("step")
    try:
        step = int(raw_step)
    except (TypeError, ValueError) as exc:
        raise Ta2Error("step には手順の番号（0 以上の整数）が必要です", 400) from exc
    if step < 0:
        raise Ta2Error("step には手順の番号（0 以上の整数）が必要です", 400)
    test, reason = _split_fix(_store().apply_fix(domain, test_id, step))
    if not test:
        # ストアが理由を返した＝入力が悪い（400）／何も無い＝そのテストが無い（404）
        raise Ta2Error(reason or "指定のテストが見つかりません", 400 if reason else 404)
    if reason:
        # 修正案が無いのは正常系（契約 §3.1「無ければ null で修正案なし」）
        return {"test": test, "applied": False, "reason": reason}
    return {"test": test, "applied": True}


# =========================================================================
# 実行
# =========================================================================
def _record_run_history(domain: str, run_id: str, at: str, result: dict[str, Any]) -> None:
    """直近 30 件の実行履歴を ta2/runs.json に残す（/api/ta2/runs の源）。"""
    path = _runs_path(domain)
    runs = _load_runs(domain)
    runs.insert(
        0,
        {
            "run_id": run_id,
            "at": at,
            "passed": int(result.get("passed") or 0),
            "failed": int(result.get("failed") or 0),
            "total": int(result.get("total") or 0),
            "duration_ms": int(result.get("duration_ms") or 0),
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(runs[:30], ensure_ascii=False, indent=2), encoding="utf-8")


def _skip_patch(reason: str, at: str) -> dict[str, Any]:
    return {"status": "new", "last": {"at": at, "step": None, "dur_ms": 0, "error": reason}}


def _mark_skipped(domain: str, skipped: list[dict[str, str]], at: str) -> None:
    """実行対象から外れたテストに理由を残す（status=new・last.error=理由）。"""
    st = _store()
    pending: dict[str, str] = {}
    for item in skipped:
        test_id, reason = item["id"], item["reason"]
        try:
            updated = st.update_test(domain, test_id, _skip_patch(reason, at)) or {}
        except Exception:  # noqa: BLE001 - 理由の記録失敗で実行そのものを止めない
            logger.warning("TA2: %s の除外理由を保存できません", test_id, exc_info=True)
            updated = {}
        if str((updated.get("last") or {}).get("error") or "") != reason:
            pending[test_id] = reason
    if pending:
        _write_skip_reasons(domain, pending, at)


def _write_skip_reasons(domain: str, pending: dict[str, str], at: str) -> None:
    """`update_test` が status / last を受け付けない場合の退避経路。"""
    st = _store()
    try:
        data = st.load(domain) or {}
        rows = data.get("tests")
        if not isinstance(rows, list):
            return
        patched = [
            {**row, **_skip_patch(pending[str(row.get("id") or "")], at)}
            if str(row.get("id") or "") in pending
            else row
            for row in rows
        ]
        st.save(domain, {**data, "tests": patched})
    except Exception:  # noqa: BLE001
        logger.warning("TA2: %s の除外理由を保存できません", domain, exc_info=True)


def _execute(domain: str, run_id: str, spec_path: Path, out_dir: Path, browser: str) -> None:
    """別スレッドで Playwright を実行し、結果を tests.json と履歴へ反映する。"""
    result: dict[str, Any] = {}
    try:
        result = run_playwright(
            spec_path,
            out_dir,
            per_test_timeout_sec=20,
            egress_policy=EgressPolicy(allow_local=_local_targets_allowed()),
            browser=browser,
            on_proc=lambda proc: _RUNNING_PROCS.__setitem__(run_id, proc),
        )
    except Exception:  # noqa: BLE001 - 実行失敗でスレッドを黙って死なせない
        logger.exception("TA2: %s の実行に失敗しました", domain)
    finally:
        proc = _RUNNING_PROCS.pop(run_id, None)
        cancelled = bool(proc is not None and proc.returncode is not None and proc.returncode < 0)
        if proc is not None:
            _terminate_proc(proc)
        entry = _RUNS.get(domain)
        if entry is not None and entry.get("cancelled"):
            cancelled = True

    if cancelled or not result:
        # 停止した実行は結果を書かない（途中経過を「失敗」として残さないため）
        return
    at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # `save_run_result` はテスト名の先頭が `TC-` の行しか畳まない（検証 10a）。TA2 の
    # テスト名は `PW-xxxx` なので cases が必ず空になり、旧テストケース表に
    # 「実行したのに結果が空」の run_result.json を上書きするだけだった。呼ばない。
    for label, call in (
        ("tests.json", lambda: _store().apply_run_result(domain, result, run_id, at)),
        ("runs.json", lambda: _record_run_history(domain, run_id, at, result)),
    ):
        try:
            call()
        except Exception:  # noqa: BLE001 - 1 つの保存失敗で他を捨てない
            logger.exception("TA2: %s への実行結果の保存に失敗しました", label)


@bp.post("/api/ta2/run")
@_guard
def api_ta2_run() -> dict:
    domain = _domain()
    body = _body()
    entry = _RUNS.get(domain)
    if entry is not None and entry["thread"].is_alive():
        raise Ta2Error("実行中です", 409)

    ids = body.get("ids") or []
    if not isinstance(ids, list):
        raise Ta2Error("ids は配列で指定してください", 400)
    browser = str(body.get("browser") or "chromium")
    if browser not in ("chromium", "firefox", "webkit"):
        raise Ta2Error("browser は chromium / firefox / webkit のいずれかです", 400)

    tests = _tests_of(domain)
    if ids:
        allow = {str(i) for i in ids}
        tests = [t for t in tests if str(t.get("id")) in allow]
    if not tests:
        raise Ta2Error("実行できるテストがありません", 400)

    rows, skipped = _split_rows(_store().to_table_rows(tests))
    if not rows:
        reason = skipped[0]["reason"] if skipped else ""
        raise Ta2Error("実行できるテストがありません" + (f"：{reason}" if reason else ""), 400)
    at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if skipped:
        # 黙って捨てない。UI が「なぜ実行されないか」を出せるよう理由を残す（検証 B-3）
        _mark_skipped(domain, skipped, at)

    out_dir = _resolved_run_dir(domain)
    gen = generate_spec(rows, out_dir)

    stale = out_dir / "playwright_progress.ndjson"
    if stale.is_file():
        stale.unlink()

    run_id = uuid.uuid4().hex
    # total は「実際に spec へ載った件数」。除外分を含めると done が total に届かない
    mapped = [str(m.get("case_id") or "") for m in gen.get("mapping") or [] if isinstance(m, dict)]
    ordered = [i for i in mapped if i] or [str(r.get("case_id") or "") for r in rows]
    total = len(ordered) or len(rows)

    worker = _execute
    try:  # テナント別の出力先を解決できるよう、リクエストコンテキストを引き継ぐ
        from flask import copy_current_request_context

        worker = copy_current_request_context(_execute)
    except Exception:  # noqa: BLE001
        logger.warning("TA2: リクエストコンテキストを引き継げませんでした", exc_info=True)

    thread = threading.Thread(
        target=worker,
        args=(domain, run_id, Path(gen["spec_path"]), out_dir, browser),
        daemon=True,
    )
    _RUNS[domain] = {
        "run_id": run_id,
        "thread": thread,
        "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "cancelled": False,
        "ids": ordered,
        "out_dir": str(out_dir),
        "skipped": skipped,
    }
    thread.start()
    return {"run_id": run_id, "total": total, "skipped": skipped}


@bp.get("/api/ta2/run/status")
@_guard
def api_ta2_run_status() -> dict:
    domain = _domain()
    entry = _RUNS.get(domain)
    out_dir = Path(entry["out_dir"]) if entry else _resolved_run_dir(domain)
    progress_total, raw = _read_progress_ndjson(out_dir / "playwright_progress.ndjson")

    tests = [
        {
            "id": str(t.get("title") or "").split(" ", 1)[0],
            "status": str(t.get("status") or ""),
            "duration_ms": int(t.get("duration_ms") or 0),
            "error": str(t.get("error") or ""),
        }
        for t in raw
    ]
    running = bool(entry is not None and entry["thread"].is_alive())
    ordered: list[str] = list(entry["ids"]) if entry else []
    current_id = ""
    if running and len(tests) < len(ordered):
        current_id = ordered[len(tests)]
    return {
        "running": running,
        "run_id": str(entry["run_id"]) if entry else "",
        "total": int(entry["total"]) if entry else int(progress_total or 0),
        "done": len(tests),
        "passed": sum(1 for t in tests if t["status"] == "passed"),
        "failed": sum(1 for t in tests if t["status"] == "failed"),
        "current_id": current_id,
        "tests": tests,
        "skipped": list(entry.get("skipped") or []) if entry else [],
    }


@bp.post("/api/ta2/run/cancel")
@_guard
def api_ta2_run_cancel() -> dict:
    domain = _domain()
    entry = _RUNS.get(domain)
    if entry is None or not entry["thread"].is_alive():
        return {"ok": False}
    entry["cancelled"] = True
    proc = _RUNNING_PROCS.get(str(entry["run_id"]))
    if proc is None:
        return {"ok": False}
    _terminate_proc(proc)
    return {"ok": True}


@bp.get("/api/ta2/runs")
@_guard
def api_ta2_runs() -> dict:
    return {"runs": _load_runs(_domain())[:30]}


# =========================================================================
# 証跡
# =========================================================================
def _newest(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _under(target: Path, base: Path) -> bool:
    try:
        target.relative_to(base)
    except ValueError:
        return False
    return True


def _matches_test(path: Path, test_id: str) -> bool:
    """Playwright は `test-results/testcases-<テストID>-<テスト名>/…` に証跡を置く。"""
    needle = test_id.lower()
    for part in path.parts:
        low = part.lower()
        if low.startswith(f"{needle}-") or low.endswith(f"-{needle}") or f"-{needle}-" in low:
            return True
    return False


def _artifact_target(base: Path, kind: str, test_id: str) -> Path | None:
    """実レイアウト（`output/<domain>/testcases/`）から証跡の実ファイルを選ぶ。

    report   : `playwright-report/index.html`（無ければ `playwright_report.html`）
    trace    : `test-results/<テスト>/trace.zip`
    screenshot: `test-results/<テスト>/test-failed-1.png`（無ければ test-finished）
    """
    if kind == "report":
        return _newest([base / "playwright-report" / "index.html", base / "playwright_report.html"])
    results = base / "test-results"
    if not results.is_dir():
        return None
    pattern = "trace*.zip" if kind == "trace" else "*.png"
    candidates = sorted(results.rglob(pattern))
    if test_id:
        candidates = [p for p in candidates if _matches_test(p, test_id)]
    if kind == "screenshot":
        failed = [p for p in candidates if "failed" in p.name.lower()]
        candidates = failed or candidates
    return _newest(candidates)


@bp.get("/api/ta2/artifact")
@_guard
def api_ta2_artifact() -> Any:
    domain = _domain()
    kind = request.args.get("kind", "")
    if kind not in _ARTIFACT_KINDS:
        raise Ta2Error("kind は trace / screenshot / report のいずれかです", 400)
    test_id = request.args.get("id", "")
    if test_id and not _SCREEN_RE.match(test_id):
        raise Ta2Error("id が不正です", 400)

    base = _resolved_run_dir(domain)
    target = _artifact_target(base, kind, test_id)
    if target is None:
        raise Ta2Error(_NO_ARTIFACT, 404)
    target = target.resolve()
    if not target.is_file() or not _under(target, base):
        raise Ta2Error(_NO_ARTIFACT, 404)
    try:
        return send_file(str(target))
    except OSError as exc:  # 送信直前に消えた場合も 404 に畳む（500 を返さない）
        raise Ta2Error(_NO_ARTIFACT, 404) from exc


@bp.get("/api/ta2/screenshot")
@_guard
def api_ta2_screenshot() -> Any:
    domain = _domain()
    screen = request.args.get("screen", "")
    if not _SCREEN_RE.match(screen):
        raise Ta2Error("screen が不正です", 400)
    # send_file は相対パスを Blueprint の root_path（web/）基準で解決するため、必ず絶対パスにする。
    path = (_out() / domain / "screenshots" / f"{screen}.png").resolve()
    if not path.is_file():
        raise Ta2Error("この画面のスクリーンショットはありません", 404)
    return send_file(str(path))


# =========================================================================
# 地図と変更
# =========================================================================
@bp.get("/api/ta2/techniques")
@_guard
def api_ta2_techniques() -> dict:
    """画面ごとのテスト技法の適用結果。

    ISO/IEC/IEEE 29119-4:2021 が定める仕様ベース技法のうち、この製品が
    画面の解析結果から導けるものを返す（5.2.1 同値分割 / 5.2.2 分類ツリー /
    5.2.3 境界値分析 / 5.2.5 組合せ / 5.2.6 デシジョンテーブル /
    5.2.7 原因結果グラフ / 5.2.8 状態遷移）。加えて経験ベースの
    エラー推測（5.4）とドメイン分析を含む。

    適用できない技法は applicable=False と理由を返す。黙って省くと
    「その技法を検討していない」のか「対象が無い」のかが分からなくなる。
    """
    domain = _domain()
    report = _report(domain)
    screen_id = str(request.args.get("screen") or "").strip()

    import sys
    from pathlib import Path as _Path

    src = str(_Path(__file__).resolve().parents[2] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from autorun.techniques import apply_all

    screens = [s for s in (report.get("screens") or []) if isinstance(s, dict)]
    if screen_id:
        screens = [s for s in screens if str(s.get("page_id") or "") == screen_id]
        if not screens:
            raise Ta2Error("その画面は解析結果にありません", 404)

    out: list[dict[str, Any]] = []
    for sc in screens:
        try:
            res = apply_all(sc)
        except Exception as exc:  # noqa: BLE001  技法側の失敗で画面ごと落とさない
            logger.warning("技法の適用に失敗: %s (%s)", sc.get("page_id"), exc)
            continue
        res["title"] = str(sc.get("title") or "")
        res["url"] = str(sc.get("url") or "")
        out.append(res)
    return {"domain": domain, "screens": out}


@bp.get("/api/ta2/map")
@_guard
def api_ta2_map() -> dict:
    domain = _domain()
    report = _report(domain)
    st = _store()
    tests = _tests_of(domain)
    gaps = st.gaps_of(domain, report, tests) or []
    screens: list[dict[str, Any]] = []
    for screen in st.screens_of(report) or []:
        sid = str(screen.get("id") or "")
        mine = [t for t in tests if str(t.get("screen") or "") == sid]
        holes = [g for g in gaps if str(g.get("screen") or "") == sid]
        covered = len(mine)
        denominator = covered + len(holes)
        screens.append(
            {
                "id": sid,
                "name": str(screen.get("name") or ""),
                "path": str(screen.get("path") or ""),
                "tests": covered,
                "fails": sum(1 for t in mine if t.get("status") == "fail"),
                "coverage": round(100 * covered / denominator) if denominator else 0,
                "gaps": holes,
            }
        )
    return {"screens": screens}


@bp.get("/api/ta2/drift")
@_guard
def api_ta2_drift() -> dict:
    domain = _domain()
    result = _store().drift_items(domain)
    if isinstance(result, list):
        result = {"items": result}
    if not isinstance(result, dict):
        result = {"items": []}
    items = list(result.get("items") or [])
    payload: dict[str, Any] = {
        "baseline_at": str(result.get("baseline_at") or ""),
        "current_at": str(result.get("current_at") or ""),
        "items": items,
    }
    reason = str(result.get("reason") or "")
    if not items and not payload["baseline_at"]:
        reason = reason or _NO_BASELINE
    if reason:
        payload["reason"] = reason
    return payload


@bp.post("/api/ta2/drift/<item_id>/apply")
@_guard
def api_ta2_drift_apply(item_id: str) -> dict:
    domain = _domain()
    applied = _store().drift_apply(domain, item_id)
    if isinstance(applied, dict):
        applied = applied.get("applied") or []
    return {"applied": [str(x) for x in (applied or [])]}


@bp.post("/api/ta2/drift/<item_id>/dismiss")
@_guard
def api_ta2_drift_dismiss(item_id: str) -> dict:
    domain = _domain()
    _store().drift_dismiss(domain, item_id)
    return {"ok": True}


def _after_recrawl(domain: str, out_dir: Path, job: Any) -> None:
    """再クロール完了時に成果物の退避と利用実績の記録を行う。

    クロールのバックグラウンドスレッドから呼ばれるためリクエスト
    コンテキストが無い。出力先は起動時に解決したものを受け取る。
    """
    if getattr(job, "status", "") != "completed":
        return
    from web.routes.crawl import _record_usage_safely

    _record_usage_safely(domain, True, out_dir)


@bp.post("/api/ta2/recrawl")
@_guard
def api_ta2_recrawl() -> dict:
    domain = _domain()
    report = _report(domain)
    meta = report.get("meta") or {}
    url = str((meta.get("target_url") if isinstance(meta, dict) else "") or "").strip()
    if not url:
        raise Ta2Error("対象 URL が report.json にありません", 400)

    # スレッド内ではリクエストコンテキストを参照できないため、
    # テナントスコープ済みの出力先をここで解決して渡す（/api/ta2/run と同じ）。
    out_dir = _out()
    from web.services.job_queue import list_jobs_for_domain, start_crawl_job

    # 同じサイトへ 2 本のクロールを同時に走らせない。並走すると同じ
    # report.json / snapshots を互いに上書きし、成果物が壊れる。
    running = [j for j in list_jobs_for_domain(domain) if j.status in ("queued", "running")]
    if running:
        raise Ta2Error(f"このサイトは再クロール中です（job_id={running[0].job_id}）", 409)

    job_id = start_crawl_job(
        domain,
        url,
        formats=["md", "html", "json"],
        compare=True,
        output_dir=out_dir,
        on_done=lambda job: _after_recrawl(domain, out_dir, job),
        domain_name=domain,
    )
    return {"job_id": job_id}


@bp.get("/api/ta2/recrawl/status")
@_guard
def api_ta2_recrawl_status() -> dict:
    _domain()
    job_id = str(request.args.get("job_id") or "").strip()
    if not job_id:
        raise Ta2Error("job_id を指定してください", 400)
    from web.services.job_queue import get_job

    job = get_job(job_id)
    if job is None:
        raise Ta2Error("その再クロールは見つかりません", 404)
    return {
        "status": job.status,
        "finished_at": job.finished_at,
        "exit_code": job.exit_code,
        "log_tail": (job.log_tail or "")[-300:],
    }


# =========================================================================
# 報告（C3）— 単体 HTML。組み立ては web/services/site_report.py（純関数）が行う
# =========================================================================
def _report_screens(domain: str, report: dict[str, Any], tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """カバレッジ表のための画面ごとの集計（/api/ta2/map と同じ数え方）。"""
    st = _store()
    gaps = st.gaps_of(domain, report, tests) or []
    screens: list[dict[str, Any]] = []
    for screen in st.screens_of(report) or []:
        sid = str(screen.get("id") or "")
        mine = [t for t in tests if str(t.get("screen") or "") == sid]
        holes = [g for g in gaps if str(g.get("screen") or "") == sid]
        denominator = len(mine) + len(holes)
        screens.append(
            {
                "id": sid,
                "name": str(screen.get("name") or ""),
                # 画面名はサイトによって全画面共通のことがある（<title> が同じ）。
                # 報告を受け取る側が見分けられるよう、パスも渡す。
                "path": str(screen.get("path") or ""),
                "tests": len(mine),
                "fails": sum(1 for t in mine if t.get("status") == "fail"),
                "coverage": round(100 * len(mine) / denominator) if denominator else 0,
            }
        )
    return screens


def _report_usage(out_dir: Path, domain: str = "") -> dict[str, Any]:
    """利用実績の集計。記録が無ければ空 dict（推定値を作らない）。

    domain を渡すと usage_log.jsonl の domain 列でそのサイトの行だけに絞る。
    サイト名義の報告書にワークスペース全体の金額を載せないため（絞れた場合は
    集計に domain を添え、報告側が「このサイトのみ」と明示できるようにする）。
    """
    try:
        from web.services.usage_tracker import load_usage, summarize_usage

        records = load_usage(out_dir)
        if domain:
            records = [r for r in records if str(r.get("domain") or "") == domain]
        if not records:
            return {}
        return {**summarize_usage(records), "domain": domain} if domain else summarize_usage(records)
    except Exception:  # noqa: BLE001 — 報告本体は落とさない
        logger.warning("報告: 利用実績の集計に失敗しました", exc_info=True)
        return {}


@bp.get("/api/ta2/report")
@_guard
def api_ta2_report() -> Any:
    from flask import Response

    from web.services.site_report import ALL_SECTIONS, build_site_report_html

    domain = _domain()
    report = _report(domain)
    tests = _tests_of(domain)

    raw_sections = str(request.args.get("sections") or "").strip()
    sections = (
        [s for s in (x.strip() for x in raw_sections.split(",")) if s in ALL_SECTIONS]
        if raw_sections
        else list(ALL_SECTIONS)
    )

    try:
        drift = _store().drift_items(domain)
    except Exception:  # noqa: BLE001 — 変更が読めなくても報告は出す
        logger.warning("報告: drift_items に失敗しました domain=%s", domain, exc_info=True)
        drift = {"items": []}

    html_text = build_site_report_html(
        domain,
        report=report,
        tests=tests,
        runs=_load_runs(domain),
        drift=drift,
        map_screens=_report_screens(domain, report, tests),
        usage=_report_usage(_out(), domain),
        base_url=request.url_root.rstrip("/"),
        sections=sections,
    )
    response = Response(html_text, mimetype="text/html; charset=utf-8")
    if request.args.get("download") == "1":
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{domain}-report.html"'
        )
    return response


def _existing_candidate_count(domain: str) -> int | None:
    """System 02 既存のテスト候補数。取得できなければ None（呼び出し側が代替の Before を使う）。"""
    try:
        data = _store().load(domain) or {}
        tests = data.get("tests")
        if isinstance(tests, list) and tests:
            return len(tests)
        report_path = _out() / domain / "report.json"
        if not report_path.is_file():
            return None
        derived = _store().derive_initial(domain, _report(domain)) or {}
        return len(derived.get("tests") or [])
    except Exception:  # noqa: BLE001  既存件数は補助情報。取れなくても観点の表示は止めない
        logger.warning("既存のテスト候補数を取得できませんでした: %s", domain, exc_info=True)
        return None


@bp.get("/api/sites/<domain>/rea-test-viewpoints")
def api_rea_test_viewpoints(domain: str) -> Any:
    """リバース解析の根拠から増えるテスト観点候補（読み取りのみ）。"""
    from web.routes.reverse_analysis import site_evidence
    from web.services.rea_test_viewpoints import build_viewpoints

    if not _valid_domain(domain):
        return {"state": "error", "message": "サイトの指定が正しくありません。",
                "next_action": "サイト一覧から開き直してください。"}, 400  # fmt: skip
    from web.services import static_route_probe_store as probe_store

    probe = probe_store.by_evidence(probe_store.load(scoped_output_dir(OUTPUT_DIR), domain))
    return build_viewpoints(site_evidence(domain), _existing_candidate_count(domain), probe)
