"""保守対応報告書。オートヒーリングの成果物そのもの。

このシステムが売っているのは「修正」ではなく「顧客に出せる保守報告書」である。
判断とは「この報告書を顧客に出してよいか」を決めることで、PR はその副産物。

report.py（PR 本文用の Markdown）とは別物。あちらは開発者が GitHub 上で読むもの、
こちらは保守担当者が顧客へ提出するもので、節構成も語彙も違う。
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.healing import spec_match
from web.services.healing.report_present import CAUSE_MAX_CHARS as _CAUSE_MAX_CHARS
from web.services.healing.report_present import contradiction_note as _contradiction_note
from web.services.healing.report_present import display_report as _display_report
from web.services.healing.report_present import title_from_test_id, to_view_dict
from web.services.healing.report_present import truncate_sentences as _truncate_sentences
from web.services.healing.report_present import with_note as _with_note
from web.services.healing.risk import _parse_file_diffs
from web.services.healing.types import (
    Defect,
    FixProposal,
    HealingIteration,
    HealingProject,
    HealingRun,
    VerifyResult,
)

logger = logging.getLogger(__name__)

#: エージェント ID から報告書に書く表示名へ。顧客が読むので英字 ID を出さない。
_AGENT_LABELS: dict[str, str] = {
    "claude": "AI（Claude Code）",
    "codex": "AI（Codex）",
    "openai": "AI（OpenAI）",
    "ollama": "AI（Ollama・ローカル）",
    "dryrun": "動作確認用",
}

#: 本文の整形・字数・食い違いの判定は report_present に集約している。
#: この層は「保存する形」だけを持ち、表示のために作り直すことはしない。


@dataclass(frozen=True)
class MaintenanceReport:
    """保守対応報告書 1 件。1 欠陥 = 1 報告書。

    節の順序は画面・PDF・Markdown で共通:
    1 事象 → 2 原因 → 3 対応 → 4 検証 → 確認が必要な点 → 5 承認
    """

    report_id: str
    project_id: str
    project_name: str
    target_url: str
    run_id: str
    defect_id: str
    title: str
    status: str
    # 1. 事象
    incident_text: str = ""
    incident_detected_at: str = ""
    incident_source: str = ""  # monitor | manual | autorun
    incident_screen_id: str = ""
    incident_screen_name: str = ""
    incident_test_id: str = ""
    incident_screenshot: str = ""
    incident_verify: str = ""
    # 2. 原因
    cause_text: str = ""
    cause_location: str = ""
    # 3. 対応
    action_text: str = ""
    action_by: str = ""
    action_at: str = ""
    action_diff_stats: str = ""
    action_screenshot: str = ""
    # 4. 検証
    verify_before: str = ""
    verify_after: str = ""
    verify_after_ok: bool | None = None
    spec_match: str = "未照合"
    # 確認が必要な点（FixProposal.risks をそのまま持つ）
    attention: tuple[dict[str, Any], ...] = ()
    # 5. 承認
    approvals: tuple[dict[str, Any], ...] = ()
    pr_number: int = 0
    pr_url: str = ""
    created_at: str = ""
    updated_at: str = ""


# ─────────────────────────── 人の言葉にする ───────────────────────────


def _screen_prefix(defect: Defect) -> str:
    """件名の先頭に付ける画面名。分からなければ空にして「画面で」ごと落とす。"""
    name = (defect.screen_name or "").strip() or (defect.screen_id or "").strip()
    return f"{name}画面" if name else ""


def humanize_title(defect: Defect) -> str:
    """失敗の内容から、顧客に言える件名を組み立てる。

    LLM は使わない。件名は毎回同じ入力から同じ結果になる必要がある
    （報告書の一覧で並ぶものなので、揺れると探せない）。
    """
    text = f"{defect.message or ''}\n{defect.evidence or ''}"
    screen = _screen_prefix(defect)
    fallback = (defect.test_title or defect.test_id or defect.title or "テスト").strip()

    m = re.search(r"getByRole\(\s*'button'\s*,\s*\{\s*name:\s*'([^']+)'", text)
    if m:
        target = m.group(1)
        return f"{screen}で「{target}」ボタンが表示されない" if screen else f"「{target}」ボタンが表示されない"

    m = re.search(r"getBy(?:Text|Label|Placeholder|TestId)\(\s*'([^']+)'", text)
    if m:
        target = m.group(1)
        return f"{screen}で「{target}」が表示されない" if screen else f"「{target}」が表示されない"

    m = re.search(r"getByRole\(\s*'([^']+)'\s*,\s*\{\s*name:\s*'([^']+)'", text)
    if m:
        target = m.group(2)
        return f"{screen}で「{target}」が表示されない" if screen else f"「{target}」が表示されない"

    if re.search(r"toHaveText|toContainText", text):
        return f"{screen}の表示内容が期待と異なる" if screen else f"{fallback} の表示内容が期待と異なる"

    if "toHaveURL" in text:
        return f"{screen}からの遷移先が期待と異なる" if screen else f"{fallback} の遷移先が期待と異なる"

    if re.search(r"AssertionError|^\s*assert ", text, re.MULTILINE):
        return title_from_test_id(defect.test_id, defect.message or "") or f"{fallback} が失敗する"

    return f"{screen}: {fallback} が失敗" if screen else f"{fallback} が失敗"


def _hunk_lines(diff: str) -> str:
    """diff の最初のハンクから「41〜44 行」の形を作る。取れなければ空。

    行番号 0 は「差分が無い」を意味するので出さない。修正が適用されなかった
    実行で「demo_calc.py 0 行」と書くと、そこに問題があるように読める。
    """
    m = re.search(r"@@ -(\d+)(?:,(\d+))? ", diff or "")
    if not m:
        return ""
    start = int(m.group(1))
    if start <= 0:
        return ""
    count = int(m.group(2) or 1)
    end = start + max(count - 1, 0)
    return f"{start}〜{end} 行" if end > start else f"{start} 行"


def _cause_path(proposal: FixProposal | None, defect: Defect) -> str:
    """原因の箇所に使うファイル。特定できなければ空。"""
    first = defect.locations[0] if defect.locations else None
    if isinstance(first, Mapping) and first.get("path"):
        return str(first["path"])
    if proposal and proposal.files_changed:
        return proposal.files_changed[0]
    return defect.suspect_files[0] if defect.suspect_files else ""


def _enclosing_def(diff: str) -> str:
    """差分が入っている関数の名前。取れなければ空。

    ハンクヘッダの末尾は当てにならない（実測ではモジュールの説明文が入っていた）。
    文脈行を上から読み、最初の変更行にぶつかった時点の定義名を採る。
    """
    name = ""
    for line in (diff or "").splitlines():
        if line.startswith(("diff ", "index ", "--- ", "+++ ")):
            continue
        found = re.match(r"^[ +\-]\s*(?:async\s+)?(?:def|function)\s+([A-Za-z_]\w*)", line)
        if found:
            name = found.group(1)
        elif line.startswith("@@"):
            name = ""
        elif line.startswith(("-", "+")):
            return name
    return name


def _code_snippet(lines: Sequence[str], limit: int = 60) -> str:
    """変更行を 1 行の引用にする。長ければ切る。"""
    text = " / ".join(x for x in lines if x)
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _cause_from_diff(proposal: FixProposal | None, location: str) -> str:
    """差分という事実から原因を書く。差分が無ければ空。"""
    if proposal is None or not (proposal.diff or "").strip():
        return ""
    files = [f for f in _parse_file_diffs(proposal.diff) if f.added or f.removed]
    if not files:
        return ""
    head = files[0]
    func = _enclosing_def(proposal.diff)
    where = f"{head.path} の {func}" if func else (head.path or location)
    changed = sum(len(f.added) + len(f.removed) for f in files)
    if len(files) > 1:
        others = len(files) - 1
        return f"{where} ほか {others} ファイルの実装が期待と異なっていました（{changed} 行を修正）。"
    removed = [x.strip() for x in head.removed if x.strip()]
    added = [x.strip() for x in head.added if x.strip()]
    if removed and added and len(removed) <= 3 and len(added) <= 3:
        verb = "を返していました" if removed[0].startswith("return ") else "でした"
        return f"{where} が {_code_snippet(removed)} {verb}（{_code_snippet(added)} に修正）。"
    if removed and not added:
        return f"{where} に不要な処理が残っていました（{len(removed)} 行を削除）。"
    if added and not removed:
        return f"{where} に必要な処理がありませんでした（{len(added)} 行を追加）。"
    return f"{where} の実装が期待と異なっていました（{changed} 行を修正）。"


def humanize_cause(proposal: FixProposal | None, defect: Defect) -> tuple[str, str]:
    """原因の説明と、その箇所を返す。

    説明は AI の自己申告ではなく本体が持つ事実（差分・欠陥）から組み立てる。
    自己申告は自分の実行環境の話を書き、検証結果と食い違う（実測）。
    """
    path = _cause_path(proposal, defect)
    lines = _hunk_lines(proposal.diff if proposal else "")
    location = f"{path} {lines}".strip() if path else ""
    cause = _cause_from_diff(proposal, location)
    if not cause:
        cause = "原因を特定できませんでした。検証ログを確認してください。"
    return _truncate_sentences(cause, _CAUSE_MAX_CHARS), location


def _action_text(proposal: FixProposal | None, cause_text: str) -> str:
    """対応の説明。原因と同じ文章なら繰り返さない。

    エージェントは summary と rationale に同じ文章を入れてくることがあり、
    そのまま出すと報告書の「原因」と「対応」が同一になる（実測で発生）。
    """
    if proposal is None:
        return ""
    summary = _truncate_sentences(proposal.summary or "", _CAUSE_MAX_CHARS)
    if not summary:
        return "修正を適用しました"
    # 先頭 60 字が一致すれば同じ説明とみなす（末尾だけ違う版も拾う）。
    head = 60
    if summary[:head] and summary[:head] == cause_text[:head]:
        files = ", ".join(proposal.files_changed) if proposal.files_changed else ""
        return f"上記の原因に対する修正を適用しました。{('対象: ' + files) if files else ''}".strip()
    return summary


def _verify_text(result: VerifyResult | None) -> tuple[str, bool | None]:
    """検証結果を「失敗 1 / 42」の形にする。未実行は None を返す。"""
    if result is None:
        return "未実行", None
    total = int(getattr(result, "total", 0) or 0)
    failed = int(getattr(result, "failed", 0) or 0)
    passed = int(getattr(result, "passed", 0) or 0)
    ok = bool(getattr(result, "ok", False))
    if total == 0 and not ok:
        return "実行できませんでした", False
    if failed:
        return f"失敗 {failed} / {total}", False
    return f"通過 {passed or total} / {total}", ok


def _diff_stats_text(proposal: FixProposal | None) -> str:
    """「1 ファイル・+1 / −3」の形。差分が無ければ空。"""
    if not proposal or not proposal.diff:
        return ""
    added = sum(
        1 for line in proposal.diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in proposal.diff.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    files = len(proposal.files_changed) or 1
    return f"{files} ファイル・+{added} / −{removed}"


def _target_url(project: HealingProject) -> str:
    """報告書に出す対象。domain があればそれ、無ければリポジトリの末尾。"""
    if project.domain:
        return project.domain
    parts = Path(project.repo_path).parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ─────────────────────────── 組み立て ───────────────────────────


def _spec_match_text(
    defect: Defect,
    proposal: FixProposal | None,
    project: HealingProject,
    out_dir: Path | None,
) -> str:
    """「画面仕様との照合」欄の 1 行。

    照合できなかったときは「未照合」。照合して不一致が無かったときは
    対象件数を出す。この 2 つを同じ文言にすると、確認していないことが
    確認済みに見える。
    """
    if proposal is None or out_dir is None or not defect.screen_id:
        return "未照合"
    domain = str(getattr(project, "domain", "") or "")
    if not domain:
        return "未照合"
    try:
        spec = spec_match.load_screen_spec(out_dir, domain, defect.screen_id)
        signals = spec_match.assess_spec(proposal, spec)
        return spec_match.summarize(proposal, spec, signals)
    except Exception:  # noqa: BLE001 - 照合の失敗で報告書を落とさない
        logger.warning("画面仕様との照合に失敗しました", exc_info=True)
        return "未照合"


def build_maintenance_report(
    *,
    run: HealingRun,
    iteration: HealingIteration,
    defect: Defect,
    proposal: FixProposal | None,
    project: HealingProject,
    out_dir: Path | None = None,
) -> MaintenanceReport:
    """1 欠陥ぶんの報告書を組み立てる。直せなかった場合も報告書は作る。"""
    verify_before, _ = _verify_text(getattr(iteration, "verify_before", None))
    verify_after, after_ok = _verify_text(getattr(iteration, "verify_after", None))
    cause_text, cause_location = humanize_cause(proposal, defect)
    applied = bool(proposal and proposal.status == "applied")

    incident_verify = ""
    before = getattr(iteration, "verify_before", None)
    if before is not None:
        total = int(getattr(before, "total", 0) or 0)
        failed = int(getattr(before, "failed", 0) or 0)
        if total:
            incident_verify = f"検証 {total} 件中 {failed} 件失敗"

    return MaintenanceReport(
        report_id="rep-" + secrets.token_hex(6),
        project_id=project.project_id,
        project_name=project.name,
        target_url=_target_url(project),
        run_id=run.run_id,
        defect_id=defect.defect_id,
        title=humanize_title(defect),
        status="awaiting",
        incident_text=(defect.message or defect.title or "").strip(),
        incident_detected_at=run.started_at or getattr(run, "created_at", "") or _now(),
        incident_source=_incident_source(run),
        incident_screen_id=defect.screen_id,
        incident_screen_name=defect.screen_name,
        incident_test_id=defect.test_id,
        incident_screenshot=defect.screenshot,
        incident_verify=incident_verify,
        cause_text=cause_text,
        cause_location=cause_location,
        action_text=_action_text(proposal, cause_text) if applied else "",
        action_by=_AGENT_LABELS.get(
            (proposal.agent if proposal else "") or "", (proposal.agent if proposal else "") or ""
        ),
        action_at=getattr(iteration, "finished_at", "") or _now(),
        action_diff_stats=_diff_stats_text(proposal),
        action_screenshot="",
        verify_before=verify_before,
        verify_after=verify_after,
        verify_after_ok=after_ok,
        spec_match=_spec_match_text(defect, proposal, project, out_dir),
        attention=_with_note(
            tuple(dict(r) for r in (proposal.risks if proposal else ())),
            _contradiction_note(
                (proposal.rationale if proposal else "") or "", verify_after, after_ok
            ),
        ),
        approvals=(
            {
                "role": "proposed",
                "who": _AGENT_LABELS.get(
                    (proposal.agent if proposal else "") or "", "AI"
                ),
                "at": getattr(iteration, "finished_at", "") or _now(),
                "note": "",
            },
        )
        if applied
        else (),
        pr_number=run.pull_request.number if run.pull_request else 0,
        pr_url=run.pull_request.url if run.pull_request else "",
        created_at=_now(),
        updated_at=_now(),
    )


def _incident_source(run: HealingRun) -> str:
    """検知の経路。監視・指揮者が起こしたのか、人が押したのかを報告書に残す。"""
    actor = str(getattr(run, "actor", "") or "")
    for entry in run.decisions or []:
        if isinstance(entry, Mapping) and entry.get("actor"):
            actor = str(entry["actor"])
            break
    if actor == "monitor":
        return "monitor"
    if actor == "conductor":
        return "conductor"
    for line in run.log or []:
        if "actor=monitor" in str(line):
            return "monitor"
        if "actor=conductor" in str(line):
            return "conductor"
    return "manual"


# ─────────────────────────── 入出力 ───────────────────────────


def to_save_dict(report: MaintenanceReport) -> dict[str, Any]:
    """保存する形。整形しない。

    ここに表示用の作り直しを入れると、保存のたびに JSON が書き換わり、
    「AI が何と言ったか」を証跡から復元できなくなる（2026-09-05 に実際に壊した）。
    """
    data = asdict(report)
    data["attention"] = [dict(a) for a in report.attention]
    data["approvals"] = [dict(a) for a in report.approvals]
    return data


def to_dict(report: MaintenanceReport) -> dict[str, Any]:
    """画面・API・書き出しが受け取る形。表示用に作り直したもので、保存には使わない。"""
    return to_view_dict(report)


def from_dict(data: Mapping[str, Any]) -> MaintenanceReport:
    """欠けたキーは既定値へ。古い報告書を読んでも落ちない。"""

    def _tuple(key: str) -> tuple[dict[str, Any], ...]:
        raw = data.get(key) or []
        return tuple(dict(x) for x in raw if isinstance(x, Mapping))

    after_ok = data.get("verify_after_ok")
    return MaintenanceReport(
        report_id=str(data.get("report_id") or ""),
        project_id=str(data.get("project_id") or ""),
        project_name=str(data.get("project_name") or ""),
        target_url=str(data.get("target_url") or ""),
        run_id=str(data.get("run_id") or ""),
        defect_id=str(data.get("defect_id") or ""),
        title=str(data.get("title") or ""),
        status=str(data.get("status") or "awaiting"),
        incident_text=str(data.get("incident_text") or ""),
        incident_detected_at=str(data.get("incident_detected_at") or ""),
        incident_source=str(data.get("incident_source") or ""),
        incident_screen_id=str(data.get("incident_screen_id") or ""),
        incident_screen_name=str(data.get("incident_screen_name") or ""),
        incident_test_id=str(data.get("incident_test_id") or ""),
        incident_screenshot=str(data.get("incident_screenshot") or ""),
        incident_verify=str(data.get("incident_verify") or ""),
        cause_text=str(data.get("cause_text") or ""),
        cause_location=str(data.get("cause_location") or ""),
        action_text=str(data.get("action_text") or ""),
        action_by=str(data.get("action_by") or ""),
        action_at=str(data.get("action_at") or ""),
        action_diff_stats=str(data.get("action_diff_stats") or ""),
        action_screenshot=str(data.get("action_screenshot") or ""),
        verify_before=str(data.get("verify_before") or ""),
        verify_after=str(data.get("verify_after") or ""),
        verify_after_ok=None if after_ok is None else bool(after_ok),
        spec_match=str(data.get("spec_match") or "未照合"),
        attention=_tuple("attention"),
        approvals=_tuple("approvals"),
        pr_number=int(data.get("pr_number") or 0),
        pr_url=str(data.get("pr_url") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


def reports_dir(out_dir: Path) -> Path:
    return Path(out_dir) / ".healing" / "reports"


def save_report(out_dir: Path, report: MaintenanceReport) -> Path:
    target = reports_dir(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{report.report_id}.json"
    path.write_text(
        json.dumps(to_save_dict(report), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return path


def load_report(out_dir: Path, report_id: str) -> MaintenanceReport | None:
    """保存されたままの報告書を返す。整形しない。

    人が書き足した内容を保存し直す経路（PATCH・承認）がこれを使うため、
    ここで表示用に作り直すと、その作り直しがそのままディスクへ焼き付く。
    """
    path = reports_dir(out_dir) / f"{report_id}.json"
    if not path.is_file():
        return None
    try:
        return from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("報告書を読めません: %s (%s)", path, exc)
        return None


def _read_reports(
    out_dir: Path, *, status: str = "", project_id: str = "", limit: int = 100
) -> list[MaintenanceReport]:
    """保存されたままの報告書を新しい順に返す。壊れたファイルは読み飛ばす。"""
    target = reports_dir(out_dir)
    if not target.is_dir():
        return []
    found: list[MaintenanceReport] = []
    for path in target.glob("rep-*.json"):
        try:
            report = from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("報告書を読めません: %s (%s)", path, exc)
            continue
        if status and report.status != status:
            continue
        if project_id and report.project_id != project_id:
            continue
        found.append(report)
    found.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
    return found[:limit]


def list_reports(
    out_dir: Path, *, status: str = "", project_id: str = "", limit: int = 100
) -> list[MaintenanceReport]:
    """一覧に出す形。件名と本文を表示用に直したものを返す（保存には使わない）。"""
    return [
        _display_report(r)
        for r in _read_reports(
            out_dir, status=status, project_id=project_id, limit=limit
        )
    ]


def find_report(
    out_dir: Path, *, run_id: str, defect_id: str
) -> MaintenanceReport | None:
    """同じ実行・同じ欠陥の報告書を探す。周回ごとの上書きに使う。

    書き戻す経路なので、保存されたままのものを返す（表示用に直さない）。
    """
    for report in _read_reports(out_dir, limit=1000):
        if report.run_id == run_id and report.defect_id == defect_id:
            return report
    return None


def merge_report(
    existing: MaintenanceReport, fresh: MaintenanceReport
) -> MaintenanceReport:
    """既存の報告書を新しい内容で更新する。ID と作成時刻と人の判断は保つ。

    保存に回るので、表示用ではなく保存形式で取り出す。
    """
    data = to_save_dict(fresh)
    for key in ("report_id", "created_at"):
        data.pop(key, None)
    # 人が下した判断は機械の再生成で消さない。
    data["status"] = existing.status if existing.status != "awaiting" else fresh.status
    data["approvals"] = [dict(a) for a in existing.approvals] or data["approvals"]
    data["action_text"] = existing.action_text or fresh.action_text
    data["updated_at"] = _now()
    return replace(
        existing,
        **{
            k: (
                tuple(dict(x) for x in v)
                if k in {"attention", "approvals"}
                else v
            )
            for k, v in data.items()
        },
    )


# ─────────────────────────── Markdown ───────────────────────────


def _escape_pipe(value: str) -> str:
    return str(value or "").replace("|", "\\|")


def _quote(text: str) -> list[str]:
    """全行に > を付ける。1 行目だけ引用にすると 2 行目以降が地の文になる。"""
    if not text:
        return ["> 記録なし"]
    return [f"> {line}" if line.strip() else ">" for line in text.splitlines()]


_SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


def render_markdown(report: MaintenanceReport) -> str:
    """顧客に出す様式で Markdown を組み立てる。画面・PDF と同じ節構成。"""
    report = _display_report(report)
    lines: list[str] = ["## 保守対応報告書", ""]
    meta = [f"案件: {report.project_name}"]
    if report.target_url:
        meta.append(f"対象: {report.target_url}")
    if report.incident_detected_at:
        meta.append(f"対応日: {report.incident_detected_at[:10]}")
    lines += [" ／ ".join(meta), ""]

    lines += ["### 1. 事象", ""]
    lines += _quote(report.incident_text)
    lines.append("")
    detail = [x for x in (report.incident_screen_name, report.incident_test_id, report.incident_verify) if x]
    if detail:
        lines += [" ／ ".join(detail), ""]

    lines += ["### 2. 原因", "", report.cause_text, ""]
    if report.cause_location:
        lines += [f"箇所: `{report.cause_location}`", ""]

    lines += ["### 3. 対応", ""]
    if report.action_text:
        lines += [report.action_text, ""]
        info = [x for x in (report.action_by, report.action_diff_stats) if x]
        if info:
            lines += [" ／ ".join(info), ""]
    else:
        lines += ["自動では直せませんでした。対応は担当者が記入してください。", ""]

    lines += ["### 4. 検証", "", "| | 結果 |", "|---|---|"]
    lines.append(f"| 修正前 | {_escape_pipe(report.verify_before)} |")
    lines.append(f"| 修正後 | {_escape_pipe(report.verify_after)} |")
    lines.append(f"| 画面仕様との照合 | {_escape_pipe(report.spec_match)} |")
    lines.append("")

    lines += ["### 確認が必要な点", ""]
    if report.attention:
        for item in report.attention:
            sev = _SEVERITY_LABELS.get(str(item.get("severity") or ""), "")
            label = str(item.get("label") or "")
            note = str(item.get("detail") or "")
            head = f"- {sev} {label}".strip()
            lines.append(head)
            if note:
                lines.append(f"  - {note}")
        lines.append("")
    else:
        lines += [
            "機械的に検出できる兆候はありませんでした。"
            "テストの通過は正しさを保証しません。差分を確認してください。",
            "",
        ]

    lines += ["### 5. 承認", ""]
    rows = []
    for entry in report.approvals:
        role = {
            "proposed": "提案",
            "approved": "承認",
            "returned": "差し戻し",
            "rejected": "却下",
            "customer": "顧客確認",
        }.get(str(entry.get("role") or ""), str(entry.get("role") or ""))
        rows.append(f"{role}: {entry.get('who') or '—'} {entry.get('at') or ''}".strip())
    if report.pr_number:
        rows.append(f"PR: #{report.pr_number}")
    else:
        rows.append("PR: 承認後に作成")
    lines += [" ／ ".join(rows) if rows else "未承認", ""]
    return "\n".join(lines)


def build_pr_body_section(reports: Sequence[MaintenanceReport]) -> str:
    """複数の報告書を PR 本文へ連結する。"""
    if not reports:
        return ""
    parts = [render_markdown(r) for r in reports]
    return "\n\n---\n\n".join(parts)
