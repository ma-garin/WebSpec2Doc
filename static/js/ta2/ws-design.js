/* System 02 テスト設計ボード。URL（?design=<設計>&case=<ID>）を正として選択を復元する。 */
(function () {
  "use strict";
  var sec = document.getElementById("ws-design-sec");
  if (!sec) return;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]; }); };
  var B = { data: null, sel: "" };

  function setState(s) {
    sec.dataset.state = s;
    sec.querySelectorAll(".p1-states button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.set === s)); });
  }
  function banner(msg, warn) {
    var el = $("p2-banner");
    el.hidden = !msg; el.textContent = msg || ""; el.classList.toggle("is-warn", !!warn);
  }
  function url(k, v) {
    var u = new URL(location.href);
    if (v) u.searchParams.set(k, v); else u.searchParams.delete(k);
    history.replaceState(null, "", u);
  }
  function api(path, opt) {
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, body: j }; });
    });
  }
  function failText(res) {
    if (res.status === 403) return "この画面は管理者だけが使えます。管理者に「テスト自動化」の権限付与を依頼してください。";
    if (res.status === 409) return (res.body.error || "他の人が先に更新しました。") ;
    return (res.body && res.body.error ? res.body.error : "読み込めませんでした。") + " 時間をおいて「再読み込み」を押してください。";
  }

  function loadSources() {
    setState("loading");
    return api("/api/ta2/design/sources").then(function (res) {
      if (res.status !== 200) { banner(failText(res)); setState("error"); return; }
      var src = res.body.sources || [];
      var want = new URL(location.href).searchParams.get("design") || "";
      $("p2-src").innerHTML = src.map(function (s) {
        return '<option value="' + esc(s.domain) + '">' + esc(s.label) + "（" + s.cases + " 件）</option>";
      }).join("");
      if (!src.length) { $("p2-origin").textContent = ""; setState("empty"); return; }
      var pick = src.some(function (s) { return s.domain === want; }) ? want : src[0].domain;
      $("p2-src").value = pick;
      return loadBoard(pick);
    }).catch(function () { banner("サーバに接続できませんでした。ネットワークを確認して再読み込みしてください。"); setState("error"); });
  }

  function loadBoard(domain) {
    setState("loading"); banner("");
    url("design", domain);
    return api("/api/ta2/design?domain=" + encodeURIComponent(domain)).then(function (res) {
      if (res.status !== 200) { banner(failText(res)); setState("error"); return; }
      B.data = res.body;
      $("p2-origin").textContent = B.data.origin;
      $("p2-note").hidden = !B.data.note; $("p2-note").textContent = B.data.note || "";
      B.sel = new URL(location.href).searchParams.get("case") || "";
      render();
      setState(B.data.cases.length ? "normal" : "empty");
    }).catch(function () { banner("サーバに接続できませんでした。ネットワークを確認して再読み込みしてください。"); setState("error"); });
  }

  function visible() {
    var q = ($("p2-q").value || "").trim().toLowerCase(), st = $("p2-st").value;
    return B.data.cases.filter(function (c) {
      if (st && c.state !== st) return false;
      return !q || (c.name + " " + c.requirement_id + " " + c.case_id).toLowerCase().indexOf(q) >= 0;
    });
  }

  function render() {
    var rows = visible();
    $("p2-rows").innerHTML = rows.map(function (c) {
      return '<tr data-id="' + esc(c.id) + '" tabindex="0" aria-selected="' + (c.id === B.sel) + '" class="' + (c.changed ? "is-changed" : "") + '">' +
        "<td>" + esc(c.name || c.id) + (c.changed ? ' <span class="p1-tag">変更</span>' : "") + "</td><td>" + esc(c.requirement_id || "なし") +
        "</td><td>" + esc(c.viewpoint) + "</td><td>" + esc(c.expected || "要確認（未記入）") +
        '</td><td><span class="p1-tag st-' + esc(c.state) + '">' + esc(c.state) + "</span></td></tr>";
    }).join("");
    $("p2-noresult").hidden = rows.length > 0 || !B.data.cases.length;
    renderSide(); renderGates();
  }

  function renderSide() {
    var c = (B.data.cases || []).filter(function (x) { return x.id === B.sel; })[0];
    if (!c) { $("p2-side").innerHTML = '<p class="ws-muted">ケースを選ぶと、根拠と手順が表示されます。</p>'; return; }
    var f = c.findings.length ? "<ul>" + c.findings.map(function (x) { return "<li>" + esc(x.id) + " " + esc(x.kind) + " " + esc(x.severity) + "</li>"; }).join("") + "</ul>" : "<p>結びつく指摘はありません。</p>";
    $("p2-side").innerHTML = "<b>" + esc(c.name || c.id) + "</b><div class=\"p1-who\">" + esc(c.id) + " ・ 根拠の区分: " + esc(c.basis) + "</div>" +
      "<h4>根拠要件</h4><p>" + esc(c.requirement_id || "要件との結びつきはありません") + (c.requirement_text ? "<br>" + esc(c.requirement_text) : "") + "</p>" +
      "<h4>関連する指摘</h4>" + f + "<h4>観点</h4><p>" + esc(c.viewpoint) + "</p>" +
      "<h4>手順</h4><ol>" + c.steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ol>" +
      "<h4>期待結果</h4><p>" + esc(c.expected || "要確認（未記入）") + "</p><h4>状態</h4><p>" + esc(c.state) +
      (c.last_at ? "（最終実行 " + esc(c.last_at) + "）" : "（まだ実行していません）") + "</p>";
  }

  function names(list) {
    return list.map(function (x) { return '<a data-go="' + esc(x.id) + '">' + esc(x.name || x.id) + "</a>"; }).join("・");
  }
  function gateHtml(g) {
    var cls = g.verdict === "合格" ? "ok" : (g.verdict === "不合格" ? "ng" : "hold");
    var h = '<div class="p1-g-h"><span class="tt">' + esc(g.title) + '</span><span class="p1-verdict ' + cls + '">' + esc(g.verdict) + "</span><small>" + g.passed + " / " + g.total + " 件合格</small></div><ul>";
    if (!g.total) h += "<li>対象のケースがありません。</li>";
    if (g.failed.length) h += '<li><span class="k">失敗 ' + g.failed.length + " 件</span>: " + names(g.failed) + "</li>";
    if (g.needs_check.length) h += '<li><span class="k">要確認 ' + g.needs_check.length + " 件</span>: " + names(g.needs_check) + "</li>";
    if (g.missing_links.length) h += '<li><span class="k">欠落リンク</span><ul>' + g.missing_links.map(function (m) { return "<li>" + esc(m) + "</li>"; }).join("") + "</ul></li>";
    h += '<li><span class="k">未検証（未実行）' + g.not_run.length + " 件</span>" + (g.not_run.length ? ": " + names(g.not_run) : ": なし") + "</li></ul>";
    return h;
  }
  function renderGates() {
    $("p2-gate-all").innerHTML = gateHtml(B.data.gates[0]);
    $("p2-gate-chg").innerHTML = gateHtml(B.data.gates[1]) + '<small class="p1-who">比較の起点: ' + esc(B.data.changed_basis) + "</small>";
    var b = B.data.baseline;
    $("p2-base").innerHTML = b.at ? '<div class="p1-who">最終記録 ' + esc(b.at) + " ・ " + esc(b.by) + "</div>" +
      (b.history.length > 1 ? "<ul>" + b.history.slice(0, -1).reverse().map(function (x) { return "<li>" + esc(x.at) + " " + esc(x.by) + "（" + x.cases + " 件）</li>"; }).join("") + "</ul>" : "")
      : '<div class="p1-who">まだ基準を記録していません。</div>';
  }

  function recordBaseline() {
    var btn = $("p2-baseline"); btn.disabled = true;
    api("/api/ta2/design/baseline", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain: B.data.domain, expected_at: B.data.baseline.at || "" }) }).then(function (res) {
      btn.disabled = false;
      if (res.status === 409) { banner(failText(res), true); setState("conflict"); return; }
      if (res.status !== 200) { banner(failText(res)); return; }
      loadBoard(B.data.domain);
    }).catch(function () { btn.disabled = false; banner("記録できませんでした。ネットワークを確認してもう一度押してください。"); });
  }

  $("p2-src").addEventListener("change", function () { url("case", ""); loadBoard(this.value); });
  $("p2-q").addEventListener("input", function () { if (B.data) render(); });
  $("p2-st").addEventListener("change", function () { if (B.data) render(); });
  $("p2-clear").addEventListener("click", function () { $("p2-q").value = ""; $("p2-st").value = ""; render(); });
  $("p2-baseline").addEventListener("click", recordBaseline);
  function pick(id) { B.sel = id; url("case", id); render(); }
  sec.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-id]"), a = e.target.closest("a[data-go]");
    if (tr) pick(tr.dataset.id); else if (a) pick(a.dataset.go);
  });
  sec.addEventListener("keydown", function (e) { var tr = e.target.closest("tr[data-id]"); if (tr && e.key === "Enter") pick(tr.dataset.id); });
  sec.querySelectorAll(".p1-states button").forEach(function (b) {
    b.addEventListener("click", function () {
      var s = b.dataset.set;
      banner(s === "error" ? "読み込めませんでした。時間をおいて再読み込みしてください。" : (s === "conflict" ? "他の人が先に基準を記録しました。画面を再読み込みしてから記録してください。" : ""), s === "conflict");
      setState(s);
    });
  });
  var s0 = new URL(location.href).searchParams.get("state");
  loadSources().then(function () { if (s0) { var b = sec.querySelector('.p1-states button[data-set="' + s0 + '"]'); if (b) b.click(); } });
})();
