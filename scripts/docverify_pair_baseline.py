#!/usr/bin/env python3
"""System 06（docverify）の現行実装を、組評価セット pair_v1 にかけて予測 JSONL を書く（ベースライン測定用）。

LLM・ネットワークは使わない。web/services/docverify の既存関数を呼ぶだけで、サービス側は変更しない。
採点は別スクリプトの担当。ここは予測を書くだけ。

使い方:
  venv/bin/python scripts/docverify_pair_baseline.py \
      --eval-dir quality/docverify_eval/pair_v1 --out-defects pred_defects.jsonl --out-trace pred_trace.jsonl

型の対応表（現行の指摘 → 評価セットの type）
  checks.candidates（単文の規則。両文書に当てる。指摘した文書側の行に入れる）
    RD.AMBIGUOUS / REQ.AMBIGUOUS_TERM / REQ.OPEN_ENDED / REQ.AND_OR   → AMBIGUOUS
    REQ.MEASURABILITY / REQ.UNIVERSAL                                → UNTESTABLE
    REQ.INCOMPLETE / REQ.MULTIPLE_REQUIREMENTS / その他               → 捨てる（対応する type が無い）
  setcheck.find_pairs（2 文書を合わせた文の組）
    contradiction                                                    → CONTRADICTION
    duplicate                                                        → 捨てる
  trace.build（要件=requirements.md、設計=basic_design.md。ID 書式は FORMATS のうち要件側で最多のもの）
    rows の設計列が空の要件 ID                                       → MISSING_IN_DESIGN（req_lines のみ）
    orphans（要件に無い設計側 ID）                                   → EXTRA_IN_DESIGN（design_lines のみ）
    rows の要件位置と設計位置                                        → リンク予測（--out-trace）
  現行に該当機能が無い type（予測 0 件のまま。標準出力に「未対応: <type>」）
    TABLE_MISMATCH      表の値の突き合わせが無い（md の表は表として取り込まれない）
    TERM_INCONSISTENCY  setcheck.term_variants は組織の同義語辞書が前提で、既定（空）では何も出ない

行番号の戻し方: md は readers._lines が 1 行 = 1 断片で location「N行」を付ける（N は元ファイルの 1 始まりの行）。
  location の N 行目に断片の本文が含まれていればそれを採る。合わなければ本文で元ファイルを検索し、最初に
  含む行を採る。どちらも失敗したら「戻せなかった」に数えて捨てる。範囲は 1 断片 = 1 行なので [N, N]。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.services.docverify import checks, ingest, ingest_r3, setcheck, trace  # noqa: E402

REQ_FILE, DESIGN_FILE = "requirements.md", "basic_design.md"
TYPES = ("MISSING_IN_DESIGN", "EXTRA_IN_DESIGN", "CONTRADICTION", "TABLE_MISMATCH",
         "TERM_INCONSISTENCY", "AMBIGUOUS", "UNTESTABLE")
CHECK_MAP = {
    "RD.AMBIGUOUS": "AMBIGUOUS", "REQ.AMBIGUOUS_TERM": "AMBIGUOUS", "REQ.OPEN_ENDED": "AMBIGUOUS",
    "REQ.AND_OR": "AMBIGUOUS", "REQ.MEASURABILITY": "UNTESTABLE", "REQ.UNIVERSAL": "UNTESTABLE",
}
SET_MAP = {"contradiction": "CONTRADICTION"}
UNSUPPORTED = {
    "TABLE_MISMATCH": "表の値の突き合わせ機能が無い",
    "TERM_INCONSISTENCY": "同義語辞書が空の既定では term_variants が何も出さない",
}
_LINE = re.compile(r"(\d+)行\s*$")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


class Doc:
    """1 文書の取り込み結果と、元 Markdown の行（行番号の戻し先）。"""

    def __init__(self, path: Path, work: Path) -> None:
        self.name = path.name
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.norm_lines = [_norm(x) for x in self.lines]
        _, self.passages = ingest_r3.ingest_r3(path.name, path.read_bytes(), work)
        self.by_id = {p["id"]: p for p in self.passages}

    def line_of(self, location: str, text: str) -> int | None:
        """location（「N行」）と本文から元ファイルの 1 始まりの行番号を返す。戻せなければ None。"""
        key = _norm(text)
        m = _LINE.search(location or "")
        if m:
            n = int(m.group(1))
            if 1 <= n <= len(self.lines) and (not key or key in self.norm_lines[n - 1]):
                return n
        if not key:
            return None
        hit = next((i for i, x in enumerate(self.norm_lines, 1) if key in x), None)
        if hit is None:  # 断片が文に分かれた場合に備え、先頭 20 字でも探す
            hit = next((i for i, x in enumerate(self.norm_lines, 1) if key[:20] and key[:20] in x), None)
        return hit


class Stats:
    def __init__(self) -> None:
        self.raw = Counter()        # 現行の指摘の件数（出所別）
        self.dropped = Counter()    # 型に対応づけられず捨てた件数（規則・種類別）
        self.unmapped_lines = 0     # 行番号に戻せず捨てた件数
        self.emitted = Counter()    # 書いた予測の件数（type 別）
        self.links = 0
        self.dedup = 0
        self.no_ids = 0             # ID を読み取れず追跡表を作れなかった組


def _defect(pair: str, typ: str, req: int | None = None, des: int | None = None,
            req_hi: int | None = None, des_hi: int | None = None) -> dict:
    return {"pair": pair, "type": typ,
            "req_lines": [req, req_hi or req] if req else [],
            "design_lines": [des, des_hi or des] if des else []}


def _check_defects(pair: str, docs: dict[str, Doc], st: Stats) -> list[dict]:
    out = []
    for side, doc in docs.items():
        for f in checks.candidates(doc.passages):
            st.raw["checks"] += 1
            typ = CHECK_MAP.get(f["rule"])
            if typ is None:
                st.dropped[f["rule"]] += 1
                continue
            p = doc.by_id.get(f.get("passage_id")) or {}
            n = doc.line_of(f.get("location", ""), p.get("text") or f.get("quote", ""))
            if n is None:
                st.unmapped_lines += 1
                continue
            out.append(_defect(pair, typ, req=n) if side == "req" else _defect(pair, typ, des=n))
    return out


def _set_defects(pair: str, docs: dict[str, Doc], st: Stats) -> list[dict]:
    documents = [{"id": side, "name": d.name, "passages": d.passages} for side, d in docs.items()]
    out = []
    for p in setcheck.find_pairs(setcheck.units(documents)):
        st.raw["setcheck"] += 1
        typ = SET_MAP.get(p["kind"])
        if typ is None:
            st.dropped[f"SET.{p['kind']}"] += 1
            continue
        lines: dict[str, list[int]] = {"req": [], "design": []}
        ok = True
        for s in (p["a"], p["b"]):
            n = docs[s["doc_id"]].line_of(s["location"], s["text"])
            if n is None:
                ok = False
                break
            lines[s["doc_id"]].append(n)
        if not ok:
            st.unmapped_lines += 1
            continue
        r, d = sorted(lines["req"]), sorted(lines["design"])
        out.append(_defect(pair, typ, req=r[0] if r else None, req_hi=r[-1] if r else None,
                           des=d[0] if d else None, des_hi=d[-1] if d else None))
    return out


def _best_format(passages: list[dict]) -> str | None:
    counts = {f["id"]: len(trace.extract(passages, f["id"])) for f in trace.FORMATS}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else None


def _loc_line(doc: Doc, loc: str) -> int | None:
    """trace の位置「<文書名> N行」を行番号に戻す。本文が無いので location だけで決める。"""
    m = _LINE.search(loc or "")
    n = int(m.group(1)) if m else None
    return n if n and 1 <= n <= len(doc.lines) else None


def _trace(pair: str, docs: dict[str, Doc], st: Stats) -> tuple[list[dict], list[dict]]:
    fmt = _best_format(docs["req"].passages)
    if fmt is None:
        st.no_ids += 1
        return [], []
    table = trace.build([{"id": "req", "name": "", "kind": "requirement", "passages": docs["req"].passages},
                         {"id": "design", "name": "", "kind": "design", "passages": docs["design"].passages}], fmt)
    defects, links = [], []
    for row in table["rows"]:
        st.raw["trace.rows"] += 1
        req = _loc_line(docs["req"], (row.get("requirement") or [""])[0])
        des = [n for n in (_loc_line(docs["design"], x) for x in row.get("design") or []) if n]
        if req is None or (row.get("design") and not des):
            st.unmapped_lines += 1
            continue
        if des:
            links.append({"pair": pair, "req_lines": [req, req], "design_lines": [[n, n] for n in sorted(set(des))]})
        else:
            defects.append(_defect(pair, "MISSING_IN_DESIGN", req=req))
    for o in table["orphans"]:
        st.raw["trace.orphans"] += 1
        des = [n for n in (_loc_line(docs["design"], x) for x in o.get("locations") or []) if n]
        if not des:
            st.unmapped_lines += 1
            continue
        defects.append(_defect(pair, "EXTRA_IN_DESIGN", des=des[0]))
    return defects, links


def _dedup(rows: list[dict], st: Stats) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        key = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if key in seen:
            st.dedup += 1
            continue
        seen.add(key)
        out.append(r)
    return out


def run_pair(pair_dir: Path, st: Stats) -> tuple[list[dict], list[dict]]:
    pair = pair_dir.name
    with tempfile.TemporaryDirectory() as tmp:
        docs = {"req": Doc(pair_dir / REQ_FILE, Path(tmp) / "req"),
                "design": Doc(pair_dir / DESIGN_FILE, Path(tmp) / "design")}
    defects = _check_defects(pair, docs, st) + _set_defects(pair, docs, st)
    t_defects, links = _trace(pair, docs, st)
    defects = _dedup(defects + t_defects, st)
    for d in defects:
        st.emitted[d["type"]] += 1
    st.links += len(links)
    return defects, links


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="docverify 現行実装のベースライン予測を書く")
    ap.add_argument("--eval-dir", type=Path, default=ROOT / "quality/docverify_eval/pair_v1")
    ap.add_argument("--out-defects", type=Path, required=True)
    ap.add_argument("--out-trace", type=Path, required=True)
    args = ap.parse_args(argv)
    pairs = sorted(p for p in args.eval_dir.iterdir()
                   if p.is_dir() and (p / REQ_FILE).is_file() and (p / DESIGN_FILE).is_file()) \
        if args.eval_dir.is_dir() else []
    if not pairs:
        print(f"組が見つかりません: {args.eval_dir}（<組 ID>/{REQ_FILE} と {DESIGN_FILE} を置いてください）")
        return 2
    st, all_defects, all_links, failed = Stats(), [], [], []
    for p in pairs:
        try:
            d, ln = run_pair(p, st)
        except ingest.IngestError as exc:
            failed.append(f"{p.name}: {exc}")
            continue
        all_defects.extend(d)
        all_links.extend(ln)
    _write(args.out_defects, all_defects)
    _write(args.out_trace, all_links)
    print(f"組: {len(pairs)}（取り込み失敗 {len(failed)}）")
    for f in failed:
        print(f"  取り込み失敗 {f}")
    print("現行の指摘: " + "、".join(f"{k} {v}" for k, v in sorted(st.raw.items())))
    print(f"型に対応づけられず捨てた指摘: {sum(st.dropped.values())}"
          + ("（" + "、".join(f"{k} {v}" for k, v in sorted(st.dropped.items())) + "）" if st.dropped else ""))
    print(f"行番号に戻せず捨てた指摘: {st.unmapped_lines}")
    print(f"重複として畳んだ予測: {st.dedup}")
    print(f"ID を読み取れず追跡表を作れなかった組: {st.no_ids}")
    print("欠陥予測: " + "、".join(f"{t} {st.emitted.get(t, 0)}" for t in TYPES) + f"（計 {sum(st.emitted.values())}）")
    print(f"リンク予測: {st.links}")
    for t, why in UNSUPPORTED.items():
        print(f"未対応: {t}（{why}）")
    for t in TYPES:
        if t not in UNSUPPORTED and not st.emitted.get(t):
            print(f"予測 0 件: {t}")
    print(f"出力: {args.out_defects} / {args.out_trace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
