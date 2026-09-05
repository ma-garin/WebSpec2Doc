# 実装計画 v2: 「壊れたら直る」— 報告書を主語にしたオートヒーリング

作成: 2026-09-05 / 実行者: Sonnet（`goal` 単位） / 対象: WebSpec2Doc System 05
**参照の実在検査済み**（2026-09-05・壊れていた 7 件を修正済み）

## Context

事業計画と画面案（https://claude.ai/code/artifact/216f4e38-92e3-4dea-8564-cbf5c36eb218）で決めたこと:

- **製品は「保守対応報告書」**。判断とは「この報告書を顧客に出してよいか」。PR は承認の副産物
- 買い手は **SIer の保守部門**（固定価格の保守契約・クラウド AI にコードを送れない）
- 画面は **報告書一覧／報告書本文／設定** の 3 つ。差分・根拠・AI の説明は折りたたみの奥
- 作らない: 自動マージ・ロケータ張替・クラウド版・IDE プラグイン

本書は、それを **Sonnet が 1 手順ずつ迷わず実行できる形**にしたもの。
各手順は **前提チェック → 変更 → 確認 → 失敗時** を持ち、30 分以内で閉じる。

---

## A. 全 goal 共通の型（Sonnet はこの順を毎回そのまま実行する）

```bash
# A-1 着手
cd /Users/fujimagariyuki/dev/active/webspec2doc
git pull --ff-only && git checkout -b feat/healing-g<N>-<slug>
git status --short            # 自分が触っていない変更が出たら、それは他セッションのもの。触らない・退避しない・add しない

# A-2 8765 を最新コードで起動（テンプレ・JS・CSS・Python を変えたら毎回）
kill $(lsof -ti:8765) 2>/dev/null
FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 WEBSPEC2DOC_AUTH_MODE=off \
  WEBSPEC2DOC_HEALING_ROOTS="/private/tmp/claude-501/-Users-fujimagariyuki-dev-active-webspec2doc/3890b03b-4d26-4605-8650-722fb0829966/scratchpad:/Users/fujimagariyuki/dev/active" \
  nohup venv/bin/python app.py > /tmp/ws2d.log 2>&1 &
curl -s --retry 25 --retry-delay 1 --retry-connrefused -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/healing   # 200
grep -c Traceback /tmp/ws2d.log   # 0

# A-3 担当外ファイルの機械検査（goal ごとの ALLOWED を使う。出力が空でなければ、その変更を git checkout -- <file> で戻す）
git diff --name-only | grep -vE "<ALLOWED>"

# A-4 コミット → PR → マージ（作成とマージは別コマンド。連結しない）
git add <パス明示>
git commit --no-verify -F /tmp/msg.txt
git push -u origin HEAD
gh pr create --base main --title "<件名>" --body-file /tmp/pr.md
gh pr merge <番号> --squash --delete-branch
git checkout main && git pull --ff-only
```

**守ること**
| # | 規則 | 根拠 |
|---|---|---|
| 1 | pytest / make test / verify-ui は**ユーザーが要求した時だけ**。受け入れ確認は下記の `curl` / `python -c` で行う | H-7 |
| 2 | 8765 以外にサーバを立てない | 2026-09-05 指示 |
| 3 | frozen dataclass はミューテーションしない。フィールド追加は**末尾・既定値つき** | 後方互換 |
| 4 | 画面に機能説明・キャッチコピー・内部用語（構造化／シリアライズ／spec-mismatch 等の code 名）を出さない | 本日の指摘 |
| 5 | `innerHTML` 禁止・外部 CDN 禁止・`healing.css` の `!important` は宣言 2 件から増やさない | 既存規約 |
| 6 | 前提チェックが期待と違ったら**その goal を止めて報告する**。推測で進めない | H-0-2 |
| 7 | 完了報告は 5 行: 変更ファイル／受け入れの実測値／未実行／PR 番号／他セッションの未コミット変更の有無 | H-8 |
| 8 | 検証で作った PR は `gh pr close <番号> --delete-branch`。PR #194（本日の実証）は**触らない** | |

**認証オフ（8765）での out_dir は `output/`**。`web/routes/healing.py::_out()` = `scoped_output_dir(OUTPUT_DIR)` はテナント有効時のみ `output/tenants/<slug>/` を返す。受け入れコマンドは `output/` で書く。

**検証用の実データ**（登録済み）
- 接続 `project_id=d9a116c79a98`「WebSpec2Doc 実証」。検証コマンドは絶対パスの `…/venv/bin/python -m pytest tests/healing_demo -q`
- `tests/healing_demo/demo_calc.py::add` が `a - b` で**失敗する**（main にコミット済み）
- 実行 `heal-d635066b27ba` = `awaiting_human`・PR #194 作成済み（触らない）
- デモリポジトリ `scratchpad/demo-134145`（`app/calc.py` が壊れている・リモート無し）

---

## B. 既存コードの地図（検査済み・2026-09-05）

| ファイル | 実在する関数・型（このとおりに呼ぶ） |
|---|---|
| `web/services/healing/types.py` | `HealingProject`（`project_id,name,repo_path,default_branch,verify_command,remote,github_repo,agent,max_iterations,max_parallel_agents,agent_timeout_sec,verify_timeout_sec,created_at,updated_at`）・`Defect`（`defect_id,title,severity,source,test_id,message,evidence,suspect_files,detected_at,locations`）・`FixProposal`（`…,risks,report_md`）・`HealingRun`（`run_id,project_id,status,iterations,pull_request,decisions,unverified,log,error,created_at,…`）・`RUN_STATUSES`・`ACTIVE_STATUSES`・`DECISION_ACTIONS`・`ConnectionCheck(key,label,ok,detail,severity)` |
| `web/services/healing/orchestrator.py` | `start_run(*, out_dir, project, actor="", extra_instructions="")`・`_run_loop_inner(out_dir, run, project, extra_instructions)`・`_fix_defects`・`_localize_defects`・`_enrich_proposal`・`record_decision(out_dir, run_id, *, action, note="", actor="")`・`create_pull_request_for_run(out_dir, run_id, *, draft=False)`・`rerun_verification(out_dir, run_id)`・`list_run_summaries(out_dir, project_id="", limit=50)`・`get_run(out_dir, run_id)`・`_add_log(run, msg)`・`_update(out_dir, run, *, status=None, step_label="", note="")`・`_RUNS_LOCK` |
| `web/services/healing/run_store.py` | `save_run(out_dir, run)`・`load_run(out_dir, run_id)`・`list_runs(out_dir, …)`・`run_summary(run)`。保存先 `out_dir/.healing/runs/<run_id>.json`・`_dict_tuple` |
| `web/services/healing/localization.py` | `LocationEvidence(path, reason, score, detail="")`・`locate(defect, *, repo, limit=5)`・`_SKIP_DIRS`・`_is_scannable(rel)`・`_is_test_file(rel)`・`_search_by_name` |
| `web/services/healing/risk.py` | `RiskSignal(code,label,detail,severity)`・`assess(proposal)`（12 種）・`parse_diff_stats(diff)`・`_parse_file_diffs(diff)`（モジュールレベル・import 可）・`_is_test_file` |
| `web/services/healing/report.py` | `build_report(defect, proposal, evidence=(), risks=(), *, run_id="", repo="", started_at="") -> str`・`build_pr_section(reports, risks=())`・`_escape_pipe` |
| `web/services/healing/project_store.py` | `list_projects(out_dir)`・`get_project(out_dir, pid)`・`save_project(out_dir, project)`・`allowed_roots()`・`discover_repos(out_dir, *, limit=200)`・`DiscoveredRepo`・`check_connection(project)`・`_DISCOVER_SKIP_DIRS` |
| `web/services/healing/agents.py` | `build_prompt(task)`・`_extract_json_object(text)`・`_collect_worktree_change(workdir)`・`_redact`・`ClaudeCodeAgent/CodexAgent/OpenAIAgent/OllamaAgent/DryRunAgent`・`_AGENT_CLASSES`・`_post_json` |
| `web/services/healing/git_ops.py` | `run_git(repo, args, timeout=120)`・`create_worktree(repo, branch, base, workdir)`・`commit_all(workdir, message)`（`--no-verify` 済）・`merge_branch_into_worktree(workdir, source_branch)`・`push_branch` |
| `web/services/healing/verification.py` | `run_verification(command, cwd, timeout)`・`parse_pytest_output`・`parse_generic_output`・`is_command_allowed`・`failures_to_defects(failures, *, repo, source="verify")` |
| `web/routes/healing.py` | `_out()`・`require_admin()`・`_record_audit(action, detail)`・`_mask_home(text)`・`_body()`・`_clean_note`・`_clean_int`・既存 API（`/api/healing/projects*`・`/runs*`・`/agents`・`/discover`）・画面 `GET /healing`・`GET /healing/runs/<run_id>`（テンプレ `healing.html`、`agents=`・`allowed_roots=`・`focus_run_id=` を渡す） |
| 02/03 の出力 | `output/<domain>/qa_process/playwright_report.json`（`tests[{title,status,duration_ms,error}]`）・`output/<domain>/testcases/playwright_report.json`・`output/<domain>/testcases/run_result.json`（`cases{TC-ID:{status,error}}`）・**`output/<domain>/testcases/testcases.spec.meta.json` = `{"tests":[{"test_title":"TC-P001-DSP-001 …","case_id":"TC-P001-DSP-001"}]}`（`page_id`/`url` は無い）**・スクショ `output/<domain>/test-results/**/*.png` |
| 01 の画面仕様 | `output/<domain>/report.json` の `screens[]`: `{page_id:"P001", url, title, headings[], buttons[], forms[], transitions:{to[],from[]}}`。生成は `src/generator/json_reporter.py::generate_json_report` / `_screen_dict` |
| 実行スナップショット | `web/services/run_store.py::run_dir(output_root, domain, run_id)`・`artifact_file(output_root, domain, run_id, relative)` |
| Playwright 実行 | `web/services/playwright_executor.py::run_playwright(spec_path, output_dir, …)`（**`output_dir` 必須**） |
| 定期実行の流儀 | `web/services/scheduler.py::start_scheduler()`（daemon Thread・60 秒・`_stop_event`）。起動は `web/__init__.py:138-140` |
| PDF | `src/generator/pdf_reporter.py::generate_pdf(html_path, pdf_path)`（Playwright headless・A4） |
| 03 の画面 | `templates/autorun-report.html`・`static/js/autorun-report.js`・`web/routes/autorun_report.py::autorun_report_page`（`GET /autorun/report/<domain>`） |
| `static/js/healing.js` | IIFE。`IS_ADMIN`(L159)・`on()`(L105)・`humanizeError`(L269)・`renderMarkdown`(L1845)・`buildDiffElement`(L1971) は **`window` に出ていない**。新 JS から使えない |

---

## C. 判断ルール（迷ったらこれに従う。ユーザーに聞かない）

| 状況 | 決定 |
|---|---|
| 新 JS で `healing.js` のヘルパーが欲しい | **コピーする**（自己完結）。`healing.js` を触らない。重複は G3c の報告に「重複 N 関数」と書く |
| 既存 dataclass にフィールドを足すと `to_dict/from_dict` が要る | `run_store._dict_tuple` の流儀に揃え、**古い JSON を読んでも落ちない**（`.get(key, 既定)`）ことを確認コマンドに含める |
| 受け入れコマンドが期待と違う | 直す前に**原因を 1 行で報告**し、その goal 内で直す。2 回目も違えば止める |
| LLM（Claude CLI / Ollama）が要る確認で、環境に無い | **その確認だけ「未実行」と明記**して goal を閉じる。代替として `agent=dryrun` で経路だけ通す |
| 「触らない」ファイルを触らないと成立しない | 止めて報告。**勝手に触らない** |
| 文言に迷う | 画面案 v3 の文言をそのまま使う。無ければ「事実＋次の行動」の 1 文 |
| 3 時間を超えそう | 止めて、済んだ手順と残りを報告。分割はユーザー |

---

## D. Goal 一覧と順序

```
Gpre 事前確認 → G0 移送 → G9 ブロッカー ─┐
                                        ▼
G1 報告書ドメイン → G2 報告書 API → G3a 一覧 → G3b 本文 → G3c 印刷と判断 ─┐（pytest 起点で報告書を承認できる＝デモ可）
                                                                       ▼
G4 02/03 接続 → G6 URL→ファイル限局 → G7 仕様照合 → G5 監視 ─┐（E2E 起点で「壊れたら直る」）
                                                          ▼
G8 ローカル LLM を diff に
```

---

## Gpre ─ 事前確認（15 分・変更なし）

**目的**: 以降の goal が前提にする環境が揃っているかを先に確かめる。1 つでも欠けたら止めて報告。

| # | コマンド | 期待 | 欠けたとき |
|---|---|---|---|
| 1 | `git status --short` | 空、または自分が触っていないファイルのみ | 触らない。報告に書く |
| 2 | A-2 の起動 → `curl … /healing` | `200` | `/tmp/ws2d.log` の Traceback を報告 |
| 3 | `gh auth status` | `Logged in` | ユーザーに `gh auth login` を依頼 |
| 4 | `curl -s http://127.0.0.1:8765/api/healing/projects \| python3 -c "import sys,json;print([p['project_id'] for p in json.load(sys.stdin)['projects']])"` | `d9a116c79a98` を含む | 「検証用の実データ」の接続を `POST /api/healing/projects` で作り直す（本文は A 節） |
| 5 | `ls output/.healing/runs/ \| wc -l` | ≥ 1 | 問題なし（0 なら G1 の受け入れで run を 1 本作る） |
| 6 | `curl -s http://127.0.0.1:11434/api/tags \| python3 -c "import sys,json;print([m['name'] for m in json.load(sys.stdin)['models']])"` | 任意（G8 で `qwen2.5-coder:7b` が要る） | 無ければ G8 の報告に「モデル未取得」と書くだけ。今は止めない |
| 7 | `ls output/*/report.json output/*/testcases/testcases.spec.meta.json 2>/dev/null` | 1 組以上 | 無ければ G4/G6/G7 の前に、01→02 を 8765 自身（`http://127.0.0.1:8765`）で 1 回回す（既存 UI で） |
| 8 | `which claude` | パスが出る | 無ければ G1〜G3 の受け入れは `agent=dryrun` で経路のみ確認し「Claude CLI 未検出」と書く |

完了報告: 8 項目の結果を 1 行ずつ。

### Gpre 実施済みの結果（2026-09-05・読み取り分のみ）

| # | 結果 | 対応 |
|---|---|---|
| 1 | `git status` に **`web/services/healing/git_ops.py`（未コミット）** と `.claude/settings.json`（他セッション） | **`git_ops.py` は本日の `--no-verify` + ANSI 除去の修正で、コミット漏れ。G9 の最初に、G9-1 の変更と合わせてコミットする。**`.claude/settings.json` は触らない |
| 3 | gh: `Logged in to github.com account ma-garin` | 問題なし |
| 6 | Ollama のモデルは **`qwen2.5:3b` のみ**。`qwen2.5-coder:7b` は**無い** | **G8 は着手時に `ollama pull qwen2.5-coder:7b` をユーザーへ依頼して止まる**（判断ルール C） |
| 7 | `output/{127.0.0.1:8765,8766,8767}/report.json` と各 `testcases/testcases.spec.meta.json` あり | G4/G6/G7 の前提充足。**`<D>` は `127.0.0.1:8765` を使う** |
| 8 | `/opt/homebrew/bin/claude` | G1〜G3 の受け入れは `agent=claude` で通せる |
| 2,4,5 | サーバ起動が要るため未実施 | 実装開始直後に A-2 を実行して確認する |

---

## G0 ─ 調査ファイルの移送（10 分）

**ALLOWED** `^docs/(research|plans)/`
| 手順 | 変更 | 確認 |
|---|---|---|
| 1 | `~/.claude/plans/zany-baking-popcorn-agent-abead0e546087e5db.md` → `docs/research/2026-09-05_biz-commercial-code-fix-tools.md`。先頭の `> **注記**` 段落（最初の空行まで）を除く | `grep -c "Plan mode" docs/research/2026-09-05_biz-commercial-code-fix-tools.md` → 0 |
| 2 | 同様に `a1fbfbe4fddc4759d` → `_biz-self-healing-test-market.md`、`a3e544578ed91b753` → `_biz-market-size-and-pricing.md`、`a0b449780007496b1` → `_biz-unmet-needs-and-gaps.md` | `ls docs/research/2026-09-05_biz-*.md \| wc -l` → 4 |
| 3 | 本ファイルを `docs/plans/2026-09-05_self-maintaining-web-plan.md` へコピー | `head -1 docs/plans/2026-09-05_self-maintaining-web-plan.md` が `# 実装計画 v2` |
コミット: `docs: オートヒーリング事業計画の調査 4 本と実装計画を保存`

---

## G9 ─ 実運用ブロッカー 4 件（40 分・独立）

**ALLOWED** `^web/services/healing/(git_ops|project_store|report|risk|localization)\.py$`

### 9-1 worktree に `venv` が無い（10 分）
- 前提: `grep -n "def create_worktree" web/services/healing/git_ops.py` → 1 行
- 変更: `create_worktree(repo, branch, base, workdir)` の**成功直後**に次を追加
  ```python
  _LINKED_UNTRACKED_DIRS = ("venv", ".venv", "node_modules")
  def _link_untracked_dirs(repo: Path, workdir: Path) -> None:
      """git 管理外の環境ディレクトリを worktree から辿れるようにする。
      worktree にはこれらが無く、相対パスの検証コマンドが必ず落ちる（2026-09-05 実測）。"""
      for name in _LINKED_UNTRACKED_DIRS:
          src, dst = Path(repo) / name, Path(workdir) / name
          if src.is_dir() and not dst.exists():
              try: os.symlink(src, dst)
              except OSError as exc: logger.warning("環境ディレクトリのリンクに失敗: %s (%s)", name, exc)
  ```
- 確認: 接続 `d9a116c79a98` を `PATCH` で `verify_command` を**相対** `venv/bin/python -m pytest tests/healing_demo -q` に → `POST /api/healing/runs` → 完了後 `python3 -c "import json;r=json.load(open('output/.healing/runs/<run_id>.json'));print(r['iterations'][0]['verify_before']['total'])"` → `1`（起動失敗なら `0`）。確認後 `verify_command` を絶対パスに戻す
- 失敗時: `ls -la <worktree>/venv` でリンクの有無を見る。worktree のパスは run JSON の `log` にある

### 9-2 `discover` の相対パス提案（5 分）
- 変更: `project_store.py` の `suggested_command` 生成で `venv/bin/python` を `str(repo / "venv" / "bin" / "python")` に
- 確認: `curl -s http://127.0.0.1:8765/api/healing/discover \| python3 -c "import sys,json;print(sum(1 for r in json.load(sys.stdin)['repos'] if r['suggested_command'].startswith('venv/')))"` → `0`

### 9-3 PR 本文の重複・無関係ファイル・英語 severity（15 分）
- 変更（`report.py::build_report`）: (a) 「該当箇所」は `evidence` を score 降順で**上位 3 件**のみ (b) `proposal.summary == proposal.rationale` なら「修正」節を省く (c) 冒頭の表の `severity` に既存の和訳表を適用
- 確認:
  ```bash
  venv/bin/python -c "
  from web.services.healing import report, types, localization
  d=types.Defect(defect_id='d',title='t',severity='medium',source='verify',test_id='x::y',message='m')
  p=types.FixProposal(defect_id='d',agent='claude',status='applied',summary='S',rationale='S',diff='',files_changed=('a.py',))
  ev=tuple(localization.LocationEvidence(path=f'f{i}.py',reason='traceback',score=1-i*0.1) for i in range(6))
  md=report.build_report(d,p,ev,())
  print('medium' in md, md.count('f3.py')+md.count('f4.py')+md.count('f5.py'), md.count('| S |')+md.count('\nS\n'))"
  ```
  期待: `False 0 1`
- 失敗時: 出力 `md` を `print` して該当節を見る

### 9-4 `tests-only` の誤判定（10 分）
- 変更: `risk.py` と `localization.py` の `_is_test_file` を**両方**、`パスが tests/ 配下` ではなく **`basename が test_*.py / *_test.py / conftest.py`** に
- 確認:
  ```bash
  venv/bin/python -c "
  from web.services.healing import risk, types
  d='--- a/tests/healing_demo/demo_calc.py\n+++ b/tests/healing_demo/demo_calc.py\n@@ -1,1 +1,1 @@\n-x\n+y\n'
  print([s.code for s in risk.assess(types.FixProposal(defect_id='d',agent='a',status='applied',diff=d,files_changed=('tests/healing_demo/demo_calc.py',)))])
  d2=d.replace('demo_calc.py','test_healing_demo.py')
  print([s.code for s in risk.assess(types.FixProposal(defect_id='d',agent='a',status='applied',diff=d2,files_changed=('tests/healing_demo/test_healing_demo.py',)))])"
  ```
  期待: 1 行目に `tests-only` が**無い**、2 行目に**ある**
コミット: `fix: オートヒーリングの実運用ブロッカー 4 件（worktree の venv・相対パス提案・PR 本文・tests-only 誤判定）`

---

## G1 ─ 報告書ドメイン（90 分）

**ALLOWED** `^web/services/healing/(report_doc|types|orchestrator|run_store)\.py$`

### 1-1 型を足す（15 分）
- 前提: `grep -nE "^\s+(url|screen_id|screen_name|test_title|screenshot|domain|report_org|report_ids): " web/services/healing/types.py` → **0 行**（衝突なし。検査済み）
- 変更（すべて**末尾・既定値つき**）:
  ```python
  # Defect
  url: str = ""; screen_id: str = ""; screen_name: str = ""; test_title: str = ""; screenshot: str = ""
  # HealingProject
  domain: str = ""; report_org: str = ""
  # HealingRun
  report_ids: list[str] = field(default_factory=list)
  # モジュールレベル
  REPORT_STATUSES: tuple[str, ...] = ("draft", "awaiting", "approved", "returned", "rejected", "submitted")
  ```
- `run_store.py`: `HealingRun.report_ids` を往復（`.get("report_ids", [])`）。`Defect` の新 5 フィールドは `to_dict`/`from_dict` が `asdict`/`.get` なら自動。**手書きなら足す**
- 確認: `venv/bin/python -c "from web.services.healing import run_store; from pathlib import Path; r=run_store.load_run(Path('output'),'heal-d635066b27ba'); print(r.report_ids, r.iterations[0].defects[0].url if hasattr(r.iterations[0].defects[0],'url') else 'NG')"` → `[] ''`（古い JSON を読んでも落ちない）

### 1-2 `report_doc.py` を作る（45 分・400 行以内・標準ライブラリのみ）
```python
@dataclass(frozen=True)
class MaintenanceReport:
    report_id: str; project_id: str; project_name: str; target_url: str; run_id: str; defect_id: str
    title: str; status: str
    incident_text: str; incident_detected_at: str; incident_source: str; incident_screen_id: str
    incident_screen_name: str; incident_test_id: str; incident_screenshot: str; incident_verify: str
    cause_text: str; cause_location: str
    action_text: str; action_by: str; action_at: str; action_diff_stats: str; action_screenshot: str
    verify_before: str; verify_after: str; verify_after_ok: bool | None; spec_match: str
    attention: tuple[dict, ...]; approvals: tuple[dict, ...]
    pr_number: int = 0; pr_url: str = ""; created_at: str = ""; updated_at: str = ""

def build_maintenance_report(*, run, iteration, defect, proposal, project) -> MaintenanceReport
def humanize_title(defect) -> str
def humanize_cause(proposal, defect) -> tuple[str, str]      # (cause_text, cause_location)
def to_dict(report) -> dict
def from_dict(d: dict) -> MaintenanceReport                   # 欠けたキーは既定値
def reports_dir(out_dir) -> Path                              # out_dir / ".healing" / "reports"
def save_report(out_dir, report) -> Path
def load_report(out_dir, report_id) -> MaintenanceReport | None
def list_reports(out_dir, *, status="", project_id="", limit=100) -> list[MaintenanceReport]   # updated_at 降順
def find_report(out_dir, *, run_id, defect_id) -> MaintenanceReport | None
def render_markdown(report) -> str
```
**`humanize_title` の規則**（上から順・最初に当たったもの・LLM 不使用）:
| `message`+`evidence` に含まれる | 件名 |
|---|---|
| `getByRole('button', { name: 'X' })` | `{画面}画面で「X」ボタンが表示されない` |
| `getByText('X')` / `getByLabel('X')` / `getByPlaceholder('X')` | `{画面}画面で「X」が表示されない` |
| `toHaveText` / `toContainText` | `{画面}画面の表示内容が期待と異なる` |
| `toHaveURL` | `{画面}画面からの遷移先が期待と異なる` |
| `AssertionError` or 行頭 `assert ` | `{test_title or test_id} が失敗する` |
| それ以外 | `{画面}画面: {test_title or test_id} が失敗` |
`{画面}` = `screen_name` → `screen_id` → 無ければ「画面で」ごと省く。正規表現は `re.search(r"getByRole\('button',\s*\{\s*name:\s*'([^']+)'", s)` の形。

**`humanize_cause`**: `proposal.rationale` を `。` で区切り、先頭から **200 字を超えない**範囲の文を連結。無ければ `原因を特定できませんでした。検証ログを確認してください。`。`cause_location` = `defect.locations[0]["path"]`（無ければ `proposal.files_changed[0]`）＋ diff の最初の `@@ -N,M` から ` N〜N+M-1 行`。
**`action_text`**: `proposal.status == "applied"` → `proposal.summary or "修正を適用しました"`。それ以外 → `""`。
**`action_by`**: `{"claude":"AI（Claude Code）","codex":"AI（Codex）","openai":"AI（OpenAI）","ollama":"AI（Ollama・ローカル）","dryrun":"動作確認用"}.get(agent, agent)`。
**`verify_*`**: `失敗 {failed} / {total}` or `通過 {passed} / {total}`。`verify_after` が `None` → `未実行`。
**`render_markdown`**: 節見出しは `## 保守対応報告書` `### 1. 事象` `### 2. 原因` `### 3. 対応` `### 4. 検証` `### 5. 承認`。値の `|` は `\|` に。

### 1-3 orchestrator に組み込む（30 分）
- `start_run(*, out_dir, project, actor="", extra_instructions="", defects=None)` に **`defects: Sequence[Defect] | None`** を追加。`_run_loop_inner` へ渡し、**渡されたら `failures_to_defects` の代わりに使う**（`verify_before` は実行する。`_localize_defects` は両方に通す）
- `_run_loop_inner` の各周回末（`verify_after` 確定後）と、run が terminal になる直前（`failed`/`no_defects`/`awaiting_human`/`succeeded` の `_update` 直前）に `_write_reports(out_dir, run, project)` を呼ぶ:
  - `iteration.defects` ごとに、対応する `proposal`（`defect_id` 一致・無ければ `None`）で `build_maintenance_report` → `find_report` で既存があれば `dataclasses.replace(existing, **新しい値, report_id=既存, created_at=既存, updated_at=now)` → `save_report` → `run.report_ids` に追加（重複なし）
  - 初期 `status` は常に `"awaiting"`
  - **try/except で包み、失敗しても run を止めない**（`_add_log` に日本語 1 行）
- 確認（8765 で run を 1 本回す。`agent=claude`、無ければ `dryrun`）:
  ```bash
  ls output/.healing/reports/ | wc -l                                                     # ≥ 1
  venv/bin/python -c "
  from pathlib import Path; from web.services.healing import report_doc
  r=report_doc.list_reports(Path('output'), status='awaiting')[0]
  print(r.title); print(r.cause_location); print(r.verify_before,'->',r.verify_after); print(r.action_by, len(r.attention))
  md=report_doc.render_markdown(r); print(all(h in md for h in ['1. 事象','2. 原因','3. 対応','4. 検証','5. 承認']))"
  ```
  期待: `title` = `tests/healing_demo/test_healing_demo.py::test_add が失敗する`、`verify_after` = `通過 1 / 1`（dryrun なら `未実行`）、最終行 `True`
- 失敗時: `output/.healing/runs/<run_id>.json` の `log` 末尾に「報告書の生成に失敗」があれば、その理由を報告
コミット: `feat: 保守対応報告書を生成・保存する（report_doc）`

---

## G2 ─ 報告書 API（60 分）

**ALLOWED** `^web/(routes/healing|services/healing/orchestrator)\.py$`

| メソッド | パス | 権限 | 返す |
|---|---|---|---|
| GET | `/api/healing/reports?status=&project_id=&limit=` | 閲覧 | `{"reports":[{report_id,run_id,project_id,project_name,target_url,title,status,verify_after,verify_after_ok,attention_count,attention_high,action_empty,incident_source,created_at,updated_at}]}` |
| GET | `/api/healing/reports/count?status=awaiting` | 閲覧 | `{"count":N}` |
| GET | `/api/healing/reports/<report_id>` | 閲覧 | `{"report": to_dict, "proposal": {diff,files_changed,rationale,locations}, "run": run_summary}` |
| PATCH | `/api/healing/reports/<report_id>` | 管理者 | body `{action_text?, cause_text?}` のみ更新（`_clean_note` 相当で制御文字除去・2000 字上限） |
| POST | `/api/healing/reports/<report_id>/decision` | 管理者 | body `{"action":"approve"\|"return"\|"reject","note":"","actor":""}` → `{"report": to_dict}` |
| GET | `/api/healing/reports/<report_id>/export?format=md\|json` | 閲覧 | `md`: `text/markdown; charset=utf-8`。`json`: `to_dict`。`html` は G3c |

`orchestrator.decide_report(out_dir, report_id, *, action, note="", actor="") -> MaintenanceReport`:
- `approve`: `create_pull_request_for_run(out_dir, run_id)` → `record_decision(action="approve")` → `status="approved"`・`pr_number/pr_url` を run の `pull_request` から → `approvals += {"role":"approved","who":actor,"at":now,"note":note}`
- `return`: `note` が空なら `HealingError("差し戻しの指示を書いてください")`。元 run の `Defect` を `iteration.defects` から取り、`start_run(out_dir=, project=, actor=actor, extra_instructions=note, defects=[defect])` → 元 report `status="returned"`・`approvals += returned`
- `reject`: `record_decision(action="reject")` → `status="rejected"`
- いずれも `_record_audit("healing.report.decision", {report_id, action, actor})`
- `count` は `/reports/<report_id>` より**前に**登録する（`count` が `report_id` にマッチしないよう、`_ID_RE` に `rep-[0-9a-f]{12}` を追加して 404 で弾く）

確認:
```bash
B=http://127.0.0.1:8765
curl -s "$B/api/healing/reports/count?status=awaiting"                                                   # {"count": ≥1}
RID=$(curl -s "$B/api/healing/reports?status=awaiting" | python3 -c "import sys,json;print(json.load(sys.stdin)['reports'][0]['report_id'])")
curl -s "$B/api/healing/reports/$RID/export?format=md" | head -3                                          # "## 保守対応報告書"
curl -s -X PATCH "$B/api/healing/reports/$RID" -H 'Content-Type: application/json' -d '{"action_text":"手で書いた対応"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['report']['action_text'])"   # 手で書いた対応
curl -s -X POST "$B/api/healing/reports/$RID/decision" -H 'Content-Type: application/json' -d '{"action":"approve","note":"検証","actor":"sonnet"}' | python3 -c "import sys,json;d=json.load(sys.stdin)['report'];print(d['status'],d['pr_number'])"   # approved <番号>
gh pr close <番号> --delete-branch
```
失敗時: `approve` が 4xx なら本文の `error` を報告（リモート未設定なら接続 `d9a116c79a98` の `github_repo` を確認）
コミット: `feat: 報告書の一覧・詳細・判断・出力 API`

---

## G3a ─ 報告書一覧（60 分）

**ALLOWED** `^(templates/(healing_reports\.html|partials/healing-sidebar\.html)|static/(js/healing-reports\.js|css/healing-reports\.css)|web/routes/healing\.py)$`
**判断ルール**: `healing.js` のヘルパーは**コピー**（`on`/`el`/`escape`/相対時刻）。`healing.js` は触らない。

### 3a-1 サイドバー partial（10 分）
`templates/partials/healing-sidebar.html`（`{% set active %}` で `reports`/`settings` を受ける）:
```
[W] WebSpec2Doc / オートヒーリング
システム ヒーリング [切替 → /systems]
─ ヒーリング
  報告書  <span id="hl-nav-count" hidden></span>   → /healing
  設定                                             → /healing/settings
```
「実行」「接続先」「実行履歴」「監視」は**出さない**。

### 3a-2 ルートと画面（30 分）
- `web/routes/healing.py`: `GET /healing` → `healing_reports.html`。**旧 `/healing` の内容は `GET /healing/settings`** に移す（`healing.html` をそのまま返す。`focus_run_id=None`）。`healing.html` のサイドバーは**次の G3c で** partial に差し替える（今は触らない）
- `healing_reports.html`: `topbar_title='オートヒーリング'`、本文 = チップ（`承認待ち N`・`提出済み`・`却下`）＋ `<select id="hl-project-filter">` ＋ 表 `#hl-reports-table`
- `healing-reports.js`（IIFE・`innerHTML` 禁止）: 起動時に `/api/healing/reports?status=awaiting` と `/count` と `/api/healing/projects` を並列取得 → 表を描く。列: 案件（`project_name`＋小さく `target_url`）／件名（`title`＋小さく `incident_screen_id incident_screen_name`）／検証（`verify_after` を `hl-badge-ok`（ok）/`hl-badge-err`（失敗）/`hl-badge-mute`（未実行））／確認が必要な点（`attention_high>0` → 赤 `N 件`、`attention_count>0` → 黄、`action_empty` → 灰 `直っていません`、else 灰 `なし`）／下書き（相対時刻）／`読む` ボタン。行は `role="link"` `tabindex="0"`、click/Enter で `/healing/reports/<id>`
- 空状態: `承認待ちの報告書はありません。` の 1 行
- 表の下に薄字 1 行: `「直っていません」は、機械が直せなかったもの。原因の報告書だけが下書きされ、対応は人が書く。`

### 3a-3 CSS（20 分）
`healing-reports.css`: `ta2.css` のトークンをフォールバック付きで。表・バッジ・チップは `healing.css` の見た目に**寄せる**（値をコピーしてよい）。`main.app-content{overflow:hidden}` ＋ 表の wrap を `overflow:auto; min-height:0`（1 画面構造）。

確認（8765・Playwright MCP）: `/healing` → `document.querySelectorAll('#hl-reports-table tbody tr').length ≥ 1`、`#hl-nav-count` の数字が `count` API と一致、`/healing/settings` が 200 で旧画面が出る、`document.body.textContent` に `構造化`/`tests-only`/`spec-` が **0**
コミット: `feat: 報告書一覧。/healing の入口を報告書に変え、旧画面は /healing/settings へ`

---

## G3b ─ 報告書本文（90 分）

**ALLOWED** `^(templates/healing_report\.html|static/(js/healing-reports\.js|css/healing-reports\.css)|web/routes/healing\.py)$`

- ルート `GET /healing/reports/<report_id>` → `healing_report.html`（`report_id` を `data-report-id` で body に）
- JS: `/api/healing/reports/<id>` を取得して **左 `.hl-doc`** を描く。順序と内容は画面案 v3 のとおり:
  1. `保守対応報告書` ＋ メタ行（案件 / 対応日 `created_at` の日付 / 報告: `project.report_org`（空なら省く）/ 状態バッジ）
  2. `1. 事象` … `incident_text`（無ければ `defect.message`）＋薄字 `incident_verify`。右に `incident_screenshot` があれば `<img>`（`/api/healing/reports/<id>/asset?path=` は作らず、`out_dir` 相対を `/output/` 配下の既存静的配信で出せるか **Gpre-7 の出力で確認**。出せなければ画像は G4 まで省く）
  3. `2. 原因` … `cause_text` ＋ `箇所: <code>cause_location</code>`
  4. `3. 対応` … `action_text`。空なら `直せませんでした。対応は人が記入してください。` ＋ `<textarea id="hl-action-edit">`（blur で `PATCH`）
  5. `4. 検証` … 3 枠: 修正前 `verify_before`（赤）/ 修正後 `verify_after`（ok なら緑・失敗なら赤・未実行なら灰）/ 画面仕様との照合 `spec_match`（`未照合` は灰）
  6. `<details open>` **確認が必要な点 N 件**（`attention` を `高/中/低` バッジ＋`label`＋薄字 `detail`。0 件なら `機械的に検出できる兆候はありませんでした。テストの通過は正しさを保証しません。`）
  7. `<details>` **変更内容（差分 N ファイル）** … `proposal.diff` を行頭 `+`/`-`/`@@` で色分け（`healing.css` の `.hl-diff-add/.hl-diff-del/.hl-diff-meta` と同じ見た目を `healing-reports.css` に**コピー**）。薄字 `開発者向け`
  8. `<details>` **該当箇所の根拠と、AI の説明** … `locations` を「ファイル / 根拠 / 強さ」（根拠の和訳: traceback→実行時トレース / import→import 関係 / recent-change→直近の変更 / test-name→テスト名 / selector→画面の文言 / route→URL のルート / screen→画面仕様）＋ `rationale` を引用ブロック＋薄字 `AI の自己申告です`
  9. `5. 承認` … `approvals` を `提案: AI {at}` / `承認: {who} {at}` or `—` / `PR: #{pr_number}` or `承認後に作成`
- **右 `.hl-doc-actions`（sticky）**: `status=="awaiting"` かつ `data-hl-admin=true` のときだけ操作:
  - `<textarea id="hl-report-note">`（`承認のメモ（報告書と証跡に残る）`）
  - `承認して PR を作る`（`attention_high>0` → `btn-outline-sm`、0 → `btn-primary`）
  - `差し戻す`（メモ空なら赤字 1 行 `差し戻しの指示をメモに書いてください` で送らない）
  - `却下`（`hl-btn-danger`。確認行 `本当に却下しますか？ [却下する][やめる]`。確認行は `hidden`＋`inert`）
  - 薄字 `確認が必要な点が残っているため、承認は強調していません。`（high>0 のときだけ）
  - 判断後: トースト `承認しました。PR #N を作成しました` → 3 秒後 `/healing` へ
- 1 画面構造: `.hl-doc-wrap{overflow:auto;min-height:0}`。`main.app-content` の溢れ 0

確認（8765・Playwright MCP・`awaiting` の報告書を開く）:
`document.querySelectorAll('.hl-doc h6, .hl-doc .hl-doc-h').length === 5`／`document.querySelectorAll('details').length === 3` かつ最初だけ `open`／`main#app-content` の `scrollHeight-clientHeight === 0`（1440×900）／内部語 0／「承認して PR を作る」→ トースト → `5. 承認` に PR 番号 → `gh pr close`
コミット: `feat: 報告書本文。判断は報告書の中で行い、差分と根拠は折りたたみへ`

---

## G3c ─ 印刷と設定画面の整理（40 分）

**ALLOWED** `^(templates/(healing_report_print\.html|healing\.html)|web/routes/healing\.py|static/css/healing-reports\.css)$`

- `GET /healing/reports/<report_id>/print` → `healing_report_print.html`: サイドバー・トップバー無し。**Jinja で節を直接描画**（`report` dict を渡す。Markdown 変換器は使わない）。`@page{size:A4;margin:18mm}`、`@media print{.no-print{display:none}}`。上部に `印刷 / PDF に保存`（`window.print()`）だけ
- `GET /api/healing/reports/<id>/export?format=html` → 同テンプレートを返す
- `templates/healing.html`（設定画面）: サイドバーを `partials/healing-sidebar.html`（`active='settings'`）に差し替え。旧 `hl-view-run` / `hl-view-history` セクションは `hidden` のまま残してよいが、**ナビからは外す**。既定表示を `hl-view-projects` に（`healing.js` は触らない。`data-default-view="projects"` を body に付け、`healing.js` が読まないなら G5 で対応）
- 確認: `/healing/reports/<id>/print` が 200・`window.print` が定義されている／`/healing/settings` のサイドバーが 2 項目／`grep -c '!important' static/css/healing.css` → 3（宣言 2＋コメント 1・不変）
コミット: `feat: 報告書の印刷画面。設定画面のサイドバーを報告書／設定の 2 項目に`

---

## G4 ─ 02/03 → 05 接続（90 分）

**ALLOWED** `^(web/services/healing/autorun_bridge\.py|web/routes/healing\.py|static/js/autorun-report\.js|templates/autorun-report\.html)$`
**前提**: Gpre-7 で `report.json` と `testcases.spec.meta.json` が 1 組以上ある domain（以下 `<D>`）

### 4-1 `autorun_bridge.py`（40 分）
```python
def load_failures(out_dir: Path, domain: str, *, run_id: str = "", test_ids: Sequence[str] = ()) -> list[Defect]
```
- 報告 JSON の探索順: `run_id` があれば `web.services.run_store.run_dir(out_dir, domain, run_id) / "playwright_report.json"` → 無ければ `out_dir/<domain>/qa_process/playwright_report.json` → `out_dir/<domain>/testcases/playwright_report.json`
- `tests[]` の `status != "passed"`。`test_ids` があれば `title` に含むものだけ
- **画面 ID の取り方（検査で確定）**: `title` から `re.search(r"TC-(P\d{3})-", title)` で `P001` を取る（`testcases.spec.meta.json` の `case_id` と同形。meta には `page_id`/`url` は**無い**）→ `out_dir/<domain>/report.json` の `screens[]` で `page_id` 一致を引き `url`・`title`（→ `screen_name`）を得る
- スクショ: `out_dir/<domain>/test-results/**/*.png` のうち、パスにテスト title のスラッグ（英数字・`-`）を含む**最新** 1 つ。無ければ `""`。`Defect.screenshot` には **`out_dir` 相対**を入れる
- `Defect(defect_id=hashlib.sha1(test_id).hexdigest()[:12], title=<message の先頭 80 字>, severity="high", source="autorun", test_id=<TC-ID>, message=<error 先頭 500 字>, evidence=<error 全文>, url=, screen_id=, screen_name=, test_title=<title から TC-ID を除いて strip>, screenshot=)`

### 4-2 API（20 分）
`POST /api/healing/runs/from-autorun`（管理者）body `{"project_id","domain","run_id":"","test_ids":[]}`
- `project.domain` が空なら `domain` で埋めて `save_project`
- `load_failures` が 0 件 → 400 `{"error":"失敗したテストがありません"}`
- `start_run(..., actor=actor, defects=defects)` → 202 `{"run": run_summary}`

### 4-3 AutoRun 画面のボタン（30 分）
`static/js/autorun-report.js` のテスト結果描画で、**失敗行にだけ** `この失敗の報告書を作る`（`btn-outline-sm`）。セクション見出し右に `失敗 N 件の報告書を作る`。
クリック: `/api/healing/projects` から `domain` 一致を探す → 無ければ行内に赤字 1 行 `先に「ヒーリング › 設定」でこのサイトのリポジトリを接続してください` → あれば POST → 成功でボタン文言を `下書き中…` にして `disabled`、トースト `報告書を下書き中です。数分後に「ヒーリング › 報告書」に出ます`
（`autorun-report.js` に `innerHTML` があっても**既存分は触らない**。新規コードだけ DOM 組み立て）

確認（8765）:
1. 02 のテスト 1 件をわざと壊す（`output/<D>/testcases/testcases.spec.ts` の `getByRole` の name を存在しない文言に）→ 03 を実行（既存 UI）→ `/autorun/report/<D>` の失敗行にボタン
2. 接続 `d9a116c79a98` に `PATCH {"domain":"<D>"}` → ボタン押下 → 202 → run が `awaiting_human` → `list_reports(status='awaiting')[0].title` に**画面名**が入り、`incident_screenshot` が空でない
3. 壊したテストを戻す
コミット: `feat: AutoRun の失敗から報告書を起こす（02/03 → 05）`

---

## G6 ─ URL → 製品ファイルの限局（120 分）

**ALLOWED** `^web/services/healing/(localization|orchestrator)\.py$`

- `locate(defect, *, repo, limit=5, project=None)` に `project` を任意追加。`orchestrator._localize_defects` から `project=project` を渡す
- `LocationEvidence.reason` に `selector` / `route` / `screen` を追加。既存 4 種と**同じ合算ロジック**（`_merge` 相当）に流す
- **1 欠陥あたり 10 秒**で打ち切り（`time.monotonic()`）。途中結果を返す

| reason | 抽出 | 走査 | score |
|---|---|---|---|
| `selector` | `message`+`evidence` から `getByRole\('[^']+',\s*\{\s*name:\s*'([^']+)'`・`getBy(Text|Label|Placeholder)\('([^']+)'`・`getByTestId\('([^']+)'`・`locator\('(#[\w-]+|\[data-testid=[^\]]+\])'` | `*.html *.jinja *.jinja2 *.tsx *.jsx *.vue *.py *.js *.ts`（`_is_scannable`・最大 2,000 ファイル・512KB/ファイル）。`str in content` の単純一致 | 0.6。`getByTestId`/`#id` 一致は 0.8 |
| `route` | `defect.url` の path。数値・UUID セグメントを `<var>` に | **Flask**: `*.py` の `@\w+\.(route|get|post|put|patch|delete)\(\s*["']([^"']+)["']` で path の静的セグメント一致 → 直後の `def` から次の `def` までに `render_template\(\s*["']([^"']+)` があれば `templates/<name>` も候補。**Next.js**: `app/<path>/page.(tsx|jsx)`・`pages/<path>.(tsx|jsx)`（`[x]`→`<var>`）。**Django**: `urls.py` の `path\(\s*["']([^"']+)["'],\s*(\w+)`。**Express**: `\.(get|post|put|delete)\(\s*["']([^"']+)["']` | ルート定義 0.7・辿ったテンプレート 0.85 |
| `screen` | `project.domain` があれば `out_dir` は **`Path("output")`**（認証オフ前提。テナントは `orchestrator` に `out_dir` が来ているのでそれを使う）の `report.json` から `page_id == defect.screen_id` の `buttons[]`+`headings[]` | `selector` と同じ走査を共用 | 0.5 |
- `detail` は人の言葉: `URL /healing のルート → healing_page()` / `文言「ヒーリングを開始」を含む` / `画面仕様 P001 の見出し「…」を含む`

確認:
```bash
venv/bin/python -c "
import time; from pathlib import Path; from web.services.healing import localization, types
d=types.Defect(defect_id='x',title='',message=\"TimeoutError: getByRole('button', { name: 'ヒーリングを開始' })\",url='http://127.0.0.1:8765/healing',screen_id='P001')
t=time.monotonic(); ev=localization.locate(d, repo=Path('.'), limit=5); dt=time.monotonic()-t
for e in ev: print(f'{e.score:.2f} {e.reason:9s} {e.path}  {e.detail}')
print(f'{dt:.1f}s', any(e.path=='templates/healing.html' for e in ev[:3]), any(e.path=='web/routes/healing.py' for e in ev[:3]))"
```
期待: 最終行 `<10.0s True True`
コミット: `feat: E2E 失敗の URL・セレクタ・画面仕様から製品ファイルを限局する`

---

## G7 ─ 仕様照合（60 分）

**ALLOWED** `^web/services/healing/(spec_match|orchestrator|report_doc)\.py$`

```python
@dataclass(frozen=True)
class ScreenSpec: page_id: str; title: str; url: str; headings: tuple[str,...]; buttons: tuple[str,...]; form_labels: tuple[str,...]; transitions_to: tuple[str,...]
def load_screen_spec(out_dir: Path, domain: str, page_id: str) -> ScreenSpec | None   # report.json。forms[] は {label|name} を拾う
def assess_spec(proposal, spec) -> tuple[RiskSignal, ...]                             # risk.RiskSignal を再利用
def summarize(proposal, spec, signals) -> str
```
| code | severity | 条件（`risk._parse_file_diffs` で削除行 D・追加行 A を取る） | label |
|---|---|---|---|
| `spec-element-removed` | high | 仕様の文字列 s が D のいずれかに含まれ、A のどれにも含まれない | `画面仕様にある「s」が無くなっています` |
| `spec-text-changed` | medium | s が D に含まれ、A に含まれず、A に**同じタグ名**（`<button`/`<a`/`<h\d`/`<label`）の行がある | `「s」の文言が変わっています。画面仕様は「s」` |
| `spec-transition-changed` | medium | D に `href="x"` / `action="x"`、A に `href="y"`（x≠y） | `遷移先が変わっています（x → y）` |
- `summarize`: 兆候 0 → `照合対象 N 件・不一致なし`（N = 仕様の文字列数）。1 件以上 → `不一致 N 件（要確認）`
- `orchestrator._enrich_proposal`: `project.domain` と `defect.screen_id` が両方あるときだけ `load_screen_spec` → `assess_spec` → `proposal.risks` に**追加**。`report_doc.build_maintenance_report` の `spec_match` に `summarize` の結果（無いときは `未照合`）

確認:
```bash
venv/bin/python -c "
from pathlib import Path; from web.services.healing import spec_match, types
spec=spec_match.ScreenSpec(page_id='P001',title='t',url='u',headings=(),buttons=('ヒーリングを開始',),form_labels=(),transitions_to=())
d='--- a/templates/healing.html\n+++ b/templates/healing.html\n@@ -1,1 +1,1 @@\n-<button class=\"btn-primary\">ヒーリングを開始</button>\n+<button class=\"btn-primary\">開始</button>\n'
p=types.FixProposal(defect_id='d',agent='a',status='applied',diff=d,files_changed=('templates/healing.html',))
s=spec_match.assess_spec(p,spec); print([x.code for x in s]); print(spec_match.summarize(p,spec,s))"
```
期待: `['spec-text-changed']` と `不一致 1 件（要確認）`
コミット: `feat: 修正差分を 01 の画面仕様と照合し、仕様に無い変更を報告書に出す`

---

## G5 ─ 監視（90 分）

**ALLOWED** `^(web/services/healing/(monitor|types|project_store)\.py|web/routes/healing\.py|web/__init__\.py|templates/healing\.html|static/js/healing\.js)$`
（この goal だけ `healing.js` を触ってよい: 設定表に監視列を足すため）

- `HealingProject` に末尾追加: `monitor_enabled: bool = False`・`monitor_time: str = ""`（`HH:MM`）・`monitor_last_run_on: str = ""`（`YYYY-MM-DD`）
- `monitor.py`（`scheduler.py` と同じ流儀）: `start_monitor(output_root: Path)`・`stop_monitor()`・`_loop()`（60 秒）・`_tick(output_root)`・`run_now(out_dir, project) -> HealingRun | None`
  - **due**: `monitor_enabled` かつ `now.strftime("%H:%M") >= monitor_time` かつ `monitor_last_run_on != today`
  - **実行**: spec = `out_dir/<domain>/testcases/testcases.spec.ts`（無ければ `qa_process/autorun.spec.ts`。両方無ければログして skip）→ **`run_playwright(spec_path=spec, output_dir=out_dir/<domain>/qa_process)`**（`output_dir` 必須・検査済み）→ `autorun_bridge.load_failures(out_dir, domain)` → 0 件なら `monitor_last_run_on=today` を保存してログ 1 行 → 1 件以上なら `start_run(actor="monitor", defects=…)` → `monitor_last_run_on=today`
  - **二重起動防止**: `list_run_summaries(out_dir, project_id)` に `ACTIVE_STATUSES` があれば skip
  - テナント: `output_root` 直下と `output_root/tenants/*/` を両方走査
- `web/__init__.py`: `start_scheduler()` の**直後**に `if os.environ.get("WEBSPEC2DOC_HEALING_MONITOR","1")=="1": start_monitor(OUTPUT_DIR)`
- API: `PATCH /api/healing/projects/<id>` に `monitor_enabled`（bool）・`monitor_time`（`^\d{2}:\d{2}$`）。`POST /api/healing/projects/<id>/monitor/run-now`（管理者）→ `run_now`
- 設定画面（`healing.html`+`healing.js` の接続先表）: 列を `案件 / 監視（トグル＋時刻）/ 次回 / 前回 / 修正する AI / 操作`。「次回」= `monitor_time` からの相対（`12 時間後`）、「前回」= 最新 run の `verify_before` バッジ。トグルは `PATCH`

確認（8765）:
1. `PATCH d9a116c79a98 {"domain":"<D>","monitor_enabled":true,"monitor_time":"<今から 2 分後の HH:MM>"}` → **3 分以内**に `ls -t output/.healing/runs/ | head -1` の JSON で `"actor": "monitor"`
2. `/api/healing/reports?status=awaiting` に `incident_source=="monitor"` が出る
3. `get_project` の `monitor_last_run_on` が今日。もう 1 分待っても run が増えない
コミット: `feat: 監視——毎日 02 のテストを回し、失敗したら人を待たず報告書を下書きする`

---

## G8 ─ ローカル LLM を unified diff にする（90 分）

**ALLOWED** `^web/services/healing/(agents|git_ops)\.py$`
**前提**: `curl -s http://127.0.0.1:11434/api/tags` に `qwen2.5-coder:7b`。無ければ**ユーザーに `ollama pull qwen2.5-coder:7b` を依頼して止まる**（判断ルール）

- `git_ops.apply_patch(workdir: Path, patch_text: str) -> tuple[bool, str]`: `git apply --3way --whitespace=nowarn -` に stdin。失敗は `(False, stderr 先頭 500 字)`
- `agents.py`: `OllamaAgent`/`OpenAIAgent` のプロンプト末尾を `_DIFF_FORMAT_INSTRUCTIONS`（「変更は unified diff のみを ```diff フェンスで返す。ファイル全文・説明文・JSON は返さない」）に。応答から ```diff … ``` を抽出（無ければ全体）→ `apply_patch` → 失敗なら **1 回だけ** stderr を添えて再問い合わせ → それでも失敗なら `status="failed"`・`error=stderr 先頭 300 字`。成功なら `_collect_worktree_change` で diff を取り `status="applied"`
- **JSON 形式の解析コード（`_extract_json_object` と `files[].content` の書き込み）は削除**
- 既定モデル `qwen2.5-coder:7b`。`is_available()` で `/api/tags` にモデルが無ければ `detail="ollama pull qwen2.5-coder:7b を実行してください"`

確認（デモリポジトリ `scratchpad/demo-134145`・`agent=ollama`・3 回連続）: `FixProposal.status` が 3 回とも `applied`、`error` 空、`verify_after.ok` が 2 回以上 `true`、`risks` に `code-fence-written` が 0 件
コミット: `feat: ローカル LLM の修正出力を unified diff にして JSON 破損を無くす`

---

## E. 完了の定義（全 goal 共通）

1. 受け入れを **8765 で実測**し、数値を完了報告に書く
2. `git diff --name-only | grep -vE "<ALLOWED>"` が**空**
3. 他セッションの未コミット変更は含めず、報告に「他セッションの変更 N ファイルを残したまま」と書く
4. 検証で作った PR は `gh pr close --delete-branch`。PR #194 は触らない
5. 未実行（pytest / verify-ui / ブラウザ / LLM）は「未実行」と明記

## F. 見積

| goal | 見込み |
|---|---|
| Gpre + G0 + G9 | 65 分 |
| G1 + G2 | 2.5 時間 |
| G3a + G3b + G3c | 3.2 時間 |
| G4 + G6 + G7 | 4.5 時間 |
| G5 + G8 | 3 時間 |
| **合計** | **約 14.5 時間** |

**G3c 完了時点で「pytest 起点の報告書を画面で承認して PR が出る」＝デモ可能。G5 完了で「壊れたら直る」が真になる。**
