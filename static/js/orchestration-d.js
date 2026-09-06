/* 指揮（案D: 日々の記録が主役）。
   起動時に 4 本だけ取り、あとはクライアント側で束ねる。
   走行中があるときだけ 10 秒おきに実行の一覧を取り直す。 */
(function () {
  "use strict";

  var LIMIT_RUNS = 400;
  var LIMIT_REPORTS = 200;
  var DAYS = 14;
  var POLL_MS = 10000;

  var GOAL_LABEL = { daily: "今すぐ全部回す", onboard: "保守下に置く" };
  var REPORT_STATE = {
    awaiting: "承認待ち", approved: "承認済み",
    returned: "差し戻し", rejected: "却下"
  };
  var LOAD_ERROR = "読み込みに失敗しました。時間をおいて開き直してください。";

  /* ───────── 通信（この 6 本以外では fetch を呼ばない）───────── */

  function toJson(res) {
    if (!res || !res.ok) { throw new Error("bad response"); }
    return res.json();
  }

  function loadSites() {
    return fetch("/api/healing/sites", { credentials: "same-origin" }).then(toJson);
  }

  function loadProjects() {
    return fetch("/api/healing/projects", { credentials: "same-origin" }).then(toJson);
  }

  function loadRuns() {
    return fetch("/api/orchestration/runs?limit=" + LIMIT_RUNS, { credentials: "same-origin" }).then(toJson);
  }

  function loadReports() {
    return fetch("/api/healing/reports?limit=" + LIMIT_REPORTS, { credentials: "same-origin" }).then(toJson);
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error((data && data.error) || "処理に失敗しました"); }
        return data;
      });
    });
  }

  function sendAb(payload) {
    try {
      fetch("/api/orchestration/ab", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).catch(function () { /* 計測は画面を壊さない */ });
    } catch (err) { /* 同上 */ }
  }

  /* ───────── 日付と文字の道具 ───────── */

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  function parseDate(text) {
    if (!text) { return null; }
    var d = new Date(String(text));
    return isNaN(d.getTime()) ? null : d;
  }

  function dayKeyOf(text) {
    var d = parseDate(text);
    if (!d) { return String(text || "").slice(0, 10); }
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function keyOfDate(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function shortMD(key) {
    var parts = String(key || "").split("-");
    if (parts.length < 3) { return String(key || ""); }
    return Number(parts[1]) + "/" + Number(parts[2]);
  }

  function hhmm(text) {
    var d = parseDate(text);
    if (!d) { return ""; }
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  function cut(text, max) {
    var s = String(text || "").replace(/\s+/g, " ").trim();
    return s.length > max ? s.slice(0, max) + "…" : s;
  }

  /* ───────── 判定（node からも検査できるよう純関数にする）───────── */

  /** その日の最新の実行の状態 → 点の色のクラス。 */
  function dayClass(status) {
    var s = String(status || "");
    if (s === "succeeded" || s === "skipped") { return ""; }
    if (s === "failed") { return "is-ng"; }
    if (s === "waiting_human") { return "is-wait"; }
    return "is-none";
  }

  /**
   * 右上の 1 文と 1 ボタン。
   * state: {awaiting:[{title,id}], latest:run|null, stepLabel, healingStep:bool,
   *         streak:int, nextTime:"07:30", site:"..."}
   */
  function decideNow(state) {
    var s = state || {};
    var awaiting = s.awaiting || [];
    var latest = s.latest || null;
    var step = s.stepLabel || "確認";

    if (awaiting.length >= 1) {
      return {
        lead: "報告書 " + awaiting.length + " 件が承認待ちです。",
        rest: "ほかは自動で片づいています。",
        button: {
          label: "報告書を見る",
          kind: "link",
          href: awaiting.length === 1 ? "/healing/reports/" + awaiting[0].id : "/healing"
        }
      };
    }
    if (latest && latest.status === "waiting_human") {
      return {
        lead: latest.human_action || (step + "の判断をお願いします。"),
        rest: "",
        button: {
          label: "承認画面へ",
          kind: "link",
          href: s.healingStep ? "/healing" : "/autorun/report/" + encodeURIComponent(s.site || "")
        }
      };
    }
    if (latest && latest.status === "failed") {
      var why = cut(latest.error, 60);
      return {
        lead: step + "が失敗しました" + (why ? ": " + why : "。"),
        rest: "",
        button: { label: "もう一度", kind: "retry" }
      };
    }
    if (latest && (latest.status === "running" || latest.status === "queued")) {
      var at = hhmm(latest.started_at);
      return {
        lead: step + "を実行しています" + (at ? "（開始 " + at + "）" : ""),
        rest: "",
        button: { label: "やめる", kind: "cancel", sub: true, runId: latest.run_id }
      };
    }
    return {
      lead: (s.streak || 0) + " 日連続で異常なし。",
      rest: "次は明日 " + (s.nextTime || "07:30") + " に確認します。",
      button: null
    };
  }

  /**
   * 1 サイトの状態タグ。案 B（static/js/orchestration-b.js の decideRow）と
   * 同じ名前・同じ順序で書く。順序を変えるときは両方を同時に直すこと。
   * ctx = { domain, run, awaiting: [...], monitor: {enabled, time} }
   */
  function decideRow(ctx) {
    var c = ctx || {};
    var run = c.run || null;
    var awaiting = c.awaiting || [];
    var monitor = c.monitor || {};

    if (awaiting.length >= 1) { return { rank: 0, state: "要対応", stateClass: "is-act" }; }
    if (run && run.status === "waiting_human") { return { rank: 1, state: "人待ち", stateClass: "is-wait" }; }
    if (run && run.status === "failed") { return { rank: 0, state: "要対応", stateClass: "is-act" }; }
    if (run && (run.status === "running" || run.status === "queued")) {
      return { rank: 2, state: "実行中", stateClass: "is-wait" };
    }
    if (monitor.enabled) { return { rank: 3, state: "見張り中", stateClass: "is-ok" }; }
    return { rank: 4, state: "未設定", stateClass: "is-off" };
  }

  if (typeof module === "object" && module.exports) {
    module.exports = { decideNow: decideNow, dayClass: dayClass, decideRow: decideRow };
  }
  if (typeof document === "undefined") { return; }

  /* ───────── DOM（要素は createElement と textContent だけで組む）───────── */

  var $ = function (id) { return document.getElementById(id); };

  /** 案の記号は画面（body[data-variant]）を正とする。JS 側では持たない。 */
  function variantOf() {
    var body = document.body;
    var name = body && body.dataset ? String(body.dataset.variant || "") : "";
    return name === "b" || name === "d" ? name : "d";
  }

  /** 開くサイト（/orchestration/d?site=... をサーバが body[data-site] へ載せる）。 */
  function siteFromPage() {
    var body = document.body;
    return body && body.dataset ? String(body.dataset.site || "") : "";
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) { node.removeChild(node.firstChild); }
  }

  /* ───────── 画面の状態 ───────── */

  var data = { sites: [], projects: [], runs: [], reports: [] };
  var selectedSite = "";
  var selectedDay = "";
  var timer = null;
  var abSent = false;
  var shownAt = Date.now();

  function showError(message) {
    var box = $("cd-error");
    if (!box) { return; }
    if (message) { box.textContent = message; box.hidden = false; } else { box.hidden = true; }
  }

  function firstAction(label) {
    if (abSent) { return; }
    abSent = true;
    sendAb({ variant: variantOf(), event: "first_action", ms: Date.now() - shownAt, target: String(label || "") });
  }

  function projectOf(site) {
    for (var i = 0; i < data.projects.length; i += 1) {
      if (data.projects[i] && data.projects[i].domain === site) { return data.projects[i]; }
    }
    return null;
  }

  function siteOfProjectId(projectId) {
    for (var i = 0; i < data.projects.length; i += 1) {
      if (data.projects[i] && data.projects[i].project_id === projectId) { return data.projects[i].domain || ""; }
    }
    return "";
  }

  function runsOf(site) {
    var out = data.runs.filter(function (r) { return r && r.domain === site; });
    out.sort(function (a, b) { return String(b.started_at || "").localeCompare(String(a.started_at || "")); });
    return out;
  }

  function reportsOf(site) {
    return data.reports.filter(function (r) { return r && siteOfProjectId(r.project_id) === site; });
  }

  function awaitingOf(site) {
    return reportsOf(site).filter(function (r) { return r.status === "awaiting"; });
  }

  function reportForRun(site, runId) {
    if (!runId) { return null; }
    var list = reportsOf(site);
    for (var i = 0; i < list.length; i += 1) {
      if (list[i].run_id === runId) { return list[i]; }
    }
    return null;
  }

  function currentStep(run) {
    if (!run || !run.steps || !run.steps.length) { return null; }
    var i = run.step_index;
    if (typeof i !== "number" || i < 0 || i >= run.steps.length) { i = run.steps.length - 1; }
    return run.steps[i];
  }

  /** 画面のデータから decideRow へ渡す ctx を組み、状態タグを 1 つ決める。 */
  function decisionOf(site) {
    var project = projectOf(site);
    return decideRow({
      domain: site,
      run: runsOf(site)[0] || null,
      awaiting: awaitingOf(site),
      monitor: {
        enabled: !!(project && project.monitor_enabled),
        time: (project && project.monitor_time) || ""
      }
    });
  }

  function siteRank(site) { return decisionOf(site).rank; }

  function siteSubText(site) {
    var runs = runsOf(site);
    var latest = runs[0] || null;
    if (!latest) { return "まだ一度も見に行っていません"; }
    var when = shortMD(dayKeyOf(latest.started_at)) + " " + hhmm(latest.started_at);
    var awaiting = awaitingOf(site).length;
    if (awaiting) { return when + "・報告書が承認待ち"; }
    if (latest.status === "failed") { return when + "・うまくいきませんでした"; }
    if (latest.status === "waiting_human") { return when + "・あなたの判断待ち"; }
    if (latest.status === "running" || latest.status === "queued") { return when + "・実行しています"; }
    return when + "・" + streakOf(site) + " 日連続で異常なし";
  }

  function dayMap(site) {
    var map = {};
    runsOf(site).forEach(function (run) {
      var key = dayKeyOf(run.started_at);
      if (!map[key]) { map[key] = []; }
      map[key].push(run);
    });
    return map;
  }

  function streakOf(site) {
    var map = dayMap(site);
    var count = 0;
    var cursor = new Date();
    for (var i = 0; i < 60; i += 1) {
      var list = map[keyOfDate(cursor)];
      if (list && list.length) {
        var st = list[0].status;
        if (st === "failed" || st === "waiting_human") { break; }
        if (st === "succeeded" || st === "skipped") { count += 1; }
      }
      cursor.setDate(cursor.getDate() - 1);
    }
    return count;
  }

  function nextTimeOf(site) {
    var project = projectOf(site);
    if (project && project.monitor_time) { return String(project.monitor_time); }
    var latest = runsOf(site)[0];
    return (latest && hhmm(latest.started_at)) || "07:30";
  }

  /* ───────── 左: サイトの一覧 ───────── */

  function renderSites() {
    var list = $("cd-list");
    var count = $("cd-count");
    if (!list) { return; }
    clear(list);

    var names = data.sites.map(function (s) { return s && s.domain; }).filter(Boolean);
    data.projects.forEach(function (p) {
      if (p && p.domain && names.indexOf(p.domain) === -1) { names.push(p.domain); }
    });
    if (count) { count.textContent = names.length + " 件"; }

    if (!names.length) {
      list.appendChild(el("p", "cd-empty", "01 ドキュメントでサイトを観測すると、ここに並びます。"));
      return;
    }

    names.sort(function (a, b) {
      var d = siteRank(a) - siteRank(b);
      return d !== 0 ? d : a.localeCompare(b);
    });
    if (!selectedSite || names.indexOf(selectedSite) === -1) { selectedSite = names[0]; }

    names.forEach(function (site) {
      var decision = decisionOf(site);
      var row = el("button", "cd-site " + decision.stateClass);
      row.type = "button";
      row.dataset.site = site;
      row.appendChild(el("span", "cd-flag"));
      var body = el("span");
      body.appendChild(el("span", "cd-nm", site));
      body.appendChild(el("span", "cd-sub", siteSubText(site)));
      row.appendChild(body);
      row.appendChild(el("span", "cd-tag " + decision.stateClass, decision.state));
      row.addEventListener("click", function () {
        firstAction(site);
        selectSite(site);
      });
      list.appendChild(row);
    });
    markSelection();
  }

  /** 選択中の 1 行だけに印を移す。一覧は作り直さない（行が飛ばない）。 */
  function markSelection() {
    var list = $("cd-list");
    if (!list) { return; }
    var rows = list.querySelectorAll(".cd-site");
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i];
      var on = row.dataset.site === selectedSite;
      row.classList.toggle("is-on", on);
      row.classList.toggle("is-selected", on);
      row.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) { row.setAttribute("aria-current", "true"); } else { row.removeAttribute("aria-current"); }
    }
  }

  /** サイトを選び直す。印の付け替えと右側の描き直しだけを行う。 */
  function selectSite(site) {
    if (!site) { return; }
    selectedSite = site;
    selectedDay = "";
    markSelection();
    renderLog();
  }

  /* ───────── 右: 記録 ───────── */

  function renderNow() {
    var title = $("cd-log-title");
    var now = $("cd-now");
    var slot = $("cd-cta-slot");
    if (!title || !now || !slot) { return; }

    clear(now);
    clear(slot);
    if (!selectedSite) {
      title.textContent = "記録";
      now.appendChild(document.createTextNode("左でサイトを選ぶと、その 14 日ぶんの記録が出ます。"));
      return;
    }
    title.textContent = selectedSite + " の記録";

    var runs = runsOf(selectedSite);
    var latest = runs[0] || null;
    var step = currentStep(latest);
    var view = decideNow({
      awaiting: awaitingOf(selectedSite).map(function (r) { return { id: r.report_id, title: r.title }; }),
      latest: latest,
      stepLabel: (step && step.label) || "確認",
      healingStep: !!(step && step.name === "healing"),
      streak: streakOf(selectedSite),
      nextTime: nextTimeOf(selectedSite),
      site: selectedSite
    });

    now.appendChild(el("b", "", view.lead));
    if (view.rest) { now.appendChild(document.createTextNode(view.rest)); }

    if (!view.button) { return; }
    var b = view.button;
    if (b.kind === "link") {
      var link = el("a", "cd-cta", b.label);
      link.href = b.href;
      link.addEventListener("click", function () { firstAction(b.label); });
      slot.appendChild(link);
      return;
    }
    var btn = el("button", "cd-cta" + (b.sub ? " is-sub" : ""), b.label);
    btn.type = "button";
    btn.addEventListener("click", function () {
      firstAction(b.label);
      btn.disabled = true;
      var action = b.kind === "cancel"
        ? postJson("/api/orchestration/runs/" + encodeURIComponent(b.runId) + "/cancel", {})
        : postJson("/api/orchestration/runs", { domain: selectedSite, goal: "daily" });
      action.then(function () {
        showError("");
        return refreshRuns();
      }).catch(function (err) {
        btn.disabled = false;
        showError((err && err.message) || "処理に失敗しました。");
      });
    });
    slot.appendChild(btn);
  }

  function renderStrip() {
    var strip = $("cd-strip");
    if (!strip) { return; }
    clear(strip);
    if (!selectedSite) { return; }

    var map = dayMap(selectedSite);
    var start = new Date();
    start.setDate(start.getDate() - (DAYS - 1));
    if (!selectedDay) { selectedDay = keyOfDate(new Date()); }

    for (var i = 0; i < DAYS; i += 1) {
      var d = new Date(start.getTime());
      d.setDate(start.getDate() + i);
      var key = keyOfDate(d);
      var list = map[key] || [];
      var status = list.length ? list[0].status : "";
      var cls = "cd-day " + dayClass(status);
      if (key === selectedDay) { cls += " is-on"; }
      var cell = el("button", cls.trim());
      cell.type = "button";
      cell.title = shortMD(key) + "・" + dayHeadline(list);
      cell.setAttribute("aria-pressed", key === selectedDay ? "true" : "false");
      cell.appendChild(el("span", "cd-d", shortMD(key)));
      cell.appendChild(el("span", "cd-dot"));
      cell.dataset.day = key;
      cell.addEventListener("click", function (ev) {
        var target = ev.currentTarget;
        firstAction("日を選ぶ");
        selectedDay = target.dataset.day;
        renderStrip();
        renderBody();
      });
      strip.appendChild(cell);
    }
  }

  function dayHeadline(list) {
    if (!list || !list.length) { return "実行なし"; }
    var run = list[0];
    if (run.status === "failed") { return "うまくいきませんでした"; }
    if (run.status === "waiting_human") { return "あなたの判断待ち"; }
    if (run.status === "running" || run.status === "queued") { return "実行しています"; }
    if (run.status === "cancelled") { return "途中でやめました"; }
    return "異常なし";
  }

  function renderSteps(run) {
    var ul = el("ul", "cd-steps");
    var steps = (run && run.steps) || [];
    steps.forEach(function (step, index) {
      var cls = "";
      if (step.status === "succeeded" || step.status === "skipped") { cls = "done"; }
      else if (index === run.step_index && (run.status === "running" || run.status === "waiting_human")) { cls = "now"; }
      ul.appendChild(el("li", cls, step.label || "確認"));
    });
    return ul;
  }

  function renderBody() {
    var body = $("cd-body");
    if (!body) { return; }
    clear(body);
    if (!selectedSite) { return; }

    var map = dayMap(selectedSite);
    var list = map[selectedDay] || [];
    var run = list[0] || null;
    var today = keyOfDate(new Date());

    var tone = !run ? "" : (run.status === "failed" ? " is-ng" : (run.status === "succeeded" || run.status === "skipped" ? " is-ok" : ""));
    var box = el("div", "cd-sel" + tone);
    var head = shortMD(selectedDay).replace("/", "月") + "日" + (selectedDay === today ? "（今日）" : "");
    box.appendChild(el("h3", "", head));

    var line = el("p", "cd-line");
    if (!run) {
      line.appendChild(document.createTextNode("この日は実行していません。"));
    } else {
      var at = hhmm(run.started_at);
      var report = reportForRun(selectedSite, run.run_id);
      if (run.status === "failed") {
        line.appendChild(document.createTextNode(at + " に見に行きましたが、"));
        line.appendChild(el("em", "", "うまくいきませんでした"));
        line.appendChild(document.createTextNode("。" + cut(run.error, 80)));
      } else if (run.status === "waiting_human") {
        line.appendChild(document.createTextNode(at + " に見に行き、"));
        line.appendChild(el("em", "", "直しと報告書"));
        line.appendChild(document.createTextNode("まで用意してあります。残っているのは、あなたが内容を認めるかどうかの判断だけです。"));
      } else if (report) {
        line.appendChild(document.createTextNode(at + " に見に行き、"));
        line.appendChild(el("em", "", "壊れ"));
        line.appendChild(document.createTextNode("を見つけて直しました。"));
      } else {
        line.appendChild(document.createTextNode(at + " に全ページを見に行き、異常はありませんでした。"));
      }
    }
    box.appendChild(line);
    box.appendChild(renderSteps(run));

    var acts = el("div", "cd-acts");
    if (run) {
      var report2 = reportForRun(selectedSite, run.run_id);
      if (run.status === "waiting_human") {
        var key = el("a", "cd-btn is-key", "内容を認めて出す");
        key.href = "/autorun/report/" + encodeURIComponent(selectedSite);
        key.addEventListener("click", function () { firstAction("内容を認めて出す"); });
        acts.appendChild(key);
      }
      if (report2) {
        var open = el("a", "cd-btn", "報告書「" + (report2.title || "無題") + "」を開く");
        open.href = "/healing/reports/" + encodeURIComponent(report2.report_id);
        open.addEventListener("click", function () { firstAction("報告書を開く"); });
        acts.appendChild(open);
      }
    }
    if (acts.childNodes.length) { box.appendChild(acts); }
    body.appendChild(box);

    body.appendChild(renderPast());
    body.appendChild(renderFoot(map));
  }

  function renderPast() {
    var ul = el("ul", "cd-past");
    var runs = runsOf(selectedSite).slice(0, DAYS);
    if (!runs.length) {
      ul.appendChild(el("li", "ok", "まだ記録がありません。"));
      return ul;
    }
    runs.forEach(function (run) {
      var report = reportForRun(selectedSite, run.run_id);
      var quiet = (run.status === "succeeded" || run.status === "skipped") && !report;
      var li = el("li", quiet ? "ok" : "");
      li.appendChild(el("b", "", shortMD(dayKeyOf(run.started_at)) + " " + hhmm(run.started_at)));
      var text = "　" + (GOAL_LABEL[run.goal] || "確認") + " → " + dayHeadline([run]);
      if (report) {
        text += " → 直して報告書「" + (report.title || "無題") + "」" + (REPORT_STATE[report.status] || report.status || "");
        if (report.pr_number) { text += "・PR #" + report.pr_number; }
      }
      li.appendChild(document.createTextNode(text));
      ul.appendChild(li);
    });
    return ul;
  }

  function renderFoot(map) {
    var days = 0;
    var fixed = 0;
    var cursor = new Date();
    cursor.setDate(cursor.getDate() - (DAYS - 1));
    for (var i = 0; i < DAYS; i += 1) {
      var list = map[keyOfDate(cursor)];
      if (list && list.length) {
        days += 1;
        if (list[0].status === "failed" || reportForRun(selectedSite, list[0].run_id)) { fixed += 1; }
      }
      cursor.setDate(cursor.getDate() + 1);
    }
    var foot = el("div", "cd-foot");
    foot.appendChild(el("p", "", "この 14 日は " + days + " 日ぶんの記録があり、うち " + fixed
      + " 日は壊れを見つけて直しました。顧客への月次報告にそのまま使えます。"));
    var out = el("a", "cd-btn", "14 日ぶんを書き出す");
    out.href = "/healing/reports";
    out.addEventListener("click", function () { firstAction("14 日ぶんを書き出す"); });
    foot.appendChild(out);
    return foot;
  }

  function renderLog() {
    renderNow();
    renderStrip();
    renderBody();
  }

  function renderAll() {
    renderSites();
    renderLog();
    schedulePoll();
  }

  /* ───────── 走行中だけ取り直す ───────── */

  function hasLive() {
    return data.runs.some(function (r) { return r && (r.status === "running" || r.status === "queued"); });
  }

  function refreshRuns() {
    return loadRuns().then(function (res) {
      data.runs = (res && res.runs) || [];
      renderAll();
    }).catch(function () { showError(LOAD_ERROR); });
  }

  function schedulePoll() {
    if (timer) { clearInterval(timer); timer = null; }
    if (!hasLive()) { return; }
    timer = setInterval(function () { refreshRuns(); }, POLL_MS);
  }

  /* ───────── 保守下に置く ───────── */

  function setupAdd() {
    var dialog = $("cd-dialog");
    var open = $("cd-add");
    var select = $("cd-add-site");
    var url = $("cd-add-url");
    var form = $("cd-add-form");
    var cancel = $("cd-add-cancel");
    if (!dialog || !open || !select || !url || !form) { return; }

    function fill() {
      clear(select);
      var names = data.sites.map(function (s) { return s && s.domain; }).filter(Boolean);
      names.sort(function (a, b) { return siteRank(b) - siteRank(a); });
      names.forEach(function (site) {
        var opt = document.createElement("option");
        opt.value = site;
        opt.textContent = site;
        select.appendChild(opt);
      });
      url.value = names.length ? "http://" + names[0] + "/" : "";
    }

    select.addEventListener("change", function () {
      url.value = select.value ? "http://" + select.value + "/" : "";
    });
    open.addEventListener("click", function () {
      firstAction("保守下に置く");
      fill();
      if (typeof dialog.showModal === "function") { dialog.showModal(); } else { dialog.setAttribute("open", "open"); }
    });
    if (cancel) {
      cancel.addEventListener("click", function () {
        if (typeof dialog.close === "function") { dialog.close(); } else { dialog.removeAttribute("open"); }
      });
    }
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var site = select.value;
      if (!site) { showError("サイトを選んでください。"); return; }
      postJson("/api/orchestration/runs", {
        domain: site, goal: "onboard", params: { url: url.value || ("http://" + site + "/") }
      }).then(function () {
        showError("");
        if (typeof dialog.close === "function") { dialog.close(); } else { dialog.removeAttribute("open"); }
        selectedSite = site;
        return refreshRuns();
      }).catch(function (err) {
        showError((err && err.message) || "保守下に置けませんでした。");
      });
    });
  }

  /* ───────── 起動 ───────── */

  function boot() {
    setupAdd();
    selectedSite = siteFromPage();
    sendAb({ variant: variantOf(), event: "view", ms: 0, target: "" });
    Promise.all([
      loadSites().catch(function () { return { sites: [] }; }),
      loadProjects().catch(function () { return { projects: [] }; }),
      loadRuns().catch(function () { return null; }),
      loadReports().catch(function () { return { reports: [] }; })
    ]).then(function (res) {
      data.sites = (res[0] && res[0].sites) || [];
      data.projects = (res[1] && res[1].projects) || [];
      if (res[2] === null) { showError(LOAD_ERROR); } else { data.runs = (res[2] && res[2].runs) || []; }
      data.reports = (res[3] && res[3].reports) || [];
      renderAll();
    }).catch(function () {
      showError(LOAD_ERROR);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
