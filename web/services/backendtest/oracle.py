"""期待値 3 方式（DB 前後比較／別経路 SQL／ゴールデン）とスキーマの確定規則・自動判定。

中核原則（RD-008 3 章・BD-008 7 章）:
- 機械判定できる期待値（冪等性・再実行・前後比較・スキーマ・件数）だけ自動確定（state="auto"）
- 業務判断を含む期待値は人（senior_qa）が確定（state="human"）。未確定は「未判定」で合格に数えない
- 根拠がソース（対象の実装）だけの期待値は確定させない。LLM に対象の振る舞いから期待値を学ばせない

入力の case は変更せず、新しい dict を返す。利用者に見せてよい失敗は StoreError。
"""
from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from . import diffing

try:
    from .store import StoreError
except ImportError:  # U01（store）が未配置のときだけ。型は同じ ValueError 派生
    class StoreError(ValueError):
        """利用者に見せてよい理由を持つ失敗。"""

METHODS = ("db_diff", "alt_sql", "golden", "schema")
STATES = ("unconfirmed", "auto", "human")
ROLE_RANK = {"qa": 1, "senior_qa": 2}
CONFIRMER_ROLE = "senior_qa"
PASS, FAIL, UNDETERMINED = "pass", "fail", "undetermined"

_COUNT_RE = re.compile(r"^\s*after\s*=\s*(?:before\s*([+-])\s*)?(\d+)\s*$", re.I)
_COUNT_SAME_RE = re.compile(r"^\s*after\s*=\s*before\s*$", re.I)
_COPY_MIN_LEN = 12  # これより短いソースの式は写し判定に使わない（誤検知を避ける）


# ---------------------------------------------------------------- 共通

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _oracle(case: Mapping) -> dict:
    return dict(case.get("oracle") or {})


def _with_oracle(case: Mapping, **changes: Any) -> dict:
    """case を複製し、oracle の欄だけ差し替えた新しい dict を返す。"""
    out = copy.deepcopy(dict(case))
    oracle = copy.deepcopy(_oracle(case))
    oracle.update(changes)
    out["oracle"] = oracle
    return out


def _resolve_role(role: Any, members: Any) -> str:
    """role がロール名ならそのまま。members（{利用者: ロール}）に載る利用者名ならそのロール。"""
    if role in ROLE_RANK:
        return role
    if isinstance(members, Mapping) and role in members:
        return members.get(role) or ""
    return role or ""


def _is_senior(role: Any, members: Any = None) -> bool:
    return ROLE_RANK.get(_resolve_role(role, members), 0) >= ROLE_RANK[CONFIRMER_ROLE]


def _basis_is_source_only(case: Mapping, facts: Sequence[Mapping] | None) -> bool:
    """根拠がソース事実だけか（FR-08-143）。basis="source" か、根拠の事実がすべて origin="source"。"""
    basis = case.get("basis")
    if isinstance(basis, str) and basis.strip().lower() == "source":
        return True
    ids = [b.strip() for b in basis.split(",")] if isinstance(basis, str) else list(basis or [])
    ids = [i for i in ids if i]
    if not ids or not facts:
        return False
    origin = {f.get("id"): f.get("origin") for f in facts}
    found = [origin[i] for i in ids if i in origin]
    return bool(found) and len(found) == len(ids) and all(o == "source" for o in found)


def default_method(case: Mapping, level: str) -> str:
    """テストレベルの既定の期待値方式（catalog.LEVEL_DEFAULTS の先頭）。不明なら db_diff。"""
    method = _oracle(case).get("method")
    if method in METHODS:
        return method
    try:
        from .catalog import LEVEL_DEFAULTS
    except ImportError:
        return "db_diff"
    oracles = (LEVEL_DEFAULTS.get(level) or {}).get("oracles") or ("db_diff",)
    return oracles[0]


# ---------------------------------------------------------------- 確定の可否

def _method_ready(oracle: Mapping) -> tuple[bool, str]:
    """方式ごとに、確定に必要な設定がそろっているか。"""
    method = oracle.get("method")
    if method not in METHODS:
        return False, "期待値の方式が選ばれていません。方式を選んでください。"
    if method == "db_diff" and not oracle.get("key"):
        return False, "突合キーが設定されていません。突合キーを選んでください。"
    if method == "alt_sql":
        if not (oracle.get("alt_sql") or "").strip():
            return False, "別経路の SQL が空です。SQL を入力してから確定してください。"
        if oracle.get("warnings"):
            return False, "別経路の SQL に写しの警告が残っています。仕様から SQL を書き直してください。"
    if method == "golden" and not (oracle.get("golden") or {}).get("file"):
        return False, "承認済みのゴールデンがありません。期待値ファイルを登録して承認してください。"
    return True, ""


method_ready = _method_ready


def can_confirm(case: Mapping, role: Any, members: Any = (), facts: Sequence[Mapping] | None = None
                ) -> tuple[bool, str]:
    """期待値を確定できるか（確定可否, 理由）。

    auto（機械判定）は誰でも可。unconfirmed は senior_qa のみ。根拠がソースだけ・
    別経路 SQL が空・写し警告が未解消のものは不可。human は確定済み。
    """
    oracle = _oracle(case)
    state = oracle.get("state") or "unconfirmed"
    if state == "auto":
        return True, "機械判定できる期待値のため自動で確定します。"
    if state == "human":
        return True, "シニア QA が確定済みです。"
    if not _is_senior(role, members):
        return False, "業務判断を含む期待値はシニア QA だけが確定できます。シニア QA に確定を依頼してください。"
    if _basis_is_source_only(case, facts):
        return False, "期待値の根拠が対象の実装だけです。仕様書などの根拠を追加してください。"
    ok, reason = _method_ready(oracle)
    if not ok:
        return False, reason
    return True, "確定できます。"


def confirm(case: Mapping, role: Any, actor: str, members: Any = (),
            facts: Sequence[Mapping] | None = None) -> dict:
    """シニア QA が期待値を確定する（state=human）。auto・確定済みは変えずに複製を返す。"""
    ok, reason = can_confirm(case, role, members, facts)
    if not ok:
        raise StoreError(reason)
    if (_oracle(case).get("state") or "unconfirmed") != "unconfirmed":
        return copy.deepcopy(dict(case))
    return _with_oracle(case, state="human", confirmed_by=actor or _resolve_role(role, members),
                        confirmed_at=_now())


# ---------------------------------------------------------------- 設定（新しい case を返す）

def _check_tolerance(tolerance: Mapping[str, Any]) -> dict:
    out = {}
    for col, spec in (tolerance or {}).items():
        vals = spec.values() if isinstance(spec, Mapping) else [spec]
        if isinstance(spec, Mapping) and not set(spec) <= {"abs", "rel"}:
            raise StoreError("列 %s の許容差の形が正しくありません。絶対差か相対差を数値で入れてください。" % col)
        for v in vals:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise StoreError("列 %s の許容差が 0 以上の数値ではありません。0 以上の数値を入れてください。" % col)
        out[col] = dict(spec) if isinstance(spec, Mapping) else spec
    return out


def configure_db_diff(case: Mapping, keys: Sequence[str], tolerance: Mapping[str, Any] | None = None,
                      exclude: Iterable[str] = (), *, mask: Iterable[str] = (),
                      tables: Iterable[str] | None = None, count_formula: str | None = None) -> dict:
    """DB 前後比較の設定。件数式が無ければ機械判定（差分 0 で合格）なので state=auto。

    件数式は業務判断を含むため、指定時は unconfirmed（シニア QA の確定待ち）にする。
    """
    keys = [k for k in (keys or []) if isinstance(k, str) and k.strip()]
    if not keys:
        raise StoreError("突合キーが指定されていません。1 列以上の突合キーを選んでください。")
    exclude = [c for c in (exclude or []) if c]
    clash = sorted(set(keys) & set(exclude))
    if clash:
        raise StoreError("突合キーと除外列が重なっています（%s）。どちらか一方から外してください。" % ", ".join(clash))
    if count_formula is not None and not _parse_count(count_formula):
        raise StoreError("件数式の形が読めません。「after = before + 3」「after = 10」の形で入れてください。")
    oracle = _oracle(case)
    return _with_oracle(
        case, method="db_diff", key=keys, exclude=exclude, tolerance=_check_tolerance(tolerance or {}),
        mask=[c for c in (mask or []) if c],
        tables=list(tables) if tables is not None else list(oracle.get("tables") or []),
        count_formula=count_formula, alt_sql=None, alt_sql_ja="", golden=None, warnings=[],
        state="unconfirmed" if count_formula else "auto", confirmed_by=None)


def _normalize_sql(text: str) -> str:
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", text or "", flags=re.S)
    return re.sub(r"[^0-9a-z_]+", " ", text.lower()).strip()


def check_alt_sql(sql: str, source_facts: Sequence[Mapping] = ()) -> list[str]:
    """別経路 SQL がソース事実（対象の実装の式）の写しになっていないか。警告文の list。"""
    norm_sql = _normalize_sql(sql)
    warnings = []
    for fact in source_facts or []:
        if fact.get("origin") != "source":
            continue
        norm_fact = _normalize_sql(str(fact.get("value") or ""))
        if len(norm_fact) >= _COPY_MIN_LEN and norm_fact in norm_sql:
            warnings.append("SQL に対象の実装と同じ式があります（%s）。仕様から独立に書き直してください。"
                            % (fact.get("id") or fact.get("subject") or "ソース"))
    return warnings


def set_alt_sql(case: Mapping, sql: str, role: Any, *, sql_ja: str = "", actor: str = "",
                members: Any = (), source_facts: Sequence[Mapping] = ()) -> dict:
    """別経路 SQL を設定。senior_qa かつ写し警告なしなら確定（human）、それ以外は下書き。"""
    if not isinstance(sql, str) or not sql.strip():
        raise StoreError("別経路の SQL が空です。読み取りの SQL を入力してください。")
    try:
        from .dbconn import guard_sql
    except ImportError:
        guard_sql = None
    if guard_sql is not None:
        guard_sql(sql, True)  # 書き込み系なら StoreError（読み取り SQL のみ）
    warnings = check_alt_sql(sql, source_facts)
    senior = _is_senior(role, members)
    human = senior and not warnings and not _basis_is_source_only(case, source_facts)
    return _with_oracle(
        case, method="alt_sql", alt_sql=sql, alt_sql_ja=sql_ja or _oracle(case).get("alt_sql_ja") or "",
        warnings=warnings, golden=None, state="human" if human else "unconfirmed",
        confirmed_by=(actor or _resolve_role(role, members)) if human else None,
        confirmed_at=_now() if human else None)


def approve_golden(case: Mapping, golden_ref: Any, role: Any, *, actor: str = "",
                   members: Any = ()) -> dict:
    """ゴールデン（承認済み期待値）を新しい版として承認する。旧版は history に残す（FR-08-065）。"""
    if not _is_senior(role, members):
        raise StoreError("ゴールデンの承認はシニア QA だけができます。シニア QA に承認を依頼してください。")
    ref = {"file": golden_ref} if isinstance(golden_ref, str) else dict(golden_ref or {})
    if not (ref.get("file") or "").strip():
        raise StoreError("期待値ファイルが指定されていません。ファイルを登録してから承認してください。")
    prev = copy.deepcopy(_oracle(case).get("golden") or None)
    history = list((prev or {}).get("history") or [])
    if prev and prev.get("file"):
        history.append({k: v for k, v in prev.items() if k != "history"})
    who = actor or _resolve_role(role, members)
    golden = {"version": int((prev or {}).get("version") or 0) + 1, "file": ref["file"],
              "sha256": ref.get("sha256"), "approved_by": who, "approved_at": _now(),
              "history": history}
    return _with_oracle(case, method="golden", golden=golden, alt_sql=None, warnings=[],
                        state="human", confirmed_by=who, confirmed_at=golden["approved_at"])


# ---------------------------------------------------------------- 判定

def _result(verdict: str, rule: str, reason: str, **detail: Any) -> dict:
    return {"verdict": verdict, "rule": rule, "reason": reason, "detail": detail}


def _parse_count(formula: str | None):
    """件数式を (演算, 値) に。after = before / after = before ± N / after = N。読めなければ None。"""
    if not isinstance(formula, str):
        return None
    if _COUNT_SAME_RE.match(formula):
        return ("+", 0)
    m = _COUNT_RE.match(formula)
    if not m:
        return None
    return (m.group(1) or "=", int(m.group(2)))


def _expected_count(parsed: tuple, before: int) -> int:
    op, n = parsed
    return n if op == "=" else (before + n if op == "+" else before - n)


def _diff_counts(d: Mapping) -> dict:
    return {"added": len(d.get("added") or []), "removed": len(d.get("removed") or []),
            "updated": len(d.get("updated") or []), "unchanged": d.get("unchanged", 0),
            "indeterminate": d.get("indeterminate", 0)}


def _run_diff(oracle: Mapping, left: Sequence, right: Sequence, aggregate: Sequence[str] = ()) -> dict:
    return diffing.diff(left, right, oracle.get("key") or [], exclude=oracle.get("exclude") or (),
                        tolerance=oracle.get("tolerance") or {}, mask=oracle.get("mask") or (),
                        aggregate=aggregate)


def _verdict_from_diff(rule: str, d: Mapping, what: str) -> dict:
    counts = _diff_counts(d)
    totals = d.get("totals") or {}
    if counts["indeterminate"]:
        return _result(UNDETERMINED, rule, "突合キーが一意でない・欠けている行があり判定できません。"
                       "突合キーを見直してください。", counts=counts, totals=totals,
                       warnings=d.get("warnings") or [])
    n = counts["added"] + counts["removed"] + counts["updated"]
    if n == 0:
        return _result(PASS, rule, "%sとの差分は 0 件です。" % what, counts=counts, totals=totals)
    return _result(FAIL, rule, "%sとの差分が %d 件あります（追加 %d・削除 %d・更新 %d）。"
                   % (what, n, counts["added"], counts["removed"], counts["updated"]),
                   diff_count=n, counts=counts, totals=totals, updated=list(d.get("updated") or [])[:10])


def _eval_db_diff(oracle: Mapping, observed: Mapping) -> dict:
    if "before" not in observed or "after" not in observed:
        return _result(UNDETERMINED, "db_diff", "実行前後のスナップショットがありません。実行し直してください。")
    before, after = observed["before"] or [], observed["after"] or []
    parsed = _parse_count(oracle.get("count_formula"))
    if oracle.get("count_formula"):
        if not parsed:
            return _result(UNDETERMINED, "count", "件数式が読めません。件数式を見直してください。")
        want = _expected_count(parsed, len(before))
        got = len(after)
        verdict = PASS if got == want else FAIL
        return _result(verdict, "count", "実行後の件数は %d 件（期待 %d 件）です。" % (got, want),
                       count_before=len(before), count_after=got, count_expected=want,
                       count_diff=got - want)
    return _verdict_from_diff("db_diff", _run_diff(oracle, before, after), "実行前")


def _aggregate_cols(oracle: Mapping, observed: Mapping) -> list[str]:
    return list(observed.get("aggregate") or (oracle.get("tolerance") or {}).keys())


def _eval_compare(oracle: Mapping, observed: Mapping, ref_key: str, rule: str, what: str) -> dict:
    """別経路 SQL・ゴールデン: 期待側の行と対象の出力を突合キー・許容差で比べる。"""
    if ref_key not in observed or "actual" not in observed:
        return _result(UNDETERMINED, rule, "%sか対象の出力がありません。実行し直してください。" % what)
    if not oracle.get("key") and rule != "alt_sql":  # 別経路は変わった行だけを比べるので、キーが無ければ全列で比べる
        return _result(UNDETERMINED, rule, "突合キーが設定されていません。突合キーを選んでください。")
    d = _run_diff(oracle, observed[ref_key] or [], observed["actual"] or [],
                  _aggregate_cols(oracle, observed))
    return _verdict_from_diff(rule, d, what)


def _eval_schema(observed: Mapping) -> dict:
    if "violations" not in observed:
        return _result(UNDETERMINED, "schema", "スキーマ検査の結果がありません。実行し直してください。")
    violations = list(observed.get("violations") or [])
    if not violations:
        return _result(PASS, "schema", "スキーマ違反は 0 件です。", violations=0)
    return _result(FAIL, "schema", "スキーマ違反が %d 件あります。" % len(violations),
                   violations=len(violations), samples=violations[:10])


def _keyless_rerun(case: Mapping, oracle: Mapping) -> bool:
    """冪等性（再実行）の前後比較は、突合キーが無くても行全体の個数の増減で判定できる。"""
    rerun = case.get("check") == "rerun" or case.get("variant") == "再実行"
    return rerun and oracle.get("method") == "db_diff" and not oracle.get("key")


def evaluate(case: Mapping, observed: Mapping | None) -> dict:
    """方式ごとに pass / fail / undetermined と根拠を返す。未確定の期待値は undetermined（合格に数えない）。

    observed: db_diff={"before","after"}、alt_sql={"expected"（別経路 SQL の結果）,"actual"}、
    golden={"golden","actual"}、schema={"violations"}。
    """
    oracle = _oracle(case)
    method = oracle.get("method")
    if method not in METHODS:
        return _result(UNDETERMINED, "none", "期待値の方式が未確定のため未判定です。方式を選んでください。")
    if (oracle.get("state") or "unconfirmed") not in ("auto", "human"):
        return _result(UNDETERMINED, method, "期待値が未確定のため未判定です。シニア QA に確定を依頼してください。")
    ok, reason = _method_ready(oracle)
    if not ok and not _keyless_rerun(case, oracle):
        return _result(UNDETERMINED, method, reason)
    observed = observed or {}
    try:
        if method == "db_diff":
            return _eval_db_diff(oracle, observed)
        if method == "alt_sql":
            return _eval_compare(oracle, observed, "expected", "alt_sql", "別経路 SQL の結果")
        if method == "golden":
            return _eval_compare(oracle, observed, "golden", "golden", "ゴールデン")
        return _eval_schema(observed)
    except ValueError as exc:  # diffing の入力不備は未判定として理由を返す（握りつぶさない）
        return _result(UNDETERMINED, method, str(exc))


def judge_auto(case: Mapping, evidence: Mapping | None) -> dict:
    """BD-008 2 章の名前。evaluate と同じ。"""
    return evaluate(case, evidence)
