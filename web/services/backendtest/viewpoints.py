"""段階 3: 観点表。カタログ 61 観点のすべてを「出す／対象外＋理由」のどちらかにして返す（FR-08-021）。

入力の facts は変更しない。黙って落ちる観点を作らない（coverage の silent が 0 になる）。
"""
from web.services.backendtest.catalog import (
    CATALOG,
    LEVEL_DEFAULTS,
    LEVEL_LABELS,
)

DECIDED = ("emit", "excluded", "adopted", "edited", "discarded")
NEED_REASON_REQUIRED = ("excluded", "discarded")

_LEVEL_ALIASES = {
    "integration": "integration_internal",
    "component_integration": "integration_internal",
    "system_integration": "integration_external",
}
_KIND_LABELS = {"batch": "バッチジョブ", "jobnet": "ジョブネット", "script": "スクリプト", "api": "API"}
_NEED_LABELS = {
    "date": "日付項目",
    "io": "入出力ファイル",
    "fixed": "固定長ファイル",
    "commit": "コミット単位の記述",
    "jobnet": "ジョブの先行・後続",
    "jobnet_kind": "ジョブネット",
    "table_or_io": "入力テーブルまたはファイル",
}


def _text(fact):
    return f"{fact.get('subject', '')} {fact.get('value', '')}".lower()


def _has_date(facts):
    for f in facts:
        if f.get("kind") == "date_rule":
            return True
        if f.get("kind") == "column" and any(
            w in _text(f) for w in ("date", "time", "日付", "日時", "年月")
        ):
            return True
    return False


def _has_jobnet(facts):
    return any(
        f.get("kind") == "rule" and any(w in _text(f) for w in ("ジョブネット", "先行", "後続", "jobnet"))
        for f in facts
    )


def _need_met(need, facts, target_kind):
    """観点が必要とする事実が、取得済みの facts（または対象種別）に在るか。"""
    kinds = {f.get("kind") for f in facts}
    checks = {
        "date": lambda: _has_date(facts),
        "io": lambda: "io" in kinds,
        "fixed": lambda: any(f.get("kind") == "io" and ("固定長" in _text(f) or "fixed" in _text(f)) for f in facts),
        "commit": lambda: "commit" in kinds,
        "jobnet": lambda: target_kind == "jobnet" or _has_jobnet(facts),
        "jobnet_kind": lambda: target_kind == "jobnet",
        "table_or_io": lambda: bool(kinds & {"table", "column", "io"}),
    }
    return checks[need]()


def _normalize_level(level):
    key = _LEVEL_ALIASES.get(level, level)
    if key not in LEVEL_DEFAULTS:
        raise ValueError("テストレベルが正しくありません。結合（内部・外部）・システム・受け入れのいずれかを選んでください。")
    return key


def _decide(entry, facts, level, target_kind):
    """1 観点について (decision, reason) を返す。理由は利用者に見せてよい日本語。"""
    if entry["id"] == "A-1-05":
        return "excluded", "対象外: ジョブ管理製品の直接連携は本システムの対象外です"
    if target_kind not in entry["kinds"]:
        label = _KIND_LABELS.get(target_kind, target_kind)
        want = "・".join(_KIND_LABELS[k] for k in entry["kinds"])
        return "excluded", f"対象外: 対象種別が{label}のため。この観点は{want}が対象です"
    if level not in entry["levels"]:
        return "excluded", f"対象外: {LEVEL_LABELS[level]}の既定の観点に含まれません。レベルを変えると出ます"
    need = entry["needs"]
    notes = []
    if need:
        strict = need == "jobnet_kind"
        if not _need_met(need, facts, target_kind) and (facts or strict):
            label = _NEED_LABELS[need]
            return "excluded", f"対象外: {label}が対象に見当たりません。対象の読み取りに追加されたら再生成してください"
        if not facts:
            notes.append("対象の読み取り結果が無いため暫定で出しています")
    if entry["release"] != "R1":
        notes.append(f"{entry['release']} 以降で提供")
    return "emit", "。".join(notes)


def _viewpoint(entry, decision, reason):
    basis = "根拠: 実務通説（未検証）" if entry["unverified"] else f"根拠: {entry['basis']}"
    return {
        "id": entry["id"],
        "cat": entry["cat"],
        "cat_name": entry["cat_name"],
        "name": entry["name"],
        "technique": entry["technique"],
        "decision": decision,
        "reason": reason,
        "basis": basis,
        "unverified": entry["unverified"],
        "release": entry["release"],
        "priority": entry["priority"],
        "fr": entry["fr"],
        "oracle": entry["oracle"],
        "human_oracle": entry["human_oracle"],
        "provided": entry["release"] == "R1",
        "added_by": None,
    }


def build(facts, level, target_kind):
    """カタログ全件を事実に当てる。戻り値は 61 件すべて（出す／対象外＋理由）。"""
    if target_kind not in _KIND_LABELS:
        raise ValueError("対象種別が正しくありません。バッチジョブ・ジョブネット・スクリプト・API のいずれかを選んでください。")
    lv = _normalize_level(level)
    facts = list(facts or [])
    return [
        _viewpoint(e, *_decide(e, facts, lv, target_kind))
        for e in CATALOG
    ]


def coverage(viewpoints):
    """カタログに対する判断済み件数と、沈黙している観点（判断が無い／対象外なのに理由が無い）。"""
    by_id = {v.get("id"): v for v in viewpoints}
    silent = []
    for e in CATALOG:
        v = by_id.get(e["id"])
        ok = (
            v is not None
            and v.get("decision") in DECIDED
            and not (v["decision"] in NEED_REASON_REQUIRED and not str(v.get("reason", "")).strip())
        )
        if not ok:
            silent.append(e["id"])
    return {"total": len(CATALOG), "decided": len(CATALOG) - len(silent), "silent": silent}
