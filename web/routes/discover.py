from __future__ import annotations

import json
import subprocess
import sys
import uuid

from flask import Blueprint, Response, request

from web.config import DISCOVER_TIMEOUT_SEC, MAX_DEPTH, MAX_PAGES_LIMIT
from web.process import _RUNNING_PROCS, _terminate_proc
from web.validation import _clean_int, _safe_auth_path

bp = Blueprint("discover", __name__)


@bp.post("/api/discover")
def api_discover() -> Response | tuple[dict, int] | dict:
    url = request.form.get("url", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    if not url:
        return {"pages": [], "error": "URLを入力してください"}, 400
    cmd = [
        sys.executable,
        "src/main.py",
        "--discover",
        "--url",
        url,
        "--depth",
        depth,
        "--max-pages",
        max_pages,
    ]
    if auth:
        cmd += ["--auth", auth]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DISCOVER_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"pages": [], "error": "画面リスト取得がタイムアウトしました"}, 504
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"pages": [], "error": "画面リストの解析に失敗しました"}, 500
    return {"pages": data.get("pages", [])}


@bp.post("/api/discover-stream")
def api_discover_stream() -> Response | tuple[dict, int]:
    """発見ページを SSE（text/event-stream）でリアルタイム配信する。"""
    url = request.form.get("url", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    if not url:
        return {"error": "URLを入力してください"}, 400
    cmd = [
        sys.executable,
        "src/main.py",
        "--discover",
        "--stream",
        "--url",
        url,
        "--depth",
        depth,
        "--max-pages",
        max_pages,
    ]
    if auth:
        cmd += ["--auth", auth]

    run_id = uuid.uuid4().hex

    def generate():
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            # 中断ボタンから /api/cancel 経由でこのプロセスを止められるよう登録する
            # （画面分析フェーズには停止手段が無い、というドッグフーディング要望への対応）。
            _RUNNING_PROCS[run_id] = proc
            yield f"data: {json.dumps({'run_id': run_id})}\n\n"
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if line:
                    yield f"data: {line}\n\n"
            proc.wait()
            if proc.returncode is not None and proc.returncode < 0:
                yield f"data: {json.dumps({'cancelled': True})}\n\n"
            elif proc.returncode != 0:
                yield f"data: {json.dumps({'error': '画面リスト取得に失敗しました'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            _RUNNING_PROCS.pop(run_id, None)
            if proc is not None:
                _terminate_proc(proc)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
