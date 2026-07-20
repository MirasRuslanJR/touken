/* Изолят — страница прохождения опроса учеником (анонимно, по коду). */
(function () {
  "use strict";

  // Рекурсивно добавляет ребёнка (узел, строку/число, вложенный массив, либо
  // null/false — пропускается). Рекурсия важна: массивы могут быть вложенными
  // (например, список блоков внутри списка детей), и без неё appendChild
  // получил бы Array вместо Node.
  function append(parent, kid) {
    if (kid == null || kid === false) return;
    if (Array.isArray(kid)) {
      for (var i = 0; i < kid.length; i++) append(parent, kid[i]);
      return;
    }
    parent.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }

  function h(tag, props) {
    var e = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v == null || v === false) return;
        if (k === "class") e.className = v;
        else if (k === "html") e.innerHTML = v;
        else if (k === "value") e.value = v;
        else if (k.slice(0, 2) === "on" && typeof v === "function") e.addEventListener(k.slice(2).toLowerCase(), v);
        else e.setAttribute(k, v);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(e, arguments[i]);
    return e;
  }

  // Совместимая с любым браузером очистка/замена содержимого (без replaceChildren).
  function clear(node) { node.innerHTML = ""; }
  function setContent(node) {
    clear(node);
    for (var i = 1; i < arguments.length; i++) append(node, arguments[i]);
  }

  var root = document.getElementById("survey");
  function mount(node) { clear(root); root.appendChild(node); }

  function api(method, url, body) {
    var opt = { method: method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opt.body = JSON.stringify(body);
    return fetch(url, opt).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (d) {
        if (!r.ok) throw new Error((d && d.detail) || ("Ошибка " + r.status));
        return d;
      });
    });
  }

  var params = new URLSearchParams(location.search);
  var surveyId = params.get("survey");

  function card(children) { return h("div", { class: "card card-pad" }, children); }

  function showError(msg) {
    return h("div", { class: "alert alert-error", style: "margin-bottom:14px" }, msg);
  }

  function boot() {
    if (!surveyId) { mount(card(showError("Ссылка на опрос недействительна."))); return; }
    mount(h("div", { class: "spinner" }));
    api("GET", "/api/public/surveys/" + surveyId + "/info")
      .then(function (info) {
        if (!info.is_open) {
          mount(card([h("h2", { style: "font-size:20px;margin-bottom:8px" }, info.title || "Опрос"), showError("Этот опрос сейчас закрыт.")]));
          return;
        }
        renderIntro(info);
      })
      .catch(function (e) { mount(card(showError(e.message))); });
  }

  function renderIntro(info) {
    var codeIn = h("input", { class: "input", placeholder: "Например, K7P2QT", style: "text-transform:uppercase;letter-spacing:2px;font-weight:600" });
    var msg = h("div");
    var btn = h("button", { class: "btn btn-primary btn-lg", style: "width:100%" }, "Начать опрос");
    function start() {
      var code = codeIn.value.trim().toUpperCase();
      if (!code) return;
      clear(msg);
      btn.disabled = true;
      api("POST", "/api/public/surveys/" + surveyId + "/start", { code: code })
        .then(function (data) { renderQuestions(code, data); })
        .catch(function (e) { setContent(msg, showError(e.message)); btn.disabled = false; });
    }
    codeIn.addEventListener("keydown", function (e) { if (e.key === "Enter") start(); });
    btn.addEventListener("click", start);
    mount(card([
      h("h2", { style: "font-size:22px;margin-bottom:4px" }, info.title),
      h("p", { class: "muted", style: "margin-bottom:18px" }, info.class_name + " · анонимный опрос"),
      h("div", { class: "field", style: "margin-bottom:14px" }, h("label", {}, "Введите ваш код"), codeIn),
      msg, btn,
      h("p", { class: "muted tiny", style: "margin-top:16px;text-align:center" }, "Ответы анонимны. Другие ученики их не видят."),
    ]));
  }

  function renderQuestions(code, data) {
    var selections = {}; // key -> Set of ids
    data.questions.forEach(function (q) { selections[q.key] = new Set(); });
    var msg = h("div");

    var blocks = data.questions.map(function (q) {
      var hint = h("div", { class: "q-hint" }, "Можно выбрать до " + q.max + ". Выбрано: 0");
      var grid = h("div", { class: "choice-grid" });
      data.roster.forEach(function (st) {
        var b = h("button", { class: "choice", type: "button" }, st.full_name);
        b.addEventListener("click", function () {
          var set = selections[q.key];
          if (set.has(st.id)) { set.delete(st.id); b.classList.remove("on"); }
          else {
            if (set.size >= q.max) return;
            set.add(st.id); b.classList.add("on");
          }
          hint.textContent = "Можно выбрать до " + q.max + ". Выбрано: " + set.size;
        });
        grid.appendChild(b);
      });
      return h("div", { class: "q-block" }, h("div", { class: "q-title" }, q.text), hint, grid);
    });

    var submitBtn = h("button", { class: "btn btn-primary btn-lg", style: "width:100%;margin-top:8px" }, "Отправить ответы");
    submitBtn.addEventListener("click", function () {
      clear(msg);
      submitBtn.disabled = true;
      var answers = {};
      Object.keys(selections).forEach(function (k) { answers[k] = Array.from(selections[k]); });
      api("POST", "/api/public/surveys/" + surveyId + "/submit", { code: code, answers: answers })
        .then(function () { renderDone(); })
        .catch(function (e) { setContent(msg, showError(e.message)); submitBtn.disabled = false; });
    });

    mount(card([
      h("h2", { style: "font-size:20px;margin-bottom:2px" }, data.title),
      h("p", { class: "muted", style: "margin-bottom:20px" }, data.class_name),
      blocks,
      msg, submitBtn,
    ]));
    window.scrollTo(0, 0);
  }

  function renderDone() {
    mount(card([
      h("div", { style: "text-align:center;padding:20px 0" },
        h("div", { style: "font-size:52px;margin-bottom:10px" }, "✓"),
        h("h2", { style: "font-size:22px;margin-bottom:8px" }, "Спасибо!"),
        h("p", { class: "muted" }, "Ваши ответы записаны. Повторно пройти опрос нельзя."))
    ]));
  }

  boot();
})();
