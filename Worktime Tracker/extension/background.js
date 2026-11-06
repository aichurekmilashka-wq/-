/* Classic Manifest V3 worker: alarms keep sampling across worker suspension. */
importScripts("core.js");
let serial = Promise.resolve();

async function request(config, path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(config.baseUrl + path, {
      method: body ? "POST" : "GET",
      headers: {Authorization: "Bearer " + config.key, ...(body ? {"Content-Type": "application/json"} : {})},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || "Ошибка подключения");
      error.status = response.status;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

async function observe() {
  const idle = await chrome.idle.queryState(300);
  if (idle !== "active") return {kind: "idle"};
  const window = await chrome.windows.getLastFocused({populate: true});
  return WorktimeCore.classify(idle, window.focused, window.tabs?.find(tab => tab.active));
}

async function sample() {
  const saved = await chrome.storage.local.get(["config", "previous", "pending"]);
  const config = saved.config;
  if (!config?.enabled) return;
  let state;
  try {
    state = await request(config, "/api/tracker/state");
  } catch (error) {
    // No server means no confirmed running task. Never extrapolate old activity.
    await chrome.storage.local.set({previous: null, status: {
      message: error.status === 401 ? "Неверный код подключения" : "Сервер недоступен. Наблюдение приостановлено.",
      ok: false, at: Date.now(), queued: (saved.pending || []).length,
    }});
    return;
  }
  const at = state.server_time;
  const interval = WorktimeCore.interval(saved.previous, at);
  const pending = saved.pending || [];
  if (interval) pending.push({...interval, event_id: crypto.randomUUID()});
  // A bounded queue cannot grow forever. Dropped intervals remain unobserved.
  if (pending.length > 240) pending.splice(0, pending.length - 240);
  const previous = state.session ? {at, session: state.session, state: await observe()} : null;
  await chrome.storage.local.set({previous, pending});
  let deliveryError = "";
  while (pending.length) {
    try {
      await request(config, "/api/tracker/activity", pending[0]);
      pending.shift();
      await chrome.storage.local.set({pending});
    } catch (error) {
      if ([400, 403, 404].includes(error.status)) {
        pending.shift();
        await chrome.storage.local.set({pending});
        deliveryError = "Один интервал отклонён. Он останется без наблюдения.";
        continue;
      }
      deliveryError = "Не удалось отправить данные. Повторим автоматически.";
      break;
    }
  }
  await chrome.storage.local.set({status: {
    ok: !deliveryError, message: deliveryError || (state.session ? "Учёт включён" : "Нет запущенной задачи"),
    employee: state.employee.name, task: state.session?.description || "", at: Date.now(), queued: pending.length,
  }});
}

function schedule() {
  serial = serial.then(sample).catch(async () => {
    await chrome.storage.local.set({previous: null, status: {ok: false, message: "Ошибка наблюдения. Повторим при следующем опросе.", at: Date.now()}});
  });
  return serial;
}

async function initialize() {
  chrome.idle.setDetectionInterval(300);
  if (!await chrome.alarms.get("worktime-sample")) {
    await chrome.alarms.create("worktime-sample", {periodInMinutes: 0.5});
  }
}

chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === "worktime-sample") schedule(); });
chrome.tabs.onActivated.addListener(schedule);
chrome.tabs.onUpdated.addListener((_id, changes) => { if (changes.url || changes.title) schedule(); });
chrome.tabs.onRemoved.addListener(schedule);
chrome.windows.onFocusChanged.addListener(schedule);
chrome.idle.onStateChanged.addListener(schedule);
chrome.runtime.onInstalled.addListener(() => initialize().then(schedule));
chrome.runtime.onStartup.addListener(() => {
  serial = serial.then(() => chrome.storage.local.set({previous: null})).then(initialize).then(sample);
});
chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message.type === "configure") {
    serial = serial.then(async () => {
      const config = message.config;
      const url = new URL(config.baseUrl);
      if (!WorktimeCore.isAllowedServer(url)) {
        throw new Error("Укажите локальный адрес или HTTPS-адрес демо на onrender.com");
      }
      config.baseUrl = url.origin;
      const state = await request(config, "/api/tracker/state");
      const saved = await chrome.storage.local.get(["config", "previous", "pending"]);
      const restored = WorktimeCore.reconnectState(saved, config);
      await chrome.storage.local.set({config, ...restored, status: {
        ok: true, message: "Подключено", employee: state.employee.name, at: Date.now(), queued: 0,
      }});
      await initialize();
      await sample();
      reply({ok: true});
    }).catch(error => reply({ok: false, error: error.message}));
    return true;
  }
  if (message.type === "pause") {
    serial = serial.then(async () => {
      await sample();
      const {config} = await chrome.storage.local.get("config");
      if (config) await chrome.storage.local.set({config: {...config, enabled: false}, previous: null,
        status: {ok: true, message: "Наблюдение выключено", at: Date.now()}});
      reply({ok: true});
    }).catch(error => reply({ok: false, error: error.message}));
    return true;
  }
});
initialize().catch(() => {});
