"""Final Accuracy Closure（2026-10-20）: API の有界な定数解決・観点の正規カテゴリ・System06 規則の単体テスト。"""
from __future__ import annotations

from pathlib import Path

from web.services.docverify import checks

from reverse_analysis import api_resolve


def _resolver(tmp_path: Path, files: dict[str, str]):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    loaded = api_resolve._load(tmp_path, "")
    return loaded, api_resolve._Resolver(loaded)


def _info(res, call: str, path: str = "app.js"):
    segs, method = res.call_info(call, path, {}, 0)
    return api_resolve._path_of(segs)[1], method


def test_constant_concat_template_and_chain(tmp_path):
    _, res = _resolver(tmp_path, {"config.js": "var API = '/api/v1';\nconst USERS = API + '/users';\n",
                                  "app.js": "fetch(USERS);\n"})
    assert _info(res, "fetch(USERS)") == ("/api/v1/users", "GET")
    assert _info(res, "fetch(`${API}/items/${id}`, { method: 'DELETE' })") == ("/api/v1/items/:param", "DELETE")
    assert _info(res, "fetch(API + '/orders/' + id + '/cancel', { method: 'POST' })") == ("/api/v1/orders/:param/cancel", "POST")


def test_unknown_base_is_not_guessed(tmp_path):
    _, res = _resolver(tmp_path, {"app.js": "let base = '/a';\nbase = location.pathname;\n"})
    assert _info(res, "fetch(base + '/x')")[0] is None  # 再代入される変数は解決しない
    assert _info(res, "fetch(unknownBase + '/x')")[0] is None


def test_helper_wrapper_and_method_param(tmp_path):
    src = ("function http(method, url) { var opts = { method: method }; return fetch(url, opts); }\n"
           "function post(url) { return http('POST', url); }\n")
    _, res = _resolver(tmp_path, {"app.js": src})
    assert _info(res, "post('/api/feedback')") == ("/api/feedback", "POST")
    assert _info(res, "http(m, '/api/x')") == ("/api/x", "UNKNOWN")  # 動的な method は UNKNOWN


def test_xhr_open_and_window_open(tmp_path):
    _, res = _resolver(tmp_path, {"app.js": ""})
    assert _info(res, "xhr.open('PUT', '/api/health')") == ("/api/health", "PUT")
    assert res.call_info("window.open('/help')", "app.js", {}, 0) is None


def test_unreachable_code(tmp_path):
    src = "function f() {\n  return 1;\n  fetch('/a');\n}\nif (false) {\n  fetch('/b');\n}\nfetch('/c');\n"
    files, _ = _resolver(tmp_path, {"app.js": src})
    f = files["app.js"]
    assert api_resolve.dead_reason(files, "app.js", src.index("fetch('/a')")) == "return の後"
    assert api_resolve.dead_reason(files, "app.js", src.index("fetch('/b')")) == "if (false) の中"
    assert api_resolve.dead_reason(files, "app.js", src.index("fetch('/c')")) is None
    assert f.offset(3, 2) == src.index("fetch('/a')")


def test_comments_are_masked():
    masked = api_resolve.mask_comments("a(); // fetch('/x')\n/* fetch('/y') */ b('// not');\n")
    assert "/x" not in masked and "/y" not in masked and "'// not'" in masked


def _rules(text: str) -> set[str]:
    return {f["rule"] for f in checks.candidates([{"id": "p", "location": "t", "text": text}], apply_disabled=False)}


def test_docverify_generalized_patterns():
    assert "REQ.OPEN_ENDED" in _rules("センサーは温度、湿度等を計測する。")
    assert "REQ.OPEN_ENDED" not in _rules("他の機関と情報を共有する。")
    assert "REQ.UNIVERSAL" in _rules("データは一切消失しないこと。")
    assert "REQ.UNIVERSAL" not in _rules("予約は必ずしも事前登録を必要としない。")
    assert "REQ.AND_OR" in _rules("保護者／教員に通知する。")
    assert "REQ.MEASURABILITY" in _rules("検索結果は迅速に表示する。")
    assert "REQ.MULTIPLE_REQUIREMENTS" in _rules("システムは注文を受け付け、在庫を引き当てる。")
    assert "REQ.INCOMPLETE" in _rules("最大登録台数：未定")
    assert "REQ.INCOMPLETE" not in _rules("未定義のコードが入力された場合はエラーとする。")


def _screen(texts, buttons=("保存",), fields=None):
    return {"page_id": "P001", "url": "http://x/a.html", "title": "申請", "headings": ["申請"], "buttons": list(buttons),
            "texts": list(texts), "transitions": {"to": [], "from": []},
            "forms": [{"action": "", "method": "get", "fields": fields if fields is not None else
                       [{"name": "amount", "label_text": "金額 ※", "field_type": "number", "required": True}]}]}


def _cats(screen):
    from src.generator.testcase_table import _evidence_viewpoint_rows, _ScreenContext
    return {r.category for r in _evidence_viewpoint_rows(_ScreenContext(screen), has_required_rows=False)}


def test_viewpoints_need_evidence():
    plain = _cats(_screen([], buttons=("計算",)))
    assert plain == {"required", "format"}  # 必須の印と number 型だけ。API・状態・保存・エラーの根拠が無いので作らない
    rich = _cats(_screen(["状態の流れ：下書き → 申請中 → 承認済み。", "承認は承認者のみ操作できます。",
                          "送信すると POST /api/claims に送ります。", "保存後に再読み込みしても表示されます。",
                          "金額が上限を超える場合は「上限を超えています」と表示します。", "通信に失敗したら再試行できます。"]))
    assert {"state_transition", "permission", "api", "persistence", "error", "retry"} <= rich
    assert "timeout" not in rich and "duplicate" not in rich and "empty" not in rich


def test_arrow_helper_and_local_url_variable(tmp_path):
    src = ("const req = (m, u) =>\n  fetch(u, { method: m });\n"
           "function apiPost(path) { return req('POST', BASE + path); }\n"
           "function visits(id) { var url = BASE + '/patients/' + id + '/visits'; return fetch(url); }\n"
           "function other() { var url = '/x'; return url; }\n")
    _, res = _resolver(tmp_path, {"config.js": "const BASE = '/api/v2';\n", "app.js": src})
    assert _info(res, "apiPost('/check-in')") == ("/api/v2/check-in", "POST")
    off = src.index("fetch(url)")
    segs, method = res.call_info("fetch(url)", "app.js", {}, 0, off)
    assert api_resolve._path_of(segs)[1] == "/api/v2/patients/:param/visits" and method == "GET"
