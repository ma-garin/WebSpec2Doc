"""共通の中間表現（IR）と USDM 文書モデル。

解析器（analyzers/<lang>/）はすべてこの IR を返す。USDM 生成（usdm.py）は IR だけを入力にする。
すべて不変（frozen dataclass）。変更するときは新しいオブジェクトを返す。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace, asdict
from typing import Literal, Any

Confidence = Literal["事実", "推定", "要確認"]
StatementSource = Literal["static", "llm", "human"]
ConditionKind = Literal[
    "validation",   # 入力検証（if not x: error = ... 等）
    "branch",       # その他の条件分岐
    "exception",    # raise / except
    "http_error",   # abort(4xx/5xx)
    "redirect",     # redirect(url_for(...))
    "render",       # render_template(...)
    "db_write",     # execute(INSERT/UPDATE/DELETE) + commit
    "state",        # session の設定・消去
    "precondition", # ルートの前提（@login_required）
    "preprocess",   # 前処理（@X.before_app_request）
    "command",      # コマンドとして実行できる（@click.command）
    "db_read",      # execute(SELECT)（text は仕様文）
    "db_script",    # executescript(...)（text は仕様文）
    "behavior",     # 設定値・登録・ディレクトリ作成・row_factory・functools.wraps（text は仕様文）
]


@dataclass(frozen=True)
class Evidence:
    """根拠。コードは「ファイルと行番号」（REQ-F-020-01）。"""
    file: str                 # プロジェクト内の相対パス
    line_start: int
    line_end: int
    snippet: str = ""         # 該当行のソース（1〜3 行）

    def label(self) -> str:
        if self.line_start == self.line_end:
            return f"{self.file}:{self.line_start}"
        return f"{self.file}:{self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class Condition:
    kind: ConditionKind
    text: str                 # 条件の原文（ast.unparse）または要約
    evidence: Evidence
    detail: str = ""          # 例: エラー文、HTTP コード、遷移先、テンプレート名
    related: tuple[Evidence, ...] = ()  # 追加の根拠（例: 呼び先の abort の行。V-005c）


@dataclass(frozen=True)
class RouteInfo:
    path: str                 # 例: /auth/login（Blueprint の url_prefix を含む）
    methods: tuple[str, ...]  # 例: ("GET", "POST")
    evidence: Evidence


@dataclass(frozen=True)
class FunctionIR:
    name: str
    qualname: str             # module.name
    module: str
    is_public: bool           # 先頭が _ でない
    params: tuple[str, ...]
    docstring: str | None
    route: RouteInfo | None
    conditions: tuple[Condition, ...]
    evidence: Evidence        # def 行〜関数末尾
    calls: tuple[str, ...] = ()   # 呼び出している関数名（重複除去・出現順）
    decorators: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateEvent:
    name: str                 # イベント名（関数名など）
    from_state: str
    to_state: str
    evidence: Evidence


@dataclass(frozen=True)
class StateMachine:
    name: str                 # 例: ログインセッション
    states: tuple[str, ...]
    events: tuple[StateEvent, ...]


@dataclass(frozen=True)
class ModuleIR:
    path: str                 # 相対パス
    name: str                 # 例: sample_blog.auth
    language: str             # 例: python
    functions: tuple[FunctionIR, ...]
    state_machines: tuple[StateMachine, ...] = ()
    imports: tuple[str, ...] = ()
    line_count: int = 0
    url_prefix: str | None = None   # Blueprint の url_prefix（分かる場合）


@dataclass(frozen=True)
class AnalysisResult:
    modules: tuple[ModuleIR, ...]
    skipped: tuple[str, ...] = ()   # 解析できなかったファイル（構文エラー等）


# ── USDM 文書モデル ─────────────────────────────────────────────────────────

Origin = Literal["code", "screen", "document", "answer", "llm", "test"]
ORIGINS: tuple[str, ...] = ("code", "screen", "document", "answer", "llm", "test")
ORIGIN_LABELS: dict[str, str] = {"code": "コード", "screen": "画面", "document": "文書", "answer": "回答", "llm": "LLM",
                                 "test": "テスト"}
LEGACY_ORIGINS: dict[str, str] = {label: key for key, label in ORIGIN_LABELS.items()}   # v0.5 途中版の日本語値
CONFIDENCES: tuple[str, ...] = ("事実", "推定", "要確認")


def normalize_origin(value: str) -> str:
    """出所を契約の値（code / screen / document / answer / llm）にする。旧版の日本語値は読み替える。"""
    key = LEGACY_ORIGINS.get(value, value)
    if key not in ORIGINS:
        raise ValueError(f"出所の値が不正: {value!r}（{' / '.join(ORIGINS)} のいずれか）")
    return key


@dataclass(frozen=True)
class Statement:
    text: str
    confidence: Confidence
    evidence: tuple[Evidence, ...] = ()
    source: StatementSource = "static"
    origin: str = "code"      # 出所（確度とは別の属性。REQ-F-021-01 の付与表の左列。値は ORIGINS）

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"確度の値が不正: {self.confidence!r}（{' / '.join(CONFIDENCES)} のいずれか）")
        object.__setattr__(self, "origin", normalize_origin(self.origin))


@dataclass(frozen=True)
class Spec:
    id: str                   # <要求ID>-NN
    group: str                # <グループ名>
    statement: Statement


@dataclass(frozen=True)
class RequirementAttributes:
    """要求ごとの属性 3 欄（ISO/IEC/IEEE 29148 の優先度・検証方法・上位追跡。D4 DD-076）。"""
    priority: str = "要確認"            # 高／中／低／要確認
    verification: str = "要確認"        # テスト／レビュー／分析／実演／要確認
    parent_ids: tuple[str, ...] = ()    # 上位の要求 ID。空なら表示は「要確認」
    priority_origin: str = "none"       # 値の出所: test／document／answer／none


@dataclass(frozen=True)
class FrontSection:
    """要求仕様書の冒頭章（29148 9.6 の 7 章。番号は 1.1〜1.7）。"""
    number: str
    title: str
    statements: tuple[Statement, ...] = ()


@dataclass(frozen=True)
class Requirement:
    id: str                   # 要求 ID
    title: str
    requirement: Statement
    reason: Statement
    description: Statement
    specs: tuple[Spec, ...]
    state_machine: StateMachine | None = None
    attributes: RequirementAttributes = RequirementAttributes()   # 既定値で旧 JSON を読める


@dataclass(frozen=True)
class Question:
    id: str                   # Q-NNN
    text: str
    related_ids: tuple[str, ...]
    choices: tuple[str, ...] = ()
    answer: str | None = None


@dataclass(frozen=True)
class HistoryRow:
    version: str
    date: str
    content: str
    author: str


@dataclass(frozen=True)
class Appendix:
    """付録（形式仕様の Z など。D2）。md は見出し無しの Markdown 本文。"""
    id: str
    title: str
    md: str


@dataclass(frozen=True)
class UsdmDocument:
    doc_id: str
    title: str
    version: str
    project_name: str
    generated_at: str
    llm_provider: str                       # none / ollama / openai
    requirements: tuple[Requirement, ...]
    questions: tuple[Question, ...] = ()
    history: tuple[HistoryRow, ...] = ()
    source_summary: dict[str, Any] = field(default_factory=dict)   # ファイル数・行数など
    appendices: tuple[Appendix, ...] = ()
    front_sections: tuple[FrontSection, ...] = ()

    def all_statements(self) -> tuple[tuple[str, Statement], ...]:
        """(ID, Statement) の一覧。確度の集計と根拠検査に使う。"""
        out: list[tuple[str, Statement]] = []
        for r in self.requirements:
            out.append((r.id, r.requirement))
            out.append((f"{r.id}(理由)", r.reason))
            out.append((f"{r.id}(説明)", r.description))
            for s in r.specs:
                out.append((s.id, s.statement))
        return tuple(out)

    def confidence_counts(self) -> dict[str, int]:
        counts = {"事実": 0, "推定": 0, "要確認": 0}
        for _, st in self.all_statements():
            counts[st.confidence] += 1
        return counts

    def origin_counts(self) -> dict[str, int]:
        counts = {o: 0 for o in ORIGINS}
        for _, st in self.all_statements():
            counts[st.origin] += 1
        return counts


def to_dict(obj: Any) -> Any:
    """dataclass → JSON 化できる dict（SQLite の stages.result_json 用）。"""
    return asdict(obj)


def doc_from_dict(d: dict[str, Any]) -> UsdmDocument:
    """UsdmDocument の JSON 復元。"""
    def ev(e: dict[str, Any]) -> Evidence:
        return Evidence(**e)

    def st(s: dict[str, Any]) -> Statement:
        return Statement(text=s["text"], confidence=s["confidence"],
                         evidence=tuple(ev(e) for e in s.get("evidence", ())), source=s.get("source", "static"),
                         origin=s.get("origin", "code"))

    def sm(m: dict[str, Any] | None) -> StateMachine | None:
        if not m:
            return None
        return StateMachine(name=m["name"], states=tuple(m["states"]),
                            events=tuple(StateEvent(name=e["name"], from_state=e["from_state"],
                                                    to_state=e["to_state"], evidence=ev(e["evidence"]))
                                         for e in m["events"]))

    def attrs(a: dict[str, Any] | None) -> RequirementAttributes:
        if not a:
            return RequirementAttributes()
        return RequirementAttributes(priority=a.get("priority", "要確認"), verification=a.get("verification", "要確認"),
                                     parent_ids=tuple(a.get("parent_ids", ())),
                                     priority_origin=a.get("priority_origin", "none"))

    reqs = tuple(
        Requirement(id=r["id"], title=r["title"], requirement=st(r["requirement"]), reason=st(r["reason"]),
                    description=st(r["description"]),
                    specs=tuple(Spec(id=s["id"], group=s["group"], statement=st(s["statement"])) for s in r["specs"]),
                    state_machine=sm(r.get("state_machine")), attributes=attrs(r.get("attributes")))
        for r in d["requirements"])
    qs = tuple(Question(id=q["id"], text=q["text"], related_ids=tuple(q["related_ids"]),
                        choices=tuple(q.get("choices", ())), answer=q.get("answer")) for q in d.get("questions", ()))
    hist = tuple(HistoryRow(**h) for h in d.get("history", ()))
    appendices = tuple(Appendix(id=a["id"], title=a["title"], md=a.get("md", "")) for a in d.get("appendices", ()))
    front = tuple(FrontSection(number=f["number"], title=f["title"],
                               statements=tuple(st(x) for x in f.get("statements", ())))
                  for f in d.get("front_sections", ()))
    return UsdmDocument(doc_id=d["doc_id"], title=d["title"], version=d["version"], project_name=d["project_name"],
                        generated_at=d["generated_at"], llm_provider=d.get("llm_provider", "none"),
                        requirements=reqs, questions=qs, history=hist, source_summary=d.get("source_summary", {}),
                        appendices=appendices, front_sections=front)


def analysis_from_dict(d: dict[str, Any]) -> AnalysisResult:
    """AnalysisResult の JSON 復元。"""
    def ev(e: dict[str, Any]) -> Evidence:
        return Evidence(**e)

    mods = []
    for m in d["modules"]:
        funcs = tuple(
            FunctionIR(name=f["name"], qualname=f["qualname"], module=f["module"], is_public=f["is_public"],
                       params=tuple(f["params"]), docstring=f.get("docstring"),
                       route=RouteInfo(path=f["route"]["path"], methods=tuple(f["route"]["methods"]),
                                       evidence=ev(f["route"]["evidence"])) if f.get("route") else None,
                       conditions=tuple(Condition(kind=c["kind"], text=c["text"], evidence=ev(c["evidence"]),
                                                  detail=c.get("detail", ""),
                                                  related=tuple(ev(e) for e in c.get("related", ())))
                                        for c in f["conditions"]),
                       evidence=ev(f["evidence"]), calls=tuple(f.get("calls", ())),
                       decorators=tuple(f.get("decorators", ())))
            for f in m["functions"])
        sms = tuple(StateMachine(name=s["name"], states=tuple(s["states"]),
                                 events=tuple(StateEvent(name=e["name"], from_state=e["from_state"],
                                                         to_state=e["to_state"], evidence=ev(e["evidence"]))
                                              for e in s["events"]))
                    for s in m.get("state_machines", ()))
        mods.append(ModuleIR(path=m["path"], name=m["name"], language=m["language"], functions=funcs,
                             state_machines=sms, imports=tuple(m.get("imports", ())),
                             line_count=m.get("line_count", 0), url_prefix=m.get("url_prefix")))
    return AnalysisResult(modules=tuple(mods), skipped=tuple(d.get("skipped", ())))


__all__ = [
    "Confidence", "StatementSource", "ConditionKind", "Origin", "ORIGINS", "ORIGIN_LABELS", "CONFIDENCES",
    "normalize_origin", "Evidence", "Condition", "RouteInfo", "FunctionIR",
    "StateEvent", "StateMachine", "ModuleIR", "AnalysisResult", "Statement", "Spec", "Requirement",
    "Question", "HistoryRow", "UsdmDocument", "Appendix", "RequirementAttributes", "FrontSection", "to_dict", "doc_from_dict", "analysis_from_dict", "replace",
]
