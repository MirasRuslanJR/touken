/* =====================================================================
   Изолят — front-end SPA for the psychologist (vanilla JS + vis-network).
   ===================================================================== */
(function () {
  "use strict";

  var PALETTE = ["#2563eb", "#0ea5e9", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f43f5e", "#64748b", "#84cc16"];
  var QLABEL = { cinema: "Кино", project: "Проект", alone: "«Часто один»" };
  var DEFAULT_QUESTIONS = [
    { key: "cinema", text: "С кем бы ты пошёл в кино?", hint: "положительный выбор" },
    { key: "project", text: "С кем хотел бы делать проект?", hint: "положительный выбор" },
    { key: "alone", text: "Кто в классе часто остаётся один?", hint: "сигнал изоляции" },
  ];

  /* ---------------------------------------------------------- DOM helpers */
  function h(tag, props) {
    var e = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v == null || v === false) return;
        if (k === "class") e.className = v;
        else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
        else if (k === "html") e.innerHTML = v;
        else if (k === "value") e.value = v;
        else if (k.slice(0, 2) === "on" && typeof v === "function") e.addEventListener(k.slice(2).toLowerCase(), v);
        else if (v === true) e.setAttribute(k, "");
        else e.setAttribute(k, v);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(e, arguments[i]);
    return e;
  }
  function hs(tag, props) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    if (props) Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      e.setAttribute(k, v);
    });
    for (var i = 2; i < arguments.length; i++) append(e, arguments[i]);
    return e;
  }
  function append(p, kid) {
    if (kid == null || kid === false) return;
    if (Array.isArray(kid)) { kid.forEach(function (k) { append(p, k); }); return; }
    p.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
  function mount(node) { document.getElementById("app").replaceChildren(node); }

  /* -------------------------------------------------------------- helpers */
  function fmtDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso.replace(" ", "T"));
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
  }
  function fmtShort(iso) {
    var d = new Date((iso || "").slice(0, 10) + "T00:00:00");
    return isNaN(d.getTime()) ? iso : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  }
  function num(n, d) { return (Number(n) || 0).toFixed(d == null ? 0 : d); }
  function csvCell(v) { v = String(v == null ? "" : v); return /[";\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function downloadCSV(filename, rows) {
    var csv = rows.map(function (r) { return r.map(csvCell).join(";"); }).join("\r\n");
    var blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    var url = URL.createObjectURL(blob);
    var a = h("a", { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* ------------------------------------------------------------------ api */
  function errMsg(data, status) {
    if (!data) return "Ошибка " + status;
    var d = data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map(function (x) { return x.msg || JSON.stringify(x); }).join("; ");
    return "Ошибка " + status;
  }
  function api(method, url, body) {
    var headers = { "Content-Type": "application/json" };
    var t = localStorage.getItem("izolyat.token");
    if (t) headers["Authorization"] = "Bearer " + t;
    var opt = { method: method, headers: headers };
    if (body !== undefined) opt.body = JSON.stringify(body);
    return fetch(url, opt).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (res.status === 401) { localStorage.removeItem("izolyat.token"); state.user = null; }
        if (!res.ok) throw new Error(errMsg(data, res.status));
        return data;
      });
    });
  }
  var API = {
    get: function (u) { return api("GET", u); },
    post: function (u, b) { return api("POST", u, b); },
    put: function (u, b) { return api("PUT", u, b); },
    del: function (u) { return api("DELETE", u); },
  };

  /* ------------------------------------------------------------- ui atoms */
  function spinner() { return h("div", { class: "center" }, h("div", { class: "spinner" })); }
  function alertBox(kind, msg) { return h("div", { class: "alert alert-" + kind }, msg); }
  function emptyState(title, hint, action) {
    return h("div", { class: "empty" }, h("div", { class: "big" }, title), hint ? h("div", { class: "muted" }, hint) : null, action ? h("div", { style: { marginTop: "16px" } }, action) : null);
  }
  function field(label, control) { return h("div", { class: "field" }, h("label", {}, label), control); }
  function tile(label, value, sub) {
    return h("div", { class: "tile" }, h("div", { class: "tile-label" }, label), h("div", { class: "tile-value" }, value), sub != null ? h("div", { class: "tile-sub" }, sub) : null);
  }
  function isolateBadge() { return h("span", { class: "badge badge-red" }, h("span", { class: "dot" }), "Изолят"); }
  function communityPill(g) {
    var c = PALETTE[g % PALETTE.length];
    return h("span", { class: "pill", style: { color: c } }, h("span", { class: "swatch", style: { width: "9px", height: "9px", borderRadius: "50%", background: c } }), "Группа " + (g + 1));
  }
  function stars(v) {
    if (v == null) return h("span", { class: "muted" }, "—");
    var f = Math.max(0, Math.min(5, v));
    return h("span", { class: "stars" }, "★".repeat(f), h("span", { class: "dim" }, "★".repeat(5 - f)));
  }
  function deltaSpan(v) {
    var cls = v > 0 ? "delta-up" : v < 0 ? "delta-down" : "delta-flat";
    var sign = v > 0 ? "▲ +" : v < 0 ? "▼ " : "– ";
    return h("span", { class: cls }, sign + Math.abs(v));
  }

  function openModal(title, bodyNodes, footerNodes, wide) {
    var backdrop = h("div", { class: "modal-backdrop" });
    function close() { backdrop.remove(); window.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    var modal = h("div", { class: "modal" + (wide ? " wide" : "") },
      h("div", { class: "modal-head no-print" }, h("h3", {}, title), h("button", { class: "btn btn-ghost btn-sm", onClick: close }, "✕")),
      h("div", { class: "modal-body" }, bodyNodes),
      footerNodes ? h("div", { class: "modal-foot no-print" }, footerNodes) : null);
    backdrop.appendChild(modal);
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) close(); });
    window.addEventListener("keydown", onKey);
    document.body.appendChild(backdrop);
    return close;
  }

  /* ---------------------------------------------------------- app state */
  var state = { user: null };
  var dash = {
    classes: null, classId: null, cls: null, students: [], surveys: [],
    surveyId: null, analysis: null, loaded: false,
    filters: { isolate: true, bridge: true, mutual: true, community: "" },
    network: null, nodesDS: null, edgesDS: null,
  };

  function stopNetwork() {
    if (dash.network) { try { dash.network.destroy(); } catch (e) {} dash.network = null; }
    dash.nodesDS = null; dash.edgesDS = null;
  }
  function go(path) { if (location.hash === "#" + path) router(); else location.hash = "#" + path; }

  function shell(content) {
    var frag = document.createDocumentFragment();
    frag.appendChild(h("header", { class: "topbar" },
      h("a", { class: "brand", href: "#/" }, h("span", { class: "logo" }, "И"), "Изолят"),
      h("span", { class: "pill" }, "🔒 Только психолог"),
      h("span", { class: "spacer" }),
      state.user ? h("span", { class: "who" }, state.user.email) : null,
      h("button", { class: "btn btn-sm", onClick: logout }, "Выйти")));
    frag.appendChild(h("main", { class: "page" }, content));
    return frag;
  }
  function logout() {
    localStorage.removeItem("izolyat.token");
    state.user = null; dash.classes = null; dash.classId = null; dash.surveyId = null; dash.analysis = null; dash.loaded = false;
    stopNetwork(); go("/");
  }

  /* ============================================================== LOGIN */
  function renderLogin() {
    stopNetwork();
    var mode = "in";
    var emailIn = h("input", { class: "input", type: "email", placeholder: "you@example.com" });
    var passIn = h("input", { class: "input", type: "password", placeholder: "••••••••" });
    var nameIn = h("input", { class: "input", placeholder: "Как к вам обращаться" });
    var nameField = field("Имя", nameIn);
    var msg = h("div");
    var submit = h("button", { class: "btn btn-primary", type: "submit" }, "Войти");
    var toggle = h("a", { href: "#" });
    function setMode(m) {
      mode = m; nameField.style.display = m === "up" ? "" : "none";
      submit.textContent = m === "in" ? "Войти" : "Создать аккаунт";
      toggle.textContent = m === "in" ? "Зарегистрироваться" : "Войти"; msg.replaceChildren();
    }
    toggle.addEventListener("click", function (e) { e.preventDefault(); setMode(mode === "in" ? "up" : "in"); });
    var form = h("form", { class: "card-pad stack", style: { paddingTop: "0" } },
      nameField, field("E-mail", emailIn), field("Пароль", passIn), msg, submit,
      h("div", { class: "tiny muted", style: { textAlign: "center" } }, h("span", {}, "Нет аккаунта? "), toggle));
    form.addEventListener("submit", function (e) {
      e.preventDefault(); msg.replaceChildren(); submit.disabled = true;
      var email = emailIn.value.trim(), password = passIn.value;
      var p = mode === "in" ? API.post("/api/auth/login", { email: email, password: password })
        : API.post("/api/auth/register", { email: email, password: password, full_name: nameIn.value.trim() });
      p.then(function (d) { localStorage.setItem("izolyat.token", d.token); state.user = d.user; dash.classes = null; dash.loaded = false; go("/"); })
        .catch(function (err) { msg.replaceChildren(alertBox("error", err.message)); submit.disabled = false; });
    });
    setMode("in");
    mount(h("div", { class: "center" },
      h("div", { class: "card", style: { width: "380px", maxWidth: "92vw" } },
        h("div", { class: "card-pad", style: { textAlign: "center", paddingTop: "28px" } },
          h("div", { class: "logo", style: { width: "46px", height: "46px", fontSize: "22px", margin: "0 auto 12px" } }, "И"),
          h("h2", { style: { fontSize: "20px" } }, "Изолят"),
          h("p", { class: "muted", style: { marginTop: "4px" } }, "Раннее выявление социальной изоляции")),
        form)));
  }

  /* ========================================================== DASHBOARD */
  function setClass(cid) { dash.classId = cid; dash.surveyId = null; dash.analysis = null; dash.filters.community = ""; renderDashboard(); }
  function setSurvey(sid) { dash.surveyId = sid; dash.analysis = null; dash.filters.community = ""; renderDashboard(); }

  function renderDashboard() {
    stopNetwork();
    if (!dash.loaded) mount(shell(spinner()));
    Promise.resolve()
      .then(function () { if (dash.classes === null) return API.get("/api/classes").then(function (d) { dash.classes = d.classes; }); })
      .then(function () {
        if (dash.classes.length === 0) { dash.loaded = true; mount(shell(dashEmpty())); return Promise.reject("stop"); }
        if (!dash.classId || !dash.classes.some(function (c) { return c.id === dash.classId; })) {
          var stored = Number(localStorage.getItem("izolyat.class"));
          dash.classId = dash.classes.some(function (c) { return c.id === stored; }) ? stored : dash.classes[0].id;
        }
        localStorage.setItem("izolyat.class", dash.classId);
        return API.get("/api/classes/" + dash.classId);
      })
      .then(function (data) {
        dash.cls = data.class; dash.students = data.students; dash.surveys = data.surveys;
        if (!dash.surveyId || !dash.surveys.some(function (s) { return s.id === dash.surveyId; }))
          dash.surveyId = dash.surveys.length ? dash.surveys[dash.surveys.length - 1].id : null;
        if (dash.surveyId) return API.get("/api/surveys/" + dash.surveyId + "/analytics");
        return null;
      })
      .then(function (analysis) {
        dash.analysis = analysis; dash.loaded = true;
        mount(shell(dashView()));
        buildNetwork();
      })
      .catch(function (err) { if (err === "stop") return; dash.loaded = true; mount(shell(alertBox("error", err.message || String(err)))); });
  }

  function dashEmpty() {
    return h("div", {}, dashHeader(),
      h("div", { class: "card card-pad" }, emptyState("Ещё нет ни одного класса",
        "Создайте класс, добавьте учеников, затем срез — ученики пройдут опрос по QR/коду, и граф построится автоматически. Для демо: python -m app.seed",
        h("button", { class: "btn btn-primary", onClick: function () { classModal(null); } }, "Создать класс"))));
  }

  function dashHeader() {
    var sel = h("select", { class: "select", style: { width: "auto", minWidth: "200px" }, onChange: function (e) { setClass(Number(e.target.value)); } });
    (dash.classes || []).forEach(function (c) { sel.appendChild(h("option", { value: c.id }, c.name)); });
    if (dash.classId) sel.value = String(dash.classId);
    var controls = [sel];
    if (dash.classId) {
      controls.push(h("button", { class: "btn btn-sm", title: "Изменить класс", onClick: function () { classModal(dash.cls); } }, "✎"));
      controls.push(h("button", { class: "btn btn-sm", onClick: manageStudentsModal }, "Ученики"));
    }
    controls.push(h("button", { class: "btn btn-sm btn-primary", onClick: function () { classModal(null); } }, "+ Класс"));
    return h("div", { style: { marginBottom: "18px" } },
      h("div", { class: "section-title", style: { marginBottom: "4px" } }, "Класс"),
      h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } }, controls));
  }

  function currentSurvey() { return dash.surveys.filter(function (s) { return s.id === dash.surveyId; })[0] || null; }

  function dashView() {
    var sv = currentSurvey();
    return h("div", {}, dashHeader(), srezPanel(sv), radarCard(),
      h("div", { class: "dash-grid" }, graphCard(sv), h("div", { class: "stack" }, metricsCard(), rosterCard())));
  }

  function srezPanel(sv) {
    var controls = [];
    controls.push(h("button", { class: "btn btn-sm", disabled: dash.students.length < 2, title: dash.students.length < 2 ? "Добавьте минимум двух учеников" : "", onClick: surveyModal }, "+ Срез"));
    if (sv) controls.push(h("button", { class: "btn btn-sm btn-primary", onClick: function () { codesModal(sv); } }, "🔗 Ссылка и QR"));
    if (dash.surveys.length >= 2) controls.push(h("button", { class: "btn btn-sm", onClick: compareModal }, "⇄ Сравнить срезы"));

    var inner = [h("div", { style: { display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" } },
      h("div", { class: "section-title", style: { margin: 0, flex: 1 } }, "Срез (социометрический снимок)"), controls)];

    if (dash.surveys.length === 0) {
      inner.push(h("p", { class: "muted", style: { marginTop: "8px" } }, "Пока нет ни одного среза. Создайте срез, чтобы ученики прошли опрос."));
    } else {
      var idx = Math.max(0, dash.surveys.findIndex(function (s) { return s.id === dash.surveyId; }));
      var slider = h("input", { class: "slider", type: "range", min: "0", max: String(dash.surveys.length - 1), value: String(idx),
        oninput: function (e) { var s = dash.surveys[Number(e.target.value)]; if (s) setSurvey(s.id); } });
      var ticks = h("div", { class: "slider-ticks" }, dash.surveys.map(function (s) { return h("span", {}, fmtShort(s.conducted_on)); }));
      var responded = dash.analysis ? (dash.analysis.responded_ids || []).length : 0;
      var total = dash.students.length;
      var pct = total ? Math.round(responded / total * 100) : 0;
      var openBtn = sv ? h("button", { class: "btn btn-sm " + (sv.is_open ? "" : "btn-primary"),
        onClick: function () { API.put("/api/surveys/" + sv.id, { is_open: !sv.is_open }).then(function () { renderDashboard(); }); } },
        sv.is_open ? "Закрыть опрос" : "Открыть опрос") : null;
      var delBtn = sv ? h("button", { class: "btn btn-sm btn-danger", onClick: function () {
        if (confirm("Удалить срез вместе со всеми ответами?")) API.del("/api/surveys/" + sv.id).then(function () { dash.surveyId = null; renderDashboard(); }); } }, "Удалить срез") : null;

      inner.push(h("div", { class: "slider-wrap", style: { marginTop: "14px" } }, dash.surveys.length > 1 ? slider : null, dash.surveys.length > 1 ? ticks : null));
      inner.push(h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", marginTop: "10px" } },
        h("div", { style: { flex: 1, minWidth: "180px" } },
          h("div", { style: { fontWeight: 650 } }, sv ? sv.title : "—"),
          h("div", { class: "muted tiny" }, sv ? fmtDate(sv.conducted_on) : ""),
          h("div", { class: "progress", style: { marginTop: "8px" } }, h("span", { style: { width: pct + "%" } })),
          h("div", { class: "muted tiny", style: { marginTop: "4px" } }, "Прошли опрос: " + responded + " из " + total + " (" + pct + "%)")),
        h("span", { class: "pill " + (sv && sv.is_open ? "badge-green" : "") }, sv && sv.is_open ? "Опрос открыт" : "Опрос закрыт"),
        openBtn, delBtn));
    }
    return h("div", { class: "card card-pad", style: { marginBottom: "18px" } }, inner);
  }

  function graphCard(sv) {
    var a = dash.analysis;
    var body;
    if (!sv) body = emptyState("Нет среза", "Создайте срез и дайте ученикам пройти опрос.");
    else if (!a || a.students.length === 0) body = emptyState("Нет учеников", "Добавьте учеников в класс.");
    else if (!window.vis) body = alertBox("error", "Библиотека vis-network не загрузилась. Проверьте интернет-соединение.");
    else {
      var toolbar = h("div", { class: "toolbar" },
        checkbox("Изоляты", dash.filters.isolate, function (v) { dash.filters.isolate = v; applyFilters(); }),
        checkbox("Мосты", dash.filters.bridge, function (v) { dash.filters.bridge = v; applyFilters(); }),
        checkbox("Взаимные", dash.filters.mutual, function (v) { dash.filters.mutual = v; applyFilters(); }),
        communitySelect(a));
      body = h("div", {},
        toolbar,
        h("div", { id: "net", class: "net" }),
        graphLegend(a),
        (a.responded_ids || []).length === 0 ? h("div", { style: { marginTop: "12px" } },
          alertBox("info", "Ученики ещё не прошли опрос — связей нет. Откройте опрос и раздайте коды/QR.")) : null);
    }
    return h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h3", {}, "Социограмма"), h("span", { class: "spacer" }),
        h("span", { class: "muted tiny" }, sv ? sv.title + " · " + fmtDate(sv.conducted_on) : "—")),
      h("div", { class: "card-pad" }, body));
  }

  function checkbox(label, checked, onChange) {
    var input = h("input", { type: "checkbox" });
    input.checked = checked;
    input.addEventListener("change", function () { onChange(input.checked); });
    return h("label", { class: "check" }, input, label);
  }
  function communitySelect(a) {
    var count = (a.communities || []).length;
    var sel = h("select", { class: "select", style: { width: "auto" }, onChange: function (e) { dash.filters.community = e.target.value; applyFilters(); } },
      h("option", { value: "" }, "Все группы"));
    for (var i = 0; i < count; i++) sel.appendChild(h("option", { value: String(i) }, "Группа " + (i + 1)));
    sel.value = dash.filters.community;
    return sel;
  }

  function graphLegend(a) {
    var items = [];
    var count = Math.min((a.communities || []).length, PALETTE.length);
    for (var i = 0; i < count; i++) items.push(h("span", { class: "item" }, h("span", { class: "swatch", style: { background: PALETTE[i % PALETTE.length] } }), "Группа " + (i + 1)));
    items.push(h("span", { class: "item" }, h("span", { class: "swatch", style: { background: "#fee2e2", border: "2px solid #ef4444" } }), "Изолят"));
    items.push(h("span", { class: "item" }, h("span", { class: "line", style: { borderTopColor: "#2563eb" } }), "Взаимный выбор"));
    items.push(h("span", { class: "item" }, h("span", { class: "line", style: { borderTopColor: "#f59e0b", borderTopStyle: "dashed" } }), "Мост"));
    return h("div", { class: "legend" }, items);
  }

  function metricsCard() {
    var a = dash.analysis;
    var body;
    if (!a) body = emptyState("Нет данных", "Выберите срез.");
    else {
      var m = a.graph_metrics;
      body = h("div", {},
        h("div", { class: "tiles" },
          tile("Учеников", m.students),
          tile("Изоляты", m.isolates, "нет входящих выборов"),
          tile("Взаимные пары", m.mutual_pairs, "взаимность " + num(m.reciprocity * 100) + "%"),
          tile("Плотность", num(m.density, 2), "density")),
        h("div", { class: "chip-row", style: { marginTop: "14px" } },
          h("span", { class: "pill" }, "Сплочённость: " + num(m.cohesion, 2)),
          h("span", { class: "pill" }, "Компоненты: " + m.components),
          h("span", { class: "pill" }, "Сообщества: " + m.communities),
          h("span", { class: "pill" }, "Мосты: " + m.bridges),
          h("span", { class: "pill" }, "Связей: " + m.positive_edges)));
    }
    return h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Показатели класса")), h("div", { class: "card-pad" }, body));
  }

  function rosterCard() {
    var a = dash.analysis;
    var per = a ? a.per_student : {};
    var sorted = dash.students.slice().sort(function (x, y) {
      var mx = per[String(x.id)], my = per[String(y.id)];
      return ((mx && mx.in_degree) || 0) - ((my && my.in_degree) || 0);
    });
    var body;
    if (dash.students.length === 0) body = emptyState("Список пуст", "Добавьте учеников через «Ученики».");
    else {
      var rows = sorted.map(function (s) {
        var m = per[String(s.id)];
        return h("tr", { class: "clickable", onClick: function () { go("/student/" + s.id); } },
          h("td", {}, s.full_name),
          h("td", {}, m ? (m.is_isolate ? isolateBadge() : communityPill(m.community)) : "—"),
          h("td", { class: "num" }, m ? m.in_degree : 0),
          h("td", { class: "num" }, m ? m.out_degree : 0),
          h("td", { class: "num" }, m ? m.mutual : 0),
          h("td", { class: "num" }, m ? m.alone_votes : 0));
      });
      body = h("div", { style: { overflowX: "auto" } },
        h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", {}, "Статус"),
            h("th", { class: "num", title: "Входящие" }, "Вх"), h("th", { class: "num", title: "Исходящие" }, "Исх"),
            h("th", { class: "num", title: "Взаимные" }, "Вз"), h("th", { class: "num", title: "«Часто один»" }, "Один"))),
          h("tbody", {}, rows)));
    }
    return h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h3", {}, "Ученики"), h("span", { class: "spacer" }),
        dash.analysis ? h("button", { class: "btn btn-sm", onClick: reportModal }, "📄 Отчёт") : null),
      h("div", { class: "card-pad", style: { paddingTop: "6px", paddingBottom: "6px" } }, body));
  }

  /* ------------------------------------------------------ vis-network */
  function computeVisible(a) {
    var s = new Set();
    a.nodes.forEach(function (n) { if (dash.filters.community === "" || String(n.group) === String(dash.filters.community)) s.add(n.id); });
    return s;
  }
  function nodeStyle(n) {
    var base = PALETTE[n.group % PALETTE.length];
    var color = { background: base, border: base, highlight: { background: base, border: "#0f172a" } };
    var bw = 2;
    if (dash.filters.isolate && n.isolate) { color = { background: "#fee2e2", border: "#ef4444", highlight: { background: "#fecaca", border: "#ef4444" } }; bw = 3; }
    var hidden = dash.filters.community !== "" && String(n.group) !== String(dash.filters.community);
    return { id: n.id, label: n.label, title: n.title, value: n.value, color: color, borderWidth: bw, hidden: hidden };
  }
  function edgeStyle(e, visible) {
    var color = "#cbd5e1", width = 1, dashes = false;
    if (dash.filters.mutual && e.mutual) { color = "#2563eb"; width = 3; }
    if (dash.filters.bridge && e.bridge) { color = "#f59e0b"; width = 3; dashes = [6, 4]; }
    var hidden = dash.filters.community !== "" && (!visible.has(e.from) || !visible.has(e.to));
    return { id: e.id, from: e.from, to: e.to, color: { color: color, highlight: "#0f172a" }, width: width, dashes: dashes, hidden: hidden };
  }
  function buildNetwork() {
    var a = dash.analysis;
    var container = document.getElementById("net");
    if (!a || !container || !window.vis || a.nodes.length === 0) return;
    a.edges.forEach(function (e, i) { e.id = "e" + i; });
    var visible = computeVisible(a);
    dash.nodesDS = new vis.DataSet(a.nodes.map(nodeStyle));
    dash.edgesDS = new vis.DataSet(a.edges.map(function (e) { return edgeStyle(e, visible); }));
    var options = {
      nodes: { shape: "dot", scaling: { min: 10, max: 34 }, font: { size: 14, color: "#0f172a" } },
      edges: { arrows: { to: { enabled: true, scaleFactor: 0.6 } }, smooth: { type: "continuous" } },
      physics: { stabilization: { iterations: 150 }, barnesHut: { gravitationalConstant: -9000, springLength: 110, springConstant: 0.035, damping: 0.28 } },
      interaction: { hover: true, tooltipDelay: 120, zoomView: true, dragNodes: true, dragView: true },
    };
    dash.network = new vis.Network(container, { nodes: dash.nodesDS, edges: dash.edgesDS }, options);
    dash.network.on("click", function (params) { if (params.nodes && params.nodes.length) go("/student/" + params.nodes[0]); });
  }
  function applyFilters() {
    var a = dash.analysis;
    if (!a || !dash.nodesDS) return;
    var visible = computeVisible(a);
    dash.nodesDS.update(a.nodes.map(nodeStyle));
    dash.edgesDS.update(a.edges.map(function (e) { return edgeStyle(e, visible); }));
  }

  /* ------------------------------------------------------ dash modals */
  function classModal(cls) {
    var nameIn = h("input", { class: "input", value: cls ? cls.name : "", placeholder: "Например, 8 «А» класс" });
    var descIn = h("textarea", { class: "textarea", value: cls && cls.description ? cls.description : "" });
    var err = h("div"); var close;
    function save() {
      var name = nameIn.value.trim(); if (!name) return;
      var body = { name: name, description: descIn.value.trim() };
      (cls ? API.put("/api/classes/" + cls.id, body) : API.post("/api/classes", body))
        .then(function (d) { dash.classes = null; if (!cls) dash.classId = d.class.id; close(); renderDashboard(); })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }
    function remove() {
      if (!confirm("Удалить класс со всеми учениками, срезами и ответами?")) return;
      API.del("/api/classes/" + cls.id).then(function () { dash.classes = null; dash.classId = null; dash.surveyId = null; close(); renderDashboard(); });
    }
    close = openModal(cls ? "Класс" : "Новый класс", [err, field("Название", nameIn), field("Описание", descIn)],
      [cls ? h("button", { class: "btn btn-danger", onClick: remove }, "Удалить") : null, h("div", { style: { flex: "1" } }),
       h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"), h("button", { class: "btn btn-primary", onClick: save }, "Сохранить")]);
  }

  function studentModal(student, onSaved) {
    var nameIn = h("input", { class: "input", value: student ? student.full_name : "" });
    var genderIn = h("select", { class: "select" }, h("option", { value: "" }, "—"), h("option", { value: "m" }, "Мужской"), h("option", { value: "f" }, "Женский"));
    genderIn.value = student && student.gender ? student.gender : "";
    var birthIn = h("input", { class: "input", type: "date", value: student && student.birth_date ? student.birth_date : "" });
    var noteIn = h("textarea", { class: "textarea", value: student && student.note ? student.note : "" });
    var err = h("div"); var close;
    function save() {
      var full = nameIn.value.trim(); if (!full) return;
      var body = { full_name: full, gender: genderIn.value, birth_date: birthIn.value, note: noteIn.value.trim() };
      (student ? API.put("/api/students/" + student.id, body) : API.post("/api/classes/" + dash.classId + "/students", body))
        .then(function () { close(); if (onSaved) onSaved(); })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal(student ? "Ученик" : "Новый ученик",
      [err, field("Имя и фамилия", nameIn), h("div", { class: "row" }, field("Пол", genderIn), field("Дата рождения", birthIn)), field("Заметка", noteIn)],
      [h("div", { style: { flex: "1" } }), h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"), h("button", { class: "btn btn-primary", onClick: save }, "Сохранить")]);
  }

  function manageStudentsModal() {
    var listWrap = h("div");
    function reload() { API.get("/api/classes/" + dash.classId).then(function (d) { dash.students = d.students; render(); }); }
    function render() {
      if (dash.students.length === 0) { listWrap.replaceChildren(emptyState("Список пуст", "Добавьте первого ученика.")); return; }
      var rows = dash.students.map(function (s) {
        return h("tr", {},
          h("td", {}, s.full_name),
          h("td", { class: "mono" }, s.code),
          h("td", { class: "num" },
            h("button", { class: "btn btn-ghost btn-sm", title: "Новый код", onClick: function () { API.post("/api/students/" + s.id + "/regenerate-code").then(reload); } }, "⟳"),
            h("button", { class: "btn btn-ghost btn-sm", title: "Изменить", onClick: function () { studentModal(s, reload); } }, "✎"),
            h("button", { class: "btn btn-danger btn-sm", title: "Удалить", onClick: function () { if (confirm("Удалить ученика?")) API.del("/api/students/" + s.id).then(reload); } }, "✕")));
      });
      listWrap.replaceChildren(h("div", { style: { overflowX: "auto" } },
        h("table", { class: "table" }, h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", {}, "Код"), h("th", {}))), h("tbody", {}, rows))));
    }
    render();
    var close = openModal("Ученики класса",
      [h("div", { style: { marginBottom: "6px", display: "flex", gap: "8px", flexWrap: "wrap" } },
        h("button", { class: "btn btn-primary btn-sm", onClick: function () { studentModal(null, reload); } }, "+ Добавить ученика"),
        h("button", { class: "btn btn-sm", onClick: function () { importStudentsModal(reload); } }, "⬆ Импорт Excel/CSV")), listWrap],
      [h("button", { class: "btn btn-primary", onClick: function () { close(); renderDashboard(); } }, "Готово")], true);
  }

  function surveyModal() {
    var today = new Date().toISOString().slice(0, 10);
    var titleIn = h("input", { class: "input", placeholder: "Например, Осенний срез" });
    var dateIn = h("input", { class: "input", type: "date", value: today });
    var qInputs = DEFAULT_QUESTIONS.map(function (q) {
      return { key: q.key, input: h("input", { class: "input", value: q.text }), hint: q.hint };
    });
    var qFields = qInputs.map(function (q, i) {
      return field("Вопрос " + (i + 1) + " (" + q.hint + ")", q.input);
    });
    var err = h("div"); var close;
    function save() {
      var title = titleIn.value.trim(); if (!title) return;
      var questions = qInputs.map(function (q) { return { key: q.key, text: q.input.value.trim() }; });
      API.post("/api/classes/" + dash.classId + "/surveys", { title: title, conducted_on: dateIn.value, questions: questions })
        .then(function (d) { close(); dash.surveyId = d.survey.id; renderDashboard(); setTimeout(function () { codesModal(d.survey); }, 60); })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Новый срез",
      [err, field("Название", titleIn), field("Дата проведения", dateIn),
       h("div", { class: "section-title", style: { marginTop: "6px" } }, "Вопросы (можно адаптировать под возраст класса)"),
       qFields,
       h("p", { class: "muted tiny" }, "Смысл вопросов фиксирован (2 положительных + 1 на изоляцию) — меняется только формулировка. После создания откроется окно со ссылкой и QR-кодом.")],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"), h("button", { class: "btn btn-primary", onClick: save }, "Создать")]);
  }

  function codesModal(sv) {
    var link = location.origin + "/survey.html?survey=" + sv.id;
    var qrBox = h("div", { class: "qr-box" });
    var linkIn = h("input", { class: "input", value: link });
    linkIn.setAttribute("readonly", "");
    var codesWrap = h("div", { class: "print-area" }, spinner());
    var body = [
      h("div", { class: "section-title" }, "QR-код для прохождения опроса"),
      qrBox,
      h("div", { class: "row", style: { marginTop: "6px" } },
        linkIn,
        h("button", { class: "btn", onClick: function () { linkIn.select(); document.execCommand && document.execCommand("copy"); } }, "Копировать")),
      h("div", { class: "section-title", style: { marginTop: "10px" } }, "Коды учеников (для печати и раздачи)"),
      codesWrap,
    ];
    var close = openModal("Ссылка и QR — " + sv.title, body,
      [h("button", { class: "btn", onClick: function () { window.print(); } }, "🖨 Печать кодов"),
       h("div", { style: { flex: "1" } }), h("button", { class: "btn btn-primary", onClick: function () { close(); } }, "Закрыть")], true);
    // QR
    if (typeof QRCode !== "undefined") { try { new QRCode(qrBox, { text: link, width: 190, height: 190, correctLevel: QRCode.CorrectLevel.M }); } catch (e) { qrBox.textContent = link; } }
    else qrBox.textContent = "QR-библиотека не загрузилась. Используйте ссылку выше.";
    // codes
    API.get("/api/classes/" + dash.classId + "/codes").then(function (d) {
      var grid = h("div", { class: "code-grid" }, d.codes.map(function (c) {
        return h("div", { class: "code-card" }, h("div", { class: "nm" }, c.full_name), h("div", { class: "cd" }, c.code));
      }));
      codesWrap.replaceChildren(h("div", { class: "muted tiny no-print", style: { marginBottom: "8px" } }, "Каждый ученик вводит свой код на странице опроса."), grid);
    });
  }

  /* -------------------------------------------------- радар изоляции */
  function radarCard() {
    var a = dash.analysis; if (!a) return null;
    var per = a.per_student;
    var risk = dash.students.filter(function (s) { var m = per[String(s.id)]; return m && (m.is_isolate || (m.alone_votes || 0) >= 2); });
    if (risk.length === 0) return null;
    risk.sort(function (x, y) {
      var mx = per[String(x.id)], my = per[String(y.id)];
      var sx = (mx.is_isolate ? 100 : 0) + (mx.alone_votes || 0), sy = (my.is_isolate ? 100 : 0) + (my.alone_votes || 0);
      return sy - sx;
    });
    var chips = risk.map(function (s) {
      var m = per[String(s.id)];
      var tag = (m.is_isolate ? " · изолят" : "") + ((m.alone_votes || 0) ? " · «один»×" + m.alone_votes : "");
      return h("button", { class: "pill", style: { cursor: "pointer", borderColor: "#fecaca", color: "var(--red)" }, onClick: function () { go("/student/" + s.id); } }, s.full_name + tag);
    });
    return h("div", { class: "card", style: { marginBottom: "18px", borderColor: "#fecaca", background: "linear-gradient(180deg,#ffffff,#fff6f6)" } },
      h("div", { class: "card-pad" },
        h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" } },
          h("span", { style: { fontSize: "22px" } }, "⚠️"),
          h("div", { style: { flex: "1", minWidth: "200px" } },
            h("div", { style: { fontWeight: "700", fontSize: "15px" } }, "Радар изоляции: " + risk.length + " на контроль"),
            h("div", { class: "muted tiny" }, "Изоляты и ученики с номинациями «часто остаётся один» — требуют внимания")),
          h("span", { class: "badge badge-red" }, String(risk.length))),
        h("div", { class: "chip-row", style: { marginTop: "12px" } }, chips)));
  }

  /* -------------------------------------------------- отчёт (CSV/печать) */
  function reportModal() {
    var a = dash.analysis; if (!a) return;
    var per = a.per_student, gm = a.graph_metrics, sv = currentSurvey();
    var sorted = dash.students.slice().sort(function (x, y) {
      var mx = per[String(x.id)], my = per[String(y.id)];
      return ((mx && mx.in_degree) || 0) - ((my && my.in_degree) || 0);
    });
    function statusText(m) { return !m ? "—" : m.is_isolate ? "Изолят" : "Группа " + ((m.community || 0) + 1); }
    var tbody = h("tbody", {}, sorted.map(function (s) {
      var m = per[String(s.id)] || {};
      return h("tr", {}, h("td", {}, s.full_name), h("td", {}, statusText(m)),
        h("td", { class: "num" }, m.in_degree || 0), h("td", { class: "num" }, m.out_degree || 0),
        h("td", { class: "num" }, m.mutual || 0), h("td", { class: "num" }, m.alone_votes || 0),
        h("td", { class: "num" }, num(m.degree_centrality, 2)), h("td", { class: "num" }, num(m.betweenness, 3)));
    }));
    var report = h("div", { class: "print-area" },
      h("h2", { style: { fontSize: "20px", marginBottom: "2px" } }, "Отчёт: " + dash.cls.name),
      h("p", { class: "muted", style: { marginBottom: "12px" } }, sv ? sv.title + " · " + fmtDate(sv.conducted_on) : ""),
      h("div", { class: "chip-row", style: { marginBottom: "14px" } },
        h("span", { class: "pill" }, "Учеников: " + gm.students),
        h("span", { class: "pill" }, "Изоляты: " + gm.isolates),
        h("span", { class: "pill" }, "Взаимные пары: " + gm.mutual_pairs),
        h("span", { class: "pill" }, "Плотность: " + num(gm.density, 2)),
        h("span", { class: "pill" }, "Сплочённость: " + num(gm.cohesion, 2))),
      h("div", { style: { overflowX: "auto" } }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", {}, "Статус"),
          h("th", { class: "num" }, "Вх"), h("th", { class: "num" }, "Исх"), h("th", { class: "num" }, "Вз"),
          h("th", { class: "num" }, "Один"), h("th", { class: "num" }, "Degree"), h("th", { class: "num" }, "Betw."))),
        tbody)));
    function csvRows() {
      var rows = [["Класс", dash.cls.name], ["Срез", sv ? sv.title : "", sv ? sv.conducted_on : ""],
        ["Учеников", gm.students, "Изоляты", gm.isolates, "Взаимные пары", gm.mutual_pairs],
        ["Плотность", gm.density, "Сплочённость", gm.cohesion, "Взаимность", gm.reciprocity], [],
        ["Ученик", "Статус", "Входящие", "Исходящие", "Взаимные", "Часто один", "Degree centrality", "Betweenness", "Группа"]];
      sorted.forEach(function (s) {
        var m = per[String(s.id)] || {};
        rows.push([s.full_name, statusText(m), m.in_degree || 0, m.out_degree || 0, m.mutual || 0, m.alone_votes || 0, m.degree_centrality || 0, m.betweenness || 0, (m.community || 0) + 1]);
      });
      return rows;
    }
    var fname = "izolyat_" + String(dash.cls.name || "class").replace(/\s+/g, "_") + ".csv";
    var close = openModal("Отчёт класса", report,
      [h("button", { class: "btn", onClick: function () { downloadCSV(fname, csvRows()); } }, "⬇ CSV для Excel"),
       h("button", { class: "btn", onClick: function () { window.print(); } }, "🖨 Печать"),
       h("div", { style: { flex: "1" } }),
       h("button", { class: "btn btn-primary", onClick: function () { close(); } }, "Закрыть")], true);
  }

  /* -------------------------------------------------- сравнение срезов */
  function compareModal() {
    if (dash.surveys.length < 2) return;
    var selA = h("select", { class: "select" }), selB = h("select", { class: "select" });
    dash.surveys.forEach(function (s) {
      selA.appendChild(h("option", { value: s.id }, s.title + " · " + fmtShort(s.conducted_on)));
      selB.appendChild(h("option", { value: s.id }, s.title + " · " + fmtShort(s.conducted_on)));
    });
    var n = dash.surveys.length;
    selA.value = String(dash.surveys[n - 2].id);
    selB.value = String(dash.surveys[n - 1].id);
    var out = h("div");
    function run() {
      if (selA.value === selB.value) { out.replaceChildren(alertBox("info", "Выберите два разных среза.")); return; }
      out.replaceChildren(h("div", { class: "spinner" }));
      Promise.all([API.get("/api/surveys/" + selA.value + "/analytics"), API.get("/api/surveys/" + selB.value + "/analytics")])
        .then(function (r) { out.replaceChildren(renderCompare(r[0], r[1])); })
        .catch(function (e) { out.replaceChildren(alertBox("error", e.message)); });
    }
    selA.addEventListener("change", run); selB.addEventListener("change", run);
    run();
    openModal("Сравнение срезов", [h("div", { class: "row" }, field("Срез A (раньше)", selA), field("Срез B (позже)", selB)), out], null, true);
  }

  function renderCompare(A, B) {
    var perA = A.per_student, perB = B.per_student;
    var rows = B.students.map(function (s) {
      var mA = perA[String(s.id)] || {}, mB = perB[String(s.id)] || {};
      var inA = mA.in_degree || 0, inB = mB.in_degree || 0;
      var isoA = !!mA.is_isolate, isoB = !!mB.is_isolate;
      var kind = (!isoA && isoB) ? "worse" : (isoA && !isoB) ? "better" : "same";
      return { name: s.full_name, id: s.id, inA: inA, inB: inB, delta: inB - inA, kind: kind };
    });
    var rank = { worse: 0, same: 1, better: 2 };
    rows.sort(function (x, y) { return rank[x.kind] !== rank[y.kind] ? rank[x.kind] - rank[y.kind] : x.delta - y.delta; });
    var became = rows.filter(function (r) { return r.kind === "worse"; }).length;
    var recovered = rows.filter(function (r) { return r.kind === "better"; }).length;
    var summary = h("div", { class: "chip-row", style: { marginBottom: "12px" } },
      h("span", { class: "pill badge-red" }, "Стали изолятами: " + became),
      h("span", { class: "pill badge-green" }, "Вышли из изоляции: " + recovered));
    var body = rows.map(function (r) {
      var badge = r.kind === "worse" ? h("span", { class: "badge badge-red" }, "стал изолятом")
        : r.kind === "better" ? h("span", { class: "badge badge-green" }, "вышел из изоляции")
        : (r.delta === 0 ? h("span", { class: "muted" }, "без изменений") : deltaSpan(r.delta));
      return h("tr", { class: "clickable", onClick: function () { go("/student/" + r.id); } },
        h("td", {}, r.name), h("td", { class: "num" }, r.inA), h("td", { class: "num" }, r.inB),
        h("td", { class: "num" }, deltaSpan(r.delta)), h("td", {}, badge));
    });
    return h("div", {}, summary,
      h("div", { style: { overflowX: "auto" } }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", { class: "num" }, "Вх (A)"),
          h("th", { class: "num" }, "Вх (B)"), h("th", { class: "num" }, "Δ"), h("th", {}, "Изменение"))),
        h("tbody", {}, body))));
  }

  /* -------------------------------------------------- импорт учеников */
  function importStudentsModal(onDone) {
    var info = h("div", { class: "muted tiny" }, "Excel/CSV: имя берётся из первого столбца (поддерживаются колонки: имя, пол, дата). Или вставьте список вручную.");
    var fileIn = h("input", { class: "input", type: "file", accept: ".xlsx,.xls,.csv" });
    var ta = h("textarea", { class: "textarea", style: { minHeight: "170px" }, placeholder: "По одному ученику в строке:\nАлина Смирнова\nБорис Кузнецов, м, 2011-05-14" });
    var msg = h("div"); var close;
    fileIn.addEventListener("change", function () {
      var f = fileIn.files && fileIn.files[0]; if (!f) return;
      msg.replaceChildren(h("span", { class: "muted tiny" }, "Читаю файл…"));
      parseFile(f, function (lines) {
        ta.value = (ta.value ? ta.value.trim() + "\n" : "") + lines.join("\n");
        msg.replaceChildren(alertBox("ok", "Из файла добавлено строк: " + lines.length + ". Проверьте список и нажмите «Импортировать»."));
      }, function (err) { msg.replaceChildren(alertBox("error", err)); });
    });
    function parseLines() {
      return ta.value.split(/\r?\n/).map(function (l) { return l.trim(); }).filter(Boolean).map(function (l) {
        var p = l.split(/[,;\t]/).map(function (x) { return x.trim(); });
        var g = (p[1] || "").toLowerCase();
        var gender = /^(м|муж|m|male)/.test(g) ? "m" : /^(ж|жен|f|female)/.test(g) ? "f" : null;
        return { full_name: p[0], gender: gender, birth_date: p[2] || null };
      }).filter(function (x) { return x.full_name; });
    }
    function doImport() {
      var students = parseLines();
      if (!students.length) { msg.replaceChildren(alertBox("error", "Список пуст.")); return; }
      msg.replaceChildren(h("span", { class: "muted tiny" }, "Импортирую…"));
      API.post("/api/classes/" + dash.classId + "/students/bulk", { students: students })
        .then(function () { close(); if (onDone) onDone(); })
        .catch(function (e) { msg.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Импорт учеников",
      [info, field("Файл Excel / CSV", fileIn), field("Список (по одному в строке)", ta), msg,
       h("p", { class: "tiny muted" }, "Формат строки: Имя Фамилия[, пол (м/ж)][, дата ГГГГ-ММ-ДД]. Каждому автоматически выдастся код.")],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"), h("button", { class: "btn btn-primary", onClick: doImport }, "Импортировать")], true);
  }

  function parseFile(file, ok, fail) {
    var reader = new FileReader();
    reader.onload = function (e) {
      try {
        if (typeof XLSX === "undefined") { fail("Библиотека для Excel не загрузилась (нужен интернет). Сохраните файл как CSV или вставьте список вручную."); return; }
        var wb = XLSX.read(new Uint8Array(e.target.result), { type: "array" });
        var ws = wb.Sheets[wb.SheetNames[0]];
        var grid = XLSX.utils.sheet_to_json(ws, { header: 1, blankrows: false });
        var lines = [];
        grid.forEach(function (r) {
          if (!r || !r.length) return;
          var first = (r[0] == null ? "" : String(r[0])).trim();
          if (!first) return;
          var line = first;
          if (r[1] != null && String(r[1]).trim()) line += ", " + String(r[1]).trim();
          if (r[2] != null && String(r[2]).trim()) line += ", " + String(r[2]).trim();
          lines.push(line);
        });
        if (lines.length && /^(имя|фио|name|ученик|ф\.?и\.?о)/i.test(lines[0])) lines.shift();
        if (!lines.length) { fail("В файле не найдено имён."); return; }
        ok(lines);
      } catch (err) { fail("Не удалось прочитать файл."); }
    };
    reader.onerror = function () { fail("Ошибка чтения файла."); };
    reader.readAsArrayBuffer(file);
  }

  /* ========================================================= STUDENT CARD */
  function renderStudent(id) {
    stopNetwork();
    mount(shell(spinner()));
    API.get("/api/students/" + id + "/card").then(buildStudent)
      .catch(function (e) { mount(shell(h("div", {}, alertBox("error", e.message), h("p", { style: { marginTop: "12px" } }, h("a", { href: "#/" }, "← На главную"))))); });
  }

  function buildStudent(data) {
    var student = data.student;
    var roster = {}; data.roster.forEach(function (r) { roster[r.id] = r.full_name; });
    var nameOf = function (sid) { return roster[sid] || "—"; };
    var surveysAsc = data.surveys.slice().sort(function (a, b) { return a.conducted_on < b.conducted_on ? -1 : 1; });
    var dyn = data.dynamics;
    var latest = dyn.length ? dyn[dyn.length - 1] : null;

    var header = h("div", { class: "card card-pad", style: { marginBottom: "18px" } },
      h("div", { style: { display: "flex", gap: "16px", alignItems: "flex-start", flexWrap: "wrap" } },
        h("div", { style: { flex: "1", minWidth: "220px" } },
          h("h1", { style: { fontSize: "24px" } }, student.full_name),
          h("div", { class: "muted", style: { marginTop: "6px" } },
            h("span", { class: "pill mono", style: { marginRight: "8px" } }, student.code),
            student.gender === "m" ? "мужской пол · " : student.gender === "f" ? "женский пол · " : "", ageText(student.birth_date)),
          student.note ? h("p", { class: "muted", style: { marginTop: "8px" } }, student.note) : null),
        h("div", { style: { textAlign: "right" } },
          h("div", { class: "section-title" }, "Текущий статус"),
          latest ? (latest.is_isolate ? isolateBadge() : communityPill(latest.community)) : h("span", { class: "muted" }, "нет срезов"),
          latest ? h("div", { class: "muted tiny", style: { marginTop: "6px" } }, "на " + fmtDate(latest.date)) : null)));

    var metricsBody = latest ? h("div", { class: "tiles" },
      tile("Входящие", latest.in_degree, "кто выбрал"),
      tile("Исходящие", latest.out_degree, "кого выбрал"),
      tile("Взаимные", latest.mutual, "пары"),
      tile("«Часто один»", latest.alone_votes, "номинаций"),
      tile("Betweenness", num(latest.betweenness, 3), "посредничество"))
      : emptyState("Нет данных", "Нужен хотя бы один заполненный срез.");
    var metricsCardEl = h("div", { class: "card", style: { marginBottom: "18px" } },
      h("div", { class: "card-head" }, h("h3", {}, "Показатели"), h("span", { class: "spacer" }),
        latest ? h("span", { class: "muted tiny" }, latest.title + " · " + fmtDate(latest.date)) : null),
      h("div", { class: "card-pad" }, metricsBody));

    var dynTable = null;
    if (dyn.length) {
      var trs = dyn.map(function (p, i) {
        return h("tr", {},
          h("td", {}, p.title), h("td", {}, fmtDate(p.date)),
          h("td", {}, p.is_isolate ? isolateBadge() : communityPill(p.community)),
          h("td", { class: "num" }, p.in_degree), h("td", { class: "num" }, p.out_degree),
          h("td", { class: "num" }, p.mutual), h("td", { class: "num" }, p.alone_votes),
          h("td", { class: "num" }, i === 0 ? h("span", { class: "muted" }, "—") : deltaSpan(p.in_degree - dyn[i - 1].in_degree)));
      });
      dynTable = h("div", { style: { overflowX: "auto", marginTop: "12px" } },
        h("table", { class: "table" }, h("thead", {}, h("tr", {}, h("th", {}, "Срез"), h("th", {}, "Дата"), h("th", {}, "Статус"),
          h("th", { class: "num" }, "Вх"), h("th", { class: "num" }, "Исх"), h("th", { class: "num" }, "Вз"), h("th", { class: "num" }, "Один"), h("th", { class: "num" }, "Δвх"))),
          h("tbody", {}, trs)));
    }
    var dynamicsCard = h("div", { class: "card", style: { marginBottom: "18px" } },
      h("div", { class: "card-head" }, h("h3", {}, "Динамика (входящие выборы)")),
      h("div", { class: "card-pad" }, lineChart(dyn), dynTable));

    var historyCard = h("div", { class: "card", style: { marginBottom: "18px" } },
      h("div", { class: "card-head" }, h("h3", {}, "История связей"), h("span", { class: "spacer" }), h("span", { class: "muted tiny" }, "изменение по срезам")),
      h("div", { class: "card-pad" }, surveysAsc.length === 0 ? emptyState("Нет срезов")
        : h("div", { class: "stack" }, surveysAsc.slice().reverse().map(function (sv) { return connectionBlock(sv, student.id, data.choices_by_survey[String(sv.id)] || [], nameOf); }))));

    var intCard = h("div", { class: "card", style: { marginBottom: "18px" } },
      h("div", { class: "card-head" }, h("h3", {}, "Вмешательства и эффективность")),
      h("div", { class: "card-pad" }, interventionForm(student.id),
        data.interventions.length === 0 ? h("div", { style: { marginTop: "8px" } }, emptyState("Пока нет вмешательств"))
          : h("div", { class: "stack", style: { marginTop: "8px" } }, data.interventions.map(function (iv) { return interventionItem(iv, dyn, student.id); }))));

    var meetingsCard = h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h3", {}, "Встречи")),
      h("div", { class: "card-pad" }, meetingForm(student.id),
        data.meetings.length === 0 ? h("div", { style: { marginTop: "8px" } }, emptyState("Нет встреч"))
          : h("div", { class: "stack", style: { marginTop: "8px" } }, data.meetings.map(function (m) {
              return listRow(fmtDate(m.met_on), m.summary || h("span", { class: "muted" }, "без описания"), function () { del("/api/meetings/" + m.id, "Удалить встречу?", student.id); }); }))));
    var notesCard = h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h3", {}, "Заметки психолога")),
      h("div", { class: "card-pad" }, noteForm(student.id),
        data.notes.length === 0 ? h("div", { style: { marginTop: "8px" } }, emptyState("Нет заметок"))
          : h("div", { class: "stack", style: { marginTop: "8px" } }, data.notes.map(function (nt) {
              return listRow(fmtDate(nt.created_at), nt.body, function () { del("/api/notes/" + nt.id, "Удалить заметку?", student.id); }); }))));

    mount(shell(h("div", { class: "page-narrow", style: { margin: "0 auto" } },
      h("div", { class: "breadcrumb" }, h("a", { href: "#/" }, "Классы"), h("span", {}, "/"), h("span", {}, "Карточка ученика")),
      header, metricsCardEl, dynamicsCard, historyCard, intCard, h("div", { class: "two-col" }, meetingsCard, notesCard))));

    function del(url, msg, sid) { if (confirm(msg)) API.del(url).then(function () { renderStudent(sid); }); }
  }

  function listRow(when, body, onDelete) {
    return h("div", { class: "list-item" }, h("div", { class: "when" }, when), h("div", { class: "body" }, body),
      h("button", { class: "btn btn-danger btn-sm", onClick: onDelete }, "✕"));
  }

  function connectionBlock(survey, studentId, choices, nameOf) {
    var pos = ["cinema", "project"];
    var outPos = {}, incPos = {};
    choices.forEach(function (c) {
      if (c.from_student === studentId && pos.indexOf(c.question) >= 0) outPos[c.to_student] = true;
      if (c.to_student === studentId && pos.indexOf(c.question) >= 0) incPos[c.from_student] = true;
    });
    function group(filterFn) { return choices.filter(filterFn); }
    var out = group(function (c) { return c.from_student === studentId && pos.indexOf(c.question) >= 0; });
    var outAlone = group(function (c) { return c.from_student === studentId && c.question === "alone"; });
    var inc = group(function (c) { return c.to_student === studentId && pos.indexOf(c.question) >= 0; });
    var incAlone = group(function (c) { return c.to_student === studentId && c.question === "alone"; });

    function pill(name, kind, mutual) {
      var color = kind === "alone" ? "var(--amber)" : kind === "in" ? "var(--accent)" : "var(--green)";
      return h("span", { class: "pill", style: { color: color, borderColor: mutual ? "var(--accent)" : "var(--border)" } },
        (mutual ? "↔ " : "") + name);
    }
    function grp(title, items) {
      return h("div", {}, h("div", { class: "section-title" }, title),
        items.length ? h("div", { class: "chip-row" }, items) : h("span", { class: "muted tiny" }, "—"));
    }
    var empty = out.length + outAlone.length + inc.length + incAlone.length === 0;
    return h("div", { style: { borderBottom: "1px solid var(--border)", paddingBottom: "14px" } },
      h("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" } },
        h("b", {}, survey.title), h("span", { class: "muted tiny" }, fmtDate(survey.conducted_on))),
      empty ? h("span", { class: "muted tiny" }, "Нет ответов в этом срезе.") :
        h("div", { class: "two-col", style: { gap: "16px" } },
          h("div", {},
            grp("Выбирает (кино/проект)", out.map(function (c) { return pill(nameOf(c.to_student), "out", !!outPos[c.to_student] && !!incPos[c.to_student]); })),
            outAlone.length ? h("div", { style: { marginTop: "10px" } }, grp("Отметил(а) «часто один»", outAlone.map(function (c) { return pill(nameOf(c.to_student), "alone", false); }))) : null),
          h("div", {},
            grp("Выбрали его / её", inc.map(function (c) { return pill(nameOf(c.from_student), "in", !!outPos[c.from_student] && !!incPos[c.from_student]); })),
            incAlone.length ? h("div", { style: { marginTop: "10px" } }, grp("Отметили как «часто один»", incAlone.map(function (c) { return pill(nameOf(c.from_student), "alone", false); }))) : null)));
  }

  function interventionItem(iv, dyn, studentId) {
    var endRef = iv.ended_on || iv.started_on;
    var before = null, after = null;
    for (var i = dyn.length - 1; i >= 0; i--) { if (dyn[i].date <= iv.started_on) { before = dyn[i]; break; } }
    for (var j = 0; j < dyn.length; j++) { if (dyn[j].date >= endRef) { after = dyn[j]; break; } }
    var delta = before && after && before.survey_id !== after.survey_id ? after.in_degree - before.in_degree : null;
    return h("div", { style: { borderBottom: "1px solid var(--border)", paddingBottom: "14px" } },
      h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
        h("b", {}, iv.title), stars(iv.effectiveness), h("div", { style: { flex: "1" } }),
        h("span", { class: "muted tiny" }, fmtDate(iv.started_on) + " — " + (iv.ended_on ? fmtDate(iv.ended_on) : "по наст. время")),
        h("button", { class: "btn btn-danger btn-sm", onClick: function () { if (confirm("Удалить вмешательство?")) API.del("/api/interventions/" + iv.id).then(function () { renderStudent(studentId); }); } }, "✕")),
      iv.description ? h("p", { class: "muted", style: { marginTop: "6px" } }, iv.description) : null,
      iv.outcome ? h("p", { style: { marginTop: "6px" } }, h("b", {}, "Итог: "), iv.outcome) : null,
      h("div", { style: { marginTop: "8px" } }, delta != null
        ? h("span", { class: "pill" }, "Входящие выборы: " + before.in_degree + " → " + after.in_degree + " ", deltaSpan(delta))
        : h("span", { class: "muted tiny" }, "Недостаточно срезов до и после для оценки динамики.")));
  }

  /* --------------------------------------------------------- card forms */
  function noteForm(sid) {
    var ta = h("textarea", { class: "textarea", placeholder: "Новая заметка…" });
    var btn = h("button", { class: "btn btn-primary btn-sm", onClick: function () {
      var body = ta.value.trim(); if (!body) return; btn.disabled = true;
      API.post("/api/students/" + sid + "/notes", { body: body }).then(function () { renderStudent(sid); }).catch(function (e) { alert(e.message); btn.disabled = false; }); } }, "Добавить заметку");
    return h("div", { class: "stack" }, ta, h("div", {}, btn));
  }
  function meetingForm(sid) {
    var today = new Date().toISOString().slice(0, 10);
    var dateIn = h("input", { class: "input", type: "date", value: today });
    var sumIn = h("textarea", { class: "textarea", placeholder: "Краткое содержание встречи…" });
    var btn = h("button", { class: "btn btn-primary btn-sm", onClick: function () {
      btn.disabled = true;
      API.post("/api/students/" + sid + "/meetings", { met_on: dateIn.value, summary: sumIn.value.trim() }).then(function () { renderStudent(sid); }).catch(function (e) { alert(e.message); btn.disabled = false; }); } }, "Добавить встречу");
    return h("div", { class: "stack" }, h("div", { class: "row" }, field("Дата встречи", dateIn)), sumIn, h("div", {}, btn));
  }
  function interventionForm(sid) {
    var today = new Date().toISOString().slice(0, 10);
    var wrap = h("div");
    var openBtn = h("button", { class: "btn btn-primary btn-sm", onClick: function () { wrap.replaceChildren(card()); } }, "+ Вмешательство");
    wrap.appendChild(openBtn);
    function card() {
      var titleIn = h("input", { class: "input", placeholder: "Например, Программа развития навыков общения" });
      var descIn = h("textarea", { class: "textarea" });
      var startIn = h("input", { class: "input", type: "date", value: today });
      var endIn = h("input", { class: "input", type: "date" });
      var effIn = h("select", { class: "select" }, h("option", { value: "" }, "—"), h("option", { value: "1" }, "1 — низкая"), h("option", { value: "2" }, "2"), h("option", { value: "3" }, "3 — средняя"), h("option", { value: "4" }, "4"), h("option", { value: "5" }, "5 — высокая"));
      var outcomeIn = h("textarea", { class: "textarea" });
      function save() {
        var title = titleIn.value.trim(); if (!title) return;
        API.post("/api/students/" + sid + "/interventions", { title: title, description: descIn.value.trim(), started_on: startIn.value, ended_on: endIn.value, effectiveness: effIn.value ? Number(effIn.value) : null, outcome: outcomeIn.value.trim() })
          .then(function () { renderStudent(sid); }).catch(function (e) { alert(e.message); });
      }
      return h("div", { class: "card card-pad", style: { background: "var(--surface-2)", marginBottom: "12px" } },
        h("div", { class: "stack" }, field("Название", titleIn), field("Описание", descIn),
          h("div", { class: "row" }, field("Начало", startIn), field("Окончание", endIn), field("Эффективность", effIn)),
          field("Итог / результат", outcomeIn),
          h("div", { style: { display: "flex", gap: "10px" } },
            h("button", { class: "btn btn-primary btn-sm", onClick: save }, "Сохранить"),
            h("button", { class: "btn btn-sm", onClick: function () { wrap.replaceChildren(openBtn); } }, "Отмена"))));
    }
    return wrap;
  }

  /* ------------------------------------------------------- line chart */
  function lineChart(points) {
    if (!points.length) return emptyState("Нет данных для динамики", "Нужен хотя бы один срез.");
    var W = 640, H = 220, pad = { t: 20, r: 20, b: 34, l: 34 };
    var iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    var vals = points.map(function (p) { return p.in_degree; });
    var max = Math.max.apply(null, vals.concat([1]));
    var min = 0, span = (max - min) || 1;
    function X(i) { return pad.l + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw); }
    function Y(v) { return pad.t + ih - ((v - min) / span) * ih; }
    var line = points.map(function (p, i) { return (i === 0 ? "M" : "L") + " " + X(i).toFixed(1) + " " + Y(p.in_degree).toFixed(1); }).join(" ");
    var area = line + " L " + X(points.length - 1).toFixed(1) + " " + (pad.t + ih).toFixed(1) + " L " + X(0).toFixed(1) + " " + (pad.t + ih).toFixed(1) + " Z";
    var kids = [];
    [max, Math.round(max / 2), 0].forEach(function (t) {
      kids.push(hs("line", { class: "gridline", x1: pad.l, x2: W - pad.r, y1: Y(t), y2: Y(t) }));
      kids.push(hs("text", { class: "lbl", x: pad.l - 8, y: Y(t) + 3, "text-anchor": "end" }, String(t)));
    });
    kids.push(hs("path", { class: "area", d: area }));
    kids.push(hs("path", { class: "line", d: line }));
    points.forEach(function (p, i) {
      kids.push(hs("circle", { class: "dot", cx: X(i), cy: Y(p.in_degree), r: 4.5 }));
      kids.push(hs("text", { class: "lbl", x: X(i), y: H - 12, "text-anchor": "middle" }, fmtShort(p.date)));
    });
    return hs("svg", { class: "chart", viewBox: "0 0 " + W + " " + H }, kids);
  }

  function ageText(birth) {
    if (!birth) return "возраст не указан";
    var d = new Date(birth + "T00:00:00"); if (isNaN(d.getTime())) return "возраст не указан";
    var now = new Date(), age = now.getFullYear() - d.getFullYear(), m = now.getMonth() - d.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
    return age + " лет";
  }

  /* ============================================================ router */
  function router() {
    var parts = (location.hash.slice(1) || "/").split("/").filter(Boolean);
    if (!state.user) { renderLogin(); return; }
    if (parts.length === 0) { renderDashboard(); return; }
    if (parts[0] === "student" && parts[1]) { renderStudent(Number(parts[1])); return; }
    renderDashboard();
  }
  window.addEventListener("hashchange", router);

  /* ============================================================== boot */
  mount(spinner());
  var token = localStorage.getItem("izolyat.token");
  (token ? API.get("/api/auth/me").then(function (d) { state.user = d.user; }).catch(function () { state.user = null; }) : Promise.resolve())
    .then(function () { router(); });
})();
