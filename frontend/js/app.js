/* =====================================================================
   Изолят — front-end SPA for the psychologist (vanilla JS + vis-network).
   ===================================================================== */
(function () {
  "use strict";

  // Цвета сообществ на социограмме — единственное цветное пятно в
  // интерфейсе. Подобраны под тёмный фон: достаточно светлые, чтобы
  // держать контраст с подложкой, но приглушённые — неоновые оттенки
  // режут глаз и мешают читать подписи узлов. Порядок задаёт
  // различимость соседних групп.
  var PALETTE = [
    "#6C77C4", "#4E9E82", "#B5813F", "#4A93A8", "#A76C86",
    "#7C6FAE", "#9A8F4A", "#5B8FA8", "#AE7A5C", "#7A8490",
  ];
  // Индекс связности — наша собственная свёртка взаимности, плотности и доли
  // изолятов. Она не сверялась с внешними нормами, поэтому везде, где число
  // показывается, рядом стоит эта оговорка: иначе оно читается как измеренная
  // величина, а не как наш способ отсортировать классы по вниманию.
  var WI_HINT = "Свёртка взаимности, плотности и доли изолятов. "
    + "Внутренняя шкала 0-100, с внешними нормами не сверялась: "
    + "годится, чтобы сравнивать классы между собой и с самими собой во времени.";
  // Оформление графа. Держим в одном месте, чтобы легенда и узлы не разошлись.
  //
  // Цвета фиксированные, не зависящие от темы: социограмма рисуется в тёмной
  // врезке и в светлом, и в тёмном интерфейсе (--net-bg в styles.css одинаков
  // для обеих тем). Это сознательно — граф остаётся главным объектом экрана,
  // единственным местом, где цвет кодирует данные, и не перестраивается под
  // тему на глазах у психолога, который сравнивает срезы.
  var GRAPH = {
    nodeBorder: "#35353D",
    nodeFill: "#1A1A1E",
    label: "#F2F2F4",
    // Изолят — то, ради чего открывают этот экран: приглушённая заливка и
    // отчётливая обводка. Узел читается с проектора, не превращаясь в неон.
    isolateFill: "#2E1513", isolateBorder: "#E5584D",
    unknownFill: "#18181C", unknownBorder: "#45454F",
    edge: "#33333B",
    mutual: "#6C61FF",
    bridge: "#C98A2E",
    highlight: "#4B3FFF",
  };
  var QLABEL = { cinema: "Кино", project: "Проект", alone: "«Часто один»" };
  // Виды и адресаты профилактических мероприятий. Списки закрытые: по ним
  // психолог отчитывается перед завучем, свободный текст свёл бы сводку на нет.
  var KINDS = [
    ["training", "Тренинг / групповое занятие"],
    ["class_hour", "Классный час"],
    ["diagnostics", "Групповая диагностика"],
    ["parents", "Работа с родителями"],
    ["teachers", "Работа с педагогами"],
    ["individual", "Индивидуальная беседа"],
    ["other", "Другое"],
  ];
  var TARGETS = [
    ["class", "Весь класс"],
    ["group", "Группа учеников"],
    ["student", "Один ученик"],
    ["adults", "Родители / педагоги"],
  ];
  // Казахские формулировки — не украшение: в НИШ и региональных школах часть
  // класса отвечает на казахском, а неточно понятый вопрос портит сами данные.
  var DEFAULT_QUESTIONS = [
    { key: "cinema", text: "С кем бы ты пошёл в кино?", text_kk: "Киноға кіммен барар едің?", hint: "положительный выбор" },
    { key: "project", text: "С кем хотел бы делать проект?", text_kk: "Жобаны кіммен бірге жасағың келеді?", hint: "положительный выбор" },
    { key: "alone", text: "Кто в классе часто остаётся один?", text_kk: "Сыныпта кім жиі жалғыз қалады?", hint: "сигнал изоляции" },
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
  // В журнале доступа важен не только день, но и время: вопрос проверки
  // звучит как «кто открывал карточку 14 сентября около двух часов».
  function fmtDateTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString("ru-RU", {
      day: "2-digit", month: "2-digit", year: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
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
  // На этих адресах 401 означает «неверные логин или пароль», а не «сессия
  // истекла»: сбрасывать токен и уводить на экран входа здесь нельзя — иначе
  // форма перерисовывается заново и стирает сообщение об ошибке вместе с
  // введённым e-mail. Пользователь видит только моргание и не понимает, что
  // именно не так.
  function isAuthEndpoint(url) {
    return url.indexOf("/api/auth/login") === 0
      || url.indexOf("/api/auth/register") === 0
      || url.indexOf("/api/auth/schools") === 0
      || url.indexOf("/api/auth/password") === 0;
  }

  function api(method, url, body) {
    var headers = { "Content-Type": "application/json" };
    var t = localStorage.getItem("izolyat.token");
    if (t) headers["Authorization"] = "Bearer " + t;
    var opt = { method: method, headers: headers };
    if (body !== undefined) opt.body = JSON.stringify(body);
    return fetch(url, opt).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (res.status === 401 && !isAuthEndpoint(url)) {
          var hadSession = !!state.user;
          localStorage.removeItem("izolyat.token");
          state.user = null;
          state.unseen = 0;
          // Сессия истекла или была завершена с другого устройства. Уводим на
          // вход, иначе пользователь видит «Сессия недействительна» на пустом
          // экране. При загрузке страницы (сессии ещё не было) не дёргаем
          // роутер: он и так отрисует экран входа сам.
          if (hadSession) setTimeout(function () { go("/"); }, 0);
        }
        if (!res.ok) throw new Error(errMsg(data, res.status));
        return data;
      });
    }, function () {
      // fetch отклоняется только при сетевой ошибке: сервер не поднят, нет
      // интернета, оборвалось соединение. Браузерное «Failed to fetch»
      // пользователю ничего не говорит.
      throw new Error("Нет связи с сервером. Проверьте подключение и повторите.");
    });
  }
  var API = {
    get: function (u) { return api("GET", u); },
    post: function (u, b) { return api("POST", u, b); },
    put: function (u, b) { return api("PUT", u, b); },
    del: function (u) { return api("DELETE", u); },
  };

  /* ----------------------------------------------------------------- тема
     Три состояния, как в системе: "system" (по настройке ОС), "light",
     "dark". Явный выбор проставляет data-theme на <html> и переживает
     перезагрузку; без выбора работает prefers-color-scheme.
     Хранилище может быть недоступно (приватный режим) — тогда просто
     остаёмся на системной теме, интерфейс от этого не страдает. */
  var THEME_KEY = "izolyat.theme";

  function currentTheme() {
    try {
      var v = localStorage.getItem(THEME_KEY);
      if (v === "light" || v === "dark") return v;
    } catch (e) {}
    return "system";
  }
  function systemIsDark() {
    try { return window.matchMedia("(prefers-color-scheme: dark)").matches; } catch (e) { return false; }
  }
  function applyTheme(mode) {
    var root = document.documentElement;
    if (mode === "light" || mode === "dark") root.setAttribute("data-theme", mode);
    else root.removeAttribute("data-theme");
    // Цвет адресной строки на телефоне должен совпадать с фоном страницы.
    var dark = mode === "dark" || (mode === "system" && systemIsDark());
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0B0B10" : "#FBFBFD");
  }
  function toggleTheme() {
    // Переключаем относительно того, что человек видит сейчас.
    var next = (currentTheme() === "dark" || (currentTheme() === "system" && systemIsDark()))
      ? "light" : "dark";
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
    applyTheme(next);
    // Перерисовываем текущий экран: иконка кнопки зависит от темы, а граф
    // на социограмме строится с цветами, снятыми на момент отрисовки.
    router();
  }
  function themeButton() {
    var dark = currentTheme() === "dark" || (currentTheme() === "system" && systemIsDark());
    var btn = h("button", {
      class: "btn btn-sm btn-icon", onClick: toggleTheme,
      title: dark ? "Светлая тема" : "Тёмная тема",
      "aria-label": dark ? "Включить светлую тему" : "Включить тёмную тему",
    });
    var svg = hs("svg", { viewBox: "0 0 24 24", fill: "none", "aria-hidden": "true" });
    if (dark) {
      // Солнце — нажатие включит светлую тему.
      svg.appendChild(hs("circle", { cx: "12", cy: "12", r: "4.2", fill: "currentColor" }));
      var rays = hs("g", { stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round" });
      [[12, 2, 12, 4], [12, 20, 12, 22], [2, 12, 4, 12], [20, 12, 22, 12],
       [4.9, 4.9, 6.3, 6.3], [17.7, 17.7, 19.1, 19.1],
       [19.1, 4.9, 17.7, 6.3], [6.3, 17.7, 4.9, 19.1]].forEach(function (c) {
        rays.appendChild(hs("line", { x1: c[0], y1: c[1], x2: c[2], y2: c[3] }));
      });
      svg.appendChild(rays);
    } else {
      // Луна — нажатие включит тёмную тему.
      svg.appendChild(hs("path", {
        d: "M20 14.2A8.2 8.2 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2z",
        fill: "currentColor",
      }));
    }
    btn.appendChild(svg);
    return btn;
  }

  /* ------------------------------------------------------------- ui atoms */
  // Знак «Изолята» — тот же, что на фавиконке: связанная тройка и узел,
  // оставшийся в стороне. Это и есть предмет работы программы, поэтому
  // в интерфейсе стоит он, а не первая буква названия.
  function logoMark() {
    var svg = hs("svg", { viewBox: "0 0 64 64", "aria-hidden": "true", class: "logo-mark" });
    var lines = hs("g", {
      stroke: "currentColor", "stroke-width": "3", "stroke-linecap": "round", opacity: "0.55",
    });
    [[24, 22, 40, 26], [24, 22, 27, 40], [40, 26, 27, 40]].forEach(function (c) {
      lines.appendChild(hs("line", { x1: c[0], y1: c[1], x2: c[2], y2: c[3] }));
    });
    svg.appendChild(lines);
    var dots = hs("g", { fill: "currentColor" });
    [[24, 22], [40, 26], [27, 40]].forEach(function (c) {
      dots.appendChild(hs("circle", { cx: c[0], cy: c[1], r: "6" }));
    });
    svg.appendChild(dots);
    // Отделённый узел: полый и другого цвета — его и ищет психолог.
    svg.appendChild(hs("circle", {
      cx: "47", cy: "47", r: "6.5", fill: "none",
      stroke: "currentColor", "stroke-width": "3", class: "logo-lone",
    }));
    return svg;
  }
  function spinner() { return h("div", { class: "center" }, h("div", { class: "spinner" })); }
  function alertBox(kind, msg) { return h("div", { class: "alert alert-" + kind }, msg); }
  function emptyState(title, hint, action) {
    return h("div", { class: "empty" }, h("div", { class: "big" }, title), hint ? h("div", { class: "muted" }, hint) : null, action ? h("div", { style: { marginTop: "16px" } }, action) : null);
  }
  function field(label, control) { return h("div", { class: "field" }, h("label", {}, label), control); }

  // Кнопка, которая блокируется на время запроса. При медленной сети двойной
  // клик по «Сохранить» создавал два класса / два мероприятия / два согласия:
  // модалка закрывается только по ответу сервера, а до него кнопка была живой.
  // Обработчик должен вернуть Promise — иначе кнопка просто сработает как есть.
  function asyncBtn(props, label) {
    var busy = false;
    var handler = props.onClick;
    var btn = h("button", Object.assign({}, props, {
      onClick: function () {
        if (busy) return;
        var result = handler();
        if (!result || typeof result.then !== "function") return;
        busy = true;
        btn.disabled = true;
        var original = btn.textContent;
        btn.textContent = "…";
        result.then(null, function () {}).then(function () {
          busy = false;
          btn.disabled = false;
          btn.textContent = original;
        });
      },
    }), label);
    return btn;
  }
  // Числовая плитка досчитывается до значения, а не появляется готовой:
  // на демонстрации это показывает, что показатель посчитан. Анимируются
  // только чистые числа — «—», проценты и строки вроде «12 из 25» выводятся
  // как есть, иначе на экране мелькал бы мусор.
  function countUp(el, target) {
    var calm = false;
    try { calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}
    var decimals = (String(target).split(".")[1] || "").length;
    if (calm || target === 0) { el.textContent = target.toFixed(decimals); return; }
    var start = 0, dur = 700, t0 = null;
    function step(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur);
      var eased = 1 - Math.pow(1 - p, 3);   // ease-out: быстро, затем мягко
      el.textContent = (start + (target - start) * eased).toFixed(decimals);
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = target.toFixed(decimals);
    }
    el.textContent = "0";
    requestAnimationFrame(step);
  }
  function tile(label, value, sub) {
    var valueEl = h("div", { class: "tile-value" });
    var num = typeof value === "number" ? value
      : (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value.trim()) ? parseFloat(value) : null);
    if (num !== null && isFinite(num)) countUp(valueEl, num);
    else valueEl.textContent = value == null ? "" : String(value);
    return h("div", { class: "tile" }, h("div", { class: "tile-label" }, label), valueEl, sub != null ? h("div", { class: "tile-sub" }, sub) : null);
  }
  function isolateBadge() { return h("span", { class: "badge badge-red" }, h("span", { class: "dot" }), "Изолят"); }
  // «Нет данных» — не мягкая форма «изолята», а отказ ставить статус: ответило
  // слишком мало класса, и отсутствие входящих выборов ничего не доказывает.
  function unknownBadge() {
    return h("span", { class: "pill", title: "Опрос прошло меньше 70% класса, судить об изоляции нельзя" },
      "нет данных");
  }
  function statusPill(status) {
    if (status === "isolate") return isolateBadge();
    if (status === "unknown") return unknownBadge();
    return h("span", { class: "pill badge-green" }, "есть связи");
  }
  // Одна-две номинации «часто остаётся один» — мнение одного-двух детей, а не
  // сигнал класса. Точное число ниже порога не показываем, чтобы психолог не
  // вешал на ребёнка ярлык с чужих слов (порог см. analytics.ALONE_MIN_REPORT).
  function aloneText(votes, reportable) {
    if (!votes) return 0;
    return reportable ? votes : "<3";
  }
  function lowDataPill(participation) {
    var pct = participation != null ? Math.round(participation * 100) : 0;
    return h("span", { class: "pill", style: { color: "var(--amber)", borderColor: "var(--amber)" },
      title: "Метрики среза считаются по ответившим и могут быть неполными" }, "явка " + pct + "%");
  }
  function communityPill(g) {
    var c = PALETTE[g % PALETTE.length];
    return h("span", { class: "pill", style: { color: c } }, h("span", { class: "swatch", style: { width: "9px", height: "9px", borderRadius: "50%", background: c } }), "Группа " + (g + 1));
  }
  function stars(v) {
    if (v == null) return h("span", { class: "muted" }, "—");
    var f = Math.max(0, Math.min(5, v));
    return h("span", { class: "stars" }, f + " из 5");
  }
  function deltaSpan(v) {
    var cls = v > 0 ? "delta-up" : v < 0 ? "delta-down" : "delta-flat";
    var sign = v > 0 ? "▲ +" : v < 0 ? "▼ " : "– ";
    return h("span", { class: cls }, sign + Math.abs(v));
  }

  function openModal(title, bodyNodes, footerNodes, wide) {
    var backdrop = h("div", { class: "modal-backdrop" });
    // Класс на body нужен для двух вещей: не прокручивать страницу под окном
    // и печатать только содержимое окна. Печать вызывается из окна с кодами
    // и из окна отчёта, и без этого на бумагу уходил ещё и экран за ними.
    document.body.classList.add("modal-open");
    function close() {
      backdrop.remove();
      window.removeEventListener("keydown", onKey);
      if (!document.querySelector(".modal-backdrop")) document.body.classList.remove("modal-open");
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    var modal = h("div", { class: "modal" + (wide ? " wide" : "") },
      h("div", { class: "modal-head no-print" }, h("h3", {}, title), h("button", { class: "btn btn-ghost btn-sm", onClick: close, title: "Закрыть" }, "\u00d7")),
      h("div", { class: "modal-body" }, bodyNodes),
      footerNodes ? h("div", { class: "modal-foot no-print" }, footerNodes) : null);
    backdrop.appendChild(modal);
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) close(); });
    window.addEventListener("keydown", onKey);
    document.body.appendChild(backdrop);
    return close;
  }

  /* ---------------------------------------------------------- app state */
  var state = { user: null, unseen: 0, features: {} };

  function role() { return (state.user && state.user.role) || "psychologist"; }
  function canCasework() { return role() === "psychologist" || role() === "admin"; }
  function canSchool() { return role() === "head" || role() === "admin"; }
  function isAdmin() { return role() === "admin"; }
  var dash = {
    classes: null, classId: null, cls: null, students: [], surveys: [],
    surveyId: null, analysis: null, prevAnalysis: null, loaded: false,
    // Кэш аналитики по срезам. Переключение Time Slider данные не меняет, а
    // каждый запрос заново строит граф и считает betweenness O(V·E) — без кэша
    // протаскивание слайдера по 8 срезам давало ~24 запроса и столько же
    // полных пересчётов. Сбрасывается при любом изменении данных.
    cache: {}, keepCache: false, consent: null,
    filters: { isolate: true, bridge: true, mutual: true, community: "", anon: false },
    network: null, nodesDS: null, edgesDS: null,
    anonMap: null, anonMapFor: null,
  };

  function stopNetwork() {
    if (dash.network) { try { dash.network.destroy(); } catch (e) {} dash.network = null; }
    dash.nodesDS = null; dash.edgesDS = null;
  }
  function go(path) { if (location.hash === "#" + path) router(); else location.hash = "#" + path; }

  var ROLE_LABEL = { psychologist: "Психолог", head: "Завуч", admin: "Психолог · администратор" };

  // Раздел считается активным не только на своём точном адресе: страница
  // класса и карточка ученика относятся к «Классам», иначе при переходе внутрь
  // подсветка пропадала и казалось, что меню не работает.
  var NAV_SECTIONS = {
    "/": ["/", "/class", "/student"],
    "/alerts": ["/alerts"],
    "/prevention": ["/prevention"],
    "/school": ["/school"],
    "/staff": ["/staff"],
    "/audit": ["/audit"],
  };

  function navLink(path, label, badge) {
    var current = location.hash.slice(1) || "/";
    var section = current === "/" ? "/" : "/" + current.split("/").filter(Boolean)[0];
    var active = (NAV_SECTIONS[path] || [path]).indexOf(section) >= 0;
    return h("a", { class: "navlink" + (active ? " on" : ""), href: "#" + path },
      label,
      badge ? h("span", { class: "navbadge" }, badge > 99 ? "99+" : String(badge)) : null);
  }

  // Боковое меню вместо горизонтального: разделов шесть, и в строке они
  // раньше сжимались до нечитаемых огрызков. Сбоку помещаются целиком,
  // сгруппированы по смыслу, а вся ширина страницы остаётся содержимому.
  // На узких экранах панель уезжает наверх и прокручивается горизонтально
  // (см. медиазапросы в styles.css).
  function shell(content) {
    var frag = document.createDocumentFragment();

    var groups = [];
    if (canCasework()) {
      groups.push({ title: "Работа с классами", items: [
        navLink("/", "Классы"),
        navLink("/alerts", "Входящие", state.unseen),
        navLink("/prevention", "Профилактика"),
      ]});
    }
    var manage = [];
    if (canSchool()) manage.push(navLink("/school", "Школа"));
    if (isAdmin()) manage.push(navLink("/staff", "Сотрудники"));
    if (isAdmin()) manage.push(navLink("/audit", "Журнал"));
    if (manage.length) groups.push({ title: "Управление", items: manage });

    var nav = [];
    groups.forEach(function (g) {
      nav.push(h("div", { class: "nav-group" },
        h("div", { class: "nav-group-title" }, g.title),
        h("nav", { class: "nav-items" }, g.items)));
    });

    var side = h("aside", { class: "sidebar no-print" },
      h("a", { class: "brand", href: "#/" }, h("span", { class: "logo" }, logoMark()), "Изолят"),
      h("div", { class: "sidebar-nav" }, nav),
      // Пользователь и выход прижаты к низу панели: это не навигация,
      // а служебная зона, и она не должна конкурировать с разделами.
      h("div", { class: "sidebar-foot" },
        state.user ? h("div", { class: "who", title: ROLE_LABEL[role()] || "" },
          h("div", { class: "who-name" }, state.user.full_name || state.user.email),
          h("div", { class: "who-sub" },
            ROLE_LABEL[role()] || "",
            state.user.school_name ? " · " + state.user.school_name : "")) : null,
        h("div", { class: "sidebar-actions" },
          h("button", { class: "btn btn-sm", onClick: accountModal }, "Аккаунт"),
          h("button", { class: "btn btn-sm", onClick: logout }, "Выйти"),
          themeButton())));

    frag.appendChild(h("div", { class: "app-shell" },
      side,
      h("div", { class: "app-main" },
        h("main", { class: "page" }, content),
        // Правовые документы должны быть доступны с любого экрана, а не
        // только со страницы входа: школа обязана показать их родителю по
        // первому запросу.
        h("footer", { class: "sitefoot no-print" },
          h("span", {}, "Изолят"),
          h("a", { href: "/privacy.html", target: "_blank", rel: "noopener" }, "Политика обработки данных"),
          h("a", { href: "/terms.html", target: "_blank", rel: "noopener" }, "Условия использования")))));
    return frag;
  }

  // Значок непрочитанных оповещений обновляем в фоне: он должен быть виден на
  // любом экране, иначе смысл серверных алертов теряется.
  function refreshUnseen() {
    if (!canCasework()) return Promise.resolve();
    return API.get("/api/alerts/count")
      .then(function (d) { state.unseen = d.unseen || 0; })
      .catch(function () {});
  }
  function logout() {
    // Сначала гасим токен на сервере (инкремент token_version), только потом
    // чистим локально: иначе токен из этого браузера оставался бы валидным ещё
    // 7 дней — а это школьный компьютер, за которым психолог не один.
    // Если запрос не прошёл, из интерфейса всё равно выходим.
    function done() {
      localStorage.removeItem("izolyat.token");
      state.user = null; dash.classes = null; dash.classId = null; dash.surveyId = null;
      dash.analysis = null; dash.cache = {}; dash.loaded = false;
      stopNetwork(); go("/");
    }
    if (localStorage.getItem("izolyat.token")) API.post("/api/auth/logout").then(done, done);
    else done();
  }

  /* ============================================================== LOGIN */
  // Первый шаг для новой школы: завести саму школу и получить код приглашения.
  // Тот, кто регистрируется по нему первым, становится администратором и ведёт
  // свои классы как обычный психолог.
  function schoolModal(onDone) {
    var nameIn = h("input", { class: "input", placeholder: "Например: НИШ ЕМН г. Уральск" });
    var cityIn = h("input", { class: "input", placeholder: "Город" });
    var msg = h("div");
    var close;
    function save() {
      if (nameIn.value.trim().length < 2) { msg.replaceChildren(alertBox("error", "Укажите название школы")); return; }
      return API.post("/api/auth/schools", { name: nameIn.value.trim(), city: cityIn.value.trim() })
        .then(function (d) { close(); onDone(d.school); })
        .catch(function (e) { msg.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Регистрация школы",
      [h("p", { class: "muted tiny", style: { marginBottom: "10px" } },
        "Школа получит код приглашения. По нему регистрируются психологи и завуч. "
        + "Без кода доступ к данным учеников получить нельзя."),
       msg, field("Название школы", nameIn), field("Город", cityIn)],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
       asyncBtn({ class: "btn btn-primary", onClick: save }, "Создать школу")]);
  }

  function renderLogin() {
    stopNetwork();
    var mode = "in";
    var emailIn = h("input", { class: "input", type: "email", placeholder: "you@example.com" });
    var passIn = h("input", { class: "input", type: "password", placeholder: "минимум 8 символов" });
    var nameIn = h("input", { class: "input", placeholder: "Как к вам обращаться" });
    var nameField = field("Имя", nameIn);
    // Код приглашения выдаёт школа. Регистрация открывает доступ к персональным
    // данным несовершеннолетних, поэтому свободной она быть не может.
    var inviteIn = h("input", { class: "input", placeholder: "Код от вашей школы" });
    var inviteField = field("Код приглашения", inviteIn);
    var msg = h("div");
    var submit = h("button", { class: "btn btn-primary btn-lg", type: "submit", style: { width: "100%" } }, "Войти");
    var toggle = h("a", { href: "#" });
    var schoolLink = h("a", { href: "#" }, "Зарегистрировать школу");

    function setMode(m) {
      mode = m;
      nameField.style.display = m === "up" ? "" : "none";
      inviteField.style.display = m === "up" ? "" : "none";
      submit.textContent = m === "in" ? "Войти" : "Создать аккаунт";
      toggle.textContent = m === "in" ? "Зарегистрироваться" : "Войти";
      schoolLink.style.display = m === "up" ? "" : "none";
      msg.replaceChildren();
    }
    toggle.addEventListener("click", function (e) { e.preventDefault(); setMode(mode === "in" ? "up" : "in"); });
    schoolLink.addEventListener("click", function (e) {
      e.preventDefault();
      schoolModal(function (school) {
        inviteIn.value = school.invite_code;
        msg.replaceChildren(alertBox("info",
          "Школа «" + school.name + "» создана. Код приглашения: " + school.invite_code
          + ". Сохраните его: по нему регистрируются остальные сотрудники."));
      });
    });

    var form = h("form", { class: "stack" },
      nameField, field("E-mail", emailIn), field("Пароль", passIn), inviteField, msg, submit,
      h("div", { class: "tiny muted", style: { textAlign: "center" } }, h("span", {}, "Нет аккаунта? "), toggle),
      h("div", { class: "tiny muted", style: { textAlign: "center" } }, schoolLink));
    form.addEventListener("submit", function (e) {
      e.preventDefault(); msg.replaceChildren(); submit.disabled = true;
      var email = emailIn.value.trim(), password = passIn.value;
      if (mode === "up" && password.length < 8) {
        msg.replaceChildren(alertBox("error", "Пароль — минимум 8 символов"));
        submit.disabled = false;
        return;
      }
      var p = mode === "in" ? API.post("/api/auth/login", { email: email, password: password })
        : API.post("/api/auth/register", { email: email, password: password, full_name: nameIn.value.trim(), invite_code: inviteIn.value.trim() });
      p.then(function (d) {
        localStorage.setItem("izolyat.token", d.token);
        state.user = d.user; state.features = d.features || {}; dash.classes = null; dash.loaded = false;
        return refreshUnseen().then(function () { go("/"); });
      })
        .catch(function (err) { msg.replaceChildren(alertBox("error", err.message)); submit.disabled = false; });
    });
    setMode("in");
    // Подпись под названием говорит, что это за программа и для кого, без
    // обещаний и общих слов: её читает школьный психолог, а не покупатель.
    // Две панели: слева — что это за программа и на чём держится, справа —
    // форма. Одинокая карточка посреди пустого экрана не объясняла ничего,
    // а этот экран открывают и те, кто видит «Изолят» впервые.
    mount(h("div", { class: "auth" },
      h("div", { class: "auth-side" },
        h("div", { class: "auth-brand" },
          h("span", { class: "logo" }, logoMark()),
          h("span", {}, "Изолят")),
        h("h1", { class: "auth-claim" }, "Видно, кто в классе остался один"),
        h("p", { class: "auth-lead" },
          "Ученики отвечают на три вопроса за полторы минуты. "
          + "Система строит граф связей класса и сама предупреждает, "
          + "если у ребёнка падают входящие выборы."),
        h("ul", { class: "auth-points" },
          h("li", {}, "Кто назвал ребёнка одиноким — психологу не показывается"),
          h("li", {}, "Статус «изолят» не ставится при явке ниже 70%"),
          h("li", {}, "Каждое открытие карточки пишется в журнал доступа")),
        h("div", { class: "auth-foot" },
          h("a", { href: "/privacy.html" }, "Политика обработки данных"),
          h("a", { href: "/terms.html" }, "Условия использования"))),
      h("div", { class: "auth-panel" },
        h("div", { class: "auth-form" },
          // Дублируем бренд: на узких экранах левая панель скрыта, и без
          // этого пользователь видел бы форму без названия программы.
          h("div", { class: "auth-brand auth-brand-sm" },
            h("span", { class: "logo" }, logoMark()),
            h("span", {}, "Изолят")),
          h("h2", {}, "Вход в кабинет"),
          h("p", { class: "muted tiny auth-sub" },
            "Аккаунт выдаёт школа по коду приглашения"),
          form))));
  }

  /* ========================================================== DASHBOARD */
  function setClass(cid) {
    if (dash.classId !== cid) { dash.surveyId = null; dash.analysis = null; dash.filters.community = ""; }
    dash.classId = cid;
    renderDashboard();
  }
  function setSurvey(sid) {
    dash.surveyId = sid; dash.analysis = null; dash.filters.community = "";
    dash.keepCache = true;  // переключение среза ничего не меняет — кэш валиден
    renderDashboard();
  }

  // Аналитика конкретного среза при неизменных данных всегда одна и та же.
  function loadAnalysis(surveyId) {
    if (dash.cache[surveyId]) return Promise.resolve(dash.cache[surveyId]);
    return API.get("/api/surveys/" + surveyId + "/analytics").then(function (d) {
      dash.cache[surveyId] = d;
      return d;
    });
  }

  function renderDashboard() {
    stopNetwork();
    // Любой путь, кроме переключения среза (создание/удаление/правка, смена
    // класса, первая загрузка), мог изменить данные — кэш сбрасываем.
    if (!dash.keepCache) dash.cache = {};
    dash.keepCache = false;
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
        dash.consent = data.consent;
        if (!dash.surveyId || !dash.surveys.some(function (s) { return s.id === dash.surveyId; }))
          dash.surveyId = dash.surveys.length ? dash.surveys[dash.surveys.length - 1].id : null;
        if (dash.surveyId) return loadAnalysis(dash.surveyId);
        return null;
      })
      .then(function (analysis) {
        dash.analysis = analysis;
        // Подтягиваем предыдущий срез, чтобы показать резкое падение связей.
        var idx = dash.surveys.findIndex(function (s) { return s.id === dash.surveyId; });
        if (analysis && idx > 0) {
          return loadAnalysis(dash.surveys[idx - 1].id)
            .then(function (prev) { dash.prevAnalysis = prev; })
            .catch(function () { dash.prevAnalysis = null; });
        }
        dash.prevAnalysis = null;
      })
      .then(function () {
        dash.loaded = true;
        mount(shell(dashView()));
        buildNetwork();
      })
      .catch(function (err) { if (err === "stop") return; dash.loaded = true; mount(shell(alertBox("error", err.message || String(err)))); });
  }

  function dashEmpty() {
    return h("div", {}, dashHeader(),
      h("div", { class: "card card-pad" }, emptyState("Ещё нет ни одного класса",
        "Создайте класс, добавьте учеников, затем срез. Ученики пройдут опрос по коду, и граф построится автоматически. Для демо: python -m app.seed",
        h("button", { class: "btn btn-primary", onClick: function () { classModal(null); } }, "Создать класс"))));
  }

  function dashHeader() {
    var sel = h("select", { class: "select", style: { width: "auto", minWidth: "200px" },
      onChange: function (e) { go("/class/" + e.target.value); } });
    (dash.classes || []).forEach(function (c) { sel.appendChild(h("option", { value: c.id }, c.name)); });
    if (dash.classId) sel.value = String(dash.classId);
    var controls = [sel];
    if (dash.classId) {
      controls.push(h("button", { class: "btn btn-sm", onClick: function () { classModal(dash.cls); } }, "Настройки класса"));
      controls.push(h("button", { class: "btn btn-sm", onClick: manageStudentsModal }, "Ученики"));
      controls.push(h("button", { class: "btn btn-sm", onClick: function () { preventionModal(dash.classId); } }, "Профилактика"));
    }
    controls.push(h("button", { class: "btn btn-sm btn-primary", onClick: function () { classModal(null); } }, "+ Класс"));
    return h("div", { class: "mb-5" },
      h("div", { class: "breadcrumb" }, h("a", { href: "#/" }, "Мои классы"), h("span", {}, "/"),
        h("span", {}, dash.cls ? dash.cls.name : "Класс")),
      h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } }, controls));
  }

  // Ученики без отметки о согласии не участвуют в срезах — психолог должен
  // увидеть это до того, как удивится неполной явке.
  function consentBanner() {
    var missing = (dash.consent && dash.consent.missing) || [];
    if (!missing.length) return null;
    return h("div", { class: "mb-5" }, alertBox("info",
      h("span", {}, "Не участвуют в срезах, нет отметки о согласии на обработку данных: ",
        h("b", {}, missing.map(function (m) { return m.full_name; }).join(", ")), ". ",
        h("a", { href: "#", onClick: function (e) { e.preventDefault(); manageStudentsModal(); } }, "Отметить согласие"))));
  }

  function currentSurvey() { return dash.surveys.filter(function (s) { return s.id === dash.surveyId; })[0] || null; }

  function dashView() {
    var sv = currentSurvey();
    return h("div", {}, dashHeader(), consentBanner(), srezPanel(sv), reliabilityBanner(), dropBanner(), radarCard(),
      h("div", { class: "dash-grid" }, graphCard(sv), h("div", { class: "stack" }, metricsCard(), rosterCard())));
  }

  // Явка ниже порога означает, что «нет входящих выборов» может быть следствием
  // неявки друзей, а не изоляции. Психолог должен видеть это до того, как
  // сделает вывод о ребёнке, — поэтому баннер стоит над графом и метриками.
  function reliabilityBanner() {
    var a = dash.analysis;
    if (!a || a.graph_metrics.reliability !== "low") return null;
    var m = a.graph_metrics;
    if (!m.responded) return null;  // «совсем нет ответов» подсвечивается на самом графе
    var pct = Math.round((m.participation || 0) * 100);
    return h("div", { class: "mb-5" }, alertBox("info",
      "Опрос прошли " + m.responded + " из " + m.students + " (" + pct + "%). Пока ответило меньше 70% класса, "
      + "статус «изолят» не ставится, индекс не считается, а оповещения о падении связей отключены: "
      + "по такой явке нельзя отличить изоляцию от того, что ученика просто некому было выбрать."));
  }

  // Явный алерт о резком падении входящих связей ученика по сравнению с
  // предыдущим срезом. Дополняет (не заменяет) подсветку на графе.
  function dropBanner() {
    var a = dash.analysis, prev = dash.prevAnalysis;
    if (!a || !prev) return null;
    // Сравнивать срезы с разной (и низкой) явкой бессмысленно: «падение связей»
    // тогда означает лишь то, что во втором срезе ответило меньше детей. Такой
    // алерт отправил бы психолога работать с ребёнком без проблемы.
    if (a.graph_metrics.reliability === "low" || prev.graph_metrics.reliability === "low") return null;
    var perNow = a.per_student, perPrev = prev.per_student;
    var drops = [];
    dash.students.forEach(function (s) {
      var mNow = perNow[String(s.id)], mPrev = perPrev[String(s.id)];
      if (!mNow || !mPrev) return;
      // Ученик, не прошедший один из срезов, мог «потерять» исходящие связи
      // просто из-за неявки — падение входящих у него не интерпретируем.
      if (mNow.status === "unknown" || mPrev.status === "unknown") return;
      var x = mPrev.in_degree, y = mNow.in_degree;
      var sharp = (x - y >= 2) || (x >= 2 && y <= x / 2); // на 2+ или вдвое
      if (y < x && sharp) drops.push({ name: s.full_name, id: s.id, from: x, to: y });
    });
    if (!drops.length) return null;
    drops.sort(function (p, q) { return (p.to - p.from) - (q.to - q.from); }); // сильнее падение — выше
    var items = drops.map(function (d) {
      return h("div", { class: "dp-item" },
        null,
        h("span", { style: { flex: "1" } }, h("b", {}, d.name), " — упало с " + d.from + " до " + d.to + " входящих связей с прошлого среза"),
        h("button", { class: "btn btn-sm", onClick: function () { go("/student/" + d.id); } }, "Карточка"));
    });
    return h("div", { class: "dropbar" }, h("div", { class: "card-pad" },
      h("div", { style: { fontWeight: "700", marginBottom: "8px", color: "var(--red)" } },
        "Резкое падение связей: " + drops.length + " — относительно среза «" + prev.survey.title + "»"),
      items));
  }

  function srezPanel(sv) {
    var controls = [];
    controls.push(h("button", { class: "btn btn-sm", disabled: dash.students.length < 2, title: dash.students.length < 2 ? "Добавьте минимум двух учеников" : "", onClick: surveyModal }, "+ Срез"));
    if (sv) controls.push(h("button", { class: "btn btn-sm btn-primary", onClick: function () { codesModal(sv); } }, "Ссылка и коды"));
    if (dash.surveys.length >= 2) controls.push(h("button", { class: "btn btn-sm", onClick: compareModal }, "Сравнить срезы"));

    var inner = [h("div", { style: { display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" } },
      h("div", { class: "section-title", style: { margin: 0, flex: 1 } }, "Срез (социометрический снимок)"), controls)];

    if (dash.surveys.length === 0) {
      inner.push(h("p", { class: "muted", style: { marginTop: "8px" } }, "Пока нет ни одного среза. Создайте срез, чтобы ученики прошли опрос."));
    } else {
      var idx = Math.max(0, dash.surveys.findIndex(function (s) { return s.id === dash.surveyId; }));
      var slider = h("input", { class: "slider", type: "range", min: "0", max: String(dash.surveys.length - 1), value: String(idx),
        // change, а не input: перерисовка идёт по отпусканию ползунка, а не на
        // каждый промежуточный срез при перетаскивании.
        onchange: function (e) { var s = dash.surveys[Number(e.target.value)]; if (s) setSurvey(s.id); } });
      var ticks = h("div", { class: "slider-ticks" }, dash.surveys.map(function (s) { return h("span", {}, fmtShort(s.conducted_on)); }));
      var responded = dash.analysis ? (dash.analysis.responded_ids || []).length : 0;
      var total = dash.students.length;
      var pct = total ? Math.round(responded / total * 100) : 0;
      // Закрытие среза — момент, когда сервер считает итог и создаёт
      // оповещения. Психолог должен сразу увидеть, что они появились.
      var openBtn = sv ? h("button", { class: "btn btn-sm " + (sv.is_open ? "" : "btn-primary"),
        onClick: function () {
          if (sv.is_open && !confirm("Закрыть опрос «" + sv.title + "»?\n\nРезультат будет зафиксирован, и система проверит, у кого ухудшились связи."))
            return;
          API.put("/api/surveys/" + sv.id, { is_open: !sv.is_open }).then(function (d) {
            dash.cache = {};
            return refreshUnseen().then(function () {
              renderDashboard();
              if (d.alerts_created) {
                setTimeout(function () {
                  if (confirm("Срез закрыт. Новых оповещений: " + d.alerts_created + ".\n\nОткрыть «Входящие»?"))
                    go("/alerts");
                }, 80);
              }
            });
          });
        } },
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
    return h("div", { class: "card card-pad mb-5" }, inner);
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
        communitySelect(a),
        h("span", { style: { flex: "1", minWidth: "8px" } }),
        // Анонимный режим для показа на экране/проекторе: скрывает имена учеников.
        checkbox("Скрыть имена", dash.filters.anon, function (v) {
          dash.filters.anon = v; mount(shell(dashView())); buildNetwork();
        }));
      body = h("div", {},
        toolbar,
        h("div", { id: "net", class: "net" }),
        graphLegend(a),
        (a.responded_ids || []).length === 0 ? h("div", { style: { marginTop: "12px" } },
          alertBox("info", "Ученики ещё не прошли опрос, связей нет. Откройте опрос и раздайте коды.")) : null);
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
    items.push(h("span", { class: "item" }, h("span", { class: "swatch", style: { background: GRAPH.isolateFill, border: "2px solid " + GRAPH.isolateBorder } }), "Изолят"));
    if (a.graph_metrics && a.graph_metrics.unknown)
      items.push(h("span", { class: "item", title: "Нет входящих выборов, но ответило меньше 70% класса" },
        h("span", { class: "swatch", style: { background: GRAPH.unknownFill, border: "2px solid " + GRAPH.unknownBorder } }), "Нет данных"));
    items.push(h("span", { class: "item" }, h("span", { class: "line", style: { borderTopColor: GRAPH.mutual } }), "Взаимный выбор"));
    items.push(h("span", { class: "item" }, h("span", { class: "line", style: { borderTopColor: GRAPH.bridge, borderTopStyle: "dashed" } }), "Мост"));
    return h("div", { class: "legend" }, items);
  }

  function metricsCard() {
    var a = dash.analysis;
    var body;
    if (!a) body = emptyState("Нет данных", "Выберите срез.");
    else {
      var m = a.graph_metrics;
      // При низкой явке сервер не считает индекс: такое число говорило бы о
      // том, сколько детей не прошли опрос, а не о том, что с классом.
      var wi = m.wellbeing_index;
      var wiLabel = wi == null ? "недостаточно ответов"
        : wi >= 70 ? "высокий уровень" : wi >= 45 ? "средний уровень" : "низкий уровень";
      // Колонка рядом с графом узкая, поэтому показатели идут в два уровня:
      // индекс во всю ширину, под ним четыре плитки в две колонки, а
      // второстепенные величины — строками «ключ-значение», а не россыпью
      // одинаковых пилюль, в которой глазу не за что зацепиться.
      body = h("div", {},
        h("div", { class: "metric-hero" },
          h("div", { class: "tile-label", title: WI_HINT }, "Индекс связности класса"),
          h("div", { class: "metric-hero-value" }, wi == null ? "—" : String(wi)),
          h("div", { class: "tile-sub", title: WI_HINT },
            wiLabel + (wi == null ? "" : " · шкала 0–100 · экспериментальный"))),
        h("div", { class: "tiles metric-tiles" },
          tile("Учеников", m.students, "прошли: " + m.responded),
          tile("Изоляты", m.isolates, m.unknown ? "ещё " + m.unknown + " без данных" : "нет входящих"),
          tile("Взаимные пары", m.mutual_pairs, "взаимность " + num(m.reciprocity * 100) + "%"),
          tile("Плотность", num(m.density, 2), "среди ответивших")),
        h("div", { class: "metric-rows" },
          metricRow("Сплочённость", num(m.cohesion, 2)),
          metricRow("Компоненты", m.components),
          metricRow("Сообщества", m.communities),
          metricRow("Мосты", m.bridges),
          metricRow("Связей", m.positive_edges)));
    }
    return h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Показатели класса")), h("div", { class: "card-pad" }, body));
  }

  function metricRow(label, value) {
    return h("div", { class: "metric-row" },
      h("span", { class: "mr-label" }, label),
      h("span", { class: "mr-dots" }),
      h("span", { class: "mr-value" }, String(value)));
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
      // Список людей, а не таблица чисел. Раньше здесь было шесть числовых
      // колонок с урезанными заголовками («Вх», «Исх», «Вз», «Один»), которые
      // в узкой колонке рядом с графом читались как ведомость. Теперь строка
      // устроена по важности: имя, статус, и справа — входящие выборы,
      // главный показатель этого экрана. Остальные метрики остаются в
      // подписи и в карточке ученика.
      var items = sorted.map(function (s) {
        var m = per[String(s.id)];
        var detail = [];
        if (m) {
          detail.push("исходящих: " + m.out_degree);
          detail.push("взаимных: " + m.mutual);
          // aloneText возвращает 0 (число) при отсутствии номинаций и "<3",
          // когда их меньше порога раскрытия, — в подписи ни то ни другое
          // показывать не нужно.
          if (m.alone_votes) detail.push("«часто один»: " + aloneText(m.alone_votes, m.alone_reportable));
        }
        var isIsolate = m && m.status === "isolate";
        return h("div", {
          class: "stu" + (isIsolate ? " is-isolate" : ""),
          onClick: function () { go("/student/" + s.id); },
        },
          h("div", { class: "stu-main" },
            h("div", { class: "stu-name" },
              dispName(s.id, s.full_name),
              m && !m.responded
                ? h("span", { class: "stu-flag", title: "Не прошёл(-ла) этот срез" }, "не ответил")
                : null),
            detail.length ? h("div", { class: "stu-sub" }, detail.join(" · ")) : null),
          h("div", { class: "stu-status" },
            m ? (m.status === "connected" ? communityPill(m.community) : statusPill(m.status)) : null),
          h("div", { class: "stu-in", title: "Входящие выборы: сколько одноклассников назвали" },
            h("span", { class: "stu-in-num" }, m ? String(m.in_degree) : "0"),
            h("span", { class: "stu-in-cap" }, "вх")));
      });
      body = h("div", { class: "stulist" }, items);
    }
    return h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h3", {}, "Ученики"),
        dash.students.length ? h("span", { class: "count-chip" }, String(dash.students.length)) : null,
        h("span", { class: "spacer" }),
        dash.analysis ? h("button", { class: "btn btn-sm", onClick: exportXlsx }, "Excel") : null,
        dash.analysis ? h("button", { class: "btn btn-sm", onClick: reportModal }, "Отчёт") : null),
      body);
  }

  /* ------------------------------------------------------ vis-network */
  function computeVisible(a) {
    var s = new Set();
    a.nodes.forEach(function (n) { if (dash.filters.community === "" || String(n.group) === String(dash.filters.community)) s.add(n.id); });
    return s;
  }
  // Анонимный режим: стабильно заменяем имена на «Ученик N» (нумерация по id),
  // чтобы граф и таблицу можно было показывать публично (на сцене), не
  // раскрывая личности детей. Карта перестраивается при смене класса/состава.
  function anonName(id) {
    if (dash.anonMapFor !== dash.classId || !dash.anonMap ||
        Object.keys(dash.anonMap).length !== dash.students.length) {
      var m = {};
      dash.students.slice().sort(function (a, b) { return (a.id || 0) - (b.id || 0); })
        .forEach(function (s, i) { m[s.id] = "Ученик " + (i + 1); });
      dash.anonMap = m; dash.anonMapFor = dash.classId;
    }
    return dash.anonMap[id] || "Ученик";
  }
  function dispName(id, real) { return dash.filters.anon ? anonName(id) : real; }

  function nodeStyle(n) {
    var base = PALETTE[n.group % PALETTE.length];
    var color = { background: base, border: base, highlight: { background: base, border: GRAPH.label } };
    var bw = 2;
    if (dash.filters.isolate && n.isolate) {
      color = {
        background: GRAPH.isolateFill, border: GRAPH.isolateBorder,
        highlight: { background: GRAPH.isolateFill, border: GRAPH.isolateBorder },
      };
      bw = 3;
    } else if (n.status === "unknown") {
      // «Нет данных» — нейтральный серый узел: без входящих выборов, но и без
      // достаточной явки, чтобы называть это изоляцией. Красным не красим.
      color = {
        background: GRAPH.unknownFill, border: GRAPH.unknownBorder,
        highlight: { background: GRAPH.unknownFill, border: GRAPH.unknownBorder },
      };
      bw = 2;
    }
    var hidden = dash.filters.community !== "" && String(n.group) !== String(dash.filters.community);
    var label = n.label, title = n.title;
    if (dash.filters.anon) {
      label = anonName(n.id);
      var nl = String(n.title || "").indexOf("\n");   // первая строка title — имя; заменяем, метрики оставляем
      title = label + (nl >= 0 ? String(n.title).slice(nl) : "");
    }
    return { id: n.id, label: label, title: title, size: n.size, color: color, borderWidth: bw, hidden: hidden };
  }
  function edgeStyle(e, visible) {
    var color = GRAPH.edge, width = 1, dashes = false;
    if (dash.filters.mutual && e.mutual) { color = GRAPH.mutual; width = 2.5; }
    if (dash.filters.bridge && e.bridge) { color = GRAPH.bridge; width = 2.5; dashes = [6, 4]; }
    var hidden = dash.filters.community !== "" && (!visible.has(e.from) || !visible.has(e.to));
    return { id: e.id, from: e.from, to: e.to, color: { color: color, highlight: GRAPH.mutual }, width: width, dashes: dashes, hidden: hidden };
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
      // Подпись узла рисуется поверх холста и может попасть на ребро, поэтому
      // ей даётся обводка цветом фона: без неё имена читаются через раз.
      // На тёмной теме обводка тёмная — светлая давала бы ореол вокруг букв.
      nodes: {
        shape: "dot",
        font: { size: 14, color: GRAPH.label, strokeWidth: 3, strokeColor: "#08080A" },
      },
      edges: { arrows: { to: { enabled: true, scaleFactor: 0.6 } }, smooth: { type: "continuous" } },
      physics: { stabilization: { iterations: 150 }, barnesHut: { gravitationalConstant: -9000, springLength: 110, springConstant: 0.035, damping: 0.28 } },
      interaction: { hover: true, tooltipDelay: 120, zoomView: true, dragNodes: true, dragView: true },
    };
    dash.network = new vis.Network(container, { nodes: dash.nodesDS, edges: dash.edgesDS }, options);
    dash.network.on("click", function (params) { if (params.nodes && params.nodes.length) go("/student/" + params.nodes[0]); });
    // Граф проявляется, когда раскладка уже сошлась: пока идёт стабилизация,
    // узлы прыгают, и показывать это незачем. Плавность уважает системную
    // настройку «уменьшить движение» — при ней холст виден сразу.
    var calm = false;
    try { calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}
    if (!calm) {
      container.style.opacity = "0";
      container.style.transition = "opacity 0.55s cubic-bezier(0.22, 1, 0.36, 1)";
    }
    function reveal() { container.style.opacity = "1"; }
    // Вписываем весь граф в контейнер после раскладки — чтобы на маленьких
    // экранах он корректно уменьшался и был виден целиком.
    dash.network.once("stabilizationIterationsDone", function () {
      try { dash.network.fit({ animation: false }); } catch (e) {}
      reveal();
    });
    // Страховка: если событие стабилизации не придёт, холст не должен
    // остаться невидимым.
    setTimeout(reveal, 1200);
    // Резервный fit на случай, если событие стабилизации не сработает
    // (мало узлов / отключённая физика) — граф всё равно впишется в экран.
    setTimeout(function () { try { if (dash.network) dash.network.fit({ animation: false }); } catch (e) {} }, 500);
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
      var name = nameIn.value.trim();
      if (!name) { err.replaceChildren(alertBox("error", "Укажите название класса")); return; }
      var body = { name: name, description: descIn.value.trim() };
      return (cls ? API.put("/api/classes/" + cls.id, body) : API.post("/api/classes", body))
        .then(function (d) { dash.classes = null; if (!cls) dash.classId = d.class.id; close(); renderDashboard(); })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }
    function remove() {
      if (!confirm("Удалить класс со всеми учениками, срезами и ответами?")) return;
      API.del("/api/classes/" + cls.id).then(function () { dash.classes = null; dash.classId = null; dash.surveyId = null; close(); renderDashboard(); });
    }
    // Срок хранения сырых ответов. Показываем его явно: психолог должен знать,
    // что данные детей не лежат в системе вечно, и уметь сократить срок.
    var retentionBlock = null;
    if (cls) {
      var retIn = h("input", { class: "input", type: "date", value: cls.retention_until || "" });
      var retMsg = h("div");
      var retBtn = h("button", { class: "btn btn-sm", onClick: function () {
        API.put("/api/classes/" + cls.id + "/settings", { retention_until: retIn.value })
          .then(function (d) { cls.retention_until = d.class.retention_until; retMsg.replaceChildren(alertBox("ok", "Срок хранения сохранён")); })
          .catch(function (e) { retMsg.replaceChildren(alertBox("error", e.message)); });
      } }, "Сохранить срок");
      retentionBlock = h("div", { style: { marginTop: "6px" } },
        h("div", { class: "section-title" }, "Хранение данных"),
        h("p", { class: "muted tiny", style: { marginBottom: "8px" } },
          "После этой даты сырые ответы учеников удаляются, а посчитанные показатели остаются: "
          + "графики динамики продолжат работать, восстановить по ним отдельные ответы будет нельзя. "
          + "Срок можно только сократить. Продлить дальше политики школы нельзя."),
        h("div", { class: "row" }, retIn, retBtn), retMsg);
    }

    close = openModal(cls ? "Класс" : "Новый класс",
      [err, field("Название", nameIn), field("Описание", descIn), retentionBlock],
      [cls ? h("button", { class: "btn btn-danger", onClick: remove }, "Удалить") : null, h("div", { style: { flex: "1" } }),
       h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
       asyncBtn({ class: "btn btn-primary", onClick: save }, "Сохранить")]);
  }

  function studentModal(student, onSaved) {
    var nameIn = h("input", { class: "input", value: student ? student.full_name : "" });
    var genderIn = h("select", { class: "select" }, h("option", { value: "" }, "—"), h("option", { value: "m" }, "Мужской"), h("option", { value: "f" }, "Женский"));
    genderIn.value = student && student.gender ? student.gender : "";
    var birthIn = h("input", { class: "input", type: "date", value: student && student.birth_date ? student.birth_date : "" });
    var noteIn = h("textarea", { class: "textarea", value: student && student.note ? student.note : "" });
    var err = h("div"); var close;
    function save() {
      var full = nameIn.value.trim();
      if (!full) { err.replaceChildren(alertBox("error", "Укажите имя и фамилию")); return; }
      var body = { full_name: full, gender: genderIn.value, birth_date: birthIn.value, note: noteIn.value.trim() };
      return (student ? API.put("/api/students/" + student.id, body) : API.post("/api/classes/" + dash.classId + "/students", body))
        .then(function () { close(); if (onSaved) onSaved(); })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal(student ? "Ученик" : "Новый ученик",
      [err, field("Имя и фамилия", nameIn), h("div", { class: "row" }, field("Пол", genderIn), field("Дата рождения", birthIn)), field("Заметка", noteIn)],
      [h("div", { style: { flex: "1" } }), h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"), asyncBtn({ class: "btn btn-primary", onClick: save }, "Сохранить")]);
  }

  function activeConsent(s) {
    return (s.consents || []).filter(function (c) { return !c.revoked_on; })[0] || null;
  }

  function manageStudentsModal() {
    var listWrap = h("div");
    var summary = h("div");
    function reload() {
      API.get("/api/classes/" + dash.classId).then(function (d) {
        dash.students = d.students;
        dash.consent = d.consent;
        render();
      });
    }
    function render() {
      var missing = (dash.consent && dash.consent.missing) || [];
      summary.replaceChildren(missing.length
        ? alertBox("info", "Без согласия на обработку данных: " + missing.length + " из "
            + (dash.consent.total || 0) + ". Эти ученики не участвуют в срезах и не видны одноклассникам в списке выбора.")
        : (dash.students.length
            ? alertBox("info", "Согласия оформлены у всех учеников класса.")
            : h("span")));

      if (dash.students.length === 0) {
        listWrap.replaceChildren(emptyState("Список пуст", "Добавьте первого ученика."));
        return;
      }
      var rows = dash.students.map(function (s) {
        var c = activeConsent(s);
        var consentCell = c
          ? h("span", { class: "pill badge-green", title: (c.document_ref || "") + " · с " + fmtDate(c.obtained_on) }, "Есть")
          : h("button", { class: "btn btn-sm btn-primary", onClick: function () { consentModal(s, reload); } }, "Отметить");
        return h("tr", { style: s.is_active ? null : { opacity: "0.55" } },
          h("td", {}, s.full_name, s.is_active ? null : h("span", { class: "muted tiny" }, " · выбыл")),
          h("td", {}, consentCell),
          h("td", { class: "num" },
            c ? h("button", {
              class: "btn btn-ghost btn-sm", title: "Отозвать согласие",
              onClick: function () {
                if (confirm("Отозвать согласие для «" + s.full_name + "»?\nОн перестанет участвовать в новых срезах."))
                  API.del("/api/consents/" + c.id).then(reload);
              },
            }, "Отозвать") : null,
            h("button", { class: "btn btn-ghost btn-sm", title: "Изменить", onClick: function () { studentModal(s, reload); } }, "Изменить"),
            // Выбывший ученик архивируется, а не удаляется: удаление снесло бы
            // и его историю в прошлых срезах, и метрики класса за те периоды.
            h("button", {
              class: "btn btn-ghost btn-sm",
              title: s.is_active ? "Выбыл из класса (останется в истории срезов)" : "Вернуть в класс",
              onClick: function () {
                API.put("/api/students/" + s.id, {
                  full_name: s.full_name, gender: s.gender,
                  birth_date: s.birth_date, note: s.note, is_active: !s.is_active,
                }).then(function () { dash.cache = {}; reload(); });
              },
            }, s.is_active ? "Выбыл" : "Вернуть"),
            h("button", { class: "btn btn-danger btn-sm", title: "Удалить безвозвратно вместе с историей", onClick: function () { if (confirm("Удалить «" + s.full_name + "» вместе со всей историей?\n\nЕсли ученик просто выбыл из класса — отметьте его как выбывшего, тогда история срезов сохранится.")) API.del("/api/students/" + s.id).then(function () { dash.cache = {}; reload(); }); } }, "Удалить")));
      });
      listWrap.replaceChildren(h("div", { class: "table-wrap" },
        h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", {}, "Согласие"), h("th", {}))),
          h("tbody", {}, rows))));
    }
    reload();
    var close = openModal("Ученики класса",
      [h("div", { style: { marginBottom: "10px", display: "flex", gap: "8px", flexWrap: "wrap" } },
        h("button", { class: "btn btn-primary btn-sm", onClick: function () { studentModal(null, reload); } }, "+ Добавить ученика"),
        h("button", { class: "btn btn-sm", onClick: function () { importStudentsModal(reload); } }, "Импорт из файла"),
        h("button", { class: "btn btn-sm", onClick: function () { bulkConsentModal(reload); } }, "Согласия пачкой")),
       summary, listWrap],
      [h("button", { class: "btn btn-primary", onClick: function () { close(); dash.cache = {}; renderDashboard(); } }, "Готово")], true);
  }

  // Бланки согласий приносят стопкой с родительского собрания. Отмечать их по
  // одному никто не станет — и срез в итоге запустили бы вообще без отметок.
  function bulkConsentModal(onDone) {
    var missing = (dash.consent && dash.consent.missing) || [];
    var today = new Date().toISOString().slice(0, 10);
    var dateIn = h("input", { class: "input", type: "date", value: today });
    var refIn = h("input", { class: "input", placeholder: "Например: журнал согласий, собрание 05.09" });
    var msg = h("div");
    var boxes = missing.map(function (m) {
      var cb = h("input", { type: "checkbox" });
      cb.checked = true;
      return { id: m.id, cb: cb, row: h("label", { class: "check" }, cb, m.full_name) };
    });
    var close;
    function save() {
      var ids = boxes.filter(function (b) { return b.cb.checked; }).map(function (b) { return b.id; });
      if (!ids.length) { msg.replaceChildren(alertBox("error", "Никто не выбран")); return; }
      return API.post("/api/classes/" + dash.classId + "/consents/bulk",
        { student_ids: ids, obtained_on: dateIn.value, document_ref: refIn.value.trim(), kind: "parent" })
        .then(function (d) { close(); onDone(); alert("Отмечено согласий: " + d.count); })
        .catch(function (e) { msg.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Согласия пачкой",
      missing.length
        ? [h("p", { class: "muted tiny", style: { marginBottom: "10px" } },
            "Отметьте, по кому получены письменные согласия родителей. Система хранит только факт "
            + "и ссылку на документ. Бумажные оригиналы остаются у вас."),
           msg, field("Дата получения", dateIn), field("Где подшиты оригиналы", refIn),
           h("div", { class: "section-title", style: { marginTop: "10px" } }, "Ученики без согласия"),
           h("div", { class: "stack", style: { gap: "2px" } }, boxes.map(function (b) { return b.row; }))]
        : [alertBox("ok", "Согласия оформлены у всех учеников класса.")],
      missing.length
        ? [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
           asyncBtn({ class: "btn btn-primary", onClick: save }, "Отметить")]
        : [h("button", { class: "btn btn-primary", onClick: function () { close(); } }, "Закрыть")], true);
  }

  // Согласие на обработку персональных данных. В базе лежат ФИО, дата
  // рождения и заметки психолога о состоянии несовершеннолетнего — без
  // основания обрабатывать это нельзя, поэтому без отметки ученик просто не
  // участвует в срезах.
  function consentModal(student, onDone) {
    var today = new Date().toISOString().slice(0, 10);
    var dateIn = h("input", { class: "input", type: "date", value: today });
    var refIn = h("input", { class: "input", placeholder: "Например: журнал согласий, стр. 12" });
    var msg = h("div");
    var close;
    function save() {
      return API.post("/api/students/" + student.id + "/consent",
        { kind: "parent", obtained_on: dateIn.value, document_ref: refIn.value.trim() })
        .then(function () { close(); onDone(); })
        .catch(function (e) { msg.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Согласие — " + student.full_name,
      [h("p", { class: "muted tiny", style: { marginBottom: "10px" } },
        "Отметьте, что письменное согласие родителя (законного представителя) получено. "
        + "Система хранит только факт и ссылку на документ. Сам бумажный оригинал остаётся у вас."),
       msg, field("Дата получения", dateIn), field("Где подшит оригинал", refIn)],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
       asyncBtn({ class: "btn btn-primary", onClick: save }, "Согласие получено")]);
  }

  function surveyModal() {
    var today = new Date().toISOString().slice(0, 10);
    var titleIn = h("input", { class: "input", placeholder: "Например, Осенний срез" });
    var dateIn = h("input", { class: "input", type: "date", value: today });
    var qInputs = DEFAULT_QUESTIONS.map(function (q) {
      return {
        key: q.key, hint: q.hint,
        input: h("input", { class: "input", value: q.text }),
        inputKk: h("input", { class: "input", value: q.text_kk }),
      };
    });
    var qFields = qInputs.map(function (q, i) {
      return h("div", { style: { marginBottom: "10px" } },
        field("Вопрос " + (i + 1) + " (" + q.hint + ")", q.input),
        field("Қазақша", q.inputKk));
    });
    var err = h("div"); var close;
    function save() {
      var title = titleIn.value.trim();
      if (!title) { err.replaceChildren(alertBox("error", "Укажите название среза")); return; }
      // Пустая формулировка вопроса на сервере заменится на текст по умолчанию,
      // но психолог должен об этом узнать до создания, а не после.
      var empty = qInputs.filter(function (q) { return !q.input.value.trim(); });
      if (empty.length) {
        err.replaceChildren(alertBox("error", "Заполните формулировки всех трёх вопросов"));
        return;
      }
      var questions = qInputs.map(function (q) {
        return { key: q.key, text: q.input.value.trim(), text_kk: q.inputKk.value.trim() };
      });
      return API.post("/api/classes/" + dash.classId + "/surveys", { title: title, conducted_on: dateIn.value, questions: questions })
        .then(function (d) {
          close();
          dash.surveyId = d.survey.id;
          dash.cache = {};
          renderDashboard();
          if (d.excluded && d.excluded.length) {
            alert("Срез создан. Не участвуют (нет отметки о согласии): "
              + d.excluded.map(function (e2) { return e2.full_name; }).join(", "));
          }
          setTimeout(function () { codesModal(d.survey); }, 60);
        })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Новый срез",
      [err, field("Название", titleIn), field("Дата проведения", dateIn),
       h("div", { class: "section-title", style: { marginTop: "6px" } }, "Вопросы (можно адаптировать под возраст класса)"),
       qFields,
       h("p", { class: "muted tiny" }, "Смысл вопросов фиксирован: два положительных и один на изоляцию. Меняется только формулировка. Ученик сам переключает язык на странице опроса. После создания откроется окно со ссылкой и QR-кодом.")],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"), asyncBtn({ class: "btn btn-primary", onClick: save }, "Создать")]);
  }

  // Коды раздаются на конкретный срез и в других срезах не работают. Если код
  // подсмотрели и ответили за ученика — психолог перевыпускает его здесь же,
  // не трогая остальных.
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
        h("button", { class: "btn", onClick: function () { linkIn.select(); try { document.execCommand("copy"); } catch (e) {} } }, "Копировать")),
      h("div", { class: "section-title", style: { marginTop: "10px" } }, "Коды на этот срез (для печати и раздачи)"),
      codesWrap,
    ];
    var close = openModal("Ссылка и QR — " + sv.title, body,
      [h("button", { class: "btn", onClick: function () { window.print(); } }, "Печать кодов"),
       h("div", { style: { flex: "1" } }), h("button", { class: "btn btn-primary", onClick: function () { close(); } }, "Закрыть")], true);

    if (typeof QRCode !== "undefined") { try { new QRCode(qrBox, { text: link, width: 190, height: 190, correctLevel: QRCode.CorrectLevel.M }); } catch (e) { qrBox.textContent = link; } }
    else qrBox.textContent = "QR-библиотека не загрузилась. Используйте ссылку выше.";

    function loadTickets() {
      API.get("/api/surveys/" + sv.id + "/tickets").then(function (d) {
        var grid = h("div", { class: "code-grid" }, d.tickets.map(function (t) {
          return h("div", { class: "code-card" + (t.done ? " done" : "") },
            h("div", { class: "nm" }, t.full_name),
            h("div", { class: "cd" }, t.code),
            t.done ? h("div", { class: "muted tiny no-print" }, "Прошёл") : null,
            h("button", {
              class: "btn btn-ghost btn-sm no-print",
              title: "Перевыпустить код: старый перестанет работать, ответы ученика по этому срезу будут удалены",
              onClick: function () {
                if (!confirm("Перевыпустить код для «" + t.full_name + "»?\n\nСтарый код перестанет работать, а его ответы по этому срезу будут удалены."))
                  return;
                API.post("/api/surveys/" + sv.id + "/students/" + t.student_id + "/reissue")
                  .then(function () { loadTickets(); dash.cache = {}; })
                  .catch(function (e) { alert(e.message); });
              },
            }, "Новый код"));
        }));

        var excluded = d.excluded.length
          ? h("div", { class: "alert alert-info no-print", style: { marginBottom: "10px" } },
              "Не участвуют (нет отметки о согласии на обработку данных): "
              + d.excluded.map(function (e) { return e.full_name; }).join(", ")
              + ". Отметьте согласие в разделе «Ученики» и нажмите «Обновить коды».")
          : null;

        codesWrap.replaceChildren(
          h("div", { class: "muted tiny no-print", style: { marginBottom: "8px" } },
            "Код действует только в этом срезе. Каждый ученик вводит свой код на странице опроса."),
          excluded,
          d.excluded.length ? h("button", {
            class: "btn btn-sm no-print", style: { marginBottom: "10px" },
            onClick: function () { API.post("/api/surveys/" + sv.id + "/tickets/refresh").then(loadTickets); },
          }, "Обновить коды") : null,
          grid);
      }).catch(function (e) { codesWrap.replaceChildren(alertBox("error", e.message)); });
    }
    loadTickets();
  }

  /* -------------------------------------------------- радар изоляции */
  function radarCard() {
    var a = dash.analysis; if (!a) return null;
    // Радар — это список «пойти и поработать с ребёнком». Поэтому он молчит на
    // недостоверном срезе и не поднимает тревогу по одной-двум номинациям:
    // порог тот же, что и в остальном интерфейсе (analytics.ALONE_MIN_REPORT).
    if (a.graph_metrics.reliability === "low") return null;
    var per = a.per_student;
    var risk = dash.students.filter(function (s) { var m = per[String(s.id)]; return m && (m.is_isolate || m.alone_reportable); });
    if (risk.length === 0) return null;
    risk.sort(function (x, y) {
      var mx = per[String(x.id)], my = per[String(y.id)];
      var sx = (mx.is_isolate ? 100 : 0) + (mx.alone_votes || 0), sy = (my.is_isolate ? 100 : 0) + (my.alone_votes || 0);
      return sy - sx;
    });
    var chips = risk.map(function (s) {
      var m = per[String(s.id)];
      var tag = (m.is_isolate ? " · изолят" : "") + (m.alone_reportable ? " · «один»×" + m.alone_votes : "");
      return h("button", { class: "pill badge-red", style: { cursor: "pointer" }, onClick: function () { go("/student/" + s.id); } }, s.full_name + tag);
    });
    return h("div", { class: "card dropbar mb-5" },
      h("div", { class: "card-pad" },
        h("div", { style: { display: "flex", alignItems: "baseline", gap: "10px", flexWrap: "wrap" } },
          h("div", { style: { flex: "1", minWidth: "200px" } },
            h("div", { style: { fontWeight: "650", fontSize: "15px", color: "var(--red)" } },
              "Требуют внимания: " + risk.length),
            h("div", { class: "muted tiny" },
              "Изоляты и ученики, которых класс отмечает как одиноких")),
          h("span", { class: "badge badge-red" }, String(risk.length))),
        h("div", { class: "chip-row", style: { marginTop: "12px" } }, chips)));
  }

  /* -------------------------------------------------- экспорт в Excel (.xlsx) */
  // Файл собирает сервер (openpyxl). Раньше он строился в браузере библиотекой
  // с CDN: без интернета кнопка не работала, а школьные сети cdnjs фильтруют.
  function exportXlsx() {
    if (!dash.surveyId) return;
    window.location.href = "/api/surveys/" + dash.surveyId + "/export.xlsx" + tokenQuery();
  }

  /* -------------------------------------------------- отчёт (CSV/печать) */
  function reportModal() {
    var a = dash.analysis; if (!a) return;
    var per = a.per_student, gm = a.graph_metrics, sv = currentSurvey();
    var sorted = dash.students.slice().sort(function (x, y) {
      var mx = per[String(x.id)], my = per[String(y.id)];
      return ((mx && mx.in_degree) || 0) - ((my && my.in_degree) || 0);
    });
    function statusText(m) {
      if (!m) return "—";
      if (m.status === "isolate") return "Изолят";
      if (m.status === "unknown") return "Нет данных";
      return "Группа " + ((m.community || 0) + 1);
    }
    var tbody = h("tbody", {}, sorted.map(function (s) {
      var m = per[String(s.id)] || {};
      return h("tr", {}, h("td", {}, s.full_name), h("td", {}, statusText(m)),
        h("td", { class: "num" }, m.in_degree || 0), h("td", { class: "num" }, m.out_degree || 0),
        h("td", { class: "num" }, m.mutual || 0), h("td", { class: "num" }, aloneText(m.alone_votes, m.alone_reportable)),
        h("td", { class: "num" }, num(m.degree_centrality, 2)), h("td", { class: "num" }, num(m.betweenness, 3)));
    }));
    var report = h("div", { class: "print-area" },
      h("h2", { style: { fontSize: "20px", marginBottom: "2px" } }, "Отчёт: " + dash.cls.name),
      h("p", { class: "muted", style: { marginBottom: "12px" } }, sv ? sv.title + " · " + fmtDate(sv.conducted_on) : ""),
      h("div", { class: "chip-row", style: { marginBottom: "14px" } },
        h("span", { class: "pill" }, "Учеников: " + gm.students),
        h("span", { class: "pill" }, "Прошли опрос: " + gm.responded + " (" + Math.round((gm.participation || 0) * 100) + "%)"),
        h("span", { class: "pill" }, "Изоляты: " + gm.isolates),
        gm.unknown ? h("span", { class: "pill" }, "Без данных: " + gm.unknown) : null,
        h("span", { class: "pill" }, "Взаимные пары: " + gm.mutual_pairs),
        h("span", { class: "pill" }, "Плотность: " + num(gm.density, 2)),
        h("span", { class: "pill" }, "Сплочённость: " + num(gm.cohesion, 2))),
      // Отчёт уходит завучу и в личное дело — оговорка о достоверности должна
      // ехать вместе с цифрами, а не оставаться на экране психолога.
      gm.reliability === "low" ? h("p", { class: "muted", style: { marginBottom: "12px" } },
        "Внимание: опрос прошли менее 70% класса. Показатели считаются по ответившим, "
        + "статус «изолят» в этом срезе не присваивается.") : null,
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", {}, "Статус"),
          h("th", { class: "num" }, "Вх"), h("th", { class: "num" }, "Исх"), h("th", { class: "num" }, "Вз"),
          h("th", { class: "num" }, "Один"), h("th", { class: "num" }, "Degree"), h("th", { class: "num" }, "Betw."))),
        tbody)));
    function csvRows() {
      var rows = [["Класс", dash.cls.name], ["Срез", sv ? sv.title : "", sv ? sv.conducted_on : ""],
        ["Учеников", gm.students, "Прошли опрос", gm.responded, "Явка", Math.round((gm.participation || 0) * 100) + "%"],
        ["Достоверность", gm.reliability, "Изоляты", gm.isolates, "Без данных", gm.unknown],
        ["Взаимные пары", gm.mutual_pairs, "Плотность", gm.density, "Сплочённость", gm.cohesion, "Взаимность", gm.reciprocity], [],
        ["Ученик", "Статус", "Входящие", "Исходящие", "Взаимные", "Часто один", "Degree centrality", "Betweenness", "Группа"]];
      sorted.forEach(function (s) {
        var m = per[String(s.id)] || {};
        rows.push([s.full_name, statusText(m), m.in_degree || 0, m.out_degree || 0, m.mutual || 0, aloneText(m.alone_votes, m.alone_reportable), m.degree_centrality || 0, m.betweenness || 0, (m.community || 0) + 1]);
      });
      return rows;
    }
    var fname = "izolyat_" + String(dash.cls.name || "class").replace(/\s+/g, "_") + ".csv";
    var close = openModal("Отчёт класса", report,
      [h("button", { class: "btn", onClick: function () { downloadCSV(fname, csvRows()); } }, "Скачать CSV"),
       h("button", { class: "btn", onClick: function () { window.print(); } }, "Печать"),
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
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", { class: "num" }, "Вх (A)"),
          h("th", { class: "num" }, "Вх (B)"), h("th", { class: "num" }, "Δ"), h("th", {}, "Изменение"))),
        h("tbody", {}, body))));
  }

  /* -------------------------------------------------- импорт учеников */
  function importStudentsModal(onDone) {
    var info = h("div", { class: "muted tiny" }, "Excel (.xlsx) или CSV: имя берётся из колонки «ФИО»/«Имя», а если заголовков нет, берётся первый столбец. Или вставьте список вручную.");
    var fileIn = h("input", { class: "input", type: "file", accept: ".xlsx,.csv,.txt" });
    var ta = h("textarea", { class: "textarea", style: { minHeight: "170px" }, placeholder: "По одному ученику в строке:\nАлина Смирнова\nБорис Кузнецов, м, 2011-05-14" });
    var msg = h("div"); var close;
    // Файл разбирает сервер: раньше это делала библиотека с CDN, и в школьной
    // сети без доступа к cdnjs импорт не работал вовсе.
    fileIn.addEventListener("change", function () {
      var f = fileIn.files && fileIn.files[0]; if (!f) return;
      msg.replaceChildren(h("span", { class: "muted tiny" }, "Читаю файл…"));
      var fd = new FormData();
      fd.append("file", f);
      fetch("/api/classes/" + dash.classId + "/students/import", {
        method: "POST",
        headers: { Authorization: "Bearer " + localStorage.getItem("izolyat.token") },
        body: fd,
      })
        // json() бросает на не-JSON ответе (502 от прокси, HTML-страница
        // ошибки) — тогда пользователь увидел бы «Unexpected token <».
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (d) {
            if (!r.ok) throw new Error(errMsg(d, r.status));
            return d;
          });
        }, function () { throw new Error("Нет связи с сервером. Проверьте подключение и повторите."); })
        .then(function (d) {
          var lines = d.students.map(function (s) {
            return [s.full_name, s.gender === "m" ? "м" : s.gender === "f" ? "ж" : "", s.birth_date || ""]
              .filter(Boolean).join(", ");
          });
          ta.value = (ta.value ? ta.value.trim() + "\n" : "") + lines.join("\n");
          msg.replaceChildren(alertBox("ok", "Из файла прочитано строк: " + lines.length + ". Проверьте список и нажмите «Импортировать»."));
        })
        .catch(function (e) { msg.replaceChildren(alertBox("error", e.message)); });
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

  /* ========================================================= STUDENT CARD */
  function renderStudent(id) {
    stopNetwork();
    mount(shell(spinner()));
    API.get("/api/students/" + id + "/card").then(buildStudent)
      .catch(function (e) { mount(shell(h("div", {}, alertBox("error", e.message), h("p", { style: { marginTop: "12px" } }, h("a", { href: "#/" }, "На главную"))))); });
  }

  /* --------------------------------------------- «Как помочь»: подсказка
     Методическая подсказка по обезличенным показателям. Наружу уходят
     только цифры — ни имени, ни заметок (см. app/assist.py). Психолог
     может раскрыть и посмотреть, что именно было отправлено: доверие к
     такой функции держится на проверяемости, а не на обещании.

     Кнопка показывается только если ключ задан на сервере: предлагать
     действие, которое заведомо вернёт ошибку, хуже, чем не предлагать. */
  function assistBlock(sid, latest) {
    if (!state.features || !state.features.ai_assist) return null;

    var body = h("div", { class: "card-pad" });
    var btn = h("button", { class: "btn btn-primary" }, "Подобрать шаги");

    function intro() {
      body.replaceChildren(
        h("p", { class: "muted", style: { marginBottom: "var(--s4)" } },
          latest
            ? "Подберём, с чего начать работу, по показателям последнего среза. "
              + "Наружу уходят только цифры: возраст, число выборов и явка класса. "
              + "Имя, код и заметки не передаются."
            : "Срезов ещё не было — подсказку можно получить после первого опроса."),
        latest ? btn : null);
    }

    function fail(msg) {
      body.replaceChildren(alertBox("error", msg),
        h("div", { style: { marginTop: "var(--s3)" } },
          h("button", { class: "btn btn-sm", onClick: run }, "Попробовать ещё раз")));
    }

    function show(d) {
      var a = d.assist;
      var kids = [];
      if (a.reading) kids.push(h("p", { class: "assist-reading" }, a.reading));

      kids.push(h("ol", { class: "assist-steps" }, a.steps.map(function (s) {
        return h("li", {},
          h("div", { class: "as-title" }, s.title),
          s.how ? h("div", { class: "as-how" }, s.how) : null);
      })));

      if (a.watch && a.watch.length) {
        kids.push(h("div", { class: "assist-sub" },
          h("div", { class: "section-title" }, "На что обратить внимание"),
          h("ul", { class: "assist-watch" }, a.watch.map(function (w) { return h("li", {}, w); }))));
      }
      if (a.escalate) {
        kids.push(h("div", { class: "assist-escalate" },
          h("div", { class: "section-title" }, "Когда нужен не только психолог"),
          h("p", {}, a.escalate)));
      }

      // Что именно ушло наружу — раскрывается по клику. Психолог отвечает
      // за данные детей и должен иметь возможность это проверить.
      kids.push(h("details", { class: "assist-sent" },
        h("summary", { class: "tiny muted" }, "Что было отправлено"),
        h("pre", { class: "assist-json" }, JSON.stringify(d.sent, null, 2))));

      kids.push(h("p", { class: "assist-disclaimer tiny" },
        "Подсказка составлена языковой моделью по обезличенным показателям и "
        + "не является заключением. Решение принимает психолог."));

      kids.push(h("div", { style: { marginTop: "var(--s4)" } },
        h("button", { class: "btn btn-sm", onClick: run }, "Пересобрать")));

      body.replaceChildren();
      kids.forEach(function (k) { if (k) body.appendChild(k); });
    }

    function run() {
      body.replaceChildren(
        h("div", { class: "assist-loading" },
          h("div", { class: "spinner" }),
          h("p", { class: "muted tiny", style: { marginTop: "var(--s3)" } },
            "Подбираем шаги…")));
      API.post("/api/students/" + sid + "/assist", {})
        .then(show)
        .catch(function (e) { fail(e.message); });
    }

    btn.addEventListener("click", run);
    intro();

    return h("div", { class: "card mb-5" },
      h("div", { class: "card-head" },
        h("h3", {}, "Как помочь"),
        h("span", { class: "spacer" }),
        h("span", { class: "badge" }, "ИИ-подсказка")),
      body);
  }

  function buildStudent(data) {
    var student = data.student;
    // dynamics приходят уже отсортированными по дате среза и содержат только
    // агрегаты — сырых выборов с авторством сервер больше не отдаёт.
    var dyn = data.dynamics;
    var latest = dyn.length ? dyn[dyn.length - 1] : null;

    // Шапка-профиль: инициалы, имя, под ним — сухие факты одной строкой.
    // Статус справа, потому что это первое, ради чего карточку открывают.
    var initials = (student.full_name || "?").trim().split(/\s+/)
      .slice(0, 2).map(function (w) { return w.charAt(0).toUpperCase(); }).join("");
    var facts = [];
    facts.push(student.gender === "m" ? "мужской пол" : student.gender === "f" ? "женский пол" : null);
    facts.push(ageText(student.birth_date));
    facts = facts.filter(Boolean);

    var header = h("div", { class: "card stu-header" },
      h("div", { class: "sh-avatar" }, initials),
      h("div", { class: "sh-main" },
        h("h1", {}, student.full_name),
        h("div", { class: "sh-facts" },
          h("span", { class: "pill mono" }, student.code),
          facts.length ? h("span", { class: "muted tiny" }, facts.join(" · ")) : null),
        student.note ? h("p", { class: "sh-note" }, student.note) : null),
      h("div", { class: "sh-status" },
        h("div", { class: "section-title" }, "Текущий статус"),
        latest ? (latest.status === "connected" && latest.community != null
          ? communityPill(latest.community) : statusPill(latest.status)) : h("span", { class: "muted" }, "нет срезов"),
        latest ? h("div", { class: "muted tiny", style: { marginTop: "6px" } }, "на " + fmtDate(latest.date)) : null));

    var metricsBody = latest ? h("div", {},
      h("div", { class: "tiles" },
        tile("Входящие", latest.in_degree, "кто выбрал"),
        tile("Исходящие", latest.out_degree, "кого выбрал"),
        tile("Взаимные", latest.mutual, "пары"),
        tile("«Часто один»", latest.alone_count == null ? "менее 3" : latest.alone_count, "номинаций"),
        tile("Betweenness", num(latest.betweenness, 3), "посредничество")),
      latest.reliability === "low" ? h("div", { style: { marginTop: "12px" } },
        alertBox("info", "Последний срез прошли " + Math.round((latest.participation || 0) * 100)
          + "% класса. Показатели считаются по ответившим, судить об изоляции по ним нельзя.")) : null)
      : emptyState("Нет данных", "Нужен хотя бы один заполненный срез.");
    var metricsCardEl = h("div", { class: "card mb-5" },
      h("div", { class: "card-head" }, h("h3", {}, "Показатели"), h("span", { class: "spacer" }),
        latest ? h("span", { class: "muted tiny" }, latest.title + " · " + fmtDate(latest.date)) : null),
      h("div", { class: "card-pad" }, metricsBody));

    // Срезы — строками сверху вниз, новые первыми. Таблица на восемь колонок
    // («Вх», «Исх», «Вз», «Один», «Δвх») не читалась: сокращения приходилось
    // расшифровывать по всплывающей подсказке. Здесь на виду то, ради чего
    // смотрят динамику, — входящие выборы и их изменение к прошлому срезу.
    var dynTable = null;
    if (dyn.length) {
      var items = dyn.slice().reverse().map(function (p) {
        var i = dyn.indexOf(p);
        var delta = i === 0 ? null : p.in_degree - dyn[i - 1].in_degree;
        var parts = ["исходящих: " + p.out_degree, "взаимных: " + p.mutual];
        if (p.alone_count != null) parts.push("«часто один»: " + p.alone_count);
        return h("div", { class: "dynrow" },
          h("div", { class: "dr-main" },
            h("div", { class: "dr-title" }, p.title),
            h("div", { class: "dr-sub" }, fmtDate(p.date) + " · " + parts.join(" · "))),
          h("div", { class: "dr-status" }, statusPill(p.status)),
          h("div", { class: "dr-in" },
            h("span", { class: "dr-in-num" }, String(p.in_degree)),
            h("span", { class: "dr-in-cap" }, "входящих")),
          h("div", { class: "dr-delta" },
            delta === null ? h("span", { class: "muted tiny" }, "первый") : deltaSpan(delta)));
      });
      dynTable = h("div", { class: "dynlist" }, items);
    }
    var dynamicsCard = h("div", { class: "card mb-5" },
      h("div", { class: "card-head" }, h("h3", {}, "Динамика (входящие выборы)")),
      h("div", { class: "card-pad" }, lineChart(dyn), dynTable));

    var historyCard = h("div", { class: "card mb-5" },
      h("div", { class: "card-head" }, h("h3", {}, "История связей"), h("span", { class: "spacer" }), h("span", { class: "muted tiny" }, "изменение по срезам")),
      h("div", { class: "card-pad" }, dyn.length === 0 ? emptyState("Нет срезов")
        : h("div", { class: "stack" }, dyn.slice().reverse().map(function (p) { return connectionBlock(p); }))));

    var assistCard = assistBlock(student.id, latest);

    var intCard = h("div", { class: "card mb-5" },
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
      header, metricsCardEl, assistCard, dynamicsCard, historyCard, intCard,
      h("div", { class: "two-col" }, meetingsCard, notesCard))));

    function del(url, msg, sid) { if (confirm(msg)) API.del(url).then(function () { renderStudent(sid); }); }
  }

  function listRow(when, body, onDelete) {
    return h("div", { class: "list-item" }, h("div", { class: "when" }, when), h("div", { class: "body" }, body),
      h("button", { class: "btn btn-danger btn-sm", onClick: onDelete }, "Удалить"));
  }

  // Сводка по одному срезу.
  //
  // Раньше здесь рисовался поимённый список «отметили как часто один» — то
  // есть психолог видел, кто из детей назвал этого ребёнка одиноким. Сервер
  // такие данные больше не отдаёт вообще (см. app/analytics.py): негативная
  // номинация приходит только числом и только начиная с трёх. Положительные
  // связи остаются — они и так видны на социограмме, — но здесь показываются
  // счётчиками и взаимными парами, а не списком «кто тебя выбрал».
  function connectionBlock(p) {
    var aloneTxt = p.alone_count == null ? "менее 3" : String(p.alone_count);
    var body;
    if (!p.responded && p.in_degree === 0) {
      body = h("span", { class: "muted tiny" }, "Ученик не проходил этот срез, и его никто не выбрал.");
    } else {
      body = h("div", {},
        h("div", { class: "tiles" },
          tile("Входящие", p.in_degree, "кто выбрал его / её"),
          tile("Исходящие", p.out_degree, "кого выбрал(а)"),
          tile("Взаимные", p.mutual, "пары"),
          tile("«Часто один»", aloneTxt, "номинаций класса")),
        p.mutual_names && p.mutual_names.length
          ? h("div", { style: { marginTop: "10px" } },
              h("div", { class: "section-title" }, "Взаимные симпатии"),
              h("div", { class: "chip-row" }, p.mutual_names.map(function (nm) {
                return h("span", { class: "pill", style: { color: "var(--accent)", borderColor: "var(--accent)" } }, "Взаимно: " + nm);
              })))
          : h("div", { class: "muted tiny", style: { marginTop: "10px" } }, "Взаимных пар в этом срезе нет."));
    }
    return h("div", { style: { borderBottom: "1px solid var(--border)", paddingBottom: "14px" } },
      h("div", { style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", flexWrap: "wrap" } },
        h("b", {}, p.title), h("span", { class: "muted tiny" }, fmtDate(p.date)),
        h("span", { style: { flex: "1" } }),
        statusPill(p.status),
        p.reliability === "low" ? lowDataPill(p.participation) : null),
      body);
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
        h("button", { class: "btn btn-danger btn-sm", onClick: function () { if (confirm("Удалить вмешательство?")) API.del("/api/interventions/" + iv.id).then(function () { renderStudent(studentId); }); } }, "Удалить")),
      iv.description ? h("p", { class: "muted", style: { marginTop: "6px" } }, iv.description) : null,
      iv.outcome ? h("p", { style: { marginTop: "6px" } }, h("b", {}, "Итог: "), iv.outcome) : null,
      h("div", { style: { marginTop: "8px" } }, delta != null
        ? h("span", { class: "pill" }, "Входящие выборы: было " + before.in_degree + ", стало " + after.in_degree + " ", deltaSpan(delta))
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
            asyncBtn({ class: "btn btn-primary btn-sm", onClick: save }, "Сохранить"),
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
  /* ============================================== ГЛАВНАЯ: все классы */
  // Работа психолога — 250-300 учеников в десятке классов. Открывать каждый
  // класс по очереди, чтобы понять, где что-то происходит, невозможно, поэтому
  // главный экран — список классов, отсортированный по тому, куда смотреть
  // в первую очередь.
  function renderHome() {
    stopNetwork();
    mount(shell(spinner()));
    Promise.all([API.get("/api/overview"), refreshUnseen()])
      .then(function (res) { mount(shell(homeView(res[0]))); })
      .catch(function (e) { mount(shell(alertBox("error", e.message))); });
  }

  function homeView(data) {
    var rows = data.classes;
    if (!rows.length) {
      return h("div", {}, homeHeader(0),
        h("div", { class: "card card-pad" }, emptyState("Ещё нет ни одного класса",
          "Создайте класс, добавьте учеников, отметьте согласия родителей и запускайте срез.",
          h("button", { class: "btn btn-primary", onClick: function () { classModal(null); } }, "Создать класс"))));
    }

    // Классы — строками, а не плитками. Сервер уже отсортировал их по
    // «нужности внимания», и список сверху вниз читается как очередь работы:
    // в сетке равнозначных карточек этот порядок не виден. Каждая строка —
    // одна мысль: что за класс, что с ним, насколько он связен.
    var items = rows.map(function (r) {
      var c = r["class"];
      var wi = r.wellbeing_index;
      var needsSurvey = !r.last_survey;

      // Состояние класса одной формулировкой — то, ради чего психолог
      // просматривает список. Приоритет тот же, что в серверной сортировке.
      var state_, stateClass;
      if (r.open_alerts) {
        state_ = r.open_alerts + " " + plural(r.open_alerts, "сигнал", "сигнала", "сигналов");
        stateClass = "badge-danger";
      } else if (r.isolates) {
        state_ = r.isolates + " " + plural(r.isolates, "изолят", "изолята", "изолятов");
        stateClass = "badge-warn";
      } else if (needsSurvey) {
        state_ = "Нет срезов";
        stateClass = "";
      } else if (r.reliability === "low") {
        state_ = "Низкая явка";
        stateClass = "badge-warn";
      } else {
        state_ = "Спокойно";
        stateClass = "badge-ok";
      }

      var notes = [];
      if (r.consent.missing.length) {
        notes.push(r.consent.missing.length + " без согласия");
      }
      if (!needsSurvey) {
        notes.push(fmtDate(r.last_survey.conducted_on));
      }

      return h("div", {
        class: "classrow" + (r.open_alerts ? " urgent" : ""),
        onClick: function () { go("/class/" + c.id); },
      },
        h("div", { class: "cr-main" },
          h("div", { class: "cr-name" }, c.name),
          h("div", { class: "cr-sub" },
            r.students + " " + plural(r.students, "ученик", "ученика", "учеников"),
            notes.length ? " · " + notes.join(" · ") : "")),
        h("div", { class: "cr-state" },
          h("span", { class: "badge " + stateClass }, h("span", { class: "dot" }), state_)),
        h("div", { class: "cr-part" },
          needsSurvey
            ? h("span", { class: "muted tiny" }, "—")
            : h("div", {},
                h("div", { class: "cr-part-num" }, Math.round((r.participation || 0) * 100) + "%"),
                h("div", { class: "progress" },
                  h("span", { style: { width: Math.round((r.participation || 0) * 100) + "%" } })))),
        h("div", { class: "cr-wi", title: WI_HINT },
          h("span", { class: "cr-wi-num" }, wi == null ? "—" : wi),
          h("span", { class: "cr-wi-cap" }, "индекс")));
    });

    return h("div", {},
      homeHeader(rows.length),
      homeSummary(rows),
      h("div", { class: "card section-gap" },
        h("div", { class: "card-head" },
          h("h3", {}, "Классы"),
          h("span", { class: "count-chip" }, String(rows.length)),
          h("span", { class: "spacer" }),
          h("span", { class: "muted tiny hide-sm" }, "Сверху — куда смотреть в первую очередь")),
        h("div", { class: "classlist-head" },
          h("div", {}, "Класс"),
          h("div", {}, "Состояние"),
          h("div", {}, "Явка"),
          h("div", {}, "Индекс")),
        h("div", { class: "classlist" }, items)));
  }

  // Сводка по всем классам сразу: психологу с 250-300 учениками важно
  // сначала увидеть общую картину, а уже потом идти по карточкам. Числа
  // считаются на клиенте из того же ответа /api/overview — отдельный
  // запрос ради четырёх сумм не нужен.
  function homeSummary(rows) {
    var students = 0, alerts = 0, isolates = 0, noConsent = 0, wiSum = 0, wiCount = 0, needSurvey = 0;
    rows.forEach(function (r) {
      students += r.students || 0;
      alerts += r.open_alerts || 0;
      isolates += r.isolates || 0;
      noConsent += (r.consent && r.consent.missing ? r.consent.missing.length : 0);
      if (r.wellbeing_index != null) { wiSum += r.wellbeing_index; wiCount++; }
      if (!r.last_survey) needSurvey++;
    });
    var avgWi = wiCount ? Math.round(wiSum / wiCount) : null;

    // Качественная оценка рядом с числом: «61» само по себе ничего не
    // говорит тому, кто видит индекс впервые.
    var wiWord = avgWi == null ? null
      : avgWi >= 70 ? "высокий" : avgWi >= 45 ? "средний" : "низкий";

    // Показатели разведены по роли, а не выстроены в ряд одинаковых плиток:
    //   * индекс — аналитика, главное число экрана;
    //   * сигналы и согласия — требуют действия, поэтому ведут по ссылке
    //     и окрашены статусным цветом только когда действие есть;
    //   * классы и ученики — контекст, нейтральные.
    return h("div", { class: "hero" },
      h("div", { class: "hero-main" },
        h("div", { class: "tile-label", title: WI_HINT }, "Средний индекс связности"),
        h("div", { class: "hero-figure" },
          h("div", { class: "hero-value", title: WI_HINT }, avgWi == null ? "—" : String(avgWi)),
          wiWord ? h("div", { class: "hero-scale" },
            h("div", { class: "hero-word" }, wiWord),
            h("div", { class: "hero-track" },
              h("span", { style: { width: Math.max(2, Math.min(100, avgWi)) + "%" } })),
            h("div", { class: "hero-ticks" }, h("span", {}, "0"), h("span", {}, "100"))) : null),
        h("div", { class: "muted tiny" },
          wiCount
            ? "по " + wiCount + " " + plural(wiCount, "классу", "классам", "классам") + " со срезами"
            : "срезов пока не было"),
        h("div", { class: "hero-note" },
          alerts
            ? [h("span", { class: "badge badge-danger" }, h("span", { class: "dot" }),
                alerts + " " + plural(alerts, "сигнал", "сигнала", "сигналов")),
               h("a", { href: "#/alerts" }, "Разобрать")]
            : h("span", { class: "badge badge-ok" }, h("span", { class: "dot" }), "Активных сигналов нет"))),
      h("div", { class: "hero-tiles" },
        tile("Классов", rows.length, needSurvey ? needSurvey + " без срезов" : "все со срезами"),
        tile("Учеников", students, "в работе"),
        tile("Изолятов", isolates, "по последним срезам"),
        tile("Без согласия", noConsent, noConsent ? "не участвуют в срезах" : "все согласия собраны")));
  }

  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  }

  function homeHeader(count) {
    var name = state.user && state.user.full_name ? state.user.full_name.split(" ")[0] : null;
    return h("div", { class: "page-head" },
      h("div", { style: { flex: "1", minWidth: "200px" } },
        h("h1", {}, name ? "С возвращением, " + name : "Мои классы"),
        h("div", { class: "muted tiny" }, count ? "Сначала те, где нужно внимание" : "")),
      h("button", { class: "btn btn-primary", onClick: function () { classModal(null); } }, "+ Класс"));
  }

  /* ================================================ ВХОДЯЩИЕ: оповещения */
  function renderAlerts() {
    stopNetwork();
    mount(shell(spinner()));
    var showResolved = false;

    function load() {
      API.get("/api/alerts" + (showResolved ? "?resolved=true" : ""))
        .then(function (d) {
          state.unseen = d.unseen || 0;
          mount(shell(view(d)));
          // Открыли входящие — значок гасим, но сами оповещения остаются
          // в работе, пока психолог не закроет каждое явно.
          if (!showResolved && d.unseen) {
            API.post("/api/alerts/seen").then(function () { state.unseen = 0; });
          }
        })
        .catch(function (e) { mount(shell(alertBox("error", e.message))); });
    }

    function view(d) {
      var toggle = h("button", { class: "btn btn-sm", onClick: function () { showResolved = !showResolved; load(); } },
        showResolved ? "К активным" : "Показать закрытые");
      var body;
      if (!d.alerts.length) {
        body = emptyState(
          showResolved ? "Закрытых оповещений нет" : "Активных оповещений нет",
          showResolved ? null : "Оповещения появляются здесь автоматически, когда вы закрываете срез.");
      } else {
        body = h("div", { class: "stack" }, d.alerts.map(function (a) { return alertRow(a, load, showResolved); }));
      }
      return h("div", {},
        h("div", { class: "page-head" },
          h("div", { style: { flex: "1", minWidth: "200px" } },
            h("h1", { style: { fontSize: "22px" } }, showResolved ? "Закрытые оповещения" : "Входящие"),
            h("div", { class: "muted tiny" }, "Система сама отмечает, у кого ухудшились связи между срезами")),
          toggle),
        h("div", { class: "card card-pad" }, body));
    }

    load();
  }

  function alertRow(a, reload, resolvedView) {
    var change = a.from_value != null
      ? h("span", { class: "muted tiny" }, "входящие связи: было " + a.from_value + ", стало " + a.to_value)
      : (a.kind === "alone"
          ? h("span", { class: "muted tiny" }, "номинаций «часто один»: " + a.to_value)
          : h("span", { class: "muted tiny" }, "нет входящих выборов"));
    // Тип сигнала — короткой подписью слева, а не значком: три разных
    // пиктограммы психолог всё равно держал бы в голове, а слово читается сразу.
    var mark = a.kind === "alone" ? "Одиночество" : a.kind === "isolate" ? "Изоляция" : "Спад";
    return h("div", { class: "list-item" },
      h("div", { class: "when" }, h("span", { class: "badge badge-red" }, mark)),
      h("div", { class: "body" },
        h("div", {}, h("b", {}, a.student_name), h("span", { class: "muted tiny" }, " · " + a.class_name)),
        h("div", { style: { marginTop: "2px" } }, a.title, ". ", change),
        h("div", { class: "muted tiny", style: { marginTop: "2px" } }, "срез «" + a.survey_title + "» · " + fmtDate(a.created_at))),
      h("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap" } },
        h("button", { class: "btn btn-sm", onClick: function () { go("/student/" + a.student_id); } }, "Карточка"),
        resolvedView
          ? h("button", { class: "btn btn-sm", onClick: function () { API.post("/api/alerts/" + a.id + "/reopen").then(reload); } }, "Вернуть")
          : h("button", { class: "btn btn-sm btn-primary", onClick: function () { API.post("/api/alerts/" + a.id + "/resolve").then(reload); } }, "Закрыть")));
  }

  /* ================================================== СВОДКА ПО ШКОЛЕ */
  // Экран завуча. Поимённой информации здесь нет и не должно быть: для
  // управленческого решения нужен класс, а не ребёнок.
  function renderSchool() {
    stopNetwork();
    mount(shell(spinner()));
    API.get("/api/school/summary")
      .then(function (d) { mount(shell(schoolView(d))); })
      .catch(function (e) { mount(shell(alertBox("error", e.message))); });
  }

  function schoolView(d) {
    var t = d.totals;
    var tiles = h("div", { class: "tiles" },
      h("div", { class: "tile tile-hero" },
        h("div", { class: "tile-label", title: WI_HINT }, "Средний индекс связности"),
        h("div", { class: "tile-value" }, t.avg_wellbeing == null ? "—" : t.avg_wellbeing),
        h("div", { class: "tile-sub", title: WI_HINT },
          t.avg_wellbeing == null ? "нет закрытых срезов" : "по школе · экспериментальный")),
      tile("Классов", t.classes, t.classes_without_surveys ? t.classes_without_surveys + " без срезов" : "все с срезами"),
      tile("Учеников", t.students),
      tile("Требуют внимания", t.open_alerts, "активных оповещений"),
      tile("Профилактика", t.activities_done, "проведено · " + t.activities_planned + " в плане"),
      tile("Без согласия", t.consent_missing, "не участвуют в срезах"));

    // Главный управленческий вопрос завуча к психологу: где есть сигналы, но
    // профилактическая работа не запланирована.
    var gap = t.alerts_without_activities
      ? h("div", { style: { marginTop: "12px" } }, alertBox("info",
          "Классов с тревожными сигналами, где профилактика не запланирована: "
          + t.alerts_without_activities + ". Это повод обсудить план с психологом."))
      : null;

    var rows = d.classes.map(function (r) {
      return h("tr", {},
        h("td", {}, r.class_name),
        h("td", {}, r.psychologist || h("span", { class: "muted" }, "—")),
        h("td", { class: "num" }, r.students),
        h("td", {}, r.last_survey ? fmtDate(r.last_survey) : h("span", { class: "muted" }, "нет срезов")),
        h("td", { class: "num" }, r.participation == null ? "—" : Math.round(r.participation * 100) + "%"),
        h("td", { class: "num" }, r.wellbeing_index == null
          ? h("span", { class: "muted", title: "Низкая явка: индекс не считается" }, "—") : r.wellbeing_index),
        h("td", { class: "num" }, r.isolates == null ? "—" : r.isolates),
        h("td", { class: "num" }, r.open_alerts
          ? h("span", { class: "badge badge-red" }, String(r.open_alerts)) : h("span", { class: "muted" }, "—")),
        h("td", { class: "num" }, (r.activities_done || 0) + " / " + ((r.activities_done || 0) + (r.activities_planned || 0))));
    });

    return h("div", {},
      h("div", { class: "page-head" },
        h("div", { style: { flex: "1", minWidth: "200px" } },
          h("h1", { style: { fontSize: "22px" } }, d.school ? d.school.name : "Школа"),
          h("div", { class: "muted tiny" }, "Сводка по классам. Персональных данных учеников на этом экране нет.")),
        h("a", { class: "btn btn-sm", href: "/api/school/export.xlsx" + tokenQuery() }, "Выгрузить в Excel")),
      h("div", { class: "card card-pad mb-5" }, tiles, gap),
      h("div", { class: "card" },
        h("div", { class: "card-head" }, h("h3", {}, "Классы"), h("span", { class: "spacer" }),
          h("span", { class: "muted tiny" }, "сначала те, где нужно внимание")),
        h("div", { class: "card-pad", style: { paddingTop: "6px" } },
          h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, h("th", {}, "Класс"), h("th", {}, "Психолог"),
              h("th", { class: "num" }, "Учеников"), h("th", {}, "Последний срез"),
              h("th", { class: "num" }, "Явка"), h("th", { class: "num", title: WI_HINT }, "Индекс"),
              h("th", { class: "num" }, "Изоляты"), h("th", { class: "num" }, "Сигналы"),
              h("th", { class: "num", title: "Проведено / всего запланировано" }, "Профилактика"))),
            h("tbody", {}, rows))))));
  }

  /* ==================================================== СОТРУДНИКИ */
  function renderStaff() {
    stopNetwork();
    mount(shell(spinner()));
    function load() {
      API.get("/api/auth/staff")
        .then(function (d) { mount(shell(staffView(d, load))); })
        .catch(function (e) { mount(shell(alertBox("error", e.message))); });
    }
    load();
  }

  function staffView(d, reload) {
    var ROLES = [["psychologist", "Психолог"], ["head", "Завуч (сводка без данных детей)"], ["admin", "Администратор"]];
    var rows = d.staff.map(function (u) {
      var sel = h("select", { class: "select", style: { width: "auto" }, onChange: function (e) {
        API.put("/api/auth/staff/" + u.id, { role: e.target.value }).then(reload).catch(function (err) { alert(err.message); reload(); });
      } });
      ROLES.forEach(function (r) { sel.appendChild(h("option", { value: r[0] }, r[1])); });
      sel.value = u.role;
      var self = state.user && u.id === state.user.id;
      if (self) sel.disabled = true;
      return h("tr", {},
        h("td", {}, u.full_name || u.email, self ? h("span", { class: "muted tiny" }, " · это вы") : null),
        h("td", { class: "muted" }, u.email),
        h("td", {}, sel),
        h("td", {}, u.last_login_at ? fmtDate(u.last_login_at) : h("span", { class: "muted" }, "не заходил")),
        h("td", { class: "num" }, self ? h("span", { class: "muted tiny" }, "—")
          : [h("button", {
              class: "btn btn-sm", title: "Выдать временный пароль",
              onClick: function () {
                if (!confirm("Сбросить пароль для «" + (u.full_name || u.email) + "»?\n\nВсе его текущие сессии будут завершены."))
                  return;
                API.post("/api/auth/staff/" + u.id + "/reset-password")
                  .then(function (d) {
                    prompt("Временный пароль для " + d.email
                      + "\n\nПередайте его лично и попросите сменить при первом входе:", d.temporary_password);
                    reload();
                  })
                  .catch(function (e) { alert(e.message); });
              },
            }, "Сбросить пароль"),
            h("button", { class: "btn btn-sm " + (u.is_active ? "btn-danger" : "btn-primary"), onClick: function () {
              API.put("/api/auth/staff/" + u.id, { is_active: !u.is_active }).then(reload);
            } }, u.is_active ? "Отключить" : "Включить")]));
    });

    var inviteIn = h("input", { class: "input mono", value: d.invite_code || "" });
    inviteIn.setAttribute("readonly", "");

    return h("div", {},
      h("h1", { style: { fontSize: "22px", marginBottom: "4px" } }, "Сотрудники школы"),
      h("div", { class: "muted tiny mb-5" },
        "Завуч видит только сводку по классам. Карточки учеников и имена ему недоступны."),
      h("div", { class: "card card-pad mb-5" },
        h("div", { class: "section-title" }, "Код приглашения"),
        h("p", { class: "muted tiny", style: { marginBottom: "8px" } },
          "Передайте его сотруднику. По нему он зарегистрируется именно в вашей школе. Без кода регистрация невозможна."),
        h("div", { class: "row" }, inviteIn,
          h("button", { class: "btn", onClick: function () { inviteIn.select(); try { document.execCommand("copy"); } catch (e) {} } }, "Копировать"))),
      h("div", { class: "card" },
        h("div", { class: "card-head" }, h("h3", {}, "Доступы")),
        h("div", { class: "card-pad", style: { paddingTop: "6px" } },
          h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, h("th", {}, "Сотрудник"), h("th", {}, "E-mail"),
              h("th", {}, "Роль"), h("th", {}, "Последний вход"), h("th", {}))),
            h("tbody", {}, rows))))));
  }

  /* ============================================ ПРОФИЛАКТИЧЕСКАЯ РАБОТА */
  // Граф сам по себе ничего не меняет. Этот экран — про то, что психолог
  // делает по его итогам: план занятий, отметка о проведении, охват и
  // сравнение «до/после». Это же его отчётность перед завучем.
  function renderPrevention() {
    stopNetwork();
    mount(shell(spinner()));
    var filter = "";
    function load() {
      API.get("/api/prevention/schedule" + (filter ? "?status=" + filter : ""))
        .then(function (d) { mount(shell(view(d))); })
        .catch(function (e) { mount(shell(alertBox("error", e.message))); });
    }

    function view(d) {
      var t = d.totals;
      var tiles = h("div", { class: "tiles" },
        tile("Запланировано", t.planned, t.overdue ? t.overdue + " просрочено" : "по всем классам"),
        tile("Проведено", t.done, "мероприятий"),
        tile("Охват учеников", t.students_covered, "уникальных"),
        tile("Родители и педагоги", t.adults_covered, "участников"));

      var tabs = h("div", { class: "toolbar" },
        ["", "planned", "done", "cancelled"].map(function (s) {
          var label = s === "" ? "Все" : s === "planned" ? "В плане" : s === "done" ? "Проведённые" : "Отменённые";
          return h("button", {
            class: "btn btn-sm" + (filter === s ? " btn-primary" : ""),
            onClick: function () { filter = s; load(); },
          }, label);
        }));

      var body = d.activities.length
        ? h("div", { class: "stack" }, d.activities.map(function (a) { return activityRow(a, load); }))
        : emptyState("Мероприятий нет",
            "Откройте класс и нажмите «Профилактика». Система предложит, с чего начать, по данным последнего среза.");

      return h("div", {},
        h("div", { class: "mb-5" },
          h("h1", { style: { fontSize: "22px" } }, "Профилактическая работа"),
          h("div", { class: "muted tiny" }, "План, проведение и охват по всем вашим классам")),
        h("div", { class: "card card-pad mb-5" }, tiles),
        h("div", { class: "card" },
          h("div", { class: "card-head" }, h("h3", {}, "Мероприятия"), h("span", { class: "spacer" }), tabs),
          h("div", { class: "card-pad" }, body)));
    }
    load();
  }

  function activityRow(a, reload) {
    var status = a.status === "done"
      ? h("span", { class: "pill badge-green" }, "проведено")
      : a.status === "cancelled"
        ? h("span", { class: "pill muted" }, "отменено")
        : a.overdue
          ? h("span", { class: "pill", style: { color: "var(--red)", borderColor: "var(--red)" } }, "просрочено")
          : h("span", { class: "pill" }, "в плане");

    var when = a.status === "done"
      ? "проведено " + fmtDate(a.conducted_on)
      : "запланировано на " + fmtDate(a.planned_on);

    var coverage = a.target === "adults"
      ? (a.adults_count ? a.adults_count + " участников" : null)
      : (a.status === "done" ? "охват: " + a.attended_count + " учеников" : null);

    var actions = [];
    if (a.status === "planned") {
      actions.push(h("button", { class: "btn btn-sm btn-primary", onClick: function () { completeModal(a, reload); } }, "Отметить проведение"));
      actions.push(h("button", { class: "btn btn-sm", onClick: function () { activityModal(a.class_id, a, reload); } }, "Изменить"));
      actions.push(h("button", { class: "btn btn-sm", title: "Отменить", onClick: function () {
        if (confirm("Отменить мероприятие «" + a.title + "»?")) API.post("/api/prevention/activities/" + a.id + "/cancel").then(reload);
      } }, "Удалить"));
    } else if (a.status === "done") {
      actions.push(h("button", { class: "btn btn-sm", onClick: function () { effectModal(a); } }, "Оценка эффекта"));
    }
    actions.push(h("button", { class: "btn btn-danger btn-sm", title: "Удалить", onClick: function () {
      if (confirm("Удалить мероприятие «" + a.title + "» из журнала?")) API.del("/api/prevention/activities/" + a.id).then(reload);
    } }, "Удалить"));

    return h("div", { class: "list-item", style: { alignItems: "flex-start" } },
      h("div", { class: "body" },
        h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
          h("b", {}, a.title), status,
          h("span", { class: "pill" }, a.kind_title)),
        h("div", { class: "muted tiny", style: { marginTop: "4px" } },
          [a.class_name, a.target_title, when, coverage].filter(Boolean).join(" · ")),
        a.goal ? h("div", { class: "muted", style: { marginTop: "6px", fontSize: "13px" } }, a.goal) : null,
        a.outcome ? h("div", { style: { marginTop: "6px", fontSize: "13px" } }, h("b", {}, "Итог: "), a.outcome) : null,
        a.effectiveness ? h("div", { style: { marginTop: "4px" } }, stars(a.effectiveness)) : null),
      h("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap" } }, actions));
  }

  // Рекомендации по данным среза + план класса. Открывается из карточки класса.
  function preventionModal(classId) {
    var wrap = h("div", spinner());
    var close = openModal("Профилактика — " + (dash.cls ? dash.cls.name : "класс"), [wrap],
      [h("button", { class: "btn btn-primary", onClick: function () { close(); } }, "Закрыть")], true);

    function reload() {
      Promise.all([
        API.get("/api/prevention/classes/" + classId + "/recommendations"),
        API.get("/api/prevention/classes/" + classId + "/activities"),
      ]).then(function (res) { wrap.replaceChildren(body(res[0], res[1].activities)); })
        .catch(function (e) { wrap.replaceChildren(alertBox("error", e.message)); });
    }

    function body(rec, activities) {
      var recBlock;
      if (!rec.available) {
        recBlock = alertBox("info", rec.reason);
      } else if (!rec.items.length) {
        recBlock = alertBox("ok", "По последнему срезу тревожных признаков нет. "
          + "Срочных мероприятий система не предлагает. Плановые занятия можно добавить вручную.");
      } else {
        recBlock = h("div", { class: "stack" }, rec.items.map(function (item) {
          return h("div", { class: "card card-pad", style: { borderColor: "var(--border-strong)" } },
            h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
              h("b", {}, item.title),
              h("span", { class: "pill" }, item.reason)),
            h("div", { class: "muted", style: { marginTop: "6px", fontSize: "13px" } }, item.goal),
            item.pairs && item.pairs.length
              ? h("div", { style: { marginTop: "8px" } },
                  h("div", { class: "section-title" }, "Кого с кем объединить"),
                  h("div", { class: "chip-row" }, item.pairs.map(function (p) {
                    return h("span", { class: "pill" }, p.partner_name
                      ? p.student_name + " и " + p.partner_name
                      : p.student_name + ": пару подобрать вручную");
                  })))
              : null,
            h("details", { style: { marginTop: "8px" } },
              h("summary", { class: "muted tiny", style: { cursor: "pointer" } }, "Ход занятия"),
              h("pre", { class: "plan-text" }, item.plan)),
            h("div", { style: { marginTop: "10px" } },
              h("button", { class: "btn btn-sm btn-primary", onClick: function () {
                activityModal(classId, null, function () { reload(); }, item, rec.survey);
              } }, "Запланировать")));
        }));
      }

      var planBlock = activities.length
        ? h("div", { class: "stack" }, activities.map(function (a) {
            a.class_name = dash.cls ? dash.cls.name : "";
            return activityRow(a, reload);
          }))
        : h("span", { class: "muted tiny" }, "Пока ничего не запланировано.");

      return h("div", {},
        h("div", { class: "section-title" }, "Что предлагает система"),
        rec.survey ? h("div", { class: "muted tiny", style: { marginBottom: "8px" } },
          "По срезу «" + rec.survey.title + "» от " + fmtDate(rec.survey.conducted_on)) : null,
        recBlock,
        h("div", { class: "section-title", style: { marginTop: "18px" } }, "План класса"),
        h("div", { style: { marginBottom: "8px" } },
          h("button", { class: "btn btn-sm", onClick: function () { activityModal(classId, null, reload); } },
            "+ Своё мероприятие")),
        planBlock);
    }

    reload();
  }

  // Создание/правка мероприятия. tmpl — заготовка из рекомендаций.
  function activityModal(classId, activity, onDone, tmpl, survey) {
    var src = activity || tmpl || {};
    var titleIn = h("input", { class: "input", value: src.title || "" });
    var goalIn = h("textarea", { class: "textarea", value: src.goal || "" });
    var planIn = h("textarea", { class: "textarea", style: { minHeight: "160px" }, value: src.plan || "" });
    var dateIn = h("input", { class: "input", type: "date",
      value: (activity && activity.planned_on) || new Date().toISOString().slice(0, 10) });
    var durIn = h("input", { class: "input", type: "number", min: "5", step: "5",
      value: (activity && activity.duration_min) || 45 });

    var kindIn = h("select", { class: "select" });
    KINDS.forEach(function (k) { kindIn.appendChild(h("option", { value: k[0] }, k[1])); });
    kindIn.value = src.kind || "training";

    var targetIn = h("select", { class: "select" });
    TARGETS.forEach(function (k) { targetIn.appendChild(h("option", { value: k[0] }, k[1])); });
    targetIn.value = src.target || "class";

    // Состав участников нужен только для подгруппы и отдельного ученика:
    // для мероприятия на весь класс он подставится на момент проведения.
    var pickWrap = h("div");
    var picks = [];
    function renderPicks() {
      var need = targetIn.value === "group" || targetIn.value === "student";
      if (!need) {
        pickWrap.replaceChildren(h("span", { class: "muted tiny" },
          targetIn.value === "class"
            ? "Охват — весь класс на момент проведения, отмечать никого не нужно."
            : "Мероприятие для взрослых: число участников укажете при отметке о проведении."));
        return;
      }
      var preset = {};
      ((activity && activity.participants) || []).forEach(function (p) { preset[p.student_id] = true; });
      (src.student_ids || []).forEach(function (id) { preset[id] = true; });
      picks = (dash.students || []).filter(function (s) { return s.is_active; }).map(function (s) {
        var cb = h("input", { type: "checkbox" });
        cb.checked = !!preset[s.id];
        return { id: s.id, cb: cb, row: h("label", { class: "check" }, cb, s.full_name) };
      });
      pickWrap.replaceChildren(h("div", { class: "stack", style: { gap: "2px" } },
        picks.map(function (p) { return p.row; })));
    }
    targetIn.addEventListener("change", renderPicks);
    renderPicks();

    var err = h("div");
    var close;
    function save() {
      var title = titleIn.value.trim();
      if (!title) { err.replaceChildren(alertBox("error", "Укажите название")); return; }
      var ids = null;
      if (targetIn.value === "group" || targetIn.value === "student") {
        ids = picks.filter(function (p) { return p.cb.checked; }).map(function (p) { return p.id; });
        if (!ids.length) { err.replaceChildren(alertBox("error", "Выберите хотя бы одного ученика")); return; }
      }
      var payload = {
        title: title, kind: kindIn.value, target: targetIn.value,
        goal: goalIn.value.trim(), plan: planIn.value.trim(),
        planned_on: dateIn.value, duration_min: Number(durIn.value) || null,
        student_ids: ids,
      };
      if (!activity && survey) payload.source_survey_id = survey.id;
      var p = activity
        ? API.put("/api/prevention/activities/" + activity.id, payload)
        : API.post("/api/prevention/classes/" + classId + "/activities", payload);
      return p.then(function () { close(); if (onDone) onDone(); })
       .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }

    close = openModal(activity ? "Мероприятие" : "Новое мероприятие",
      [err, field("Название", titleIn),
       h("div", { class: "two-col" }, field("Вид", kindIn), field("Для кого", targetIn)),
       h("div", { class: "two-col" }, field("Дата", dateIn), field("Длительность, мин", durIn)),
       field("Цель", goalIn),
       field("Ход занятия", planIn),
       h("div", { class: "section-title", style: { marginTop: "6px" } }, "Участники"),
       pickWrap],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
       asyncBtn({ class: "btn btn-primary", onClick: save }, "Сохранить")], true);
  }

  function completeModal(activity, onDone) {
    var dateIn = h("input", { class: "input", type: "date", value: new Date().toISOString().slice(0, 10) });
    var outIn = h("textarea", { class: "textarea", placeholder: "Что получилось, как реагировал класс" });
    var effIn = h("select", { class: "select" }, h("option", { value: "" }, "не оценивать"));
    var EFF = ["1 — не сработало", "2 — слабый результат", "3 — умеренный",
               "4 — заметный результат", "5 — задача решена"];
    EFF.forEach(function (label, i) { effIn.appendChild(h("option", { value: String(i + 1) }, label)); });
    var adultsIn = h("input", { class: "input", type: "number", min: "0",
      value: activity.adults_count || "" });
    var err = h("div");

    // Для взрослых охват — числом: поимённо родителей мы не заводим.
    var isAdults = activity.target === "adults";
    var picks = [];
    var pickWrap = h("div");
    if (!isAdults) {
      var pool = activity.participants.length
        ? activity.participants.map(function (p) { return { id: p.student_id, full_name: p.full_name }; })
        : (dash.students || []).filter(function (s) { return s.is_active; });
      picks = pool.map(function (s) {
        var cb = h("input", { type: "checkbox" });
        cb.checked = true;
        return { id: s.id, cb: cb, row: h("label", { class: "check" }, cb, s.full_name) };
      });
      pickWrap.replaceChildren(
        picks.length
          ? h("div", { class: "stack", style: { gap: "2px" } }, picks.map(function (p) { return p.row; }))
          : h("span", { class: "muted tiny" }, "Охват — весь класс на момент проведения."));
    }

    var close;
    function save() {
      var payload = {
        conducted_on: dateIn.value,
        outcome: outIn.value.trim(),
        effectiveness: effIn.value ? Number(effIn.value) : null,
      };
      if (isAdults) payload.adults_count = Number(adultsIn.value) || 0;
      else if (picks.length) payload.attended_ids = picks.filter(function (p) { return p.cb.checked; })
        .map(function (p) { return p.id; });
      return API.post("/api/prevention/activities/" + activity.id + "/complete", payload)
        .then(function () { close(); onDone(); })
        .catch(function (e) { err.replaceChildren(alertBox("error", e.message)); });
    }

    close = openModal("Проведено — " + activity.title,
      [err, field("Дата проведения", dateIn),
       isAdults ? field("Сколько участников", adultsIn) : null,
       field("Что получилось", outIn),
       field("Ваша оценка результата", effIn),
       isAdults ? null : h("div", {},
         h("div", { class: "section-title", style: { marginTop: "6px" } }, "Кто присутствовал"),
         h("p", { class: "muted tiny", style: { marginBottom: "6px" } },
           "Снимите отметку с тех, кого не было. Охват считается по фактически присутствовавшим."),
         pickWrap)],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
       asyncBtn({ class: "btn btn-primary", onClick: save }, "Сохранить")], true);
  }

  function effectModal(activity) {
    var wrap = h("div", spinner());
    var close = openModal("Эффект — " + activity.title, [wrap],
      [h("button", { class: "btn btn-primary", onClick: function () { close(); } }, "Закрыть")], true);

    API.get("/api/prevention/activities/" + activity.id + "/effect").then(function (d) {
      if (!d.available) { wrap.replaceChildren(alertBox("info", d.reason)); return; }

      function block(title, s) {
        if (!s) return h("div", { class: "muted tiny" }, title + ": нет данных");
        return h("div", { class: "card card-pad" },
          h("div", { class: "section-title" }, title + " (" + s.students + ")"),
          h("div", { class: "tiles" },
            tile("Входящие связи", (s.avg_in_delta > 0 ? "+" : "") + s.avg_in_delta, "в среднем"),
            tile("Взаимные", (s.avg_mutual_delta > 0 ? "+" : "") + s.avg_mutual_delta, "в среднем"),
            tile("Вышли из изоляции", s.left_isolation),
            tile("Стали изолятами", s.became_isolate)));
      }

      var rows = d.details.map(function (r) {
        return h("tr", { class: "clickable", onClick: function () { close(); go("/student/" + r.student_id); } },
          h("td", {}, r.full_name),
          h("td", { class: "num" }, r.in_before), h("td", { class: "num" }, r.in_after),
          h("td", { class: "num" }, deltaSpan(r.in_delta)),
          h("td", {}, r.was_isolate && !r.is_isolate
            ? h("span", { class: "badge badge-green" }, "вышел из изоляции")
            : !r.was_isolate && r.is_isolate
              ? h("span", { class: "badge badge-red" }, "стал изолятом")
              : h("span", { class: "muted" }, "—")));
      });

      wrap.replaceChildren(h("div", {},
        h("div", { class: "muted tiny", style: { marginBottom: "12px" } },
          "Сравнение срезов «" + d.before.title + "» (" + fmtDate(d.before.conducted_on) + ") и «"
          + d.after.title + "» (" + fmtDate(d.after.conducted_on) + ")"),
        h("div", { class: "two-col", style: { gap: "12px" } },
          block("Охваченные мероприятием", d.covered),
          block("Остальной класс", d.rest_of_class)),
        // Честная оговорка: без неё цифры читались бы как доказательство.
        h("div", { style: { marginTop: "12px" } }, alertBox("info", d.disclaimer)),
        d.details.length ? h("div", { class: "table-wrap", style: { marginTop: "var(--s3)" } },
          h("table", { class: "table" },
            h("thead", {}, h("tr", {}, h("th", {}, "Ученик"), h("th", { class: "num" }, "Вх. до"),
              h("th", { class: "num" }, "Вх. после"), h("th", { class: "num" }, "Δ"), h("th", {}, "Изменение"))),
            h("tbody", {}, rows))) : null));
    }).catch(function (e) { wrap.replaceChildren(alertBox("error", e.message)); });
  }

  /* ================================================ ЖУРНАЛ ДОСТУПА */
  // Журнал, который нельзя прочитать, бесполезен: смысл в том, чтобы ответить
  // на вопрос проверки «кто и когда открывал данные этого ребёнка».
  function renderAudit() {
    stopNetwork();
    mount(shell(spinner()));
    var days = 30;
    function load() {
      API.get("/api/audit?days=" + days)
        .then(function (d) { mount(shell(view(d))); })
        .catch(function (e) { mount(shell(alertBox("error", e.message))); });
    }
    function view(d) {
      var sel = h("select", { class: "select", style: { width: "auto" },
        onChange: function (e) { days = Number(e.target.value); load(); } },
        h("option", { value: "7" }, "7 дней"),
        h("option", { value: "30" }, "30 дней"),
        h("option", { value: "90" }, "90 дней"),
        h("option", { value: "365" }, "год"));
      sel.value = String(days);

      var body = d.entries.length
        ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, h("th", {}, "Когда"), h("th", {}, "Кто"),
              h("th", {}, "Действие"), h("th", {}, "Объект"), h("th", {}, "IP"))),
            h("tbody", {}, d.entries.map(function (e) {
              return h("tr", {},
                h("td", { class: "muted tiny" }, fmtDateTime(e.at)),
                h("td", {}, e.who),
                h("td", {}, e.action_title),
                h("td", {}, e.target_name),
                h("td", { class: "muted tiny mono" }, e.ip || "—"));
            }))))
        : emptyState("Записей нет", "За выбранный период никто не открывал персональные данные.");

      return h("div", {},
        h("div", { class: "page-head" },
          h("div", { style: { flex: "1", minWidth: "200px" } },
            h("h1", { style: { fontSize: "22px" } }, "Журнал доступа"),
            h("div", { class: "muted tiny" }, "Кто и когда открывал персональные данные учеников вашей школы")),
          sel),
        h("div", { class: "card card-pad" }, body));
    }
    load();
  }

  /* ======================================================= АККАУНТ */
  function accountModal() {
    var cur = h("input", { class: "input", type: "password" });
    var next = h("input", { class: "input", type: "password", placeholder: "минимум 8 символов" });
    var msg = h("div");
    var close;
    function save() {
      msg.replaceChildren();
      if (next.value.length < 8) { msg.replaceChildren(alertBox("error", "Новый пароль — минимум 8 символов")); return; }
      return API.post("/api/auth/password", { current_password: cur.value, new_password: next.value })
        .then(function (d) {
          localStorage.setItem("izolyat.token", d.token);
          close();
          alert("Пароль изменён. Остальные сессии завершены.");
        })
        .catch(function (e) { msg.replaceChildren(alertBox("error", e.message)); });
    }
    close = openModal("Аккаунт",
      [h("div", { class: "muted tiny", style: { marginBottom: "10px" } },
        state.user.email + (state.user.school_name ? " · " + state.user.school_name : "") + " · " + (ROLE_LABEL[role()] || "")),
       h("div", { class: "section-title" }, "Смена пароля"),
       h("p", { class: "muted tiny", style: { marginBottom: "8px" } },
         "После смены пароля все остальные входы завершаются, в том числе на школьном компьютере."),
       msg, field("Текущий пароль", cur), field("Новый пароль", next)],
      [h("button", { class: "btn", onClick: function () { close(); } }, "Отмена"),
       asyncBtn({ class: "btn btn-primary", onClick: save }, "Сменить пароль")]);
  }

  // Скачивание файла идёт обычной ссылкой, а не fetch, поэтому токен нельзя
  // положить в заголовок — передаём его в query. Эндпоинты экспорта принимают
  // оба способа.
  function tokenQuery() {
    var t = localStorage.getItem("izolyat.token");
    return t ? "?token=" + encodeURIComponent(t) : "";
  }

  function router() {
    var parts = (location.hash.slice(1) || "/").split("/").filter(Boolean);
    if (!state.user) { renderLogin(); return; }

    if (parts[0] === "student" && parts[1]) { renderStudent(Number(parts[1])); return; }
    if (parts[0] === "class" && parts[1]) { setClass(Number(parts[1])); return; }
    if (parts[0] === "alerts") { renderAlerts(); return; }
    if (parts[0] === "prevention") { renderPrevention(); return; }
    if (parts[0] === "school") { renderSchool(); return; }
    if (parts[0] === "staff") { renderStaff(); return; }
    if (parts[0] === "audit") { renderAudit(); return; }

    // Завуч классов не ведёт — его домашний экран это сводка по школе.
    if (!canCasework() && canSchool()) { renderSchool(); return; }
    renderHome();
  }
  window.addEventListener("hashchange", router);

  /* ============================================================== boot */
  // Тему применяем до первой отрисовки, иначе при выбранной тёмной
  // мелькнёт светлый фон.
  applyTheme(currentTheme());
  mount(spinner());
  var token = localStorage.getItem("izolyat.token");
  (token ? API.get("/api/auth/me").then(function (d) { state.user = d.user; state.features = d.features || {}; }).catch(function () { state.user = null; }) : Promise.resolve())
    .then(refreshUnseen)
    .then(function () { router(); });
})();
