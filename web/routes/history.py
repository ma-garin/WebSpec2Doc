from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

from web.config import OUTPUT_DIR, SAMPLE_DOMAIN
from web.services import run_store
from web.summary import _fmt_snap_ts, _summary_for_domain
from web.tenancy import scoped_output_dir
from web.validation import _safe_output_path, _valid_domain

bp = Blueprint("history", __name__)
logger = logging.getLogger(__name__)


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


@bp.get("/api/history")
def api_history() -> dict:
    items: list[dict] = []
    out_dir = _out()
    if out_dir.is_dir():
        from web.tenancy import TENANTS_DIR_NAME

        # ドット始まり（.playwright_env 等の隠しディレクトリ）と
        # テナント領域（tenants/）はサイトではないため除外。
        # 同梱サンプル（P3-1）は利用者が解析したサイトではないため、自分の解析結果と
        # 混ざらないよう履歴からも件数からも外す。
        domains = [
            d
            for d in out_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name != TENANTS_DIR_NAME
            and d.name != SAMPLE_DOMAIN
        ]
        for d in sorted(domains, key=lambda p: p.stat().st_mtime, reverse=True):
            from registry.site_registry import load_site

            summary = _summary_for_domain(d.name, out_dir)
            site = load_site(d.name, out_dir)
            site_url = site.urls[0] if site and site.urls else ""
            formats = [
                name
                for name, fname in (
                    ("HTML", "report.html"),
                    ("PDF", "report.pdf"),
                    ("Excel", "spec.xlsx"),
                    ("JSON", "report.json"),
                    ("MD", "screens.md"),
                    ("差分", "diff_report.html"),
                )
                if (d / fname).exists()
            ]
            snap_dir = d / "snapshots"
            snapshot_count = len(list(snap_dir.glob("*.json"))) if snap_dir.is_dir() else 0
            mtime = d.stat().st_mtime
            items.append(
                {
                    "domain": d.name,
                    "site_url": site_url,
                    "screens": summary.get("screens", 0),
                    "fields": summary.get("fields", 0),
                    "updated": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                    "updated_ts": int(mtime),
                    "formats": formats,
                    "snapshot_count": snapshot_count,
                    "has_diff": (d / "diff_report.html").exists(),
                }
            )
    return {"items": items}


@bp.delete("/api/site/<domain>")
def api_delete_site(domain: str) -> dict | tuple[dict, int]:
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    out_dir = _out()
    target_dir = out_dir / domain
    # テナントスコープ済み出力ディレクトリの外に出ないことをローカル参照で確認
    # （_safe_output_path はモジュールレベルの定数を使うため、ここでは _out() 基準で検証する）
    try:
        resolved = target_dir.resolve()
        base = out_dir.resolve()
    except (OSError, ValueError):
        return {"error": "invalid path"}, 400
    if base not in resolved.parents:
        return {"error": "invalid path"}, 400
    if not target_dir.is_dir():
        return {"error": "not found"}, 404
    try:
        shutil.rmtree(str(target_dir))
    except Exception as e:
        logger.exception("サイト削除に失敗しました: domain=%s, error=%s", domain, e)
        return {"error": "内部エラーが発生しました。ログを確認してください。"}, 500
    return {"ok": True, "domain": domain}


@bp.get("/api/snapshots")
def api_snapshots() -> dict | tuple[dict, int]:
    """サイトのクロール履歴（スナップショット）一覧。新しい順。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    snaps_dir = _out() / domain / "snapshots"
    items: list[dict] = []
    if snaps_dir.is_dir():
        for f in sorted(snaps_dir.glob("*.json"), reverse=True):
            try:
                pages = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            forms = sum(len(p.get("forms", [])) for p in pages)
            fields = sum(len(fm.get("fields", [])) for p in pages for fm in p.get("forms", []))
            items.append(
                {
                    "id": f.stem,
                    "label": _fmt_snap_ts(f.stem),
                    "screens": len(pages),
                    "forms": forms,
                    "fields": fields,
                }
            )
    return {"snapshots": items}


@bp.get("/api/snapshot-diff")
def api_snapshot_diff() -> Response:
    """2つのスナップショット間の仕様ドリフト差分をHTMLで返す。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    snaps_dir = _out() / domain / "snapshots"
    from_path = _safe_output_path(str(snaps_dir / (request.args.get("from", "") + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (request.args.get("to", "") + ".json")))
    if from_path is None or to_path is None:
        return Response(
            "<p style='font-family:sans-serif;padding:16px'>指定されたスナップショットが見つかりません。</p>",
            mimetype="text/html",
        )
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot
        from generator.diff_reporter import generate_diff_report
    except ImportError:
        return Response(status=500)
    old_pages = load_snapshot(from_path)
    new_pages = load_snapshot(to_path)
    diff = compute_diff(old_pages, new_pages)
    report_html = generate_diff_report(
        diff=diff,
        old_label=_fmt_snap_ts(from_path.stem),
        new_label=_fmt_snap_ts(to_path.stem),
        target_url=f"https://{domain}/",
    )
    resp = Response(report_html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/api/snapshot-diff-summary")
def api_snapshot_diff_summary() -> dict | tuple[dict, int]:
    """2 時点間に仕様の変更があったかを JSON で返す（P2-1）。

    差分レポート本体は HTML で返しているため、画面側からは「変更 0 件」なのか
    「そもそも比較できていない」のかを区別できなかった。区別できないまま何も出さないと
    不在の証明になるため、件数を機械可読な形でも配信する。
    """
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    snaps_dir = _out() / domain / "snapshots"
    from_path = _safe_output_path(str(snaps_dir / (request.args.get("from", "") + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (request.args.get("to", "") + ".json")))
    if from_path is None or to_path is None or not from_path.exists() or not to_path.exists():
        return {"error": "snapshot not found"}, 404
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot
    except ImportError:
        logger.exception("差分モジュールの読み込みに失敗しました")
        return {"error": "diff unavailable"}, 500
    try:
        diff = compute_diff(load_snapshot(from_path), load_snapshot(to_path))
    except Exception:  # noqa: BLE001  # 壊れたスナップショットの形は事前に絞れない
        # ここで 500 を返しても画面は差分表本体を出せる。誤って「変更なし」と
        # 言わないことのほうが重要なので、握りつぶさず失敗として返す。
        logger.exception("スナップショットの比較に失敗しました: %s / %s", from_path, to_path)
        return {"error": "diff failed"}, 500
    return {
        "from": from_path.stem,
        "to": to_path.stem,
        "has_changes": bool(diff.has_changes),
        "counts": {
            "added_pages": len(diff.added_pages),
            "removed_pages": len(diff.removed_pages),
            "field_changes": len(diff.field_changes),
            "link_changes": len(diff.link_changes),
            "title_changes": len(diff.title_changes),
        },
    }


def _snapshot_not_found() -> Response:
    return Response(
        "<p style='font-family:sans-serif;padding:16px'>指定されたスナップショットが見つかりません。</p>",
        mimetype="text/html",
    )


@bp.get("/api/snapshot-comparison")
def api_snapshot_comparison() -> Response:
    """2つのスナップショット間を「現新比較（4分類）」でHTML化して返す。

    旧 `/api/snapshot-diff`（簡易ドリフト差分）は非破壊のため残置する。こちらは
    表示崩れ/文字化け/理解不可/操作不可の 4 分類レポート（現新比較ツール相当）。
    """
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    out_dir = _out()
    snaps_dir = out_dir / domain / "snapshots"
    from_path = _safe_output_path(str(snaps_dir / (request.args.get("from", "") + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (request.args.get("to", "") + ".json")))
    if from_path is None or to_path is None or not from_path.exists() or not to_path.exists():
        return _snapshot_not_found()
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from analyzer.html_analyzer import analyze_pages
        from diff.comparison import compare_analyzed_pages, load_dynamic_masks
        from diff.snapshot import load_snapshot
        from generator.comparison_reporter import generate_comparison_html
    except ImportError:
        logger.exception("現新比較モジュールの読み込みに失敗しました")
        return Response(status=500)
    try:
        old_pages = load_snapshot(from_path)
        new_pages = load_snapshot(to_path)
    except (OSError, json.JSONDecodeError):
        logger.exception("スナップショットの読み込みに失敗しました: domain=%s", domain)
        return Response(
            "<p style='font-family:sans-serif;padding:16px'>スナップショットの読み込みに失敗しました。</p>",
            mimetype="text/html",
        )
    old_analyzed = analyze_pages(old_pages)
    new_analyzed = analyze_pages(new_pages)
    # 現行側クロール時に永続化された動的マスク（あれば）を再利用する。無ければマスクなし。
    masks = load_dynamic_masks(out_dir / domain / "old")
    result = compare_analyzed_pages(
        old_analyzed,
        new_analyzed,
        dynamic_masks=masks,
        check_links=False,
    )
    resp = Response(generate_comparison_html(result), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/api/snapshot-comparison.json")
def api_snapshot_comparison_json() -> Response | tuple[dict, int]:
    """現新比較をペア単位の JSON で返す（現新比較ワークスペース用）。

    HTML を返す `/api/snapshot-comparison` は iframe に埋めるだけで操作できない。
    画面ペアを選ぶ・差分を辿る・根拠を見る、を画面上で行うために構造化して返す。
    """
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 404
    out_dir = _out()
    snaps_dir = out_dir / domain / "snapshots"
    from_key = request.args.get("from", "")
    to_key = request.args.get("to", "")
    from_path = _safe_output_path(str(snaps_dir / (from_key + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (to_key + ".json")))
    if from_path is None or to_path is None or not from_path.exists() or not to_path.exists():
        return {"error": "snapshot not found"}, 404
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from analyzer.html_analyzer import analyze_pages
        from diff.comparison import compare_analyzed_pages, load_dynamic_masks
        from diff.snapshot import load_snapshot
        from generator.comparison_reporter import comparison_result_to_dict
        from web.services.comparison_workspace import build_workspace
    except ImportError:
        logger.exception("現新比較モジュールの読み込みに失敗しました")
        return {"error": "comparison unavailable"}, 500
    try:
        old_analyzed = analyze_pages(load_snapshot(from_path))
        new_analyzed = analyze_pages(load_snapshot(to_path))
    except (OSError, json.JSONDecodeError):
        logger.exception("スナップショットの読み込みに失敗しました: domain=%s", domain)
        return {"error": "snapshot unreadable"}, 500

    # 差分画像は 2 時点の組み合わせごとに変わるため、その組み合わせ専用の置き場に作る。
    # 使い回すと、別の比較を開いたときに前の枠が残った画像を見せてしまう。
    diff_dir = out_dir / domain / "comparisons" / f"{from_key}__{to_key}"
    result = compare_analyzed_pages(
        old_analyzed,
        new_analyzed,
        dynamic_masks=load_dynamic_masks(out_dir / domain / "old"),
        check_links=False,
        new_dir=diff_dir,
    )
    # ScreenPair は page_id しか持たない。一覧に「P001」だけ並ぶとどの画面か分からないため、
    # 解析済みページから名前と URL を渡す。
    page_info = {
        page.page_id: {
            "title": str(page.page_data.title or page.page_id),
            "url": str(page.page_data.url or ""),
        }
        for page in [*old_analyzed, *new_analyzed]
    }
    payload = build_workspace(
        comparison_result_to_dict(result),
        out_dir,
        from_label=from_path.stem,
        to_label=to_path.stem,
        page_info=page_info,
    )
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---- 実行履歴の 1 行削除 ----
# 削除するのは「その実行回に固有のもの」だけ:
#   1. usage_log.jsonl の該当 1 行
#   2. output/<domain>/runs/<run_id>/
# current 側の成果物（output/<domain>/report.html など）は削除しない。あれは「最新」として
# 他の実行回と共有されており、消すと成果物を持たない履歴行まで開けなくなるため。

# run_id を持たない古い行を指すための予約語。パスに空文字は置けないため 1 文字で表す。
_NO_RUN_ID = "-"
# timestamp は完全一致でしか使わないが、異常に長い値を読み込ませない上限を設ける。
_MAX_TIMESTAMP_LEN = 64


def _usage_log_path(out_dir: Path) -> Path:
    """利用実績ログの実体（テナントスコープ済み出力ディレクトリ直下）。"""
    from web.services.usage_tracker import USAGE_LOG_FILE_NAME

    return out_dir / USAGE_LOG_FILE_NAME


def _match_usage_line(record: dict, domain: str, run_id: str, timestamp: str) -> bool:
    """その JSONL 行が削除対象かを判定する。"""
    if str(record.get("domain", "")) != domain:
        return False
    if run_id:
        return str(record.get("run_id", "")) == run_id
    # run_id を持たない古い行。timestamp は完全一致のみで見る。前方一致にすると
    # 同じ日の別の実行まで巻き込んで消してしまう。
    return bool(timestamp) and str(record.get("timestamp", "")) == timestamp


def _remove_usage_log_lines(out_dir: Path, domain: str, run_id: str, timestamp: str) -> int:
    """usage_log.jsonl から該当行を取り除き、除いた件数を返す。

    残す行は元の文字列のまま書き戻す（再シリアライズしない）。他の行のキー順や
    表記が削除のたびに変わると、履歴全体の diff が読めなくなるため。
    """
    log_path = _usage_log_path(out_dir)
    if not log_path.is_file():
        return 0
    original = log_path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    removed = 0
    for line in original:
        text = line.strip()
        # timestamp だけを手掛かりに消す場合は 1 行で打ち切る（同時刻の別行を巻き込まない）。
        done = removed >= 1 and not run_id
        if text and not done:
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                record = None
            if isinstance(record, dict) and _match_usage_line(record, domain, run_id, timestamp):
                removed += 1
                continue
        kept.append(line)
    if removed == 0:
        return 0
    # 書き込み中断で履歴全体を失わないよう、tmp へ書いてから差し替える（原子的置換）。
    tmp_path = log_path.with_name(log_path.name + ".tmp")
    body = "\n".join(kept)
    tmp_path.write_text(f"{body}\n" if body else "", encoding="utf-8")
    tmp_path.replace(log_path)
    return removed


def _remove_run_dir(out_dir: Path, domain: str, run_id: str) -> bool:
    """runs/<run_id>/ を削除する。消せる範囲をそこだけに限定する。"""
    target = run_store.run_dir(out_dir, domain, run_id)
    if target is None or not target.is_dir():
        return False
    # シンボリックリンクは辿らない（リンク先の実体を消させない）。
    if target.is_symlink():
        return False
    try:
        resolved = target.resolve()
        root = run_store.runs_root(out_dir, domain).resolve()
    except (OSError, ValueError):
        return False
    # 実体パスが runs/ の直下でなければ消さない。相対指定・リンク経由で
    # output/<domain>/ 本体や他サイトへ届く余地を残さないための最終確認。
    if resolved.parent != root or resolved.name != run_id:
        return False
    shutil.rmtree(str(resolved))
    return True


@bp.delete("/api/history/runs/<domain>/<run_id>")
def api_delete_run(domain: str, run_id: str) -> dict | tuple[dict, int]:
    """実行履歴の 1 行を削除する。

    run_id が無い古い行は run_id に "-" を、クエリ ``timestamp`` に元の ISO 文字列を渡す。
    """
    if not _valid_domain(domain):
        return {"ok": False, "error": "invalid domain"}, 400
    timestamp = (request.args.get("timestamp") or "").strip()
    if len(timestamp) > _MAX_TIMESTAMP_LEN:
        return {"ok": False, "error": "invalid timestamp"}, 400
    has_run_id = run_id != _NO_RUN_ID
    if has_run_id and not run_store.valid_run_id(run_id):
        return {"ok": False, "error": "invalid run_id"}, 400
    if not has_run_id and not timestamp:
        # 手掛かりが 1 つも無い状態で消しに行かせない（どの行が消えるか決まらない）。
        return {"ok": False, "error": "timestamp required"}, 400
    out_dir = _out()
    try:
        removed_lines = _remove_usage_log_lines(
            out_dir, domain, run_id if has_run_id else "", timestamp
        )
        # 一致行が 0 件でも成果物の削除は試みる。ログと成果物の片方だけが残った
        # 状態（退避後にログを消した等）を、この操作で解消できるようにする。
        removed_dir = _remove_run_dir(out_dir, domain, run_id) if has_run_id else False
    except Exception as exc:  # noqa: BLE001  # 破壊操作の失敗要因は事前に絞れない
        logger.exception(
            "実行履歴の削除に失敗しました: domain=%s run_id=%s (%s)", domain, run_id, exc
        )
        # 500 で落とすと画面側が理由を出せない。失敗も JSON で返して握りつぶさない。
        return {"ok": False, "error": "削除に失敗しました。ログを確認してください。"}
    return {"ok": True, "removed_log_lines": removed_lines, "removed_dir": removed_dir}
