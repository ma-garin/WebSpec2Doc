"""AutoRun の段階承認パイプライン。

仕様7〜13に対応する7段階。各段階は**提示 → 承認**で進み、項目単位で
修正できる。生成はルールベース（実測データから確定的に作る）を基本とし、
LLM は補助（言い回しの具体化・追加候補の提案）に限る。

    7  test_objective  テスト目的の提示・承認
    8  test_plan       テスト計画の提示・承認（同一URLの2回目以降はSKIP可）
    9  features        テストフィーチャー分析（全項目の承認が必要）
    10 viewpoints      テスト観点分析
    11 basic_design    テスト基本設計（テスト技法）
    12 detail_design   テスト詳細設計（ハイレベルテストケース）
    13 test_cases      テストケース（ローレベル / QualityForward カラム）

**設計方針**
- 不変データ。更新は必ず新しいオブジェクトを返す。
- 観測できない事項は「前提」として明示し、実行は止めない。
- 「未検証」と「問題なし」を混同しない。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from typing import Any, Final

from autorun.qf_schema import CASE_TYPE_ABNORMAL, CASE_TYPE_NORMAL, TestCaseRow, renumber

# ---------------------------------------------------------------- 段階の定義

STAGE_TEST_OBJECTIVE: Final = "test_objective"
STAGE_TEST_PLAN: Final = "test_plan"
STAGE_FEATURES: Final = "features"
STAGE_VIEWPOINTS: Final = "viewpoints"
STAGE_BASIC_DESIGN: Final = "basic_design"
STAGE_DETAIL_DESIGN: Final = "detail_design"
STAGE_TEST_CASES: Final = "test_cases"

STATUS_PENDING: Final = "pending"
STATUS_GENERATED: Final = "generated"
STATUS_APPROVED: Final = "approved"
STATUS_SKIPPED: Final = "skipped"


@dataclass(frozen=True)
class StageDefinition:
    stage_id: str
    step_no: int
    name: str
    purpose: str
    #: 全項目の個別承認を要求するか（仕様9「全てのフィーチャが承認されないとNG」）
    requires_item_approval: bool = False
    #: 同一URLの2回目以降にスキップできるか（仕様8）
    skippable_on_rerun: bool = False


STAGE_DEFINITIONS: Final[tuple[StageDefinition, ...]] = (
    StageDefinition(
        STAGE_TEST_OBJECTIVE,
        7,
        "テスト目的",
        "この対象に対して、どのような目的・方針でテストするのかを定める（ISTQB のテスト目的）。",
    ),
    StageDefinition(
        STAGE_TEST_PLAN,
        8,
        "テスト計画",
        "テスト目的に対して、この後の進め方・範囲・前提を定める。",
        skippable_on_rerun=True,
    ),
    StageDefinition(
        STAGE_FEATURES,
        9,
        "テストフィーチャー分析",
        "実測した画面から、テスト対象のフィーチャー（機能のまとまり）を切り出す。",
        requires_item_approval=True,
    ),
    StageDefinition(
        STAGE_VIEWPOINTS,
        10,
        "テスト観点分析",
        "フィーチャーごとにテスト観点を洗い出す（既存の観点セット＋実測からの補完）。",
    ),
    StageDefinition(
        STAGE_BASIC_DESIGN,
        11,
        "テスト基本設計",
        "観点に対して適用するテスト技法を決める（同値分割・境界値・デシジョンテーブル・状態遷移・組合せ）。",
    ),
    StageDefinition(
        STAGE_DETAIL_DESIGN,
        12,
        "テスト詳細設計",
        "ハイレベルテストケース（何を確かめるか）を全量作る。",
    ),
    StageDefinition(
        STAGE_TEST_CASES,
        13,
        "テストケース",
        "ローレベルテストケース（手順・データ・期待結果）を全量作る。QualityForward のカラム構成。",
    ),
)

STAGE_BY_ID: Final[dict[str, StageDefinition]] = {d.stage_id: d for d in STAGE_DEFINITIONS}
STAGE_ORDER: Final[tuple[str, ...]] = tuple(d.stage_id for d in STAGE_DEFINITIONS)


# ---------------------------------------------------------------- データ構造


@dataclass(frozen=True)
class StageItem:
    """段階内の1項目。個別に承認・修正できる。"""

    item_id: str
    title: str
    detail: str = ""
    #: 生成元。rule=実測からの確定生成 / llm=LLM提案 / user=人手
    source: str = "rule"
    approved: bool = False
    #: 観測で決められず前提を置いた項目は True（正直な明示）
    assumed: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def with_approval(self, approved: bool) -> StageItem:
        return replace(self, approved=approved)

    def edited(self, title: str | None = None, detail: str | None = None) -> StageItem:
        return replace(
            self,
            title=self.title if title is None else title,
            detail=self.detail if detail is None else detail,
            source="user",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "detail": self.detail,
            "source": self.source,
            "approved": self.approved,
            "assumed": self.assumed,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class Stage:
    stage_id: str
    status: str = STATUS_PENDING
    items: tuple[StageItem, ...] = ()
    note: str = ""

    @property
    def definition(self) -> StageDefinition:
        return STAGE_BY_ID[self.stage_id]

    @property
    def can_approve(self) -> bool:
        """承認できる状態か。項目承認が必要な段階では全項目の承認を要求する。"""
        if self.status == STATUS_PENDING:
            return False
        if self.definition.requires_item_approval:
            return bool(self.items) and all(item.approved for item in self.items)
        return True

    def with_items(self, items: tuple[StageItem, ...], note: str = "") -> Stage:
        return replace(self, items=items, status=STATUS_GENERATED, note=note or self.note)

    def with_status(self, status: str) -> Stage:
        return replace(self, status=status)

    def with_item(self, item: StageItem) -> Stage:
        items = tuple(item if existing.item_id == item.item_id else existing for existing in self.items)
        return replace(self, items=items)

    def to_dict(self) -> dict[str, Any]:
        d = self.definition
        return {
            "stage_id": self.stage_id,
            "step_no": d.step_no,
            "name": d.name,
            "purpose": d.purpose,
            "status": self.status,
            "requires_item_approval": d.requires_item_approval,
            "skippable_on_rerun": d.skippable_on_rerun,
            "can_approve": self.can_approve,
            "note": self.note,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class Pipeline:
    """7段階の状態。"""

    stages: tuple[Stage, ...]
    is_rerun: bool = False

    @classmethod
    def initial(cls, is_rerun: bool = False) -> Pipeline:
        return cls(stages=tuple(Stage(stage_id=sid) for sid in STAGE_ORDER), is_rerun=is_rerun)

    def get(self, stage_id: str) -> Stage | None:
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def replaced(self, stage: Stage) -> Pipeline:
        stages = tuple(stage if s.stage_id == stage.stage_id else s for s in self.stages)
        return replace(self, stages=stages)

    @property
    def current_stage_id(self) -> str | None:
        """まだ承認（またはスキップ）されていない最初の段階。"""
        for stage in self.stages:
            if stage.status not in (STATUS_APPROVED, STATUS_SKIPPED):
                return stage.stage_id
        return None

    @property
    def all_approved(self) -> bool:
        return all(s.status in (STATUS_APPROVED, STATUS_SKIPPED) for s in self.stages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "current_stage_id": self.current_stage_id,
            "all_approved": self.all_approved,
            "is_rerun": self.is_rerun,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pipeline:
        stages: list[Stage] = []
        by_id = {s.get("stage_id"): s for s in data.get("stages", [])}
        for stage_id in STAGE_ORDER:
            raw = by_id.get(stage_id) or {}
            items = tuple(
                StageItem(
                    item_id=str(i.get("item_id", "")),
                    title=str(i.get("title", "")),
                    detail=str(i.get("detail", "")),
                    source=str(i.get("source", "rule")),
                    approved=bool(i.get("approved", False)),
                    assumed=bool(i.get("assumed", False)),
                    data=dict(i.get("data") or {}),
                )
                for i in raw.get("items", [])
            )
            stages.append(
                Stage(
                    stage_id=stage_id,
                    status=str(raw.get("status", STATUS_PENDING)),
                    items=items,
                    note=str(raw.get("note", "")),
                )
            )
        return cls(stages=tuple(stages), is_rerun=bool(data.get("is_rerun", False)))


# ---------------------------------------------------------------- 観測の読み取り


def form_fields(form: dict[str, Any]) -> list[dict[str, Any]]:
    """フォームの入力項目を返す。

    report.json は `fields` を使う。他の生成物・テストデータでは `inputs`
    と表記される場合があるため、両方を受け付ける。
    """
    raw = form.get("fields")
    if raw is None:
        raw = form.get("inputs")
    return [f for f in (raw or []) if isinstance(f, dict)]


@dataclass(frozen=True)
class Observation:
    """実測レポートから、段階生成に必要な情報だけを抜き出したもの。"""

    url: str = ""
    screens: tuple[dict[str, Any], ...] = ()
    has_previous_snapshot: bool = False
    document_driven: bool = False
    viewpoint_set_name: str = ""

    @property
    def screen_count(self) -> int:
        return len(self.screens)

    @property
    def forms(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """(画面, フォーム) の組を返す。"""
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for screen in self.screens:
            for form in screen.get("forms") or []:
                pairs.append((screen, form))
        return pairs

    @property
    def input_count(self) -> int:
        return sum(len(form_fields(form)) for _, form in self.forms)

    @property
    def required_input_count(self) -> int:
        return sum(
            1
            for _, form in self.forms
            for field_ in form_fields(form)
            if field_.get("required")
        )

    @property
    def transition_count(self) -> int:
        return sum(len((s.get("transitions") or {}).get("to") or []) for s in self.screens)


def observation_from_report(
    report: dict[str, Any] | None,
    *,
    url: str = "",
    has_previous_snapshot: bool = False,
    document_driven: bool = False,
    viewpoint_set_name: str = "",
) -> Observation:
    screens = tuple((report or {}).get("screens") or [])
    return Observation(
        url=url,
        screens=screens,
        has_previous_snapshot=has_previous_snapshot,
        document_driven=document_driven,
        viewpoint_set_name=viewpoint_set_name,
    )


# ---------------------------------------------------------------- 生成（ルールベース）


def _slug(text: str, fallback: str) -> str:
    """ID 用のスラグを返す。

    日本語のように ASCII を含まない文字列は素朴な除去では空になり、
    別々の項目が同じ ID に衝突する。空になる場合は安定ハッシュで補う。
    """
    cleaned = re.sub(r"[^0-9a-zA-Z]+", "-", text).strip("-").lower()
    if cleaned:
        return cleaned
    if not text:
        return fallback
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]  # nosec B324 - ID生成用
    return f"{fallback}-{digest}"


def _screen_label(screen: dict[str, Any]) -> str:
    title = str(screen.get("title") or "").strip()
    if title:
        return title
    return str(screen.get("url") or screen.get("page_id") or "画面")


def _build_test_objective(obs: Observation) -> tuple[tuple[StageItem, ...], str]:
    """ISTQB のテスト目的から、観測に応じて提案する。"""
    items: list[StageItem] = [
        StageItem(
            item_id="obj-defects",
            title="欠陥の摘出",
            detail=(
                f"実測した {obs.screen_count} 画面・{obs.input_count} 入力項目に対して、"
                "故障を誘発して欠陥を見つける。"
            ),
        ),
        StageItem(
            item_id="obj-coverage",
            title="カバレッジの確保",
            detail=(
                f"画面 {obs.screen_count} / 遷移 {obs.transition_count} を網羅基準に沿って通す。"
                "網羅したのは「自動で到達できた範囲」であり、全経路の保証ではない。"
            ),
        ),
    ]

    if obs.required_input_count:
        items.append(
            StageItem(
                item_id="obj-risk",
                title="リスクの低減",
                detail=(
                    f"必須入力 {obs.required_input_count} 項目は誤入力・未入力の影響が大きい。"
                    "入力検証を重点的に確認する。"
                ),
            )
        )
    if obs.document_driven:
        items.append(
            StageItem(
                item_id="obj-requirements",
                title="要件の充足確認",
                detail="提供された要件・仕様文書と実測画面を突合し、要件がテストで押さえられているかを確認する。",
            )
        )
    if obs.has_previous_snapshot:
        items.append(
            StageItem(
                item_id="obj-regression",
                title="変更の確認（回帰）",
                detail="前回スナップショットとの差分を確認し、意図しない変化がないかを見る。",
            )
        )
    else:
        items.append(
            StageItem(
                item_id="obj-baseline",
                title="基準の確立",
                detail=(
                    "前回スナップショットが無いため、今回は比較の基準を作る回とする。"
                    "現新比較は次回以降に成立する。"
                ),
                assumed=True,
            )
        )

    note = "ISTQB のテスト目的から、実測結果に応じて提案しています。不要な目的は外し、必要な目的は追加してください。"
    return tuple(items), note


def _build_test_plan(obs: Observation) -> tuple[tuple[StageItem, ...], str]:
    items: list[StageItem] = [
        StageItem(
            item_id="plan-scope",
            title="スコープ",
            detail=(
                f"対象URL: {obs.url or '(未設定)'}\n"
                f"画面 {obs.screen_count} / フォーム {len(obs.forms)} / "
                f"入力項目 {obs.input_count}（うち必須 {obs.required_input_count}）/ "
                f"遷移 {obs.transition_count}"
            ),
        ),
        StageItem(
            item_id="plan-levels",
            title="テストレベル",
            detail=(
                "システムテスト / 受け入れテスト。"
                "URL からブラックボックスで観測するため、コンポーネント・結合レベルは対象外。"
            ),
        ),
        StageItem(
            item_id="plan-approach",
            title="進め方",
            detail=(
                "フィーチャー分析 → 観点分析 → 基本設計（技法選択）→ 詳細設計（ハイレベル）"
                " → テストケース（ローレベル）→ Playwright 自動化 → 実行・証跡。"
                "各段階で提示し、承認を得てから次へ進む。"
            ),
        ),
        # 観測では決められない事項は「前提」として明示し、止めない
        StageItem(
            item_id="plan-assume-browser",
            title="前提: 対象ブラウザ",
            detail="指定が無いため Chromium（デスクトップ）を前提とする。PC 専用の利用を想定。",
            assumed=True,
        ),
        StageItem(
            item_id="plan-assume-auth",
            title="前提: 認証・権限",
            detail="ロール別の期待結果は指定が無いため、未認証で到達できる範囲を対象とする。",
            assumed=True,
        ),
        StageItem(
            item_id="plan-assume-sideeffect",
            title="前提: 副作用のある操作",
            detail="送信・決済・メール送信など副作用のある操作は行わない。入力の観測にとどめる。",
            assumed=True,
        ),
        StageItem(
            item_id="plan-assume-exit",
            title="前提: 合否基準",
            detail=(
                "リリース判定基準の指定が無いため、重大度による整理を代替として提示する。"
                "最終的な合否判断は人間が行う。"
            ),
            assumed=True,
        ),
        StageItem(
            item_id="plan-claim-scope",
            title="報告の範囲",
            detail=(
                "検出できた範囲のみを証跡付きで報告する。検証できなかった領域は「未検証」と明記し、"
                "欠陥が無いことは証明しない。"
            ),
        ),
    ]
    note = "「前提」は観測では決められない事項です。誤りがあればこの場で修正してください。修正しなくても実行は止まりません。"
    return tuple(items), note


def _feature_key(screen: dict[str, Any]) -> str:
    """URL パスの第1階層でフィーチャーをまとめる。"""
    url = str(screen.get("url") or "")
    match = re.search(r"https?://[^/]+/([^/?#]*)", url)
    segment = match.group(1) if match else ""
    segment = re.sub(r"\.(html?|php|aspx?)$", "", segment)
    return segment or "top"


def _build_features(obs: Observation) -> tuple[tuple[StageItem, ...], str]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for screen in obs.screens:
        groups.setdefault(_feature_key(screen), []).append(screen)

    items: list[StageItem] = []
    for key in sorted(groups):
        screens = groups[key]
        form_count = sum(len(s.get("forms") or []) for s in screens)
        labels = [_screen_label(s) for s in screens[:4]]
        items.append(
            StageItem(
                item_id=f"feat-{_slug(key, 'feature')}",
                title=f"{labels[0] if labels else key}",
                detail=(
                    f"画面 {len(screens)} / フォーム {form_count}\n"
                    f"含まれる画面: {', '.join(labels)}"
                    + (" ほか" if len(screens) > len(labels) else "")
                ),
                data={
                    "feature_key": key,
                    "screen_ids": [str(s.get("page_id") or "") for s in screens],
                    "form_count": form_count,
                },
            )
        )

    note = (
        "実測画面をURL構造でまとめた候補です。"
        "**全てのフィーチャーを承認しないと次へ進めません。** 粒度が違う場合は修正してください。"
    )
    return tuple(items), note


_VIEWPOINT_RULES: Final[tuple[tuple[str, str], ...]] = (
    ("表示・レイアウト", "画面要素が意図どおり表示され、崩れや重なりがないこと。"),
    ("入力検証", "必須・型・桁・範囲などの制約が期待どおり働くこと。"),
    ("画面遷移", "操作に応じて正しい画面へ遷移し、戻る操作も破綻しないこと。"),
    ("データ整合", "画面をまたいで引き回されるデータが保持・反映されること。"),
    ("エラー処理", "異常な入力・操作に対して適切なメッセージが提示されること。"),
    ("アクセシビリティ", "キーボード操作・代替テキストなど、自動検出できる範囲を確認する。"),
)


def _build_viewpoints(obs: Observation, features: Stage | None) -> tuple[tuple[StageItem, ...], str]:
    approved_features = [i for i in (features.items if features else ()) if i.approved]
    targets = approved_features or list(features.items if features else ())

    items: list[StageItem] = []
    for feature in targets:
        form_count = int(feature.data.get("form_count") or 0)
        for name, description in _VIEWPOINT_RULES:
            # 入力のないフィーチャーに入力検証の観点は付けない
            if name in ("入力検証", "エラー処理") and form_count == 0:
                continue
            items.append(
                StageItem(
                    item_id=f"vp-{feature.item_id}-{_slug(name, 'vp')}",
                    title=f"{feature.title} / {name}",
                    detail=description,
                    data={"feature_id": feature.item_id, "viewpoint": name},
                )
            )

    note = (
        f"観点セット: {obs.viewpoint_set_name or '自動選択'} と実測構造から生成しました。"
        "自動で検出できる観点に限られており、これで観点が尽きたわけではありません。"
    )
    return tuple(items), note


_TECHNIQUE_BY_VIEWPOINT: Final[dict[str, tuple[str, str]]] = {
    "入力検証": ("同値分割・境界値分析", "入力項目ごとに有効／無効の同値クラスと境界値を洗い出す。"),
    "エラー処理": ("デシジョンテーブル", "エラー条件の組合せと期待する応答を表で網羅する。"),
    "画面遷移": ("状態遷移テスト", "画面を状態、操作を遷移とみなし、遷移網羅の基準で経路を選ぶ。"),
    "データ整合": ("組合せ（ペアワイズ）", "画面をまたぐ入力の組合せを2因子間で網羅する。"),
    "表示・レイアウト": ("実測比較", "表示要素の観測結果を基準と突き合わせる（初回は基準確立）。"),
    "アクセシビリティ": ("チェックリスト", "自動検出できる達成基準に限って機械的に確認する。"),
}


def _build_basic_design(viewpoints: Stage | None) -> tuple[tuple[StageItem, ...], str]:
    items: list[StageItem] = []
    seen: set[str] = set()
    for vp in viewpoints.items if viewpoints else ():
        name = str(vp.data.get("viewpoint") or "")
        technique, how = _TECHNIQUE_BY_VIEWPOINT.get(name, ("シナリオテスト", "利用シナリオに沿って確認する。"))
        item_id = f"bd-{vp.item_id}"
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append(
            StageItem(
                item_id=item_id,
                title=f"{vp.title} → {technique}",
                detail=how,
                data={
                    "viewpoint_id": vp.item_id,
                    "viewpoint": name,
                    "technique": technique,
                    "feature_id": vp.data.get("feature_id", ""),
                },
            )
        )
    note = "観点ごとに適用する技法を割り当てました。技法が合わない箇所は修正してください。"
    return tuple(items), note


def _build_detail_design(basic: Stage | None) -> tuple[tuple[StageItem, ...], str]:
    items: list[StageItem] = []
    for design in basic.items if basic else ():
        viewpoint = str(design.data.get("viewpoint") or "")
        technique = str(design.data.get("technique") or "")
        base_title = design.title.split(" → ")[0]
        for suffix, case_type, what in (
            ("正常", CASE_TYPE_NORMAL, "有効な条件で期待どおりに振る舞うこと"),
            ("異常", CASE_TYPE_ABNORMAL, "無効・境界の条件で適切に拒否・通知されること"),
        ):
            items.append(
                StageItem(
                    item_id=f"dd-{design.item_id}-{suffix}",
                    title=f"{base_title}（{case_type}）",
                    detail=f"{technique} を用いて、{what}を確認する。",
                    data={
                        "design_id": design.item_id,
                        "viewpoint": viewpoint,
                        "technique": technique,
                        "case_type": case_type,
                        "feature_id": design.data.get("feature_id", ""),
                    },
                )
            )
    note = "ハイレベルテストケース（何を確かめるか）です。次の段階で手順・データまで具体化します。"
    return tuple(items), note


def _entry_screen(obs: Observation, screen_ids: list[str]) -> dict[str, Any] | None:
    """フィーチャーの代表画面（最初に観測された画面）を返す。"""
    if not screen_ids:
        return None
    by_id = {str(s.get("page_id") or ""): s for s in obs.screens}
    for sid in screen_ids:
        screen = by_id.get(str(sid))
        if screen is not None:
            return screen
    return None


def _field_names(screen: dict[str, Any] | None, limit: int = 4) -> list[str]:
    """画面の入力項目名を返す（手順の具体化に使う）。"""
    if not screen:
        return []
    names: list[str] = []
    for form in screen.get("forms") or []:
        for field_ in form_fields(form):
            name = str(field_.get("label") or field_.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
            if len(names) >= limit:
                return names
    return names


def _build_test_cases(
    obs: Observation, detail: Stage | None, features: Stage | None
) -> tuple[tuple[StageItem, ...], str]:
    feature_items = {f.item_id: f for f in (features.items if features else ())}

    rows: list[TestCaseRow] = []
    for hl in detail.items if detail else ():
        viewpoint = str(hl.data.get("viewpoint") or "")
        technique = str(hl.data.get("technique") or "")
        case_type = str(hl.data.get("case_type") or CASE_TYPE_NORMAL)
        feature_id = str(hl.data.get("feature_id") or "")

        feature = feature_items.get(feature_id)
        screen_name = feature.title if feature else ""
        screen_ids = list((feature.data.get("screen_ids") if feature else []) or [])
        entry = _entry_screen(obs, screen_ids)
        url = str((entry or {}).get("url") or "")
        fields = _field_names(entry)

        # 前提条件は「どの画面か」「どうやって開くか」「認証状態」を具体的に書く。
        # 「到達できる状態」のような同義反復は前提条件として機能しない。
        precondition_parts = [
            f"対象URL: {url}" if url else f"対象画面: {screen_name or '(未特定)'}",
            "未認証状態で直接URLを開く（認証ロールの指定が無いため）",
        ]
        precondition = "\n".join(precondition_parts)

        open_step = f"1. {url} を開く" if url else "1. 対象画面を開く"
        if fields:
            listed = "・".join(fields)
            if case_type == CASE_TYPE_NORMAL:
                input_step = f"2. {listed} に有効な値を入力する"
            else:
                input_step = f"2. {listed} のいずれかに無効値または境界値を入力する"
        else:
            input_step = (
                "2. 画面の表示内容を確認する"
                if case_type == CASE_TYPE_NORMAL
                else "2. 想定外の操作（直接URL遷移・連続操作など）を行う"
            )

        if case_type == CASE_TYPE_NORMAL:
            steps = f"{open_step}\n{input_step}\n3. 実行する操作を行う"
            expected = "期待どおりに処理され、後続の画面・表示が正しいこと"
        else:
            steps = f"{open_step}\n{input_step}\n3. 実行する操作を行う"
            expected = "処理が拒否され、原因が分かるメッセージが表示されること"

        note = (
            "入力値の具体値は未確定です。実データに合わせて確定してください。"
            if fields
            else "この画面には観測された入力項目がありません。表示・遷移の確認が主になります。"
        )

        rows.append(
            TestCaseRow(
                no=0,
                screen=screen_name,
                case_type=case_type,
                viewpoint=viewpoint,
                category_large=screen_name or "対象機能",
                category_medium=viewpoint,
                category_small=technique,
                precondition=precondition,
                steps=steps,
                expected=expected,
                note=note,
            )
        )

    numbered = renumber(rows)
    items = tuple(
        StageItem(
            item_id=f"tc-{row.no}",
            title=f"No.{row.no} {row.screen} / {row.viewpoint}（{row.case_type}）",
            detail=f"{row.steps}\n期待結果: {row.expected}",
            data=row.to_dict(),
        )
        for row in numbered
    )
    note = (
        f"ローレベルテストケース {len(items)} 件。QualityForward のカラム構成で出力します。"
        "手順・データはひな形なので、QAアシスタントに相談しながら具体化できます。"
    )
    return items, note


def build_stage(stage_id: str, obs: Observation, pipeline: Pipeline) -> Stage:
    """指定段階の内容をルールベースで生成し、生成済みの Stage を返す。"""
    stage = pipeline.get(stage_id)
    if stage is None:
        raise ValueError(f"未知の段階です: {stage_id}")

    if stage_id == STAGE_TEST_OBJECTIVE:
        items, note = _build_test_objective(obs)
    elif stage_id == STAGE_TEST_PLAN:
        items, note = _build_test_plan(obs)
    elif stage_id == STAGE_FEATURES:
        items, note = _build_features(obs)
    elif stage_id == STAGE_VIEWPOINTS:
        items, note = _build_viewpoints(obs, pipeline.get(STAGE_FEATURES))
    elif stage_id == STAGE_BASIC_DESIGN:
        items, note = _build_basic_design(pipeline.get(STAGE_VIEWPOINTS))
    elif stage_id == STAGE_DETAIL_DESIGN:
        items, note = _build_detail_design(pipeline.get(STAGE_BASIC_DESIGN))
    elif stage_id == STAGE_TEST_CASES:
        items, note = _build_test_cases(
            obs, pipeline.get(STAGE_DETAIL_DESIGN), pipeline.get(STAGE_FEATURES)
        )
    else:  # pragma: no cover - STAGE_ORDER で網羅済み
        raise ValueError(f"未実装の段階です: {stage_id}")

    return stage.with_items(items, note)


def test_case_rows(pipeline: Pipeline) -> list[TestCaseRow]:
    """テストケース段階から QualityForward 互換の行を取り出す。"""
    from autorun.qf_schema import from_dict

    stage = pipeline.get(STAGE_TEST_CASES)
    if stage is None:
        return []
    return renumber([from_dict(item.data, fallback_no=i) for i, item in enumerate(stage.items, 1)])
