"use strict";
const $ = id => document.getElementById(id);
const state = {user: null, people: [], today: null, selected: null, serverTime: 0, syncedAt: 0, view: "timer", editable: false, generation: 0};
const format = seconds => {
  const value = Math.max(0, Math.floor(seconds || 0));
  return [Math.floor(value / 3600), Math.floor(value / 60) % 60, value % 60].map(n => String(n).padStart(2, "0")).join(":");
};
const utcDate = value => new Date(value * 1000).toLocaleString("ru-RU", {timeZone: "UTC", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
const today = () => new Date().toISOString().slice(0, 10);
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function syncTime(value) { if (value) { state.serverTime = value; state.syncedAt = performance.now(); } }
function serverNow() { return state.serverTime + (performance.now() - state.syncedAt) / 1000; }
async function api(path, body) {
  const generation = state.generation;
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-Requested-With": "worktime"}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/login" && generation === state.generation) showLogin();
    const error = new Error(data.error || "Не удалось выполнить запрос");
    error.status = response.status;
    throw error;
  }
  if (generation === state.generation) syncTime(data.server_time);
  return data;
}
let noticeTimeout;
function notify(message) { $("notice").textContent = message; $("notice").hidden = false; clearTimeout(noticeTimeout); noticeTimeout = setTimeout(() => { $("notice").hidden = true; }, 5500); }
function showLogin() {
  state.user = null; state.people = []; state.today = null; state.selected = null; state.generation++;
  ["recent-rows", "employee-totals", "entry-rows", "page-rows", "people-list", "summary-grid", "report-stats", "time-bars", "employee", "report-employee"].forEach(id => $(id).replaceChildren());
  ["tracking-key", "description", "password", "person-name", "person-login", "person-password"].forEach(id => { $(id).value = ""; });
  ["account-name", "role", "running-description", "person-error", "report-error", "people-count"].forEach(id => { $(id).textContent = ""; });
  $("elapsed").textContent = "00:00:00";
  window.worktimeSummary = undefined;
  window.dispatchEvent(new CustomEvent("worktime:summary", {detail: undefined}));
  $("login-screen").hidden = false; $("workspace").hidden = true;
}
function showView(view) {
  if (view === "people" && state.user?.role !== "admin") return;
  state.view = view;
  for (const name of ["timer", "report", "people"]) $(name + "-view").hidden = name !== view;
  document.querySelectorAll("nav [data-view]").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  if (view === "report") loadReport().catch(error => { $("report-error").textContent = error.message; });
}
async function enter(user) {
  state.generation++;
  state.user = user;
  $("password").value = "";
  $("login-screen").hidden = true;
  $("workspace").hidden = false;
  $("account-name").textContent = user.name;
  $("role").textContent = user.role === "admin" ? "Администратор" : "Сотрудник";
  document.querySelectorAll(".admin-only").forEach(node => { node.hidden = user.role !== "admin"; });
  $("people-view").hidden = true;
  const date = today();
  $("from").value = date.slice(0, 8) + "01";
  $("to").value = date;
  $("today-label").textContent = new Date().toLocaleDateString("ru-RU", {timeZone: "UTC", day: "numeric", month: "long", year: "numeric"});
  await refresh();
  showView("timer");
}
function fillSelect(select, people, all = false) {
  const previous = select.value;
  select.replaceChildren();
  if (all) { const option = element("option", "", "Все сотрудники"); option.value = ""; select.append(option); }
  people.forEach(person => { const option = element("option", "", person.name); option.value = person.id; select.append(option); });
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
async function refresh() {
  const generation = state.generation;
  const result = await api("/api/employees");
  if (!state.user || generation !== state.generation) return;
  state.people = result.employees;
  fillSelect($("employee"), state.people);
  fillSelect($("report-employee"), state.people, state.user.role === "admin");
  state.selected = Number($("employee").value) || null;
  renderTimer();
  renderPeople();
  const date = today();
  const report = await api(`/api/report?start=${date}&end=${date}`);
  if (!state.user || generation !== state.generation) return;
  state.today = report;
  renderSummary();
  renderEntries($("recent-rows"), state.today.entries.slice(0, 5), true);
}
function selectedPerson() { return state.people.find(person => person.id === state.selected); }
function renderTimer() {
  const person = selectedPerson();
  const running = person?.active;
  $("employee").disabled = !state.people.length;
  $("description").disabled = !!running || !person;
  $("start").hidden = !!running;
  $("start").disabled = !person;
  $("stop").hidden = !running;
  $("timer-state").textContent = running ? "В работе" : "Остановлен";
  $("timer-state").classList.toggle("live", !!running);
  $("elapsed").classList.toggle("running", !!running);
  $("running-description").textContent = running?.description || (!person ? "Добавьте первого сотрудника в разделе «Сотрудники»" : "Готовы к следующей задаче");
  $("tracking-key").value = person?.tracking_key || "";
  $("copy-key").disabled = !person;
  $("extension-address").textContent = location.origin;
  tick();
}
function tick() {
  const running = selectedPerson()?.active;
  $("elapsed").textContent = running ? format(serverNow() - running.started_at) : "00:00:00";
}
const WIDGETS = [
  {id: "total", label: "Общее время задач", field: "total_seconds", meta: "Включает простой и время без наблюдения", wide: true},
  {id: "browser", label: "На страницах", field: "page_seconds", meta: "Активная вкладка браузера"},
  {id: "running", label: "Сейчас в работе", meta: "Сотрудников с запущенной задачей"},
];
let widgetOrder;
try { widgetOrder = JSON.parse(localStorage.getItem("worktime-layout") || "null"); } catch (_) { widgetOrder = null; }
if (!Array.isArray(widgetOrder) || widgetOrder.length !== 3 || new Set(widgetOrder).size !== 3 || widgetOrder.some(id => !WIDGETS.some(w => w.id === id))) widgetOrder = WIDGETS.map(w => w.id);
function renderSummary() {
  const report = state.today;
  if (!report) return;
  const summary = {report, running: state.people.filter(p => p.active).length, people: state.people.length, order: widgetOrder, editable: state.editable};
  window.worktimeSummary = summary;
  window.dispatchEvent(new CustomEvent("worktime:summary", {detail: summary}));
  const grid = $("summary-grid");
  grid.replaceChildren();
  widgetOrder.forEach(id => {
    const widget = WIDGETS.find(w => w.id === id);
    const card = element("section", "summary-widget");
    card.setAttribute("role", "listitem"); card.dataset.id = id;
    card.draggable = state.editable; card.tabIndex = state.editable ? 0 : -1;
    card.setAttribute("aria-label", widget.label + (state.editable ? ". Alt и стрелки для перемещения" : ""));
    card.append(element("span", "widget-label", widget.label), element("strong", "widget-value", widget.field ? format(report[widget.field]) : summary.running + " / " + summary.people), element("span", "widget-meta", widget.meta));
    card.addEventListener("dragstart", event => { event.dataTransfer.setData("text/plain", id); card.classList.add("dragging"); });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
    card.addEventListener("dragover", event => { if (state.editable) event.preventDefault(); });
    card.addEventListener("drop", event => { event.preventDefault(); if (state.editable) moveWidget(event.dataTransfer.getData("text/plain"), id); });
    card.addEventListener("keydown", event => {
      if (!state.editable || !event.altKey || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const index = widgetOrder.indexOf(id), delta = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
      const target = widgetOrder[index + delta];
      if (target) { moveWidget(id, target); grid.querySelector(`[data-id="${id}"]`)?.focus(); }
    });
    grid.append(card);
  });
  const definitions = [["Страницы", "page_seconds"], ["Простой / блокировка", "idle_seconds"], ["Вне отслеживаемых страниц", "away_seconds"], ["Без наблюдения", "unobserved_seconds"]];
  $("time-bars").replaceChildren();
  definitions.forEach(([label, field]) => {
    const row = element("div", "time-bar"), names = element("div", "bar-label"), track = element("div", "bar-track"), fill = element("span", "bar-fill");
    names.append(element("span", "", label), element("span", "", format(report[field])));
    fill.style.width = (report.total_seconds ? Math.min(100, report[field] / report.total_seconds * 100) : 0) + "%";
    track.append(fill); row.append(names, track); $("time-bars").append(row);
  });
}
function moveWidget(id, target) {
  const from = widgetOrder.indexOf(id), to = widgetOrder.indexOf(target);
  if (from < 0 || to < 0 || from === to) return;
  widgetOrder.splice(from, 1); widgetOrder.splice(to, 0, id);
  localStorage.setItem("worktime-layout", JSON.stringify(widgetOrder)); renderSummary();
}
function empty(tbody, columns, message) {
  const row = element("tr"), cell = element("td", "empty", message); cell.colSpan = columns; row.append(cell); tbody.append(row);
}
function renderEntries(tbody, entries, recent = false) {
  tbody.replaceChildren();
  if (!entries.length) { empty(tbody, 4, "За этот период записей пока нет"); return; }
  entries.forEach(entry => {
    const row = element("tr"), task = element("td");
    task.append(element("span", "table-primary", entry.description), element("span", "table-secondary", entry.employee_name));
    row.append(task, element("td", "", utcDate(entry.started_at)));
    if (recent) {
      const cell = element("td"); cell.append(element("span", "badge" + (entry.ended_at === null ? " live" : ""), entry.ended_at === null ? "В работе" : "Завершена")); row.append(cell);
    } else row.append(element("td", "", entry.ended_at === null ? "В работе" : utcDate(entry.ended_at)));
    row.append(element("td", "number", format(entry.total_seconds))); tbody.append(row);
  });
}
function renderPeople() {
  $("people-count").textContent = "В команде: " + state.people.length;
  $("people-list").replaceChildren();
  if (!state.people.length) $("people-list").append(element("p", "empty", "Добавьте первого сотрудника"));
  state.people.forEach(person => {
    const row = element("div", "person-row"), details = element("div");
    const initials = person.name.split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase();
    details.append(element("p", "person-name", person.name), element("p", "subtle", person.active?.description || "Нет активной задачи"));
    row.append(element("span", "avatar", initials), details, element("span", "badge" + (person.active ? " live" : ""), person.active ? "В работе" : "Остановлен"));
    $("people-list").append(row);
  });
}
async function loadReport() {
  const generation = state.generation;
  $("report-error").textContent = "";
  if ($("from").value > $("to").value) throw new Error("Дата начала не может быть позже даты окончания");
  const params = new URLSearchParams({start: $("from").value, end: $("to").value});
  if ($("report-employee").value) params.set("employee_id", $("report-employee").value);
  const result = await api("/api/report?" + params);
  if (!state.user || generation !== state.generation) return;
  $("report-stats").replaceChildren();
  [["Общее время", "total_seconds"], ["Страницы", "page_seconds"], ["Простой", "idle_seconds"], ["Вне страниц", "away_seconds"], ["Без наблюдения", "unobserved_seconds"]].forEach(([label, field]) => {
    const card = element("div", "report-stat"); card.append(element("span", "", label), element("strong", "", format(result[field]))); $("report-stats").append(card);
  });
  const totals = $("employee-totals"); totals.replaceChildren();
  result.employees.forEach(person => {
    const row = element("tr"); row.append(element("td", "", person.name));
    ["total_seconds", "page_seconds", "idle_seconds", "away_seconds", "unobserved_seconds"].forEach(field => row.append(element("td", "number", format(person[field])))); totals.append(row);
  });
  if (!result.employees.length) empty(totals, 6, "Сотрудников пока нет");
  renderEntries($("entry-rows"), result.entries);
  $("page-rows").replaceChildren();
  result.pages.forEach(page => {
    const row = element("tr"), cell = element("td"), link = element("a", "table-primary", page.title || page.domain);
    link.href = page.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    cell.append(link, element("span", "table-secondary", page.url));
    const person = state.people.find(p => p.id === page.employee_id);
    row.append(cell, element("td", "", person?.name || "—"), element("td", "", page.category), element("td", "number", format(page.seconds))); $("page-rows").append(row);
  });
  if (!result.pages.length) empty($("page-rows"), 4, "Нет наблюдений браузера за выбранный период");
}
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
$("login-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; $("login-error").textContent = "";
  try { const result = await api("/api/login", {login: $("login").value, password: $("password").value}); loadWidgets(result.widgets_available); await enter(result.user); }
  catch (error) { $("login-error").textContent = error.message; } finally { button.disabled = false; }
});
$("logout").addEventListener("click", async () => { try { await api("/api/logout", {}); showLogin(); } catch (error) { notify(error.message); } });
$("employee").addEventListener("change", () => { state.selected = Number($("employee").value); renderTimer(); });
$("timer-form").addEventListener("submit", async event => {
  event.preventDefault(); $("start").disabled = true;
  try { await api("/api/sessions", {employee_id: state.selected, description: $("description").value}); $("description").value = ""; await refresh(); notify("Задача начата"); }
  catch (error) { notify(error.message); } finally { $("start").disabled = !selectedPerson(); }
});
$("stop").addEventListener("click", async () => {
  const running = selectedPerson()?.active; if (!running) return; $("stop").disabled = true;
  try { await api(`/api/sessions/${running.id}/stop`, {}); await refresh(); notify("Задача завершена. Время сохранено."); }
  catch (error) { notify(error.message); } finally { $("stop").disabled = false; }
});
$("report-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try { await loadReport(); } catch (error) { $("report-error").textContent = error.message; } finally { button.disabled = false; }
});
$("person-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; $("person-error").textContent = "";
  try { await api("/api/employees", {name: $("person-name").value, login: $("person-login").value, password: $("person-password").value}); $("person-form").reset(); await refresh(); notify("Сотрудник добавлен и может войти в приложение"); }
  catch (error) { $("person-error").textContent = error.message; } finally { button.disabled = false; }
});
$("copy-key").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("tracking-key").value); notify("Код скопирован"); }
  catch (_) { $("tracking-key").focus(); $("tracking-key").select(); notify("Код выделен. Скопируйте его вручную."); }
});
$("theme").addEventListener("click", () => { const dark = !document.documentElement.classList.contains("dark"); document.documentElement.classList.toggle("dark", dark); localStorage.setItem("worktime-theme", dark ? "dark" : "light"); });
$("edit-layout").addEventListener("click", () => { state.editable = !state.editable; $("edit-layout").setAttribute("aria-pressed", String(state.editable)); $("edit-layout").textContent = state.editable ? "Готово" : "Настроить виджеты"; renderSummary(); });
const savedTheme = localStorage.getItem("worktime-theme");
document.documentElement.classList.toggle("dark", savedTheme === "dark" || (!savedTheme && matchMedia("(prefers-color-scheme: dark)").matches));
setInterval(tick, 1000);
let refreshing = false;
setInterval(async () => { if (!state.user || document.hidden || refreshing) return; refreshing = true; try { await refresh(); if (state.view === "report") await loadReport(); } catch (error) { if (error.status !== 401) notify("Не удалось обновить данные. " + error.message); } finally { refreshing = false; } }, 15000);
let widgetsLoaded = false;
function loadWidgets(available) {
  if (!available || widgetsLoaded) return;
  widgetsLoaded = true;
  import("/widgets.js").catch(() => { widgetsLoaded = false; notify("React-виджеты не загрузились. Используется обычная сетка."); });
}
const startupGeneration = state.generation;
api("/api/me").then(result => {
  if (startupGeneration !== state.generation) return;
  loadWidgets(result.widgets_available); return enter(result.user);
}).catch(error => {
  if (startupGeneration !== state.generation) return;
  showLogin(); if (error.status !== 401) $("login-error").textContent = error.message;
});
