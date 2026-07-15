# 設計ドキュメント: ログイン（メールのみ）＋ テナント選択の本体組み込み

> **注（2026-07-16 追記）**: 本 ADR で導入した軽量認証は、商用/共有サーバ向けの
> 認証・テナント分離実装（`docs/AUTH_TENANCY.md`、機能 `account_auth`/`tenant_isolation`）に
> 統合・置換された。本書は設計判断の履歴として保持する。

対象: WebSpec2Doc 本体（`web/` Flask アプリ）
作成日: 2026-07-14
状態: **レビュー待ち（未実装）**

---

## 1. 背景と目的

現状の WebSpec2Doc は **ローカル単一ユーザー向けツール**であり、アプリ利用者の認証・アカウント・テナント（ワークスペース）概念を一切持たない。

- `app.py` は `127.0.0.1` バインド＋ブラウザ自動起動。
- コード内の「login」（`web/routes/login.py` の `/api/login/*`, `src/main.py --login`）は**クロール対象サイトへのログインセッション取得**であり、本件のユーザー認証とは無関係。
- Flask `secret_key` 未設定・`session` 未使用。

本件では、`Downloads/login_tenant.html` のモックデザインを実装として取り込み、
**メールアドレスのみのログイン → テナント選択 → アプリ本体** という利用者導線を追加する。

## 2. スコープ

### やること（このフェーズ）
1. メールアドレスのみのログイン（パスワードなし）
2. ログイン後のテナント（ワークスペース）選択
3. セッションによる認証状態の保持・ログアウト
4. 未認証時のアクセス制御（ガード）
5. 上記のサーバレンダリング画面（モックデザイン準拠）
6. pytest / Playwright による経路検証

### やらないこと（明示的な非ゴール・別フェーズ）
- **テナント別データ物理分離**（既存のクロール成果物・履歴・`viewpoints.db` のテナント単位分割）。→ 第5章の重要決定事項参照。
- メール送信によるマジックリンク／確認コード認証。
- パスワード・MFA・外部 IdP（Google 等）連携の実接続（モックのボタンは表示のみ）。

## 3. 認証モデル（重要な前提）

「メールアドレスのみで良い」に基づき、本実装は **self-asserted identity（自己申告のメール識別）** とする。

- パスワード検証・メール到達確認は行わない。入力メール＝そのまま本人とみなしセッションを張る。
- これは**暗号的な認証ではなく「利用者の識別と作業ワークスペースの選択」**である。ドキュメント・UI 文言でもそのニュアンスを保ち、「セキュアなログイン」とは称さない。
- 社内 LAN／ローカル利用（既存の localhost_guard / TRUSTED_HOSTS 前提）を想定した軽量識別として妥当。

> この前提で問題ないか、レビューで確認したい（第8章 Q1）。

## 4. ドメインモデルと保存

イミュータブル更新（新オブジェクト生成）でファイルベース保存。既存の `instance/` を利用。

```
instance/auth/
  users.json         # [{ "email", "created_at", "last_login_at" }]
  tenants.json       # [{ "id", "name", "created_at" }]
  memberships.json   # [{ "user_email", "tenant_id", "role" }]  role: owner|admin|member
```

- `frozen=True` dataclass で `User` / `Tenant` / `Membership` を表現（`web/rules/python` 準拠）。
- 初回ログイン時、メンバーシップが無ければ**既定テナントを自動作成**して owner を付与（初回体験を成立させる）。
- ストアは小さなリポジトリ関数群（`load/save/find`）に分離。多数小ファイル原則に従い `web/auth/` 配下に分割。

## 5. 【要決定】テナント別データ分離の扱い

現状、クロール成果物・履歴・設定・`viewpoints.db` は**単一の格納先**を共有している。「本物の認証」を厳密に取ると、テナントごとにこれらを分離する必要があるが、これは広範囲（全 route / service）に及ぶ大規模改修になる。

機能インテグリティ・ゲート上、「分離できているように見えるが実は共有」は禁止のため、以下いずれかをレビューで選ぶ:

- **(A) 段階導入（推奨）**: 本フェーズは「認証＋テナント選択をセッションに保持し UI に表示」まで。既存データは共有のまま。ドキュメントに"未分離"を明記し、分離は別チケット。
- **(B) 完全分離まで一括**: 出力ディレクトリ・履歴・DB をテナント ID で名前空間化。工数大・既存テスト全面改修・回帰リスク大。

## 6. ルート設計（新規 `auth` ブループリント）

既存 `/api/login/*`（サイト認証）との混同を避け、利用者認証は `auth` ブループリント配下に置く。

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/auth/login` | ログイン画面（メールのみ） |
| POST | `/auth/login` | メール検証→ユーザ upsert→`session['user_email']`→`/auth/tenants` へ |
| GET | `/auth/tenants` | テナント選択画面（要ログイン） |
| POST | `/auth/tenants/select` | `session['tenant_id']` 設定→`/` へ |
| POST | `/auth/logout` | セッション破棄→`/auth/login` へ |

- CSRF は既存 `csrf_guard`（Origin/Referer 同一オリジン判定）でカバーされるため、フォーム隠しトークンは不要。
- メール検証は境界バリデーション（正規表現＋長さ）。不正時は 400 相当でエラー表示（フェイルファスト）。

## 7. ガードと既存挙動の非破壊

**課題**: 全 route を認証必須にすると、既存の E2E／quality_harness／自動ブラウザ起動（無認証前提）が全滅する。

**方針（推奨）**: 認証を環境変数フラグ `WEBSPEC2DOC_AUTH`（既定 OFF）で切替。

- OFF（既定）: 現行どおり完全無認証。既存テスト・ローカル UX を維持。
- ON: `before_request` ガードを有効化。
  - 許可: `/auth/*`, `static`, 既存 `/api/login/*`（サイト認証 API）。
  - 未ログイン→`/auth/login` にリダイレクト。
  - ログイン済・テナント未選択→`/auth/tenants` にリダイレクト。
- `secret_key` は `WEBSPEC2DOC_SECRET_KEY`（無ければ `instance/auth/secret.key` を生成・永続化）。

> フラグ既定 OFF が最も安全（回帰ゼロ）。ただし「常時 ON で組み込む」を望む場合はテスト側の一括対応が必要（第8章 Q2）。

## 8. レビューで決めたいこと

- **Q1**: 認証モデルは「メール自己申告（パスワード・到達確認なし）」で確定してよいか。
- **Q2**: 認証はフラグ既定 OFF（推奨）か、常時 ON か。
- **Q3**: テナント別データ分離は (A) 段階導入（推奨）か (B) 完全分離一括か。
- **Q4**: 既定テナント名の初期値（例: `"My Workspace"` / メールのドメイン名）。

## 9. 追加・変更ファイル（実装フェーズの計画）

新規:
- `web/auth/__init__.py`, `web/auth/models.py`（frozen dataclass）, `web/auth/store.py`（JSON リポジトリ）, `web/auth/session.py`（セッションヘルパ）, `web/auth/guard.py`（before_request）
- `web/routes/auth.py`（上記ルート）
- `templates/auth/login.html`, `templates/auth/tenants.html`
- `static/css/auth.css`, （必要なら）`static/js/auth.js`
- `tests/web/test_auth_routes.py`, `tests/e2e/test_auth_flow.spec`（Playwright）

変更:
- `web/__init__.py`: `secret_key` 設定、`auth` ブループリント登録、フラグ ON 時のガード登録。
- `quality/feature_contracts.yml` / `scripts/quality_harness.py`: 認証導線の契約追加（必要に応じ）。

## 10. テスト計画（機能インテグリティ経路）

`UI → API → route → service/store → session → output → error` を実検証。

- happy: メール入力→ログイン→既定テナント自動作成→選択→`/` 到達。
- failure: 不正メール→エラー表示・非遷移。
- guard: 未ログインで保護 route→`/auth/login` へ。ログイン済・未選択→`/auth/tenants` へ。
- logout: セッション破棄後、保護 route が再度リダイレクト。
- 非破壊: `WEBSPEC2DOC_AUTH` 未設定で既存 E2E / `make test` / `make verify-ui` が緑のまま。
- Playwright（MCP）でログイン→テナント選択の実機導線を確認。

## 11. リスク

- マルチテナントの**データ分離を伴わない**認証は「見せかけ」になりやすい。第5章で扱いを明確化する。
- ローカル単一ユーザーツールに利用者認証を足すこと自体の設計整合性（本当に必要か）。→ 別環境展開（TRUSTED_HOSTS）を想定するなら妥当。
- 既存テスト資産への影響。→ フラグ既定 OFF で回避。
