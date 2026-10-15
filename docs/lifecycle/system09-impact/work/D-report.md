# D-report（画面: DD-008）
- 作成: templates/impact_analysis.html（全面書き直し）, static/js/impact/{api,app,system,cr,graph}.js（119/258/320/335/96 行。node --check 全件 OK）, static/css/impact.css（書き直し）。static/js/impact.js は残置・テンプレートから外した。ブラウザ確認は未実行
- 使った API（/api/impact/v2）: systems（GET/POST）, systems/<sid>（GET/PATCH/DELETE）, members（GET/PUT/DELETE）, documents（GET/POST multipart の file 1 件ずつ・PATCH kind・DELETE）, items?q, baselines（GET/POST）, baselines/diff?old&new, links（GET/POST/DELETE）, links/suggest, links/suggestions（GET・POST {accept}）
- 続き: crs?status, crs（POST）, crs/<code>（GET）, transition {to,reason}, estimate, analyze {confirm_send}, jobs/<id>（GET 1 秒間隔・終了で停止）, jobs/<id>/cancel, crs/<code>/impacts?priority&state, impacts/<id>（GET）, resolve, override, graph, approval {decision,reason}, actuals（GET/POST）, review, report.xlsx（リンク）, audit?since&until&actor&cr, audit.csv（リンク）, sample
- 逸脱1: URL に &tab=<区分> を追加（DD-008 の 4 形に加え、対象システム／CR 内の区分を保持するため）。承認・差し戻しは /transition ではなく /approval を使用
- 要判断1: DD-006 に応答の形が無いため次を仮定（包みは {systems:[…]} でも配列でも可に実装）: GET systems/<sid> の my_role・counts{documents,items,baselines,links,crs}・policy/p1_min/p2_min/depth_default/degraded_recall/degraded_precision、GET crs/<code> の changes[]・summary{total,p1,p2,p3,open,retest,test_gap}・engine{mode,reason}・approvals[]・job{id,status}
- 要判断2: graph は nodes[{id,kind:'change'|'item',depth,priority,code,text,impact_id,change_id}]・edges[{source,target,type:'link'|'semantic'|'keyword'|'llm'}]、analyze は {job:id} か {job:{id}}、links/suggestions は a_code/a_text/b_code/b_text を仮定。API 担当と突き合わせが必要
- 要判断3: REQ-F-040（採用率・見逃しの推移）は DD-006 に API が無く画面未実装。CR の編集（PATCH crs/<code>）も画面未実装
- 制限: モーダルは Esc で閉じ・閉じた後に元の要素へフォーカスを戻すが、Tab のフォーカス閉じ込めは未実装。メンバー追加は利用者 ID の自由入力
