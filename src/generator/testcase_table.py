"""ローレベルテストケース表の生成。

テスト設計（BVA/DT/PW/ST）と画面実測データから、9列のテストケース表を決定的に生成する。

「初めてシステムを触る作業者が読んでも同じ結果になる」ことを設計目標に置く。そのため:

- 手順には必ず「開くURL」「操作する欄の画面上のラベルとロケータ」「入力する具体値」を書く
- 期待結果は「正しく動くこと」ではなく、画面上で観測できる事象として書く
- 判断が要る箇所（実装依存でエラー文言が確定しない等）は expected に確認手順として明示する

生成は純関数。同じ入力からは必ず同じ ID・同じ順序の表が出る（差分比較のため）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from generator.test_design import (
    DecisionTable,
    PairwiseTable,
    ScreenTestDesign,
    StateTransitionSet,
    TestDesign,
)

# 自動化判定の区分
AUTOMATION_AUTO = "自動化可"
AUTOMATION_MANUAL = "要目視"

_REPEAT_CHAR = "あ"
_LENGTH_VALUE = re.compile(r"^(\d+)文字$")

# 全ケースに共通する前提条件。各行に複製せず、表の上に一度だけ提示する。
COMMON_PRECONDITIONS: tuple[str, ...] = (
    "ブラウザ: Google Chrome（最新版）／ウィンドウ幅 1280px 以上",
    "開始状態: 未ログイン・前のテストの入力が残っていないこと（新しいタブで開く）",
    "テストデータ: 他の担当者が同時に同じデータを更新していないこと",
)


@dataclass(frozen=True)
class Step:
    """1 手順の「人が読む文」と「機械が実行する操作」の対。

    表示文と実行操作を必ず同時に作ることで、両者がずれない。手順文をあとから
    人が編集しても実行内容は変わらない（実行は action 側だけを見る）。
    """

    text: str
    action: dict[str, Any]


@dataclass(frozen=True)
class TestCaseRow:
    """テストケース表の 1 行（列は UI の表示順と一致させる）。"""

    case_id: str
    name: str
    screen: str
    function: str
    viewpoint: str
    preconditions: tuple[str, ...]
    steps: tuple[str, ...]
    expected: tuple[str, ...]
    automation: str
    automation_reason: str
    trace_id: str
    origin: str = "generated"
    # 実行用の構造化操作。表示列には出さず、Playwright コード生成が使う。
    actions: tuple[dict[str, Any], ...] = ()
    assertions: tuple[dict[str, Any], ...] = ()


# =========================================================================
# エントリポイント
# =========================================================================
def build_testcase_table(report: Mapping[str, Any], design: TestDesign) -> tuple[TestCaseRow, ...]:
    """report と TestDesign から、画面順・技法順に並んだテストケース表を作る。"""
    screens = {str(s.get("page_id", "")): s for s in report.get("screens") or []}
    global _SITE_PREFIX, _DUP_TITLES
    _SITE_PREFIX = _common_title_prefix(screens)
    _DUP_TITLES = _duplicate_titles(screens)
    designs = {d.page_id: d for d in design.screens}
    rows: list[TestCaseRow] = []
    for page_id, screen in screens.items():
        ctx = _ScreenContext(screen)
        rows.extend(_display_rows(ctx))
        sd = designs.get(page_id)
        if sd is not None:
            rows.extend(_bva_rows(ctx, sd))
            rows.extend(_dt_rows(ctx, sd))
            rows.extend(_pairwise_rows(ctx, sd))
            rows.extend(_state_rows(ctx, sd, screens))
        rows.extend(_transition_rows(ctx, screens))
    return tuple(rows)


# =========================================================================
# 画面コンテキスト（手順文を組み立てるための材料をまとめる）
# =========================================================================
class _ScreenContext:
    def __init__(self, screen: Mapping[str, Any]) -> None:
        self.raw = screen
        self.page_id = str(screen.get("page_id", ""))
        self.title = _screen_title(screen)
        self.url = str(screen.get("url", ""))
        self.buttons = [str(b) for b in (screen.get("buttons") or []) if str(b).strip()]
        self.forms = list(screen.get("forms") or [])
        self.fields = _input_fields(screen)
        self.field_by_name = {_field_key(f): f for f in self.fields}

    @property
    def label(self) -> str:
        return f"{self.page_id} {self.title}".strip()

    @property
    def function(self) -> str:
        """機能名: 画面上の主要操作（送信ボタン名 → フォーム action → 画面表示）。"""
        if self.buttons:
            return self.buttons[0]
        if self.forms:
            action = str(self.forms[0].get("action") or "")
            name = action.rstrip("/").split("/")[-1].split(".")[0]
            if name:
                return name
        return "画面表示"

    @property
    def submit_label(self) -> str:
        return self.buttons[0] if self.buttons else "送信"

    def preconditions(self, *extra: str) -> tuple[str, ...]:
        """画面固有の前提条件だけを返す。

        全ケース共通の前提（ブラウザ・開始状態）は COMMON_PRECONDITIONS 側に置く。
        全行に同じ 3 行を並べると表が縦に伸び、固有の前提が埋もれるため分離する。
        """
        base = [f"{self.page_id}（{self.title}）を {self.url or '（URL未取得）'} で開けること"]
        base.extend(x for x in extra if x)
        return tuple(base)

    def open_step(self) -> Step:
        return Step(
            f"ブラウザの新しいタブで {self.url} を開く",
            {"type": "goto", "url": self.url},
        )


# 全画面のタイトルに共通して付くサイト名。テスト名に何度も出ると
# 「DemoMart - トップ → DemoMart - 商品一覧」のように読む場所が埋まるため、
# 表を組み立てるたびに求めて落とす。
_SITE_PREFIX = ""


def _common_title_prefix(screens: Mapping[str, Mapping[str, Any]]) -> str:
    """全画面のタイトルが共有する接頭辞（「DemoMart - 」など）。

    2 画面以上で、区切り文字（- – — : ｜ |）まで一致する場合だけ返す。
    途中で切ると意味が壊れるので、区切りの位置でしか落とさない。
    """
    titles = [
        str(s.get("title") or "").split("|")[0].strip()
        for s in screens.values()
        if str(s.get("title") or "").strip()
    ]
    if len(titles) < 2:
        return ""
    first = titles[0]
    end = len(first)
    for other in titles[1:]:
        i = 0
        while i < end and i < len(other) and first[i] == other[i]:
            i += 1
        end = i
        if not end:
            return ""
    head = first[:end]
    for sep in (" - ", " – ", " — ", ": ", "："):
        pos = head.rfind(sep)
        if pos > 0:
            return head[: pos + len(sep)]
    return ""


# 同じ <title> を持つ画面が複数あると、名前だけでは見分けがつかない
# （「トップ → トップ」に見えてしまう）。表を組み立てるたびに求める。
_DUP_TITLES: frozenset[str] = frozenset()


def _screen_title(screen: Mapping[str, Any]) -> str:
    title = str(screen.get("title") or "")
    # 「商品一覧 | QAストア会員注文システム」→「商品一覧」（サイト名は全画面共通で冗長）
    title = title.split("|")[0].strip()
    if _SITE_PREFIX and title.startswith(_SITE_PREFIX) and len(title) > len(_SITE_PREFIX):
        title = title[len(_SITE_PREFIX):].strip()
    title = title or str(screen.get("page_id", ""))
    if title in _DUP_TITLES:
        path = _url_path(str(screen.get("url") or ""))
        if path:
            title = f"{title}（{path}）"
    return title



def _url_path(url: str) -> str:
    """URL のパス部分。見分け用の短い手掛かりにする。"""
    if not url:
        return ""
    body = url.split("://", 1)[-1]
    slash = body.find("/")
    return body[slash:] if slash >= 0 else "/"


def _duplicate_titles(screens: Mapping[str, Mapping[str, Any]]) -> frozenset[str]:
    """2 画面以上で共有されているタイトル。"""
    seen: dict[str, int] = {}
    for sc in screens.values():
        t = str(sc.get("title") or "").split("|")[0].strip()
        if _SITE_PREFIX and t.startswith(_SITE_PREFIX):
            t = t[len(_SITE_PREFIX):].strip()
        if t:
            seen[t] = seen.get(t, 0) + 1
    return frozenset(k for k, n in seen.items() if n > 1)

def _input_fields(screen: Mapping[str, Any]) -> list[dict[str, Any]]:
    skip = {"hidden", "submit", "button", "reset", "image"}
    out: list[dict[str, Any]] = []
    for form in screen.get("forms") or []:
        for fld in form.get("fields") or []:
            if str(fld.get("field_type", "")) not in skip:
                out.append(dict(fld))
    return out


def _field_key(fld: Mapping[str, Any]) -> str:
    return str(fld.get("name") or fld.get("field_type") or "field")


# 欄名として使える属性（優先順）。placeholder は「入力例」であって欄名ではないため使わない。
_LABEL_KEYS = ("label", "label_text", "aria_label", "title")


def _field_label(fld: Mapping[str, Any] | None, fallback: str) -> str:
    """画面に見えている欄名を返す。取得できなければ fallback（name 属性など）。"""
    if fld is None:
        return str(fallback)
    for key in _LABEL_KEYS:
        value = str(fld.get(key) or "").strip()
        if value:
            return value
    return str(fallback)


# =========================================================================
# 手順の文言（作業者が迷わない粒度に固定する）
# =========================================================================
def _field_ref(fld: Mapping[str, Any] | None, fallback: str) -> str:
    """欄の指し方: 画面上のラベル＋ロケータ。ラベル未取得なら name 属性で代替する。"""
    if fld is None:
        return f"「{fallback}」欄"
    label = str(fld.get("label_text") or fld.get("aria_label") or "").strip()
    shown = label or _field_key(fld)
    locator = _locator(fld)
    return f"「{shown}」欄（{locator}）" if locator else f"「{shown}」欄"


def _locator(fld: Mapping[str, Any]) -> str:
    locators = fld.get("locators") or []
    if locators:
        return str(locators[0])
    element_id = str(fld.get("element_id") or "")
    return f"#{element_id}" if element_id else ""


def _render_value(value: str) -> str:
    """設計上の値表現を、そのまま打てる指示に開く（「51文字」→ 実際に打つ内容）。"""
    text = str(value)
    m = _LENGTH_VALUE.match(text)
    if m:
        n = int(m.group(1))
        if n == 0:
            return ""
        return f"「{_REPEAT_CHAR}」を{n}回繰り返した文字列（{_REPEAT_CHAR * min(n, 5)}…／{n}文字）"
    return f"「{text}」" if text != "" else ""


def _resolve_class_value(fld: Mapping[str, Any] | None, value: str) -> str:
    """同値クラスの抽象ラベル（有効値／無効値）を、その欄に実際に入れられる値へ解決する。

    「有効値」のままでは作業者も何を入れるか判断できず、number 欄には物理的に入力できない。
    """
    if value == "有効値":
        return _sample_value(fld)
    if value != "無効値":
        return value
    field_type = str((fld or {}).get("field_type", ""))
    if field_type == "number":
        # 数値欄に文字は入力できないため、範囲外の数値を無効値として使う
        return "-1"
    if field_type == "email":
        return "not-an-email"
    return "!" * 3


def _actual_value(value: str) -> str:
    """実行時に実際に入力する文字列（「51文字」→ 「あ」×51）。"""
    text = str(value)
    m = _LENGTH_VALUE.match(text)
    if m:
        return _REPEAT_CHAR * int(m.group(1))
    return text


def _input_step(fld: Mapping[str, Any] | None, fallback: str, value: str) -> Step:
    ref = _field_ref(fld, fallback)
    field_type = str((fld or {}).get("field_type", ""))
    value = _resolve_class_value(fld, value)
    rendered = _render_value(value)
    locator = _locator(fld) if fld else ""
    actual = _actual_value(value)
    label = fallback if fld is None else _field_key(fld)
    if rendered == "":
        return Step(
            f"{ref}は空欄のままにする（初期値が入っている場合は削除する）",
            {"type": "clear", "locator": locator, "field": label},
        )
    if field_type in {"select", "radio"}:
        return Step(
            f"{ref}で{rendered}を選択する",
            {"type": "select", "locator": locator, "value": actual, "field": label},
        )
    return Step(
        f"{ref}に{rendered}を入力する",
        {"type": "fill", "locator": locator, "value": actual, "field": label},
    )


def _submit_step(ctx: _ScreenContext) -> Step:
    return Step(
        f"「{ctx.submit_label}」ボタンをクリックする",
        {"type": "click_text", "text": ctx.submit_label},
    )


def _fill_other_required_steps(ctx: _ScreenContext, *skip: str) -> list[Step]:
    """検証対象以外の必須項目を、具体値つきで 1 項目 1 手順に展開する。

    「規定内の値を入力」のような書き方だと実行者ごとに入力が変わり、結果が一致しない。
    """
    skipped = set(skip)
    return [
        _input_step(f, _field_key(f), _sample_value(f))
        for f in ctx.fields
        if _field_key(f) not in skipped and f.get("required")
    ]


def _split_steps(steps: list[Step]) -> tuple[tuple[str, ...], tuple[dict[str, Any], ...]]:
    """Step 列を「表示用の文」と「実行用の操作」に分ける。"""
    return tuple(s.text for s in steps), tuple(s.action for s in steps if s.action)


def _automation_for(fld: Mapping[str, Any] | None) -> tuple[str, str]:
    if fld is None:
        return AUTOMATION_AUTO, "URL とページタイトルだけで判定できるため"
    locator = _locator(fld)
    if not locator:
        return AUTOMATION_MANUAL, "要素を一意に特定するロケータが取得できていないため"
    return AUTOMATION_AUTO, f"ロケータ {locator} が実測済みのため"


# =========================================================================
# 技法ごとの行生成
# =========================================================================
def _display_rows(ctx: _ScreenContext) -> list[TestCaseRow]:
    steps = [
        ctx.open_step(),
        Step("ページの読み込み完了を待つ（読み込み中表示が消えるまで）", {"type": "wait_load"}),
    ]
    expected = [
        f"ブラウザのタブに「{ctx.raw.get('title') or ctx.title}」が表示される",
        f"画面内に見出し「{(ctx.raw.get('headings') or [ctx.title])[0]}」が表示される",
        "エラーメッセージ・404/500 の画面が表示されない",
    ]
    texts, actions = _split_steps(steps)
    return [
        TestCaseRow(
            case_id=f"TC-{ctx.page_id}-DSP-001",
            name=f"{ctx.title}画面が正常に表示される",
            screen=ctx.label,
            function="画面表示",
            viewpoint="画面表示確認",
            preconditions=ctx.preconditions(),
            steps=texts,
            expected=tuple(expected),
            automation=AUTOMATION_AUTO,
            automation_reason="URL とページタイトルだけで判定できるため",
            trace_id=ctx.page_id,
            actions=actions,
            assertions=(
                {"type": "expect_title", "value": str(ctx.raw.get("title") or ctx.title)},
                {"type": "expect_text", "value": str((ctx.raw.get("headings") or [ctx.title])[0])},
            ),
        )
    ]


def _bva_rows(ctx: _ScreenContext, sd: ScreenTestDesign) -> list[TestCaseRow]:
    rows: list[TestCaseRow] = []
    seq = 0
    for table in sd.bva:
        fld = ctx.field_by_name.get(table.field_name)
        for case in table.cases:
            seq += 1
            steps = [ctx.open_step(), _input_step(fld, table.field_name, case.value)]
            steps.extend(_fill_other_required_steps(ctx, table.field_name))
            steps.append(_submit_step(ctx))
            automation, reason = _automation_for(fld)
            if case.expected == "要確認":
                # 仕様が未確定な値カタログ由来のケースは、合否を機械判定できない
                automation, reason = AUTOMATION_MANUAL, "期待結果が仕様未確定（要確認）のため"
            elif case.expected == "無効" and str(case.evidence).startswith("値カタログ"):
                # 「未登録アドレス」等は弾くかどうかがアプリ仕様。機械判定すると誤検知になる
                automation, reason = (
                    AUTOMATION_MANUAL,
                    "無効判定がアプリ仕様に依存するため（値カタログ由来）",
                )
            texts, actions = _split_steps(steps)
            rows.append(
                TestCaseRow(
                    case_id=f"TC-{ctx.page_id}-BVA-{seq:03d}",
                    name=f"{_field_label(fld, table.field_name)}: {case.label}（{case.value}）",
                    screen=ctx.label,
                    function=ctx.function,
                    viewpoint=f"境界値分析／{case.label}",
                    preconditions=ctx.preconditions(),
                    steps=texts,
                    expected=_bva_expected(ctx, fld, table.field_name, case.expected),
                    automation=automation,
                    automation_reason=reason,
                    trace_id=f"{ctx.page_id}:{table.field_name}",
                    actions=actions,
                    assertions=_bva_assertions(ctx, fld, case),
                )
            )
    return rows


def _bva_expected(
    ctx: _ScreenContext,
    fld: Mapping[str, Any] | None,
    field_name: str,
    verdict: str,
) -> tuple[str, ...]:
    ref = _field_ref(fld, field_name)
    if verdict == "有効":
        return (
            f"{ref} にエラーメッセージが表示されない",
            f"「{ctx.submit_label}」が実行され、画面が次の状態へ進む（URL または表示内容が変わる）",
        )
    if verdict == "無効":
        return (
            f"{ref} の近くにエラーメッセージが表示される（文言は実装依存のため、表示の有無で判定する）",
            "送信は行われず、入力した値が画面に保持される",
            "ブラウザ側で入力自体が制限される場合は、制限された結果（入力可能な最大文字数など）を記録する",
        )
    return (
        f"{ref} の挙動を記録する（受理／拒否のいずれか）",
        "仕様が確定していないため、結果を事実として記録し、判定は担当者に確認する",
    )


def _bva_assertions(
    ctx: _ScreenContext, fld: Mapping[str, Any] | None, case: Any
) -> tuple[dict[str, Any], ...]:
    """境界値ケースの機械検証。

    エラー文言は実装依存なので当てにしない。仕様が確定しない「要確認」は自動判定しない。

    maxlength 属性がある欄の「上限超過」は、ブラウザが入力自体を切るため送信は成功する。
    この場合に「送信されないこと」を期待すると誤 FAIL になるので、
    「入力が maxlength までに制限されること」を検証する。
    """
    verdict = getattr(case, "expected", "")
    if verdict == "有効":
        return ({"type": "expect_no_error"},)
    if verdict != "無効":
        return ()
    locator = _locator(fld or {})
    maxlength = (fld or {}).get("maxlength")
    evidence = str(getattr(case, "evidence", ""))
    if locator and isinstance(maxlength, int) and evidence.startswith("maxlength="):
        # 入力の制限は「送信前」に見る（送信すると画面が変わり要素が消える）
        return (
            {
                "type": "expect_value_length",
                "locator": locator,
                "max": maxlength,
                "stage": "after_input",
            },
        )
    return ({"type": "expect_stay", "url": ctx.url, "locator": locator},)


def _dt_rows(ctx: _ScreenContext, sd: ScreenTestDesign) -> list[TestCaseRow]:
    dt: DecisionTable | None = sd.decision_table
    if dt is None:
        return []
    rows: list[TestCaseRow] = []
    for idx, rule in enumerate(dt.rules, start=1):
        steps = [ctx.open_step()]
        for name, present in zip(dt.conditions, rule.conditions, strict=False):
            fld = ctx.field_by_name.get(name)
            steps.append(_input_step(fld, name, _sample_value(fld) if present else ""))
        # 条件に含まれない必須項目（max_dt_conditions で溢れた分）も具体値で埋める
        steps.extend(_fill_other_required_steps(ctx, *dt.conditions))
        steps.append(_submit_step(ctx))
        filled = [n for n, p in zip(dt.conditions, rule.conditions, strict=False) if p]
        missing = [n for n, p in zip(dt.conditions, rule.conditions, strict=False) if not p]
        texts, actions = _split_steps(steps)
        rows.append(
            TestCaseRow(
                case_id=f"TC-{ctx.page_id}-DT-{idx:03d}",
                name="必須項目の組み合わせ: "
                + (
                    f"入力あり={'、'.join(filled) or 'なし'}／未入力={'、'.join(missing) or 'なし'}"
                ),
                screen=ctx.label,
                function=ctx.function,
                viewpoint="デシジョンテーブル／必須チェック",
                preconditions=ctx.preconditions(),
                steps=texts,
                expected=_dt_expected(ctx, missing),
                automation=AUTOMATION_AUTO,
                automation_reason="入力と送信のみで判定でき、目視確認が不要なため",
                trace_id=f"{ctx.page_id}:DT",
                actions=actions,
                assertions=(
                    ({"type": "expect_stay", "url": ctx.url},)
                    if missing
                    else ({"type": "expect_no_error"},)
                ),
            )
        )
    return rows


def _dt_expected(ctx: _ScreenContext, missing: list[str]) -> tuple[str, ...]:
    if not missing:
        return (
            "エラーメッセージが表示されない",
            f"「{ctx.submit_label}」が実行され、画面が次の状態へ進む（URL または表示内容が変わる）",
        )
    names = "、".join(missing)
    return (
        f"未入力の項目（{names}）それぞれにエラーメッセージが表示される",
        "送信は行われず、同じ画面に留まる",
        "入力済みの項目の値が消えていない",
    )


# 項目名から推測する既定値。実行者が値を考えなくて済むよう固定値を持たせる。
_NAME_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("zip", "postal", "yubin", "郵便"), "1000001"),
    (("tel", "phone", "電話"), "09012345678"),
    (("kana", "カナ", "フリガナ"), "テストタロウ"),
    (("address", "addr", "住所"), "東京都千代田区1-1-1"),
    (("name", "氏名", "名前"), "テスト太郎"),
    (("qty", "quantity", "数量", "個数"), "1"),
    (("email", "mail", "メール"), "test@example.com"),
)


# 画面が申告している書式（pattern）から、実際に通る値を組み立てるための対応表。
# 「テスト」のような通らない値を入れると、そのケースは何も確かめられない。
_PATTERN_SAMPLES: tuple[tuple[str, str], ...] = (
    # カード番号など「数字と空白の 13〜19 桁」
    (r"[0-9 ]{13,19}", "4242424242424242"),
    (r"[0-9]{13,19}", "4242424242424242"),
    # 有効期限 MM/YY
    (r"(0[1-9]|1[0-2])/[0-9]{2}", "12/28"),
    (r"[0-9]{2}/[0-9]{2}", "12/28"),
)


def _digits_only(pattern: str) -> int:
    """`[0-9]{n}` 形式の桁数。取れなければ 0。"""
    m = re.search(r"\[0-9\]\{(\d+)(?:,(\d+))?\}", pattern)
    if not m:
        return 0
    return int(m.group(2) or m.group(1))



def _matches(pattern: str, value: str) -> bool:
    """value が pattern（HTML の pattern 属性）を満たすか。壊れた式は満たさない扱い。"""
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return False

def _value_from_pattern(pattern: str, maxlength: Any) -> str:
    """pattern から、それを満たす値を作る。作れなければ空文字を返す（でっち上げない）。"""
    if not pattern:
        return ""
    compact = pattern.replace("^", "").replace("$", "").strip()
    for sig, sample in _PATTERN_SAMPLES:
        if sig in compact:
            return sample
    n = _digits_only(compact)
    if n:
        if isinstance(maxlength, int) and 0 < maxlength < n:
            n = maxlength
        return "1" * n
    if re.fullmatch(r"[A-Za-z ]\{?\d*,?\d*\}?", compact or "x"):
        return ""
    return ""


def _sample_value(fld: Mapping[str, Any] | None) -> str:
    """必須チェック用の既定値。

    画面が申告している制約（pattern・型・min/max・選択肢）を優先して、
    **実際にその欄を通る値**を返す。制約を無視した固定文字列を入れると、
    「必須チェックが働くか」を確かめるはずのケースが、書式エラーで
    落ちるだけになり、何も確かめられなくなる。
    """
    if fld is None:
        return "テスト"
    field_type = str(fld.get("field_type", ""))
    options = [str(o) for o in (fld.get("options") or []) if str(o)]
    if field_type in {"select", "radio"} and options:
        # 先頭は「選択してください」等のプレースホルダのことが多いため 2 番目を優先
        return options[1] if len(options) > 1 else options[0]
    if field_type == "email":
        return "test@example.com"
    if field_type == "number":
        lo = fld.get("min_value")
        hi = fld.get("max_value")
        for cand in (lo, hi):
            if str(cand or "").strip():
                return str(cand).strip()
        return "1"

    maxlength = fld.get("maxlength")
    pattern = str(fld.get("pattern") or "")
    placeholder = str(fld.get("placeholder") or "").strip()
    fits_len = not (isinstance(maxlength, int) and maxlength > 0 and len(placeholder) > maxlength)
    # 1) 画面に書かれた例（placeholder）が書式を満たすなら、それが一番良い見本。
    #    作り物の値より、その欄で実際に想定されている形が伝わる。
    if placeholder and fits_len and not re.search(r"[ぁ-んァ-ヶ一-龠]", placeholder):
        if not pattern or _matches(pattern, placeholder):
            return placeholder
    # 2) 例が無い・満たさないときは、書式から組み立てる
    from_pattern = _value_from_pattern(pattern, maxlength)
    if from_pattern:
        return from_pattern
    # 3) 項目名からの既定値
    key = f"{_field_key(fld)} {fld.get('label_text') or ''}".lower()
    value = "テスト"
    for keywords, sample in _NAME_HINTS:
        if any(k in key for k in keywords):
            value = sample
            break
    if isinstance(maxlength, int) and maxlength > 0 and len(value) > maxlength:
        value = value[:maxlength]
    return value


def _pairwise_rows(ctx: _ScreenContext, sd: ScreenTestDesign) -> list[TestCaseRow]:
    pw: PairwiseTable | None = sd.pairwise
    if pw is None:
        return []
    rows: list[TestCaseRow] = []
    for idx, values in enumerate(pw.rows, start=1):
        steps = [ctx.open_step()]
        pairs: list[str] = []
        for param, value in zip(pw.params, values, strict=False):
            fld = ctx.field_by_name.get(param.name)
            steps.append(_input_step(fld, param.name, value))
            pairs.append(f"{param.name}={value}")
        steps.extend(_fill_other_required_steps(ctx, *(p.name for p in pw.params)))
        steps.append(_submit_step(ctx))
        texts, actions = _split_steps(steps)
        rows.append(
            TestCaseRow(
                case_id=f"TC-{ctx.page_id}-PW-{idx:03d}",
                name="組み合わせ: " + "／".join(pairs),
                screen=ctx.label,
                function=ctx.function,
                viewpoint=f"ペアワイズ（{pw.strength}-way）／組み合わせ",
                preconditions=ctx.preconditions(),
                steps=texts,
                expected=_pairwise_expected(values),
                automation=AUTOMATION_AUTO,
                automation_reason="入力値の組み合わせのみで完結するため",
                trace_id=f"{ctx.page_id}:PW",
                actions=actions,
                assertions=({"type": "expect_no_server_error"},),
            )
        )
    return rows



def _pairwise_expected(values: Sequence[Any]) -> tuple[str, ...]:
    """組み合わせに応じた期待結果。

    無効値を 1 つでも含むなら、通ってはいけない。全ケースに
    「処理が実行される」と書くと、落ちるべきケースが通っても気づけない。
    """
    has_invalid = any("無効" in str(v) for v in values)
    if has_invalid:
        return (
            "無効な値を入れた項目にエラーメッセージが表示される",
            "送信は行われず、同じ画面に留まる",
            "システムエラー（500 等）にはならない",
        )
    return (
        "入力した組み合わせで処理が実行され、次の状態へ進む",
        "システムエラー（500 等）が出ない",
        "入力した値が、送信後の画面にそのまま反映されている",
    )

def _state_rows(
    ctx: _ScreenContext, sd: ScreenTestDesign, screens: Mapping[str, Mapping[str, Any]]
) -> list[TestCaseRow]:
    st: StateTransitionSet | None = sd.state_transitions
    if st is None:
        return []
    rows: list[TestCaseRow] = []
    idx = 0
    for seq in st.sequences:
        # 同じ画面へ戻るだけの並びは、遷移として確かめるものが無い。
        # 「トップ → トップ」のようなケースが混ざると、一覧の信頼が落ちる。
        if _is_meaningless_sequence(seq.steps, ctx.page_id, screens):
            continue
        idx += 1
        steps = [ctx.open_step()]
        last_url = ""
        for nxt in seq.steps[1:]:
            target = screens.get(nxt) or {}
            target_title = _screen_title(target)
            last_url = str(target.get("url") or "")
            steps.append(
                Step(
                    f"{nxt}（{target_title}）へ進むリンクまたはボタンをクリックする",
                    {"type": "click_link_to", "url": last_url, "title": target_title},
                )
            )
        texts, actions = _split_steps(steps)
        rows.append(
            TestCaseRow(
                case_id=f"TC-{ctx.page_id}-ST-{idx:03d}",
                name="画面遷移の連続操作: "
                + " → ".join(
                    _screen_title(screens.get(page) or {}) or page for page in seq.steps
                ),
                screen=ctx.label,
                function="画面遷移",
                viewpoint=f"状態遷移テスト（{st.n_switch}-スイッチ）",
                preconditions=ctx.preconditions(),
                steps=texts,
                expected=tuple(
                    f"{nxt}（{_screen_title(screens.get(nxt) or {})}）が表示される"
                    for nxt in seq.steps[1:]
                )
                + ("途中でエラー画面・空白画面にならない",),
                automation=AUTOMATION_AUTO,
                automation_reason="遷移先 URL の一致で判定できるため",
                trace_id="->".join(seq.steps),
                actions=actions,
                assertions=(({"type": "expect_url", "value": last_url},) if last_url else ()),
            )
        )
    return rows



def _is_meaningless_sequence(
    steps: Sequence[str], page_id: str, screens: Mapping[str, Mapping[str, Any]]
) -> bool:
    """確かめるものが無い遷移か。

    - 遷移先が 1 つも無い
    - 自分自身へ戻るだけ
    - 同じ URL の別 page_id（解析上の重複画面）へ移るだけ
    """
    tail = [str(x) for x in list(steps)[1:] if str(x)]
    if not tail:
        return True
    here = str((screens.get(page_id) or {}).get("url") or "")
    for nxt in tail:
        if nxt == page_id:
            continue
        url = str((screens.get(nxt) or {}).get("url") or "")
        if not here or not url or url != here:
            return False
    return True

def _transition_rows(
    ctx: _ScreenContext, screens: Mapping[str, Mapping[str, Any]]
) -> list[TestCaseRow]:
    to_ids = [str(x) for x in ((ctx.raw.get("transitions") or {}).get("to") or [])]
    rows: list[TestCaseRow] = []
    for idx, nxt in enumerate(to_ids, start=1):
        target = screens.get(nxt) or {}
        target_title = _screen_title(target)
        target_url = str(target.get("url") or "")
        steps = [
            ctx.open_step(),
            Step(
                f"「{target_title}」へ進むリンクまたはボタンをクリックする",
                {"type": "click_link_to", "url": target_url, "title": target_title},
            ),
        ]
        texts, actions = _split_steps(steps)
        rows.append(
            TestCaseRow(
                case_id=f"TC-{ctx.page_id}-TRN-{idx:03d}",
                name=f"{ctx.title} から {target_title} へ遷移できる",
                screen=ctx.label,
                function="画面遷移",
                viewpoint="画面遷移／リンク導線",
                preconditions=ctx.preconditions(),
                steps=texts,
                expected=(
                    f"URL が {target_url or nxt} に変わる",
                    f"{nxt}（{target_title}）の内容が表示される",
                    "ブラウザの戻るボタンで元の画面に戻れる",
                ),
                automation=AUTOMATION_AUTO,
                automation_reason="遷移先 URL の一致で判定できるため",
                trace_id=f"{ctx.page_id}->{nxt}",
                actions=actions,
                assertions=(({"type": "expect_url", "value": target_url},) if target_url else ()),
            )
        )
    return rows
