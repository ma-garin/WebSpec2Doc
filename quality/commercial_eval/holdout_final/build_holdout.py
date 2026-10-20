#!/usr/bin/env python3
"""最終判定用 holdout (evidence / viewpoints) を生成する。標準ライブラリのみ。
製品コードは参照しない・実行しない。HTML を 1 要素書くと同時にヘルパが正解を記録する。"""
import json, os, collections

BASE = os.path.dirname(os.path.abspath(__file__))
BRAND = 'あおぞらポータル'
HEAD = ('<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>%s</title><link rel="stylesheet" href="css/h.css"></head>\n<body>\n')
CSS = (".gone{display:none}.error{color:#b00020}.row{margin:6px 0}.hdr{padding:8px;background:#eef}"
       "main{max-width:760px;margin:0 auto;padding:12px}table{border-collapse:collapse}"
       "td,th{border:1px solid #888;padding:4px 8px}.btn{display:inline-block;padding:4px 10px;border:1px solid #444}\n")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


class P:
    def __init__(s, fn, title, idx=False):
        s.fn = fn
        s.title = '%s | %s' % (title, BRAND)
        s.body = []
        s.n = 0
        s.e = collections.OrderedDict(
            title=s.title, headings=[], dynamic_headings=[], buttons=[], dynamic_buttons=[], fields=[],
            links=[], dynamic_links=[], tables=[], error_messages=[], deferred_error_messages=[],
            api_endpoints=[], must_not_appear=[], unavailable=[], external_links=[], anchor_links=[],
            hidden_fields=[])
        if not idx:
            s.hdr = s.a('index.html', 'メニュー')

    def w(s, *x):
        s.body.extend(x)

    def h(s, n, t):
        s.e['headings'].append(t)
        return '<h%d>%s</h%d>' % (n, t, n)

    def btn(s, t, typ='button'):
        s.e['buttons'].append(t)
        return '<button type="%s">%s</button>' % (typ, t)

    def sub(s, t):
        s.e['buttons'].append(t)
        return '<input type="submit" value="%s">' % t

    def ibtn(s, t):
        s.e['buttons'].append(t)
        return '<input type="button" value="%s">' % t

    def a(s, href, t, cls=''):
        if href.startswith('http'):
            k = 'external_links'
        elif href.startswith('#'):
            k = 'anchor_links'
        else:
            k = 'links'
        if href not in s.e[k]:
            s.e[k].append(href)
        return '<a href="%s"%s>%s</a>' % (href, (' class="%s"' % cls) if cls else '', t)

    def hin(s, name, val):
        s.e['hidden_fields'].append(name)
        return '<input type="hidden" name="%s" value="%s">' % (name, val)

    def err(s, t):
        s.e['error_messages'].append(t)
        return '<p class="error" role="alert">%s</p>' % t

    def hid(s, kind, inner, texts, summary='詳細を表示'):
        s.e['must_not_appear'].extend(texts)
        if kind == 'none':
            return '<div style="display:none">%s</div>' % inner
        if kind == 'attr':
            return '<div hidden>%s</div>' % inner
        if kind == 'aria':
            return '<div aria-hidden="true" style="display:none">%s</div>' % inner
        if kind == 'vis':
            return '<div style="visibility:hidden">%s</div>' % inner
        if kind == 'cls':
            return '<div class="gone">%s</div>' % inner
        if kind == 'det':
            return '<details><summary>%s</summary>%s</details>' % (summary, inner)
        raise ValueError(kind)

    def f(s, typ, name, label=None, mode=None, req=False, ml=None, nl=None, mn=None, mx=None, pat=None,
          opts=None, val=None, ph=None, dis=False, ro=False, row=True, fid=None, rows=None):
        s.n += 1
        fid = fid or 'f%d' % s.n
        mode = mode or ('after' if typ in ('radio', 'checkbox') else 'for')
        at = []
        if typ not in ('select', 'textarea'):
            at.append('type="%s"' % typ)
        at.append('id="%s"' % fid)
        if name:
            at.append('name="%s"' % name)
        if val is not None and typ not in ('select', 'textarea'):
            at.append('value="%s"' % val)
        if req:
            at.append('required')
        for k, v in (('maxlength', ml), ('minlength', nl), ('min', mn), ('max', mx), ('pattern', pat)):
            if v is not None:
                at.append('%s="%s"' % (k, v))
        if ph:
            at.append('placeholder="%s"' % ph)
        if dis:
            at.append('disabled')
        if ro:
            at.append('readonly')
        if mode == 'aria':
            at.append('aria-label="%s"' % label)
        a = ' '.join(at)
        if typ == 'select':
            ctl = '<select %s>%s</select>' % (a, ''.join('<option value="%s">%s</option>' % o for o in opts))
        elif typ == 'textarea':
            ctl = '<textarea %s rows="%d"></textarea>' % (a, rows or 4)
        else:
            ctl = '<input %s>' % a
        lab = label if mode in ('for', 'after', 'wrap', 'aria') else None
        s.e['fields'].append(collections.OrderedDict(
            name=name, type=typ, required=bool(req), maxlength=ml, minlength=nl, min=mn, max=mx,
            pattern=pat, label=lab))
        if mode == 'for':
            h = '<label for="%s">%s</label>%s' % (fid, label, ctl)
        elif mode == 'after':
            h = ctl + '<label for="%s">%s</label>' % (fid, label)
        elif mode == 'wrap':
            h = '<label>%s %s</label>' % (label, ctl)
        else:
            h = ctl
        return '<div class="row">%s</div>' % h if row else h

    def group(s, typ, name, legend, items, req=False):
        out = ['<fieldset><legend>%s</legend>' % legend]
        for i, (v, lab) in enumerate(items):
            out.append(s.f(typ, name, lab, req=req, val=v, fid='%s-%d' % (name, i + 1)))
        out.append('</fieldset>')
        return ''.join(out)

    def table(s, headers, rows):
        s.e['tables'].append({'headers': headers, 'rows': len(rows)})
        return ('<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (
            ''.join('<th>%s</th>' % x for x in headers),
            ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in r) for r in rows)))

    def js(s, code, dh=(), db=(), dl=(), api=(), defer=()):
        s.e['dynamic_headings'] += list(dh)
        s.e['dynamic_buttons'] += list(db)
        s.e['dynamic_links'] += list(dl)
        s.e['deferred_error_messages'] += list(defer)
        for m, path in api:
            s.e['api_endpoints'].append({'method': m, 'path': path})
        return '<script>%s</script>' % code

    def valjs(s, fid, box, checks, api, fail):
        cj = ''.join('if(%s){errs.push("%s");}' % (c, m) for c, m in checks)
        m, path = api
        code = ('(function(){var f=document.getElementById("%s");var box=document.getElementById("%s");'
                'f.addEventListener("submit",function(ev){ev.preventDefault();var errs=[];%s'
                'box.innerHTML="";errs.forEach(function(m){var q=document.createElement("p");q.className="error";'
                'q.textContent=m;box.appendChild(q);});'
                'if(!errs.length){fetch("%s",{method:"%s",body:new FormData(f)}).then(function(r){'
                'if(!r.ok){throw new Error("x");}return r.json();}).catch(function(){var q=document.createElement("p");'
                'q.className="error";q.textContent="%s";box.appendChild(q);});}});})();') % (fid, box, cj, path, m, fail)
        return s.js(code, api=[api], defer=[mm for _, mm in checks] + [fail])

    def foot(s):
        return '<footer>%s<p>電話 0120-000-000 (平日 9:00-17:00)</p></footer>' % s.h(3, 'お問い合わせ')

    def render(s):
        return HEAD % s.title + '<header class="hdr">%s</header>\n<main>\n%s\n</main>\n</body></html>\n' % (
            s.hdr if hasattr(s, 'hdr') else '', '\n'.join(s.body))


# ============================ 1. evidence ============================
def build_evidence():
    D = os.path.join(BASE, 'evidence')
    pages = []
    ERR = 'document.getElementById'

    # h01 自動車保険 見積もり
    p = P('h01.html', '自動車保険 お見積もり')
    p.w(p.h(1, '自動車保険 お見積もり'), p.btn('見積もる'), p.h(2, 'ご契約者の情報'))
    p.w('<form id="q" action="h02.html" method="post">', '<div id="q-err" aria-live="polite"></div>', p.hin('quote_token', 'tok-7781'))
    p.w(p.f('date', 'birth', '生年月日', req=True, mn='1940-01-01', mx='2008-12-31'))
    p.w(p.f('number', 'years', '運転歴(年)', req=True, mn=0, mx=60))
    p.w(p.f('select', 'car', '車種', req=True, opts=[('', '選択してください'), ('k', '軽自動車'), ('s', '小型乗用車'), ('l', '普通乗用車')]))
    p.w(p.h(2, '免許証の色'), p.group('radio', 'license', '免許証の色', [('g', 'ゴールド'), ('b', 'ブルー'), ('gr', 'グリーン')]))
    p.w(p.h(2, '特約'), p.group('checkbox', 'rider', '特約', [('law', '弁護士費用特約'), ('road', 'ロードサービス'), ('new', '車両新価特約')]))
    p.w(p.f('email', 'email', 'メールアドレス', req=True, ml=80))
    p.w(p.f('textarea', 'remarks', '備考', ml=300))
    p.w(p.hid('none', '<h2>法人契約のお客様</h2><label>法人番号<input name="corp_no"></label><button type="button">法人割引を適用</button>',
              ['法人契約のお客様', '法人番号', '法人割引を適用']))
    p.w(p.hid('attr', '<p class="error">運転歴は60年以内で入力してください</p>', ['運転歴は60年以内で入力してください']))
    p.w(p.sub('見積もる'), p.ibtn('入力をクリア'), '</form>')
    p.w('<p>%s / %s</p>' % (p.a('h02.html', '契約者情報を変更する'), p.a('https://example.com/terms', '約款を確認する')))
    p.w(p.valjs('q', 'q-err', [('f.elements["birth"].value===\'\'', '生年月日を入力してください'),
                               ('f.elements["years"].value===\'\'', '運転歴を入力してください'),
                               ('f.elements["car"].value===\'\'', '車種を選択してください'),
                               ('f.elements["email"].value.indexOf(\'@\')<0', 'メールアドレスの形式が正しくありません')],
                  ('POST', '/api/quotes'), '見積もりに失敗しました。時間をおいて再度お試しください'))
    pages.append(p)

    # h02 契約者情報の変更
    p = P('h02.html', '契約者情報の変更')
    p.w(p.h(1, '契約者情報の変更'), p.h(2, '現在の登録内容'))
    p.w('<form id="c" action="h02.html" method="post">', p.hin('contract_id', 'C-20931'), '<div id="c-err"></div>')
    p.w(p.f('text', 'holder', '契約者名', dis=True, val='青空 太郎'))
    p.w(p.f('text', 'zip', '郵便番号', req=True, ml=8, pat='^[0-9]{3}-[0-9]{4}$'))
    p.w(p.f('text', 'addr', '住所', req=True, ml=100))
    p.w(p.f('tel', 'tel', '電話番号', ml=11, nl=10, pat='^0[0-9]{9,10}$'))
    p.w(p.f('select', 'contact', '連絡方法', opts=[('mail', 'メール'), ('tel', '電話'), ('post', '郵送')]))
    p.w(p.hid('attr', '<h2>変更履歴 (管理者のみ)</h2><table><tr><td>2025-04-01</td><td>住所変更</td></tr></table>', ['変更履歴 (管理者のみ)', '住所変更']))
    p.w(p.btn('変更を保存', 'submit'), p.btn('変更を保存', 'submit'), p.btn('戻る'), '</form>')
    p.w(p.a('h01.html', '見積もりに戻る'))
    p.w(p.valjs('c', 'c-err', [('f.elements["zip"].value===\'\'', '郵便番号を入力してください'),
                               ('f.elements["addr"].value===\'\'', '住所を入力してください')],
                ('PUT', '/api/contracts/self'), '変更を保存できませんでした'))
    pages.append(p)

    # h03 学習コース検索
    p = P('h03.html', 'コース検索')
    p.w(p.h(1, '学習コース検索'), p.h(2, '検索条件'))
    p.w('<form id="s" action="h03.html" method="get">')
    p.w(p.f('text', 'keyword', None, mode='ph', ml=50, ph='キーワードを入力'))
    p.w(p.f('select', 'level', 'レベル', opts=[('', 'すべて'), ('b', '入門'), ('a', '応用')]))
    p.w(p.f('checkbox', 'free', '無料コースのみ'))
    p.w(p.sub('検索'), p.ibtn('条件をクリア'), '</form>')
    p.w(p.h(2, '検索結果'))
    p.w(p.hid('vis', '<p>該当するコースがありません</p><button type="button">条件を緩める</button>', ['該当するコースがありません', '条件を緩める']))
    p.w('<div id="c-err"></div>')
    p.w(p.table(['コース名', '受講料', '期間'], [
        [p.a('h04.html?course=101', 'Python入門'), '12,000円', '4週間'],
        [p.a('h04.html?course=102', '統計の基礎'), '無料', '2週間'],
        [p.a('h04.html?course=103', 'データ分析演習'), '24,000円', '8週間']]))
    p.w(p.foot())
    p.w(p.js('(function(){var box=document.getElementById("c-err");fetch("/api/courses").then(function(r){if(!r.ok){throw new Error("x");}return r.json();})'
             '.catch(function(){var q=document.createElement("p");q.className="error";q.textContent="コース情報を取得できませんでした";box.appendChild(q);});})();',
             api=[('GET', '/api/courses')], defer=['コース情報を取得できませんでした']))
    p.e['unavailable'].append('追加コースは /api/courses から読み込む想定でサーバが無いため取得できない')
    pages.append(p)

    # h04 学習進捗
    p = P('h04.html', '学習の進捗')
    p.w(p.h(1, '受講者の学習進捗'), p.h(2, '学習の進捗'), p.h(3, '学習の進捗'))
    p.w(p.table(['単元', '進捗', '状態'], [
        ['1. 変数と型', '100%', '完了'], ['2. 条件分岐', '80%', '学習中'],
        ['3. 繰り返し', '30%', p.a('h05.html?unit=3', '課題を提出する')], ['4. 関数', '0%', '未着手']]))
    p.w(p.btn('進捗を更新'))
    p.w(p.a('h04.html?export=csv', 'CSVを出力', 'btn'))
    p.w(p.hid('det', '<h3>2024年度の履歴</h3><p>修了証 発行済み</p>', ['2024年度の履歴', '修了証 発行済み'], summary='過去の受講履歴を表示'))
    p.w('<p>%s | %s</p>' % (p.a('h03.html', 'コース検索へ'), p.a('h06.html', '成績入力へ')))
    p.w(p.js('fetch("/api/progress").then(function(r){if(!r.ok){throw new Error("x");}return r.json();}).catch(function(){});', api=[('GET', '/api/progress')]))
    p.e['unavailable'].append('進捗率のグラフは /api/progress の応答で描画される想定で、サーバが無いため取得できない')
    pages.append(p)

    # h05 課題の提出
    p = P('h05.html', '課題の提出')
    p.w(p.h(1, '課題の提出'))
    p.w(p.err('前回の提出は期限を過ぎていたため受理されませんでした'))
    p.w('<form id="sub" action="h05.html" method="post" enctype="multipart/form-data">', p.hin('course_id', '101'), '<div id="sub-err"></div>')
    p.w(p.f('select', 'task', '課題番号', req=True, opts=[('', '選択してください'), ('1', '課題1'), ('2', '課題2'), ('3', '課題3')]))
    p.w(p.f('file', 'attachment', '提出ファイル', req=True))
    p.w(p.group('radio', 'format', '提出物の形式', [('pdf', 'PDF'), ('doc', 'Word'), ('etc', 'その他')]))
    p.w(p.f('textarea', 'comment', 'コメント', ml=500, rows=5))
    p.w(p.f('checkbox', 'selfcheck', '自己点検を済ませた', req=True))
    p.w(p.hid('aria', '<h2>採点者向けの設定</h2><p>採点者向けメモ</p><button type="button">採点を確定</button>', ['採点者向けの設定', '採点者向けメモ', '採点を確定']))
    p.w(p.sub('提出する'), p.btn('下書き保存'), '</form>')
    p.w(p.valjs('sub', 'sub-err', [('f.elements["task"].value===\'\'', '課題を選択してください'),
                                  ('f.elements["attachment"].value===\'\'', 'ファイルを選択してください'),
                                  ('!f.elements["selfcheck"].checked', '自己点検にチェックしてください')],
                ('POST', '/api/submissions'), '提出に失敗しました'))
    pages.append(p)

    # h06 成績一括入力 (表の中の入力欄・form なし)
    p = P('h06.html', '成績一括入力')
    p.w(p.h(1, '成績一括入力'), p.h(2, '採点対象'), '<p>Python入門 第3回小テスト</p>', p.h(2, '成績表'))
    rows = []
    for i, nm in enumerate(['山田', '佐藤', '鈴木'], 1):
        rows.append([nm + ' さん',
                     p.f('number', 'score_%d' % i, '%sさんの得点' % nm, mode='aria', req=True, mn=0, mx=100, row=False),
                     p.f('select', 'grade_%d' % i, '%sさんの評価' % nm, mode='aria', opts=[('a', 'A'), ('b', 'B'), ('c', 'C')], row=False),
                     p.f('text', 'memo_%d' % i, None, mode='ph', ml=60, ph='備考', row=False)])
    p.w('<div id="g-err"></div>', p.table(['受講者', '得点', '評価', '備考'], rows))
    p.w(p.btn('一括保存').replace('<button ', '<button id="bulk" '), p.btn('全員に満点を入力'))
    p.w(p.hid('cls', '<h3>採点履歴</h3><button type="button">採点を取り消す</button>', ['採点履歴', '採点を取り消す']))
    p.w(p.js('(function(){var b=document.getElementById("bulk");var box=document.getElementById("g-err");'
             'function show(m){var q=document.createElement("p");q.className="error";q.textContent=m;box.appendChild(q);}'
             'b.addEventListener("click",function(){box.innerHTML="";var ins=document.querySelectorAll("input[name^=score_]");var ok=true;'
             'for(var i=0;i<ins.length;i++){if(ins[i].value===""){ok=false;}}if(!ok){show("すべての得点を入力してください");return;}'
             'fetch("/api/grades",{method:"PUT",body:"{}"}).then(function(r){if(!r.ok){throw new Error("x");}return r.json();})'
             '.catch(function(){show("成績の保存に失敗しました");});});})();',
             api=[('PUT', '/api/grades')], defer=['すべての得点を入力してください', '成績の保存に失敗しました']))
    p.w(p.a('h04.html', '進捗に戻る'))
    pages.append(p)

    # h07 荷物追跡
    p = P('h07.html', '荷物追跡')
    p.w(p.h(1, '荷物追跡'), '<form id="trk" action="h07.html" method="get">', p.hin('carrier', 'jp'), '<div id="trk-err"></div>')
    p.w(p.f('text', 'no', '追跡番号', req=True, ml=12, nl=10, pat='^[0-9]{10,12}$'))
    p.w(p.f('checkbox', 'notify', '配達完了を通知する'))
    p.w(p.sub('追跡する'), '</form>')
    p.w(p.h(2, '追跡の見本'), p.table(['日時', '状況', '拠点'], [['10/18 09:12', '集荷', '東京'], ['10/18 21:40', '輸送中', '名古屋']]))
    p.w('<div id="timeline"></div>')
    p.w(p.a('h09.html', '配送ルートを見る'))
    p.w(p.js('(function(){var f=document.getElementById("trk");var box=document.getElementById("trk-err");var tl=document.getElementById("timeline");'
             'function show(m){var q=document.createElement("p");q.className="error";q.textContent=m;box.appendChild(q);}'
             'var h=document.createElement("h2");h.textContent="最近の追跡履歴";tl.appendChild(h);'
             'var b=document.createElement("button");b.type="button";b.textContent="履歴を再読み込み";tl.appendChild(b);'
             'var a=document.createElement("a");a.href="h08.html?from=tracking";a.textContent="集荷を依頼する";tl.appendChild(a);'
             'f.addEventListener("submit",function(ev){ev.preventDefault();box.innerHTML="";var v=f.elements["no"].value;'
             'if(v===""){show("追跡番号を入力してください");return;}if(!/^[0-9]{10,12}$/.test(v)){show("追跡番号は10〜12桁の数字で入力してください");return;}'
             'fetch("/api/tracking?no="+encodeURIComponent(v)).then(function(r){if(!r.ok){throw new Error("x");}return r.json();})'
             '.catch(function(){show("追跡情報を取得できませんでした");});});})();',
             dh=['最近の追跡履歴'], db=['履歴を再読み込み'], dl=['h08.html?from=tracking'], api=[('GET', '/api/tracking')],
             defer=['追跡番号を入力してください', '追跡番号は10〜12桁の数字で入力してください', '追跡情報を取得できませんでした']))
    pages.append(p)

    # h08 集荷依頼
    p = P('h08.html', '集荷依頼')
    p.w(p.h(1, '集荷の依頼'), p.h(2, '依頼者'))
    p.w('<form id="pk" action="h08.html" method="post">', '<div id="pk-err"></div>')
    p.w(p.f('text', 'requester', 'お名前', req=True, ml=30))
    p.w(p.f('tel', 'req_tel', '電話番号', req=True, ml=11, pat='^0[0-9]{9,10}$'))
    p.w(p.h(2, '届け先'))
    p.w(p.f('tel', 'dest_tel', '電話番号', ml=11, pat='^0[0-9]{9,10}$'))
    p.w(p.f('date', 'pickup_date', '集荷日', req=True, mn='2026-10-21', mx='2026-12-31'))
    p.w(p.group('radio', 'slot', '時間帯', [('am', '午前'), ('pm', '午後'), ('ng', '夜間')], req=True))
    p.w(p.group('checkbox', 'kind', '荷物の種類', [('fragile', '割れ物'), ('frozen', '冷凍'), ('valuable', '貴重品')]))
    p.w(p.f('number', 'count', '個数', req=True, mn=1, mx=20))
    p.w(p.f('select', 'size', 'サイズ', req=True, opts=[('', '選択してください'), ('60', '60サイズ'), ('80', '80サイズ'), ('100', '100サイズ')]))
    p.w(p.hid('attr', '<h2>法人契約の集荷</h2><p>法人コードを入力してください</p>', ['法人契約の集荷', '法人コードを入力してください']))
    p.w(p.btn('入力内容を確認'), p.sub('依頼する'), '</form>')
    p.w(p.valjs('pk', 'pk-err', [('f.elements["requester"].value===\'\'', 'お名前を入力してください'),
                                ('!f.elements["slot"].value', '時間帯を選択してください'),
                                ('f.elements["count"].value===\'\'', '個数を入力してください')],
                ('POST', '/api/pickups'), '集荷の依頼に失敗しました'))
    pages.append(p)

    # h09 配送ルート (iframe)
    p = P('h09.html', '配送ルート確認')
    p.w(p.h(1, '配送ルート確認'))
    p.w(p.f('select', 'day', '表示する日', opts=[('t', '今日'), ('y', '昨日')]))
    p.w(p.btn('地図を更新'), '<div id="rt-err"></div>')
    p.w('<iframe src="https://maps.example.com/embed/route?id=88" title="配送ルート地図" width="600" height="300"></iframe>')
    p.w(p.h(2, '配送先一覧'))
    p.w(p.table(['順番', '配送先', '到着予定'], [
        ['1', p.a('h07.html?no=1234567890', '渋谷営業所'), '10:30'], ['2', '新宿センター', '11:45'], ['3', '池袋支店', '13:10']]))
    p.w(p.js('(function(){var box=document.getElementById("rt-err");fetch("/api/routes").then(function(r){if(!r.ok){throw new Error("x");}return r.json();})'
             '.catch(function(){var q=document.createElement("p");q.className="error";q.textContent="経路を取得できませんでした";box.appendChild(q);});})();',
             api=[('GET', '/api/routes')], defer=['経路を取得できませんでした']))
    p.e['unavailable'].append('iframe 内の地図 (外部ドメイン maps.example.com) の内容は取得できない')
    pages.append(p)

    # h10 転入届
    p = P('h10.html', '転入届の事前申請')
    p.w(p.h(1, '転入届の事前申請'), '<p>申請は窓口の受付時間内に処理されます。</p>')
    p.w('<form id="mv" action="h11.html" method="post">', p.hin('application_type', 'move_in'), p.hin('csrf', 'x91'), '<div id="mv-err"></div>')
    p.w(p.h(2, '申請者'))
    p.w(p.f('text', 'full_name', '氏名', req=True, ml=40, nl=2))
    p.w(p.f('text', 'kana', 'フリガナ', req=True, ml=60, pat='^[ぁ-んー　]+$'))
    p.w(p.f('date', 'birth', '生年月日', req=True, mx='2026-10-20'))
    p.w(p.h(2, '住所'))
    p.w(p.f('text', 'zip', '新住所の郵便番号', req=True, ml=7, nl=7, pat='^[0-9]{7}$'))
    p.w(p.f('text', 'new_addr', '新住所', req=True, ml=100))
    p.w(p.f('text', 'old_addr', '旧住所', req=True, ml=100))
    p.w(p.f('date', 'move_date', '転入予定日', req=True, mn='2026-10-21'))
    p.w(p.f('number', 'members', '同居人数', mn=0, mx=10))
    p.w(p.f('select', 'mynumber', 'マイナンバーカード', req=True, opts=[('', '選択してください'), ('y', '持っている'), ('n', '持っていない')]))
    p.w(p.f('checkbox', 'confirm', '内容に相違ありません', req=True))
    p.w(p.hid('aria', '<p>窓口職員用: 受付印</p>', ['窓口職員用: 受付印']))
    p.w(p.sub('申請する'), p.btn('一時保存'), p.sub('申請する'), '</form>')
    p.w(p.a('h11.html', '申請状況を確認する'))
    p.w(p.valjs('mv', 'mv-err', [('f.elements["full_name"].value===\'\'', '氏名を入力してください'),
                                ('!/^[0-9]{7}$/.test(f.elements["zip"].value)', '郵便番号は7桁の数字で入力してください'),
                                ('f.elements["new_addr"].value===\'\'', '新住所を入力してください'),
                                ('f.elements["move_date"].value===\'\'', '転入予定日を入力してください'),
                                ('!f.elements["confirm"].checked', '内容の確認にチェックしてください')],
                ('POST', '/api/applications/move-in'), '申請できませんでした'))
    pages.append(p)

    # h11 申請状況
    p = P('h11.html', '申請状況の確認')
    p.w(p.h(1, '申請状況の確認'))
    p.w(p.err('一部の申請の状況を表示できません'))
    p.w('<form id="st" action="h11.html" method="get">', p.h(2, '受付番号で探す'))
    p.w(p.f('text', 'receipt', '受付番号', req=True, ml=9, pat='^MV-[0-9]{6}$', fid='receipt'))
    p.w(p.sub('照会'), '</form>')
    p.w(p.h(2, '直近の申請'))
    p.w(p.f('text', 'last_no', '直近の受付番号', dis=True, val='MV-004512'))
    p.w(p.f('select', 'last_type', '申請種別', dis=True, opts=[('mv', '転入届')]))
    p.w(p.f('text', 'last_name', '申請者名', ro=True, val='青空 太郎'))
    p.w(p.h(2, '申請履歴'))
    p.w(p.table(['受付番号', '種別', '状態'], [
        [p.a('h12.html?id=MV-004512', 'MV-004512'), '転入届', '受付済み'], ['MV-004098', '転出届', '完了']]))
    p.w('<div id="more"></div>', '<div id="st-err"></div>')
    p.w(p.js('(function(){var m=document.getElementById("more");var box=document.getElementById("st-err");'
             'var a=document.createElement("a");a.href="h10.html?resubmit=1";a.textContent="再申請する";m.appendChild(a);'
             'var b=document.createElement("button");b.type="button";b.textContent="状況を更新";m.appendChild(b);'
             'var r=document.getElementById("receipt");r.addEventListener("blur",function(){box.innerHTML="";'
             'if(r.value!==""&&!/^MV-[0-9]{6}$/.test(r.value)){var q=document.createElement("p");q.className="error";q.textContent="受付番号の形式が正しくありません";box.appendChild(q);}});'
             'fetch("/api/applications").then(function(r){if(!r.ok){throw new Error("x");}return r.json();}).catch(function(){});})();',
             db=['状況を更新'], dl=['h10.html?resubmit=1'], api=[('GET', '/api/applications')], defer=['受付番号の形式が正しくありません']))
    p.e['unavailable'].append('申請履歴の続きは /api/applications から読み込む想定でサーバが無いため取得できない')
    pages.append(p)

    # h12 住民票の写し請求
    p = P('h12.html', '住民票の写しの請求')
    p.w(p.h(1, '住民票の写しの請求'), p.h(2, '請求内容'), p.h(2, '請求内容'))
    p.w('<form id="rq" action="h12.html" method="post">', '<div id="rq-err"></div>')
    p.w(p.group('radio', 'claimant', '請求者', [('self', '本人'), ('family', '同一世帯の代理人'), ('other', 'その他の代理人')], req=True))
    p.w(p.f('number', 'copies', '請求通数', mode='aria', req=True, mn=1, mx=10))
    p.w(p.f('text', 'requester', '請求者の氏名', mode='aria', req=True, ml=40))
    p.w(p.f('checkbox', 'honseki', '本籍を記載する'))
    p.w(p.f('select', 'receive', '受取方法', req=True, opts=[('', '選択してください'), ('counter', '窓口'), ('post', '郵送')]))
    p.w('<p>手数料は1通300円です。</p>')
    p.w(p.hid('cls', '<label>郵送先住所を入力<input name="post_addr"></label>', ['郵送先住所を入力']))
    p.w(p.hid('aria', '<p>本人確認書類のアップロード</p>', ['本人確認書類のアップロード']))
    p.w(p.sub('請求する'), p.btn('キャンセル'), p.btn('キャンセル'), '</form>')
    p.w(p.valjs('rq', 'rq-err', [('!f.elements["claimant"].value', '請求者を選択してください'),
                                ('f.elements["copies"].value===\'\'', '請求通数を入力してください'),
                                ('f.elements["receive"].value===\'\'', '受取方法を選択してください')],
                ('POST', '/api/certificates'), '請求に失敗しました'))
    pages.append(p)

    # h13 請求書一覧 (表の中のチェックボックス・form なし)
    p = P('h13.html', '請求書一覧')
    p.w(p.h(1, '請求書一覧'), p.h(2, '絞り込み'))
    p.w('<form id="flt" action="h13.html" method="get">')
    p.w(p.f('date', 'from', '開始日'), p.f('date', 'to', '終了日'))
    p.w(p.f('select', 'status', '状態', opts=[('', 'すべて'), ('paid', '支払い済み'), ('unpaid', '未払い')]))
    p.w(p.sub('絞り込み'), '</form>')
    p.w(p.h(2, '請求書'))
    rows = []
    for no, amt, stt in [('INV-2610', '48,000円', '未払い'), ('INV-2609', '48,000円', '支払い済み'), ('INV-2608', '36,000円', '支払い済み')]:
        rows.append([p.f('checkbox', 'sel', '選択 ' + no, mode='aria', val=no, row=False), no, amt, stt,
                     p.a('h15.html?inv=' + no, '詳細') + ' ' + p.btn('再発行')])
    p.w(p.table(['選択', '請求書番号', '金額', '状態', '操作'], rows))
    p.w(p.btn('選択した請求書をまとめて送付').replace('<button ', '<button id="send" '), p.btn('下書きを削除').replace('<button ', '<button id="del" '))
    p.w(p.hid('vis', '<button type="button">督促メールを送信</button><p>督促対象: 1件</p>', ['督促メールを送信', '督促対象: 1件']))
    p.w('<div id="dyn"></div>', '<div id="inv-err"></div>')
    p.w(p.js('(function(){var d=document.getElementById("dyn");var box=document.getElementById("inv-err");'
             'function show(m){var q=document.createElement("p");q.className="error";q.textContent=m;box.appendChild(q);}'
             'var h=document.createElement("h3");h.textContent="未払いの合計";d.appendChild(h);'
             'var b=document.createElement("button");b.type="button";b.textContent="未払いのみ表示";d.appendChild(b);'
             'document.getElementById("send").addEventListener("click",function(){box.innerHTML="";'
             'if(document.querySelectorAll("input[name=sel]:checked").length===0){show("送付する請求書を選択してください");}});'
             'document.getElementById("del").addEventListener("click",function(){box.innerHTML="";'
             'fetch("/api/invoices/drafts",{method:"DELETE"}).then(function(r){if(!r.ok){throw new Error("x");}}).catch(function(){show("下書きを削除できませんでした");});});})();',
             dh=['未払いの合計'], db=['未払いのみ表示'], api=[('DELETE', '/api/invoices/drafts')],
             defer=['送付する請求書を選択してください', '下書きを削除できませんでした']))
    pages.append(p)

    # h14 プラン変更
    p = P('h14.html', 'プラン変更')
    p.w(p.h(1, 'プラン変更'), p.h(2, 'プランを選択'), p.h(2, 'プランを選択'))
    p.w('<form id="pl" action="h14.html" method="post">', p.hin('current_plan', 'standard'), '<div id="pl-err"></div>')
    p.w(p.group('radio', 'plan', 'プラン', [('free', 'フリー (0円)'), ('std', 'スタンダード (3,000円)'), ('pre', 'プレミアム (9,000円)')], req=True))
    p.w(p.f('select', 'cycle', '請求サイクル', opts=[('m', '月払い'), ('y', '年払い')]))
    p.w(p.f('text', 'coupon', None, mode='ph', ml=8, pat='^[A-Z0-9]{8}$', ph='クーポンコード'))
    p.w(p.f('checkbox', 'agree', 'データ保持の注意事項を確認した', req=True))
    p.w('<div id="calc"></div>')
    p.w(p.hid('none', '<h2>解約手続き</h2><button type="button">解約する</button>', ['解約手続き', '解約する']))
    p.w(p.sub('プランを変更する'), '</form>', p.a('h15.html', '支払い方法を登録する'))
    code = p.valjs('pl', 'pl-err', [('!f.elements["plan"].value', 'プランを選択してください'),
                                   ('!f.elements["agree"].checked', '確認事項に同意してください'),
                                   ('f.elements["coupon"].value!==""&&!/^[A-Z0-9]{8}$/.test(f.elements["coupon"].value)', 'クーポンコードの形式が正しくありません')],
                   ('PUT', '/api/subscription'), 'プランの変更に失敗しました')
    p.w(code)
    p.w(p.js('(function(){var c=document.getElementById("calc");var h=document.createElement("h3");h.textContent="変更後の月額の目安";c.appendChild(h);'
             'var b=document.createElement("button");b.type="button";b.textContent="料金を再計算";c.appendChild(b);})();',
             dh=['変更後の月額の目安'], db=['料金を再計算']))
    pages.append(p)

    # h15 支払い方法
    p = P('h15.html', '支払い方法の登録')
    p.w(p.h(1, '支払い方法の登録'))
    p.w('<form id="pm" action="h15.html" method="post">', p.hin('pay_token', 'pt-55'), '<div id="pm-err"></div>')
    p.w(p.f('text', 'card_no', 'カード番号', req=True, ml=16, nl=16, pat='^[0-9]{16}$'))
    p.w(p.f('text', 'card_name', 'カード名義', req=True, ml=40))
    p.w(p.f('month', 'expiry', '有効期限', req=True, mn='2026-10', mx='2036-12'))
    p.w(p.f('password', 'cvc', 'セキュリティコード', req=True, ml=4, nl=3, pat='^[0-9]{3,4}$'))
    p.w(p.group('radio', 'bill_to', '請求書の送付先', [('reg', '登録メール'), ('alt', '別のメール')]))
    p.w(p.f('email', 'alt_mail', '別の送付先メール', dis=True, ml=80))
    p.w(p.f('checkbox', 'default', 'この支払い方法を既定にする'))
    p.w(p.hid('attr', '<p>テスト決済モード</p>', ['テスト決済モード']))
    p.w(p.sub('登録する'), '</form>')
    p.w('<p>%s / %s</p>' % (p.a('https://example.com/security', 'セキュリティについて'), p.a('h14.html', 'プラン変更へ')))
    p.w(p.valjs('pm', 'pm-err', [('!/^[0-9]{16}$/.test(f.elements["card_no"].value)', 'カード番号は16桁の数字で入力してください'),
                                ('f.elements["card_name"].value===\'\'', 'カード名義を入力してください'),
                                ('!/^[0-9]{3,4}$/.test(f.elements["cvc"].value)', 'セキュリティコードが正しくありません')],
                ('POST', '/api/payment-methods'), 'カードを登録できませんでした'))
    pages.append(p)

    # h16 利用量レポート
    p = P('h16.html', '利用量レポート')
    p.w(p.h(1, '利用量レポート'))
    p.w('<form id="us" action="h16.html" method="get">', '<div id="us-err"></div>')
    p.w(p.f('date', 'from', '集計開始日', req=True), p.f('date', 'to', '集計終了日', req=True))
    p.w(p.f('select', 'unit', '集計単位', opts=[('d', '日'), ('w', '週'), ('m', '月')]))
    p.w(p.f('number', 'limit', 'API 呼び出しの上限', mn=0, mx=100000))
    p.w(p.f('checkbox', 'alert', '超過時に通知する'))
    p.w(p.sub('表示'), p.btn('CSV出力'), '</form>')
    p.w(p.a('h16.html?csv=1', 'CSV出力', 'btn'))
    p.w(p.h(2, '利用量'))
    p.w('<canvas id="chart" width="600" height="240">グラフを表示できません</canvas>')
    p.w(p.table(['日付', 'API呼び出し', 'ストレージ(GB)'], [['10/18', '12,400', '31.2'], ['10/19', '15,010', '31.3'], ['10/20', '9,870', '31.3']]))
    p.w(p.hid('aria', '<h2>内部監査用の集計</h2><p>監査ログ 3件</p>', ['内部監査用の集計', '監査ログ 3件']))
    p.w(p.valjs('us', 'us-err', [('f.elements["from"].value===\'\'||f.elements["to"].value===\'\'', '集計期間を入力してください'),
                                ('f.elements["from"].value>f.elements["to"].value', '集計期間が正しくありません')],
                ('GET', '/api/usage'), '利用量を取得できませんでした').replace('body:new FormData(f)', 'body:null'))
    p.e['unavailable'].append('グラフは canvas 描画で、データは /api/usage の応答に依存するため取得できない')
    pages.append(p)

    # h17 管理コンソール (ログイン必須)
    p = P('h17.html', '管理コンソール')
    p.w(p.h(1, '管理コンソール'), '<p>このページはログインが必要です。</p>')
    p.w('<form id="ad" action="h17.html" method="post">', '<div id="ad-err"></div>')
    p.w(p.f('text', 'admin_id', '管理者ID', req=True, ml=20))
    p.w(p.f('password', 'admin_pw', 'パスワード', req=True, nl=8))
    p.w(p.sub('ログイン'), '</form>')
    p.w(p.hid('attr', '<h2>ようこそ、管理者さん</h2><p>契約数 1,204件</p>', ['ようこそ、管理者さん', '契約数 1,204件']))
    p.w(p.a('h13.html', '請求書一覧へ'))
    p.w(p.valjs('ad', 'ad-err', [('f.elements["admin_id"].value===\'\'', '管理者IDを入力してください'),
                                ('f.elements["admin_pw"].value.length<8', 'パスワードは8文字以上で入力してください')],
                ('POST', '/api/admin/login'), 'ログインに失敗しました'))
    p.e['unavailable'].append('ログイン後の管理領域 (契約数・設定) の内容はログインが必要なため取得できない')
    pages.append(p)

    # index
    ix = P('index.html', 'メニュー', idx=True)
    ix.w(ix.h(1, 'ホールドアウト画面一覧'), ix.h(2, '画面一覧'), '<ul>')
    for q in pages:
        ix.w('<li>%s</li>' % ix.a(q.fn, q.title.split(' | ')[0]))
    ix.w('</ul>')
    allp = pages + [ix]

    exp = collections.OrderedDict()
    for q in allp:
        write(os.path.join(D, 'site', q.fn), q.render())
        exp[q.fn] = q.e
    write(os.path.join(D, 'site', 'css', 'h.css'), CSS)
    write(os.path.join(D, 'expected.json'), json.dumps({'pages': exp}, ensure_ascii=False, indent=1))

    # README (件数は生成物から数える)
    c = pages
    def cnt(fn): return sum(1 for q in c if fn(q.e))
    dup = lambda e: any(v > 1 for k in ('headings', 'buttons') for v in collections.Counter(e[k]).values()) or \
        any(v > 1 for v in collections.Counter(f['label'] for f in e['fields'] if f['label']).values())
    readme = """# 画面仕様・Evidence 抽出 最終判定用 holdout

最終判定用の holdout。**改善に使っていない**。製品の出力はこのデータと突き合わせて採点するだけで、結果を見て製品を直し、このデータを直す、という往復には使わない。

## 目的
WebSpec2Doc の「画面仕様・Evidence 抽出」(見出し・ボタン・入力項目・リンク・表・エラー文言・API・取得不能の判別)の最終判定用の独立した正解。開発セット (`quality/commercial_eval/evidence/`) とドメイン・画面を重ねていない (保険見積・学習管理・物流追跡・自治体の申請・SaaS の請求管理)。

## 独立性
- 製品コード (src/, web/, static/, scripts/) は参照していない (読んでも grep してもいない)。製品も実行していない。git・pytest も使っていない。
- 開発セットから借りたのは形式 (README の構成と expected.json のキー) だけ。
- 正解は `build_holdout.py` のヘルパが「HTML を 1 要素書く」と同時に記録した。製品の抽出ロジックは使っていない。

## 構成
- `site/` : コンテンツページ **n = %d** (`h01.html`〜`h%02d.html`) + `index.html`。外部 CDN・外部フォント不使用。JS はインライン。サーバは無く `/api/...` は 404 になる前提。
- `expected.json` : `{"pages": {"h01.html": {...}}}`。`index.html` を含む (全 %d ページ)。キーは開発セットと同じ。
- `build_holdout.py` : site/・expected.json・README (evidence と viewpoints の両方) を再生成する。標準ライブラリのみ。

## 定義 (開発セットと同じ。判断が分かれる所だけ追記)
- headings: 見えている h1〜h3。非表示ラッパー内・閉じた details 内は含めない。文書順・重複はそのまま。
- buttons: 見えている `<button>` と `input[type=submit/button]`。重複は個数分。`<a class="btn">` は link であり button ではない。
- fields: 見えている入力項目。`type=hidden` は含めない。**disabled / readonly の入力は見えているので含める**。表の中・form の外の入力も含める。radio / checkbox は 1 個 1 エントリで、label は各自の `label for` の文言 (fieldset の legend は label ではない)。aria-label も label とみなす。placeholder だけのものは label = null。
- links: 内部リンク (クエリ付きはそのまま・重複 href は 1 回・初出順)。外部 URL は external_links、`#` は anchor_links。
- error_messages: 初期表示で見えるもののみ。JS 中にしか無い文言 (送信・blur・API 失敗時) は deferred_error_messages。
- must_not_appear: 非表示要素内の文言。どの種別としても抽出されたら誤検出。hidden_fields: `type=hidden` の name。
- 非表示の種類: `style="display:none"`、`hidden` 属性、`aria-hidden="true"` + display:none、CSS クラス (`css/h.css` の `.gone`)、`visibility:hidden`、閉じた `<details>`。
- unavailable: iframe の中身・ログイン必須領域・API/canvas に依存する内容。

## 件数 (コンテンツページ %d 件中)
| 観点 | ページ数 |
|---|---|
| 非表示 (hidden 系) を含む | %d |
| 閉じた details を含む | %d |
| type=hidden の入力を含む | %d |
| 同じ文言 (見出し・ボタン・ラベル) の重複を含む | %d |
| form 外の入力 (表の中など) を含む | 2 (h06, h13) |
| radio / checkbox のグループを含む | %d |
| JS が読み込み後に追加する要素を含む | %d |
| disabled / readonly の入力を含む | 3 (h02, h11, h15) |
| ラベルが placeholder だけの入力を含む | 3 (h03, h06, h14) |
| aria-label でラベル付けした入力を含む | 3 (h06, h12, h13) |
| 送信・blur・API 失敗で初めて出るエラー (deferred) を含む | %d |
| 初期表示で見えているエラーを含む | 2 (h05, h11) |
| API 通信 (fetch) を含む | %d |
| 取得できない情報 (unavailable) を含む | %d |
| iframe を含む | 1 (h09) |

## 限界
- 作成者は 1 名で、第三者による裁定は行っていない。
- 静的な HTML と素朴な JS だけ。SPA フレームワーク・Shadow DOM・動的に変わる URL・実在するバックエンドは扱わない。
- 文言は日本語のみ。ページ数 (%d) は少なく、1 ページの誤りが数 %% に響く。
- disabled の扱いなど、定義が分かれる所は上記で決めた。別の定義で採点すると差が出る。
""" % (len(c), len(c), len(allp), len(c),
       cnt(lambda e: e['must_not_appear']), cnt(lambda e: False) + 1, cnt(lambda e: e['hidden_fields']), cnt(dup),
       cnt(lambda e: any(f['type'] in ('radio', 'checkbox') for f in e['fields'])),
       cnt(lambda e: e['dynamic_headings'] or e['dynamic_buttons'] or e['dynamic_links']),
       cnt(lambda e: e['deferred_error_messages']), cnt(lambda e: e['api_endpoints']), cnt(lambda e: e['unavailable']), len(c))
    write(os.path.join(D, 'README.md'), readme)
    return pages


# ============================ 2. viewpoints ============================
CATS = ['normal', 'abnormal', 'boundary', 'required', 'format', 'state_transition', 'permission', 'error', 'api', 'persistence']
CAT_NAME = {'normal': '正常', 'abnormal': '異常値の入力', 'boundary': '境界値', 'required': '必須', 'format': '形式',
            'state_transition': '状態遷移', 'permission': '権限', 'error': 'エラーの表示と回復', 'api': 'API 連携', 'persistence': '保存と再表示'}


def build_viewpoints():
    D = os.path.join(BASE, 'viewpoints')
    S = []

    def scr(fn, title, desc, body, vps, notes, script=''):
        S.append((fn, title, desc, body, vps, notes, script))

    def fetchjs(method, path, box='msg', fail='失敗しました'):
        return ('(function(){var b=document.getElementById("go");if(!b){return;}b.addEventListener("click",function(){'
                'fetch("%s",{method:"%s"}).then(function(r){if(!r.ok){throw new Error("x");}return r.json();})'
                '.catch(function(){document.getElementById("%s").textContent="%s";});});})();') % (path, method, box, fail)

    scr('w01.html', '利用規約の確認',
        ['下の利用規約を読み、「同意する」にチェックを入れて「次へ進む」を押す。', '同意は必須。'],
        '<form action="w02.html" method="get"><p>第1条 本サービスは会員に限り利用できる。</p>'
        '<input type="checkbox" id="ag" name="agree" required><label for="ag">同意する</label><button type="submit">次へ進む</button></form>',
        ['normal', 'required'], '同意チェックが必須(required)で、進めば次の画面へ。入力値の形式・範囲の記述は無い。')
    scr('w02.html', 'お知らせ一覧',
        ['お知らせの題名を新しい順に表示する。', '題名を押すと詳細画面へ移動する。'],
        '<ul><li><a href="w03.html?id=3">システム保守のお知らせ</a></li><li><a href="w03.html?id=2">料金改定のお知らせ</a></li><li><a href="w03.html?id=1">新機能のご案内</a></li></ul>',
        ['normal'], '表示と遷移だけの画面。入力欄が無いので正常のみ。')
    scr('w03.html', '保険料シミュレーション',
        ['年齢は 18 歳から 80 歳までの整数で入力する(必須)。', '保険金額は 500万円・1000万円・3000万円から選ぶ(必須)。',
         '数字以外を入力した場合は「年齢は半角数字で入力してください」と表示する。',
         '「計算する」で /api/premium に POST し、月額保険料を画面に表示する。', '通信に失敗した場合は「計算できませんでした」と表示する。'],
        '<form><label for="age">年齢</label><input type="number" id="age" name="age" min="18" max="80" required>'
        '<label for="amt">保険金額</label><select id="amt" name="amt" required><option value="">選択してください</option><option>500万円</option><option>1000万円</option><option>3000万円</option></select>'
        '<button type="button" id="go">計算する</button></form><p id="msg"></p>',
        ['normal', 'required', 'abnormal', 'boundary', 'error', 'api'],
        '年齢の範囲 18〜80(boundary)、必須、数字以外のエラー文言(abnormal)、通信失敗の表示(error)、POST(api)。',
        fetchjs('POST', '/api/premium', 'msg', '計算できませんでした'))
    scr('w04.html', 'メモの保存',
        ['メモは 200 文字まで入力できる。', '「保存」を押すと /api/memo に PUT する。', '保存したメモは、画面を開き直しても表示される。'],
        '<form><label for="memo">メモ</label><textarea id="memo" name="memo" maxlength="200" rows="4"></textarea>'
        '<button type="button" id="go">保存</button></form><p id="msg"></p>',
        ['normal', 'boundary', 'api', 'persistence'], '200 文字上限(boundary)、PUT 保存(api)、開き直しても表示(persistence)。必須の記述は無い。',
        fetchjs('PUT', '/api/memo'))
    scr('w05.html', '荷物追跡',
        ['追跡番号は半角数字 12 桁で入力する。必須。', '「追跡する」で /api/tracking を取得して配送状況を表示する。',
         '通信に失敗した場合は「通信エラーが発生しました」と表示し、「再試行」ボタンで同じ要求を再送できる。'],
        '<form><label for="no">追跡番号</label><input type="text" id="no" name="no" required pattern="^[0-9]{12}$">'
        '<button type="button" id="go">追跡する</button><button type="button" id="retry">再試行</button></form><p id="msg"></p>',
        ['normal', 'required', 'format', 'error', 'api'], '12 桁数字(format)、必須、通信失敗と再試行(error)、GET(api)。',
        fetchjs('GET', '/api/tracking', 'msg', '通信エラーが発生しました'))
    scr('w06.html', '請求書の管理',
        ['請求書の一覧を表示する。', '「管理者」ロールのユーザーにだけ各行の「削除」ボタンを表示する。「閲覧者」ロールには表示しない。'],
        '<p>現在のロール: 管理者</p><table><thead><tr><th>請求書番号</th><th>金額</th><th>操作</th></tr></thead><tbody>'
        '<tr><td>INV-1</td><td>10,000円</td><td><button type="button">削除</button></td></tr>'
        '<tr><td>INV-2</td><td>20,000円</td><td><button type="button">削除</button></td></tr></tbody></table>',
        ['normal', 'permission'], 'ロールで削除ボタンの表示が変わる(permission)。入力欄は無い。')
    scr('w07.html', '申請ステータス',
        ['申請の状態は「下書き」→「申請中」→「承認済み」または「差戻し」と遷移する。', '「下書き」でだけ「申請する」を押せる。「申請中」でだけ「取り下げ」を押せる。',
         '「差戻し」の申請は「再申請」で「申請中」に戻る。', '遷移できない状態で操作した場合は「この状態ではできません」と表示する。'],
        '<p>現在の状態: <strong>下書き</strong></p><button type="button">申請する</button><button type="button">取り下げ</button><button type="button">再申請</button><p id="msg"></p>',
        ['normal', 'state_transition', 'error'], '状態の遷移規則(state_transition)と不可時のメッセージ(error)。')
    scr('w08.html', '運営会社の紹介',
        ['当社は 2015 年に東京で創業し、保険と物流の業務画面づくりを支援している。', '従業員は 40 名で、本社は東京都千代田区にある。', '詳しい沿革は会社案内の冊子を参照のこと。'],
        '<p>お問い合わせは代表窓口までお願いします。</p>',
        [], 'hard negative。説明文だけで、入力・操作・保存・通信のいずれの記述も無い。テスト観点は不要。')
    scr('w09.html', '用語集',
        ['この画面は用語の意味を説明するだけで、操作はできない。'],
        '<dl><dt>免責金額</dt><dd>事故のとき契約者が自己負担する額。</dd><dt>等級</dt><dd>事故歴に応じて決まる保険料の割引率の区分。</dd><dt>特約</dt><dd>基本の契約に付ける追加の補償。</dd></dl>'
        '<p><a href="#t1">免責金額</a>・<a href="#t2">等級</a></p>',
        [], 'hard negative。用語の説明だけ。ページ内リンクはあるが観点を要する仕様は無い。')
    scr('w10.html', '転入届の事前申請',
        ['氏名・郵便番号・転入予定日は必須。', '郵便番号はハイフンなしの半角数字 7 桁。電話番号は 0 から始まる 10〜11 桁の半角数字。', '同居人数は 0 人から 10 人まで。',
         '全角数字や記号を入力した場合は項目の下に「入力形式が正しくありません」と表示する。', '「申請する」で /api/move-in に POST する。失敗時は「申請できませんでした」と表示する。',
         '「一時保存」を押すと入力内容を保存し、次回の画面表示で続きから入力できる。'],
        '<form><label for="n">氏名</label><input id="n" name="name" required maxlength="40">'
        '<label for="z">郵便番号</label><input id="z" name="zip" required pattern="^[0-9]{7}$" maxlength="7">'
        '<label for="t">電話番号</label><input type="tel" id="t" name="tel" pattern="^0[0-9]{9,10}$">'
        '<label for="m">同居人数</label><input type="number" id="m" name="members" min="0" max="10">'
        '<label for="d">転入予定日</label><input type="date" id="d" name="move" required>'
        '<button type="button" id="go">申請する</button><button type="button">一時保存</button></form><p id="msg"></p>',
        ['normal', 'required', 'abnormal', 'boundary', 'format', 'error', 'api', 'persistence'], '必須・桁数形式・人数範囲・全角記号・失敗表示・POST・一時保存の全てが明記された複雑な画面。',
        fetchjs('POST', '/api/move-in', 'msg', '申請できませんでした'))
    scr('w11.html', 'メンバーの招待',
        ['メールアドレスは必須。メールアドレスの形式でなければ「メールアドレスの形式が正しくありません」と表示する。', '招待できるのは「管理者」だけ。管理者以外が実行すると「権限がありません」と表示する。',
         '招待は /api/invitations に POST する。'],
        '<form><label for="e">メールアドレス</label><input type="email" id="e" name="email" required maxlength="80"><button type="button" id="go">招待する</button></form><p id="msg"></p>',
        ['normal', 'required', 'format', 'permission', 'error', 'api'], '必須・形式・管理者のみ(permission)・エラー表示・POST。',
        fetchjs('POST', '/api/invitations', 'msg', '権限がありません'))
    scr('w12.html', '表示設定',
        ['言語(日本語・英語)と 1 ページの表示件数(10・50・100)を選べる。', '選んだ内容はこの端末に保存され、次に開いたときも同じ内容で表示される。'],
        '<form><label for="l">言語</label><select id="l" name="lang"><option>日本語</option><option>英語</option></select>'
        '<label for="c">表示件数</label><select id="c" name="per"><option>10</option><option>50</option><option>100</option></select></form>',
        ['normal', 'persistence'], '選択肢から選ぶだけで必須・形式の記述なし。端末に保存し再表示(persistence)。')
    scr('w13.html', 'カートの数量変更',
        ['数量は 1 から 99 までの整数で入力する。必須。', '範囲外のときは入力欄の下に「1〜99で入力してください」と表示し、更新しない。'],
        '<form><label for="q">数量</label><input type="number" id="q" name="qty" min="1" max="99" required><p class="error" id="msg"></p><button type="button">数量を更新</button></form>',
        ['normal', 'required', 'boundary', 'error'], '1〜99 の範囲(boundary)・必須・範囲外のメッセージ(error)。API・保存の記述なし。')
    scr('w14.html', '出荷処理',
        ['注文の状態は「受付」→「出荷準備」→「出荷済み」→「配達完了」と進む。「出荷済み」になった注文はキャンセルできない。', '「出荷する」を押せるのは「出荷担当」ロールだけ。他のロールではボタンが無効になる。',
         '状態の更新は /api/orders/status に PUT する。', '更新に失敗したら「更新に失敗しました」と表示し、「再試行」ボタンで再送できる。'],
        '<p>注文 #4410 の状態: <strong>出荷準備</strong></p><button type="button" id="go">出荷する</button><button type="button">再試行</button><button type="button">キャンセル</button><p id="msg"></p>',
        ['normal', 'state_transition', 'permission', 'api', 'error'], '状態遷移とキャンセル不可、ロール制限、PUT、失敗時の再試行。',
        fetchjs('PUT', '/api/orders/status', 'msg', '更新に失敗しました'))
    scr('w15.html', '商品検索',
        ['キーワードは 50 文字まで。価格は 0 円から 1,000,000 円まで。', '下限が上限より大きいときは「価格の範囲が正しくありません」と表示する。', '検索は /api/products に GET で問い合わせ、結果を表に表示する。'],
        '<form><label for="k">キーワード</label><input id="k" name="keyword" maxlength="50">'
        '<label for="a">下限</label><input type="number" id="a" name="min" min="0" max="1000000"><label for="b">上限</label><input type="number" id="b" name="max" min="0" max="1000000">'
        '<button type="button" id="go">検索</button></form><p id="msg"></p><table><thead><tr><th>商品名</th><th>価格</th></tr></thead><tbody><tr><td>ケーブル</td><td>980円</td></tr></tbody></table>',
        ['normal', 'abnormal', 'boundary', 'error', 'api'], '文字数・価格の範囲(boundary)、逆転した範囲の入力(abnormal)とその表示(error)、GET(api)。必須は無い。',
        fetchjs('GET', '/api/products', 'msg', '検索できませんでした'))
    scr('w16.html', 'ログイン',
        ['ログインIDとパスワードは必須。', '認証に失敗すると「IDまたはパスワードが違います」と表示する。', '連続 5 回失敗するとアカウントは「ロック中」の状態になり、30 分間ログインできない。', '認証は /api/login に POST する。'],
        '<form><label for="i">ログインID</label><input id="i" name="login_id" required><label for="p">パスワード</label><input type="password" id="p" name="pw" required>'
        '<button type="button" id="go">ログイン</button></form><p id="msg"></p>',
        ['normal', 'required', 'error', 'state_transition', 'api'], '必須・認証失敗表示・5 回でロック(state_transition)・POST。',
        fetchjs('POST', '/api/login', 'msg', 'IDまたはパスワードが違います'))

    scr_map = collections.OrderedDict()
    for fn, title, desc, body, vps, notes, script in S:
        html = (HEAD % ('%s | %s' % (title, BRAND)) + '<header class="hdr"><a href="index.html">メニュー</a></header>\n<main>\n<h1>%s</h1>\n'
                '<section class="spec"><h2>画面の説明</h2><ul>%s</ul></section>\n<section><h2>画面</h2>\n%s\n</section>\n%s</main>\n</body></html>\n') % (
            title, ''.join('<li>%s</li>' % d for d in desc), body, ('<script>%s</script>\n' % script) if script else '')
        write(os.path.join(D, 'site', fn), html)
        scr_map[fn] = collections.OrderedDict(required_viewpoints=vps, notes=notes)
    idx = (HEAD % ('メニュー | ' + BRAND) + '<main>\n<h1>ホールドアウト画面一覧</h1>\n<ul>%s</ul>\n</main>\n</body></html>\n') % ''.join(
        '<li><a href="%s">%s</a></li>' % (fn, t) for fn, t, *_ in S)
    write(os.path.join(D, 'site', 'index.html'), idx)
    write(os.path.join(D, 'site', 'css', 'h.css'), CSS)
    write(os.path.join(D, 'expected.json'), json.dumps({'categories': CATS, 'screens': scr_map}, ensure_ascii=False, indent=2))

    per = collections.Counter(v for s in scr_map.values() for v in s['required_viewpoints'])
    total = sum(per.values())
    sizes = [len(s['required_viewpoints']) for s in scr_map.values()]
    rows = '\n'.join('| `%s` | %s | %d |' % (c, CAT_NAME[c], per[c]) for c in CATS)
    readme = """# テスト観点生成 最終判定用 holdout

最終判定用の holdout。**改善に使っていない**。製品の出力を採点するだけで、結果を見て製品を直し、このデータを直す、という使い方はしない。

## 目的
製品が画面から生成する「テスト観点」が、QA の専門家が必要とする観点をどれだけ網羅しているかを測る独立した正解データ。開発セット (`quality/commercial_eval/viewpoints/`) と画面を重ねていない。

## 独立性
- 製品コード (src/, web/, static/, scripts/) は参照していない (読んでも grep してもいない)。製品も実行していない。git・pytest も使っていない。
- 開発セットから借りたのは形式 (README の構成と expected.json のキー) だけ。

## 構成
- `site/` : 静的サイト (`index.html` と `w01.html`〜`w%02d.html`)。外部 CDN なし。各画面に「画面の説明」(仕様文)と、HTML 属性つきの画面部品がある。
- `expected.json` : `categories` (10 個) と、画面ごとの `required_viewpoints` (カテゴリ ID)・`notes` (根拠)。
- `build_holdout.py` : site/・expected.json・README を再生成する。

## 画面数
n = %d (必須観点の延べ数 %d、1 画面あたり %d〜%d 個)

| 内訳 | 画面 |
|---|---|
| 観点が 1〜2 個の単純な画面 | w01, w02, w06, w12 |
| 5 個以上の複雑な画面 | w03, w05, w10, w11, w14, w15, w16 |
| API で保存する画面 | w04 (PUT), w10 (POST) |
| エラー表示と再試行の説明がある画面 | w05, w14 |
| 権限で表示が変わる画面 | w06, w11, w14 |
| 状態遷移の説明がある画面 | w07, w14, w16 |
| どの観点にも当たらない説明だけの画面 (hard negative) | w08, w09 (required_viewpoints = []) |

## カテゴリ別の件数
| ID | 名称 | 出現画面数 |
|---|---|---|
%s

## 正解の作り方
- 画面上の説明文と HTML 属性から、QA の観点で人が決めた。`required_viewpoints` は、その画面に必ず要る観点だけ。説明文に書かれていない観点は付けていない。
- 説明文が無い観点を HTML 属性だけから足すことはしていない (例: w01 の form に入力形式の記述が無いので `format` は付けない)。
- hard negative は、観点が空であることが正解。観点を出しすぎた場合は過剰生成として数える。

## 限界
- 作成者は 1 名で、裁定(第三者による合意)は行っていない。
- 画面からカテゴリへの対応づけ自体が主観を含む。特に `abnormal` と `error`、`boundary` と `format` の境目は人によって分かれうる(w15 の「下限が上限より大きい」は abnormal と error の両方にした)。
- 表現の違いは評価側でカテゴリ ID に寄せる前提で、ここでは ID のみを使う。
- 画面数が %d と少ない。1 画面の判断が全体の数 %% に響く。日本語のみ。

## measured commit
未計測 (最終判定の実行時に記入する)。
""" % (len(S), len(S), total, min(sizes), max(sizes), rows, len(S))
    write(os.path.join(D, 'README.md'), readme)


if __name__ == '__main__':
    build_evidence()
    build_viewpoints()
