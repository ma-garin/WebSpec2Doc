# SPEC-6-2 依存更新戦略（playwright 1.44 固定の更新判断基準と移行検証手順）

| 項目 | 値 |
|---|---|
| WBS | 6-2 |
| 優先度 / 見積 | P2 / 1sp |
| 依存 | なし |
| 背景 | 動作環境（Python 3.11〜3.12 のみ = playwright 1.44.0 の wheel 制約、`docs/specs/CONVENTIONS.md §2`） |

## 1. 目的と背景

`playwright==1.44.0` 固定（requirements.txt）が製品全体の動作環境を規定している。制約の実装箇所は分散しており、**更新のたびに全箇所を漏れなく動かす手順が存在しない**:

- `src/doctor.py`: `SUPPORTED_PYTHON_MIN = (3, 11)` / `SUPPORTED_PYTHON_MAX_EXCLUSIVE = (3, 13)` と、「playwright 1.44」のハードコード文言 3 箇所（docstring 6 行目・コメント 27 行目・エラーメッセージ 65 行目）
- `src/crawler/playwright_runtime.py`: Chromium をリポジトリ配下 `.runtime/ms-playwright` に固定（`configure_playwright_browsers_path` / `verify_playwright_runtime`。導入は `scripts/manage_playwright_runtime.py install` = CONVENTIONS §4 罠 8）
- `.github/workflows/ci.yml`: smoke / e2e-ui ジョブが **ubuntu-22.04 固定**（コメント「Playwright 1.44 の OS 依存は 24.04 と非互換のため固定」）、`PLAYWRIGHT_BROWSERS_PATH` を workspace 配下へ指定
- `docs/specs/CONVENTIONS.md §2`: 「Python 3.11〜3.12（3.13 は不可）」の文書制約
- 関連ピン: `pytest-playwright==0.8.0`（playwright 本体とバージョン整合が必要）

放置リスク: Python 3.13 以降の環境に導入不可（新規顧客環境・開発機の OS 更新で詰む）、Ubuntu ランナー EOL 追随不可、Chromium/playwright の脆弱性対応が遅れる（pip-audit は CI 済みだが検出後の更新手順が未整備）。

**本仕様の成果物は 3 点**: (a) 更新判断基準と移行検証手順の playbook 文書、(b) doctor の「対応表」化（playwright ピン→対応 Python 範囲を導出。未知ピンは根拠なく許可せず「未確認」と言う）、(c) 現行版でのロールバック・再固定手順の実地検証。**playwright の実更新そのものはスコープ外**（本仕様が整備する手順に従う別 PR で実施）。

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: doctor が requirements.txt の playwright ピンから対応 Python 範囲を導出する（Given: ピン 1.44.0 / When: check_python_version / Then: 3.12 は PASS・3.13 は FAIL＋venv 再作成の fix 提示 — 現行挙動と同一）
- **AC-2**: 対応表に無いピンでは「対応 Python 範囲は未確認（PyPI の wheel メタデータを実測して対応表へ追記すること）」という fix 付きの**未確認**結果を返す（evidence-only: 根拠のない範囲を PASS/FAIL と断定しない）
- **AC-3**: `docs/process/dependency_update_playbook.md` に §4-2 の判断基準表と §4-3 の検証手順（候補選定→再構築→chromium 再固定→全ゲート→E2E 全通し→文書更新→ロールバック）が全て記載され、参照するコマンド・ファイルパスが実在する（テストで存在検証）
- **AC-4**: chromium 再固定とロールバックの手順が現行版で実地検証されている（Given: .runtime/ms-playwright を退避 / When: `make setup-runtime` → `make doctor` / Then: `verify_playwright_runtime` が Chromium 起動確認 PASS。検証ログを実装報告に添付）
- **AC-5**: 既存テスト（1,222 件）と doctor の既存 PASS/FAIL 挙動が Python 3.12＋1.44.0 環境で不変

## 3. スコープ外

- playwright の実更新（1.44.0 → 新版）の実施とコミット（本 playbook に従う別 PR）
- Python 3.13 対応の正式宣言・CONVENTIONS §2 の書き換え（実更新 PR で同時に行う — playbook の手順 6 に含める）
- playwright 以外の依存の一括自動更新（Renovate/Dependabot 導入の是非は別途判断。pip-audit による脆弱性検出は CI 実装済み）
- Firefox/WebKit ランタイム対応（現状 Chromium のみ — manage_playwright_runtime.py の install 対象）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/doctor.py` | `PLAYWRIGHT_PYTHON_SUPPORT` 対応表・`check_python_version` がピンを受け取る・ハードコード文言 3 箇所を表参照へ |
| 新規 | `docs/process/dependency_update_playbook.md` | 判断基準・移行検証・ロールバック手順（§4-2/§4-3 を正本化） |
| 変更 | `docs/specs/CONVENTIONS.md` | §2 の Python 範囲記述に playbook への参照を 1 行追記（範囲自体は変えない） |
| 変更 | `tests/test_doctor.py` | 対応表・未知ピンのテスト追加（§6） |
| 新規 | `tests/test_dependency_playbook.py` | playbook の必須章・参照パス実在の検証（AC-3） |

### 4-2. 更新判断基準（playbook に正本を置く）

| トリガー | 判断 |
|---|---|
| pip-audit / GitHub Advisory が playwright・Chromium の脆弱性を検出 | 即時評価。修正版が対応表の検証済み範囲外なら §4-3 を完走してから更新 |
| Python 3.13+ が必須の導入先環境が発生 | cp313 wheel の存在を **PyPI メタデータで実測**した候補版へ §4-3 で移行 |
| CI ランナー（ubuntu-22.04）の EOL 接近 | 24.04 で smoke/e2e-ui が通る playwright 版へ移行（ci.yml の固定コメントを更新） |
| pytest-playwright 等の周辺が新 playwright を要求 | 本体と同一 PR で整合バージョンへ（片方だけ上げない） |
| 上記なし | 四半期ごとに更新要否をレビュー（更新しない判断も記録する） |

### 4-3. 移行検証手順（playbook の骨子・実更新 PR はこの順で全部通す）

```text
1. 候補選定   : PyPI の JSON API（pypi.org/pypi/playwright/<ver>/json）で cp313 等の
                wheel 有無を実測 → doctor の対応表へ「実測日付き」で追記。
                pytest-playwright の互換版も同時に確定
2. 再構築     : ブランチで requirements.txt / requirements-dev.txt 更新
                → Python 3.12 venv 再作成 → make setup-runtime（Chromium 再固定・
                .runtime 内の旧版ディレクトリ削除）→ make doctor 全 PASS
3. 全ゲート   : CONVENTIONS §3（black/ruff/mypy/bandit/pytest/quality_harness）
4. E2E 全通し : venv/bin/python -m pytest tests/e2e -v（実ブラウザ＋UI 全件）
                ＋ smoke 相当（src/main.py --url https://example.com --compare を 2 回）
                ＋ make verify-ui ＋ make demo で DemoMart を目視
5. 新 Python  : 移行動機が 3.13 の場合、3.13 venv でも 2〜4 を繰り返す
6. 文書更新   : doctor 対応表・CONVENTIONS §2・
                ci.yml のランナー固定（22.04→24.04 可否を e2e 実測で判断）を同一 PR で
7. ロールバック: git revert → venv/bin/pip install -r requirements-dev.txt
                → make setup-runtime → make doctor → make verify-all
                （.runtime に旧 Chromium が残っていれば再ダウンロード不要）
```

## 5. 詳細設計

### 5-1. doctor の対応表と関数シグネチャ

```python
# src/doctor.py
# playwright ピン → (対応 Python 最小, 上限排他)。検証済みの版のみ載せる（実測日を併記）。
PLAYWRIGHT_PYTHON_SUPPORT: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "1.44.0": ((3, 11), (3, 13)),  # 実測 2026-07-04: cp313 wheel なし
}

def check_python_version(
    version: tuple[int, int, int] | None = None,
    playwright_pin: str | None = None,
) -> CheckResult:
    """対応表からピンの Python 範囲を引いて検査する。
    ピン未指定は requirements.txt 由来の呼び出し側（run_all_checks）が渡す。
    表に無いピンは ok=False・detail=「対応範囲未確認」・fix=PyPI 実測の案内。"""
```

- `run_all_checks` は既存 `parse_requirement_pins` の結果から playwright ピンを取り出して渡す（requirements.txt 不在時は現行の既定範囲 3.11〜3.13 未満で従来どおり検査）
- ハードコード文言（「playwright 1.44 の対応範囲は…」）はピン値を埋め込む f-string 化し、版更新時の直し漏れを構造的になくす

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| requirements.txt 不在 | 現行既定範囲で検査（挙動維持） | doctor 結果に既定範囲の注記 |
| ピンが対応表に無い | ok=False・「未確認」 | fix「PyPI wheel を実測し PLAYWRIGHT_PYTHON_SUPPORT へ追記」 |
| pip 更新後に setup-runtime 未実行 | 既存 `verify_playwright_runtime` が起動失敗を検出 | fix「make setup-runtime」（既存文言） |

### 5-3. 既存コードとの接続点

- `src/doctor.py::parse_requirement_pins` / `check_dependency_pins` / `check_chromium_runtime` — 再利用（新規パーサを書かない）
- `scripts/manage_playwright_runtime.py::install_runtime` — 版更新時の Chromium 再固定の唯一の入口（`playwright install` 直叩き禁止 = CONVENTIONS §4 罠 8）
- `.github/workflows/ci.yml` — 本仕様では変更しない（ランナー固定の解除は実更新 PR の手順 6）

## 6. テスト仕様

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_known_pin_derives_range | ピン "1.44.0"・version=(3,12,0)/(3,13,0) | PASS / FAIL＋venv 再作成 fix | AC-1 |
| test_unknown_pin_reports_unverified | ピン "9.99.0" | ok=False・detail に「未確認」・fix に PyPI 実測の案内 | AC-2 |
| test_no_requirements_falls_back | playwright_pin=None | 現行既定範囲（3.11〜3.12）で検査 | AC-5 |
| test_message_embeds_pin_value | ピン "1.44.0"・version=(3,13,0) | detail にピン値が含まれる（ハードコード撲滅の検証） | AC-1 |
| test_playbook_sections_present | playbook md | 判断基準表・手順 1〜7・ロールバック章が存在 | AC-3 |
| test_playbook_referenced_paths_exist | playbook 内のリポジトリ相対パス | 全て実在（make ターゲット名は Makefile と突合） | AC-3 |

回帰確認: tests/test_doctor.py 既存分が無変更で PASS。`make doctor` を Python 3.12 実環境で実行し全項目 PASS の実測ログを添付（AC-4/AC-5。3.13 環境の FAIL 側は CI に 3.13 が無いため、`check_python_version(version=(3,13,0), playwright_pin="1.44.0")` の単体テストで代替 — 実行できない検証は代替根拠を明記する）。

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜5 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] AC-4 の実地検証: .runtime 退避 → `make setup-runtime` → `make doctor` PASS → 退避を戻すロールバックまでのログを実装報告に添付
- [ ] playbook が docs/process/ 配下の既存文書（functional-integrity-gate.md 等）と体裁一致・CONVENTIONS §2 から参照されている
- [ ] 実行パス確認: doctor CLI（`make doctor`）の出力に対応表由来の文言が表示されることを目視確認

## 8. このタスク固有の罠

- **playwright 版と Chromium リビジョンは 1:1**。pip だけ上げて `make setup-runtime` を忘れると実行時に初めて起動失敗する（doctor の `check_chromium_runtime` が検出するが、playbook 手順 2 で構造的に防ぐ）。旧 Chromium ディレクトリは .runtime に残り容量を食う — 手順 2 の削除を省かない
- 新版の Python 対応を**ブログ記事・リリースノートの記憶で判断しない**。PyPI の wheel ファイル名（cp313 等）の実測のみを根拠とし、対応表に実測日を残す（evidence-only）。本仕様も「どの新版が 3.13 対応か」を意図的に書いていない — 実測してから表に書く
- `pytest-playwright==0.8.0` を置き去りにすると、fixture 互換で e2e だけ落ちる。周辺ピン（pytest-playwright）は本体と**同一 PR**で更新する
- ubuntu-24.04 非互換は 1.44 固有の既知事象（ci.yml コメント）。新版で解除「できるはず」ではなく、ランナー変更は e2e 全通し（手順 4）を 24.04 で実測してから
- pytest-playwright のセッション fixture が asyncio ループを保持する罠（CONVENTIONS §4 罠 2）は版を上げても残る前提で扱う。e2e の専用スレッドパターン（`_run_in_thread`）を更新検証時に外さない
- doctor の対応表はハードコードの移し替えに見えるが、目的は「**未知の版で沈黙して PASS/FAIL を断定しない**」こと。表を辞書 get の既定値で現行範囲に倒すと AC-2 が満たせなくなる
