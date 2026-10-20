"""宣言ルールのカタログ（旧 axe id ↔ ACT ↔ WCAG SC ↔ 実装区分）。

ACT ID は W3C ACT rules 一覧で確認できたものだけを記載し、確認できないものは空にする
（創作しない）。未実装ルールは implementation=none とし、結果では常に NOT_IMPLEMENTED。
品質ゲートの母集団は declared（implementation != none）。
"""

from __future__ import annotations

from .models import Implementation as I
from .models import Level, RuleSpec

F, P, N = I.FULL, I.PARTIAL, I.NONE
A, AA, BP = Level.A, Level.AA, Level.BEST_PRACTICE


def _r(rule_id, legacy, act, sc, level, impl, cat, desc, sev="moderate", reason=""):
    return RuleSpec(rule_id, tuple(legacy), tuple(act), tuple(sc), level, impl, cat, desc, sev, reason)


_ARIA_NAME_IDS = (
    "aria-command-name", "aria-input-field-name", "aria-toggle-field-name",
    "aria-tooltip-name", "aria-tab-name", "aria-meter-name", "aria-progressbar-name",
)

_MANUAL = "機械で決定できない（人の確認が必要）。manual_review_required のまま扱う"


def _manual(rule_id, sc, level, desc):
    return _r(rule_id, (), (), (sc,), level, N, "manual", desc, "moderate", _MANUAL)


def _unported(axe_id, sc, level, cat, desc, sev="moderate"):
    return _r(f"todo.{axe_id}", (axe_id,), (), sc, level, N, cat, desc, sev,
              "現行の WebSpec2Doc は未対応（今後のバージョンで検討）")


_RULES: tuple[RuleSpec, ...] = (
    # A. 名前系（W2）
    _r("name.image", ("image-alt", "role-img-alt", "area-alt"), ("23a2a8",), ("1.1.1",), A, F, "name",
       "画像に代替テキスト（アクセシブル名）がある", "critical"),
    _r("name.input-image", ("input-image-alt",), (), ("1.1.1", "4.1.2"), A, F, "name",
       "input[type=image] に代替テキストがある", "critical"),
    _r("name.form-field", ("label",), ("e086e5",), ("4.1.2",), A, F, "name",
       "フォーム入力欄にラベル（アクセシブル名）がある", "critical"),
    _r("name.select", ("select-name",), ("e086e5",), ("4.1.2",), A, F, "name",
       "select 要素にアクセシブル名がある", "critical"),
    _r("name.button", ("button-name", "input-button-name"), ("97a4e1",), ("4.1.2",), A, F, "name",
       "ボタンにアクセシブル名がある", "critical"),
    _r("name.link", ("link-name",), ("c487ae",), ("2.4.4", "4.1.2"), A, F, "name",
       "リンクにアクセシブル名がある", "serious"),
    _r("name.frame", ("frame-title",), ("cae760",), ("4.1.2",), A, F, "name",
       "iframe/frame にタイトル（アクセシブル名）がある", "serious"),
    _r("name.aria-role-required", _ARIA_NAME_IDS, (), ("4.1.2",), A, F, "name",
       "名前が必須の ARIA ロールにアクセシブル名がある", "serious"),
    _r("name.heading", ("empty-heading",), ("ffd0e9",), (), BP, F, "name",
       "見出しが空でない", "minor"),
    # B. 文書/メタ系（W3）
    _r("doc.title", ("document-title",), ("2779a5",), ("2.4.2",), A, F, "document",
       "文書に空でない title がある", "serious"),
    _r("doc.lang-present", ("html-has-lang",), (), ("3.1.1",), A, F, "document",
       "html 要素に lang 属性がある", "serious"),
    _r("doc.lang-valid", ("html-lang-valid",), ("bf051a",), ("3.1.1",), A, P, "document",
       "html の lang が有効な言語タグである（登録簿スナップショットで検証）", "serious"),
    _r("doc.viewport-zoom", ("meta-viewport",), ("b4f0c3",), ("1.4.4",), AA, F, "document",
       "meta viewport が拡大縮小を禁止していない", "critical"),
    _r("doc.bypass", ("bypass",), ("cf77f2",), ("2.4.1",), A, P, "document",
       "ブロックスキップ手段（スキップリンク/ランドマーク/見出し）がある。有効性は人の確認", "serious"),
    _r("doc.duplicate-id-aria", ("duplicate-id-aria",), (), ("4.1.2",), A, F, "document",
       "ARIA から参照される id が重複していない", "critical"),
    _r("struct.list", ("list",), (), ("1.3.1",), A, F, "structure",
       "ul/ol の直下が li（許容要素）のみである", "serious"),
    _r("struct.listitem", ("listitem",), (), ("1.3.1",), A, F, "structure",
       "li が ul/ol の子である", "serious"),
    _r("form.autocomplete", ("autocomplete-valid",), ("73f2c2",), ("1.3.5",), AA, F, "form",
       "autocomplete の値が WHATWG の語彙に適合する", "serious"),
    # C. ARIA 妥当性系（W4）
    _r("aria.roles", ("aria-roles",), ("674b10",), ("4.1.2",), A, F, "aria",
       "role 値が WAI-ARIA で定義されている", "critical"),
    _r("aria.valid-attr", ("aria-valid-attr",), ("5f99a7",), ("4.1.2",), A, F, "aria",
       "aria-* 属性名が定義内である", "critical"),
    _r("aria.valid-attr-value", ("aria-valid-attr-value",), (), ("4.1.2",), A, F, "aria",
       "aria-* 属性値が型に適合する", "critical"),
    _r("aria.required-attr", ("aria-required-attr",), (), ("4.1.2",), A, F, "aria",
       "ロールの必須 ARIA 属性が揃っている", "critical"),
    _r("aria.allowed-attr", ("aria-allowed-attr",), (), ("4.1.2",), A, F, "aria",
       "ロールで許可された ARIA 属性のみ使っている", "critical"),
    _r("aria.prohibited-attr", ("aria-prohibited-attr",), (), ("4.1.2",), A, F, "aria",
       "ロールで禁止された ARIA 属性を使っていない", "serious"),
    _r("aria.required-children", ("aria-required-children",), (), ("1.3.1",), A, P, "aria",
       "ロールの必須の子ロールがある（aria-owns・動的追加は判定不能）", "critical"),
    _r("aria.required-parent", ("aria-required-parent",), (), ("1.3.1",), A, P, "aria",
       "ロールの必須の親ロールがある（aria-owns・動的追加は判定不能）", "critical"),
    _r("aria.hidden-body", ("aria-hidden-body",), (), ("1.3.1", "4.1.2"), A, F, "aria",
       "body に aria-hidden=true が付いていない", "critical"),
    _r("aria.hidden-focus", ("aria-hidden-focus",), (), ("1.3.1", "4.1.2"), A, F, "aria",
       "aria-hidden 配下にフォーカス可能要素がない", "serious"),
    _r("aria.nested-interactive", ("nested-interactive",), (), ("4.1.2",), A, F, "aria",
       "子が presentational のロール内にフォーカス可能要素がない", "serious"),
    # D. 視覚・操作系（W5）
    _r("visual.contrast", ("color-contrast",), ("afw4f7",), ("1.4.3",), AA, P, "visual",
       "テキストのコントラスト比が基準（通常 4.5:1／大文字 3:1）以上。背景画像等は判定不能", "serious"),
    _r("visual.target-size", ("target-size",), (), ("2.5.8",), AA, P, "visual",
       "操作対象が 24x24 CSS px 以上（例外は判定不能になり得る）", "serious"),
    _r("op.scroll-focusable", ("scrollable-region-focusable",), (), ("2.1.1", "2.1.3"), A, F, "operable",
       "スクロール領域がキーボードで到達できる", "moderate"),
    # E. 構造系 best-practice（W3 後半）。WCAG A/AA ではないため wcag_sc は空
    _r("bp.landmark", ("landmark-banner-is-top-level", "landmark-contentinfo-is-top-level",
                       "landmark-main-is-top-level", "landmark-no-duplicate-banner",
                       "landmark-no-duplicate-contentinfo", "landmark-no-duplicate-main",
                       "landmark-one-main", "landmark-unique", "landmark-complementary-is-top-level"),
       (), (), BP, F, "best_practice", "ランドマークが一意かつ適切な位置にある", "moderate"),
    _r("bp.region", ("region",), (), (), BP, F, "best_practice",
       "ページ内容がランドマークに含まれる", "moderate"),
    _r("bp.heading-order", ("heading-order",), (), (), BP, F, "best_practice",
       "見出しレベルが飛ばずに増える", "moderate"),
    _r("bp.page-has-heading-one", ("page-has-heading-one",), (), (), BP, F, "best_practice",
       "ページに h1 がある", "moderate"),
    _r("bp.tabindex", ("tabindex",), (), (), BP, F, "best_practice",
       "tabindex が 0 より大きくない", "serious"),
    # 未移植の axe ルール（比較時に「axe のみ検出」＝見逃しの分母に数える）
    _unported("svg-img-alt", ("1.1.1",), A, "name", "svg[role=img] に代替テキストがある", "serious"),
    _unported("object-alt", ("1.1.1",), A, "name", "object 要素に代替テキストがある", "serious"),
    _unported("video-caption", ("1.2.2",), A, "media", "video にキャプションがある", "critical"),
    _unported("audio-caption", ("1.2.1",), A, "media", "audio に代替手段がある", "critical"),
    _unported("no-autoplay-audio", ("1.4.2",), A, "media", "自動再生音声が 3 秒を超えない", "moderate"),
    _unported("meta-refresh", ("2.2.1", "2.2.4", "3.2.5"), A, "document", "meta refresh を使わない", "critical"),
    _unported("blink", ("2.2.2",), A, "document", "blink 要素を使わない", "serious"),
    _unported("marquee", ("2.2.2",), A, "document", "marquee 要素を使わない", "serious"),
    _unported("valid-lang", ("3.1.2",), AA, "document", "部分的な lang 属性が有効である", "serious"),
    _unported("server-side-image-map", ("2.1.1",), A, "operable", "サーバ側イメージマップを使わない", "minor"),
    _unported("td-headers-attr", ("1.3.1",), A, "table", "td の headers が同表内のセルを指す", "serious"),
    _unported("th-has-data-cells", ("1.3.1",), A, "table", "th にデータセルがある", "serious"),
    _unported("scope-attr-valid", (), BP, "table", "scope 属性が正しく使われている", "moderate"),
    _unported("definition-list", ("1.3.1",), A, "structure", "dl の構造が正しい", "serious"),
    _unported("dlitem", ("1.3.1",), A, "structure", "dt/dd が dl の子である", "serious"),
    _unported("frame-focusable-content", ("2.1.1",), A, "operable", "フォーカス可能な子を持つ frame が到達可能", "serious"),
    _unported("link-in-text-block", ("1.4.1",), A, "visual", "本文中のリンクが色以外で区別できる", "serious"),
    _unported("label-content-name-mismatch", ("2.5.3",), A, "name", "可視ラベルがアクセシブル名に含まれる", "serious"),
    _unported("aria-dialog-name", ("4.1.2",), A, "name", "dialog/alertdialog に名前がある", "serious"),
    _unported("aria-treeitem-name", ("4.1.2",), A, "name", "treeitem に名前がある", "serious"),
    _unported("aria-allowed-role", (), BP, "aria", "要素に許可された role のみ使う", "minor"),
    _unported("presentation-role-conflict", (), BP, "aria", "presentation role がグローバル属性と衝突しない", "minor"),
    _unported("identical-links-same-purpose", ("2.4.9",), Level.AA, "name", "同名リンクの目的が同じ", "minor"),
    _unported("accesskeys", (), BP, "operable", "accesskey 値が一意である", "serious"),
    _unported("skip-link", (), BP, "document", "スキップリンクの遷移先が存在する", "moderate"),
    # F. 判定不可（常に not_implemented）
    _manual("manual.sc-1-2", "1.2.1", A, "メディアの代替（1.2.x）"),
    _manual("manual.sc-1-4-1", "1.4.1", A, "色のみに依存しない"),
    _manual("manual.sc-1-4-5", "1.4.5", AA, "画像化された文字"),
    _manual("manual.sc-1-4-10", "1.4.10", AA, "リフロー"),
    _manual("manual.sc-1-4-11", "1.4.11", AA, "非テキストのコントラスト"),
    _manual("manual.sc-1-4-12", "1.4.12", AA, "テキストの間隔"),
    _manual("manual.sc-2-1-1", "2.1.1", A, "キーボードで全機能を操作できる"),
    _manual("manual.sc-2-4-3", "2.4.3", A, "フォーカス順序"),
    _manual("manual.sc-2-4-7", "2.4.7", AA, "フォーカスの可視化"),
    _manual("manual.sc-3-2", "3.2.1", A, "予測可能性（3.2.x）"),
    _manual("manual.sc-3-3", "3.3.1", A, "入力支援（3.3.x）"),
    _manual("manual.sc-3-3-7", "3.3.7", A, "冗長な入力"),
    _manual("manual.sc-3-3-8", "3.3.8", AA, "アクセシブルな認証"),
)

CATALOG: tuple[RuleSpec, ...] = _RULES
CATALOG_BY_ID: dict[str, RuleSpec] = {r.rule_id: r for r in CATALOG}
LEGACY_TO_NATIVE: dict[str, str] = {a: r.rule_id for r in CATALOG for a in r.legacy_axe_ids}


def validate_catalog(catalog: tuple[RuleSpec, ...] = CATALOG) -> list[str]:
    """不整合を文字列で返す（空なら正常）。AC-W0-1 の機械判定。"""
    problems: list[str] = []
    seen_ids: set[str] = set()
    seen_legacy: dict[str, str] = {}
    for r in catalog:
        if r.rule_id in seen_ids:
            problems.append(f"rule_id 重複: {r.rule_id}")
        seen_ids.add(r.rule_id)
        for a in r.legacy_axe_ids:
            if a in seen_legacy:
                problems.append(f"legacy_axe_id 重複: {a} ({seen_legacy[a]}, {r.rule_id})")
            seen_legacy[a] = r.rule_id
        if r.implementation is I.NONE and not r.reason_if_unimplemented:
            problems.append(f"未実装なのに理由が空: {r.rule_id}")
        if r.wcag_level is BP and r.wcag_sc:
            problems.append(f"best_practice に wcag_sc: {r.rule_id}")
    return problems


def declared_rules() -> tuple[RuleSpec, ...]:
    """対応を宣言するルール（implementation が full/partial）。品質ゲートの母集団。"""
    return tuple(r for r in CATALOG if r.declared)


def critical_aa_rules() -> tuple[RuleSpec, ...]:
    """宣言ルールのうち重大な A/AA。fixture Recall=1.00 の対象。"""
    return tuple(r for r in CATALOG if r.declared and r.critical_aa)


def coverage() -> dict[str, int]:
    """meta.coverage 用の集計。"""
    return {
        "implemented": sum(1 for r in CATALOG if r.implementation is F),
        "partial": sum(1 for r in CATALOG if r.implementation is P),
        "not_implemented": sum(1 for r in CATALOG if r.implementation is N),
    }
