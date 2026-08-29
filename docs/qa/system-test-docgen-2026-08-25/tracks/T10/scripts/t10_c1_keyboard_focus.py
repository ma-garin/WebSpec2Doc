# T10-C001〜C005: キーボード操作(WCAG 2.1.1)・フォーカス順序・フォーカス可視(WCAG 2.4.7)
# 実行: venv/bin/python tracks/T10/scripts/t10_c1_keyboard_focus.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from t10_common import launch, open_generate, save_json, shot, MOCK  # noqa: E402

R = {"case_group": "C1 keyboard/focus", "milestones": {}, "errors": []}


def active_info(page):
    return page.evaluate(
        """() => { const a = document.activeElement; if (!a) return null;
          const cs = getComputedStyle(a);
          return { id: a.id || null, tag: a.tagName, type: a.type || null,
            name: a.name || null,
            text: (a.textContent || a.value || a.placeholder || '').trim().slice(0, 48),
            inGenerate: !!a.closest('#view-generate'),
            outline: cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor,
            boxShadow: (cs.boxShadow || '').slice(0, 140) }; }""")


def tab_until(page, pred_js, max_tabs=60, shift=False):
    """条件を満たす要素にフォーカスが来るまで Tab を送る。回数(1始まり)か -1。"""
    for i in range(max_tabs):
        page.keyboard.press("Shift+Tab" if shift else "Tab")
        ok = page.evaluate(
            f"() => {{ const a = document.activeElement;"
            f" return !!a && ({pred_js})(a); }}")
        if ok:
            return i + 1
    return -1


with sync_playwright() as p:
    b, page = launch(p)
    R["milestones"]["view_reached"] = open_generate(page)

    # --- C001: タブ順序の記録（先頭30ストップ・フォーカススタイル込み） ---
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    order = []
    for i in range(30):
        page.keyboard.press("Tab")
        info = active_info(page)
        if info:
            info["step"] = i + 1
        order.append(info)
    save_json("c1_tab_order.json", order)

    # --- C002〜C004: キーボードのみで URL入力→解析→選択→実行→完了→復帰 ---
    try:
        open_generate(page)
        n = tab_until(page, "a => a.id === 'url-input'")
        R["milestones"]["reach_url_input_tabs"] = n
        page.keyboard.type(MOCK + "/")
        shot(page, "c1_focus_url_input.png", "#wizard-p1")

        # Enter キーで解析が始まるか（期待: 明示ボタンで開始。挙動を記録）
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        R["milestones"]["enter_in_url_starts_discover"] = page.evaluate(
            "() => document.getElementById('discover-loading').style.display !== 'none'")

        # 範囲ラジオへ Tab → 矢印キーで「この1画面のみ」へ変更
        n = tab_until(page, "a => a.name === 'discover-scope'")
        R["milestones"]["reach_scope_radio_tabs"] = n
        R["milestones"]["scope_focus_style"] = active_info(page)
        shot(page, "c1_focus_scope_chip.png", "#discover-scope")
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(300)
        R["milestones"]["scope_after_arrowup"] = page.evaluate(
            "() => document.querySelector('input[name=discover-scope]:checked').id")

        # Shift+Tab で「画面解析」ボタンへ → Enter で解析開始
        n = tab_until(page, "a => a.id === 'discover-btn'", shift=True)
        R["milestones"]["back_to_discover_btn_tabs"] = n
        R["milestones"]["discover_btn_focus_style"] = active_info(page)
        shot(page, "c1_focus_discover_btn.png", "#wizard-p1")
        page.keyboard.press("Enter")
        page.wait_for_selector("#p1-summary", state="visible", timeout=60000)
        R["milestones"]["discover_done_by_keyboard"] = True

        # 「条件設定へ」ボタンへ Tab → Enter
        n = tab_until(page, "a => a.id === 'p1-next-btn'")
        R["milestones"]["reach_p1_next_tabs"] = n
        R["milestones"]["p1_next_focus_style"] = active_info(page)
        shot(page, "c1_focus_p1_next.png", "#wizard-p1")
        page.keyboard.press("Enter")
        page.wait_for_selector("#wizard-p2", state="visible")
        R["milestones"]["p2_reached_by_keyboard"] = True

        # URLリスト内チェックボックスへ Tab → Space で切替
        n = tab_until(
            page,
            "a => a.type === 'checkbox' && !!a.closest('#discovered-url-list')",
            max_tabs=80)
        R["milestones"]["reach_url_checkbox_tabs"] = n
        if n > 0:
            R["milestones"]["url_checkbox_focus_style"] = active_info(page)
            shot(page, "c1_focus_url_checkbox.png", "#discovered-url-panel")
            before = page.evaluate("() => document.activeElement.checked")
            page.keyboard.press(" ")
            after = page.evaluate("() => document.activeElement.checked")
            R["milestones"]["space_toggles_checkbox"] = (before != after)
            if not after:  # 実行のため選択状態へ戻す
                page.keyboard.press(" ")

        # 「解析開始」へ Tab → Enter で実行
        n = tab_until(page, "a => a.id === 'submit-btn'", max_tabs=80)
        R["milestones"]["reach_submit_tabs"] = n
        R["milestones"]["submit_focus_style"] = active_info(page)
        shot(page, "c1_focus_submit.png", "#wizard-p2")
        page.keyboard.press("Enter")
        page.wait_for_selector("#execution-view:not(.hidden)", state="attached",
                               timeout=15000)
        R["milestones"]["execution_started_by_keyboard"] = True
        page.wait_for_selector("#exec-actions:not(.hidden)", state="attached",
                               timeout=240000)
        R["milestones"]["execution_completed"] = page.evaluate(
            "() => document.getElementById('exec-title').textContent.trim()")

        # 完了後「条件設定に戻る」へ Tab → Enter で復帰
        n = tab_until(page, "a => a.id === 'exec-new-btn'", max_tabs=80)
        R["milestones"]["reach_exec_new_tabs"] = n
        page.keyboard.press("Enter")
        page.wait_for_selector("#wizard-p2", state="visible", timeout=10000)
        R["milestones"]["keyboard_full_loop"] = True
    except Exception as e:
        R["errors"].append(str(e)[:300])
        shot(page, "c1_error.png")

    save_json("c1_result.json", R)
    b.close()

print(json.dumps := None)  # noqa: F841  (プレースホルダ回避)
print("C1 done:", {k: v for k, v in R["milestones"].items()
                   if not isinstance(v, dict)}, "errors:", R["errors"])
