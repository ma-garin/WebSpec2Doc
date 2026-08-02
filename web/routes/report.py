from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from flask import Blueprint, Response, make_response, redirect, request, send_file, url_for

from web.config import _PREVIEW_MIME, OUTPUT_DIR, SAMPLE_DOMAIN, SAMPLE_REPORT_DIR
from web.services.admin_audit import append_admin_audit
from web.services.spec_ts_generator import generate_spec_ts
from web.summary import _summary_for_domain, summary_from_report
from web.tenancy import current_auth_user, scoped_instance_path, scoped_output_dir
from web.validation import _safe_output_path, _valid_domain

bp = Blueprint("report", __name__)
INSTANCE_DIR = Path("instance")
logger = logging.getLogger(__name__)


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _record_export(target_id: str, detail: dict[str, object] | None = None) -> None:
    actor = current_auth_user() or {}
    try:
        append_admin_audit(
            scoped_instance_path(INSTANCE_DIR / "admin_audit.jsonl"),
            action="report.exported",
            actor_id=str(actor.get("id", "")),
            actor_email=str(actor.get("email", "local-admin")),
            target_type="report",
            target_id=target_id,
            detail=detail,
        )
    except OSError as exc:
        logger.warning("レポート出力の監査ログ保存に失敗しました: %s", exc)


@bp.get("/preview")
def preview() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    mime = _PREVIEW_MIME.get(target.suffix.lower(), "text/plain; charset=utf-8")
    resp = send_file(target, mimetype=mime)
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/download")
def download() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    try:
        target_id = str(target.resolve().relative_to(_out().resolve()))
    except ValueError:
        target_id = target.name
    _record_export(target_id, {"format": target.suffix.lower().lstrip(".")})
    return send_file(target, as_attachment=True, download_name=target.name)


@bp.get("/api/export/spec-xlsx")
def export_spec_xlsx() -> Response:
    """テスト仕様書一式（7 シート）の Excel を返す（P2-3）。

    クロール時に作られる `spec.xlsx` は実測仕様の 4 シートだけで、
    テスト設計・テストケース・遷移表は入っていない。これらはクロールより
    後に生成・編集されるため、要求された時点で組み直して返す。
    同じ内容をディスクへも書き戻し、ZIP 一括や CLI から読む `spec.xlsx` と
    食い違わないようにする。
    """
    from web.services.export_xlsx import ExportError, write_full_spec_xlsx

    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    out_dir = _out()
    if not (out_dir / domain).is_dir():
        return Response(status=404)
    try:
        target, counts = write_full_spec_xlsx(domain, out_dir)
    except ExportError as exc:
        logger.warning("Excel を組み立てられません（%s）: %s", domain, exc)
        return Response(str(exc), status=409, mimetype="text/plain; charset=utf-8")
    _record_export(f"{domain}/spec.xlsx", {"format": "xlsx", "sheets": counts})
    # send_file は相対パスをアプリのルート（web/）基準で解決するため絶対パスで渡す。
    return send_file(
        target.resolve(),
        as_attachment=True,
        download_name="spec.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.get("/download-zip")
def download_zip() -> Response:
    """ドメイン配下をZIP化する。`paths`（複数値・カンマ区切りいずれも可）を指定した場合は
    そのファイルのみをZIP化する（ギャラリー一括エクスポート等の選択ダウンロード用）。
    未指定時は従来通りドメイン配下全件。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    out_dir = _out()
    base = (out_dir / domain).resolve()
    if out_dir.resolve() not in base.parents or not base.is_dir():
        return Response(status=404)
    selected = _selected_zip_paths(base, request.args.getlist("paths"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        files = selected if selected is not None else (f for f in base.rglob("*") if f.is_file())
        for f in files:
            zf.write(f, f.relative_to(base.parent))
    buf.seek(0)
    _record_export(f"{domain}/{domain}.zip", {"format": "zip", "selected": selected is not None})
    return send_file(
        buf, as_attachment=True, download_name=f"{domain}.zip", mimetype="application/zip"
    )


def _selected_zip_paths(base: Path, raw_values: list[str]) -> list[Path] | None:
    """`paths` クエリ（配列またはカンマ区切り）を実在・ドメイン配下検証済みの絶対パスへ変換する。

    `paths` が一切指定されていない場合は None を返し、呼び出し側でドメイン全体の
    ZIP化にフォールバックさせる。指定された値のうち検証を通らないものは無視する
    （path traversal・他ドメインのファイル指定を許さない）。
    """
    if not raw_values:
        return None
    candidates = [part for value in raw_values for part in value.split(",") if part.strip()]
    resolved = (_safe_output_path(candidate) for candidate in candidates)
    return [path for path in resolved if path is not None and base in path.parents]


@bp.get("/api/report/<domain>/spec-ts")
def download_spec_ts(domain: str) -> Response | tuple[dict, int]:
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    out_dir = _out()
    candidates_path = out_dir / domain / "qa_process" / "playwright_candidates.json"
    if not candidates_path.exists():
        candidates_path = out_dir / domain / "qa" / "playwright_candidates.json"
    if not candidates_path.exists():
        return {"error": "playwright_candidates.json が見つかりません"}, 404
    filter_mode = request.args.get("filter", "all")
    if filter_mode not in {"all", "smoke", "transition", "form"}:
        filter_mode = "all"
    with tempfile.TemporaryDirectory() as tmp:
        output_path = Path(tmp) / f"{domain}.spec.ts"
        generate_spec_ts(domain, candidates_path, output_path, filter_mode=filter_mode)
        content = output_path.read_bytes()
    buffer = io.BytesIO(content)
    buffer.seek(0)
    _record_export(f"{domain}/{domain}.spec.ts", {"format": "typescript"})
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{domain}.spec.ts",
        mimetype="text/plain",
    )


def _generate_features_md_if_missing(domain_dir: Path) -> None:
    """report.jsonから機能一覧（features.md）を導出し、未生成なら書き出す。

    新規クロールを要求せず既存 report.json のみから導出するため、過去に生成済みの
    ドメインでも初回アクセス時に自動生成される。生成失敗は結果表示を妨げない。
    """
    features_path = domain_dir / "features.md"
    if features_path.is_file():
        return
    report_json = domain_dir / "report.json"
    if not report_json.is_file():
        return
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    screens = [
        screen
        for screen in data.get("screens", [])
        if isinstance(screen, dict) and screen.get("is_canonical", True)
    ]
    from generator.feature_catalog import generate_features_markdown

    try:
        features_path.write_text(generate_features_markdown(screens), encoding="utf-8")
    except OSError:
        pass


@bp.post("/api/sample-report")
def api_sample_report() -> dict | tuple[dict, int]:
    """同梱のサンプルレポートを自テナントの出力先へ展開し、開くドメインを返す（P3-1）。

    初回の利用者にクロールを待たせずレポートの仕上がりを見せるための導線。同梱物は
    デモサイトを事前に解析した実際の成果物で、その場でクロールは行わない。

    展開先を予約ドメインにすることで、レポート表示・スクリーンショット・エクスポートは
    通常の経路をそのまま使える（読み取り API を増やさない）。利用者自身の解析結果と
    混ざらないよう、この予約ドメインは解析履歴の一覧から除外している。
    """
    source = SAMPLE_REPORT_DIR
    if not source.is_dir():
        logger.error("同梱サンプルが見つかりません: %s", source)
        return {"error": "サンプルレポートが同梱されていません"}, 404
    target = _out() / SAMPLE_DOMAIN
    try:
        if target.exists():
            # 同梱物を正本とし、前回展開した内容は毎回置き換える（更新の取りこぼしを防ぐ）
            shutil.rmtree(target)
        shutil.copytree(source, target)
    except OSError:
        logger.exception("サンプルレポートの展開に失敗しました: %s", target)
        return {"error": "サンプルレポートを準備できませんでした"}, 500
    return {"domain": SAMPLE_DOMAIN}


@dataclass(frozen=True)
class _ResultSource:
    """結果ページのデータ源。サイト単位の最新か、特定の実行回か。

    同じ画面に 2 つのデータ源を通すため、両者の違いをここへ集める。
    分岐を呼び出し側に散らすと、項目が増えるたびに同じ ``if`` が増殖する。
    """

    base_dir: Path
    domain_dir: Path
    run_id: str

    @property
    def is_run(self) -> bool:
        return bool(self.run_id)

    @property
    def backfills_features(self) -> bool:
        """features.md の遅延生成をするか。実行回は当時の内容を変えないので生成しない。"""
        return not self.is_run

    @property
    def spec_ts_rel(self) -> str:
        # 実行回へ退避しているのは AutoRun が生成した spec。サイト単位は
        # テストケース表から生成した spec を使う（別系統の成果物）。
        return "qa_process/autorun.spec.ts" if self.is_run else "testcases/testcases.spec.ts"

    def playwright_html_rel(self, path_of: Callable[[str], str]) -> str:
        if self.is_run:
            # 実行回は testcases/playwright-report/ を退避していないため、
            # 退避済みの qa_process/playwright_report.html を実行レポートとして使う。
            return "qa_process/playwright_report.html"
        native = self.domain_dir / "testcases" / "playwright-report" / "index.html"
        fallback = self.domain_dir / "testcases" / "playwright_report.html"
        chosen = fallback if path_of("testcases/playwright_report.html") else native
        return str(chosen.relative_to(self.domain_dir))

    def summary(self, domain: str, output_root: Path) -> dict[str, int]:
        if self.is_run:
            from_run = summary_from_report(self.base_dir / "report.json")
            if from_run is not None:
                return from_run
        return _summary_for_domain(domain, output_root)


def _result_source(domain: str, domain_dir: Path, run_id: str) -> _ResultSource | None:
    """データ源を決める。実行回が指定されていて成果物が無ければ None。"""
    if not run_id:
        return _ResultSource(base_dir=domain_dir, domain_dir=domain_dir, run_id="")
    from web.services.run_store import run_dir, run_exists

    if not run_exists(_out(), domain, run_id):
        return None
    base = run_dir(_out(), domain, run_id)
    if base is None:
        return None
    return _ResultSource(base_dir=base, domain_dir=domain_dir, run_id=run_id)


@bp.get("/api/result")
def api_result() -> dict | tuple[dict, int]:
    """結果ページのデータ源。

    ``run_id`` を付けると、その実行回（runs/<run_id>/）の成果物を返す。
    付けなければ従来どおりサイト単位の最新（output/<domain>/）を返す。
    実行結果ページは同じ画面のまま、データ源だけを実行回へ差し替えて使う。
    """
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    domain_dir = _out() / domain
    if not domain_dir.is_dir() or domain_dir.is_symlink():
        return {"error": "not found"}, 404

    run_id = request.args.get("run_id", "").strip()
    source = _result_source(domain, domain_dir, run_id)
    if source is None:
        # 最新で代替しない。別の実行の中身を、この実行のものとして見せないため。
        return {
            "error": "この実行回の成果物は保存されていません",
            "recovery": (
                "実行回ごとの保存を入れる前の実行です。"
                "最新の成果物を代わりに表示することはしません。"
            ),
        }, 404
    base_dir = source.base_dir
    base_root = base_dir.resolve()

    def path_of(name: str) -> str:
        candidate = base_dir / name
        resolved = candidate.resolve()
        if (
            resolved == base_root
            or base_root not in resolved.parents
            or candidate.is_symlink()
            or not resolved.is_file()
        ):
            return ""
        return str(resolved)

    # スクリーンショットとスナップショットは実行回へ退避していない（容量のため）。
    # 実行回を見ているときは、その回のものが無いことを空で示す。
    shots_dir = base_dir / "screenshots"
    shots = sorted(shots_dir.glob("*.png")) if shots_dir.is_dir() else []
    snap_dir = domain_dir / "snapshots"
    snapshot_count = len(list(snap_dir.glob("*.json"))) if snap_dir.is_dir() else 0
    if source.backfills_features:
        _generate_features_md_if_missing(domain_dir)

    # 「テスト実行」タブのデータソースは、テストケース表から実行した結果
    # （testcases/run_result.json）だけを使う。qa_process/ 配下は AutoRun が残した
    # 別系統の成果物で、自分が実行していない結果を docs 側に出さないため参照しない。
    run_result = _testcase_run_summary(base_dir)
    pw_html_rel = source.playwright_html_rel(path_of)
    return {
        "summary": source.summary(domain, _out()),
        "snapshot_count": snapshot_count,
        "run_id": run_id,
        "files": {
            "html": path_of("report.html"),
            "pdf": path_of("report.pdf"),
            "json": path_of("report.json"),
            "excel": path_of("spec.xlsx"),
            "screens_md": path_of("screens.md"),
            "forms_md": path_of("forms.md"),
            "features_md": path_of("features.md"),
            "transition_mmd": path_of("transition.mmd"),
            "diff": path_of("diff_report.html"),
            "playwright_json": path_of("testcases/run_result.json"),
            "playwright_html": path_of(pw_html_rel),
            "playwright_native_html": path_of("testcases/playwright-report/index.html"),
            "spec_ts": path_of(source.spec_ts_rel),
            "qa_process_report": path_of("qa_process/qa_process_report.html"),
            "exploration_heatmap": path_of("exploration_heatmap.html"),
            "exploration_json": path_of("exploration_coverage.json"),
        },
        "playwright_run_at": run_result.get("ran_at", ""),
        "testcase_run": run_result,
        "screenshots": [path for s in shots if (path := path_of(str(s.relative_to(base_dir))))],
        # 同梱サンプル（P3-1）かどうか。画面側で「これはサンプルです」と明示するために使う。
        # 予約ドメインの判定はサーバを正本にし、画面側に定数を二重管理させない。
        "is_sample": domain == SAMPLE_DOMAIN,
    }


def _testcase_run_summary(domain_dir: Path) -> dict:
    """テストケース表から実行した結果の要約（無ければ空 dict＝未実行）。"""
    path = domain_dir / "testcases" / "run_result.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    summary = data.get("summary") or {}
    return {
        "ran_at": str(data.get("ran_at") or ""),
        "summary": summary if isinstance(summary, dict) else {},
        "case_count": len(data.get("cases") or {}),
    }


def _analysis_coverage_screens(shots_dir: Path, screens_meta: list[dict]) -> list[dict]:
    """report.json の画面 + スクショ実在から解析カバレッジ用の画面 dict を組む。"""
    result: list[dict] = []
    for sc in screens_meta:
        pid = str(sc.get("page_id") or "")
        captured = bool(pid) and (shots_dir / f"{pid}.png").is_file()
        result.append(
            {
                "page_id": pid,
                "title": sc.get("title") or "",
                "url": sc.get("url") or "",
                "captured": captured,
                "requires_login": bool(sc.get("requires_login") or sc.get("is_login_required")),
            }
        )
    return result


def _autorun_coverage_screens(domain_dir: Path, screens_meta: list[dict]) -> list[dict]:
    """playwright_report.json のテスト結果を画面へ決定的にマッピングする（捏造しない）。

    テスト title/name/file に page_id またはタイトルが含まれる場合のみ計上する。
    対応が取れない画面は runs=0（未実行）として正直に扱う。
    """
    pw_path = domain_dir / "qa_process" / "playwright_report.json"
    tests: list[dict] = []
    if pw_path.is_file():
        try:
            data = json.loads(pw_path.read_text(encoding="utf-8"))
            tests = data.get("tests") or []
        except (OSError, json.JSONDecodeError):
            tests = []
    result: list[dict] = []
    for sc in screens_meta:
        pid = str(sc.get("page_id") or "")
        title = str(sc.get("title") or "")
        runs = passed = failed = 0
        for t in tests:
            hay = f"{t.get('title', '')} {t.get('name', '')} {t.get('file', '')}"
            if (pid and pid in hay) or (len(title) >= 4 and title in hay):
                runs += 1
                status = str(t.get("status") or t.get("outcome") or "").lower()
                if status in ("passed", "expected", "ok"):
                    passed += 1
                elif status:
                    failed += 1
        result.append(
            {
                "page_id": pid,
                "title": title,
                "url": sc.get("url") or "",
                "runs": runs,
                "passed": passed,
                "failed": failed,
            }
        )
    return result


@bp.get("/api/state-table")
def api_state_table() -> dict | tuple[dict, int]:
    """状態遷移表（ISTQB 状態遷移テスト）を report.json から導出して返す。

    共通ナビゲーションは除外しない。除外すると「全状態から同じイベントを受け付ける」
    という状態遷移表の核心が失われ、被覆も欠ける（識別は is_common で行う）。
    """
    from graph.state_table import build_state_transition_report

    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    domain_dir = _out() / domain
    if not domain_dir.is_dir() or domain_dir.is_symlink():
        return {"error": "not found"}, 404

    report_path = _safe_output_path(str(domain_dir / "report.json"))
    if report_path is None:
        return {"error": "report not found"}, 404
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("state-table: report.json を読めません domain=%s: %s", domain, exc)
        return {"error": "report unreadable"}, 500

    screens = report.get("screens")
    if not isinstance(screens, list):
        return {"applicable": False, "reason": "画面が観測されていません。"}
    return build_state_transition_report(screens)


@bp.get("/api/coverage-heatmap")
def api_coverage_heatmap() -> Response:
    """カバレッジヒートマップ（kind=analysis: 取得状況3色 / kind=autorun: 実行回数×成否）をHTMLで返す。"""
    domain = request.args.get("domain", "")
    kind = request.args.get("kind", "analysis")
    if not _valid_domain(domain):
        return Response(status=404)
    domain_dir = _out() / domain
    if not domain_dir.is_dir() or domain_dir.is_symlink():
        return Response(status=404)
    report_path = domain_dir / "report.json"
    if not report_path.is_file():
        return Response(
            "<p style='font-family:sans-serif;padding:16px'>レポートが見つかりません。クロールを実行してください。</p>",
            mimetype="text/html",
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Response(status=500)
    screens_meta = report.get("screens") or []
    if kind == "autorun":
        from generator.heatmap_reporter import generate_autorun_coverage_html

        html_out = generate_autorun_coverage_html(
            _autorun_coverage_screens(domain_dir, screens_meta)
        )
    else:
        from generator.heatmap_reporter import generate_analysis_coverage_html

        html_out = generate_analysis_coverage_html(
            _analysis_coverage_screens(domain_dir / "screenshots", screens_meta)
        )
    resp = Response(html_out, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/open")
def open_file() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is not None:
        subprocess.Popen(["open", str(target)])
    return make_response(redirect(url_for("pages.index")))
