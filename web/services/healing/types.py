"""オートヒーリング（System 05）の型契約。

このモジュールは他のヒーリング用モジュールが共通で依存する「言葉の定義」だけを持つ。
処理は持たない。ここに副作用のあるコードを足すと、store / git / agent が
互いを import し合って循環参照になる。

用語:
    Project     ヒーリング対象のコードベース（ローカル git リポジトリ 1 個）
    Run         1 回のヒーリング実行。中に複数の Iteration（ループの周回）を持つ
    Iteration   検証 → 欠陥抽出 → 修正 → 再検証 の 1 周
    Defect      検証で観測された不具合 1 件（事実）
    FixProposal 1 件の Defect に対してエージェントが出した修正（判断）

「事実」と「判断」を型で分けている。Defect は観測結果しか持たず、
原因や修正方針は必ず FixProposal 側に置く（AutoRun と同じ方針）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# ─────────────────────────── 状態語彙 ───────────────────────────

#: Run の状態。左から右へ進む。terminal 以外へは戻れる（ループするため）。
RUN_STATUSES: tuple[str, ...] = (
    "queued",  # 受付済み・未着手
    "preparing",  # worktree 作成・ブランチ作成
    "verifying",  # 検証コマンド実行（1 周目）
    "analyzing",  # 失敗を欠陥として構造化
    "fixing",  # エージェントが並列で修正中
    "reverifying",  # 修正後の再検証
    "awaiting_human",  # PR を出して人の判断待ち（終端ではない）
    "succeeded",  # 検証が緑になって完了
    "no_defects",  # 最初から緑。直すものが無い
    "failed",  # 実行そのものが失敗
    "cancelled",  # 人が止めた
)

#: これ以上自動では進まない状態。
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "no_defects", "failed", "cancelled"})

RUN_STATUS_LABELS: dict[str, str] = {
    "queued": "受付",
    "preparing": "準備",
    "verifying": "検証",
    "analyzing": "欠陥の切り出し",
    "fixing": "修正",
    "reverifying": "再検証",
    "awaiting_human": "人の判断待ち",
    "succeeded": "完了",
    "no_defects": "不具合なし",
    "failed": "失敗",
    "cancelled": "中止",
}

#: defect_store.py と同じ語彙を使う（重大 / 高 / 中 / 低）。
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low")

#: FixProposal の状態。
PROPOSAL_STATUSES: tuple[str, ...] = (
    "proposed",  # 修正案は出たが作業ツリーには入っていない
    "applied",  # 作業ツリーへ適用済み
    "failed",  # エージェントが失敗した
    "skipped",  # 対象外と判断された
    "timeout",  # 時間切れ
)


# ─────────────────────────── プロジェクト ───────────────────────────


@dataclass(frozen=True)
class HealingProject:
    """ヒーリング対象のコードベース 1 件。

    repo_path はローカル絶対パス。許可ルート配下かどうかの検証は
    project_store 側で必ず行う（この型は検証しない）。
    github_repo が空の場合、PR は作れず「差分の提示」までで止まる。
    """

    project_id: str
    name: str
    repo_path: str
    default_branch: str = "main"
    #: 検証コマンド。リポジトリルートで実行する。空なら検証できない。
    verify_command: str = ""
    remote: str = "origin"
    #: "owner/name" 形式。空なら PR 機能を無効にする。
    github_repo: str = ""
    #: agents.py のレジストリキー（"claude" / "codex" / "dryrun"）。
    agent: str = "claude"
    #: ループの上限周回数。ここに達したら緑でなくても止める。
    max_iterations: int = 3
    #: 同時に走らせるエージェント数。1 欠陥 1 エージェント 1 worktree。
    max_parallel_agents: int = 3
    #: エージェント 1 本あたりの上限秒数。
    agent_timeout_sec: int = 900
    #: 検証コマンド 1 回あたりの上限秒数。
    verify_timeout_sec: int = 1800
    created_at: str = ""
    updated_at: str = ""
    #: 01/02/03 が使う <domain>（output/<domain>）。E2E 起点の接続に必要。
    #: 空なら pytest 等のコマンド起点のみで、画面仕様との照合はできない。
    domain: str = ""
    #: 報告書の「報告」欄に出す組織名（「株式会社△△ 保守チーム」等）。
    report_org: str = ""
    #: 毎日きまった時刻に 02 のテストを回すか。
    monitor_enabled: bool = False
    #: 回す時刻（"HH:MM"・サーバのローカル時刻）。空なら回さない。
    monitor_time: str = ""
    #: 最後に回した日（"YYYY-MM-DD"）。同じ日に二度回さないための記録。
    monitor_last_run_on: str = ""

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


#: 接続確認 1 項目の重み。NG のときに「実行できないのか」「PR だけ困るのか」を分ける。
CHECK_SEVERITIES: tuple[str, ...] = (
    "required",  # NG なら実行そのものが成立しない
    "optional",  # NG でも検証・修正ループは動く（PR 作成時にだけ必要）
)


@dataclass(frozen=True)
class ConnectionCheck:
    """接続確認 1 項目の結果。「押したら動くのか」を先に見せるために使う。"""

    key: str  # "repo" | "git" | "remote" | "github" | "verify_command" | "agent"
    label: str
    ok: bool
    detail: str = ""
    #: CHECK_SEVERITIES のいずれか。既定は "required"。
    #: 既存の位置引数の順序を壊さないよう、必ず末尾に足す。
    severity: str = "required"

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


# ─────────────────────────── 検証 ───────────────────────────


@dataclass(frozen=True)
class VerifyFailure:
    """検証で落ちた 1 件。観測できた事実のみを持つ。"""

    test_id: str
    message: str
    file: str = ""
    line: int = 0
    traceback_tail: str = ""


@dataclass(frozen=True)
class VerifyResult:
    """検証コマンド 1 回分の結果。"""

    ok: bool
    command: str
    exit_code: int
    duration_sec: float
    total: int = 0
    passed: int = 0
    failed: int = 0
    failures: tuple[VerifyFailure, ...] = ()
    log_tail: str = ""
    started_at: str = ""
    finished_at: str = ""
    #: 検証そのものが実行できなかった理由（コマンド未設定・起動失敗など）。
    error: str = ""


# ─────────────────────────── 欠陥と修正 ───────────────────────────


@dataclass(frozen=True)
class Defect:
    """観測された不具合 1 件。原因や直し方はここに書かない（判断は FixProposal）。"""

    defect_id: str
    title: str
    severity: str = "medium"
    source: str = "verify"  # "verify" | "static" | "manual"
    test_id: str = ""
    message: str = ""
    evidence: str = ""
    #: 該当しそうなファイル（相対パス）。推定なので「候補」として扱う。
    suspect_files: tuple[str, ...] = ()
    detected_at: str = ""
    #: 限局の根拠。localization.LocationEvidence を dict にしたもの
    #: （path / reason / score / detail）。既定は空。
    #: 既存の位置引数の順序を壊さないよう、必ず末尾に足す（古い履歴も読める）。
    locations: tuple[dict[str, Any], ...] = ()
    #: 失敗した画面の URL。E2E（02/03）起点のときだけ入る。pytest 起点では空。
    url: str = ""
    #: 画面 ID（P001 等）。01 が生成した画面仕様と突き合わせる鍵。
    screen_id: str = ""
    #: 画面名（「予約確認」等）。報告書の件名を人の言葉にするために使う。
    screen_name: str = ""
    #: テスト名から TC-ID を除いた部分（「予約を確定できる」等）。
    test_title: str = ""
    #: 失敗時のスクリーンショット。out_dir からの相対パス。無ければ空。
    screenshot: str = ""

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


@dataclass(frozen=True)
class AgentTask:
    """エージェント 1 本に渡す仕事。エージェントはこれ以外の文脈を持たない。"""

    defect: Defect
    #: 分離済み作業ディレクトリ（git worktree）の絶対パス。ここだけ書き換えてよい。
    workdir: str
    repo_root: str
    verify_command: str
    timeout_sec: int = 900
    extra_instructions: str = ""


@dataclass(frozen=True)
class FixProposal:
    """1 件の Defect に対する修正の結果（判断）。"""

    defect_id: str
    agent: str
    status: str = "proposed"
    summary: str = ""
    rationale: str = ""
    diff: str = ""
    files_changed: tuple[str, ...] = ()
    log_tail: str = ""
    duration_sec: float = 0.0
    error: str = ""
    #: risk.RiskSignal を dict にしたもの（code / label / detail / severity）。
    risks: tuple[dict[str, Any], ...] = ()
    #: report.build_report が作った人向け Markdown。空なら未生成。
    report_md: str = ""

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


class HealingAgent(Protocol):
    """修正エージェントの契約。

    実装は別プロセス（claude / codex CLI）でも、プロセス内でもよい。
    orchestrator はこの Protocol にしか依存しない。差し替え・並列化・
    外部への切り出しはすべてこの境界で行う。
    """

    name: str

    def is_available(self) -> ConnectionCheck:
        """このエージェントが今この環境で実行可能かを返す。"""
        ...

    def propose_fix(self, task: AgentTask) -> FixProposal:
        """task.workdir の中だけを書き換えて修正案を返す。例外は投げない。"""
        ...


# ─────────────────────────── PR とループ ───────────────────────────


@dataclass(frozen=True)
class PullRequestRef:
    """作成した PR の参照。人の判断はここで待つ。"""

    number: int = 0
    url: str = ""
    state: str = "open"  # open | merged | closed | draft
    title: str = ""
    branch: str = ""
    checks: str = ""  # "" は未取得。取得できたら success/failure/pending
    created_at: str = ""


@dataclass
class HealingIteration:
    """ループ 1 周（検証 → 欠陥 → 修正 → 再検証）。可変（進行に応じて埋まる）。"""

    index: int
    verify_before: VerifyResult | None = None
    defects: list[Defect] = field(default_factory=list)
    proposals: list[FixProposal] = field(default_factory=list)
    verify_after: VerifyResult | None = None
    started_at: str = ""
    finished_at: str = ""


@dataclass
class HealingRun:
    """ヒーリング実行 1 回。画面はこのオブジェクトをポーリングして描く。"""

    run_id: str
    project_id: str
    project_name: str = ""
    status: str = "queued"
    step_label: str = ""
    branch: str = ""
    base_branch: str = "main"
    iterations: list[HealingIteration] = field(default_factory=list)
    pull_request: PullRequestRef | None = None
    log: list[str] = field(default_factory=list)
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    #: 人の確認を経ていない事項。空でない限り「全部確認した」と書いてはならない。
    unverified: list[str] = field(default_factory=list)
    #: 人が下した判断の履歴（approve / reject / rerun）。
    decisions: list[dict[str, Any]] = field(default_factory=list)
    #: この実行から起こした保守対応報告書の ID。1 欠陥 = 1 報告書。
    report_ids: list[str] = field(default_factory=list)
    #: この実行を起こした主体。"" は画面からの手動、"autorun" は 02/03 の
    #: 失敗から、"monitor" は毎日の見張りから。ログの文言だけに頼ると
    #: 一覧で絞り込めないので、値として持つ。
    actor: str = ""


#: 保守対応報告書の状態。
#: draft     … 下書き中（生成の途中）
#: awaiting  … 承認待ち。人が読んで判断する
#: approved  … 承認済み。PR を作成した
#: returned  … 差し戻し。指示つきで再修正を走らせた
#: rejected  … 却下
#: submitted … 顧客へ提出済み
REPORT_STATUSES: tuple[str, ...] = (
    "draft",
    "awaiting",
    "approved",
    "returned",
    "rejected",
    "submitted",
)


class HealingError(Exception):
    """ヒーリング処理の想定内の失敗。利用者に見せてよいメッセージだけを持つ。"""
