/* =============================================================================
 * mock-backend.js — WebSpec2Doc の本物フロントエンドを「サンプル値」で駆動する
 *
 * このファイルは実アプリのJSより前に読み込まれ、window.fetch と <img>.src を
 * フックして、実サーバから採取済みの応答（window.__FIXTURES__）を再生する。
 * バックエンド（Flask + Playwright）は一切動かさず、GitHub Pages 上の静的配信だけで
 * URL入力→画面分析→条件設定→解析→レポート の実フローが動作する。
 *
 * 対象データは同梱デモサイト DemoMart を実際に解析した記録（実測値）。
 * 採取元・再生対象は pages/app/fixtures/。再採取は scripts と harvest で再生成する。
 * ========================================================================== */
(function () {
  "use strict";

  var FIX = window.__FIXTURES__ || {};
  var BASE = new URL(".", document.currentScript ? document.currentScript.src : location.href);
  var BASEPATH = BASE.pathname; // 例: "/app/" (ローカル) / "/WebSpec2Doc/app/" (Pages)
  var origFetch = window.fetch ? window.fetch.bind(window) : null;
  var queues = Object.create(null);

  function pathOf(u) {
    try { return new URL(u, location.href).pathname; } catch (e) { return String(u); }
  }
  function rebase(rel) { return new URL(rel, BASE).href; }
  function isPassthrough(p) {
    return p.indexOf("/fixtures/") !== -1 || p.indexOf("/static/") !== -1 ||
           /\.(css|js|png|jpg|jpeg|svg|webp|woff2?|ttf|ico|map)$/i.test(p);
  }

  /* 絶対パス /static/... を app ベースへ再ベース（動的<script>/<img>用） */
  function rebaseStatic(v) {
    try {
      var s = String(v);
      var i = s.indexOf("/static/");
      if (i !== -1) return rebase(s.slice(i + 1)); // "/static/x" -> "static/x"
    } catch (e) {}
    return v;
  }
  /* /preview?path=.../<name>.png をバンドル済みスクショへ写像 */
  function previewShot(v) {
    try {
      var s = String(v);
      var m = /[?&]path=([^&]+)/.exec(s);
      if (m) {
        var decoded = decodeURIComponent(m[1]);
        var base = decoded.split("/").pop();
        if (/\.(png|jpg|jpeg|webp)$/i.test(base)) return rebase("fixtures/screenshots/" + base);
      }
    } catch (e) {}
    return null;
  }

  /* 同一キーが複数採取されている場合は順に返し、尽きたら最後を繰り返す */
  function take(key) {
    var arr = FIX[key];
    if (!arr || !arr.length) return null;
    if (!(key in queues)) queues[key] = arr.slice();
    var q = queues[key];
    return q.length > 1 ? q.shift() : q[0];
  }

  /* live-screenshot 用の画像URL列（プレビューの「動き」を再現） */
  var liveShots = ((FIX["GET /api/live-screenshot"] || [])
    .concat(FIX["GET /api/autorun/live-screenshot"] || []))
    .filter(function (e) { return e.blob; })
    .map(function (e) { return rebase(e.blob); });
  var liveIdx = 0;

  function isStream(key, entry) {
    var ct = entry.ct || "";
    if (ct.indexOf("event-stream") !== -1) return true;
    if (key === "POST /run") return true;
    if (ct.indexOf("text/plain") !== -1 && (entry.body || "").indexOf("CRAWL_EVENT") !== -1) return true;
    return false;
  }

  /* 採取した本文を、行ごとに時間差配信して「ライブ」な進捗を再現する */
  function streamResponse(entry) {
    var body = entry.body || "";
    var lines = body.split(/(?<=\n)/);
    var enc = new TextEncoder();
    var stream = new ReadableStream({
      start: function (ctrl) {
        var i = 0;
        (function push() {
          if (i >= lines.length) { try { ctrl.close(); } catch (e) {} return; }
          try { ctrl.enqueue(enc.encode(lines[i++])); } catch (e) { return; }
          setTimeout(push, 45);
        })();
      }
    });
    return new Response(stream, {
      status: entry.status || 200,
      headers: { "content-type": entry.ct || "text/plain; charset=utf-8" }
    });
  }

  function blobResponse(entry) {
    return origFetch(rebase(entry.blob)).then(function (r) { return r.blob(); }).then(function (b) {
      return new Response(b, {
        status: entry.status || 200,
        headers: { "content-type": entry.ct || "application/octet-stream" }
      });
    });
  }

  function jsonResponse(body, status) {
    return new Response(body == null ? "{}" : body, {
      status: status || 200,
      headers: { "content-type": "application/json; charset=utf-8" }
    });
  }

  window.fetch = function (input, init) {
    var url, method;
    try {
      url = (typeof input === "string") ? input : (input && input.url) || String(input);
      method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
    } catch (e) {
      return origFetch ? origFetch(input, init) : Promise.reject(e);
    }
    var p = pathOf(url);
    if (isPassthrough(p)) return origFetch(input, init);

    var key = method + " " + p;
    var entry = take(key);
    try {
      if (entry) {
        if (entry.blob) return blobResponse(entry);
        if (isStream(key, entry)) return Promise.resolve(streamResponse(entry));
        return Promise.resolve(new Response(entry.body || "", {
          status: entry.status || 200,
          headers: { "content-type": entry.ct || "application/json; charset=utf-8" }
        }));
      }
    } catch (e) {
      console.error("[mock] build response failed", key, e);
      return Promise.resolve(jsonResponse("{}"));
    }

    /* /preview はファイル配信エンドポイント: 画像はスクショへ、JSONは採取本文へ */
    if (p === "/preview" || p === "/download") {
      var shot = previewShot(url);
      if (shot) return blobResponse({ blob: shot.replace(BASE.href, ""), ct: "image/png" });
      // .json 等は採取済み本文で代替
      if (entry && entry.body) return Promise.resolve(new Response(entry.body, { status: 200, headers: { "content-type": entry.ct || "application/json" } }));
    }

    /* 未採取のAPIは、アプリを止めないよう無害な空応答を返す */
    if (/^\/(api|run|schedule|review|traceability|preview|download|report)\b/.test(p)) {
      console.warn("[mock] unmatched endpoint ->", key);
      // 配列を期待する一覧系は [] を返して描画エラーを避ける
      if (/history|snapshots|users|tokens|jobs|cases|list/.test(p)) return Promise.resolve(jsonResponse("[]"));
      return Promise.resolve(jsonResponse("{}"));
    }
    return origFetch ? origFetch(input, init) : Promise.resolve(jsonResponse("{}"));
  };

  /* <img>.src を書き換え: ライブプレビュー→採取画像 / スクショ→バンドル / 絶対static→再ベース */
  try {
    var idesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
    if (idesc && idesc.set) {
      Object.defineProperty(HTMLImageElement.prototype, "src", {
        configurable: true, enumerable: true,
        get: function () { return idesc.get.call(this); },
        set: function (v) {
          try {
            var pp = pathOf(v);
            if ((pp === "/api/live-screenshot" || pp === "/api/autorun/live-screenshot") && liveShots.length) {
              v = liveShots[liveIdx++ % liveShots.length];
            } else if (pp === "/preview" || pp === "/download") {
              var shot = previewShot(v); if (shot) v = shot;
            } else if (String(v).indexOf("/static/") !== -1) {
              v = rebaseStatic(v);
            }
          } catch (e) {}
          idesc.set.call(this, v);
        }
      });
    }
  } catch (e) { console.warn("[mock] img.src patch failed", e); }

  /* innerHTML 経由で挿入される <img src="/preview?..."> / "/static/" を事前に書き換える
   * （属性由来のsrcはプロパティsetterで捕捉できないため、HTML文字列を変換して404を防ぐ） */
  function rewriteHtml(html) {
    if (html.indexOf("/preview") === -1 && html.indexOf("/static/") === -1) return html;
    html = html.replace(/(["'])\/(?:preview|download)\?path=([^"']+?\.(?:png|jpe?g|webp))\1/gi,
      function (_m, q, enc) {
        var base; try { base = decodeURIComponent(enc).split("/").pop(); } catch (e) { base = enc.split("/").pop(); }
        return q + BASEPATH + "fixtures/screenshots/" + base + q;
      });
    html = html.replace(/(["'(=])\/static\//g, "$1" + BASEPATH + "static/");
    return html;
  }
  try {
    var hdesc = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
    if (hdesc && hdesc.set) {
      Object.defineProperty(Element.prototype, "innerHTML", {
        configurable: true, enumerable: true,
        get: function () { return hdesc.get.call(this); },
        set: function (html) {
          try { html = rewriteHtml(String(html)); } catch (e) {}
          hdesc.set.call(this, html);
        }
      });
    }
    var origIAH = Element.prototype.insertAdjacentHTML;
    Element.prototype.insertAdjacentHTML = function (pos, html) {
      try { html = rewriteHtml(String(html)); } catch (e) {}
      return origIAH.call(this, pos, html);
    };
  } catch (e) { console.warn("[mock] innerHTML patch failed", e); }

  /* 動的 <script src="/static/..."> を app ベースへ再ベース（mermaid 等） */
  try {
    var sdesc = Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype, "src");
    if (sdesc && sdesc.set) {
      Object.defineProperty(HTMLScriptElement.prototype, "src", {
        configurable: true, enumerable: true,
        get: function () { return sdesc.get.call(this); },
        set: function (v) {
          try { if (String(v).indexOf("/static/") !== -1) v = rebaseStatic(v); } catch (e) {}
          sdesc.set.call(this, v);
        }
      });
    }
  } catch (e) { console.warn("[mock] script.src patch failed", e); }

  /* 保険: EventSource を使う分岐が来ても固まらないように最小シムを用意 */
  try {
    var NativeES = window.EventSource;
    window.EventSource = function (u) {
      var self = this;
      this.readyState = 0;
      this.onmessage = null; this.onerror = null; this.onopen = null;
      var key = "GET " + pathOf(u);
      var entry = (FIX[key] || [])[0];
      setTimeout(function () {
        self.readyState = 1;
        if (self.onopen) try { self.onopen({}); } catch (e) {}
        var body = entry && entry.body ? entry.body : "";
        body.split(/\n\n/).forEach(function (frame) {
          var m = /^data:\s?(.*)$/m.exec(frame);
          if (m && self.onmessage) try { self.onmessage({ data: m[1] }); } catch (e) {}
        });
      }, 30);
      this.close = function () { self.readyState = 2; };
      this.addEventListener = function (t, cb) { if (t === "message") self.onmessage = cb; if (t === "error") self.onerror = cb; if (t === "open") self.onopen = cb; };
      this.removeEventListener = function () {};
    };
    window.EventSource.__native = NativeES;
  } catch (e) {}

  /* 「サンプルデータで動作するデモ」であることを示す控えめなバッジ */
  function addBadge() {
    try {
      if (document.getElementById("__demo_badge__")) return;
      var el = document.createElement("div");
      el.id = "__demo_badge__";
      el.innerHTML = "● サンプルデータで動作するデモ &nbsp;<a href=\"../\" style=\"color:#fff;text-decoration:underline\">紹介ページへ</a>";
      el.style.cssText = [
        "position:fixed", "z-index:99999", "right:12px", "bottom:12px",
        "background:rgba(13,71,161,.94)", "color:#fff", "font:600 12px/1.4 'Noto Sans JP',sans-serif",
        "padding:8px 12px", "border-radius:9999px", "box-shadow:0 2px 8px rgba(0,0,0,.25)",
        "pointer-events:auto", "max-width:88vw"
      ].join(";");
      (document.body || document.documentElement).appendChild(el);
    } catch (e) {}
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addBadge);
  else addBadge();

  console.info("[mock] WebSpec2Doc サンプル駆動モード有効 — fixtures:", Object.keys(FIX).length, "endpoints");
})();
