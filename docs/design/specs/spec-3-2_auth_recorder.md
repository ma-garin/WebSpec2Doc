# SPEC-3-2 認証フローレコーダー（非エンジニア向け auth_state 保存）

| 項目 | 値 |
|---|---|
| WBS | 3-2 |
| 優先度 / 見積 | P1 / 1sp |
| 依存 | なし（3-1 と独立） |
| 背景 | docs/11 §5 A1（実用障壁の除去） |

## 1. 目的と背景

実サイト活用の最大障壁はログインの壁である。現在の auth_state（auth.json）取得手段は、(a) CLI `--login` の `input()` 待ち（端末必須）、(b) GUI 手渡しログイン `--login-signal`（CLI からのみ起動可能）、(c) `--login-simple` / `--login-scrape` / `--login-submit` の headless 自動ログイン（フォーム構造依存・MFA やソーシャルログインに弱い）の 3 系統。**「見えるブラウザで人が普通にログインし、ボタン一つで保存する」フローを Web UI から起動できる経路が無く**、非エンジニアが自力でログイン後領域をクロールできない。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/crawler/auth.py::capture_auth_state_via_signal` — headful ブラウザ起動→シグナルファイル出現待ち（`crawler/login_signal.py::wait_for_signal`）→ `context.storage_state()` 保存・chmod 600（ADR-0001）
- 済: `src/main.py` の `--login` / `--login-signal` / `--auth` 引数と `_capture_login`
- 済: `web/routes/login.py` — simple/scrape/submit の 3 API（サブプロセス起動・認証情報は stdin 渡しの前例）
- 済: `src/analyzer/login_wall.py::detect_login_wall` — ログイン成否判定（auto_login.py で使用中）
- 済: `src/capture/session_recorder.py` — 記録用 headful ブラウザ＋ポーリング監視の前例
- 未: Web UI からの手渡しログイン起動・完了ボタン・状態ポーリング
- 未: ログイン完了の自動検知（パスワード欄消失・URL 変化の提示）と保存後の検証（auth.json でログインウォールを越えられるか）

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: シグナル方式でセッションが保存される（Given: レコーダー起動中 / When: シグナルファイルが出現 / Then: auth.json が保存され、パーミッションが 600 である）
- **AC-2**: Web UI から一連のフローが完了する（Given: クロール設定画面 / When: 「ブラウザでログインして保存」→ ログイン → 「ログイン完了」ボタン / Then: レスポンスに auth_path が含まれ、クロール設定の auth 欄へ反映される）
- **AC-3**: ログイン完了の自動検知が提示される（Given: レコーダー起動中 / When: パスワード欄が消え URL が変化 / Then: ステータスが `login_detected` になる。**自動保存はしない** — 推定は提示のみ、保存は人の確認後）
- **AC-4**: タイムアウト時は保存しない（Given: レコーダー起動中 / When: timeout 秒シグナルなし / Then: ステータス `timeout`・auth.json は作成されない）
- **AC-5**: ブラウザが閉じられたら安全に終了する（When: 保存前にユーザーがブラウザを閉じる / Then: ステータス `closed`・部分ファイルを残さない）
- **AC-6**: 保存後に検証結果を返す（When: 保存直後 / Then: auth.json 適用でログイン URL を再訪し `detect_login_wall` が非ログインなら `verified: true`、判定不能なら `verified: false` と「未確認」を明示）
- **AC-7**: 既存の `--login` / `--login-simple` / `--login-scrape` / `--login-submit` 経路と既存テストが無変更で PASS する

## 3. スコープ外

- 認証情報（ID・パスワード）の保存・再利用（storage_state の Cookie/localStorage のみ保存。既存方針を維持）
- ログイン操作列からのテスト資産逆生成（WBS 2-1 の領域。操作記録は行わない）
- リモート/ヘッドレスサーバでの headful 表示（DISPLAY なし環境は明示エラー — ローカル利用前提。VNC 等は Phase 2）
- auth.json の有効期限管理・自動再ログイン（session_guard の既存挙動のまま）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/crawler/auth_recorder.py` | シグナル待ち＋完了自動検知＋保存後検証＋ステータスファイル出力 |
| 変更 | `src/crawler/auth.py` | `capture_auth_state_via_signal` の中核を auth_recorder へ委譲（互換ラッパー化） |
| 変更 | `src/main.py` | `--login-record` フラグ追加（`--login`＋`--login-signal` の統合入口・状態ファイル引数） |
| 変更 | `web/routes/login.py` | `/api/login/record/start`・`/status`・`/complete`・`/cancel` 追加 |
| 変更 | `templates/partials/view-generate.html`・`static/js/wizard.js` | 認証セクションにレコーダー UI（起動・完了・状態表示） |
| 変更 | `tests/test_auth.py`・新規 `tests/test_auth_recorder.py`・`tests/test_app_login.py` | §6-1 |
| 変更 | `quality/feature_contracts.yml` | login 契約の core_files/failure_modes/required_tests 更新 |

### 4-2. データモデル

```python
# src/crawler/auth_recorder.py
@dataclass(frozen=True)
class RecorderStatus:
    """レコーダーの進行状態。status ファイル（JSON 1 行）として UI へ公開する。"""

    phase: str          # "waiting" / "login_detected" / "saved" / "timeout" / "closed" / "error"
    current_url: str    # 検知時点の URL（evidence: 何を根拠に検知したか）
    detail: str = ""    # "パスワード欄の消失とURL変化を検知" 等（日本語）
    verified: bool | None = None  # AC-6。None = 未検証
```

### 4-3. 処理フロー

```text
Web UI「ブラウザでログインして保存」
  → POST /api/login/record/start
     └─ subprocess: src/main.py --login-record --login-record-url <url>
                    --auth <output/{domain}/auth.json>
                    --login-signal <output/{domain}/.login_signal>
                    --login-status <output/{domain}/.login_status.json>
        └─ auth_recorder.record_auth_session()
           ├─ headful Chromium 起動 → login_url へ遷移（capture_auth_state_via_signal と同型）
           ├─ ポーリングループ（0.5 秒間隔・session_recorder の方式）
           │   ├─ has_password_field / URL 変化を監視 → login_detected を status へ
           │   └─ シグナルファイル出現 → storage_state 保存（chmod 600）→ 検証 → saved
           └─ timeout / ページクローズ → timeout / closed を status へ
UI は /api/login/record/status を 1 秒間隔でポーリングし、
「ログイン完了」ボタン → POST /api/login/record/complete（シグナルファイル touch）
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/crawler/auth_recorder.py
def record_auth_session(
    login_url: str,
    auth_path: Path,
    signal_file: Path,
    status_file: Path | None = None,
    timeout: float = 600.0,           # auth.py の SIGNAL_WAIT_TIMEOUT_SEC を共用
    headless: bool = False,           # テスト・CI 用
    poll_interval: float = 0.5,
) -> RecorderStatus:
    """headful ブラウザで人のログインを待ち、シグナル受領時にセッションを保存する。
    ループ内で毎周 (1) signal_file 存在 (2) has_password_field(page) と page.url を確認。
    status_file には RecorderStatus を JSON で原子的に上書き（.tmp → replace）。"""

def verify_auth_state(login_url: str, auth_path: Path) -> bool | None:
    """保存済み auth.json でログイン URL を headless 再訪し、detect_login_wall で検証。
    到達失敗・判定不能は None（=未確認）。auto_login.py の PageAuthSignals 構築を踏襲。"""
```

- ログイン完了の自動検知は**近似**（パスワード欄消失 かつ URL 変化）。SPA では誤検知しうるため phase 提示のみで保存トリガーにしない（AC-3。evidence-only: 推定を事実として扱わない）
- `web/routes/login.py::/api/login/record/start` は `_valid_domain` 検証後、既存 3 API と同じ `subprocess.Popen` 方式（非ブロッキング。PID を返し `/cancel` で terminate）。URL はコマンドライン引数で渡してよい（秘匿情報ではない）。パスワードはプロセスに一切渡らない

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| DISPLAY なし等で headful 起動失敗 | phase="error"・detail に原因 | 「この機能はローカル環境で GUI ブラウザを使います」 |
| timeout 秒シグナルなし | phase="timeout"・auth.json 未作成 | 「時間切れです。もう一度お試しください」 |
| 保存前にブラウザを閉じた | PlaywrightError 捕捉 → phase="closed" | 「ブラウザが閉じられました（保存されていません）」 |
| storage_state 書き込み失敗 | phase="error"・部分ファイル削除 | エラーメッセージ表示 |
| 検証の再訪が失敗 | verified=None のまま saved | 「保存済み（動作確認は未確認）」 |

### 5-3. 既存コードとの接続点

- `auth.py::capture_auth_state_via_signal` は `record_auth_session` を呼ぶ薄いラッパーに置換（戻り値 `Path | None` の互換維持 — `tests/test_auth.py` を壊さない）
- `main.py::_capture_login`（504 行付近）に `--login-record` 分岐を追加。既存 `--login` / `--login-signal` の挙動は不変
- `web/routes/login.py` の `OUTPUT_DIR / domain / "auth.json"` パス規約・`_valid_domain` を踏襲。保存成功レスポンスの `auth_path` キーも既存 API と同名にする（wizard.js が共用）
- ステータスファイルは `output/{domain}/.login_status.json`（ドット始まり = report 出力と混同しない。スナップショット互換に影響なし）

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_auth_recorder.py・フェイク page 注入）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_signal_saves_auth_with_permission | シグナルを途中で作成するフェイク | storage_state 呼び出し・chmod 600 | AC-1 |
| test_login_detected_phase_without_save | password 欄消失＋URL 変化を返すフェイク | phase=login_detected・保存されない | AC-3 |
| test_timeout_leaves_no_auth_file | FakeClock でシグナルなし | phase=timeout・auth.json 不存在 | AC-4 |
| test_page_closed_returns_closed | evaluate が例外を投げるフェイク | phase=closed・例外を出さない | AC-5 |
| test_status_file_written_atomically | status_file 指定 | .tmp 経由で JSON が更新される | 5-1 |
| test_verify_auth_state_unreachable_is_none | 到達不能 URL | None（未確認） | AC-6 |

フェイクは `tests/test_capture.py::_FakeRecorderPage`・`tests/test_real_site_resilience.py::_FakeClock` に倣う。route テストは `tests/test_app_login.py` に start/status/complete/cancel を追加（subprocess はモック）。

### 6-2. 実ブラウザ E2E（tests/e2e/test_auth_recorder_e2e.py・専用スレッドパターン必須）

- 標的はデモサイト `login.html`（唯一この機能ではログインページが正しい標的。CONVENTIONS §4-5 はクロール E2E の話）。headless=True で起動し、フォーム送信をテストコードが代行 → シグナル作成 → auth.json 保存と verified を検証（AC-1, 2, 6）
- ポートは 8900 を使用（CONVENTIONS §4-7。8898 は SPEC-3-1 が使用）

### 6-3. 回帰確認

- `tests/test_auth.py`・`tests/test_auto_login.py`・`tests/test_app_login.py` の既存ケースが無変更で PASS（AC-7）
- `make verify-ui`（view-generate.html / wizard.js 変更のため必須）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness/verify-ui）
- [ ] feature_contracts.yml の login 契約に auth_recorder 系（core_files・failure_modes: display_missing / recorder_timeout / browser_closed）を追記
- [ ] 実行パス確認: Web UI → record/start → デモサイトでログイン → complete → auth.json 保存 → その auth で `--urls` クロールがログイン後ページを取得することを目視確認
- [ ] auth.json のパーミッションが 600 であることを実機確認

## 8. このタスク固有の罠

- **Playwright sync API の binding コールバック内から page 操作すると再入で行き詰まる**。監視はポーリング方式にする（session_recorder.py の設計理由コメント参照）。`page.on(...)` でのログイン検知は実装しない
- Flask 開発サーバはワーカー内グローバルが多重起動で共有されない。**レコーダーの進行状態はメモリでなくファイル（status_file）で共有する**（既存 login_signal.py と同じ理由）
- e2e で `sync_playwright()` を直接呼ぶと asyncio ループ衝突で死ぬ（CONVENTIONS §4-2）。`_run_in_thread` パターン必須
- headful 起動は CI では不可能。E2E は headless=True 引数で通し、headful は DoD の目視確認に回す（できない場合「未確認」と報告）
- `--login-record` の待機は最長 600 秒。web ルート側は subprocess.run で**ブロックしない**こと（既存 3 API と違い Popen＋ポーリング。SUBMIT_TIMEOUT_SEC=60 を流用すると必ずタイムアウトする）
