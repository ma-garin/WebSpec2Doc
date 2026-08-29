"""レコーダーの記録（JSONL）をノーコードのステップ形式へ変換する。

`session_recorder.SessionRecorder` が書く JSONL は「何が起きたか」の生ログで、
そのままでは人が直せない。ノーコード編集の正本は
`web/services/test_step_store.py` のステップ形式なので、ここで橋渡しする。

    記録用ブラウザで操作 → session_*.jsonl → convert_jsonl() → ステップ編集画面 → spec.ts

設計の約束:

- **純関数**。ファイル I/O は `convert_jsonl` だけで、モジュール状態を持たない。
- 出力は必ず `test_step_store.validate()` を通る形にする。通らない形を返すのは
  「変換できた」ことにならない（保存も spec 生成もできない）。
- 落としたイベントは黙って捨てず `conversion_report()` で件数を返す。
  何が消えたか分からない変換は、利用者が記録をやり直す判断をできない。

変換規則（記録イベント → ステップ）:

===========================  ==========================================
記録イベント                  ステップ
===========================  ==========================================
最初の ``visit``              ``goto``（value=URL）
2 件目以降の ``visit``        捨てる（click が起こした遷移を goto で
                             上書きすると、遷移したことの検証が消える）
``click``                    ``click``（target=selectors）
``input`` tag=select         ``select``
``input`` checkbox/radio     ``checked`` が真なら ``check`` / 偽なら ``uncheck``
``input`` masked=true        ``fill`` だが値は ``{{password}}``
``input`` その他             ``fill``
``press``                    ``press``（value=key）
``assert_text``              ``expect_text``（target 空）
``wait_text``                ``wait_text``（target 空）
``finding``                  直前ステップの note へ転記（ステップにしない）
``state``                    無視
===========================  ==========================================
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]


class ConversionError(ValueError):
    """記録をステップへ変換できない。何が足りないかを日本語で名指しする。"""


def _load_step_store() -> Any:
    """ステップ形式の正本モジュールを読む。語彙を自前で二重定義しないため。

    通常は `web.services.test_step_store` として読む（web を先に読み込んだ
    プロセスと同じモジュール実体になる）。web パッケージは import 時に Flask を
    要求するので、Flask の無い環境（変換だけを使う CLI・テスト）では
    ファイル位置から直接読み込んで退避する。
    """
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    try:
        from web.services import test_step_store  # noqa: PLC0415

        return test_step_store
    except Exception:  # noqa: BLE001  # Flask 未導入など web 側の事情で失敗しうる
        import importlib.util  # noqa: PLC0415

        path = _ROOT / "web" / "services" / "test_step_store.py"
        spec = importlib.util.spec_from_file_location("_ws2d_test_step_store", path)
        if spec is None or spec.loader is None:  # pragma: no cover - 配置異常
            raise ConversionError(f"ステップ形式の定義を読めません: {path}") from None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


_STEP_STORE = _load_step_store()
ACTIONS = _STEP_STORE.ACTIONS
SCHEMA_VERSION = _STEP_STORE.SCHEMA_VERSION

# マスクされた入力に入れる差し替え用プレースホルダ。
# 平文は記録に無いので、実行前に人が必ず差し替える必要がある。
MASKED_PLACEHOLDER = "{{password}}"
MASKED_NOTE = "記録時にマスクされました。実行前に値を差し替えてください"

# note の上限（test_step_store._validate_step が 300 文字で切るため、先に揃えておく）
_NOTE_MAX = 300
_LABEL_MAX = 120

# test_id に使える文字（test_step_store._ID_RE に合わせる）
_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]")


# --------------------------------------------------------------------------
# 公開 API
# --------------------------------------------------------------------------
def convert_events(events: list[dict], *, title: str = "", test_id: str = "") -> dict:
    """イベント列を 1 テストのドキュメント断片へ変換する。

    戻り値は {"version":1,"domain":"","tests":[<1件>]} の形（test_step_store の
    ドキュメント形状に合わせる。domain は呼び出し側が埋める）。
    """
    steps, _report = _build(events)
    if not any(step["action"] == "goto" for step in steps):
        # goto が無い＝どの画面から始めるか分からず、この記録からはテストが組めない。
        # 操作ステップだけを返しても実行できないので、理由を添えて落とす。
        raise ConversionError(
            "記録に画面遷移が含まれていません（visit イベントが無いため"
            "「画面を開く」ステップを作れません）。記録をやり直してください。"
        )

    resolved_title = str(title).strip() or _default_title(events)
    resolved_id = _sanitize_id(test_id) if str(test_id).strip() else _stable_id(events)
    return {
        "version": SCHEMA_VERSION,
        "domain": "",
        "tests": [
            {
                "test_id": resolved_id,
                "title": resolved_title[:_LABEL_MAX],
                "enabled": True,
                "note": "探索セッションの記録から自動変換。実行前に値と期待結果を確認してください。",
                "steps": steps,
            }
        ],
    }


def convert_jsonl(path: Path, *, title: str = "", test_id: str = "") -> dict:
    """JSONL ファイルを読んで convert_events に渡す。壊れた行は飛ばして数を記録する。

    壊れた行の件数は戻り値の "skipped_lines" に入れる（test_step_store.validate()
    はこのキーを保持しないため、保存前に呼び出し側が読むこと）。
    """
    events, broken = _read_jsonl(Path(path))
    document = convert_events(events, title=title, test_id=test_id)
    document["skipped_lines"] = broken
    return document


def conversion_report(events: list[dict]) -> dict:
    """変換の内訳を返す。利用者に「何が落ちたか」を見せるため。

    {"converted": n, "skipped": {"state": n, "extra_visit": n, ...},
     "masked_fields": ["password", ...]}

    convert_events と違い、goto が作れない記録でも例外にしない
    （「なぜ変換できないか」を画面に出すのが目的なので、ここで落ちては使えない）。
    """
    _steps, report = _build(events)
    return report


# --------------------------------------------------------------------------
# 変換本体
# --------------------------------------------------------------------------
def _build(events: list[dict]) -> tuple[list[dict], dict]:
    """イベント列からステップ列と内訳レポートを作る（純関数）。

    convert_events と conversion_report の両方がここを通る。
    2 か所で別々に数えると、画面に出る内訳と実際の変換結果がずれる。
    """
    steps: list[dict] = []
    skipped: dict[str, int] = {}
    masked_fields: list[str] = []
    pending_findings: list[str] = []  # 最初のステップができる前に出た気づき
    seen_visit = False

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for event in events:
        if not isinstance(event, dict):
            skip("invalid")
            continue
        kind = str(event.get("kind") or "")

        if kind == "visit":
            if seen_visit:
                # 2 件目以降の visit は捨てる。click が起こした遷移の途中に
                # goto を挟むと、遷移が起きたこと自体の検証が消えるため。
                skip("extra_visit")
                continue
            url = str(event.get("url") or "").strip()
            if not re.match(r"^https?://", url):
                # about:blank / chrome-error: などは開き直せない
                skip("invalid_visit")
                continue
            seen_visit = True
            steps.append(_step("goto", [], url, str(event.get("path") or "")))
            continue

        if kind == "state":
            skip("state")
            continue

        if kind == "finding":
            note = str(event.get("note") or "").strip()
            text = f"気づき: {note}" if note else "気づき（メモなし）"
            if steps:
                _append_note(steps[-1], text)
            else:
                pending_findings.append(text)
            skip("finding")  # ステップにはしないので「落とした」側に数える
            continue

        if kind == "assertion":
            text = str(event.get("text") or "").strip()
            if not text:
                skip("empty_text")
                continue
            steps.append(_step("expect_text", [], text, "表示されているべき文言"))
            continue

        if kind == "wait":
            text = str(event.get("text") or "").strip()
            if not text:
                skip("empty_text")
                continue
            steps.append(_step("wait_text", [], text, "表示されるまで待つ"))
            continue

        if kind != "action":
            skip("unknown_kind")
            continue

        step = _action_step(event, masked_fields, skip)
        if step is not None:
            steps.append(step)

    # 最初のステップより前に出た気づきは、行き場が無いので先頭ステップへ寄せる
    if pending_findings and steps:
        for text in pending_findings:
            _append_note(steps[0], text)

    _number(steps)
    return steps, {
        "converted": len(steps),
        "skipped": skipped,
        "masked_fields": masked_fields,
    }


def _action_step(event: dict, masked_fields: list[str], skip: Any) -> dict | None:
    """kind:"action" の 1 件をステップへ落とす。作れない場合は None を返す。"""
    action_type = str(event.get("action_type") or "")
    targets = _targets(event)
    label = _label(event, targets)

    if action_type == "click":
        if not targets:
            # click は対象必須。セレクタが取れていない記録は再現できない。
            skip("no_target")
            return None
        return _step("click", targets, "", label)

    if action_type == "press":
        key = str(event.get("key") or "").strip()
        if not targets or not key:
            skip("no_target" if not targets else "empty_value")
            return None
        return _step("press", targets, key, label)

    if action_type != "input":
        skip("unknown_action")
        return None

    if not targets:
        skip("no_target")
        return None

    if event.get("masked"):
        # 平文が記録に無いため、値はプレースホルダにして差し替えを強制する。
        masked_fields.append(_field_name(event, targets))
        return _step("fill", targets, MASKED_PLACEHOLDER, label, note=MASKED_NOTE)

    tag = str(event.get("tag") or "").lower()
    input_type = str(event.get("input_type") or "").lower()
    value = str(event.get("value") or "")

    if input_type in ("checkbox", "radio"):
        return _step("check" if event.get("checked") else "uncheck", targets, "", label)

    if tag == "select":
        if not value:
            # select は値必須。空選択は validate() を通らないので落とす。
            skip("empty_value")
            return None
        return _step("select", targets, value, label, note=_option_note(event))

    if not value:
        # 入力のクリア操作。fill は値必須なのでステップにできない。
        skip("empty_value")
        return None
    return _step("fill", targets, value, label)


# --------------------------------------------------------------------------
# 補助（すべて純関数）
# --------------------------------------------------------------------------
def _step(
    action: str, targets: list[str], value: str, label: str, note: str = ""
) -> dict:
    """1 ステップを組み立てる。id は _number() で後から通し番号を振る。"""
    return {
        "id": "",
        "action": action,
        "target": list(targets),
        "value": value,
        "label": (label or ACTIONS[action]["label"])[:_LABEL_MAX],
        "note": note[:_NOTE_MAX],
    }


def _number(steps: list[dict]) -> None:
    for index, step in enumerate(steps, start=1):
        step["id"] = f"s{index}"


def _append_note(step: dict, text: str) -> None:
    """既存 note を消さずに追記する（気づきが複数付く場合がある）。"""
    current = step.get("note") or ""
    step["note"] = (f"{current} / {text}" if current else text)[:_NOTE_MAX]


def _targets(event: dict) -> list[str]:
    """セレクタ候補配列を取り出す。無ければ先頭候補 1 件へ落とす。"""
    raw = event.get("selectors")
    candidates = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
    if candidates:
        return candidates
    selector = str(event.get("selector") or "").strip()
    return [selector] if selector else []


def _label(event: dict, targets: list[str]) -> str:
    """画面上で何を触ったかの手掛かり。セレクタから人が読める断片を拾う。"""
    name = _field_name(event, targets)
    return name if name != "unknown" else ""


def _field_name(event: dict, targets: list[str]) -> str:
    """セレクタ候補から項目名らしき文字列を取り出す（masked_fields の表示用）。"""
    for selector in targets:
        for pattern in (
            r'\[data-testid=[\'"]?([^\'"\]]+)',
            r'\[name=[\'"]?([^\'"\]]+)',
            r"^#([A-Za-z_-][A-Za-z0-9_-]*)$",
            r'\[aria-label=[\'"]?([^\'"\]]+)',
        ):
            match = re.search(pattern, selector)
            if match:
                return match.group(1)[:_LABEL_MAX]
    return "unknown"


def _option_note(event: dict) -> str:
    """select の選択肢テキストは value と別物なので、note に残して照合できるようにする。"""
    text = str(event.get("option_text") or "").strip()
    return f"選択した表示名: {text}" if text else ""


def _default_title(events: list[dict]) -> str:
    """title 未指定時の既定名。最初の visit の URL から日本語の名前を作る。"""
    for event in events:
        if isinstance(event, dict) and str(event.get("kind") or "") == "visit":
            url = str(event.get("url") or "")
            parsed = urlparse(url)
            path = (parsed.path or "/").rstrip("/") or "/"
            where = "トップページ" if path == "/" else path
            host = parsed.netloc or ""
            return f"{host}{' ' if host else ''}{where} の操作記録" if host else f"{where} の操作記録"
    return "操作記録"


def _stable_id(events: list[dict]) -> str:
    """記録内容から安定した test_id を作る。

    同じ記録からは何度変換しても同じ ID になる必要がある
    （変換のたびに ID が変わると、編集済みのテストと突き合わせできない）。
    乱数・時刻は使わず、イベント列そのもののハッシュを使う。
    """
    payload = json.dumps(
        [e for e in events if isinstance(e, dict)],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    prefix = ""
    for event in events:
        if isinstance(event, dict) and str(event.get("kind") or "") == "visit":
            path = str(event.get("path") or "").strip("/")
            prefix = _ID_SAFE_RE.sub("_", path)[:24].strip("_")
            break
    return f"rec_{prefix}_{digest}" if prefix else f"rec_{digest}"


def _sanitize_id(test_id: str) -> str:
    """呼び出し側が渡した test_id を _ID_RE（英数字・ハイフン・アンダースコア 64 文字）へ寄せる。"""
    cleaned = _ID_SAFE_RE.sub("_", str(test_id).strip())[:64]
    if not cleaned:
        raise ConversionError(f"test_id に使える文字がありません: {test_id!r}")
    return cleaned


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    """JSONL を 1 行ずつ読む。壊れた行は飛ばし、件数を返す。

    1 行壊れているだけで記録全体を捨てるのは損失が大きい（記録はやり直せない）。
    """
    if not path.is_file():
        raise ConversionError(f"記録ファイルが見つかりません: {path}")
    events: list[dict] = []
    broken = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            broken += 1
            continue
        if isinstance(record, dict):
            events.append(record)
        else:
            broken += 1
    return events, broken
