# SPEC-3-1 iframe / Shadow DOM 対応（実サイト対応の土台）

| 項目 | 値 |
|---|---|
| WBS | 3-1 |
| 優先度 / 見積 | P1 / 1sp |
| 依存 | なし（他タスクの土台） |
| 背景 | docs/11 §3 Sprint A |

## 1. 目的と背景

現行クローラの要素抽出は、**フォームのみ** iframe 対応済み（`extract_forms_including_frames`）だが、リンク・見出し・ボタン・アクション要素（状態探索の対象）はメインフレームしか見ていない。また Shadow DOM（Web Components）内の要素は全抽出関数が素通りする。レガシー業務システム（iframe 構成）とモダン UI（Shadow DOM）の両方で「画面にあるのに仕様書に載らない」欠落を解消する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/crawler/link_extractor.py::extract_forms_including_frames` — 同一オリジン iframe のフォーム収集・クロスオリジンはスキップ（警告ログのみ）
- 未: リンク（`extract_internal_links`）・見出し（`extract_headings`）・ボタン（`extract_buttons`）の iframe 走査
- 未: 全抽出の Shadow DOM 走査（Playwright の CSS エンジンは open shadow root を自動貫通するが、`eval_on_selector_all("form", ...)` の**セレクタ評価は貫通しても、JS 内で `document.querySelectorAll` を使う箇所は貫通しない**。関数ごとに実態を確認すること）
- 未: `src/crawler/action_explorer.py` の `SAFE_ACTION_SELECTOR` 列挙と `_LIVE_STATE_JS` の shadow root 内要素対応
- 未: closed shadow root・クロスオリジン iframe の「読めなかった」記録

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: iframe 内のリンク・見出し・ボタンが親ページの PageData に統合される（Given: iframe を含むデモページ / When: crawl_page / Then: iframe 内のリンク先が links に、見出しが headings に含まれる）
- **AC-2**: open Shadow DOM 内のフォームフィールドが FieldData として抽出され、evidence（セレクタ・bbox）が付く
- **AC-3**: open Shadow DOM 内のボタンクリックで出現するモーダルが PageState として検出される（state_signature は既存アルゴリズムのまま）
- **AC-4**: クロスオリジン iframe は中身を読まず、PageData に「外部埋め込みあり（src URL）」として記録される
- **AC-5**: closed shadow root は「検出したが読めない」として記録される（evidence-only 原則: 無いことにしない）
- **AC-6**: iframe/Shadow DOM を含まない既存ページの出力（report.json のスキーマ・既存テスト 1,222 件）が変化しない
- **AC-7**: 実ブラウザ E2E がデモサイトの新設ページで AC-1〜3 を検証する

## 3. スコープ外

- ネストした shadow root 内の iframe（組み合わせ爆発。Phase 2）
- クロスオリジン iframe の中身取得（技術的に不可能 — 記録のみ）
- pierce セレクタによる操作系（action_explorer のクリックは shadow 内トリガーのみ対応、shadow 内のフォーム dry-run 送信は対象外）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/crawler/link_extractor.py` | 抽出 JS の shadow 走査化・iframe 横断ヘルパー追加 |
| 変更 | `src/crawler/action_explorer.py` | アクション要素列挙と `_LIVE_STATE_JS` の shadow 対応 |
| 変更 | `src/crawler/page_crawler.py` | PageData に `embedded_frames` フィールド追加・crawl_page の呼び替え |
| 変更 | `src/generator/json_reporter.py` | `embedded_frames` の出力（**存在時のみキー追加** — report_hash 互換） |
| 新規 | `demo/site/legacy_frame.html` + `demo/site/frame_content.html` | iframe 検証ページ（フォーム・リンク・見出し入り） |
| 新規 | `demo/site/components.html` | Web Components 検証ページ（open + closed shadow root） |
| 変更 | `tests/test_crawler.py` ほか | 単体テスト追加（§6-1） |
| 新規 | `tests/e2e/test_frames_shadow_e2e.py` | 実ブラウザ E2E（§6-2） |
| 変更 | `quality/feature_contracts.yml` | crawl 契約の core_files/failure_modes 更新 |

### 4-2. データモデル

```python
# src/crawler/page_crawler.py に追加
@dataclass(frozen=True)
class EmbeddedFrame:
    """ページ内 iframe の記録。クロスオリジンは readable=False で中身を読まない。"""

    src: str            # iframe の src（絶対 URL）
    readable: bool      # 同一オリジンで中身を読めたか
    note: str = ""      # "クロスオリジンのため未読" / "closed shadow root を含む" 等

# PageData に追加（既定値付き = 後方互換）
    embedded_frames: tuple[EmbeddedFrame, ...] = ()
```

### 4-3. 処理フロー

```text
crawl_page(page, url, output_dir)
  ├─ extract_forms_including_frames(page)      # 既存（変更なし）
  ├─ extract_links_all_scopes(page, base_url)  # 新: main + 同一オリジン frames + open shadow
  ├─ extract_headings_all_scopes(page)         # 新: 同上
  ├─ extract_buttons_all_scopes(page)          # 新: 同上
  ├─ collect_embedded_frames(page)             # 新: EmbeddedFrame 一覧（readable 判定）
  └─ explore_page_actions(page)                # 変更: shadow 内トリガーも列挙
```

## 5. 詳細設計

### 5-1. Shadow DOM 走査 JS（共通ヘルパー）

`link_extractor.py` にモジュール定数として追加し、各抽出 JS から呼ぶ:

```javascript
// _SHADOW_WALK_JS: document 配下の全要素を open shadow root 込みで列挙し、
// セレクタに一致するものを返す。closed shadow root はホスト要素を検出のみ。
(selector) => {
  const matches = [];
  const closedHosts = [];
  const walk = (root) => {
    root.querySelectorAll('*').forEach((el) => {
      if (el.matches && el.matches(selector)) matches.push(el);
      if (el.shadowRoot) walk(el.shadowRoot);          // open のみ入れる
      else if (el.tagName && el.tagName.includes('-') && !el.shadowRoot) {
        // カスタム要素で shadowRoot が null → closed の可能性（attachShadow({mode:'closed'})）
        closedHosts.push(el.tagName.toLowerCase());
      }
    });
  };
  walk(document);
  return { matches: matches.map(/* 各抽出関数固有の変換 */), closedHosts };
}
```

実装上の要点:

- `page.evaluate` で呼ぶ（`eval_on_selector_all` は使わない — shadow 内へ降りられないため統一する）
- closed 判定は近似（カスタム要素タグ名に `-` を含み shadowRoot が null）。**過検出よりも取りこぼし側に倒し、note に「closed の可能性」と書く**（断定しない）
- 戻り値は `{matches: [...], closedHosts: [...]}` の 2 要素。closedHosts が非空なら EmbeddedFrame ではなく PageData.a11y_issues ではなく、`embedded_frames` に `EmbeddedFrame(src="shadow:<tag>", readable=False, note="closed shadow root の可能性")` として記録する

### 5-2. 関数シグネチャ

```python
# link_extractor.py
def extract_links_all_scopes(page: Page, base_url: str) -> list[str]:
    """main frame・同一オリジン iframe・open shadow root からリンクを収集する。
    順序: main → frames（page.frames 順）→ 重複除去（dict.fromkeys）。"""

def extract_headings_all_scopes(page: Page) -> list[str]: ...
def extract_buttons_all_scopes(page: Page) -> list[str]: ...

def collect_embedded_frames(page: Page) -> list[EmbeddedFrame]:
    """page.frames から main 以外を列挙。frame.url が同一オリジンなら readable=True。
    クロスオリジンは readable=False, note='クロスオリジンのため未読'。"""

# action_explorer.py（変更）
# query_selector_all(SAFE_ACTION_SELECTOR) を _SHADOW_WALK_JS ベースの列挙に置換。
# ハンドルが必要なため page.evaluate_handle で ElementHandle 配列を得る。
# _LIVE_STATE_JS 内の querySelectorAll 3 箇所を walk 化（dialog/tab/details/expanded）。
```

### 5-3. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| クロスオリジン iframe へのアクセス例外 | 捕捉して readable=False で記録・処理続行 | report の埋め込み一覧に「未読」表示 |
| shadow 走査 JS の評価失敗 | 警告ログ・従来抽出（main のみ）へフォールバック | ログ「Shadow DOM 走査に失敗（従来抽出で継続）」 |
| frame のデタッチ（走査中に消えた） | PlaywrightError 捕捉・その frame をスキップ | 警告ログ |

### 5-4. 既存コードとの接続点

- `page_crawler.py:539` 付近の import と `crawl_page` 内の抽出呼び出し（`extract_forms_including_frames` の隣）
- `action_explorer.py::SAFE_ACTION_SELECTOR`・`_LIVE_STATE_JS`・`state_signature`（**署名アルゴリズム変更禁止** — CONVENTIONS §1-3）
- `json_reporter.py::_screen_dict` — `official_name` と同じオプトイン方式で `embedded_frames` を追加

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_crawler.py または新規 tests/test_frames_shadow.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_embedded_frame_cross_origin_recorded | フェイク page（frames=[main, cross-origin]） | EmbeddedFrame(readable=False, note に「クロスオリジン」) | AC-4 |
| test_embedded_frame_same_origin_readable | 同一オリジン frame | readable=True | AC-4 |
| test_links_all_scopes_dedup | main と frame に同一リンク | 重複除去され1件 | AC-1 |
| test_shadow_walk_fallback_on_js_error | evaluate が例外を投げるフェイク | 従来抽出結果を返し例外を出さない | 5-3 |
| test_closed_shadow_recorded_as_unreadable | closedHosts=["my-widget"] を返すフェイク | embedded_frames に readable=False・note に「closed」 | AC-5 |
| test_pagedata_without_frames_unchanged | 既存ページ相当 | embedded_frames == () かつ report.json にキーなし | AC-6 |

フェイクは `tests/test_capture.py::_FakeRecorderPage` に倣い、`frames`・`evaluate` を注入可能にする。

### 6-2. 実ブラウザ E2E（tests/e2e/test_frames_shadow_e2e.py・専用スレッドパターン必須）

デモサイトに追加するページ:

- `legacy_frame.html`: `<iframe src="frame_content.html">` を含む。frame_content.html には見出し・フォーム（必須フィールド）・products.html へのリンク
- `components.html`: `customElements.define` で open shadow（フォーム＋モーダルを開くボタン）と closed shadow（`attachShadow({mode:'closed'})`）を持つ要素

| テスト名 | 検証 | AC |
|---|---|---|
| test_iframe_links_and_headings_merged | crawl_page(legacy_frame) → frame 内リンク・見出しが PageData に含まれる | AC-1 |
| test_shadow_form_fields_have_evidence | crawl_page(components) → shadow 内フィールドに evidence 付き | AC-2 |
| test_shadow_modal_state_detected | components のボタンで modal 状態が page_states に載る | AC-3 |
| test_closed_shadow_reported | components の closed 要素が「読めない」記録になる | AC-5 |

ポートは 8898 を使用（CONVENTIONS §4-7）。

### 6-3. 回帰確認

- 既存ユニット全件・既存実ブラウザ E2E 5 件が無変更で PASS
- `docs/demo/sample_output/report.json` との比較で既存ページのスキーマ差分がないこと（AC-6）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml 更新（crawl の core_files・failure_modes に iframe/shadow 系を追記）
- [ ] デモサイト新ページが `make demo` で表示される
- [ ] 実行パス確認: CLI で legacy_frame.html / components.html をクロールし、report.json に frame 内要素と embedded_frames が载ることを目視確認

## 8. このタスク固有の罠

- Playwright の「CSS エンジンは shadow を自動貫通」は**ロケータ API の話**。`page.evaluate` 内の `document.querySelectorAll` は貫通しない。混同すると「テストは通るのに実サイトで取れない」が起きる
- `eval_on_selector_all("form", ...)` から `page.evaluate(walk)` へ置き換える際、既存 `_FORM_SCRIPT` の要素変換ロジックをそのまま流用すること（FieldData のスキーマを変えない）
- iframe 内要素の evidence の selector は frame 文脈を失う。selector 先頭に `frame[src=...] >>> ` 相当のプレフィックスを付けるか、note で frame 由来を明示する（bbox は frame 内座標になるため screenshot との整合に注意 — Phase 1 では bbox 省略可、省略時は None を入れて「未取得」を明示）
