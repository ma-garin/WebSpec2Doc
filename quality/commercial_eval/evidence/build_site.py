#!/usr/bin/env python3
"""評価用サイト(site/)と正解データ(expected.json)・README.md を生成する。

製品コード(src/, web/, static/js/)には依存しない・参照しない。
各ヘルパーは「HTML を書く」と同時に、その HTML から人が読み取れる正解を記録する。
実行: python3 build_site.py   (標準ライブラリのみ)
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
KEYS = ["title", "headings", "dynamic_headings", "buttons", "dynamic_buttons", "fields",
        "links", "dynamic_links", "tables", "error_messages", "deferred_error_messages",
        "api_endpoints", "must_not_appear", "unavailable",
        "external_links", "anchor_links", "hidden_fields"]
HIDE = {
    "display": 'style="display:none"',
    "hidden": "hidden",
    "aria": 'aria-hidden="true" style="display:none"',
    "class": 'class="is-hidden"',
    "visibility": 'style="visibility:hidden"',
}


def jq(s):
    return json.dumps(s, ensure_ascii=False)


def V(n):
    return "f.elements[%s].value" % jq(n)


def C(n):
    return "f.elements[%s].checked" % jq(n)


class P:
    def __init__(self, fn, title, nav=True, ext_js=False):
        self.fn, self.nav, self.ext_js = fn, nav, ext_js
        self.body, self.js, self.n = [], [], 0
        self.e = {k: [] for k in KEYS}
        self.e["title"] = title
        if nav:
            self.link_reg("index.html")

    # ---- 基本 ----
    def add(self, h):
        self.body.append(h)

    def h(self, n, t):
        self.e["headings"].append(t)
        self.add("<h%d>%s</h%d>" % (n, t, n))

    def raw(self, h):
        self.add(h)

    def p(self, t):
        self.add("<p>%s</p>" % t)

    def link_reg(self, href, dynamic=False):
        if dynamic:
            self.e["dynamic_links"].append(href)
        elif href.startswith("http"):
            self.e["external_links"].append(href)
        elif href.startswith("#"):
            self.e["anchor_links"].append(href)
        elif href not in self.e["links"]:
            self.e["links"].append(href)

    def link(self, href, text, cls="", add=True):
        self.link_reg(href)
        c = ' class="%s"' % cls if cls else ""
        h = '<a href="%s"%s>%s</a>' % (href, c, text)
        if add:
            self.add(h)
        return h

    def btn(self, text, kind="button", extra="", add=True):
        self.e["buttons"].append(text)
        h = '<button type="%s"%s>%s</button>' % (kind, " " + extra if extra else "", text)
        if add:
            self.add(h)
        return h

    def sub(self, text):
        self.e["buttons"].append(text)
        self.add('<input type="submit" value="%s">' % text)

    def ibtn(self, text):
        self.e["buttons"].append(text)
        self.add('<input type="button" value="%s">' % text)

    def err(self, text):
        self.e["error_messages"].append(text)
        self.add('<p class="error" role="alert">%s</p>' % text)

    def unavail(self, text):
        self.e["unavailable"].append(text)

    # ---- フォーム ----
    def form(self, fid, action="#", method="post", novalidate=True):
        self.add('<form id="%s" action="%s" method="%s"%s>' % (
            fid, action, method, " novalidate" if novalidate else ""))

    def endform(self):
        self.add("</form>")

    def errbox(self, fid):
        self.add('<div id="%s-errors" aria-live="polite"></div>' % fid)

    def field(self, kind, name, label, lmode="for", required=False, maxlength=None,
              minlength=None, min=None, max=None, pattern=None, options=None,
              value=None, fid=None, add=True):
        self.n += 1
        if not fid:
            if name and value:
                fid = "%s-%s" % (name, value)
            else:
                fid = name or "auto%d" % self.n
        a = 'id="%s"' % fid
        if name:
            a += ' name="%s"' % name
        if kind not in ("select", "textarea"):
            a = 'type="%s" ' % kind + a
        if value is not None:
            a += ' value="%s"' % value
        if required:
            a += " required"
        if maxlength is not None:
            a += ' maxlength="%d"' % maxlength
        if minlength is not None:
            a += ' minlength="%d"' % minlength
        if min is not None:
            a += ' min="%s"' % min
        if max is not None:
            a += ' max="%s"' % max
        if pattern is not None:
            a += ' pattern="%s"' % pattern.replace("&", "&amp;").replace('"', "&quot;")
        if lmode == "aria":
            a += ' aria-label="%s"' % label
        if kind == "select":
            ctl = "<select %s>%s</select>" % (a, "".join(
                '<option value="%s">%s</option>' % (v, t) for v, t in options))
        elif kind == "textarea":
            ctl = '<textarea %s rows="4"></textarea>' % a
        else:
            ctl = "<input %s>" % a
        if lmode == "for":
            lab = '<label for="%s">%s</label>' % (fid, label)
            h = ctl + lab if kind in ("checkbox", "radio") else lab + ctl
        elif lmode == "wrap":
            h = "<label>%s %s</label>" % (ctl, label) if kind in ("checkbox", "radio") \
                else "<label>%s %s</label>" % (label, ctl)
        else:
            h = ctl
        h = '<div class="row">%s</div>' % h if add else h
        self.e["fields"].append({
            "name": name, "type": kind, "required": bool(required),
            "maxlength": maxlength, "minlength": minlength, "min": min, "max": max,
            "pattern": pattern, "label": label if lmode != "none" else None})
        if add:
            self.add(h)
        return h

    def hidden_input(self, name, value):
        self.e["hidden_fields"].append(name)
        self.add('<input type="hidden" name="%s" value="%s">' % (name, value))

    def hidden_text_input(self, name, label):
        self.e["hidden_fields"].append(name)
        self.add('<div style="display:none"><label for="%s">%s</label><input type="text" id="%s" name="%s"></div>'
                 % (name, label, name, name))
        self.e["must_not_appear"].append(label)

    # ---- 表 ----
    def table(self, headers, rows, tbid=None):
        self.e["tables"].append({"headers": headers, "rows": len(rows)})
        th = "".join("<th>%s</th>" % x for x in headers)
        tb = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
        i = ' id="%s"' % tbid if tbid else ""
        self.add("<table><thead><tr>%s</tr></thead><tbody%s>%s</tbody></table>" % (th, i, tb))

    # ---- 非表示 ----
    def hid(self, kind, text, mode="display", level=2):
        self.e["must_not_appear"].append(text)
        inner = {"button": '<button type="button">%s</button>' % text,
                 "h": "<h%d>%s</h%d>" % (level, text, level),
                 "p": "<p>%s</p>" % text,
                 "err": '<p class="error">%s</p>' % text,
                 "sub": '<input type="submit" value="%s">' % text}[kind]
        self.add("<div %s>%s</div>" % (HIDE[mode], inner))

    def hid_raw(self, inner, texts, mode="display"):
        self.e["must_not_appear"].extend(texts)
        self.add("<div %s>%s</div>" % (HIDE[mode], inner))

    # ---- JS ----
    def script(self, js):
        self.js.append(js)

    def fetch_js(self, method, path, body='"{}"'):
        self.e["api_endpoints"].append({"method": method, "path": path})
        if method == "GET":
            return "fetch(%s)" % jq(path)
        return "fetch(%s,{method:%s,body:%s})" % (jq(path), jq(method), body)

    def load(self, method, path, fail_msg=None):
        """読み込み時に API を呼ぶ。失敗(=サーバ無し)時は fail_msg を表示する"""
        self.n += 1
        sid = "st%d" % self.n
        if fail_msg:
            self.add('<div id="%s" role="alert"></div>' % sid)
            self.e["deferred_error_messages"].append(fail_msg)
        on_fail = ('var b=document.getElementById(%s);var q=document.createElement("p");'
                   'q.className="error";q.textContent=%s;b.appendChild(q);' % (jq(sid), jq(fail_msg))
                   if fail_msg else "")
        self.script('%s.then(function(r){if(!r.ok){throw new Error("http "+r.status);}return r.json();})'
                    '.catch(function(){%s});' % (self.fetch_js(method, path), on_fail))

    def on_click(self, selector, method, path):
        self.script('document.querySelectorAll(%s).forEach(function(b){b.addEventListener("click",'
                    'function(){%s.catch(function(){});});});' % (jq(selector), self.fetch_js(method, path)))

    def dyn(self, headings=(), buttons=(), links=()):
        self.n += 1
        cid = "dyn%d" % self.n
        self.add('<div id="%s" class="dyn"></div>' % cid)
        js = ['var c=document.getElementById(%s);' % jq(cid)]
        for lv, t in headings:
            self.e["dynamic_headings"].append(t)
            js.append('var h%d=document.createElement("h%d");h%d.textContent=%s;c.appendChild(h%d);' % (lv, lv, lv, jq(t), lv))
        for t in buttons:
            self.e["dynamic_buttons"].append(t)
            js.append('var b=document.createElement("button");b.type="button";b.textContent=%s;c.appendChild(b);' % jq(t))
        for href, t in links:
            self.link_reg(href, dynamic=True)
            js.append('var a=document.createElement("a");a.href=%s;a.textContent=%s;c.appendChild(a);' % (jq(href), jq(t)))
        self.script('document.addEventListener("DOMContentLoaded",function(){%s});' % "".join(js))

    def field_error_span(self, eid):
        self.add('<span class="field-error" id="%s" aria-live="polite"></span>' % eid)

    def blur(self, fid, eid, cond, msg):
        self.e["deferred_error_messages"].append(msg)
        self.script('(function(){var el=document.getElementById(%s);var s=document.getElementById(%s);'
                    'el.addEventListener("blur",function(){var v=el.value;s.textContent=(%s)?%s:"";});})();'
                    % (jq(fid), jq(eid), cond, jq(msg)))

    def submit_js(self, fid, checks, api=None, fail=None):
        """checks: [(JS条件(fは form), メッセージ)]  api: (method, path)"""
        self.errbox(fid)
        lines = []
        for cond, msg in checks:
            self.e["deferred_error_messages"].append(msg)
            lines.append("if(%s){errs.push(%s);}" % (cond, jq(msg)))
        call = ""
        if api:
            self.e["deferred_error_messages"].append(fail)
            if api[0] == "GET":
                self.e["api_endpoints"].append({"method": "GET", "path": api[1]})
                fc = "fetch(%s+\"?\"+new URLSearchParams(new FormData(f)).toString())" % jq(api[1])
            else:
                fc = self.fetch_js(api[0], api[1], "new FormData(f)")
            call = ('if(!errs.length){%s.then(function(r){if(!r.ok){throw new Error("http "+r.status);}return r.json();})'
                    '.catch(function(){var q=document.createElement("p");q.className="error";'
                    'q.textContent=%s;box.appendChild(q);});}' % (fc, jq(fail)))
        self.script(
            '(function(){var f=document.getElementById(%s);var box=document.getElementById(%s);'
            'f.addEventListener("submit",function(ev){ev.preventDefault();var errs=[];%s'
            'box.innerHTML="";errs.forEach(function(m){var q=document.createElement("p");'
            'q.className="error";q.textContent=m;box.appendChild(q);});%s});})();'
            % (jq(fid), jq(fid + "-errors"), "".join(lines), call))

    # ---- 出力 ----
    def render(self):
        hdr = '<header class="hdr"><a href="index.html">メニュー</a></header>' if self.nav else ""
        script = ""
        if self.js:
            code = "\n".join(self.js)
            if self.ext_js:
                with open(os.path.join(SITE, "js", self.fn.replace(".html", ".js")), "w", encoding="utf-8") as fh:
                    fh.write(code + "\n")
                script = '<script src="js/%s"></script>' % self.fn.replace(".html", ".js")
            else:
                script = "<script>\n%s\n</script>" % code
        return ('<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>%s</title><link rel="stylesheet" href="css/style.css"></head>\n<body>\n%s\n<main>\n%s\n</main>\n'
                '<footer><p><small>&copy; 2026 みらい商店 (評価用サンプル)</small></p></footer>\n%s\n</body></html>\n'
                % (self.e["title"], hdr, "\n".join(self.body), script))


PREF = [("", "選択してください"), ("13", "東京都"), ("27", "大阪府"), ("01", "北海道")]
pages = []


def new(fn, title, **kw):
    p = P(fn, title, **kw)
    pages.append(p)
    return p


os.makedirs(os.path.join(SITE, "css"), exist_ok=True)
os.makedirs(os.path.join(SITE, "js"), exist_ok=True)

# ---------------- p01 会員登録 ----------------
p = new("p01.html", "会員登録 | みらい商店")
p.h(1, "会員登録")
p.btn("登録する")  # 重複1個目 (フォーム外)
p.h(2, "基本情報")
p.h(3, "ご注意")
p.p("全ての項目をご入力ください。")
p.form("reg")
p.field("text", "full_name", "氏名", required=True, maxlength=40, minlength=2)
p.field("text", "kana", "フリガナ", required=True, maxlength=60, pattern="^[ァ-ヶー　]+$")
p.field("email", "email", "メールアドレス", required=True, maxlength=100)
p.field("password", "pw", "パスワード", required=True, minlength=8, maxlength=64,
        pattern=r"^(?=.*[A-Za-z])(?=.*\d).{8,64}$")
p.field("password", "pw2", "パスワード（確認）", lmode="aria", required=True)
p.field("tel", "tel", "電話番号", maxlength=11, pattern=r"^0\d{9,10}$")
p.field("date", "birth", "生年月日", min="1900-01-01", max="2010-12-31")
p.field("select", "pref", "都道府県", required=True, options=PREF)
p.field("radio", "gender", "男性", value="m")
p.field("radio", "gender", "女性", value="f")
p.field("radio", "gender", "回答しない", value="o")
p.field("textarea", "note", "自己紹介", maxlength=200)
p.field("checkbox", "agree", "利用規約に同意する", required=True)
p.hidden_input("csrf_token", "tok-7788")
p.hid("button", "管理者として登録", "hidden")
p.submit_js("reg", [
    (V("full_name") + "===''", "氏名を入力してください"),
    (V("email") + ".indexOf('@')<0", "メールアドレスの形式が正しくありません"),
    (V("pw") + ".length<8", "パスワードは8文字以上で入力してください"),
    (V("pw") + "!==" + V("pw2"), "パスワードが一致しません"),
    ("!" + C("agree"), "利用規約への同意が必要です")],
    api=("POST", "/api/members"), fail="登録に失敗しました。時間をおいて再度お試しください")
p.btn("登録する", "submit")
p.ibtn("キャンセル")
p.endform()
p.link("p02.html", "ログインはこちら")
p.link("https://example.com/privacy", "プライバシーポリシー(外部サイト)")

# ---------------- p02 ログイン ----------------
p = new("p02.html", "ログイン | みらい商店")
p.h(1, "ログイン")
p.err("セッションの有効期限が切れました。再度ログインしてください。")
p.hid("h", "管理者ログイン", "hidden")
p.form("login")
p.field("text", "login_id", "ログインID", lmode="aria", required=True, maxlength=30)
p.field("password", "pw", "パスワード", lmode="aria", required=True, minlength=8)
p.field("checkbox", "remember", "ログイン状態を保持する")
p.hid("button", "パスワードをお忘れの方", "display")
p.submit_js("login", [
    (V("login_id") + "===''", "ログインIDを入力してください"),
    (V("pw") + "===''", "パスワードを入力してください")],
    api=("POST", "/api/auth/login"), fail="ログインに失敗しました")
p.sub("ログイン")
p.endform()
p.btn("ログイン")
p.link("p01.html", "新規会員登録")
p.link("p22.html", "会員ページへ")

# ---------------- p03 商品検索 ----------------
p = new("p03.html", "商品検索 | みらい商店", ext_js=True)
p.h(1, "商品検索")
p.btn("検索")  # 重複1個目
p.h(2, "検索条件")
p.form("search", action="p03.html", method="get", novalidate=False)
p.field("text", "keyword", "キーワード", maxlength=50)
p.field("select", "category", "カテゴリ", options=[("", "すべて"), ("pc", "PC周辺機器"), ("home", "家電")])
p.field("number", "price_min", "最低価格", min=0, max=1000000)
p.field("number", "price_max", "最高価格", min=0, max=1000000)
p.field("checkbox", "in_stock", "在庫ありのみ")
p.sub("検索")
p.ibtn("条件をクリア")
p.endform()
p.h(2, "検索結果")
p.hid("p", "検索結果は0件です", "hidden")
p.table(["商品名", "価格", "在庫"], [
    [p.link("p04.html?id=1", "ワイヤレスマウス M-200", add=False), "2,480円", "あり"],
    [p.link("p04.html?id=2", "USBハブ 4ポート", add=False), "1,980円", "あり"],
    [p.link("p04.html?id=3", "ノートPCスタンド", add=False), "3,200円", "残りわずか"]])
p.dyn(headings=[(2, "最近見た商品")], buttons=["履歴を消去"])
p.load("GET", "/api/products", "商品情報を取得できませんでした")

# ---------------- p04 商品詳細 ----------------
p = new("p04.html", "ワイヤレスマウス M-200 | みらい商店")
p.h(1, "ワイヤレスマウス M-200")
p.btn("カートに入れる")
p.h(2, "商品説明")
p.p("静音設計のワイヤレスマウスです。")
p.h(2, "仕様")
p.h(3, "サイズと重量")
p.table(["項目", "内容"], [["幅", "60mm"], ["重さ", "85g"], ["接続", "2.4GHz"]])
p.field("number", "qty", "数量", required=True, min=1, max=99)
p.hid("button", "在庫を確認", "hidden")
p.btn("カートに入れる")
p.h(2, "レビュー")
p.raw('<ul id="reviews"></ul>')
p.unavail("レビュー一覧は /api/reviews から読み込む想定でサーバが無いため取得できない")
p.load("GET", "/api/reviews")
p.dyn(headings=[(2, "関連商品")], buttons=["お気に入りに追加"])
p.link("p03.html", "検索結果に戻る")
p.link("p05.html", "カートを見る")

# ---------------- p05 カート ----------------
p = new("p05.html", "カート | みらい商店")
p.h(1, "カート")
p.err("在庫切れの商品が含まれています")
rows = []
for i, (nm, pr) in enumerate([("ワイヤレスマウス M-200", "2,480円"), ("USBハブ 4ポート", "1,980円"),
                              ("ノートPCスタンド", "3,200円")], 1):
    rows.append([nm, pr, p.field("number", "qty_%d" % i, "数量", lmode="none", min=1, max=99, add=False),
                 p.btn("削除", extra='class="del"', add=False)])
p.table(["商品名", "単価", "数量", "操作"], rows)
p.on_click("button.del", "DELETE", "/api/cart/items")
p.btn("注文へ進む")
p.link("p06.html", "注文手続きへ", cls="btn")
p.link("p03.html", "買い物を続ける")

# ---------------- p06 注文入力 ----------------
p = new("p06.html", "注文情報の入力 | みらい商店")
p.h(1, "ご注文情報の入力")
p.form("order")
p.h(2, "お届け先")
p.field("text", "recipient", "お届け先氏名", required=True, maxlength=40)
p.field("text", "zip", "郵便番号", required=True, maxlength=8, pattern=r"^\d{3}-?\d{4}$")
p.field("text", "address", "住所", required=True, maxlength=100)
p.field("tel", "phone", "電話番号", maxlength=13)
p.field("date", "delivery", "配達希望日", min="2026-10-21", max="2026-12-31")
p.h(2, "お支払い方法")
p.field("radio", "pay", "クレジットカード", value="card")
p.field("radio", "pay", "代金引換", value="cod")
p.field("radio", "pay", "銀行振込", value="bank")
p.h(3, "クレジットカード情報")
p.field("text", "card_no", "カード番号", lmode="aria", maxlength=16, pattern=r"^\d{16}$")
p.field("checkbox", "gift", "ギフト包装にする", lmode="wrap")
p.hidden_input("order_token", "ord-4421")
p.submit_js("order", [
    (V("recipient") + "===''", "お届け先氏名を入力してください"),
    ("!/^\\d{3}-?\\d{4}$/.test(" + V("zip") + ")", "郵便番号は7桁の数字で入力してください"),
    ("!f.querySelector('input[name=\"pay\"]:checked')", "お支払い方法を選択してください")],
    api=("POST", "/api/orders"), fail="注文情報を送信できませんでした")
p.sub("確認画面へ")
p.btn("戻る")
p.endform()
p.link("p05.html", "カートに戻る")

# ---------------- p07 注文確認 ----------------
p = new("p07.html", "注文内容の確認 | みらい商店")
p.h(1, "注文内容の確認")
p.h(2, "お届け先")
p.p("山田 太郎 / 〒100-0001 東京都千代田区")
p.h(2, "ご注文商品")
p.table(["商品名", "数量", "小計"], [["ワイヤレスマウス M-200", "1", "2,480円"], ["USBハブ 4ポート", "2", "3,960円"]])
p.hid("h", "デバッグ情報", "aria")
p.hid("p", "クーポンが適用されました（テスト）", "aria")
p.form("confirm")
p.submit_js("confirm", [], api=("POST", "/api/orders/confirm"), fail="注文を確定できませんでした")
p.btn("注文を確定する", "submit")
p.btn("戻る")
p.endform()
p.link("p06.html", "入力画面に戻る")
p.link("p08.html", "完了画面へ(確認用)")

# ---------------- p08 注文完了 ----------------
p = new("p08.html", "ご注文完了 | みらい商店")
p.h(1, "ご注文ありがとうございました")
p.h(2, "次のステップ")
p.p("確認メールをお送りしました。")
p.hid("h", "エラー: 決済失敗", "hidden", level=3)
p.dyn(headings=[(2, "おすすめ商品")], buttons=["もっと見る"])
p.load("GET", "/api/recommendations")
p.link("p09.html", "注文履歴を見る")
p.link("p03.html", "商品検索へ")

# ---------------- p09 注文履歴 ----------------
p = new("p09.html", "注文履歴 | みらい商店")
p.h(1, "注文履歴")
p.h(2, "絞り込み")
p.form("hist", novalidate=False)
p.field("date", "from", "開始日")
p.field("date", "to", "終了日")
p.field("select", "status", "状態", options=[("", "すべて"), ("paid", "支払済"), ("shipped", "発送済")])
p.sub("絞り込む")
p.ibtn("リセット")
p.endform()
p.h(2, "注文一覧")
p.table(["注文番号", "注文日", "金額", "状態", "操作"], [
    [str(1000 + i), "2026-10-%02d" % (i + 5), "%s円" % f, s, p.link("p07.html?order=%d" % (1000 + i), "詳細", add=False)]
    for i, (f, s) in enumerate([("2,480", "支払済"), ("5,440", "発送済"), ("1,980", "発送済"), ("3,200", "支払済")], 1)])
p.link("p10.html", "管理画面へ")

# ---------------- p10 管理ダッシュボード ----------------
p = new("p10.html", "管理ダッシュボード | みらい商店")
p.h(1, "管理ダッシュボード")
p.h(2, "本日の売上")
p.table(["指標", "値"], [["売上", "128,400円"], ["注文数", "37件"], ["新規会員", "5人"]])
p.btn("更新")
p.h(2, "アクセス解析")
p.raw('<iframe src="https://example.com/embed/analytics" title="アクセス解析" width="400" height="200"></iframe>')
p.unavail("アクセス解析の iframe(外部 https://example.com/embed/analytics) の中身は取得できない")
p.btn("更新")
p.h(2, "管理者メニュー")
p.h(3, "未処理の注文")
p.hid("h", "システム設定（非公開）", "class")
p.raw('<div id="admin-only"><p>この領域は管理者ログイン後に表示されます。</p></div>')
p.unavail("管理者ログイン後にだけ出る領域(#admin-only の中身)。/api/admin/summary はサーバが無く取得できない")
p.script('fetch("/api/admin/summary").then(function(r){if(!r.ok){throw new Error("http "+r.status);}return r.json();})'
         '.catch(function(){var q=document.createElement("p");q.className="error";q.textContent="管理者権限が必要です";'
         'document.getElementById("admin-only").appendChild(q);});')
p.e["api_endpoints"].append({"method": "GET", "path": "/api/admin/summary"})
p.e["deferred_error_messages"].append("管理者権限が必要です")
p.link("p11.html", "ユーザー管理")
p.link("p15.html", "在庫一覧")
p.link("p16.html", "レポート出力")

# ---------------- p11 ユーザー管理 ----------------
p = new("p11.html", "ユーザー管理 | みらい商店")
p.h(1, "ユーザー管理")
p.field("text", "q", "ユーザー検索", lmode="aria", maxlength=30)
p.btn("検索")
p.h(2, "ユーザー一覧")
rows = []
for i, (nm, rl) in enumerate([("佐藤 花子", "管理者"), ("鈴木 一郎", "一般"), ("高橋 次郎", "一般"),
                              ("田中 三郎", "閲覧のみ"), ("伊藤 四郎", "一般")], 1):
    rows.append([p.field("checkbox", "sel", "", lmode="none", value=str(i), fid="sel_%d" % i, add=False),
                 str(i), nm, rl, p.link("p12.html?id=%d" % i, "編集", add=False) + " " +
                 p.btn("削除", extra='class="del"', add=False)])
p.table(["選択", "ID", "氏名", "権限", "操作"], rows)
p.hid("button", "全ユーザー削除", "display")
p.on_click("button.del", "POST", "/api/users/delete")
p.dyn(buttons=["CSV出力", "一括削除"])
p.link("p10.html", "ダッシュボードへ")

# ---------------- p12 ユーザー編集 ----------------
p = new("p12.html", "ユーザー編集 | みらい商店")
p.h(1, "ユーザー編集")
p.form("useredit")
p.h(2, "基本情報")
p.field("text", "user_id", "ユーザーID", required=True, maxlength=10)
p.field("text", "name", "氏名", required=True, minlength=2, maxlength=40)
p.field("email", "email", "メールアドレス", required=True, maxlength=100)
p.field("tel", "tel", "電話番号", pattern=r"^0\d{1,4}-\d{1,4}-\d{4}$", maxlength=13)
p.field("number", "emp_no", "社員番号", required=True, min=1, max=99999)
p.h(2, "権限")
p.field("select", "role", "権限", required=True, options=[("", "選択"), ("admin", "管理者"), ("user", "一般"), ("view", "閲覧のみ")])
p.field("radio", "status", "有効", value="active")
p.field("radio", "status", "無効", value="inactive")
p.field("textarea", "memo", "備考", lmode="aria", maxlength=500)
p.hidden_input("id", "12")
p.hidden_input("version", "3")
p.submit_js("useredit", [
    (V("name") + "===''", "氏名は必須です"),
    ("!/^\\d+$/.test(" + V("emp_no") + ")", "社員番号は数字で入力してください"),
    (V("role") + "===''", "権限を選択してください")],
    api=("PUT", "/api/users"), fail="ユーザーを更新できませんでした")
p.sub("保存")
p.btn("キャンセル")
p.btn("削除")
p.endform()
p.link("p11.html", "一覧へ戻る")

# ---------------- p13 お問い合わせ ----------------
p = new("p13.html", "お問い合わせ | みらい商店")
p.h(1, "お問い合わせ")
p.err("前回の送信内容を保存できませんでした。もう一度ご入力ください。")
p.form("contact")
p.field("text", "name", "お名前", required=True, maxlength=40)
p.field("email", "email", "メールアドレス", required=True, maxlength=100)
p.field("select", "subject", "お問い合わせ種別", required=True,
        options=[("", "選択"), ("order", "ご注文について"), ("other", "その他")])
p.field("textarea", "body", "お問い合わせ内容", required=True, minlength=10, maxlength=1000)
p.hidden_text_input("website", "ウェブサイト（スパム対策用・入力しないでください）")
p.field("checkbox", "privacy", "個人情報の取り扱いに同意する", lmode="wrap", required=True)
p.submit_js("contact", [
    (V("name") + "===''", "お名前を入力してください"),
    (V("body") + ".length<10", "お問い合わせ内容は10文字以上で入力してください")],
    api=("POST", "/api/contact"), fail="お問い合わせを送信できませんでした")
p.sub("送信")
p.endform()
p.raw('<iframe src="https://example.com/map" title="店舗地図" width="300" height="200"></iframe>')
p.unavail("店舗地図の iframe(外部 https://example.com/map) の中身は取得できない")
p.link("p17.html", "よくある質問")

# ---------------- p14 設定 ----------------
p = new("p14.html", "設定 | みらい商店")
p.h(1, "設定")
p.form("settings")
p.h(2, "通知")
p.field("checkbox", "notify_mail", "メール通知を受け取る", lmode="wrap")
p.field("checkbox", "notify_push", "プッシュ通知を受け取る", lmode="wrap")
p.h(2, "表示")
p.field("radio", "theme", "ライト", value="light")
p.field("radio", "theme", "ダーク", value="dark")
p.field("number", "page_size", "1ページの表示件数", min=10, max=100)
p.field_error_span("page_size-err")
p.blur("page_size", "page_size-err", "v!==''&&(Number(v)<10||Number(v)>100)", "表示件数は10〜100の範囲で指定してください")
p.h(2, "セキュリティ")
p.field("password", "cur_pw", "現在のパスワード", required=True)
p.field("password", "new_pw", "新しいパスワード", lmode="aria", minlength=8, maxlength=64)
p.submit_js("settings", [], api=("PUT", "/api/settings"), fail="設定を保存できませんでした")
p.sub("保存")
p.btn("保存")
p.btn("キャンセル")
p.endform()
p.dyn(headings=[(2, "接続中のデバイス")])

# ---------------- p15 在庫一覧 ----------------
p = new("p15.html", "在庫一覧 | みらい商店", ext_js=True)
p.h(1, "在庫一覧")
p.h(2, "絞り込み")
p.field("select", "warehouse", "倉庫", options=[("", "すべて"), ("tokyo", "東京倉庫"), ("osaka", "大阪倉庫")])
p.field("text", "sku", "SKU", maxlength=8, pattern="^[A-Z]{3}-\\d{4}$")
p.field_error_span("sku-err")
p.blur("sku", "sku-err", "v!==''&&!/^[A-Z]{3}-\\d{4}$/.test(v)", "SKUの形式は AAA-0000 です")
p.field("number", "min_qty", "最小在庫数", min=0)
p.btn("検索")
p.h(2, "現在庫")
p.table(["SKU", "商品名", "在庫数"], [["MOU-0001", "ワイヤレスマウス M-200", "120"],
                                   ["HUB-0002", "USBハブ 4ポート", "45"], ["STD-0003", "ノートPCスタンド", "8"]])
p.h(2, "在庫履歴")
p.table(["日時", "SKU", "増減"], [], tbid="history")
p.unavail("在庫履歴の表(#history)の行は /api/stock/history から読み込む想定でサーバが無く取得できない(静的な行は0)")
p.script('fetch("/api/stock/history").then(function(r){return r.json();}).then(function(d){'
         'var tb=document.getElementById("history");d.forEach(function(x){var tr=document.createElement("tr");'
         'tr.innerHTML="<td>"+x.at+"</td><td>"+x.sku+"</td><td>"+x.diff+"</td>";tb.appendChild(tr);});}).catch(function(){});')
p.e["api_endpoints"].append({"method": "GET", "path": "/api/stock/history"})
p.hid_raw("<h3>原価一覧</h3><table><thead><tr><th>仕入先</th><th>原価</th></tr></thead>"
          "<tbody><tr><td>仕入先A</td><td>1,200円</td></tr></tbody></table>", ["原価一覧", "仕入先A"], "hidden")
p.link("p10.html", "ダッシュボードへ")

# ---------------- p16 レポート出力 ----------------
p = new("p16.html", "レポート出力 | みらい商店")
p.h(1, "レポート出力")
p.btn("出力")
p.h(2, "出力条件")
p.form("report")
p.field("date", "from", "開始日", required=True)
p.field("date", "to", "終了日", required=True)
p.field("select", "kind", "レポート種別", required=True,
        options=[("", "選択"), ("sales", "売上"), ("stock", "在庫")])
p.field("radio", "fmt", "CSV", value="csv")
p.field("radio", "fmt", "Excel", value="xlsx")
p.field("radio", "fmt", "PDF", value="pdf")
p.field("checkbox", "with_header", "見出し行を含める", lmode="wrap")
p.submit_js("report", [
    (V("from") + "===''", "開始日を入力してください"),
    (V("to") + "<" + V("from"), "終了日は開始日以降を指定してください")],
    api=("POST", "/api/reports"), fail="レポートを出力できませんでした")
p.sub("出力")
p.btn("プレビュー")
p.endform()
p.dyn(headings=[(2, "出力履歴")], buttons=["再出力"])
p.link("p10.html", "ダッシュボードへ")

# ---------------- p17 ヘルプ ----------------
p = new("p17.html", "ヘルプ・よくある質問 | みらい商店")
p.h(1, "ヘルプ・よくある質問")
p.raw('<nav><a href="#reg">会員登録について</a> / <a href="#order">ご注文について</a></nav>')
p.link_reg("#reg")
p.link_reg("#order")
p.raw('<section id="reg">')
p.h(2, "会員登録について")
p.h(3, "登録に費用はかかりますか")
p.p("無料です。")
p.h(3, "お支払いについて")
p.p("会員登録に支払いは不要です。")
p.btn("役に立った")
p.raw("</section>")
p.raw('<section id="order">')
p.h(2, "ご注文について")
p.h(3, "お支払いについて")
p.p("クレジットカード、代金引換、銀行振込をご利用いただけます。")
p.h(3, "キャンセルはできますか")
p.raw("<details><summary>発送前であればキャンセル可能です</summary><p>詳細はお問い合わせください。</p></details>")
p.btn("役に立った")
p.raw("</section>")
p.hid("h", "社内向け: 返品時の裏ルール", "hidden", level=3)
p.hid("h", "Internal FAQ", "aria")
p.dyn(buttons=["チャットで質問する"])
p.link("p13.html", "お問い合わせフォーム")
p.link("p01.html", "会員登録")
p.link("https://example.com/terms", "利用規約（外部サイト）")

# ---------------- p18 住所変更 ----------------
p = new("p18.html", "登録住所の変更 | みらい商店")
p.h(1, "登録住所の変更")
p.form("addr")
p.h(2, "ご自宅")
p.field("text", "home_zip", "郵便番号", maxlength=8, pattern=r"^\d{3}-?\d{4}$")
p.ibtn("住所を検索")
p.field("select", "home_pref", "都道府県（自宅）", lmode="aria", options=PREF)
p.field("text", "home_addr", "住所", maxlength=100)
p.field("tel", "home_tel", "電話番号", maxlength=13)
p.h(2, "勤務先")
p.field("checkbox", "same_as_home", "勤務先は自宅と同じ", lmode="wrap")
p.field("text", "work_zip", "郵便番号", maxlength=8, pattern=r"^\d{3}-?\d{4}$")
p.ibtn("住所を検索")
p.field("text", "work_addr", "住所", maxlength=100)
p.field("tel", "work_tel", "電話番号", maxlength=13)
p.field("text", None, "備考", fid="memo1", maxlength=50)
p.hidden_input("member_id", "M-0042")
p.hidden_input("mode", "update")
p.submit_js("addr", [
    ("/^\\d{3}-?\\d{4}$/.test(" + V("home_zip") + ")===false", "自宅の郵便番号は7桁の数字で入力してください"),
    (V("home_addr") + "===''", "自宅の住所を入力してください")],
    api=("PATCH", "/api/members/address"), fail="住所を変更できませんでした")
p.sub("変更を保存")
p.endform()
p.link("p14.html", "設定へ")

# ---------------- p19 クーポン ----------------
p = new("p19.html", "クーポンの利用 | みらい商店")
p.h(1, "クーポンの利用")
p.err("クーポンの有効期限が切れています")
p.hid("p", "SECRET2026 は社内用コードです", "display")
p.h(2, "クーポンコード入力")
p.form("coupon")
p.field("text", "code", "クーポンコード", required=True, minlength=8, maxlength=8, pattern="^[A-Z0-9]{8}$")
p.submit_js("coupon", [
    ("!/^[A-Z0-9]{8}$/.test(" + V("code") + ")", "クーポンコードは英大文字と数字8桁です")],
    api=("POST", "/api/coupons/apply"), fail="クーポンを適用できませんでした")
p.sub("適用")
p.btn("適用")
p.endform()
p.h(2, "利用可能なクーポン")
p.table(["コード", "割引", "期限"], [["WELCOME1", "500円引き", "2026-12-31"], ["AUTUMN10", "10%引き", "2026-11-30"]])
p.link("p05.html", "カートへ")

# ---------------- p20 404 ----------------
p = new("p20.html", "404 ページが見つかりません | みらい商店")
p.h(1, "ページが見つかりません")
p.err("お探しのページは存在しないか、移動した可能性があります。")
p.h(2, "考えられる原因")
p.raw("<ul><li>URL の入力ミス</li><li>ページの移動・削除</li></ul>")
p.hid("h", "Stack trace", "hidden", level=3)
p.btn("前のページに戻る")
p.script('document.querySelector("button").addEventListener("click",function(){history.back();});')
p.link("p03.html", "商品検索へ")
p.link("p17.html", "ヘルプ")

# ---------------- p21 アンケート ----------------
p = new("p21.html", "ご利用アンケート | みらい商店")
p.h(1, "ご利用アンケート")
p.form("survey")
p.h(2, "満足度")
for v, t in [("5", "とても満足"), ("4", "満足"), ("3", "どちらでもない"), ("2", "不満"), ("1", "とても不満")]:
    p.field("radio", "sat", t, value=v)
p.h(2, "ご利用の理由")
p.field("checkbox", "reason_price", "価格", lmode="wrap")
p.field("checkbox", "reason_speed", "配送の速さ", lmode="wrap")
p.field("checkbox", "reason_support", "サポート", lmode="wrap")
p.field("select", "age", "年代", lmode="aria", options=[("", "選択"), ("20", "20代"), ("30", "30代"), ("40", "40代")])
p.field("number", "visits", "月間の利用回数", min=0, max=31)
p.field("email", "email", "メールアドレス（任意）", maxlength=100)
p.field("textarea", "comment", "", lmode="none")
p.submit_js("survey", [("!f.querySelector('input[name=\"sat\"]:checked')", "満足度を選択してください")],
            api=("POST", "/api/surveys"), fail="回答を送信できませんでした")
p.sub("回答を送信")
p.endform()
p.dyn(headings=[(3, "所要時間：約2分")])

# ---------------- p22 マイページ ----------------
p = new("p22.html", "マイページ | みらい商店")
p.h(1, "マイページ")
p.err("ログインが必要です。ログインしてから再度アクセスしてください。")
p.h(2, "会員情報")
p.p("会員情報はログイン後に表示されます。")
p.raw('<div id="member-area"></div>')
p.unavail("ログイン後にだけ出る会員限定情報(h2「会員限定情報」とボタン「ポイントを使う」)。/api/me が成功しないと生成されない")
p.script('fetch("/api/me").then(function(r){if(!r.ok){throw new Error("http "+r.status);}return r.json();})'
         '.then(function(d){var a=document.getElementById("member-area");var h=document.createElement("h2");'
         'h.textContent="会員限定情報";a.appendChild(h);var b=document.createElement("button");b.type="button";'
         'b.textContent="ポイントを使う";a.appendChild(b);}).catch(function(){});')
p.e["api_endpoints"].append({"method": "GET", "path": "/api/me"})
p.btn("ログインする")
p.link("p02.html", "ログイン")
p.link("p01.html", "会員登録")

# ---------------- index ----------------
idx = new("index.html", "メニュー | みらい商店", nav=False)
idx.h(1, "サイトメニュー")
idx.h(2, "画面一覧")
idx.raw("<ul>%s</ul>" % "".join(
    "<li>%s</li>" % idx.link(q.fn, "%s %s" % (q.fn[:3], q.e["title"].split(" | ")[0]), add=False)
    for q in pages[:-1]))

# ---------------- 書き出し ----------------
CSS = """body{font-family:sans-serif;margin:0;padding:0 16px;line-height:1.6}
.hdr{padding:8px 0;border-bottom:1px solid #ccc}
.row{margin:8px 0}.row label{display:inline-block;min-width:11em}
.error{color:#b00020}.field-error{color:#b00020;margin-left:8px}
.is-hidden{display:none}.btn{display:inline-block;padding:4px 12px;border:1px solid #333}
table{border-collapse:collapse;margin:8px 0}th,td{border:1px solid #999;padding:4px 8px}
footer{margin-top:32px;border-top:1px solid #ccc}
"""
with open(os.path.join(SITE, "css", "style.css"), "w", encoding="utf-8") as fh:
    fh.write(CSS)
for q in pages:
    with open(os.path.join(SITE, q.fn), "w", encoding="utf-8") as fh:
        fh.write(q.render())
exp = {"pages": {q.fn: {k: q.e[k] for k in KEYS} for q in pages}}
with open(os.path.join(ROOT, "expected.json"), "w", encoding="utf-8") as fh:
    json.dump(exp, fh, ensure_ascii=False, indent=1)
    fh.write("\n")

# ---------------- README ----------------
E = exp["pages"]
content = [q for q in E if q != "index.html"]
n = len(content)


def cnt(f):
    return sum(1 for q in content if f(E[q]))


def tot(k):
    return sum(len(E[q][k]) for q in content)


def dup(e):
    for k in ("buttons", "headings"):
        if len(set(e[k])) != len(e[k]):
            return True
    labs = [f["label"] for f in e["fields"] if f["label"] and f["type"] != "radio"]
    return len(set(labs)) != len(labs)


tricky = lambda e: bool(e["must_not_appear"] or e["hidden_fields"] or dup(e) or e["dynamic_headings"]
                        or e["dynamic_buttons"] or any(f["label"] is None for f in e["fields"]))
aria = sum(1 for q in content if "aria-label" in open(os.path.join(SITE, q), encoding="utf-8").read())
rows = [
    ("紛らわしい要素を含むページ (hidden・重複・動的・ラベルなし のいずれか)", cnt(tricky)),
    ("hidden 要素 (display:none / hidden / aria-hidden / class / visibility / type=hidden) を含む",
     cnt(lambda e: e["must_not_appear"] or e["hidden_fields"])),
    ("同じ文言の重複 (ボタン・見出し・ラベル) を含む", cnt(dup)),
    ("JS が読み込み後に追加する見出し・ボタンを含む", cnt(lambda e: e["dynamic_headings"] or e["dynamic_buttons"])),
    ("ラベルなしの入力を含む", cnt(lambda e: any(f["label"] is None for f in e["fields"]))),
    ("aria-label でラベル付けした入力を含む", aria),
    ("送信するまで出ないエラー文言 (deferred) を含む", cnt(lambda e: e["deferred_error_messages"])),
    ("初期表示で見えているエラー文言を含む", cnt(lambda e: e["error_messages"])),
    ("fetch による /api/ 通信を含む", cnt(lambda e: e["api_endpoints"])),
    ("取得できない情報 (iframe・ログイン必須・API 依存) を含む", cnt(lambda e: e["unavailable"])),
    ("フォーム入力項目を含む", cnt(lambda e: e["fields"])),
    ("表を含む", cnt(lambda e: e["tables"])),
]
total = [("見えている見出し (headings)", tot("headings")), ("動的な見出し (dynamic_headings)", tot("dynamic_headings")),
         ("見えているボタン (buttons)", tot("buttons")), ("動的なボタン (dynamic_buttons)", tot("dynamic_buttons")),
         ("入力項目 (fields)", tot("fields")), ("内部リンク (links, 重複除外)", tot("links")),
         ("表 (tables)", tot("tables")), ("初期表示エラー (error_messages)", tot("error_messages")),
         ("遅延エラー (deferred_error_messages)", tot("deferred_error_messages")),
         ("API (api_endpoints)", tot("api_endpoints")), ("誤検出監視文字列 (must_not_appear)", tot("must_not_appear")),
         ("hidden 入力 (hidden_fields)", tot("hidden_fields")), ("取得不能 (unavailable)", tot("unavailable"))]
readme = """# 画面仕様・Evidence 抽出 評価データ (独立正解)

## 目的

WebSpec2Doc の「画面仕様・Evidence 抽出」(見出し・ボタン・入力項目・リンク・表・エラー文言・API・取得不能の判別)が
どれだけ正確かを測るための、**製品から独立した正解データ**。製品の出力はこのデータと突き合わせて採点する。

- measured commit: (未記入。測定時に記入)
- 測定日: (未記入)

## 構成

- `site/` : 静的サイト。コンテンツページ **n = %d** (`p01.html`〜`p%02d.html`) + `index.html` (全ページへのリンク)。
  外部 CDN・フォント不使用。JS はインラインまたは `site/js/`。サーバは無く、`/api/...` は 404 になる前提。
- `expected.json` : ページごとの正解 (`{"pages": {"p01.html": {...}}}`)。`index.html` も含む (全 %d ページ)。
- `build_site.py` : site/・expected.json・この README を再生成するスクリプト (標準ライブラリのみ)。

## 正解の作り方

- 正解は、作成者が書いた HTML/JS の内容だけから決めた。**製品コード (src/, web/, static/js/) は読んでいない・実行していない。**
- `build_site.py` の各ヘルパー呼び出しが「HTML を 1 要素書く」と同時に、その要素から人が読み取れる正解を記録する。
  (HTML と正解のずれを防ぐための仕組みであり、製品の抽出ロジックは使っていない。)
- 生成後に別手順 (標準ライブラリ html.parser) で site/ を再パースし、見出し・ボタン・入力項目の数が expected.json と一致することを確認した。

## expected.json の各キーの定義

| キー | 定義 |
|---|---|
| title | `<title>` の文字列 |
| headings | 画面に見えている h1〜h3 (非表示ラッパー内を除く)。文書順・重複はそのまま |
| dynamic_headings | 読み込み後に JS が追加する見出し |
| buttons | 見えている `<button>`・`input[type=submit/button]` の表示文言。重複は個数分。`<a class="btn">` は button ではなく link |
| dynamic_buttons | 読み込み後に JS が追加するボタン |
| fields | 見えている入力項目 (select / textarea / checkbox / radio を含む。radio は 1 個 1 エントリ)。`type=hidden` と display:none の入力は含めない。name 属性が無ければ null。required は真偽値、maxlength/minlength は整数、min/max/pattern は属性の文字列そのまま。label は `label for` / ラベルで囲む / `aria-label` のいずれかの文言、無ければ null (placeholder は使っていない) |
| links | `<a href>` の内部リンク (相対パス・クエリ付きはそのまま)。重複 href は 1 回、初出順。form の action・外部 URL・`#` アンカーは含めない |
| dynamic_links | JS が追加する内部リンク |
| external_links / anchor_links | 外部 URL / ページ内アンカー (links に含めない) |
| tables | 表ごとに `headers` (thead の th) と `rows` (tbody の tr 数、静的 HTML のみ。JS が後で足す行は数えない) |
| error_messages | 初期表示で見えているエラー文言 |
| deferred_error_messages | 送信・blur・API 失敗時に初めて見える文言 (JS 中の文字列。error_messages に出たら誤り) |
| api_endpoints | JS の `fetch` 呼び出し。path はクエリ文字列を除いたリテラル |
| must_not_appear | 非表示要素の文言 (どの種別としても抽出されたら誤検出) |
| hidden_fields | 抽出されたら誤検出になる hidden 入力の name |
| unavailable | 取得できないはずの情報の説明 (iframe の中身・ログイン必須領域・API 依存の内容) |

非表示の種類: `style="display:none"`、`hidden` 属性、`aria-hidden="true"`+display:none、CSS クラス (`css/style.css` の `.is-hidden`)、`visibility:hidden`。
いずれも非表示ラッパー `<div>` で囲んだ要素。

## カテゴリごとの件数 (コンテンツページ %d 件中)

| カテゴリ | ページ数 |
|---|---|
%s

要素の総数 (index.html を除く):

| 項目 | 件数 |
|---|---|
%s

## 限界

- 作成者 1 名。裁定 (第三者による正解の見直し) は未実施。曖昧な定義は上の表のとおり作成者が決めた。
- 日本語のみ。静的 HTML + インライン JS のみ。SPA フレームワーク、Shadow DOM、canvas、実サーバ応答は対象外。
- サイト規模は小さい (%d ページ)。要素数が少なく、率の信頼区間は広い。
- 動的要素は「読み込み時に無条件で追加されるもの」に限る。API 成功時だけ出る内容は unavailable として扱い、dynamic には入れていない。
- 画面の「見えている」判定は HTML/CSS の記述から人が決めたもので、実ブラウザでの描画確認は未実施 (未検証)。
""" % (n, n, n + 1, n,
       "\n".join("| %s | %d |" % r for r in rows),
       "\n".join("| %s | %d |" % r for r in total), n)
with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as fh:
    fh.write(readme)
print("pages", len(pages))
