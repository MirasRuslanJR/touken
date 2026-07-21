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

  function initials(name) {
    var p = String(name).trim().split(/\s+/);
    return (((p[0] || "")[0] || "") + ((p[1] || "")[0] || "")).toUpperCase();
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
    var codeIn = h("input", { class: "input", placeholder: "Например, K7P2QT", style: "text-align:center;text-transform:uppercase;letter-spacing:4px;font-weight:800;font-size:18px" });
    var msg = h("div");
    var btn = h("button", { class: "btn btn-primary btn-lg", style: "width:100%" }, "Начать опрос →");
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
    mount(h("div", {},
      h("div", { class: "survey-hero" },
        h("div", { class: "hicon" }, "И"),
        h("h1", {}, info.title),
        h("div", { class: "sub" }, info.class_name + " · анонимный опрос")),
      card([
        h("div", { class: "field", style: "margin-bottom:14px" },
          h("label", { style: "text-align:center" }, "Введите ваш код"), codeIn),
        msg, btn,
        h("p", { class: "muted tiny", style: "margin-top:16px;text-align:center" }, "🔒 Ответы анонимны. Другие ученики их не видят.")
      ])));
  }

  // Пошаговый опрос: по одному вопросу на экран, с кнопками «Назад»/«Далее».
  function renderQuestions(code, data) {
    var selections = {}; // key -> Set of ids
    data.questions.forEach(function (q) { selections[q.key] = new Set(); });
    var total = data.questions.length;
    var step = 0;
    var msg = h("div");

    var bar = h("span");
    var lbl = h("span", { class: "lbl" });
    var progress = h("div", { class: "survey-progress" }, lbl, h("div", { class: "bar" }, bar));
    var stepHost = h("div");

    function submit(btn) {
      clear(msg);
      btn.disabled = true;
      var answers = {};
      Object.keys(selections).forEach(function (k) { answers[k] = Array.from(selections[k]); });
      api("POST", "/api/public/surveys/" + surveyId + "/submit", { code: code, answers: answers })
        .then(function () { renderDone(); })
        .catch(function (e) { setContent(msg, showError(e.message)); btn.disabled = false; });
    }

    function renderStep() {
      var q = data.questions[step];
      var set = selections[q.key];
      lbl.textContent = "Вопрос " + (step + 1) + " из " + total;
      bar.style.width = Math.round((step + 1) / total * 100) + "%";

      var qcard = h("div", { class: "q-card q-anim" });
      var hint = h("div", { class: "q-hint" }, "Можно выбрать до " + q.max + ". Выбрано: " + set.size);
      var grid = h("div", { class: "choice-grid" });
      data.roster.forEach(function (st) {
        var selected = set.has(st.id);
        var ini = h("span", { class: "ini" }, selected ? "✓" : initials(st.full_name));
        var b = h("button", { class: "choice" + (selected ? " on" : ""), type: "button" }, ini, h("span", {}, st.full_name));
        b.addEventListener("click", function () {
          if (set.has(st.id)) { set.delete(st.id); b.classList.remove("on"); ini.textContent = initials(st.full_name); }
          else { if (set.size >= q.max) return; set.add(st.id); b.classList.add("on"); ini.textContent = "✓"; }
          hint.textContent = "Можно выбрать до " + q.max + ". Выбрано: " + set.size;
        });
        grid.appendChild(b);
      });
      qcard.appendChild(h("div", { class: "q-head" }, h("span", { class: "q-num" }, String(step + 1)), h("div", { class: "q-title" }, q.text)));
      qcard.appendChild(hint);
      qcard.appendChild(grid);

      var backBtn = h("button", { class: "btn", type: "button" }, "← Назад");
      backBtn.addEventListener("click", function () { if (step > 0) { step--; renderStep(); } });
      var last = step === total - 1;
      var nextBtn = h("button", { class: "btn btn-primary", type: "button", style: "flex:1" }, last ? "Отправить ответы" : "Далее →");
      nextBtn.addEventListener("click", function () {
        if (last) submit(nextBtn);
        else { step++; renderStep(); }
      });
      var nav = h("div", { class: "survey-nav" }, step > 0 ? backBtn : null, nextBtn);

      setContent(stepHost, qcard, nav);
      clear(msg);
      window.scrollTo(0, 0);
    }

    mount(h("div", {},
      h("div", { style: "text-align:center;margin-bottom:16px" },
        h("h1", { style: "font-size:21px;letter-spacing:-0.02em" }, data.title),
        h("div", { class: "muted", style: "font-size:14px;margin-top:4px" }, data.class_name)),
      progress,
      stepHost,
      msg));
    renderStep();
  }

  function renderDone() {
    mount(h("div", { style: "text-align:center;padding:34px 0" },
      h("div", { class: "done-circle" }, "✓"),
      h("h1", { style: "font-size:24px;margin-bottom:8px" }, "Спасибо!"),
      h("p", { class: "muted", style: "max-width:360px;margin:0 auto" }, "Ваши ответы записаны. Повторно пройти опрос нельзя.")));
  }

  boot();
})();
