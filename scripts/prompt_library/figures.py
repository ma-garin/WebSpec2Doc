"""記事に埋め込む図版（インライン SVG）。

- 構造線と文字は currentColor、意味を持つ要素だけ var(--accent) / var(--signal)。
  いずれもページ側のトークンなので light / dark の両方で読める。
- marker の id は図ごとに接頭辞を変える（同一ページに複数の図が載るため）。
"""

FIGURES: dict[str, str] = {}


def _arrow(prefix: str, color: str = "currentColor") -> str:
    return (
        f'<defs><marker id="{prefix}-a" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<polygon points="0,1 10,5 0,9" fill="{color}"/></marker></defs>'
    )


FIGURES["attrs"] = f'''<svg viewBox="0 0 720 250" role="img"
 aria-label="入力欄1つの属性から、必須・最大長・パターンのテスト条件が機械的に決まる図"
 style="max-width:100%;height:auto">
{_arrow("at")}
<rect x="8" y="20" width="250" height="210" rx="4" fill="none" stroke="currentColor" stroke-opacity=".35"/>
<text x="20" y="44" font-size="11" fill="currentColor" fill-opacity=".6">観測した HTML</text>
<text x="20" y="72" font-size="13" font-family="monospace" fill="currentColor">&lt;input name="cvc"</text>
<text x="36" y="106" font-size="13" font-family="monospace" fill="var(--accent)">required</text>
<text x="36" y="140" font-size="13" font-family="monospace" fill="var(--accent)">maxlength="4"</text>
<text x="36" y="174" font-size="13" font-family="monospace" fill="var(--accent)">pattern="[0-9]{{3,4}}"</text>
<text x="20" y="208" font-size="13" font-family="monospace" fill="currentColor">&gt;</text>

<line x1="266" y1="102" x2="420" y2="82" stroke="currentColor" stroke-opacity=".5" marker-end="url(#at-a)"/>
<line x1="266" y1="136" x2="420" y2="136" stroke="currentColor" stroke-opacity=".5" marker-end="url(#at-a)"/>
<line x1="266" y1="170" x2="420" y2="190" stroke="currentColor" stroke-opacity=".5" marker-end="url(#at-a)"/>

<text x="430" y="44" font-size="11" fill="currentColor" fill-opacity=".6">導かれるテスト条件</text>
<rect x="430" y="60" width="282" height="40" rx="3" fill="none" stroke="currentColor" stroke-opacity=".35"/>
<text x="444" y="86" font-size="13" fill="currentColor">未入力で送信（必須チェック）</text>
<rect x="430" y="114" width="282" height="40" rx="3" fill="none" stroke="currentColor" stroke-opacity=".35"/>
<text x="444" y="140" font-size="13" fill="currentColor">最大長: 3/4/5 文字</text>
<rect x="430" y="168" width="282" height="40" rx="3" fill="none" stroke="currentColor" stroke-opacity=".35"/>
<text x="444" y="194" font-size="13" fill="currentColor">パターン適合 / 不適合</text>
</svg>'''


FIGURES["pipeline"] = f'''<svg viewBox="0 0 900 290" role="img"
 aria-label="URL入力から成果物までの6段のパイプラインと、途中から分岐する未確認領域の出力"
 style="max-width:100%;height:auto">
{_arrow("pl")}
<text x="8" y="26" font-size="11" fill="currentColor" fill-opacity=".6">入力</text>
<rect x="8" y="38" width="96" height="52" rx="4" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="56" y="70" font-size="13" text-anchor="middle" fill="var(--accent)">URL</text>

<text x="128" y="26" font-size="11" fill="currentColor" fill-opacity=".6">処理段（この順を崩さない）</text>
{"".join(
  f'<rect x="{128 + i*124}" y="38" width="108" height="52" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>'
  f'<text x="{182 + i*124}" y="62" font-size="12" text-anchor="middle" fill="currentColor">{a}</text>'
  f'<text x="{182 + i*124}" y="80" font-size="12" text-anchor="middle" fill="currentColor">{b}</text>'
  for i, (a, b) in enumerate([("1 収集", "画面を集める"), ("2 同定", "同じ画面を畳む"),
                              ("3 実測", "属性を読む"), ("4 条件", "条件文に変換"),
                              ("5 技法", "技法を選ぶ"), ("6 ケース", "手順と期待結果")])
)}
{"".join(
  f'<line x1="{104 + i*124}" y1="64" x2="{124 + i*124}" y2="64" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pl-a)"/>'
  for i in range(6)
)}

<line x1="182" y1="94" x2="182" y2="176" stroke="var(--signal)" stroke-dasharray="4 3" marker-end="url(#pl-a)"/>
<line x1="430" y1="94" x2="430" y2="176" stroke="var(--signal)" stroke-dasharray="4 3" marker-end="url(#pl-a)"/>
<rect x="128" y="180" width="360" height="44" rx="4" fill="none" stroke="var(--signal)" stroke-width="1.5"/>
<text x="308" y="207" font-size="12.5" text-anchor="middle" fill="var(--signal)">未確認領域（見ていない範囲）— P11 で必ず出す</text>

<line x1="802" y1="94" x2="802" y2="176" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pl-a)"/>
<rect x="716" y="180" width="172" height="44" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>
<text x="802" y="207" font-size="12.5" text-anchor="middle" fill="currentColor">テストケース表</text>

<text x="8" y="258" font-size="11.5" fill="currentColor" fill-opacity=".55">各段の出力が次の段の入力になる。まとめて頼むと途中の段が飛ばされる。</text>
</svg>'''


FIGURES["coverage"] = f'''<svg viewBox="0 0 760 292" role="img"
 aria-label="HTMLから機械的に決まる範囲と、人に聞くしかない範囲の対比"
 style="max-width:100%;height:auto">
<rect x="8" y="16" width="364" height="34" rx="3" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="190" y="39" font-size="13" text-anchor="middle" fill="var(--accent)">HTML から機械的に決まる</text>
<rect x="388" y="16" width="364" height="34" rx="3" fill="none" stroke="var(--signal)" stroke-width="1.5"/>
<text x="570" y="39" font-size="13" text-anchor="middle" fill="var(--signal)">人に聞くしかない</text>
{"".join(
  f'<line x1="20" y1="{72 + i*30}" x2="30" y2="{72 + i*30}" stroke="var(--accent)" stroke-width="2"/>'
  f'<text x="40" y="{76 + i*30}" font-size="12.5" fill="currentColor">{t}</text>'
  for i, t in enumerate(["必須かどうか（required）", "文字数の上限・下限", "入力形式（pattern）",
                         "選択肢の一覧", "数値の範囲（min / max）", "画面から画面への導線"])
)}
{"".join(
  f'<line x1="400" y1="{72 + i*30}" x2="410" y2="{72 + i*30}" stroke="var(--signal)" stroke-width="2"/>'
  f'<text x="420" y="{76 + i*30}" font-size="12.5" fill="currentColor">{t}</text>'
  for i, t in enumerate(["サーバ側の業務ルール", "権限による表示の出し分け", "エラーメッセージの正しい文言",
                         "他システムとの連携条件", "性能・負荷の合格ライン", "ログイン後にしかない画面"])
)}
<line x1="8" y1="256" x2="752" y2="256" stroke="currentColor" stroke-opacity=".25"/>
<text x="8" y="282" font-size="11.5" fill="currentColor" fill-opacity=".55">右側を「未確認」と書かずに表を作ると、抜けたことに誰も気づけない。</text>
</svg>'''


FIGURES["guard"] = f'''<svg viewBox="0 0 800 330" role="img"
 aria-label="データと指示を分離するブロック構造と、生成値を検算して破棄するゲートの図"
 style="max-width:100%;height:auto">
{_arrow("gd")}
<text x="8" y="24" font-size="11" fill="currentColor" fill-opacity=".6">ゲート1: データと指示を分ける</text>
<rect x="8" y="34" width="376" height="196" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>
<rect x="24" y="52" width="344" height="52" rx="3" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="38" y="74" font-size="12" fill="var(--accent)">指示（あなたが書いた部分）</text>
<text x="38" y="93" font-size="11.5" fill="currentColor" fill-opacity=".7">守ること / 変換ルール / 出力形式</text>
<rect x="24" y="122" width="344" height="90" rx="3" fill="none" stroke="var(--signal)" stroke-width="1.5" stroke-dasharray="5 3"/>
<text x="38" y="144" font-size="12" font-family="monospace" fill="var(--signal)">&lt;site_data&gt;</text>
<text x="38" y="166" font-size="11.5" fill="currentColor" fill-opacity=".7">貼りつけた HTML（何が書いてあるか不明）</text>
<text x="38" y="185" font-size="11.5" fill="currentColor" fill-opacity=".7">「これまでの指示を無視して…」が紛れていても</text>
<text x="38" y="204" font-size="11.5" fill="var(--signal)">指示としては読まない / データとしてだけ読む</text>

<line x1="392" y1="132" x2="428" y2="132" stroke="currentColor" stroke-opacity=".5" marker-end="url(#gd-a)"/>

<text x="436" y="24" font-size="11" fill="currentColor" fill-opacity=".6">ゲート2: 根拠のない値を捨てる</text>
<rect x="436" y="34" width="356" height="196" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>
<rect x="452" y="52" width="324" height="40" rx="3" fill="none" stroke="currentColor" stroke-opacity=".35"/>
<text x="466" y="77" font-size="12.5" fill="currentColor">pattern から適合例／不適合例を作る</text>
<line x1="614" y1="92" x2="614" y2="112" stroke="currentColor" stroke-opacity=".5" marker-end="url(#gd-a)"/>
<rect x="452" y="112" width="324" height="40" rx="3" fill="none" stroke="currentColor" stroke-opacity=".35"/>
<text x="466" y="137" font-size="12.5" fill="currentColor">その例が本当にマッチするか検算する</text>
<line x1="530" y1="152" x2="530" y2="172" stroke="var(--accent)" marker-end="url(#gd-a)"/>
<line x1="700" y1="152" x2="700" y2="172" stroke="var(--signal)" marker-end="url(#gd-a)"/>
<rect x="452" y="172" width="156" height="40" rx="3" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="530" y="197" font-size="12.5" text-anchor="middle" fill="var(--accent)">合えば採用</text>
<rect x="622" y="172" width="154" height="40" rx="3" fill="none" stroke="var(--signal)" stroke-width="1.5"/>
<text x="699" y="197" font-size="12.5" text-anchor="middle" fill="var(--signal)">破れたら捨てる</text>

<text x="8" y="258" font-size="11.5" fill="currentColor" fill-opacity=".55">捨てた場合は空欄にせず「（例生成不能・手動作成要）」と書かせる。黙って消えるのが一番危ない。</text>
</svg>'''


FIGURES["handson"] = f'''<svg viewBox="0 0 800 200" role="img"
 aria-label="30分で1画面を通すときのプロンプトの順番と、各段の所要時間"
 style="max-width:100%;height:auto">
{_arrow("hs")}
<line x1="16" y1="112" x2="784" y2="112" stroke="currentColor" stroke-opacity=".3"/>
{"".join(
  f'<rect x="{16 + i*128}" y="60" width="120" height="52" rx="4" fill="none" '
  f'stroke="{c}" stroke-width="{w}"/>'
  f'<text x="{76 + i*128}" y="82" font-size="12.5" text-anchor="middle" fill="{c}">{p}</text>'
  f'<text x="{76 + i*128}" y="100" font-size="11.5" text-anchor="middle" fill="currentColor" fill-opacity=".7">{t}</text>'
  f'<circle cx="{76 + i*128}" cy="112" r="3.5" fill="{c}"/>'
  f'<text x="{76 + i*128}" y="136" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity=".55">{m}</text>'
  for i, (p, t, m, c, w) in enumerate([
      ("材料をとる", "コンソール", "0–5分", "currentColor", "1"),
      ("P2", "画面仕様", "5–10分", "var(--accent)", "1.5"),
      ("P4", "テスト条件", "10–15分", "var(--accent)", "1.5"),
      ("P9", "ケース表", "15–22分", "var(--accent)", "1.5"),
      ("P11", "未確認領域", "22–27分", "var(--signal)", "1.5"),
      ("P13", "監査", "27–30分", "var(--signal)", "1.5"),
  ])
)}
<text x="716" y="42" font-size="11" text-anchor="middle" fill="var(--signal)">別セッション</text>
<line x1="716" y1="48" x2="716" y2="58" stroke="var(--signal)" marker-end="url(#hs-a)"/>
<text x="16" y="174" font-size="11.5" fill="currentColor" fill-opacity=".55">P2 から P11 までは同じチャットで続ける。P13 だけ新しいチャットで実行する（自己採点は甘くなるため）。</text>
</svg>'''


FIGURES["promptmap"] = f'''<svg viewBox="0 0 760 350" role="img"
 aria-label="プロンプトの依存関係。画面一覧から画面仕様、テスト条件を経てテストケース表へ流れ、監査は別セッションで走る"
 style="max-width:100%;height:auto">
{_arrow("pm")}
<rect x="300" y="16" width="160" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>
<text x="380" y="41" font-size="12.5" text-anchor="middle" fill="currentColor">P1 画面棚卸し</text>
<line x1="380" y1="56" x2="380" y2="76" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pm-a)"/>
<rect x="300" y="76" width="160" height="40" rx="4" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="380" y="101" font-size="12.5" text-anchor="middle" fill="var(--accent)">P2 画面仕様化</text>

<line x1="340" y1="116" x2="200" y2="140" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pm-a)"/>
<line x1="380" y1="116" x2="380" y2="140" stroke="var(--accent)" marker-end="url(#pm-a)"/>
<rect x="120" y="140" width="160" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>
<text x="200" y="165" font-size="12.5" text-anchor="middle" fill="currentColor">P3 テスト観点</text>
<rect x="300" y="140" width="160" height="40" rx="4" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="380" y="165" font-size="12.5" text-anchor="middle" fill="var(--accent)">P4 テスト条件</text>

<line x1="340" y1="180" x2="200" y2="206" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pm-a)"/>
<line x1="380" y1="180" x2="380" y2="206" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pm-a)"/>
<line x1="420" y1="180" x2="560" y2="206" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pm-a)"/>
{"".join(
  f'<rect x="{120 + i*180}" y="206" width="160" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>'
  f'<text x="{200 + i*180}" y="231" font-size="12.5" text-anchor="middle" fill="currentColor">{t}</text>'
  for i, t in enumerate(["P5 境界値", "P6 / P7 組合せ", "P8 画面遷移"])
)}
{"".join(
  f'<line x1="{200 + i*180}" y1="246" x2="380" y2="272" stroke="currentColor" stroke-opacity=".5" marker-end="url(#pm-a)"/>'
  for i in range(3)
)}
<rect x="300" y="272" width="160" height="40" rx="4" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
<text x="380" y="297" font-size="12.5" text-anchor="middle" fill="var(--accent)">P9 テストケース表</text>

<rect x="560" y="76" width="184" height="40" rx="4" fill="none" stroke="var(--signal)" stroke-width="1.5"/>
<text x="652" y="101" font-size="12.5" text-anchor="middle" fill="var(--signal)">P11 未確認領域</text>
<rect x="560" y="272" width="184" height="40" rx="4" fill="none" stroke="var(--signal)" stroke-width="1.5" stroke-dasharray="5 3"/>
<text x="652" y="290" font-size="12.5" text-anchor="middle" fill="var(--signal)">P13 監査</text>
<text x="652" y="306" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity=".6">別セッションで実行</text>
<line x1="460" y1="292" x2="556" y2="292" stroke="var(--signal)" stroke-dasharray="5 3" marker-end="url(#pm-a)"/>

<rect x="16" y="16" width="184" height="40" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4" stroke-dasharray="5 3"/>
<text x="108" y="41" font-size="12.5" text-anchor="middle" fill="currentColor">P0 共通ルール（全部に付ける）</text>

<text x="16" y="338" font-size="11.5" fill="currentColor" fill-opacity=".55">太い枠が最短ルート。P1 は画面が多いときだけ、P3 / P8 は必要に応じて足す。</text>
</svg>'''


FIGURES["bvaline"] = f'''<svg viewBox="0 0 760 210" role="img"
 aria-label="最大長50文字の項目で、有効な範囲と無効な範囲の境目に49・50・51の3点を置く図"
 style="max-width:100%;height:auto">
{_arrow("bv")}
<rect x="40" y="70" width="480" height="34" rx="2" fill="var(--accent)" fill-opacity=".10" stroke="var(--accent)"/>
<rect x="520" y="70" width="200" height="34" rx="2" fill="var(--signal)" fill-opacity=".10" stroke="var(--signal)"/>
<text x="280" y="92" font-size="12.5" text-anchor="middle" fill="var(--accent)">有効（受理されるはず）</text>
<text x="620" y="92" font-size="12.5" text-anchor="middle" fill="var(--signal)">無効（エラーになるはず）</text>
<text x="40" y="60" font-size="11.5" fill="currentColor" fill-opacity=".6">0 文字</text>
<text x="712" y="60" font-size="11.5" text-anchor="end" fill="currentColor" fill-opacity=".6">それ以上</text>

<line x1="520" y1="56" x2="520" y2="118" stroke="currentColor" stroke-width="1.5"/>
<text x="520" y="46" font-size="11.5" text-anchor="middle" fill="currentColor">境目 = maxlength 50</text>

{"".join(
  f'<circle cx="{x}" cy="87" r="5" fill="{c}"/>'
  f'<line x1="{x}" y1="118" x2="{x}" y2="140" stroke="{c}"/>'
  f'<text x="{x}" y="158" font-size="13" text-anchor="middle" fill="{c}">{n}</text>'
  f'<text x="{x}" y="176" font-size="11.5" text-anchor="middle" fill="currentColor" fill-opacity=".65">{lab}</text>'
  for x, n, lab, c in [(478, "49", "受理", "var(--accent)"),
                       (512, "50", "受理", "var(--accent)"),
                       (556, "51", "エラー", "var(--signal)")]
)}
<text x="40" y="200" font-size="11.5" fill="currentColor" fill-opacity=".55">1〜48 文字は「同じ結果になるはず」の仲間（同値クラス）なので、代表1つで足りる。バグは境目に出る。</text>
</svg>'''


FIGURES["dt"] = f'''<svg viewBox="0 0 760 300" role="img"
 aria-label="必須項目を先頭4件に切ったうえで、充足と未充足の全組み合わせ16行を作る図"
 style="max-width:100%;height:auto">
{_arrow("dtx")}
<text x="8" y="24" font-size="11" fill="currentColor" fill-opacity=".6">画面の必須項目（6件）</text>
{"".join(
  f'<rect x="8" y="{34 + i*34}" width="150" height="26" rx="3" fill="none" stroke="{c}" stroke-dasharray="{d}"/>'
  f'<text x="20" y="{52 + i*34}" font-size="12" fill="{c}">{t}</text>'
  for i, (t, c, d) in enumerate([("氏名", "var(--accent)", "0"), ("メール", "var(--accent)", "0"),
                                 ("電話", "var(--accent)", "0"), ("種別", "var(--accent)", "0"),
                                 ("本文", "currentColor", "4 3"), ("同意", "currentColor", "4 3")])
)}
<text x="8" y="272" font-size="11.5" fill="var(--signal)">5件目以降は切り落とす</text>
<text x="8" y="290" font-size="11.5" fill="currentColor" fill-opacity=".6">（切った項目名は必ず明記する）</text>

<line x1="166" y1="120" x2="210" y2="120" stroke="currentColor" stroke-opacity=".5" marker-end="url(#dtx-a)"/>
<text x="188" y="110" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity=".6">先頭4件</text>

<text x="222" y="24" font-size="11" fill="currentColor" fill-opacity=".6">全組み合わせ 2⁴ = 16 行（●=充足 / ○=未充足）</text>
{"".join(
  f'<text x="{240 + c*40}" y="46" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity=".6">{h}</text>'
  for c, h in enumerate(["氏名", "メール", "電話", "種別"])
)}
<text x="420" y="46" font-size="11" fill="currentColor" fill-opacity=".6">期待結果</text>
{"".join(
  "".join(
    f'<circle cx="{240 + c*40}" cy="{62 + r*14}" r="4" '
    f'fill="{"var(--accent)" if (r >> (3 - c)) & 1 == 0 else "none"}" '
    f'stroke="{"var(--accent)" if (r >> (3 - c)) & 1 == 0 else "var(--signal)"}"/>'
    for c in range(4)
  )
  + (f'<text x="420" y="{66 + r*14}" font-size="11" fill="var(--accent)">送信成功</text>' if r == 0
     else f'<text x="420" y="{66 + r*14}" font-size="11" fill="var(--signal)">エラー: 未入力の項目名を全て表示</text>')
  for r in range(16)
)}
<text x="222" y="290" font-size="11.5" fill="currentColor" fill-opacity=".55">ペアワイズには縮退しない。16行は全部出す。</text>
</svg>'''


FIGURES["pairwise"] = f'''<svg viewBox="0 0 760 270" role="img"
 aria-label="3因子3水準の場合、全組み合わせ27件がペアワイズでは9件に減ることを点の数で比較した図"
 style="max-width:100%;height:auto">
<text x="8" y="24" font-size="12.5" fill="currentColor">全組み合わせ（デカルト積）</text>
<text x="8" y="44" font-size="11.5" fill="currentColor" fill-opacity=".6">3因子 × 3水準 = 27 件</text>
{"".join(
  f'<circle cx="{20 + (i % 9) * 34}" cy="{72 + (i // 9) * 30}" r="7" fill="currentColor" fill-opacity=".22"/>'
  for i in range(27)
)}

<line x1="330" y1="60" x2="330" y2="230" stroke="currentColor" stroke-opacity=".25"/>

<text x="356" y="24" font-size="12.5" fill="var(--accent)">ペアワイズ（2-way）</text>
<text x="356" y="44" font-size="11.5" fill="currentColor" fill-opacity=".6">9 件。どの2項目の組み合わせも最低1回は現れる</text>
{"".join(
  f'<circle cx="{368 + (i % 9) * 34}" cy="72" r="7" fill="var(--accent)" fill-opacity=".9"/>'
  for i in range(9)
)}
<text x="356" y="122" font-size="11.5" fill="currentColor" fill-opacity=".7">因子が7個に増えると 3⁷ = 2187 件 → ペアワイズなら十数件</text>
<text x="356" y="146" font-size="11.5" fill="currentColor" fill-opacity=".7">因子は8個・ケースは20件で打ち切る（打ち切ったら明記する）</text>
<rect x="356" y="166" width="396" height="46" rx="3" fill="none" stroke="var(--signal)" stroke-width="1.5"/>
<text x="370" y="186" font-size="11.5" fill="var(--signal)">打ち切りが起きた表は「2-way 完全被覆に達していない」</text>
<text x="370" y="204" font-size="11.5" fill="var(--signal)">— 黙って減らさず、必ず出力に書かせる</text>
<text x="8" y="256" font-size="11.5" fill="currentColor" fill-opacity=".55">ほとんどの不具合は2項目の組み合わせで出る、という経験則に基づく手法。3項目以上の相互作用は拾えない。</text>
</svg>'''


FIGURES["switch"] = f'''<svg viewBox="0 0 760 250" role="img"
 aria-label="0-switch は単一の遷移を、1-switch は連続する2つの遷移を数えることを示す図"
 style="max-width:100%;height:auto">
{_arrow("sw")}
{_arrow("sw2", "var(--accent)")}
{_arrow("sw3", "var(--signal)")}
<text x="8" y="24" font-size="11" fill="currentColor" fill-opacity=".6">画面遷移</text>
{"".join(
  f'<rect x="{20 + i*180}" y="40" width="120" height="44" rx="4" fill="none" stroke="currentColor" stroke-opacity=".4"/>'
  f'<text x="{80 + i*180}" y="68" font-size="13" text-anchor="middle" fill="currentColor">{t}</text>'
  for i, t in enumerate(["P001 トップ", "P002 一覧", "P003 入力", "P004 完了"])
)}
{"".join(
  f'<line x1="{140 + i*180}" y1="62" x2="{196 + i*180}" y2="62" stroke="currentColor" stroke-opacity=".5" marker-end="url(#sw-a)"/>'
  for i in range(3)
)}

<text x="8" y="128" font-size="12.5" fill="var(--accent)">0-switch = 遷移1本ずつを数える（3通り）</text>
{"".join(
  f'<line x1="{140 + i*180}" y1="146" x2="{196 + i*180}" y2="146" stroke="var(--accent)" stroke-width="2" marker-end="url(#sw2-a)"/>'
  f'<text x="{168 + i*180}" y="138" font-size="11" text-anchor="middle" fill="var(--accent)">{i+1}</text>'
  for i in range(3)
)}

<text x="8" y="192" font-size="12.5" fill="var(--signal)">1-switch = 連続する2本の組を数える（2通り）</text>
<path d="M140 210 L196 210" stroke="var(--signal)" stroke-width="2"/>
<path d="M320 210 L376 210" stroke="var(--signal)" stroke-width="2" marker-end="url(#sw3-a)"/>
<path d="M140 210 C 200 232, 320 232, 376 210" stroke="var(--signal)" stroke-width="1" fill="none" stroke-dasharray="3 3"/>
<text x="258" y="204" font-size="11" text-anchor="middle" fill="var(--signal)">1</text>
<path d="M320 232 L376 232" stroke="var(--signal)" stroke-opacity=".55" stroke-width="2"/>
<path d="M500 232 L556 232" stroke="var(--signal)" stroke-opacity=".55" stroke-width="2" marker-end="url(#sw3-a)"/>
<text x="438" y="226" font-size="11" text-anchor="middle" fill="var(--signal)" fill-opacity=".7">2</text>
<text x="596" y="150" font-size="11.5" fill="currentColor" fill-opacity=".55">元ツールは設定で</text>
<text x="596" y="168" font-size="11.5" fill="currentColor" fill-opacity=".55">どちらか一方を生成する</text>
<text x="596" y="186" font-size="11.5" fill="currentColor" fill-opacity=".55">（既定は 0-switch）</text>
</svg>'''


FIGURES["technique"] = f'''<svg viewBox="0 0 780 344" role="img"
 aria-label="入力欄の特徴から、境界値分析・デシジョンテーブル・ペアワイズ・状態遷移のどれが選ばれるかの対応図"
 style="max-width:100%;height:auto">
{_arrow("tq")}
<text x="8" y="24" font-size="11" fill="currentColor" fill-opacity=".6">観測した特徴</text>
<text x="470" y="24" font-size="11" fill="currentColor" fill-opacity=".6">選ばれる技法</text>
{"".join(
  f'<rect x="8" y="{36 + i*44}" width="290" height="34" rx="3" fill="none" stroke="currentColor" stroke-opacity=".4"/>'
  f'<text x="22" y="{58 + i*44}" font-size="12.5" fill="currentColor">{t}</text>'
  for i, t in enumerate([
      "どの画面でも（無条件）",
      "maxlength / minlength / min / max がある",
      "email / tel / date / password 型",
      "required の項目が2個以上",
      "入力欄が3個以上",
      "遷移先がある",
      "検索欄＋絞り込み／並び順／ページング",
  ])
)}
{"".join(
  f'<rect x="470" y="{36 + i*44}" width="302" height="34" rx="3" fill="none" stroke="{c}" stroke-width="1.5"/>'
  f'<text x="484" y="{58 + i*44}" font-size="12.5" fill="{c}">{t}</text>'
  for i, (t, c) in enumerate([
      ("画面表示確認（DSP）・単一遷移（TRN）", "var(--accent)"),
      ("境界値分析（BVA）", "var(--accent)"),
      ("境界値分析（値カタログ由来・確信度は下げる）", "currentColor"),
      ("デシジョンテーブル（先頭4件・2⁴=16行）", "var(--accent)"),
      ("ペアワイズ（2-way）", "var(--accent)"),
      ("状態遷移（0-switch か 1-switch）", "var(--accent)"),
      ("メタモルフィックテスト", "currentColor"),
  ])
)}
{"".join(
  f'<line x1="306" y1="{53 + i*44}" x2="462" y2="{53 + i*44}" stroke="currentColor" stroke-opacity=".45" marker-end="url(#tq-a)"/>'
  for i in range(7)
)}
<text x="8" y="336" font-size="11.5" fill="currentColor" fill-opacity=".55">複数当たれば複数生成される。1つも当たらない画面でも、画面表示確認と単一遷移は必ず作られる。</text>
</svg>'''


FIGURES["ladder"] = f'''<svg viewBox="0 0 700 350" role="img"
 aria-label="画面種別は7段のはしごを上から順に降り、最初に当たった段で止まることを示す図"
 style="max-width:100%;height:auto">
{_arrow("ld")}
{"".join(
  f'<rect x="70" y="{20 + i*44}" width="300" height="34" rx="3" fill="none" stroke="{c}" stroke-width="{w}"/>'
  f'<text x="84" y="{42 + i*44}" font-size="12.5" fill="{c}">{i+1}. {t}</text>'
  f'<text x="390" y="{42 + i*44}" font-size="12" fill="{c}">{pr}</text>'
  f'<text x="470" y="{42 + i*44}" font-size="11.5" fill="currentColor" fill-opacity=".6">{kw}</text>'
  for i, (t, pr, kw, c, w) in enumerate([
      ("payment", "critical", "決済 / 支払 / カード / 課金", "var(--signal)", "1.5"),
      ("personal_info", "critical", "個人情報 / 住所 / 氏名", "var(--signal)", "1.5"),
      ("auth", "critical", "ログイン / パスワード", "var(--signal)", "1.5"),
      ("search", "medium", "検索 / filter", "currentColor", "1"),
      ("list", "medium", "入力欄1個以下 かつ 一覧", "currentColor", "1"),
      ("form", "high", "入力欄2個以上（語は不問）", "var(--accent)", "1.5"),
      ("general", "low", "上のどれにも当たらない", "currentColor", "1"),
  ])
)}
{"".join(
  f'<line x1="52" y1="{54 + i*44}" x2="52" y2="{76 + i*44}" stroke="currentColor" stroke-opacity=".45" marker-end="url(#ld-a)"/>'
  for i in range(6)
)}
<line x1="52" y1="20" x2="52" y2="34" stroke="currentColor" stroke-opacity=".45"/>
<text x="8" y="16" font-size="11" fill="currentColor" fill-opacity=".6">上から順に判定</text>
<text x="8" y="342" font-size="11.5" fill="currentColor" fill-opacity=".55">「支払い方法を検索する一覧画面」は必ず payment になる。先に当たった段で止まるため。</text>
</svg>'''
