# T10-C006〜C013: エラー文言(WCAG 3.3.1)・状態表示・二重起動防止・中断回復・状態保持
# 実行: venv/bin/python tracks/T10/scripts/t10_c2_states_errors.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from t10_common import (launch, open_generate, save_json, shot,  # noqa: E402
                        set_scope, discover, MOCK)

R = {"case_group": "C2 states/errors", "obs": {}, "errors": []}


def safe(label, fn):
    try:
        return fn()
    except Exception as e:
        R["errors"].append(f"{label}: {str(e)[:200]}")
        return None


with sync_playwright() as p:
    b, page = launch(p)
    open_generate(page)

    # C006 不正URL のリアルタイム検証文言
    page.fill("#url-input", "not-a-url")
    page.wait_for_timeout(400)
    R["obs"]["invalid_url_msg"] = page.evaluate(
        "() => document.getElementById('url-input-message').textContent.trim()")
    shot(page, "c2_invalid_url.png", "#wizard-p1")

    # C007 空入力で「画面解析」押下
    page.fill("#url-input", "")
    page.click("#discover-btn")
    page.wait_for_timeout(1000)
    R["obs"]["empty_input"] = page.evaluate(
        """() => ({
          url_msg: document.getElementById('url-input-message').textContent.trim(),
          status: document.getElementById('discover-status').textContent.trim(),
          loading: document.getElementById('discover-loading').style.display !== 'none'})""")
    shot(page, "c2_empty_input.png", "#wizard-p1")

    # C008 robots 除外により 0 件
    R["obs"]["robots_zero"] = safe(
        "robots_zero", lambda: discover(page, MOCK + "/private/secret", "single", 40000))
    shot(page, "c2_robots_zero.png", "#wizard-p1")

    # C009 対象サーバ 500 応答
    open_generate(page)
    R["obs"]["server_500"] = safe(
        "server_500", lambda: discover(page, MOCK + "/500", "single", 40000))
    shot(page, "c2_server_500.png", "#wizard-p1")

    # C010 接続不能ホスト
    open_generate(page)
    R["obs"]["conn_refused"] = safe(
        "conn_refused", lambda: discover(page, "http://127.0.0.1:19987/", "single", 90000))
    shot(page, "c2_conn_refused.png", "#wizard-p1")

    # C011 発見中の状態表示・二重起動防止・中断回復
    open_generate(page)
    page.fill("#url-input", MOCK + "/")
    set_scope(page, "standard")
    page.click("#discover-btn")
    page.wait_for_timeout(1500)
    s1 = page.evaluate(
        """() => ({
          loading_visible: document.getElementById('discover-loading').style.display !== 'none',
          phase: document.getElementById('discover-phase').textContent.trim(),
          count: document.getElementById('discover-count-label').textContent.trim(),
          elapsed1: document.getElementById('discover-elapsed').textContent.trim(),
          cancel_visible: !!document.getElementById('discover-cancel-btn').offsetParent,
          btn_disabled: document.getElementById('discover-btn').disabled})""")
    page.wait_for_timeout(1600)
    s1["elapsed2"] = page.evaluate(
        "() => document.getElementById('discover-elapsed').textContent.trim()")
    s1["feed_items"] = page.evaluate(
        "() => document.getElementById('discover-live-feed').children.length")
    shot(page, "c2_discover_progress.png")
    page.evaluate("() => document.getElementById('discover-btn').click()")  # 二重押下試行
    page.wait_for_timeout(400)
    s1["second_click_still_disabled"] = page.evaluate(
        "() => document.getElementById('discover-btn').disabled")
    R["obs"]["discover_progress"] = s1
    page.click("#discover-cancel-btn")
    page.wait_for_timeout(2000)
    R["obs"]["discover_cancel"] = page.evaluate(
        """() => ({
          status: document.getElementById('discover-status').textContent.trim(),
          loading: document.getElementById('discover-loading').style.display !== 'none',
          btn_enabled: !document.getElementById('discover-btn').disabled})""")
    shot(page, "c2_discover_cancel.png", "#wizard-p1")

    # C012 実行中の状態表示（進捗バー・経過・ログ常時表示・停止可・二重実行防止）
    try:
        open_generate(page)
        discover(page, MOCK + "/about", "single")
        page.click("#p1-next-btn")
        page.wait_for_selector("#wizard-p2", state="visible")
        page.click("#submit-btn")
        page.wait_for_selector("#execution-view:not(.hidden)", state="attached")
        page.wait_for_timeout(1200)
        ex = page.evaluate(
            """() => ({
              progress_width: document.getElementById('exec-progress-bar').style.width,
              elapsed1: document.getElementById('exec-elapsed').textContent.trim(),
              log_visible: !!document.getElementById('exec-log').offsetParent,
              log_in_details: !!document.getElementById('exec-log').closest('details'),
              phase: document.getElementById('exec-phase').textContent.trim(),
              count: document.getElementById('exec-count').textContent.trim(),
              eta: document.getElementById('exec-eta').textContent.trim(),
              stop_enabled: !document.getElementById('exec-stop-btn').disabled,
              gen_panel_display: document.getElementById('gen-panel').style.display,
              submit_reachable: !!document.getElementById('submit-btn').offsetParent})""")
        page.wait_for_timeout(1500)
        ex["elapsed2"] = page.evaluate(
            "() => document.getElementById('exec-elapsed').textContent.trim()")
        shot(page, "c2_exec_running.png")
        R["obs"]["exec_running"] = ex
        page.wait_for_selector("#exec-actions:not(.hidden)", state="attached",
                               timeout=240000)
        R["obs"]["exec_done"] = page.evaluate(
            """() => ({
              title: document.getElementById('exec-title').textContent.trim(),
              log_len: document.getElementById('exec-log').textContent.length,
              log_visible: !!document.getElementById('exec-log').offsetParent,
              error_visible: !document.getElementById('exec-error').classList.contains('hidden'),
              report_btn_display: document.getElementById('btn-view-report').style.display})""")
        shot(page, "c2_exec_done.png")

        # C013 状態保持: 完了→条件設定へ戻る→解析に戻る→進む
        page.click("#exec-new-btn")
        page.wait_for_selector("#wizard-p2", state="visible")
        ret = {}
        ret["after_new"] = page.evaluate(
            """() => ({
              url_value: document.getElementById('url-input').value,
              list_items: document.getElementById('discovered-url-list').children.length,
              checked: document.querySelectorAll(
                '#discovered-url-list input[type=checkbox]:checked').length})""")
        page.click("#p2-back-btn")
        page.wait_for_selector("#wizard-p1", state="visible")
        ret["back_to_p1"] = page.evaluate(
            """() => ({
              url_value: document.getElementById('url-input').value,
              scope: document.querySelector('input[name=discover-scope]:checked').id,
              summary_visible: document.getElementById('p1-summary').style.display !== 'none'})""")
        page.click("#p1-next-btn")
        page.wait_for_selector("#wizard-p2", state="visible")
        ret["forward_again"] = page.evaluate(
            """() => ({
              checked: document.querySelectorAll(
                '#discovered-url-list input[type=checkbox]:checked').length})""")
        R["obs"]["retention"] = ret
        shot(page, "c2_retention_p2.png")

        # C014 実行の停止（回復手段）: /slow で実行し 1 秒後に停止
        page.click("#p2-back-btn")
        page.wait_for_selector("#wizard-p1", state="visible")
        discover(page, MOCK + "/slow", "single", 60000)
        page.click("#p1-next-btn")
        page.wait_for_selector("#wizard-p2", state="visible")
        page.click("#submit-btn")
        page.wait_for_selector("#execution-view:not(.hidden)", state="attached")
        page.wait_for_timeout(1000)
        page.click("#exec-stop-btn")
        R["obs"]["stop_click"] = page.evaluate(
            """() => ({
              btn_text: document.getElementById('exec-stop-btn').textContent.trim(),
              btn_disabled: document.getElementById('exec-stop-btn').disabled})""")
        page.wait_for_selector("#exec-actions:not(.hidden)", state="attached",
                               timeout=90000)
        R["obs"]["stop_done"] = page.evaluate(
            """() => ({
              title: document.getElementById('exec-title').textContent.trim(),
              message: document.getElementById('exec-message').textContent.trim(),
              log_tail: document.getElementById('exec-log').textContent.trim().slice(-160),
              new_btn_visible: !!document.getElementById('exec-new-btn').offsetParent})""")
        shot(page, "c2_exec_stopped.png")
    except Exception as e:
        R["errors"].append(f"exec-flow: {str(e)[:250]}")
        shot(page, "c2_error.png")

    save_json("c2_result.json", R)
    b.close()

print("C2 done. keys:", list(R["obs"].keys()), "errors:", R["errors"])
