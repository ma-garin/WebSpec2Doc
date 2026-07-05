"""文書の再生（refresh_reporter）のユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData, SourceEvidence
from generator.refresh_reporter import (
    REFRESH_LOG_NAME,
    REFRESH_MD_NAME,
    build_refresh_entries,
    render_refreshed_markdown,
    save_refresh_outputs,
)
from ingest.matcher import FieldGap, FusionResult, ScreenMatch, fuse
from ingest.models import DocumentBundle, DocumentedField, DocumentedScreen, DocumentEvidence

# ---------- 共通フィクスチャ（tests/test_doc_fusion.py のパターンを再利用） ----------


def _field(
    name: str,
    required: bool = False,
    maxlength: int | None = None,
    aria_label: str = "",
    field_type: str = "text",
    selector: str = "",
) -> FieldData:
    return FieldData(
        field_type=field_type,
        name=name,
        placeholder="",
        required=required,
        maxlength=maxlength,
        aria_label=aria_label,
        evidence=SourceEvidence(selector=selector or f"[name='{name}']"),
    )


def _page(url: str, title: str, fields: tuple[FieldData, ...] = ()) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=(title,),
        links=(),
        forms=forms,
        screenshot_path=None,
    )


def _login_bundle(max_length: int = 20) -> DocumentBundle:
    login = DocumentedScreen(
        screen_id="GA-010",
        name="ログイン画面",
        url_hint="/login.html",
        evidence=DocumentEvidence(file="設計書.xlsx", location="画面一覧!A2", quote="ログイン画面"),
    )
    return DocumentBundle(
        screens=(login,),
        fields=(
            DocumentedField(
                name="パスワード",
                physical_name="password",
                screen_name="ログイン画面",
                field_type="文字列",
                required=True,
                max_length=max_length,
                note="8文字以上",
                evidence=DocumentEvidence(
                    file="設計書.xlsx", location="項目定義!A2", quote="パスワード"
                ),
            ),
        ),
        source_files=("設計書.xlsx",),
    )


# ---------- AC-1: mismatch は実測値が採用され旧値が注釈される ----------


class TestUpdatedAnnotation:
    def test_mismatch_updated_with_annotation(self) -> None:
        bundle = _login_bundle(max_length=20)
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/login.html",
                    "ログイン",
                    fields=(_field("password", required=True, maxlength=40),),
                )
            ]
        )
        result = fuse(pages, bundle)
        entries = build_refresh_entries(result, bundle, pages)
        updated = [e for e in entries if e.kind == "updated"]
        assert len(updated) == 1
        assert updated[0].attribute == "桁数"
        assert updated[0].old_value == "20"
        assert updated[0].new_value == "40"
        assert updated[0].subject == "パスワード"

        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        assert "旧: 20" in markdown
        assert "実測: 40" in markdown
        # 新版の桁数欄は実測値の 40 が採用されている
        assert "| パスワード | 文字列 | ○ | 40 |" in markdown

    def test_required_and_length_both_mismatch_are_both_updated(self) -> None:
        """必須区分と桁数が同時に食い違う項目で、両方の変更が記録され、
        桁数が実測値に更新される（旧値を確定値として描画しない・回帰）。"""
        bundle = _login_bundle(max_length=20)  # doc: required=True, max_length=20
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/login.html",
                    "ログイン",
                    # 実測: 必須=False・桁数=40（doc と両方食い違う）
                    fields=(_field("password", required=False, maxlength=40),),
                )
            ]
        )
        result = fuse(pages, bundle)
        entries = build_refresh_entries(result, bundle, pages)
        updated = [e for e in entries if e.kind == "updated"]
        attrs = {e.attribute for e in updated}
        # 必須区分・桁数の両方が updated として記録される（片方が捨てられない）
        assert attrs == {"必須区分", "桁数"}
        length_entry = next(e for e in updated if e.attribute == "桁数")
        assert (length_entry.old_value, length_entry.new_value) == ("20", "40")

        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        # 桁数は実測 40 に更新される（旧値 20 のまま確定値として描画しない）
        assert "| パスワード | 文字列 | × | 40 |" in markdown
        assert "| パスワード | 文字列 | × | 20 |" not in markdown


# ---------- AC-2: doc_only は削除せず未確認注記付きで残る ----------


class TestDocOnlyUnconfirmed:
    def test_doc_only_kept_as_unconfirmed(self) -> None:
        legacy = DocumentedScreen(
            screen_id="GA-090",
            name="帳票出力画面",
            url_hint="/report.html",
            evidence=DocumentEvidence(file="設計書.xlsx", location="画面一覧!A3"),
        )
        bundle = DocumentBundle(screens=(legacy,), fields=(), source_files=("設計書.xlsx",))
        pages = analyze_pages([_page("https://example.com/other.html", "その他")])
        result = fuse(pages, bundle)
        assert [s.name for s in result.doc_only_screens] == ["帳票出力画面"]

        entries = build_refresh_entries(result, bundle, pages)
        doc_only_screen_entries = [
            e for e in entries if e.kind == "doc_only" and e.subject == "画面"
        ]
        assert len(doc_only_screen_entries) == 1
        assert doc_only_screen_entries[0].screen_name == "帳票出力画面"

        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        assert "帳票出力画面" in markdown
        assert "実測で確認できず（未確認 — 廃止/権限/未探索の可能性）" in markdown

    def test_doc_only_field_kept_as_unconfirmed(self) -> None:
        """マッチした画面内で実測に見つからない項目も削除されず注記付きで残る。"""
        login = DocumentedScreen(screen_id="GA-010", name="ログイン画面", url_hint="/login.html")
        bundle = DocumentBundle(
            screens=(login,),
            fields=(
                DocumentedField(
                    name="社員番号", screen_name="ログイン画面", required=True, max_length=8
                ),
            ),
            source_files=("設計書.xlsx",),
        )
        pages = analyze_pages([_page("https://example.com/login.html", "ログイン")])
        result = fuse(pages, bundle)
        entries = build_refresh_entries(result, bundle, pages)
        doc_only_field = [e for e in entries if e.kind == "doc_only" and e.subject == "社員番号"]
        assert len(doc_only_field) == 1

        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        assert "社員番号" in markdown
        assert "実測で確認できず（未確認 — 廃止/権限/未探索の可能性）" in markdown


# ---------- AC-3: crawl_only は新規画面章として追記される ----------


class TestCrawlOnlyNewScreen:
    def test_crawl_only_appended_as_new(self) -> None:
        login = DocumentedScreen(screen_id="GA-010", name="ログイン画面", url_hint="/login.html")
        bundle = DocumentBundle(screens=(login,), fields=(), source_files=("設計書.xlsx",))
        pages = analyze_pages(
            [
                _page("https://example.com/login.html", "ログイン"),
                _page(
                    "https://example.com/dashboard.html",
                    "ダッシュボード",
                    fields=(_field("keyword", required=False),),
                ),
            ]
        )
        result = fuse(pages, bundle)
        assert len(result.crawl_only_page_ids) == 1

        entries = build_refresh_entries(result, bundle, pages)
        new_screen_entries = [e for e in entries if e.kind == "new" and e.subject == "画面"]
        assert len(new_screen_entries) == 1
        assert new_screen_entries[0].screen_name == "ダッシュボード"
        assert new_screen_entries[0].new_value == "https://example.com/dashboard.html"

        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        assert "文書未記載の新規画面" in markdown
        assert "ダッシュボード" in markdown
        assert "https://example.com/dashboard.html" in markdown
        assert "keyword" in markdown


# ---------- AC-4: 変更ログに全件記録される ----------


class TestRefreshLog:
    def test_refresh_log_records_all(self, tmp_path: Path) -> None:
        bundle = _login_bundle(max_length=20)
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/login.html",
                    "ログイン",
                    fields=(_field("password", required=True, maxlength=40),),
                ),
                _page(
                    "https://example.com/dashboard.html",
                    "ダッシュボード",
                    fields=(_field("keyword", required=False),),
                ),
            ]
        )
        result = fuse(pages, bundle)
        save_refresh_outputs(result, bundle, pages, tmp_path)

        assert (tmp_path / REFRESH_MD_NAME).exists()
        log_path = tmp_path / REFRESH_LOG_NAME
        assert log_path.exists()
        data = json.loads(log_path.read_text(encoding="utf-8"))
        assert data["meta"]["updated"] == 1
        assert data["meta"]["new"] == 1
        kinds = {e["kind"] for e in data["entries"]}
        assert "updated" in kinds
        assert "new" in kinds
        updated_entry = next(e for e in data["entries"] if e["kind"] == "updated")
        assert updated_entry["old_value"] == "20"
        assert updated_entry["new_value"] == "40"
        assert updated_entry["doc_evidence"] is not None
        assert updated_entry["crawl_selector"]


# ---------- AC-5: 参考文書なしでは生成されない（オプトイン） ----------


class TestOptIn:
    def test_no_reference_no_output(self, tmp_path: Path) -> None:
        bundle = DocumentBundle(screens=(), fields=(), source_files=())
        pages = analyze_pages([_page("https://example.com/", "トップ")])
        result = FusionResult(
            screen_matches=(), doc_only_screens=(), crawl_only_page_ids=(), field_gaps=()
        )
        save_refresh_outputs(result, bundle, pages, tmp_path)
        assert not (tmp_path / REFRESH_MD_NAME).exists()
        assert not (tmp_path / REFRESH_LOG_NAME).exists()


# ---------- AC-6: 一致している記載は一字も書き換えず転記される ----------


class TestUnchangedVerbatim:
    def test_unchanged_verbatim(self) -> None:
        login = DocumentedScreen(screen_id="GA-010", name="ログイン画面", url_hint="/login.html")
        bundle = DocumentBundle(
            screens=(login,),
            fields=(
                DocumentedField(
                    name="メールアドレス",
                    physical_name="email",
                    screen_name="ログイン画面",
                    field_type="文字列",
                    required=True,
                    max_length=100,
                    note="RFC5322準拠",
                ),
            ),
            source_files=("設計書.xlsx",),
        )
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/login.html",
                    "ログイン",
                    fields=(_field("email", required=True, maxlength=100),),
                )
            ]
        )
        result = fuse(pages, bundle)
        entries = build_refresh_entries(result, bundle, pages)
        unchanged = [e for e in entries if e.kind == "unchanged"]
        assert len(unchanged) == 1
        assert unchanged[0].subject == "メールアドレス"

        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        # name・型・備考が入力とバイト一致で転記される（注釈が付かない）
        assert "| メールアドレス | 文字列 | ○ | 100 | RFC5322準拠 |" in markdown


# ---------- AC-7: 文書由来の正式名称が見出しに使われる ----------


class TestOfficialNameHeading:
    def test_official_name_as_heading(self) -> None:
        login = DocumentedScreen(screen_id="GA-010", name="ログイン画面", url_hint="/login.html")
        bundle = DocumentBundle(screens=(login,), fields=(), source_files=("設計書.xlsx",))
        pages = analyze_pages([_page("https://example.com/login.html", "Sign In")])
        result = fuse(pages, bundle)
        entries = build_refresh_entries(result, bundle, pages)
        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        assert "## ログイン画面（実測: Sign In / https://example.com/login.html）" in markdown


# ---------- 5-2: crawl_selector 逆引き失敗時は安全に文書値のまま残す ----------


class TestSelectorLookupFailure:
    def test_selector_lookup_failure_safe(self) -> None:
        login = DocumentedScreen(screen_id="GA-010", name="ログイン画面", url_hint="/login.html")
        doc_field = DocumentedField(
            name="パスワード",
            screen_name="ログイン画面",
            field_type="文字列",
            required=True,
            max_length=20,
        )
        bundle = DocumentBundle(screens=(login,), fields=(doc_field,), source_files=("x.xlsx",))
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/login.html",
                    "ログイン",
                    fields=(_field("password", required=True, maxlength=40, selector="#pw"),),
                )
            ]
        )
        match = ScreenMatch(
            page_id=pages[0].page_id,
            page_url=pages[0].page_data.url,
            page_title=pages[0].page_data.title,
            screen=login,
            score=1.0,
            method="url",
        )
        # 実在しない selector を持つ mismatch ギャップを直接構築する
        gap = FieldGap(
            kind="mismatch",
            page_id=pages[0].page_id,
            field_name="パスワード",
            detail="桁数が矛盾: 文書では 20、実測では 40",
            doc_field=doc_field,
            crawl_selector="#does-not-exist",
        )
        result = FusionResult(
            screen_matches=(match,),
            doc_only_screens=(),
            crawl_only_page_ids=(),
            field_gaps=(gap,),
            official_names={pages[0].page_id: "ログイン画面"},
        )

        entries = build_refresh_entries(result, bundle, pages)
        # 実測値を特定できなかった矛盾は "updated" として空値で偽計上せず、
        # "unconfirmed"（未確認）として honest に記録する（evidence-only）
        assert [e for e in entries if e.kind == "updated"] == []
        unconfirmed = [e for e in entries if e.kind == "unconfirmed"]
        assert len(unconfirmed) == 1
        assert unconfirmed[0].attribute == ""
        assert unconfirmed[0].old_value == ""
        assert unconfirmed[0].new_value == ""

        # 例外を出さずに描画でき、文書値のまま(20)で残る
        markdown = render_refreshed_markdown(entries, result, bundle, pages)
        assert "矛盾は検出したが実測値を特定できず（未確認" in markdown
        assert "| パスワード | 文字列 | ○ | 20 |" in markdown


# ---------- 6-2 結合テスト: 新版を再度参考文書として読み戻せる ----------


class TestRefreshRoundTrip:
    def test_refreshed_markdown_is_re_readable(self, tmp_path: Path) -> None:
        from ingest.text_reader import read_markdown

        bundle = _login_bundle(max_length=20)
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/login.html",
                    "ログイン",
                    fields=(_field("password", required=True, maxlength=40),),
                )
            ]
        )
        result = fuse(pages, bundle)
        save_refresh_outputs(result, bundle, pages, tmp_path)
        md_path = tmp_path / REFRESH_MD_NAME
        tables, _headings = read_markdown(md_path)
        assert len(tables) == 1
        assert tables[0].headers == ("項目名", "型", "必須", "桁数", "備考")
        row = next(r for r in tables[0].rows if r.cells[0] == "パスワード")
        assert row.cells[3] == "40"
