const byId = id => document.getElementById(id);
async function refresh(fillConfig = false) {
  const {config, status} = await chrome.storage.local.get(["config", "status"]);
  if (config && fillConfig) {
    byId("server").value = config.baseUrl;
    byId("key").value = config.key;
  }
  byId("status").textContent = status?.message || "Настройте подключение";
  byId("details").textContent = [status?.employee, status?.task,
    status?.at ? "Проверено в " + new Date(status.at).toLocaleTimeString("ru-RU") : "",
    status?.queued ? "Ожидают отправки: " + status.queued : ""].filter(Boolean).join(" · ");
  byId("pause").disabled = !config?.enabled;
}
byId("setup").addEventListener("submit", async event => {
  event.preventDefault();
  byId("connect").disabled = true;
  byId("message").textContent = "Подключение…";
  try {
    const server = new URL(byId("server").value.trim());
    if (!WorktimeCore.isAllowedServer(server)) throw new Error("Укажите localhost или HTTPS-адрес на onrender.com");
    if (server.protocol === "https:") {
      const granted = await chrome.permissions.request({origins: [server.origin + "/*"]});
      if (!granted) throw new Error("Для подключения нужно разрешение на доступ к этому серверу");
    }
    const result = await chrome.runtime.sendMessage({type: "configure", config: {
      baseUrl: server.origin, key: byId("key").value.trim(), enabled: true,
    }});
    if (!result?.ok) throw new Error(result?.error || "Не удалось подключиться");
    byId("message").textContent = "Готово. Запустите задачу в приложении.";
    await refresh();
  } catch (error) {
    byId("message").textContent = error.message;
  } finally {
    byId("connect").disabled = false;
  }
});
byId("pause").addEventListener("click", async () => {
  try {
    const result = await chrome.runtime.sendMessage({type: "pause"});
    if (!result?.ok) throw new Error(result?.error || "Ошибка отключения");
    await refresh();
  } catch (error) { byId("message").textContent = error.message; }
});
chrome.storage.onChanged.addListener(changes => { if (changes.status) refresh(); });
refresh(true);
