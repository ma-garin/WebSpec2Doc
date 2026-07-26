from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_LOG_LINES = 1000
MAX_LOG_BYTES = 256 * 1024


def job_output_dir(job: AutoRunJob, default: Path) -> Path:
    """バックグラウンドジョブに固定済みのテナント出力先を返す。"""
    stored = getattr(job, "_output_dir", None)
    return stored if isinstance(stored, Path) else default


def _truncate_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


@dataclass
class AutoRunJob:
    job_id: str
    url: str
    domain: str = ""
    status: str = "idle"
    # idle | discovering | awaiting_input | crawling | generating_qa
    # generating_document_mbt | generating_scripts | awaiting_approval | running_tests | complete
    # cancelled | failed
    step_label: str = ""
    log: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    test_results: dict[str, Any] = field(default_factory=dict)
    failure_classifications: list[dict[str, Any]] = field(default_factory=list)
    failure_summary: dict[str, int] = field(default_factory=dict)
    step_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    approved: bool = False
    auth_path: str = ""
    input_request: dict[str, Any] | None = None
    run_policy: dict[str, Any] = field(default_factory=dict)
    viewpoint_set_id: str = ""
    viewpoint_set_name: str = ""
    viewpoint_version: int = 0
    viewpoint_checksum: str = ""
    viewpoint_selection_reason: str = ""
    viewpoint_count: int = 0
    mode: str = "url"
    selection_criterion: str = "vertex_coverage"
    target_page_id: str = ""
    observe_validation: bool = False
    # 段階承認（仕様7〜13）を実行の関門にするか。
    # 画面から始めた実行は True。自動実行など人が承認できない文脈では False にし、
    # 「承認を経ていない」ことをログへ必ず残す（黙って飛ばさない）。
    require_stage_approval: bool = True
    #: 承認待ちの段階ID（仕様7〜14: 1段階ずつ提示するためUIへ渡す）
    awaiting_stage_id: str = ""
    # 実行条件を一括で確定した場合に True。以降の段階では止まらない。
    # 生成済みの内容を段階ごとに承認させないため（利用者の指摘）。
    stages_all_released: bool = False
    # 実行条件ダイアログで確定した内容（decision_id -> {choice,label,text}）。
    # 記録だけで終わらせず、実行の挙動へ反映する。
    decisions: dict[str, Any] = field(default_factory=dict)
    # 利用者の自由記述による追加指示。実行方針として証跡に残す。
    decisions_note: str = ""
    #: 人の確認を経ていない事項。空でないなら「全部確認した」と言ってはならない。
    #: 「不在は証明しない」方針の実装。ログに流すだけでは消えるため状態として持つ。
    unverified: list[str] = field(default_factory=list)
    #: 承認・入力の待機期限（epoch秒）。0 なら待機していない。
    #: 「いつ切れるか」を画面に出せないと、時間切れは黙って起きたのと同じになる。
    awaiting_deadline_epoch: float = 0.0

    _proc: Any = field(default=None, init=False, repr=False, compare=False)
    # ジョブ開始リクエスト時に解決したテナントスコープ済み出力先（Path）。
    # ジョブ本体はバックグラウンドスレッドで動きリクエストコンテキストを
    # 参照できないため、ここに保持して持ち回る。None なら共有 output/。
    _output_dir: Any = field(default=None, init=False, repr=False, compare=False)
    _viewpoint_snapshot: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _reference_docs: list[str] = field(default_factory=list, init=False, repr=False, compare=False)
    _input_event: Any = field(
        default_factory=threading.Event, init=False, repr=False, compare=False
    )
    _input_data: dict[str, Any] = field(default_factory=dict, init=False, repr=False, compare=False)
    # 段階承認（仕様7〜13）の完了待ち。全段階が承認されるまでスクリプト生成へ進まない。
    _stages_event: Any = field(
        default_factory=threading.Event, init=False, repr=False, compare=False
    )
    _cancelled: bool = field(default=False, init=False, repr=False, compare=False)

    def add_log(self, msg: str) -> None:
        prefix = f"[{datetime.now().strftime('%H:%M:%S')}] "
        line = prefix + _truncate_utf8(str(msg), MAX_LOG_BYTES - len(prefix.encode("utf-8")))
        self.log.append(line)
        self.log = self.log[-MAX_LOG_LINES:]
        total = sum(len(item.encode("utf-8")) for item in self.log)
        while len(self.log) > 1 and total > MAX_LOG_BYTES:
            total -= len(self.log.pop(0).encode("utf-8"))
        if total > MAX_LOG_BYTES:
            self.log[0] = _truncate_utf8(self.log[0], MAX_LOG_BYTES)
        logger.info("autorun[%s] %s", self.job_id, line)

    def add_unverified(self, note: str) -> None:
        """人の確認を経ていない事項を記録する。

        ログに1行流すだけでは、後からレポートを見た人には届かない。
        「確認していない」ことは成果物に残さないと、確認済みと誤読される。
        """
        text = str(note).strip()
        if not text or text in self.unverified:
            return
        self.unverified = [*self.unverified, text]
        self.add_log(f"未確認として記録: {text}")

    def awaiting_remaining_sec(self) -> int:
        """待機期限までの残り秒。待機していなければ 0。"""
        if not self.awaiting_deadline_epoch:
            return 0
        return max(0, int(self.awaiting_deadline_epoch - time.time()))

    def elapsed_sec(self) -> int:
        if not self.started_at:
            return 0
        try:
            start = datetime.fromisoformat(self.started_at)
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
            end_str = self.finished_at
            if end_str:
                end = datetime.fromisoformat(end_str)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=UTC)
            else:
                end = datetime.now(UTC)
            return max(0, int((end - start).total_seconds()))
        except Exception:
            return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "domain": self.domain,
            "status": self.status,
            "step_label": self.step_label,
            "awaiting_stage_id": self.awaiting_stage_id,
            # 待機の期限と未確認事項は、画面と成果物の両方で必要。
            "awaiting_remaining_sec": self.awaiting_remaining_sec(),
            "unverified": self.unverified,
            "log": self.log,
            "outputs": self.outputs,
            "test_results": self.test_results,
            "failure_classifications": self.failure_classifications,
            "failure_summary": self.failure_summary,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_sec": self.elapsed_sec(),
            "input_request": self.input_request,
            "run_policy": self.run_policy,
            "decisions": self.decisions,
            "decisions_note": self.decisions_note,
            "step_data": self.step_data,
            "viewpoint": {
                "set_id": self.viewpoint_set_id,
                "set_name": self.viewpoint_set_name,
                "version": self.viewpoint_version,
                "checksum": self.viewpoint_checksum,
                "selection_reason": self.viewpoint_selection_reason,
                "count": self.viewpoint_count,
            },
            "mode": self.mode,
            "selection_criterion": self.selection_criterion,
            "target_page_id": self.target_page_id,
            "observe_validation": self.observe_validation,
            "reference_doc_count": len(self._reference_docs),
        }

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._input_event.set()
        # 段階承認の待機も解除しないと、停止しても待ち続けてしまう
        self._stages_event.set()
