"""DB 前後比較の差分（純関数）。

突合キーで before / after を辞書化し、片側だけのキーを added / removed、
両側にあるキーは正規化ハッシュで比較して、違う行だけ列ごとに許容差つきで比べる。
計算量は行数 n に対して O(n)。入力は変更せず、新しい dict を返す。

キー欠損・キー重複は握りつぶさず `warnings` に返す。該当行は突合できないため
`indeterminate`（未判定）に分け、added / removed / updated / unchanged には数えない。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

_SAMPLE_LIMIT = 10  # warnings に載せるキーの例の上限


# ---------------------------------------------------------------- 値の正規化

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _dec(v: Any) -> Decimal | None:
    """数値を Decimal に。NaN・無限大・数値でないものは None。"""
    if not _is_num(v):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _canon(v: Any) -> str:
    """型をまたいで比較できる正規形（1 と 1.0 と Decimal('1.00') は同じ）。"""
    if v is None:
        return "n:"
    if isinstance(v, bool):
        return "b:%d" % v
    d = _dec(v)
    if d is not None:
        return "d:" + format(d.normalize(), "f")
    if _is_num(v):
        return "f:" + str(v)  # NaN / inf
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return "t:" + v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return "x:" + bytes(v).hex()
    return "s:" + str(v)


def _presence(v: Any) -> str:
    """mask 列（採番・時刻）は値でなく有無で比べる。"""
    return "set" if v is not None and v != "" else "empty"


def _norm_value(col: str, v: Any, mask: frozenset) -> str:
    return _presence(v) if col in mask else _canon(v)


def row_hash(row: Mapping[str, Any], exclude: Iterable[str] = (),
             mask: Iterable[str] = ()) -> str:
    """除外列・mask 列を除いた正規化 JSON の sha256。列順に依存しない。"""
    ex, mk = frozenset(exclude), frozenset(mask)
    body = {c: _norm_value(c, v, mk) for c, v in row.items() if c not in ex}
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 許容差

def _tol_spec(tolerance: Mapping[str, Any], col: str) -> tuple[Decimal, Decimal]:
    """列の許容差を (絶対差, 相対差) で返す。数値なら絶対差、dict なら abs / rel。"""
    spec = tolerance.get(col)
    if spec is None:
        return Decimal(0), Decimal(0)
    if isinstance(spec, Mapping):
        return (_dec(spec.get("abs", 0)) or Decimal(0),
                _dec(spec.get("rel", 0)) or Decimal(0))
    return (_dec(spec) or Decimal(0)), Decimal(0)


def _same(col: str, b: Any, a: Any, tolerance: Mapping[str, Any], mask: frozenset) -> bool:
    if col in mask:
        return _presence(b) == _presence(a)
    if _canon(b) == _canon(a):
        return True
    db, da = _dec(b), _dec(a)
    if db is None or da is None:
        return False
    abs_t, rel_t = _tol_spec(tolerance, col)
    gap = abs(db - da)
    return gap <= abs_t or gap <= rel_t * max(abs(db), abs(da))


# ---------------------------------------------------------------- 索引化

def _warn(kind: str, side: str, keys: list, message: str) -> dict:
    return {"kind": kind, "side": side, "count": len(keys),
            "samples": keys[:_SAMPLE_LIMIT], "message": message}


def _index(rows: Sequence[Mapping[str, Any]], key: Sequence[str], side: str):
    """行をキーで辞書化。戻り値: (一意なキーの行, 重複キー, 欠損行の番号, warnings)。"""
    label = "前" if side == "before" else "後"
    seen: dict[tuple, Mapping[str, Any]] = {}
    dups: dict[tuple, int] = {}
    missing: list[int] = []
    for i, row in enumerate(rows):
        if any(row.get(k) is None for k in key):
            missing.append(i)
            continue
        kt = tuple(_canon(row[k]) for k in key)
        if kt in seen:
            dups[kt] = dups.get(kt, 1) + 1
        else:
            seen[kt] = row
    warnings = []
    if missing:
        warnings.append(_warn(
            "key_missing", side, [{"row": i} for i in missing],
            "%s の取得結果に突合キーが空の行が %d 件あります。この行は比較せず未判定にしました。"
            "突合キーの列を見直してください。" % (label, len(missing))))
    if dups:
        samples = [{k: seen[kt][k] for k in key} for kt in dups]
        warnings.append(_warn(
            "key_duplicate", side, samples,
            "%s の取得結果に突合キーが重複している行が %d キーあります。重複キーは比較せず未判定にしました。"
            "一意になる突合キーに直してください。" % (label, len(dups))))
    for kt in dups:
        del seen[kt]
    return seen, set(dups), missing, warnings


# ---------------------------------------------------------------- 集計

def _totals(before: Sequence[Mapping], after: Sequence[Mapping],
            aggregate: Sequence[str], tolerance: Mapping[str, Any]) -> tuple[dict, list]:
    """件数と指定列の sum / count（非 NULL 件数）を前後で比べる。"""
    warnings: list[dict] = []
    out = {"count": {"before": len(before), "after": len(after),
                     "equal": len(before) == len(after)}, "cols": {}}
    for col in aggregate:
        stat = {}
        for side, rows in (("before", before), ("after", after)):
            nums = [_dec(r.get(col)) for r in rows if r.get(col) is not None]
            good = [d for d in nums if d is not None]
            if len(good) != len(nums):
                warnings.append(_warn(
                    "non_numeric", side, [col],
                    "列 %s に数値でない値が %d 件あり、合計から除外しました。集計列を見直してください。"
                    % (col, len(nums) - len(good))))
            stat[side] = {"sum": sum(good, Decimal(0)), "count": len(nums)}
        sb, sa = stat["before"]["sum"], stat["after"]["sum"]
        out["cols"][col] = {
            "sum": [_plain(sb), _plain(sa)],
            "count": [stat["before"]["count"], stat["after"]["count"]],
            "equal": (_same(col, sb, sa, tolerance, frozenset())
                      and stat["before"]["count"] == stat["after"]["count"]),
        }
    return out, warnings


def _plain(d: Decimal) -> int | float:
    return int(d) if d == d.to_integral_value() else float(d)


# ---------------------------------------------------------------- 本体

def _changed_cols(b: Mapping, a: Mapping, exclude: frozenset, tolerance: Mapping,
                  mask: frozenset) -> dict:
    cols = {}
    for c in list(b) + [c for c in a if c not in b]:
        if c in exclude:
            continue
        bv, av = b.get(c), a.get(c)
        if not _same(c, bv, av, tolerance, mask):
            cols[c] = [bv, av]
    return cols


def diff(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]],
         key: Sequence[str], exclude: Iterable[str] = (),
         tolerance: Mapping[str, Any] | None = None, mask: Iterable[str] = (),
         aggregate: Sequence[str] = ()) -> dict:
    """前後のスナップショットを突合キーで比べる。

    tolerance: {列: 絶対差} または {列: {"abs": x, "rel": y}}。範囲内は同値。
    mask: 値でなく有無で比べる列。aggregate: 合計・件数を比べる列。
    戻り値: added / removed / updated[{key, cols:{列:[前, 後]}}] / unchanged /
    indeterminate（キー欠損・重複で未判定の件数）/ totals / warnings。
    """
    key = list(key)
    if not key:
        raise ValueError("突合キーが指定されていません。1 列以上の突合キーを選んでください。")
    tol = dict(tolerance or {})
    ex, mk = frozenset(exclude), frozenset(mask)

    b_idx, b_dup, b_miss, w_b = _index(before, key, "before")
    a_idx, a_dup, a_miss, w_a = _index(after, key, "after")
    undecided = b_dup | a_dup  # 片側でも重複したキーは両側とも比較しない

    added = [dict(r) for k, r in a_idx.items() if k not in b_idx and k not in undecided]
    removed = [dict(r) for k, r in b_idx.items() if k not in a_idx and k not in undecided]
    updated, unchanged = [], 0
    for k, b_row in b_idx.items():
        a_row = a_idx.get(k)
        if a_row is None or k in undecided:
            continue
        if row_hash(b_row, ex, mk) != row_hash(a_row, ex, mk):
            cols = _changed_cols(b_row, a_row, ex, tol, mk)
            if cols:
                updated.append({"key": {c: b_row[c] for c in key}, "cols": cols})
                continue
        unchanged += 1

    totals, w_t = _totals(before, after, list(aggregate), tol)
    return {
        "added": added, "removed": removed, "updated": updated, "unchanged": unchanged,
        "indeterminate": len(b_miss) + len(a_miss) + len(undecided),
        "totals": totals,
        "warnings": w_b + w_a + w_t,
    }
