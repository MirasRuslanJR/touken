/* Изолят — страница прохождения опроса учеником.
 *
 * Два языка, русский и казахский. Это не украшение: в НИШ и региональных
 * школах часть класса думает и отвечает на казахском, а неточно понятый
 * вопрос портит сами данные, ради которых всё и делается. Выбранный язык
 * запоминается, чтобы ученику не переключать его на каждом экране.
 */
(function () {
  "use strict";

  /* --------------------------------------------------------------- язык */
  var STRINGS = {
    ru: {
      // «Конфиденциальный», а не «анонимный»: ответ хранится связанным с
      // учеником — иначе не посчитать явку и не показать его динамику по
      // срезам. Обещать ребёнку анонимность, которой нет, нельзя.
      anon: "конфиденциальный опрос",
      enterCode: "Введите ваш код",
      codePlaceholder: "Например, K7P2QT",
      start: "Начать опрос",
      // Текст описывает ровно то, что делает система. Раньше здесь стояло
      // «кого ты отметил как одинокого, не увидит никто, даже он» — это
      // обещало больше, чем система даёт: интерфейс психологу авторство
      // действительно не показывает, но в базе связь есть, и администратор
      // её увидит. Ребёнку нельзя обещать того, что не обеспечено.
      privacy: "Одноклассники не увидят твои ответы. Психолог видит общую картину класса: кто с кем дружит. Кого ты отметил как одинокого — психологу не показывается: он увидит только, сколько человек отметили каждого.",
      linkBad: "Ссылка на опрос недействительна.",
      closed: "Этот опрос сейчас закрыт.",
      question: "Вопрос",
      of: "из",
      pick: "Можно выбрать до",
      picked: "Выбрано:",
      back: "Назад",
      next: "Далее",
      send: "Отправить ответы",
      thanks: "Спасибо!",
      done: "Ваши ответы записаны. Повторно пройти опрос нельзя.",
      skip: "Пропустить вопрос",
    },
    kk: {
      anon: "құпия сауалнама",
      enterCode: "Кодыңызды енгізіңіз",
      codePlaceholder: "Мысалы, K7P2QT",
      start: "Сауалнаманы бастау",
      privacy: "Сыныптастарың жауаптарыңды көрмейді. Психолог сыныптың жалпы көрінісін көреді: кім кіммен дос екенін. Ал сен кімді жалғыз деп белгілегеніңді психологқа көрсетілмейді: ол тек әр оқушыны қанша адам белгілегенін көреді.",
      linkBad: "Сауалнама сілтемесі жарамсыз.",
      closed: "Бұл сауалнама қазір жабық.",
      question: "Сұрақ",
      of: "/",
      pick: "Ең көбі таңдауға болады:",
      picked: "Таңдалды:",
      back: "Артқа",
      next: "Әрі қарай",
      send: "Жауаптарды жіберу",
      thanks: "Рахмет!",
      done: "Жауаптарың жазылды. Сауалнаманы қайта өтуге болмайды.",
      skip: "Сұрақты өткізіп жіберу",
    },
  };

  var lang = "ru";
  try {
    var saved = localStorage.getItem("izolyat.lang");
    if (saved && STRINGS[saved]) lang = saved;
    else if ((navigator.language || "").toLowerCase().indexOf("kk") === 0) lang = "kk";
  } catch (e) { /* приватный режим — остаёмся на русском */ }

  function t(key) { return STRINGS[lang][key]; }
  function qText(q) { return lang === "kk" ? (q.text_kk || q.text) : q.text; }

  /* --------------------------------------------------------------- DOM */
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

  // Знак «Изолята»: связанная тройка и узел, оставшийся в стороне. Тот же,
  // что на фавиконке и в кабинете психолога, — страница опроса не должна
  // выглядеть чужой.
  function logoMark() {
    var NS = "http://www.w3.org/2000/svg";
    function el(tag, attrs) {
      var n = document.createElementNS(NS, tag);
      Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
      return n;
    }
    var svg = el("svg", { viewBox: "0 0 64 64", "aria-hidden": "true", "class": "logo-mark" });
    var lines = el("g", {
      stroke: "currentColor", "stroke-width": "3", "stroke-linecap": "round", opacity: "0.55",
    });
    [[24, 22, 40, 26], [24, 22, 27, 40], [40, 26, 27, 40]].forEach(function (c) {
      lines.appendChild(el("line", { x1: c[0], y1: c[1], x2: c[2], y2: c[3] }));
    });
    svg.appendChild(lines);
    var dots = el("g", { fill: "currentColor" });
    [[24, 22], [40, 26], [27, 40]].forEach(function (c) {
      dots.appendChild(el("circle", { cx: c[0], cy: c[1], r: "6" }));
    });
    svg.appendChild(dots);
    svg.appendChild(el("circle", {
      cx: "47", cy: "47", r: "6.5", fill: "none",
      stroke: "currentColor", "stroke-width": "3", "class": "logo-lone",
    }));
    return svg;
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
    }, function () {
      // Ученик проходит опрос с телефона по школьному Wi-Fi — обрыв связи
      // здесь обычное дело. Браузерное «Failed to fetch» ему ничего не скажет,
      // а бросать ответы на полпути нельзя: он их уже ввёл.
      throw new Error(lang === "kk"
        ? "Байланыс жоқ. Wi-Fi тексеріп, қайта жіберіп көріңіз."
        : "Нет связи. Проверьте Wi-Fi и попробуйте отправить ещё раз.");
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

  // Переключатель языка. Перерисовываем текущий экран заново, чтобы перевод
  // применился и к уже показанным вопросам.
  var rerender = function () {};
  function langSwitch() {
    function btn(code, label) {
      return h("button", {
        class: "lang-btn" + (lang === code ? " on" : ""),
        type: "button",
        onClick: function () {
          if (lang === code) return;
          lang = code;
          try { localStorage.setItem("izolyat.lang", code); } catch (e) {}
          rerender();
        },
      }, label);
    }
    return h("div", { class: "lang-switch" }, btn("ru", "Рус"), btn("kk", "Қаз"));
  }

  function boot() {
    if (!surveyId) { mount(card(showError(t("linkBad")))); return; }
    mount(h("div", { class: "spinner" }));
    api("GET", "/api/public/surveys/" + surveyId + "/info")
      .then(function (info) {
        if (!info.is_open) {
          rerender = function () {
            mount(card([h("h2", { style: "font-size:20px;margin-bottom:8px" }, info.title || "Опрос"),
                        showError(t("closed")), langSwitch()]));
          };
          rerender();
          return;
        }
        renderIntro(info);
      })
      .catch(function (e) { mount(card(showError(e.message))); });
  }

  function renderIntro(info) {
    var codeValue = "";
    rerender = function () { draw(); };

    function draw() {
      var codeIn = h("input", {
        class: "input", placeholder: t("codePlaceholder"), value: codeValue,
        style: "text-align:center;text-transform:uppercase;letter-spacing:4px;font-weight:800;font-size:18px",
      });
      codeIn.addEventListener("input", function () { codeValue = codeIn.value; });
      var msg = h("div");
      var btn = h("button", { class: "btn btn-primary btn-lg", style: "width:100%" }, t("start"));

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
        langSwitch(),
        h("div", { class: "survey-hero" },
          h("div", { class: "hicon" }, logoMark()),
          h("h1", {}, info.title),
          h("div", { class: "sub" }, t("anon"))),
        card([
          h("div", { class: "field", style: "margin-bottom:14px" },
            h("label", { style: "text-align:center" }, t("enterCode")), codeIn),
          msg, btn,
          // Текст описывает ровно то, что делает система. Раньше здесь стояло
          // «Ответы анонимны», хотя психолог видел поимённо и кто кого выбрал,
          // и кто кого назвал одиноким. Первое — неизбежная часть социометрии
          // (из этого и строится граф класса), второе убрано из интерфейса:
          // психологу приходит только счётчик. В самой базе связь остаётся —
          // без неё не посчитать явку и не показать динамику ребёнка, — и
          // ребёнку про это обещать «не увидит никто» нельзя.
          h("p", { class: "muted tiny", style: "margin-top:16px;text-align:center" }, t("privacy")),
        ])));
      codeIn.focus();
    }
    draw();
  }

  // Пошаговый опрос: по одному вопросу на экран, с кнопками «Назад»/«Далее».
  function renderQuestions(code, data) {
    var selections = {}; // key -> Set of ids
    data.questions.forEach(function (q) { selections[q.key] = new Set(); });
    var total = data.questions.length;
    var step = 0;
    var msg = h("div");

    var bar, lbl, progress, stepHost;

    function shell() {
      bar = h("span");
      lbl = h("span", { class: "lbl" });
      progress = h("div", { class: "survey-progress" }, lbl, h("div", { class: "bar" }, bar));
      stepHost = h("div");
      mount(h("div", {},
        langSwitch(),
        h("div", { style: "text-align:center;margin-bottom:16px" },
          h("h1", { style: "font-size:21px;letter-spacing:-0.02em" }, data.title),
          h("div", { class: "muted", style: "font-size:14px;margin-top:4px" }, data.class_name)),
        progress,
        stepHost,
        msg));
    }

    // Флаг, а не только disabled на кнопке: переключение языка перерисовывает
    // экран и создаёт новую кнопку — без флага ученик мог отправить ответы
    // второй раз, пока идёт первый запрос, и получить 409 «вы уже проходили».
    var sending = false;

    function submit(btn) {
      if (sending) return;
      sending = true;
      clear(msg);
      btn.disabled = true;
      var answers = {};
      Object.keys(selections).forEach(function (k) { answers[k] = Array.from(selections[k]); });
      api("POST", "/api/public/surveys/" + surveyId + "/submit", { code: code, answers: answers })
        .then(function () { renderDone(); })
        .catch(function (e) {
          sending = false;
          setContent(msg, showError(e.message));
          btn.disabled = false;
        });
    }

    function renderStep() {
      var q = data.questions[step];
      var set = selections[q.key];
      lbl.textContent = t("question") + " " + (step + 1) + " " + t("of") + " " + total;
      bar.style.width = Math.round((step + 1) / total * 100) + "%";

      // Без анимации выезда: вопрос должен появляться сразу. Ученик проходит
      // опрос за полторы минуты, и каждая задержка на трёх экранах заметна.
      var qcard = h("div", { class: "q-card" });
      function hintText() { return t("pick") + " " + q.max + ". " + t("picked") + " " + set.size; }
      var hint = h("div", { class: "q-hint" }, hintText());
      var grid = h("div", { class: "choice-grid" });
      data.roster.forEach(function (st) {
        var selected = set.has(st.id);
        var ini = h("span", { class: "ini" }, selected ? "\u2713" : initials(st.full_name));
        var b = h("button", { class: "choice" + (selected ? " on" : ""), type: "button" }, ini, h("span", {}, st.full_name));
        b.addEventListener("click", function () {
          if (set.has(st.id)) { set.delete(st.id); b.classList.remove("on"); ini.textContent = initials(st.full_name); }
          else { if (set.size >= q.max) return; set.add(st.id); b.classList.add("on"); ini.textContent = "\u2713"; }
          hint.textContent = hintText();
        });
        grid.appendChild(b);
      });
      qcard.appendChild(h("div", { class: "q-head" }, h("span", { class: "q-num" }, String(step + 1)), h("div", { class: "q-title" }, qText(q))));
      qcard.appendChild(hint);
      qcard.appendChild(grid);

      var backBtn = h("button", { class: "btn", type: "button" }, t("back"));
      backBtn.addEventListener("click", function () { if (step > 0) { step--; renderStep(); } });
      var last = step === total - 1;
      var nextBtn = h("button", { class: "btn btn-primary", type: "button", style: "flex:1" }, last ? t("send") : t("next"));
      if (last && sending) nextBtn.disabled = true;  // перерисовка во время отправки
      nextBtn.addEventListener("click", function () {
        if (last) submit(nextBtn);
        else { step++; renderStep(); }
      });
      var nav = h("div", { class: "survey-nav" }, step > 0 ? backBtn : null, nextBtn);

      setContent(stepHost, qcard, nav);
      clear(msg);
      window.scrollTo(0, 0);
    }

    rerender = function () { shell(); renderStep(); };
    rerender();
  }

  function renderDone() {
    rerender = function () {
      mount(h("div", { style: "text-align:center;padding:34px 0" },
        langSwitch(),
        h("div", { class: "done-circle" }, "\u2713"),
        h("h1", { style: "font-size:24px;margin-bottom:8px" }, t("thanks")),
        h("p", { class: "muted", style: "max-width:360px;margin:0 auto" }, t("done"))));
    };
    rerender();
  }

  boot();
})();
