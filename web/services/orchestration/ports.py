"""指揮者と各システムの間の契約。

5 つのシステムは、それぞれ別の理由で作られた別のものである。だから
「同じ関数を持て」と押しつけると、どれかの都合が必ず歪む。ここで決めるのは
呼び出し方ではなく、**指揮者が知る必要のあることだけ**に絞った 4 つの語彙にする。

- 走らせてよいか（Readiness）
- 走らせた結果どうなったか（StepResult）
- 走っている途中どうなっているか（StepStatus）
- 走らせるのに要る材料（Context）

人の承認は指揮者が代行しない。承認は「待ち」という状態として表に出す
（waiting_human）。代行してよいことにすると、02 の観点承認・05 の報告書承認という
「人が責任を持つ」設計そのものが無効になる。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

#: 進行状態の語彙。これ以外の文字列を使わない。
#: 指揮者（O2）はこの語彙だけを見て次の遷移を決めるので、
#: ここに語を足すと状態機械の分岐が漏れる。
#:
#: queued（まだ始めていない）と cancelled（人が止めた）は段そのものは返さないが、
#: 指揮者の実行と段の記録が同じ語彙を使えるようにここへ置く。語彙を 2 か所に
#: 分けると、画面が「どちらの表を見ればよいか」を持たなければならなくなる。
STEP_STATES: tuple[str, ...] = (
    "queued",
    "succeeded",
    "failed",
    "running",
    "skipped",
    "waiting_human",
    "cancelled",
)


def _no_log(_message: str) -> None:
    """既定のログ出力（何もしない）。指揮者が実物を渡す。"""
    return None


@dataclass(frozen=True)
class Context:
    """1 ステップを走らせるのに要る材料。

    out_dir はテナントスコープ済みの出力ルート（認証オフなら output/）。
    エージェント側でテナントを解決し直さない。解決の責任を 2 か所に置くと、
    テナントを跨いだ書き込みという最悪の事故が起こりうる。
    """

    out_dir: Path
    domain: str
    project_id: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    log: Callable[[str], None] = _no_log
    #: 誰がこの指揮を起こしたか（"monitor" / "cli" / 利用者名）。段が残す記録の
    #: 出どころに使う。ここを空のままにすると、監視が起こしたものも画面から
    #: 押されたものも同じ出どころになり、あとから経緯を追えなくなる。
    actor: str = ""


@dataclass(frozen=True)
class Readiness:
    """走らせてよいか。ダメなら「人がやること」を 1 文で返す。

    human_action には内部用語（spec / defect / run_id）を出さない。
    これは画面にそのまま出る文であり、読む人はこの仕組みを知らない。
    """

    ok: bool
    human_action: str = ""
    detail: str = ""


@dataclass(frozen=True)
class StepResult:
    """1 ステップを走らせた結果。

    summary は人が読む 1 文にする。「68 件中 3 件失敗」のように、
    数と結末だけで意味が通るように書く。

    status == "running" は「別のスレッドが続きを進めている」という意味で、
    そのスレッドはこのプロセスと運命を共にする。呼び出し元がサーバのような
    長命なプロセス（指揮者のデーモンスレッド）でなければならないのはこのため。
    短命なスクリプトから呼ぶとプロセスの終了と一緒にスレッドが消え、
    実行は非終端の状態のまま永続化されて残る（05 の場合、その接続先は
    「まだ動いている」と見え続け、次の実行が起きなくなる）。
    """

    status: str
    summary: str
    artifacts: Mapping[str, str] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    handle: str = ""
    error: str = ""
    human_action: str = ""
    #: 機械可読の理由。同じ status でも結末の意味が違うものを指揮者が
    #: 見分けるために持つ（05 の skipped は「失敗が無い」と「前の実行が
    #: まだ動いている」で意味が正反対で、status だけでは分けられない）。
    #: 語彙: "no_defects" / "busy" / "already_reported"。空なら理由なし。
    reason: str = ""


@dataclass(frozen=True)
class StepStatus:
    """走っている途中／終わったあとの状態。

    human_action は state == "waiting_human" のとき、人がやることを 1 文で持つ。
    Readiness と同じく画面にそのまま出るので内部用語を出さない。summary（事実）と
    分けるのは、指揮者が「人に何をしてほしいか」だけを実行の先頭へ写すため。
    """

    state: str
    label: str
    summary: str = ""
    artifacts: Mapping[str, str] = field(default_factory=dict)
    error: str = ""
    human_action: str = ""


@runtime_checkable
class SystemAgent(Protocol):
    """1 システムを指揮者から見た姿。

    どのエージェントも run() は handle を返し、続きは status() で追う。
    呼ぶ側は中で何が動いているかを知らずに済む。

    非同期のエージェントはスレッドで進む。したがって run() は、サーバのような
    長命なプロセス（指揮者のデーモンスレッド）から呼ぶこと。短命なスクリプトから
    呼ぶとプロセスの終了でスレッドが消え、実行が非終端のまま残る
    （O2 の指揮者はサーバ内で動かす前提）。

    handle は「どの実行か」を指す。status() は必ず handle が指すものを見る。
    handle を無視して「最新の結果」を返すと、別の実行の結果を、指定された
    実行の結果として報告することになる。
    """

    name: str
    label: str

    def ready(self, ctx: Context) -> Readiness: ...

    def run(self, ctx: Context) -> StepResult: ...

    def status(self, ctx: Context, handle: str) -> StepStatus: ...

    def cancel(self, ctx: Context, handle: str) -> bool:
        """走っているものを止める。止められたら True。

        省略できることにしない。止め方を持たないシステムが 1 つでもあると、
        指揮者は「記録だけ cancelled・実体は動き続け」を作る。実測では
        Playwright の node がプロセス終了後も走り続けた（孤児化）。

        今すぐ止められないもの（人の承認待ちでブロックしているスレッドなど）は
        合図だけ立てて False を返す。止まったふりをしない。
        """
        ...
