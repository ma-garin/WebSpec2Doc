from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AutoRunJob:
    job_id: str
    url: str
    domain: str = ""
    status: str = "idle"
    # idle | discovering | awaiting_input | crawling | generating_qa
    # generating_scripts | awaiting_approval | running_tests | complete
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

    _proc: Any = field(default=None, init=False, repr=False, compare=False)
    _input_event: Any = field(
        default_factory=threading.Event, init=False, repr=False, compare=False
    )
    _input_data: dict[str, Any] = field(default_factory=dict, init=False, repr=False, compare=False)
    _cancelled: bool = field(default=False, init=False, repr=False, compare=False)

    def add_log(self, msg: str) -> None:
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        logger.info("autorun[%s] %s", self.job_id, msg)

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
            "log": self.log[-200:],
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
            "step_data": self.step_data,
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
