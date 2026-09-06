"""02（テスト自動化）・03（AutoRun）の失敗を、05 の欠陥に変換する。

このモジュールが「壊れたら直る」の入口。E2E が落ちた事実を、
どの画面の・どのテストが・どう失敗したかを保ったまま 05 へ渡す。

02/03 の失敗情報には**製品コードの場所が入っていない**。
Playwright のスタック（.spec.ts の行番号）と画面 ID しか無いため、
「URL → 製品ファイル」の限局は localization 側の責任になる。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from web.services.healing.types import Defect

logger = logging.getLogger(__name__)

#: テスト名の先頭に付く ID から画面 ID を取り出す。TC-P003-ST-002 → P003
_CASE_ID_RE = re.compile(r"\bTC-(P\d{3})-")
#: テスト名から ID 部分を取り除いて、人が読む部分だけにする。
_CASE_PREFIX_RE = re.compile(r"^TC-[A-Z0-9-]+\s*")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("読めません: %s (%s)", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _report_candidates(out_dir: Path, domain: str, run_id: str) -> list[Path]:
    """実行結果の探索順。run_id があればそのスナップショットを先に見る。"""
    paths: list[Path] = []
    if run_id:
        try:
            from web.services import run_store as autorun_run_store

            paths.append(
                autorun_run_store.run_dir(out_dir, domain, run_id) / "playwright_report.json"
            )
        except Exception:  # noqa: BLE001 - スナップショットが無くても続ける
            logger.debug("実行スナップショットを解決できません", exc_info=True)
    base = Path(out_dir) / domain
    paths.append(base / "qa_process" / "playwright_report.json")
    paths.append(base / "testcases" / "playwright_report.json")
    return paths


def _screen_index(out_dir: Path, domain: str) -> dict[str, dict[str, str]]:
    """画面 ID → {url, title}。01 が作った report.json から引く。"""
    data = _load_json(Path(out_dir) / domain / "report.json")
    index: dict[str, dict[str, str]] = {}
    for screen in (data or {}).get("screens") or []:
        if not isinstance(screen, Mapping):
            continue
        page_id = str(screen.get("page_id") or "")
        if page_id:
            index[page_id] = {
                "url": str(screen.get("url") or ""),
                "title": str(screen.get("title") or ""),
            }
    return index


def _slug(text: str) -> str:
    """テスト名からスクリーンショットのファイル名に使われる形を作る。"""
    return re.sub(r"[^0-9a-zA-Z]+", "-", text).strip("-").lower()


def _find_screenshot(out_dir: Path, domain: str, title: str) -> str:
    """失敗時のスクリーンショットを探す。out_dir からの相対パスを返す。

    Playwright は test-results/<テスト名のスラッグ>/... に置く。
    完全一致は期待できないので、スラッグの一部を含むものから最新を選ぶ。
    """
    root = Path(out_dir) / domain / "test-results"
    if not root.is_dir():
        return ""
    slug = _slug(title)[:40]
    if not slug:
        return ""
    best: tuple[float, Path] | None = None
    for png in root.rglob("*.png"):
        if slug[:20] not in _slug(str(png.relative_to(root))):
            continue
        try:
            mtime = png.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, png)
    if best is None:
        return ""
    try:
        return str(best[1].relative_to(Path(out_dir)))
    except ValueError:
        return ""


def _spec_path_for_report(report_path: Path) -> str:
    """使った実行結果 JSON と同じディレクトリにある .spec.ts を探す。

    見つからなければ空にする（フォールバック探索は script_fix.find_spec 側が持つ）。
    """
    folder = report_path.parent
    for name in ("testcases.spec.ts", "autorun.spec.ts"):
        candidate = folder / name
        if candidate.is_file():
            return str(candidate)
    return ""


def _defect_from_test(
    test: Mapping[str, Any],
    *,
    screens: Mapping[str, Mapping[str, str]],
    out_dir: Path,
    domain: str,
    spec_path: str = "",
) -> Defect:
    title = str(test.get("title") or "")
    error = str(test.get("error") or "")
    match = _CASE_ID_RE.search(title)
    screen_id = match.group(1) if match else ""
    screen = screens.get(screen_id, {})
    case_id = title.split(" ", 1)[0] if title.startswith("TC-") else ""
    test_title = _CASE_PREFIX_RE.sub("", title).strip()

    return Defect(
        defect_id=hashlib.sha1(  # noqa: S324 - 識別子であって暗号用途ではない
            (case_id or title).encode("utf-8")
        ).hexdigest()[:12],
        title=(error.splitlines()[0] if error else title)[:80],
        severity="high",
        source="autorun",
        test_id=case_id or title,
        message=error[:500] or f"{title} が失敗しました",
        evidence=error,
        detected_at="",
        url=screen.get("url", ""),
        screen_id=screen_id,
        screen_name=screen.get("title", ""),
        test_title=test_title,
        screenshot=_find_screenshot(out_dir, domain, title),
        spec_path=spec_path,
    )


def load_failures(
    out_dir: Path,
    domain: str,
    *,
    run_id: str = "",
    test_ids: Sequence[str] = (),
) -> list[Defect]:
    """02/03 の実行結果から、失敗したテストを欠陥として取り出す。

    test_ids を渡すと、その TC-ID を含むテストだけに絞る。
    """
    report: dict[str, Any] | None = None
    matched_path: Path | None = None
    for path in _report_candidates(out_dir, domain, run_id):
        report = _load_json(path)
        if report is not None and report.get("tests") is not None:
            logger.info("実行結果を読みました: %s", path)
            matched_path = path
            break
        report = None
    if report is None:
        return []

    spec_path = _spec_path_for_report(matched_path) if matched_path else ""
    wanted = {str(t) for t in test_ids if str(t).strip()}
    screens = _screen_index(out_dir, domain)
    defects: list[Defect] = []
    for test in report.get("tests") or []:
        if not isinstance(test, Mapping):
            continue
        if str(test.get("status") or "") == "passed":
            continue
        title = str(test.get("title") or "")
        if wanted and not any(tid in title for tid in wanted):
            continue
        defects.append(
            _defect_from_test(
                test, screens=screens, out_dir=out_dir, domain=domain, spec_path=spec_path
            )
        )
    return defects


def summarize_failures(defects: Iterable[Defect]) -> str:
    """ログに 1 行で残すための要約。"""
    items = list(defects)
    if not items:
        return "失敗したテストはありません"
    heads = "、".join(d.test_id or d.title for d in items[:3])
    more = f" ほか {len(items) - 3} 件" if len(items) > 3 else ""
    return f"{len(items)} 件の失敗（{heads}{more}）"
