"""テスト設計技法の推奨ロジック（単一の真実源）。

report.json の screen 辞書（forms[].fields[] / transitions / buttons）から、
ISTQB の 8 技法の推奨可否・根拠・テストケース雛形を**ルールベース**で導出する。

この計算結果を report.json の screen に `techniques` として埋め込み、
フロントエンド（技法マトリクス / 技法詳細）とエクスポート（CSV / Excel / spec.ts）が
同一のデータを参照する。LLM には依存しない。
"""

from __future__ import annotations

from dataclasses import dataclass

# ---- 技法定義（マトリクス列順 = この順序） ----

TECHNIQUE_KEYS: tuple[str, ...] = ("ep", "bva", "dt", "st", "ct", "pw", "uc", "comb")

_TECHNIQUE_META: dict[str, tuple[str, str]] = {
    "ep": ("同値分割", "同値分割"),
    "bva": ("境界値分析", "境界値分析"),
    "dt": ("デシジョンテーブル", "決定表"),
    "st": ("状態遷移テスト", "状態遷移"),
    "ct": ("クラシフィケーションツリー", "分類木"),
    "pw": ("ペアワイズ", "PW法"),
    "uc": ("ユースケーステスト", "UCテスト"),
    "comb": ("組み合わせ", "組合せ"),
}

# 入力値とみなさないフィールド種別
_SKIP_TYPES: frozenset[str] = frozenset(("hidden", "submit", "button", "reset", "image"))
# 型由来の境界を持つフィールド種別（min/max 未指定でも境界値分析の対象）
_NUMERIC_TYPES: frozenset[str] = frozenset(
    ("number", "range", "date", "datetime-local", "time", "month", "week")
)
# 選択肢を持つフィールド種別
_CHOICE_TYPES: frozenset[str] = frozenset(("select", "radio", "checkbox"))

_FIELD_TYPE_EXAMPLES: dict[str, tuple[str, str]] = {
    "email": ("user@example.com", "@@invalid, 空欄"),
    "password": ("Abc@1234（8文字以上・記号含む）", "短すぎる, 空欄"),
    "tel": ("090-1234-5678", "abc, 空欄"),
    "number": ("42", "-1, abc, 空欄"),
    "url": ("https://example.com", "example, 空欄"),
    "date": ("2025-06-01", "99/99/99, 空欄"),
    "text": ("有効なテキスト", "空欄, スペースのみ"),
    "textarea": ("有効なテキスト", "空欄, 最大文字数超過"),
    "select": ("有効な選択肢を選択", "未選択（初期値のまま）"),
    "radio": ("いずれかを選択", "未選択（必須の場合）"),
    "checkbox": ("チェックあり", "チェックなし（必須の場合）"),
}


@dataclass(frozen=True)
class TechniqueRecommendation:
    """1 画面・1 技法分の推奨結果。"""

    key: str
    label: str
    abbr: str
    rationale: tuple[str, ...]
    case_stub: str

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "abbr": self.abbr,
            "rationale": list(self.rationale),
            "case_stub": self.case_stub,
        }


# ---- フィールド抽出ヘルパ ----


def _input_fields(screen: dict) -> list[dict]:
    fields: list[dict] = []
    for form in screen.get("forms") or []:
        for field in form.get("fields") or []:
            if (field.get("field_type") or "") not in _SKIP_TYPES:
                fields.append(field)
    return fields


def _name(field: dict) -> str:
    return str(field.get("name") or field.get("field_type") or "")


def _has_bounds(field: dict) -> bool:
    if any(field.get(k) for k in ("maxlength", "minlength", "min_value", "max_value", "pattern")):
        return True
    return (field.get("field_type") or "") in _NUMERIC_TYPES


def _options(field: dict) -> list:
    return list(field.get("options") or [])


# ---- 推奨判定（technique key -> rationale） ----


def _recommend_rationale(screen: dict) -> dict[str, tuple[str, ...]]:
    fields = _input_fields(screen)
    boundary = [f for f in fields if _has_bounds(f)]
    required = [f for f in fields if f.get("required")]
    with_opts = [f for f in fields if _options(f)]
    selects = [f for f in fields if (f.get("field_type") or "") in _CHOICE_TYPES]
    transitions = screen.get("transitions") or {}
    to = list(transitions.get("to") or [])
    frm = list(transitions.get("from") or [])
    buttons = list(screen.get("buttons") or [])
    has_form = bool(fields)

    rec: dict[str, tuple[str, ...]] = {}

    if has_form:
        rec["ep"] = tuple(f"{_name(f)}: 有効値 / 無効値・空値クラス" for f in fields)

    if boundary:
        rec["bva"] = tuple(_bva_reason(f) for f in boundary)

    if len(required) >= 2:
        names = "、".join(_name(f) for f in required)
        patterns = 2 ** min(len(required), 4)
        rec["dt"] = (
            f"必須フィールド {len(required)}件 → 入力有無の組み合わせで {patterns} パターン",
            f"{names} の有効/無効マトリクス",
        )

    if to or len(frm) > 1:
        reasons: list[str] = []
        if to:
            reasons.append("遷移先: " + "、".join(to))
        if len(frm) > 1:
            reasons.append(f"複数の遷移元 ({len(frm)}件): " + "、".join(frm))
        rec["st"] = tuple(reasons)

    if len(selects) >= 1 or len(fields) >= 3:
        reasons = []
        for f in selects:
            count = len(_options(f)) or "複数"
            reasons.append(f"{_name(f)}: {count} 選択肢 → 独立した分類軸")
        if not selects and len(fields) >= 3:
            reasons.append(f"入力パラメータ {len(fields)}件 → 分類ツリーで網羅的カバー")
        rec["ct"] = tuple(reasons)

    if len(fields) >= 4:
        total = 2 ** len(fields) if len(fields) <= 8 else None
        total_text = f"{total} 件" if total is not None else "膨大"
        rec["pw"] = (
            f"入力パラメータ {len(fields)}件 → 全組み合わせは {total_text} → ペアワイズで削減",
        )

    if has_form and (to or len(buttons) >= 2):
        flow = ("、".join(to) + " への遷移") if to else "レスポンス確認"
        reasons = [f"入力→送信→{flow} の一連シナリオ"]
        if len(buttons) >= 2:
            reasons.append("操作ボタン: " + "、".join(buttons[:4]))
        rec["uc"] = tuple(reasons)

    if len(with_opts) >= 2 and len(fields) <= 5:
        total = 1
        for f in with_opts:
            total *= max(len(_options(f)), 2)
        detail = "、".join(f"{_name(f)}: {len(_options(f))}値" for f in with_opts)
        rec["comb"] = (
            f"選択肢フィールド {len(with_opts)}件 → 全組み合わせ {total} パターン（全数テスト可能範囲）",
            detail,
        )

    return rec


def _bva_reason(field: dict) -> str:
    parts: list[str] = []
    if field.get("maxlength"):
        parts.append(f"maxlength={field['maxlength']}")
    if field.get("minlength"):
        parts.append(f"minlength={field['minlength']}")
    if field.get("min_value"):
        parts.append(f"min={field['min_value']}")
    if field.get("max_value"):
        parts.append(f"max={field['max_value']}")
    if field.get("pattern"):
        parts.append("pattern 制約あり")
    if not parts and (field.get("field_type") or "") in _NUMERIC_TYPES:
        parts.append(f"型由来の境界（{field.get('field_type')}）")
    return f"{_name(field)}: " + "、".join(parts)


# ---- ケース雛形（全 8 技法対応） ----


def _option_labels(field: dict, limit: int = 3) -> list[str]:
    labels: list[str] = []
    for opt in _options(field)[:limit]:
        if isinstance(opt, dict):
            labels.append(str(opt.get("label") or opt.get("value") or ""))
        else:
            labels.append(str(opt))
    return [x for x in labels if x]


def _case_stub(key: str, screen: dict) -> str:
    fields = _input_fields(screen)
    transitions = screen.get("transitions") or {}
    to = list(transitions.get("to") or [])
    buttons = list(screen.get("buttons") or [])

    if key == "ep":
        rows = []
        for f in fields[:3]:
            valid, invalid = _FIELD_TYPE_EXAMPLES.get(
                f.get("field_type") or "", _FIELD_TYPE_EXAMPLES["text"]
            )
            rows.append(f"「{_name(f)}」\n  ✓ 有効値: {valid}\n  ✗ 無効値: {invalid}")
        return "\n---\n".join(rows)

    if key == "bva":
        rows = []
        for f in [x for x in fields if _has_bounds(x)][:3]:
            if f.get("maxlength"):
                n = int(f["maxlength"])
                rows.append(f"「{_name(f)}」\n  ✓ {n}文字 → 正常\n  ✗ {n + 1}文字 → エラー\n  ✗ 空欄 → エラー")
            elif f.get("minlength"):
                n = int(f["minlength"])
                rows.append(f"「{_name(f)}」\n  ✓ {n}文字以上 → 正常\n  ✗ {max(0, n - 1)}文字 → エラー")
            elif f.get("min_value") or f.get("max_value"):
                lo = f.get("min_value") or ""
                hi = f.get("max_value") or ""
                rows.append(f"「{_name(f)}」\n  ✓ {lo}〜{hi} → 正常\n  ✗ 範囲外の値 → エラー")
            else:
                rows.append(
                    f"「{_name(f)}」\n  ✓ 型の最小値・最大値・代表値 → 正常\n  ✗ 範囲外・不正な形式 → エラー"
                )
        return "\n---\n".join(r for r in rows if r)

    if key == "dt":
        required = [f for f in fields if f.get("required")]
        if len(required) < 2:
            return ""
        names = [_name(f) for f in required[:4]]
        ellipsis = "..." if len(names) > 2 else ""
        return "\n".join(
            [
                f"条件:  {' | '.join(names)}",
                f"T{'T' * (len(names) - 1)}: {' | '.join('入力あり' for _ in names)} → 送信成功",
                f"…{ellipsis}: {' | '.join('入力あり' if i != len(names) - 1 else '未入力' for i in range(len(names)))} → {names[-1]}エラー",
                f"…{ellipsis}: {' | '.join('未入力' if i == 0 else '入力あり' for i in range(len(names)))} → {names[0]}エラー",
            ]
        )

    if key == "st":
        lines = ["【状態遷移テスト】"]
        for dest in to[:6]:
            lines.append(f"  正常: 現画面 → {dest} への遷移を確認（全遷移カバレッジ）")
        lines.append("  異常: 不正な操作では遷移しない / エラー表示を確認")
        lines.append("  不正遷移: 未ログイン・直接URLアクセス時のガード（リダイレクト）を確認")
        return "\n".join(lines)

    if key == "ct":
        selects = [f for f in fields if _options(f)]
        if not selects:
            selects = fields[:3]
        lines = ["【分類木】各パラメータの分類軸と代表組み合わせ"]
        for f in selects[:4]:
            labels = _option_labels(f) or ["（値の代表クラス）"]
            lines.append(f"  {_name(f)}: " + " / ".join(labels))
        lines.append("  → 各分類クラスを最低1回カバーする組み合わせを選択")
        return "\n".join(lines)

    if key == "pw":
        n = len(fields)
        total = 2**n if n <= 8 else "多数"
        return (
            f"パラメータ数: {n}件\n全組み合わせ: {total}通り\n"
            "→ ペアワイズツール（例: PICT）で2因子間を網羅する最小テストセットを生成\n"
            "https://github.com/microsoft/pict"
        )

    if key == "uc":
        dest = "、".join(to) if to else "応答画面"
        lines = [
            "【ユースケーステスト】",
            f"  基本フロー: 前提=画面表示 → 入力 → 送信 → {dest} へ到達",
            "  代替フロー: 任意項目を変えても完了できることを確認",
            "  例外フロー: 必須未入力 / 不正値で送信 → エラー表示・遷移しないことを確認",
        ]
        if buttons:
            lines.append("  操作ボタン: " + "、".join(buttons[:4]))
        return "\n".join(lines)

    if key == "comb":
        with_opts = [f for f in fields if _options(f)]
        if len(with_opts) < 2:
            return ""
        f1, f2 = with_opts[0], with_opts[1]
        o1 = _option_labels(f1) or ["値1"]
        o2 = _option_labels(f2) or ["値2"]
        lines = [f"{_name(f1)} × {_name(f2)}"]
        for v1 in o1:
            for v2 in o2:
                lines.append(f"  {v1} × {v2}")
        return "\n".join(lines)

    return ""


# ---- 公開 API ----


def recommend_techniques(screen: dict) -> tuple[TechniqueRecommendation, ...]:
    """画面に推奨されるテスト設計技法を、定義順のタプルで返す。"""
    rationale = _recommend_rationale(screen)
    out: list[TechniqueRecommendation] = []
    for key in TECHNIQUE_KEYS:
        if key not in rationale:
            continue
        label, abbr = _TECHNIQUE_META[key]
        out.append(
            TechniqueRecommendation(
                key=key,
                label=label,
                abbr=abbr,
                rationale=rationale[key],
                case_stub=_case_stub(key, screen),
            )
        )
    return tuple(out)


def techniques_for_screen(screen: dict) -> list[dict]:
    """report.json 埋め込み用の JSON シリアライズ可能なリストを返す。"""
    return [rec.to_dict() for rec in recommend_techniques(screen)]
