"""System 06: 要件定義書⇔基本設計書の対検査をオフラインで測る（評価セット pair_v1）。

評価セットは quality/docverify_eval/pair_v1/<組 ID>/ に requirements.md・basic_design.md・
defects.jsonl・trace.jsonl を置く。形式と照合規則は同ディレクトリの README.md。

- --validate         : 評価セットの整合を検査し、NG があれば一覧して exit 1
- --defects PRED     : 不整合の予測（defects.jsonl と同じ形式。type と行範囲だけ必須）を採点
- --trace PRED       : 追跡リンクの予測（{"pair","req_lines","design_lines"}）を採点
- 標準ライブラリだけで動く。ネットワーク・LLM を使わない。同じ入力なら同じ結果になる

使い方: venv/bin/python scripts/docverify_pair_eval.py --validate
        venv/bin/python scripts/docverify_pair_eval.py --defects pred.jsonl [--json] [--out result.json]
        venv/bin/python scripts/docverify_pair_eval.py --trace pred.jsonl [--dataset DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "quality" / "docverify_eval" / "pair_v1"
FILES = ("requirements.md", "basic_design.md", "defects.jsonl", "trace.jsonl")
TYPES = ("MISSING_IN_DESIGN", "EXTRA_IN_DESIGN", "CONTRADICTION", "TABLE_MISMATCH",
         "TERM_INCONSISTENCY", "AMBIGUOUS", "UNTESTABLE")
LIMITS = (
    "AI が生成し AI 1 名が注釈した合成データ。注釈者間一致（kappa）は未測定。",
    "実文書での精度を示すものではない。",
    "照合は行範囲の重なりだけで判定し、指摘の説明文の正しさは見ていない。",
)


class DataError(ValueError):
    """入力ファイルの形式が不正（fail fast）。"""


# ---------- 読み込み ----------

def _rng(v, where: str):
    """[a,b] → (a,b)。[] → None。それ以外は DataError。"""
    if v == [] or v is None:
        return None
    if (not isinstance(v, list) or len(v) != 2 or not all(isinstance(x, int) and not isinstance(x, bool) for x in v)
            or v[0] < 1 or v[0] > v[1]):
        raise DataError(f"{where}: 行範囲は [開始, 終了]（1 始まり・開始≦終了）か [] で指定してください: {v!r}")
    return (v[0], v[1])


def _jsonl(path: Path) -> list[tuple[int, dict]]:
    rows = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise DataError(f"{path} {no} 行目: JSON として読めません（{e.msg}）") from None
        if not isinstance(row, dict):
            raise DataError(f"{path} {no} 行目: オブジェクトではありません")
        rows.append((no, row))
    return rows


def pair_dirs(dataset: Path) -> list[Path]:
    if not dataset.is_dir():
        raise DataError(f"評価セットのディレクトリがありません: {dataset}")
    return sorted(p for p in dataset.iterdir() if p.is_dir() and not p.name.startswith("."))


def _defect(row: dict, where: str) -> dict:
    t = row.get("type")
    if t not in TYPES:
        raise DataError(f"{where}: type が 7 種のどれでもありません: {t!r}")
    req, des = _rng(row.get("req_lines"), where), _rng(row.get("design_lines"), where)
    if not req and not des:
        raise DataError(f"{where}: req_lines と design_lines の少なくとも一方に行範囲が必要です")
    return {"pair": str(row.get("pair")), "type": t, "req": req, "des": des}


def _trace(row: dict, where: str) -> dict:
    req = _rng(row.get("req_lines"), where)
    if not req:
        raise DataError(f"{where}: req_lines が必要です")
    dl = row.get("design_lines")
    if not isinstance(dl, list):
        raise DataError(f"{where}: design_lines は行範囲のリストで指定してください: {dl!r}")
    des = [_rng(d, where) for d in dl]
    if any(d is None for d in des):
        raise DataError(f"{where}: design_lines に空の行範囲があります")
    return {"pair": str(row.get("pair")), "req": req, "des": des}


def load_gold(dataset: Path, name: str, parse) -> tuple[list[dict], list[str]]:
    rows, pairs = [], []
    for d in pair_dirs(dataset):
        path = d / name
        if not path.exists():
            continue
        pairs.append(d.name)
        rows += [parse(r, f"{d.name}/{name} {no} 行目") for no, r in _jsonl(path)]
    if not pairs:
        raise DataError(f"{name} を持つ組がありません: {dataset}")
    return rows, pairs


def load_pred(path: Path, parse) -> list[dict]:
    if not path.exists():
        raise DataError(f"予測ファイルがありません: {path}")
    return [parse(r, f"{path.name} {no} 行目") for no, r in _jsonl(path)]


# ---------- 照合 ----------

def _ov(a, b) -> int:
    """2 つの行範囲が重なる行数（片方が None なら 0）。"""
    if not a or not b:
        return 0
    return max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)


def greedy(golds: list, preds: list, score) -> list[tuple[int, int]]:
    """重なりの大きい組から 1 対 1 で割り当てる。同点は正解・予測の出現順。"""
    cand = []
    for gi, g in enumerate(golds):
        for pi, p in enumerate(preds):
            s = score(g, p)
            if s > 0:
                cand.append((-s, gi, pi))
    cand.sort()
    used_g, used_p, out = set(), set(), []
    for _, gi, pi in cand:
        if gi not in used_g and pi not in used_p:
            used_g.add(gi)
            used_p.add(pi)
            out.append((gi, pi))
    return out


def _defect_score(g: dict, p: dict) -> int:
    if g["pair"] != p["pair"] or g["type"] != p["type"]:
        return 0
    return _ov(g["req"], p["req"]) + _ov(g["des"], p["des"])


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    rnd = lambda x: round(x, 3) if x is not None else None  # noqa: E731
    return {"tp": tp, "fp": fp, "fn": fn, "precision": rnd(p), "recall": rnd(r), "f1": rnd(f)}


def _split(gold: list, pred: list, pairs: list[str]) -> tuple[list, list[str]]:
    known = set(pairs)
    return [p for p in pred if p["pair"] in known], sorted({p["pair"] for p in pred} - known)


def score_defects(gold: list[dict], pred: list[dict]) -> dict:
    by_type = {}
    for t in TYPES:
        g = [x for x in gold if x["type"] == t]
        p = [x for x in pred if x["type"] == t]
        tp = len(greedy(g, p, _defect_score))
        by_type[t] = _prf(tp, len(p) - tp, len(g) - tp)
    tp = sum(v["tp"] for v in by_type.values())
    return {"by_type": by_type, "overall": _prf(tp, len(pred) - tp, len(gold) - tp)}


def _links(rows: list[dict]) -> list[dict]:
    return [{"pair": r["pair"], "req": r["req"], "des": d} for r in rows for d in r["des"]]


def score_trace(gold: list[dict], pred: list[dict]) -> dict:
    def link_score(g, p):
        if g["pair"] != p["pair"]:
            return 0
        a, b = _ov(g["req"], p["req"]), _ov(g["des"], p["des"])
        return a + b if a and b else 0

    def req_score(g, p):
        return _ov(g["req"], p["req"]) if g["pair"] == p["pair"] else 0

    gl, pl = _links(gold), _links(pred)
    tp = len(greedy(gl, pl, link_score))
    gu = [r for r in gold if not r["des"]]
    pu = [r for r in pred if not r["des"]]
    tu = len(greedy(gu, pu, req_score))
    return {"links": _prf(tp, len(pl) - tp, len(gl) - tp),
            "unreflected": _prf(tu, len(pu) - tu, len(gu) - tu)}


# ---------- 検査（--validate） ----------

def _in_range(text_lines: list[str], rng, quote: str) -> bool:
    seg = text_lines[rng[0] - 1:rng[1]]
    return quote in "\n".join(seg) or quote in "".join(seg)


def _check_side(ng, where, row, key_l, key_q, lines, fname):
    try:
        rng = _rng(row.get(key_l), where)
    except DataError as e:
        ng.append(str(e))
        return None
    quote = row.get(key_q) or ""
    if rng is None:
        if quote:
            ng.append(f"{where}: {key_l} が空なのに {key_q} があります")
        return None
    if rng[1] > len(lines):
        ng.append(f"{where}: {key_l} {list(rng)} が {fname} の行数 {len(lines)} を超えています")
        return rng
    if not quote:
        ng.append(f"{where}: {key_l} があるのに {key_q} が空です")
    elif not _in_range(lines, rng, quote):
        ng.append(f"{where}: {key_q} が {fname} の {rng[0]}〜{rng[1]} 行目にありません: {quote[:40]!r}")
    return rng


def _validate_pair(d: Path, ng: list[str]) -> None:
    missing = [f for f in FILES if not (d / f).exists()]
    if missing:
        ng.append(f"{d.name}: ファイルがありません: {', '.join(missing)}")
        return
    req_lines = (d / "requirements.md").read_text(encoding="utf-8").splitlines()
    des_lines = (d / "basic_design.md").read_text(encoding="utf-8").splitlines()
    seen, missing_reqs = set(), []
    try:
        drows, trows = _jsonl(d / "defects.jsonl"), _jsonl(d / "trace.jsonl")
    except DataError as e:
        ng.append(str(e))
        return
    for no, row in drows:
        where = f"{d.name}/defects.jsonl {no} 行目"
        if row.get("pair") != d.name:
            ng.append(f"{where}: pair {row.get('pair')!r} がディレクトリ名 {d.name!r} と違います")
        rid = row.get("id")
        if not rid:
            ng.append(f"{where}: id がありません")
        elif rid in seen:
            ng.append(f"{where}: id {rid!r} が重複しています")
        seen.add(rid)
        t = row.get("type")
        if t not in TYPES:
            ng.append(f"{where}: type が 7 種のどれでもありません: {t!r}")
        req = _check_side(ng, where, row, "req_lines", "req_quote", req_lines, "requirements.md")
        des = _check_side(ng, where, row, "design_lines", "design_quote", des_lines, "basic_design.md")
        if not row.get("req_lines") and not row.get("design_lines"):
            ng.append(f"{where}: req_lines と design_lines が両方とも空です")
        if t == "MISSING_IN_DESIGN":
            if req:
                missing_reqs.append((where, rid, req))
            else:
                ng.append(f"{where}: MISSING_IN_DESIGN なのに req_lines がありません")
        if t == "EXTRA_IN_DESIGN" and not des:
            ng.append(f"{where}: EXTRA_IN_DESIGN なのに design_lines がありません")
    traces, keys = [], set()
    for no, row in trows:
        where = f"{d.name}/trace.jsonl {no} 行目"
        if row.get("pair") != d.name:
            ng.append(f"{where}: pair {row.get('pair')!r} がディレクトリ名 {d.name!r} と違います")
        key = row.get("req_key")
        if not key:
            ng.append(f"{where}: req_key がありません")
        elif key in keys:
            ng.append(f"{where}: req_key {key!r} が重複しています")
        keys.add(key)
        try:
            tr = _trace(row, where)
        except DataError as e:
            ng.append(str(e))
            continue
        if tr["req"][1] > len(req_lines):
            ng.append(f"{where}: req_lines {list(tr['req'])} が requirements.md の行数 {len(req_lines)} を超えています")
        for r in tr["des"]:
            if r[1] > len(des_lines):
                ng.append(f"{where}: design_lines {list(r)} が basic_design.md の行数 {len(des_lines)} を超えています")
        traces.append((where, key, tr))
    # MISSING の要件は trace で design_lines が空。逆に design_lines が空の要件には MISSING がある。
    for where, rid, req in missing_reqs:
        hit = [tr for _, _, tr in traces if _ov(tr["req"], req)]
        if not hit:
            ng.append(f"{where}: MISSING {rid!r} の要件 {list(req)} が trace.jsonl にありません")
        elif all(tr["des"] for tr in hit):
            ng.append(f"{where}: MISSING {rid!r} の要件 {list(req)} が trace.jsonl では設計に反映ありです")
    for where, key, tr in traces:
        if not tr["des"] and not any(_ov(tr["req"], req) for _, _, req in missing_reqs):
            ng.append(f"{where}: req_key {key!r} は設計に反映なしなのに MISSING_IN_DESIGN の指摘がありません")


def validate(dataset: Path) -> dict:
    ng: list[str] = []
    dirs = pair_dirs(dataset)
    if not dirs:
        ng.append(f"組がありません: {dataset}")
    for d in dirs:
        _validate_pair(d, ng)
    return {"schema": 1, "mode": "validate", "dataset": str(dataset), "pairs": [d.name for d in dirs],
            "ng_count": len(ng), "ng": ng}


# ---------- 出力 ----------

def _sha(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]


def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _table(head: list[str], rows: list[list]) -> str:
    cells = [head] + [["-" if v is None else str(v) for v in r] for r in rows]
    widths = [max(_w(r[i]) for r in cells) for i in range(len(head))]
    fmt = lambda r: "  ".join(c + " " * (widths[i] - _w(c)) for i, c in enumerate(r)).rstrip()  # noqa: E731
    return "\n".join([fmt(cells[0]), "  ".join("-" * w for w in widths)] + [fmt(r) for r in cells[1:]])


def _row(label: str, m: dict) -> list:
    return [label, m["tp"], m["fp"], m["fn"], m["precision"], m["recall"], m["f1"]]


HEAD = ["区分", "TP", "FP", "FN", "適合率", "再現率", "F1"]


def render(res: dict) -> str:
    if res["mode"] == "validate":
        lines = [f"組: {len(res['pairs'])}  NG: {res['ng_count']}"] + [f"NG  {m}" for m in res["ng"]]
        return "\n".join(lines + (["OK  全組の整合を確認しました"] if not res["ng"] else []))
    out = [f"組: {len(res['dataset']['pairs'])}  予測: {res['predictions']['n']} 件（{res['predictions']['path']}）"]
    if res["ignored_pairs"]:
        out.append(f"評価セットに無い組の予測は採点から除外: {', '.join(res['ignored_pairs'])}")
    if res["mode"] == "defects":
        rows = [_row(t, m) for t, m in res["by_type"].items()] + [_row("全体", res["overall"])]
        out.append(_table(HEAD, rows))
    else:
        out.append(_table(HEAD, [_row("リンク", res["links"]), _row("反映なし要件", res["unreflected"])]))
    out.append("限界: " + " ".join(res["limits"]))
    return "\n".join(out)


def run_score(mode: str, dataset: Path, pred_path: Path) -> dict:
    name, parse, fn = (("defects.jsonl", _defect, score_defects) if mode == "defects"
                       else ("trace.jsonl", _trace, score_trace))
    gold, pairs = load_gold(dataset, name, parse)
    pred_all = load_pred(pred_path, parse)
    pred, ignored = _split(gold, pred_all, pairs)
    files = [dataset / p / name for p in pairs]
    return {"schema": 1, "mode": mode,
            "dataset": {"path": str(dataset), "pairs": pairs, "n_gold": len(gold), "sha256": _sha(files)},
            "predictions": {"path": str(pred_path), "n": len(pred_all), "n_scored": len(pred),
                            "sha256": _sha([pred_path])},
            "ignored_pairs": ignored, **fn(gold, pred), "limits": list(LIMITS)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="System 06 要件定義書⇔基本設計書 対検査の評価")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate", action="store_true", help="評価セットの整合を検査する")
    g.add_argument("--defects", type=Path, metavar="PRED", help="不整合の予測 JSONL を採点する")
    g.add_argument("--trace", type=Path, metavar="PRED", help="追跡リンクの予測 JSONL を採点する")
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--json", action="store_true", help="結果を JSON で標準出力に出す")
    ap.add_argument("--out", type=Path, help="結果 JSON の保存先")
    a = ap.parse_args(argv)
    try:
        if a.validate:
            res = validate(a.dataset)
        else:
            res = run_score("defects" if a.defects else "trace", a.dataset, a.defects or a.trace)
    except DataError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text if a.json else render(res))
    return 1 if res["mode"] == "validate" and res["ng"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
