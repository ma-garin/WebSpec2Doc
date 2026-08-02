"""実行回ごとの成果物置き場（runs/<run_id>/）。

背景
----
成果物はこれまでサイト単位で上書きされていた（``output/<domain>/report.html`` など）。
そのため同じサイトを 12 回実行しても残るのは最新 1 件だけで、実行履歴の各行が
どれも同じ画面へ飛び、7 月の実行を開いても今日の数字が出ていた。

方針
----
生成側（``src/`` 配下・241 箇所の出力先参照）には手を入れず、**実行が終わった時点で
成果物を ``runs/<run_id>/`` へ退避する**。従来の出力先はそのまま「現在の成果物」
として残るので、既存の画面・API は影響を受けない。

    output/<domain>/
      report.html            ← 従来どおり（= current）
      runs/
        20260802-113000/     ← この実行回の成果物
          meta.json
          report.html
          report.json
          qa_process/...
          testcases/...

退避するのは成果物ファイルだけで、スクリーンショット・トレースは含めない。
実行回数ぶん容量が線形に増えるため、上限のない大きさを抱え込ませない。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUNS_DIR_NAME = "runs"
META_FILE_NAME = "meta.json"

# run_id は「日時そのもの」。別途 UUID を持たせるより、一覧の並びと人が読む値が
# 一致するほうが履歴として扱いやすい。同一秒に複数実行が並ぶ場合は連番を足す。
_RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(-\d+)?$")

# 退避する成果物。ここに無いものは runs/ へ持って行かない（容量を上限のない
# 大きさにしないため）。スクリーンショット・trace.zip は意図的に除外している。
_ROOT_ARTIFACTS: tuple[str, ...] = (
    "report.html",
    "report.json",
    "report.pdf",
    "screens.md",
    "features.md",
    "forms.md",
    "spec.xlsx",
    "diff_report.html",
    "comparison.html",
    "ux_review.html",
    "doc_fusion.json",
    "transition.mmd",
)
_QA_ARTIFACTS: tuple[str, ...] = (
    "test_plan.md",
    "test_analysis.md",
    "test_design.md",
    "test_cases.md",
    "autorun.spec.ts",
    "playwright_report.json",
    "playwright_report.html",
    "qa_process_report.html",
    "stages.json",
    "mutation_verification.json",
    "nonfunctional_judgement.json",
    "observation_coverage.json",
)
_TESTCASE_ARTIFACTS: tuple[str, ...] = (
    "run_result.json",
    "table.json",
    "spec.ts",
)

# 画面（案A の 3 タブ）に対応する成果物の判定材料。
# 「あり」と言えるのは実物が置けたときだけで、無いものを在るように見せない。
_ARTIFACT_PROBES: dict[str, tuple[str, ...]] = {
    "result": ("report.json",),
    "analysis": ("report.html",),
    "autorun": (
        "qa_process/playwright_report.json",
        "qa_process/stages.json",
        "qa_process/autorun.spec.ts",
    ),
}


@dataclass(frozen=True)
class RunMeta:
    """1 実行回のメタ情報（meta.json の中身）。"""

    run_id: str
    domain: str
    event: str
    finished_at: str
    status: str
    artifacts: dict[str, bool]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "event": self.event,
            "finished_at": self.finished_at,
            "status": self.status,
            "artifacts": dict(self.artifacts),
            "summary": dict(self.summary),
        }


def valid_run_id(run_id: str) -> bool:
    """run_id としてパスに使える形かを判定する（経路トラバーサル防止）。"""
    return bool(run_id) and bool(_RUN_ID_RE.match(run_id))


def runs_root(output_root: Path, domain: str) -> Path:
    return output_root / domain / RUNS_DIR_NAME


def run_dir(output_root: Path, domain: str, run_id: str) -> Path | None:
    """実行回のディレクトリ。run_id が不正なら None（呼び出し側で 404 にする）。"""
    if not valid_run_id(run_id):
        return None
    return runs_root(output_root, domain) / run_id


def new_run_id(output_root: Path, domain: str, *, now: datetime | None = None) -> str:
    """未使用の run_id を作る。同一秒に複数実行が並んでも衝突しない。"""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    root = runs_root(output_root, domain)
    if not (root / stamp).exists():
        return stamp
    for n in range(2, 100):
        candidate = f"{stamp}-{n}"
        if not (root / candidate).exists():
            return candidate
    # 同一秒に 100 件は現実的に起きないが、起きたら黙って上書きしない
    raise RuntimeError(f"run_id を採番できませんでした: {domain} {stamp}")


def _copy_file(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as exc:
        logger.warning("成果物を退避できませんでした: %s -> %s (%s)", src, dest, exc)
        return False
    return True


def _copy_artifacts(domain_dir: Path, target: Path) -> list[str]:
    """成果物を退避し、実際にコピーできた相対パスを返す。"""
    copied: list[str] = []
    for name in _ROOT_ARTIFACTS:
        if _copy_file(domain_dir / name, target / name):
            copied.append(name)
    for name in _QA_ARTIFACTS:
        if _copy_file(domain_dir / "qa_process" / name, target / "qa_process" / name):
            copied.append(f"qa_process/{name}")
    for name in _TESTCASE_ARTIFACTS:
        if _copy_file(domain_dir / "testcases" / name, target / "testcases" / name):
            copied.append(f"testcases/{name}")
    return copied


def _artifact_flags(copied: list[str]) -> dict[str, bool]:
    present = set(copied)
    return {key: any(p in present for p in probes) for key, probes in _ARTIFACT_PROBES.items()}


def snapshot_run(
    output_root: Path,
    domain: str,
    *,
    event: str,
    status: str = "complete",
    summary: dict[str, Any] | None = None,
    run_id: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """実行完了時に成果物を runs/<run_id>/ へ退避し、run_id を返す。

    退避に 1 件も成功しなかった場合は run_id を返さない（空のディレクトリを作って
    「この実行回の成果物がある」ように見せないため）。
    失敗は呼び出し側の応答を妨げない設計にしてあり、None を返すだけで例外は投げない。
    """
    if not domain:
        return None
    domain_dir = output_root / domain
    if not domain_dir.is_dir():
        return None
    try:
        rid = run_id or new_run_id(output_root, domain, now=now)
        if not valid_run_id(rid):
            logger.warning("run_id の形が不正です: %s", rid)
            return None
        target = runs_root(output_root, domain) / rid
        target.mkdir(parents=True, exist_ok=True)
        copied = _copy_artifacts(domain_dir, target)
        if not copied:
            # 退避できる成果物が無い実行。空の器だけ残すと「あるのに開けない」になる。
            # 親の runs/ も自分が作ったなら畳む（空ディレクトリだけが残らないように）。
            shutil.rmtree(target, ignore_errors=True)
            root = runs_root(output_root, domain)
            if root.is_dir() and not any(root.iterdir()):
                root.rmdir()
            logger.info("退避できる成果物がありません（run を作りません）: %s", domain)
            return None
        meta = RunMeta(
            run_id=rid,
            domain=domain,
            event=event,
            finished_at=(now or datetime.now()).isoformat(timespec="seconds"),
            status=status,
            artifacts=_artifact_flags(copied),
            summary=dict(summary or {}),
        )
        (target / META_FILE_NAME).write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return rid
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("実行回の退避に失敗しました: domain=%s (%s)", domain, exc)
        return None


def load_meta(output_root: Path, domain: str, run_id: str) -> dict[str, Any] | None:
    """1 実行回の meta.json を読む。無ければ None。"""
    target = run_dir(output_root, domain, run_id)
    if target is None:
        return None
    path = target / META_FILE_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("meta.json を読めません: %s (%s)", path, exc)
        return None
    return data if isinstance(data, dict) else None


def list_runs(output_root: Path, domain: str) -> list[dict[str, Any]]:
    """そのサイトの実行回を新しい順で返す（meta.json のあるものだけ）。"""
    root = runs_root(output_root, domain)
    if not root.is_dir():
        return []
    metas: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir() or not valid_run_id(child.name):
            continue
        meta = load_meta(output_root, domain, child.name)
        if meta is not None:
            metas.append(meta)
    metas.sort(key=lambda m: str(m.get("run_id", "")), reverse=True)
    return metas


def artifact_file(
    output_root: Path, domain: str, run_id: str, relative: str
) -> Path | None:
    """実行回の成果物ファイルの実パス。実在しなければ None（捏造しない）。

    ``relative`` は退避対象の allowlist に含まれるものだけを受け付ける。
    """
    allowed = set(_ROOT_ARTIFACTS)
    allowed |= {f"qa_process/{n}" for n in _QA_ARTIFACTS}
    allowed |= {f"testcases/{n}" for n in _TESTCASE_ARTIFACTS}
    if relative not in allowed:
        return None
    target = run_dir(output_root, domain, run_id)
    if target is None:
        return None
    path = target / relative
    return path if path.is_file() else None


def latest_run_id(output_root: Path, domain: str) -> str | None:
    """最新の実行回。無ければ None。"""
    runs = list_runs(output_root, domain)
    return str(runs[0]["run_id"]) if runs else None
