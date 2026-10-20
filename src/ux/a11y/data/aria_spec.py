"""WAI-ARIA 1.2 のロール・属性データ（公開仕様から自社で書き起こした表）。

方針: 偽陽性を避けるため、許可属性は仕様の記述より広めに取る。
非推奨のグローバル属性（aria-disabled / errormessage / haspopup / invalid /
grabbed / dropeffect）は全ロールで許可する。
"""
from __future__ import annotations

ARIA12_ROLES = frozenset("""
alert alertdialog application article banner blockquote button caption cell checkbox
code columnheader combobox complementary contentinfo definition deletion dialog
directory document emphasis feed figure form generic grid gridcell group heading img
insertion link list listbox listitem log main marquee math meter menu menubar menuitem
menuitemcheckbox menuitemradio navigation none note option paragraph presentation
progressbar radio radiogroup region row rowgroup rowheader scrollbar search searchbox
separator slider spinbutton status strong subscript superscript switch tab table
tablist tabpanel term textbox time timer toolbar tooltip tree treegrid treeitem
""".split())

# DPUB-ARIA 1.1 / Graphics-ARIA 1.0（有効なロールとして扱う）
DPUB_ROLES = frozenset("""
doc-abstract doc-acknowledgments doc-afterword doc-appendix doc-backlink doc-biblioentry
doc-bibliography doc-biblioref doc-chapter doc-colophon doc-conclusion doc-cover
doc-credit doc-credits doc-dedication doc-endnote doc-endnotes doc-epigraph doc-epilogue
doc-errata doc-example doc-footnote doc-foreword doc-glossary doc-glossref doc-index
doc-introduction doc-noteref doc-notice doc-pagebreak doc-pagelist doc-part doc-preface
doc-prologue doc-pullquote doc-qna doc-subtitle doc-tip doc-toc
graphics-document graphics-object graphics-symbol
""".split())

ABSTRACT_ROLES = frozenset("""
command composite input landmark range roletype section sectionhead select structure
widget window
""".split())

VALID_ROLES = ARIA12_ROLES | DPUB_ROLES

# 属性の型: bool / tristate / token / tokens / idref / idrefs / int / number / string
# int は (型, 下限)、token(s) は (型, 許可値の集合)。
_BOOL = ("bool", None)
_TRI = ("tristate", None)
_STR = ("string", None)
ATTR_TYPES: dict[str, tuple] = {
    "aria-activedescendant": ("idref", None),
    "aria-atomic": _BOOL,
    "aria-autocomplete": ("token", frozenset({"inline", "list", "both", "none"})),
    "aria-braillelabel": _STR,
    "aria-brailleroledescription": _STR,
    "aria-busy": _BOOL,
    "aria-checked": _TRI,
    "aria-colcount": ("int", -1),
    "aria-colindex": ("int", 1),
    "aria-colspan": ("int", 1),
    "aria-controls": ("idrefs", None),
    "aria-current": ("token", frozenset({"page", "step", "location", "date", "time", "true", "false"})),
    "aria-describedby": ("idrefs", None),
    "aria-description": _STR,
    "aria-details": ("idrefs", None),
    "aria-disabled": _BOOL,
    "aria-dropeffect": ("tokens", frozenset({"copy", "execute", "link", "move", "none", "popup"})),
    "aria-errormessage": ("idrefs", None),
    "aria-expanded": ("bool_undef", None),
    "aria-flowto": ("idrefs", None),
    "aria-grabbed": ("bool_undef", None),
    "aria-haspopup": ("token", frozenset({"false", "true", "menu", "listbox", "tree", "grid", "dialog"})),
    "aria-hidden": ("bool_undef", None),
    "aria-invalid": ("token", frozenset({"grammar", "false", "spelling", "true"})),
    "aria-keyshortcuts": _STR,
    "aria-label": _STR,
    "aria-labelledby": ("idrefs", None),
    "aria-level": ("int", 1),
    "aria-live": ("token", frozenset({"assertive", "off", "polite"})),
    "aria-modal": _BOOL,
    "aria-multiline": _BOOL,
    "aria-multiselectable": _BOOL,
    "aria-orientation": ("token", frozenset({"horizontal", "undefined", "vertical"})),
    "aria-owns": ("idrefs", None),
    "aria-placeholder": _STR,
    "aria-posinset": ("int", 1),
    "aria-pressed": _TRI,
    "aria-readonly": _BOOL,
    "aria-relevant": ("tokens", frozenset({"additions", "all", "removals", "text"})),
    "aria-required": _BOOL,
    "aria-roledescription": _STR,
    "aria-rowcount": ("int", -1),
    "aria-rowindex": ("int", 1),
    "aria-rowspan": ("int", 0),
    "aria-selected": ("bool_undef", None),
    "aria-setsize": ("int", -1),
    "aria-sort": ("token", frozenset({"ascending", "descending", "none", "other"})),
    "aria-valuemax": ("number", None),
    "aria-valuemin": ("number", None),
    "aria-valuenow": ("number", None),
    "aria-valuetext": _STR,
}

# 全ロールで許可する属性（1.2 のグローバル＋非推奨グローバル＋1.3 の点字属性）
GLOBAL_ATTRS = frozenset({
    "aria-atomic", "aria-braillelabel", "aria-brailleroledescription", "aria-busy",
    "aria-controls", "aria-current", "aria-describedby", "aria-description",
    "aria-details", "aria-disabled", "aria-dropeffect", "aria-errormessage",
    "aria-flowto", "aria-grabbed", "aria-haspopup", "aria-hidden", "aria-invalid",
    "aria-keyshortcuts", "aria-label", "aria-labelledby", "aria-live", "aria-owns",
    "aria-relevant", "aria-roledescription",
})

_RANGE = {"aria-valuemax", "aria-valuemin", "aria-valuenow", "aria-valuetext"}
_CELL = {"aria-colindex", "aria-colspan", "aria-rowindex", "aria-rowspan"}
_GRIDCELL = _CELL | {"aria-readonly", "aria-required", "aria-selected", "aria-expanded"}
_TEXTBOX = {"aria-activedescendant", "aria-autocomplete", "aria-multiline",
            "aria-placeholder", "aria-readonly", "aria-required"}
_COMPOSITE = {"aria-activedescendant", "aria-expanded", "aria-orientation"}
_SELECT = _COMPOSITE | {"aria-required", "aria-readonly", "aria-multiselectable"}
_ITEM = {"aria-posinset", "aria-setsize", "aria-expanded", "aria-selected"}

# ロール固有の追加サポート属性（グローバルは含まない）
ROLE_SUPPORTED: dict[str, frozenset] = {k: frozenset(v) for k, v in {
    "alert": set(), "alertdialog": {"aria-modal"}, "application": {"aria-activedescendant", "aria-expanded"},
    "article": {"aria-posinset", "aria-setsize"},
    "banner": set(), "blockquote": set(), "button": {"aria-expanded", "aria-pressed"},
    "caption": set(), "cell": _CELL | {"aria-selected"},
    "checkbox": {"aria-checked", "aria-readonly", "aria-required", "aria-expanded"},
    "code": set(),
    "columnheader": _GRIDCELL | {"aria-sort"},
    "combobox": _TEXTBOX | _COMPOSITE | {"aria-controls"},
    "complementary": set(), "contentinfo": set(), "definition": set(), "deletion": set(),
    "dialog": {"aria-modal"}, "directory": set(), "document": {"aria-expanded"},
    "emphasis": set(), "feed": set(), "figure": set(), "form": set(), "generic": set(),
    "grid": _SELECT | {"aria-colcount", "aria-rowcount", "aria-level"},
    "gridcell": _GRIDCELL,
    "group": {"aria-activedescendant", "aria-expanded"},
    "heading": {"aria-level", "aria-expanded"}, "img": set(), "insertion": set(),
    "link": {"aria-expanded"},
    "list": set(), "listbox": _SELECT | {"aria-invalid"},
    "listitem": {"aria-level", "aria-posinset", "aria-setsize"},
    "log": set(), "main": set(), "marquee": set(), "math": set(),
    "meter": _RANGE, "menu": _COMPOSITE, "menubar": _COMPOSITE,
    "menuitem": {"aria-posinset", "aria-setsize", "aria-expanded"},
    "menuitemcheckbox": {"aria-checked", "aria-posinset", "aria-setsize", "aria-expanded"},
    "menuitemradio": {"aria-checked", "aria-posinset", "aria-setsize", "aria-expanded"},
    "navigation": set(), "none": set(), "note": set(),
    "option": {"aria-checked", "aria-posinset", "aria-selected", "aria-setsize"},
    "paragraph": set(), "presentation": set(),
    "progressbar": _RANGE, "radio": {"aria-checked", "aria-posinset", "aria-setsize"},
    "radiogroup": {"aria-readonly", "aria-required", "aria-activedescendant", "aria-orientation", "aria-expanded"},
    "region": set(),
    "row": {"aria-colindex", "aria-expanded", "aria-level", "aria-posinset", "aria-rowindex",
            "aria-selected", "aria-setsize", "aria-activedescendant"},
    "rowgroup": set(),
    "rowheader": _GRIDCELL | {"aria-sort"},
    "scrollbar": _RANGE | {"aria-controls", "aria-orientation"},
    "search": set(), "searchbox": _TEXTBOX,
    "separator": _RANGE | {"aria-orientation"},
    "slider": _RANGE | {"aria-orientation", "aria-readonly"},
    "spinbutton": _RANGE | {"aria-activedescendant", "aria-readonly", "aria-required"},
    "status": set(), "strong": set(), "subscript": set(), "superscript": set(),
    "switch": {"aria-checked", "aria-readonly", "aria-required"},
    "tab": {"aria-selected", "aria-expanded", "aria-posinset", "aria-setsize"},
    "table": {"aria-colcount", "aria-rowcount"},
    "tablist": _COMPOSITE | {"aria-level", "aria-multiselectable"},
    "tabpanel": set(), "term": set(), "textbox": _TEXTBOX, "time": set(), "timer": set(),
    "toolbar": _COMPOSITE,
    "tooltip": set(),
    "tree": _SELECT,
    "treegrid": _SELECT | {"aria-colcount", "aria-rowcount", "aria-level"},
    "treeitem": _ITEM | {"aria-checked", "aria-level"},
}.items()}

# 必須属性（1.2）。対象は明示 role のみ（ネイティブ要素の暗黙状態は別処理）。
ROLE_REQUIRED: dict[str, tuple[str, ...]] = {
    "checkbox": ("aria-checked",),
    "combobox": ("aria-expanded",),  # aria-controls は展開時のみ（rules_aria で処理）
    "heading": ("aria-level",),
    "menuitemcheckbox": ("aria-checked",),
    "menuitemradio": ("aria-checked",),
    "meter": ("aria-valuenow",),
    "radio": ("aria-checked",),
    "scrollbar": ("aria-controls", "aria-valuenow"),
    "slider": ("aria-valuenow",),
    "switch": ("aria-checked",),
}

# アクセシブル名の付与が禁止されるロール（1.2: name prohibited）
NAME_PROHIBITED_ROLES = frozenset({
    "caption", "code", "deletion", "emphasis", "generic", "insertion", "paragraph",
    "presentation", "none", "strong", "subscript", "superscript",
})

# 必須の子（所有）ロール。いずれか 1 つが所有されていればよい。
REQUIRED_CHILDREN: dict[str, tuple[str, ...]] = {
    "grid": ("row", "rowgroup"),
    "list": ("listitem",),
    "listbox": ("option",),
    "menu": ("menuitem", "menuitemcheckbox", "menuitemradio"),
    "menubar": ("menuitem", "menuitemcheckbox", "menuitemradio"),
    "row": ("cell", "columnheader", "gridcell", "rowheader"),
    "rowgroup": ("row",),
    "table": ("row", "rowgroup"),
    "tablist": ("tab",),
    "tree": ("treeitem",),
    "treegrid": ("row", "rowgroup"),
}
# 子ロールの途中に挟んでよい中間ロール
ALLOWED_INTERMEDIATE: dict[str, tuple[str, ...]] = {
    "grid": ("rowgroup",), "table": ("rowgroup",), "treegrid": ("rowgroup",),
    "listbox": ("group",), "menu": ("group",), "menubar": ("group",), "tree": ("group",),
}
# 空（子なし）のとき動的生成の可能性があるため判定不能にするロール
REVIEW_EMPTY = frozenset({
    "doc-bibliography", "doc-endnotes", "grid", "list", "listbox", "menu", "menubar",
    "table", "tablist", "tree", "treegrid", "rowgroup",
})

# 必須の親（コンテキスト）ロール
REQUIRED_PARENT: dict[str, tuple[str, ...]] = {
    "caption": ("figure", "grid", "table", "treegrid"),
    "cell": ("row",),
    "columnheader": ("row",),
    "gridcell": ("row",),
    "listitem": ("list", "directory"),
    "menuitem": ("menu", "menubar"),
    "menuitemcheckbox": ("menu", "menubar"),
    "menuitemradio": ("menu", "menubar"),
    "option": ("listbox",),
    "row": ("grid", "rowgroup", "table", "treegrid"),
    "rowgroup": ("grid", "table", "treegrid"),
    "rowheader": ("row",),
    "tab": ("tablist",),
    "treeitem": ("tree", "treegrid"),
}
# 親探索で透過してよい中間ロール
PARENT_INTERMEDIATE: dict[str, tuple[str, ...]] = {
    "menuitem": ("group",), "menuitemcheckbox": ("group",), "menuitemradio": ("group",),
    "option": ("group",), "treeitem": ("group",), "listitem": ("group",),
}

# 子孫が presentational になるロール（フォーカス可能な子孫を持てない）
CHILDREN_PRESENTATIONAL = frozenset({
    "button", "checkbox", "img", "menuitemcheckbox", "menuitemradio", "meter", "option",
    "progressbar", "radio", "scrollbar", "separator", "slider", "switch", "tab",
})

NEUTRAL_ROLES = frozenset({"generic", "none", "presentation"})
