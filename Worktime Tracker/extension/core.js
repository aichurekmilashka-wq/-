/* Pure accounting rules, shared by the service worker and executable tests. */
globalThis.WorktimeCore = (() => {
  function classify(idle, focused, tab) {
    if (idle !== "active") return {kind: "idle"};
    if (!focused || !tab || tab.incognito) return {kind: "away"};
    const match = /^(https?:\/\/)([^/?#]+)([^?#]*)/i.exec(tab.url || "");
    if (!match) return {kind: "away"};
    const host = match[2].slice(match[2].lastIndexOf("@") + 1);
    return {kind: "page", url: match[1] + host + (match[3] || "/"), title: (tab.title || "").slice(0, 200)};
  }

  function interval(previous, at) {
    if (!previous?.session || !previous.state || at <= previous.at || at - previous.at > 90) return null;
    const begin = Math.max(previous.at, previous.session.started_at);
    const end = Math.min(at, previous.session.ended_at ?? at);
    if (end <= begin) return null;
    return {session_id: previous.session.id, started_at: begin, ended_at: end, ...previous.state};
  }

  function reconnectState(saved, config) {
    const pending = saved.pending || [];
    const same = saved.config?.baseUrl === config.baseUrl && saved.config?.key === config.key;
    if (!same && pending.length) {
      throw new Error("Остались неотправленные события другого подключения. Восстановите прежнее подключение и дождитесь отправки.");
    }
    return {pending: same ? pending : [], previous: same && saved.config.enabled ? saved.previous ?? null : null};
  }
  return {classify, interval, reconnectState};
})();
