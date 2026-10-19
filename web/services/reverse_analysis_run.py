"""System 01 のサイトに対してリバース解析を実行する（画面からの実行用）。

CLI（``main.py --reverse-analysis``）と同じ ``reverse_analysis.service.run_reverse_analysis`` を呼ぶ。
画面専用の解析ロジックは持たず、ここで行うのは次の 3 つだけ:

1. 対象サイトの解決: ``<出力>/<domain>/snapshots`` の最新 snapshot を実行時記録として使う
2. 静的解析の入力の用意: snapshot に記録されたページから、同じホストの JS（と source map）を取得して保存
3. 実行記録 ``run.json`` の保存（対象・snapshot の digest・所要時間・Before/After の件数）

置き場所: ``<出力>/<domain>/reverse_analysis/``
  result/reverse_analysis.json  解析結果（service の専用出力先）
  inputs/                       取得した JS と source map（次回実行で置き換える）
  run.json                      実行記録。結果と対象サイトを結び付ける
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

RA_DIR = "reverse_analysis"
RESULT_DIR = "result"
INPUTS_DIR = "inputs"
RUN_FILE = "run.json"
RESULT_FILE = "reverse_analysis.json"

_DEFAULT_REA = Path.home() / ".local/share/webspec2doc-tools/rea-6.7.0/bin/rea"
_MAX_PAGES = 20
_MAX_SCRIPTS = 40
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 40 * 1024 * 1024
_FETCH_TIMEOUT = 10.0
_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]")
_SOURCE_MAP = re.compile(rb"//[#@]\s*sourceMappingURL=([^\s'\"]+)\s*$")
_JST = timezone(timedelta(hours=9))

_running: set[str] = set()
_running_lock = threading.Lock()


@dataclass(frozen=True)
class RunResult:
    result: str  # success | partial | error | provider_unavailable | busy | no_runtime
    message: str
    next_action: str


@dataclass(frozen=True)
class ProviderStatus:
    available: bool
    version: str | None
    reason: str | None
    next_action: str | None


def rea_command() -> str:
    """REA 実行ファイル。画面からは変えられない（環境変数か既定の導入先だけ）。"""
    return os.environ.get("WEBSPEC2DOC_REA_COMMAND") or str(_DEFAULT_REA)


def site_dir(base: Path, domain: str) -> Path:
    return base / domain / RA_DIR


def is_running(domain: str) -> bool:
    with _running_lock:
        return domain in _running


def latest_snapshot(base: Path, domain: str) -> Path | None:
    snaps = sorted((base / domain / "snapshots").glob("*.json"))
    return snaps[-1] if snaps else None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_provider_cache: dict[tuple[str, float], ProviderStatus] = {}


def provider_status() -> ProviderStatus:
    """REA が使えるか。版確認（--version）は実行ファイルの更新時刻ごとに 1 回だけ行う。"""
    command = rea_command()
    path = Path(command)
    if not path.is_file() or not os.access(path, os.X_OK):
        return ProviderStatus(
            False, None, "静的解析ツール（REA）が導入されていません。",
            "管理者に REA 6.7.0 の導入を依頼してください。",
        )  # fmt: skip
    try:
        from reverse_analysis.rea_adapter import probe_version
    except ImportError:
        return ProviderStatus(
            False, None, "リバース解析の機能がこの環境に含まれていません。",
            "管理者にリバース解析機能の導入を依頼してください。",
        )  # fmt: skip
    key = (command, path.stat().st_mtime)
    cached = _provider_cache.get(key)
    if cached is not None:
        return cached
    version, diag = probe_version(command)
    status = (
        ProviderStatus(True, version, None, None)
        if diag is None
        else ProviderStatus(False, version, diag.message, diag.next_action)
    )
    _provider_cache.clear()
    _provider_cache[key] = status
    return status


# ------------------------------------------------------------------ JS の取得


class _ScriptSrc(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            src = dict(attrs).get("src")
            if src:
                self.srcs.append(src)


def _fetch(url: str, limit: int) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "WebSpec2Doc reverse-analysis"})
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # noqa: S310 (http/https のみ)
            body = resp.read(limit + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return body if len(body) <= limit else None


def _same_host(url: str, domain: str) -> bool:
    """System 01 がこのサイトの保存先に使う名前（ポート込み）と一致する URL だけを許す。"""
    from crawler.url_safety import domain_key_from_url

    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and domain_key_from_url(url) == domain


def _local_path(root: Path, url: str) -> Path:
    parts = [_SAFE_SEGMENT.sub("_", p) for p in urlparse(url).path.split("/") if p not in ("", ".", "..")]
    return root.joinpath(*(parts or ["index.js"]))


def capture_scripts(pages: list[str], domain: str, dest: Path) -> tuple[int, int]:
    """記録済みページから同じホストの JS と source map を保存する。戻り値は (JS 数, map 数)。"""
    seen: set[str] = set()
    scripts = maps = total = 0
    for page in [p for p in pages if _same_host(p, domain)][:_MAX_PAGES]:
        html = _fetch(page, _MAX_FILE_BYTES)
        if html is None:
            continue
        parser = _ScriptSrc()
        parser.feed(html.decode("utf-8", "replace"))
        for src in parser.srcs:
            url = urljoin(page, src).split("#", 1)[0]
            if url in seen or not _same_host(url, domain) or scripts >= _MAX_SCRIPTS:
                continue
            seen.add(url)
            body = _fetch(url, _MAX_FILE_BYTES)
            if body is None or total + len(body) > _MAX_TOTAL_BYTES:
                continue
            target = _local_path(dest, url)
            if target.suffix not in (".js", ".mjs", ".cjs"):
                target = target.with_name(target.name + ".js")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            scripts += 1
            total += len(body)
            match = _SOURCE_MAP.search(body[-2048:])
            if not match:
                continue
            map_url = urljoin(url, match.group(1).decode("ascii", "replace"))
            map_body = _fetch(map_url, _MAX_FILE_BYTES) if _same_host(map_url, domain) else None
            if map_body is not None and total + len(map_body) <= _MAX_TOTAL_BYTES:
                map_target = target.with_name(target.name + ".map")
                map_target.write_bytes(map_body)
                maps += 1
                total += len(map_body)
    return scripts, maps


# ------------------------------------------------------------------ 実行


def _metrics(doc: dict[str, Any] | None, runtime_calls: int) -> dict[str, int]:
    static = (doc or {}).get("static_candidates", [])
    edges = ((doc or {}).get("provider_evidence") or {}).get("dependency_edges", [])
    return {
        "static_candidates": len(static),
        "route_candidates": sum(1 for c in static if c.get("kind") == "route"),
        "api_candidates": sum(1 for c in static if c.get("kind") == "api"),
        "module_dependency_edges": len(edges),
        "source_mapped_evidence": sum(1 for c in static if c.get("kind") == "source"),
        "runtime_observations": runtime_calls,
    }


def run_for_site(base: Path, domain: str) -> RunResult:
    with _running_lock:
        if domain in _running:
            return RunResult("busy", "このサイトのリバース解析はすでに実行中です。", "完了まで待ってから結果を確認してください。")
        _running.add(domain)
    try:
        return _run(base, domain)
    finally:
        with _running_lock:
            _running.discard(domain)


def _run(base: Path, domain: str) -> RunResult:
    snapshot = latest_snapshot(base, domain)
    if snapshot is None:
        return RunResult("no_runtime", "このサイトの実行時記録がありません。", "先にドキュメント作成でサイトを解析してください。")
    provider = provider_status()
    if not provider.available:
        return RunResult("provider_unavailable", provider.reason or "静的解析ツールを利用できません。",
                         provider.next_action or "管理者に確認してください。")
    pages_raw = json.loads(snapshot.read_text(encoding="utf-8"))
    pages = [p.get("url", "") for p in pages_raw if isinstance(p, dict)]
    runtime_calls = sum(len(p.get("api_calls") or []) for p in pages_raw if isinstance(p, dict))

    root = site_dir(base, domain)
    inputs = root / INPUTS_DIR
    fresh = root / (INPUTS_DIR + ".new")
    if fresh.exists():
        shutil.rmtree(fresh)  # 前回中断した取得の残り（このモジュールが作ったものだけ）
    fresh.mkdir(parents=True)
    started = datetime.now(_JST)
    scripts, maps = capture_scripts(pages, domain, fresh)
    if scripts == 0:
        shutil.rmtree(fresh)
        return RunResult("error", "サイトから JavaScript を取得できませんでした。結果は更新していません。",
                         "サイトが開けるか確認し、時間をおいて再実行してください。")
    if inputs.exists():
        shutil.rmtree(inputs)  # 取得できたときだけ前回の JS を置き換える
    fresh.rename(inputs)

    from reverse_analysis.service import ReverseAnalysisRequest, run_reverse_analysis

    request = ReverseAnalysisRequest(
        js_input=str(inputs), runtime_snapshot=str(snapshot), rea_command=rea_command(),
        output_dir=str(root / RESULT_DIR), include_provider_evidence=True,
    )  # fmt: skip
    t0 = time.monotonic()
    try:
        outcome = run_reverse_analysis(request)
    except (OSError, RuntimeError):
        return RunResult("error", "リバース解析を完了できませんでした。結果は更新していません。", "時間をおいて再実行してください。")
    seconds = round(time.monotonic() - t0, 3)
    if outcome.output_path is None or outcome.document is None:
        first = outcome.diagnostics[0] if outcome.diagnostics else None
        return RunResult("error", first.message if first else "結果を保存できませんでした。",
                         first.next_action if first else "時間をおいて再実行してください。")
    status = outcome.document.get("status")
    run = {
        "domain": domain,
        "snapshot": snapshot.name,
        "snapshot_sha256": sha256_file(snapshot),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(_JST).isoformat(timespec="seconds"),
        "seconds": seconds,
        "status": status,
        "provider_version": provider.version,
        "js_files": scripts,
        "source_maps": maps,
        "repetitions": 1,
        "before": _metrics(None, runtime_calls),
        "after": _metrics(outcome.document, runtime_calls),
    }
    (root / RUN_FILE).write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    if status == "complete":
        return RunResult("success", "解析が完了しました。", "増えた根拠を下の一覧で確認してください。")
    if status == "partial":
        return RunResult("partial", "取得できなかった部分は利用不可として表示しています。",
                         "診断タブで取得できなかった理由を確認してください。")
    return RunResult("error", "リバース解析は失敗しました。", "診断タブで理由を確認して再実行してください。")
