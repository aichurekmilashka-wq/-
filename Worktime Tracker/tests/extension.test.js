/* Run with node tests/extension.test.js or jsc tests/extension.test.js. */
if (typeof require === "function") {
  try { require("../extension/core.js"); } catch (error) { if (error.code !== "MODULE_NOT_FOUND") throw error; }
} else {
  try { load("extension/core.js"); } catch (_) { /* First TDD run: module is absent. */ }
}
const log = typeof print === "function" ? print : console.log;
let failures = 0;
let passed = 0;
function equal(actual, expected) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error("Expected " + JSON.stringify(expected) + ", got " + JSON.stringify(actual));
  }
}
function test(name, run) {
  try { run(); passed++; log("PASS " + name); }
  catch (error) { failures++; log("FAIL " + name + ": " + error.message); }
}
const tab = {url: "https://example.org/research?token=secret#part", title: "Исследование", incognito: false};
test("active foreground tab is a page", () => {
  equal(WorktimeCore.classify("active", true, tab), {kind: "page", url: "https://example.org/research", title: "Исследование"});
});
test("background browser is away", () => equal(WorktimeCore.classify("active", false, tab), {kind: "away"}));
test("idle is separate from page time", () => equal(WorktimeCore.classify("idle", true, tab), {kind: "idle"}));
test("locked machine is idle", () => equal(WorktimeCore.classify("locked", true, tab), {kind: "idle"}));
test("incognito is not recorded", () => equal(WorktimeCore.classify("active", true, {...tab, incognito: true}), {kind: "away"}));
test("internal browser pages are not recorded", () => equal(WorktimeCore.classify("active", true, {url: "chrome://settings"}), {kind: "away"}));
test("credentials are removed from URL", () => equal(WorktimeCore.classify("active", true, {url: "https://user:pass@example.org/a?x=1"}).url, "https://example.org/a"));
const sample = {at: 100, session: {id: 7, started_at: 90}, state: {kind: "page", url: "https://example.org/", title: "Пример"}};
test("interval uses previous page until switching", () => equal(WorktimeCore.interval(sample, 130), {
  session_id: 7, started_at: 100, ended_at: 130, kind: "page", url: "https://example.org/", title: "Пример"
}));
test("sleep gap is left unobserved", () => equal(WorktimeCore.interval(sample, 250), null));
test("backward clock does not produce negative time", () => equal(WorktimeCore.interval(sample, 99), null));
test("without a running task there is no observation", () => equal(WorktimeCore.interval({...sample, session: null}, 130), null));
test("first observation does not invent past activity", () => equal(WorktimeCore.interval(null, 130), null));
test("interval clips to task start", () => equal(WorktimeCore.interval({...sample, session: {id: 8, started_at: 110}}, 130).started_at, 110));
test("known stopped task clips to stop time", () => equal(WorktimeCore.interval({...sample, session: {id: 7, started_at: 90, ended_at: 120}}, 130).ended_at, 120));
test("old sample stays attached to old task", () => equal(WorktimeCore.interval(sample, 130).session_id, 7));
log(`${passed} passed, ${failures} failed`);
if (failures) throw new Error("Extension tests failed");
