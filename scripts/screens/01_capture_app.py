"""現行システムの全画面キャプチャ。撮れなかったものは失敗として記録する（捏造しない）。"""
from __future__ import annotations
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
OUT.mkdir(parents=True, exist_ok=True)
DOMAIN = "demomart"
RUN_ID = "20260828-143210"

# (id, 区分, 画面名, パス, 説明)
SCREENS = [
    ("S01", "入口", "ルート（アプリ本体・ダッシュボード）", "/", "起動直後。認証オフのため直接アプリ本体が開く"),
    ("S02", "入口", "システム選択ハブ", "/systems", "ドキュメント作成 / テスト活動支援 / AutoRun / CLI の入口"),
    ("S03", "入口", "CLI モード案内（System 03）", "/cli", "貼り付け用コマンド組み立てと終了コードの案内"),

    ("D01", "System 01 ドキュメント作成", "ダッシュボード", "/dashboard", "サイト一覧・実行状況の俯瞰"),
    ("D02", "System 01 ドキュメント作成", "仕様書生成", "/generate", "URL 入力・条件設定・解析実行"),
    ("D03", "System 01 ドキュメント作成", "QA品質", "/qa-quality", "品質観点の評価結果"),
    ("D04", "System 01 ドキュメント作成", "テスト観点", "/viewpoints", "観点ライブラリ（ブループリント）"),
    ("D05", "System 01 ドキュメント作成", "AutoRun", "/auto-run", "自動実行の設定と起動"),
    ("D06", "System 01 ドキュメント作成", "実行履歴", "/run-history", "過去の実行回一覧"),
    ("D07", "System 01 ドキュメント作成", "実行結果（run-result）", f"/runs/{DOMAIN}/{RUN_ID}", "実行回ハブ。成果物タブを含む"),
    ("D08", "System 01 ドキュメント作成", "トレーサビリティ・マトリクス", f"/traceability/view?domain={DOMAIN}", "要件↔画面↔テストの対応表"),
    ("D09", "System 01 ドキュメント作成", "AutoRun レポート", f"/autorun/report/{DOMAIN}", "自動実行の結果レポート"),
    ("D10", "System 01 ドキュメント作成", "利用状況（Usage）", "/usage", "API 利用量・コストの集計"),

    ("T01", "System 02 テスト活動支援", "テスト活動ホーム", "/test-activity", "12 工程の入口"),
    ("T02", "System 02 テスト活動支援", "テスト計画", "/test-plan", "ISTQB のテスト計画工程"),
    ("T03", "System 02 テスト活動支援", "テスト分析", "/test-analysis", "テスト条件の抽出"),
    ("T04", "System 02 テスト活動支援", "テスト戦略", "/test-strategy", "戦略・アプローチの定義"),
    ("T05", "System 02 テスト活動支援", "テスト設計", "/test-design", "テストケース設計"),
    ("T06", "System 02 テスト活動支援", "テスト実装", "/test-implementation", "自動化スクリプトの実装"),
    ("T07", "System 02 テスト活動支援", "テスト実行", "/test-execution", "自動実行と結果収集"),
    ("T08", "System 02 テスト活動支援", "手動実行", "/manual-execution", "手動テストの実行記録"),
    ("T09", "System 02 テスト活動支援", "欠陥分析", "/defect-analysis", "検出欠陥の分析"),
    ("T10", "System 02 テスト活動支援", "コード修正", "/code-fix", "修正提案とパッチ"),
    ("T11", "System 02 テスト活動支援", "テスト完了", "/test-completion", "完了基準の判定・完了報告"),
    ("T12", "System 02 テスト活動支援", "外部連携", "/integrations", "Jira / TestRail 等との連携"),

    ("C01", "共通", "ユーザーガイド", "/user-guide", "使い方の案内"),
    ("C02", "共通", "参考文献", "/references", "準拠規格・出典"),
    ("C03", "共通", "設定", "/settings", "設定画面（既定タブ）"),
    ("C04", "共通", "アカウント（個人設定）", "/account", "自分のプロフィール・パスワード"),
    ("C05", "共通", "ユーザー管理", "/user-management", "管理者向けユーザー/所属管理"),
    ("C06", "共通", "テナント管理", "/tenant-management", "管理者向けテナント管理"),
    ("C07", "共通", "フィードバック", "/feedback", "要望・不具合の送信"),
]

SETTINGS_TABS = [
    ("api", "API・LLM"), ("crawl", "クロール"), ("notify", "通知"),
    ("integrations", "外部連携"), ("operations", "運用"), ("data", "データ"),
    ("audit", "監査"), ("test-design", "テスト設計"),
]
for i, (tab, label) in enumerate(SETTINGS_TABS, start=1):
    SCREENS.append((f"C03-{i:02d}", "共通 / 設定タブ", f"設定 › {label}", f"/settings/{tab}", f"設定画面のタブ: {tab}"))

results: list[dict] = []


def shoot(page, sid, group, name, path, note, url=None):
    target = url or (BASE + path)
    rec = {"id": sid, "group": group, "name": name, "path": path, "note": note}
    try:
        resp = page.goto(target, wait_until="networkidle", timeout=25000)
        rec["status"] = resp.status if resp else None
        rec["final_url"] = page.url.replace(BASE, "")
        page.wait_for_timeout(900)
        f = OUT / f"{sid}.png"
        page.screenshot(path=str(f), full_page=True)
        rec["file"] = f.name
        rec["ok"] = True
        rec["title"] = page.title()
    except Exception as exc:  # noqa: BLE001
        rec["ok"] = False
        rec["error"] = f"{type(exc).__name__}: {exc}"
    results.append(rec)
    print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("status"), rec.get("error", ""))
    return rec


def shoot_state(page, sid, group, name, path, note):
    """既に開いている画面の状態をそのまま撮る（遷移しない）。"""
    rec = {"id": sid, "group": group, "name": name, "path": path, "note": note,
           "status": 200, "final_url": page.url.replace(BASE, "")}
    try:
        page.wait_for_timeout(600)
        f = OUT / f"{sid}.png"
        page.screenshot(path=str(f), full_page=True)
        rec["file"] = f.name; rec["ok"] = True; rec["title"] = page.title()
    except Exception as exc:  # noqa: BLE001
        rec["ok"] = False; rec["error"] = f"{type(exc).__name__}: {exc}"
    results.append(rec)
    print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("error", ""))
    return rec


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                              locale="ja-JP")
    page = ctx.new_page()
    page.on("dialog", lambda d: d.dismiss())

    for sid, group, name, path, note in SCREENS:
        shoot(page, sid, group, name, path, note)

    # --- 実行結果画面の成果物タブ（result-tab）を全部撮る ---
    shoot(page, "D07-tabs", "System 01 ドキュメント作成", "実行結果（タブ列挙の基点）",
          f"/runs/{DOMAIN}/{RUN_ID}", "タブ走査用の再読み込み")
    try:
        tabs = page.query_selector_all(".result-tab")
        print("result-tab count:", len(tabs))
        for i in range(len(tabs)):
            tabs = page.query_selector_all(".result-tab")
            t = tabs[i]
            label = (t.inner_text() or f"tab{i}").strip().replace("\n", " ")
            t.click()
            page.wait_for_timeout(900)
            shoot_state(page, f"D07-T{i+1:02d}", "System 01 / 実行結果タブ",
                        f"実行結果 › {label}", f"/runs/{DOMAIN}/{RUN_ID}",
                        "実行結果画面の成果物タブ")
            subs = page.query_selector_all(".result-subtab:visible")
            for j in range(len(subs)):
                subs = page.query_selector_all(".result-subtab:visible")
                if j >= len(subs):
                    break
                s = subs[j]
                slabel = (s.inner_text() or f"sub{j}").strip().replace("\n", " ")
                s.click(); page.wait_for_timeout(700)
                shoot_state(page, f"D07-T{i+1:02d}-S{j+1:02d}", "System 01 / 実行結果タブ",
                            f"実行結果 › {label} › {slabel}", f"/runs/{DOMAIN}/{RUN_ID}",
                            "成果物タブ内のサブタブ")
    except Exception as exc:  # noqa: BLE001
        results.append({"id": "D07-tabs", "group": "System 01", "name": "実行結果タブ走査",
                        "path": "-", "note": "-", "ok": False, "error": str(exc)})
        print("FAIL result tabs:", exc)

    # --- テスト観点画面のタブ（vp-tab） ---
    shoot(page, "D04-tabs", "System 01 ドキュメント作成", "テスト観点（タブ列挙の基点）",
          "/viewpoints", "タブ走査用の再読み込み")
    try:
        vt = page.query_selector_all(".vp-tab")
        print("vp-tab count:", len(vt))
        for i in range(len(vt)):
            vt = page.query_selector_all(".vp-tab")
            t = vt[i]
            label = (t.inner_text() or f"tab{i}").strip().replace("\n", " ")
            t.click(); page.wait_for_timeout(800)
            shoot_state(page, f"D04-T{i+1:02d}", "System 01 / テスト観点タブ",
                        f"テスト観点 › {label}", "/viewpoints", "観点ライブラリのタブ")
    except Exception as exc:  # noqa: BLE001
        print("FAIL vp tabs:", exc)

    # --- モーダル / オーバーレイ ---
    MODALS = [
        ("M01", "#file-preview-modal", "ファイルプレビュー（モーダル）", "/dashboard", "成果物をアプリ内で開くモーダル"),
        ("M02", "#autorun-login-modal", "AutoRun ログイン情報入力（モーダル）", "/auto-run", "認証付きサイトの資格情報入力"),
        ("M03", "#uadm-add-modal", "ユーザー新規登録（モーダル）", "/user-management", "管理者によるユーザー追加"),
        ("M04", "#tadm-add-modal", "テナント新規登録（モーダル）", "/tenant-management", "管理者によるテナント追加"),
        ("M05", "#completion-overlay", "生成完了オーバーレイ", "/generate", "解析完了時の通知"),
        ("M06", "#confirm-overlay", "確認ダイアログ", "/dashboard", "破壊的操作の確認"),
        ("M07", "#input-dialog-overlay", "入力ダイアログ", "/dashboard", "名前などの入力を求めるダイアログ"),
        ("M08", "#shortcut-overlay", "キーボードショートカット一覧", "/dashboard", "? キーで開くヘルプ"),
        ("M09", "#lightbox", "スクリーンショット拡大（ライトボックス）", "/dashboard", "証跡画像の拡大表示"),
    ]
    for sid, sel, name, path, note in MODALS:
        rec = {"id": sid, "group": "モーダル / オーバーレイ", "name": name, "path": path, "note": note}
        try:
            page.goto(BASE + path, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(800)
            shown = page.evaluate(
                """(sel) => { const el = document.querySelector(sel);
                     if (!el) return false;
                     el.classList.remove('hidden');
                     el.removeAttribute('hidden');
                     el.style.display = '';
                     return true; }""", sel)
            if not shown:
                raise RuntimeError(f"要素が見つかりません: {sel}")
            page.wait_for_timeout(500)
            f = OUT / f"{sid}.png"
            page.screenshot(path=str(f), full_page=False)
            rec.update(ok=True, file=f.name, status=200, final_url=path,
                       title=page.title())
        except Exception as exc:  # noqa: BLE001
            rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        results.append(rec)
        print(("OK  " if rec.get("ok") else "FAIL"), sid, name, rec.get("error", ""))

    browser.close()

(OUT / "manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n合計:", len(results), " 成功:", sum(1 for r in results if r.get("ok")),
      " 失敗:", sum(1 for r in results if not r.get("ok")))
