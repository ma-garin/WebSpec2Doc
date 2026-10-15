"""カスタム観点プリセット（FR-06-160・161・165）と組織の参考範囲（FR-06-148）。

既定のプリセットはコード内の定数で、変更・削除しない。複製したものだけをテナントの
<base>/docverify/_r4_presets.json に保存する。参考範囲の上書きは _r4_reference.json。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

# 29148 の品質特性（settings.DEFAULT_CHECKLISTS と同じ項目 ID。品質スコアの項目と対応する）
_REQ_ITEMS = (
    ("necessary", "必要: 各要求は目的の達成に必要か"),
    ("unambiguous", "曖昧でない: 解釈が 1 通りに定まるか"),
    ("complete", "完全: 条件・例外・入出力に抜けが無いか"),
    ("consistent", "一貫: 他の要求や用語と矛盾しないか"),
    ("feasible", "実現可能: 制約の中で実現できるか"),
    ("verifiable", "検証可能: 合否を判定できる基準があるか"),
    ("traceable", "追跡可能: 出所と下流への対応が辿れるか"),
)
_BASIC_ITEMS = (
    ("trace-req", "要求との対応: すべての要求に対応する設計の記述があるか"),
    ("interfaces", "外部との境界: 入出力・連携先・エラー時の扱いが書かれているか"),
    ("data", "データ: 主要なデータの項目・桁・保持期間が定まっているか"),
    ("nfr", "非機能: 性能・可用性・セキュリティの目標値が設計に落ちているか"),
    ("consistent", "一貫: 用語・番号・図表が文書の中で食い違っていないか"),
)
_SCREEN_ITEMS = (
    ("states", "全状態: 通常・処理中・失敗・0 件・入力エラーの表示が決まっているか"),
    ("fields", "入力項目: 必須・桁・形式・初期値が項目ごとに書かれているか"),
    ("messages", "文言: エラー文に次の行動が添えられているか"),
    ("navigation", "遷移: 戻る・取り消し・二重送信時の動きが決まっているか"),
    ("a11y", "操作性: キーボードだけで主要な操作ができるか"),
)
# 書籍付録 C.2 の構造（完了の判定を実行の証跡で行う）を参照し、文面は自作（CC BY-NC-SA 4.0 のため転載しない）
_DOD_ITEMS = (
    ("dod-evidence", "受入基準を実際に動かして確かめ、その結果が記録に残っているか"),
    ("dod-explain", "AI が作った部分を、担当者が読んで説明できるか"),
    ("dod-unverified", "確かめていない箇所が「未検証」と明記されているか"),
    ("dod-rollback", "変更の影響範囲と元に戻す手順が書かれているか"),
)


def _preset(pid: str, name: str, doc_kind: str, items) -> dict:
    return {"id": pid, "name": name, "doc_kind": doc_kind, "builtin": True,
            "items": [{"id": i, "text": t} for i, t in items]}


BUILTIN = (
    _preset("req-29148", "要求仕様書（ISO/IEC/IEEE 29148 の品質特性）", "requirements", _REQ_ITEMS),
    _preset("basic-design", "基本設計書", "basic", _BASIC_ITEMS),
    _preset("screen-design", "画面設計書", "screen", _SCREEN_ITEMS),
    _preset("dod-ai", "AI 時代の完了条件 4 項目", "any", _DOD_ITEMS),
)
_BUILTIN_IDS = {p["id"] for p in BUILTIN}
_PID = re.compile(r"^[a-z0-9-]{1,40}$")

M_NOT_FOUND = "プリセットが見つかりません。画面を再読み込みしてから選び直してください。"
M_BUILTIN = "既定のプリセットは変更・削除できません。複製してから編集してください。"
M_IN_USE = "このプリセットを使っているレビューがあるため削除できません。レビューの観点を別のプリセットに変えてから削除してください。"
M_NAME = "プリセットの名前を入力してください。"
M_ITEMS = "観点の文を 1 つ以上入力してください。"
M_RANGE = "参考範囲は 0 以上の数で、下限が上限以下になるように入力してください。"


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "docverify"


def _read(name: str, default):
    path = _root() / name
    if not path.is_file():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, data) -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, root / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _custom() -> list[dict]:
    return [dict(p) for p in _read("_r4_presets.json", [])]


def list_presets() -> list[dict]:
    return [json.loads(json.dumps(p)) for p in BUILTIN] + _custom()


def get(pid: str) -> dict:
    for p in list_presets():
        if p["id"] == pid:
            return p
    raise KeyError(M_NOT_FOUND)


def _clean_items(items) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise ValueError(M_ITEMS)
    out = []
    for n, i in enumerate(items, start=1):
        text = str((i or {}).get("text") or "").strip() if isinstance(i, dict) else ""
        if not text:
            raise ValueError(M_ITEMS)
        iid = str(i.get("id") or "").strip() or f"item-{n}"
        out.append({"id": iid[:40], "text": text[:400]})
    return out


def duplicate(pid: str, name: str | None = None) -> dict:
    """複製を作って保存し、複製を返す。元のプリセットは変えない（FR-06-161）。"""
    src = get(pid)
    copy = {**src, "id": f"c-{uuid.uuid4().hex[:10]}", "builtin": False,
            "name": (str(name or "").strip() or f"{src['name']} の複製")[:120],
            "items": [dict(i) for i in src["items"]], "copied_from": src["id"]}
    _write("_r4_presets.json", [*_custom(), copy])
    return copy


def update(pid: str, name, items) -> dict:
    if pid in _BUILTIN_IDS:
        raise PermissionError(M_BUILTIN)
    custom = _custom()
    if not any(p["id"] == pid for p in custom):
        raise KeyError(M_NOT_FOUND)
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError(M_NAME)
    clean = _clean_items(items)
    out = [{**p, "name": clean_name[:120], "items": clean} if p["id"] == pid else p for p in custom]
    _write("_r4_presets.json", out)
    return next(p for p in out if p["id"] == pid)


def delete(pid: str, in_use: bool) -> None:
    """使用中は削除しない（FR-06-165）。"""
    if pid in _BUILTIN_IDS:
        raise PermissionError(M_BUILTIN)
    custom = _custom()
    if not any(p["id"] == pid for p in custom):
        raise KeyError(M_NOT_FOUND)
    if in_use:
        raise PermissionError(M_IN_USE)
    _write("_r4_presets.json", [p for p in custom if p["id"] != pid])


def valid_pid(pid: str) -> bool:
    return isinstance(pid, str) and bool(_PID.match(pid))


# --- 組織の参考範囲（FR-06-148） --------------------------------------------------------

def load_reference() -> dict:
    return dict(_read("_r4_reference.json", {}))


def save_reference(body) -> dict:
    """{"basic": {"low","high"} | None, "detail": ...}。None は上書きの解除。"""
    if not isinstance(body, dict):
        raise ValueError(M_RANGE)
    out = {}
    for kind in ("basic", "detail"):
        v = body.get(kind)
        if v is None:
            continue
        if not isinstance(v, dict):
            raise ValueError(M_RANGE)
        lo, hi = v.get("low"), v.get("high")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 for x in (lo, hi)) or lo > hi:
            raise ValueError(M_RANGE)
        out[kind] = {"low": float(lo), "high": float(hi)}
    _write("_r4_reference.json", out)
    return out
