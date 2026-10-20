from __future__ import annotations

import json
import os
import signal as signal_module
import subprocess

from web.services.browser_blocked import BLOCKED_MESSAGE, is_browser_unavailable
import sys
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.tenancy import scoped_output_dir
from web.validation import _domain_of, _safe_auth_path, _valid_domain, _valid_url

bp = Blueprint("record", __name__)


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


# キャプチャ＆リプレイ（操作を記録して作る）の出力ファイル名。
# ドット始まり = report 出力と混同しない（login.py の認証フローレコーダーと同じ流儀）。
RECORD_SIGNAL_FILE_NAME = ".record_signal"
RECORD_STATUS_FILE_NAME = ".record_status.json"
DEFAULT_RECORD_STATUS = {"phase": "idle"}

_FINALIZE_TIMEOUT_SEC = 600
_STOP_WAIT_SEC = 3.0
_STOP_POLL_INTERVAL_SEC = 0.25
_MAX_NAVIGATE_URLS = 30
_IMPORT_SUFFIXES = frozenset({".json", ".side"})
_MAX_IMPORT_BYTES = 20 * 1024 * 1024  # 20MB


def _clean_domain_name(raw: str) -> str:
    """crawl.py の domain_name 検証と同じ規則（パストラバーサル防止）。"""
    dn = raw.strip()
    if dn in {".", ".."} or "/" in dn or "\\" in dn:
        return ""
    return dn


def _resolve_domain(url: str, domain_name: str) -> str:
    """domain_name（明示）があれば優先し、無ければ URL のホストから決める。"""
    dn = _clean_domain_name(domain_name)
    if dn:
        return dn
    return _domain_of(url) if url else ""


def _latest_flow_path(domain_dir: Path) -> Path | None:
    """`sessions/session_*.flow.json` の最新（連番なので辞書順 = 時系列順）。"""
    sessions_dir = domain_dir / "sessions"
    if not sessions_dir.is_dir():
        return None
    candidates = sorted(sessions_dir.glob("session_*.flow.json"))
    return candidates[-1] if candidates else None


def _flow_navigate_urls(flow_path: Path, limit: int = _MAX_NAVIGATE_URLS) -> list[str]:
    """user-flow JSON の navigate step から遷移 URL を順序維持・重複除去で取り出す。"""
    try:
        flow = json.loads(flow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    steps = flow.get("steps")
    if not isinstance(steps, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "navigate":
            continue
        url = str(step.get("url", "")).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _run_stage(cmd: list[str]) -> tuple[bool, str]:
    """CLI 段を同期実行する。失敗しても例外を投げず (ok, detail) を返す。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_FINALIZE_TIMEOUT_SEC
        )
    except subprocess.TimeoutExpired:
        return False, "タイムアウトしました"
    except OSError as exc:
        return False, f"実行に失敗しました: {exc}"
    if proc.returncode == 0:
        return True, ""
    if is_browser_unavailable(proc.stderr, proc.stdout):
        return False, BLOCKED_MESSAGE
    tail = (proc.stderr or proc.stdout or "").strip()
    return False, tail[-400:] if tail else f"exit code {proc.returncode}"


def _existing_files(domain_dir: Path, names: list[str]) -> list[str]:
    return [name for name in names if (domain_dir / name).exists()]


def _run_named_stage(
    name: str, cmd: list[str], domain_dir: Path, expected_files: list[str]
) -> dict[str, Any]:
    """finalize の 1 段を実行し、成否と生成ファイル名を steps[] の 1 要素として返す。"""
    ok, detail = _run_stage(cmd)
    if ok:
        produced = _existing_files(domain_dir, expected_files)
        return {"name": name, "ok": True, "detail": ", ".join(produced) if produced else "完了"}
    return {"name": name, "ok": False, "detail": detail}


@bp.post("/api/record/start")
def api_record_start() -> tuple[dict, int] | dict:
    """記録用ブラウザを起動する。ブラウザは非ブロッキングで起動し、
    進行は /api/record/status のポーリングで検知する。"""
    url = request.form.get("url", "").strip()
    if not url or not _valid_url(url):
        return {"ok": False, "error": "URLを指定してください"}, 400
    domain = _resolve_domain(url, request.form.get("domain_name", ""))
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを特定できません"}, 400
    auth = _safe_auth_path(request.form.get("auth", "").strip())

    domain_dir = _out() / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    signal_path = domain_dir / RECORD_SIGNAL_FILE_NAME
    status_path = domain_dir / RECORD_STATUS_FILE_NAME
    # 前回セッションの残骸（シグナル・状態ファイル）を持ち越さない
    for stale in (signal_path, status_path):
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass

    cmd = [
        sys.executable,
        "src/main.py",
        "--record-session",
        "--url",
        url,
        "--record-signal",
        str(signal_path),
        "--record-status",
        str(status_path),
        "--domain-name",
        domain,
    ]
    if auth:
        cmd += ["--auth", auth]
    try:
        proc = subprocess.Popen(cmd)
    except OSError as exc:
        return {"ok": False, "error": f"記録の起動に失敗しました: {exc}"}, 500
    return {"ok": True, "pid": proc.pid, "domain": domain, "status_path": str(status_path)}


@bp.get("/api/record/status")
def api_record_status() -> tuple[dict, int] | dict:
    """記録の進行状態をポーリングする（1秒間隔想定）。"""
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    status_path = _out() / domain / RECORD_STATUS_FILE_NAME
    if not status_path.exists():
        return dict(DEFAULT_RECORD_STATUS)
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 書き込み途中で読んだ場合など。次回ポーリングに任せる
        return dict(DEFAULT_RECORD_STATUS)
    return data if isinstance(data, dict) else dict(DEFAULT_RECORD_STATUS)


@bp.post("/api/record/stop")
def api_record_stop() -> tuple[dict, int] | dict:
    """記録を終了する。シグナルファイルで自然終了を促し、応答が無ければ SIGTERM する。"""
    domain = request.form.get("domain", "").strip()
    pid_text = request.form.get("pid", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    if not pid_text or not pid_text.isdigit():
        return {"ok": False, "error": "pidを指定してください"}, 400

    domain_dir = _out() / domain
    signal_path = domain_dir / RECORD_SIGNAL_FILE_NAME
    status_path = domain_dir / RECORD_STATUS_FILE_NAME
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal_path.touch()

    deadline = time.monotonic() + _STOP_WAIT_SEC
    stopped = False
    while time.monotonic() < deadline:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and data.get("phase") == "stopped":
            stopped = True
            break
        time.sleep(_STOP_POLL_INTERVAL_SEC)
    if not stopped:
        try:
            os.kill(int(pid_text), signal_module.SIGTERM)
        except ProcessLookupError:
            pass  # 既に終了済み
        except OSError as exc:
            return {"ok": False, "error": f"停止に失敗しました: {exc}"}, 500
    return {"ok": True}


@bp.post("/api/record/finalize")
def api_record_finalize() -> tuple[dict, int] | dict:
    """記録済みセッションから文書一式を同期生成する（クロール→逆生成→カバレッジ→気づき票）。

    各段は独立して失敗しうるが、finalize 自体は例外を投げず steps[] に成否を積む
    （司令塔の検証手順どおり、部分成功でも評価できるようにする）。
    """
    domain = request.form.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    auth = _safe_auth_path(request.form.get("auth", "").strip())

    out_dir = _out()
    domain_dir = out_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    flow_path = _latest_flow_path(domain_dir)
    flow_urls = _flow_navigate_urls(flow_path) if flow_path else []
    primary_url = flow_urls[0] if flow_urls else f"https://{domain}/"

    steps: list[dict[str, Any]] = []

    report_path = domain_dir / "report.json"
    if report_path.exists():
        steps.append({"name": "crawl", "ok": True, "detail": "report.json は既に存在します"})
    elif not flow_urls:
        steps.append(
            {"name": "crawl", "ok": False, "detail": "記録セッションの遷移URLが見つかりません"}
        )
    else:
        crawl_cmd = [
            sys.executable,
            "src/main.py",
            "--urls",
            ",".join(flow_urls),
            "--format",
            "md,html,json",
            "--output",
            str(out_dir),
            "--domain-name",
            domain,
        ]
        if auth:
            crawl_cmd += ["--auth", auth]
        ok, detail = _run_stage(crawl_cmd)
        steps.append(
            {
                "name": "crawl",
                "ok": ok,
                "detail": detail if not ok else f"{len(flow_urls)}件のURLをクロールしました",
            }
        )

    steps.append(
        _run_named_stage(
            "reverse-assets",
            [
                sys.executable,
                "src/main.py",
                "--reverse-assets",
                "--url",
                primary_url,
                "--output",
                str(out_dir),
                "--domain-name",
                domain,
            ],
            domain_dir,
            ["recorded_assets.json", "recorded_candidates.json"],
        )
    )
    steps.append(
        _run_named_stage(
            "exploration-coverage",
            [
                sys.executable,
                "src/main.py",
                "--exploration-coverage",
                "--url",
                primary_url,
                "--output",
                str(out_dir),
                "--domain-name",
                domain,
            ],
            domain_dir,
            ["exploration_heatmap.html", "exploration_burndown.html"],
        )
    )
    steps.append(
        _run_named_stage(
            "export-findings",
            [
                sys.executable,
                "src/main.py",
                "--export-findings",
                "--url",
                primary_url,
                "--output",
                str(out_dir),
                "--domain-name",
                domain,
            ],
            domain_dir,
            ["findings.json", "findings.csv"],
        )
    )

    return {"ok": all(step["ok"] for step in steps), "steps": steps, "domain": domain}


@bp.post("/api/record/replay")
def api_record_replay() -> tuple[dict, int] | dict:
    """最新の記録セッションをリプレイし、replays/<name>.json の中身を返す。"""
    domain = request.form.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    base_url = request.form.get("base_url", "").strip()
    if base_url and not _valid_url(base_url):
        return {"ok": False, "error": "base_url が不正です"}, 400

    out_dir = _out()
    domain_dir = out_dir / domain
    cmd = [
        sys.executable,
        "src/main.py",
        "--replay-session",
        "latest",
        "--output",
        str(out_dir),
        "--domain-name",
        domain,
    ]
    if base_url:
        cmd += ["--replay-base-url", base_url]
    ok, detail = _run_stage(cmd)
    if not ok:
        return {"ok": False, "error": detail or "リプレイに失敗しました"}, 500

    replays_dir = domain_dir / "replays"
    candidates = (
        sorted(replays_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if replays_dir.is_dir()
        else []
    )
    if not candidates:
        return {"ok": False, "error": "リプレイ結果が見つかりません"}, 500
    try:
        result = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"リプレイ結果を読み込めません: {exc}"}, 500
    return result if isinstance(result, dict) else {"ok": False, "error": "不正な結果形式です"}


@bp.get("/api/record/sessions")
def api_record_sessions() -> tuple[dict, int] | list[dict[str, Any]]:
    """記録済みセッション一覧（flow.json ベース）。"""
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400

    domain_dir = _out() / domain
    sessions_dir = domain_dir / "sessions"
    has_assets = (domain_dir / "recorded_assets.json").exists()
    rows: list[dict[str, Any]] = []
    if sessions_dir.is_dir():
        for flow_path in sorted(sessions_dir.glob("session_*.flow.json")):
            try:
                flow = json.loads(flow_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            meta = flow.get("ws2d")
            meta = meta if isinstance(meta, dict) else {}
            steps = flow.get("steps")
            session_name = meta.get("session") or flow_path.name.removesuffix(".flow.json")
            rows.append(
                {
                    "session": session_name,
                    "flow_path": str(flow_path.relative_to(domain_dir)),
                    "events": len(steps) if isinstance(steps, list) else 0,
                    "recorded_at": meta.get("recorded_at", ""),
                    "has_assets": has_assets,
                }
            )
    return rows


@bp.post("/api/record/import")
def api_record_import() -> tuple[dict, int] | dict:
    """Chrome DevTools Recorder（.json）/ Selenium IDE（.side）の記録を取り込む。"""
    domain = request.form.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return {"ok": False, "error": "ファイルが指定されていません"}, 400

    # secure_filename は非ASCIIを全て落とすため使わない（reference-docs と同じ流儀）。
    # Path(...).name でディレクトリ部のみ剥がし、拡張子 allowlist で安全性を担保する。
    name = Path(uploaded.filename).name
    suffix = Path(name).suffix.lower()
    if suffix not in _IMPORT_SUFFIXES:
        return {"ok": False, "error": f"未対応の形式です（.json/.side のみ）: {name}"}, 400
    data = uploaded.read()
    if len(data) > _MAX_IMPORT_BYTES:
        return {
            "ok": False,
            "error": f"ファイルサイズが上限（{_MAX_IMPORT_BYTES // (1024 * 1024)}MB）を超えています",
        }, 400

    out_dir = _out()
    domain_dir = out_dir / domain
    imports_dir = domain_dir / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    dest = imports_dir / name
    dest.write_bytes(data)

    cmd = [
        sys.executable,
        "src/main.py",
        "--import-recording",
        str(dest),
        "--output",
        str(out_dir),
        "--domain-name",
        domain,
    ]
    ok, detail = _run_stage(cmd)
    if not ok:
        return {"ok": False, "error": detail or "取り込みに失敗しました"}, 500

    flow_path = _latest_flow_path(domain_dir)
    return {
        "ok": True,
        "domain": domain,
        "flow_path": str(flow_path.relative_to(domain_dir)) if flow_path else "",
    }
