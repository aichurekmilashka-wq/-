/* Small DOM boundary double: runs the actual app script, without a browser. */
const domNodes = new Map();
function domNode() {
  return {value: '', textContent: '', hidden: false, classList: {toggle() {}, contains() {return false;}},
    addEventListener() {}, setAttribute() {}, replaceChildren() {this.textContent = '';},
    focus() {}, select() {}};
}
globalThis.document = {
  getElementById(id) {if (!domNodes.has(id)) domNodes.set(id, domNode()); return domNodes.get(id);},
  querySelectorAll() {return [];}, documentElement: domNode(),
};
globalThis.window = globalThis;
globalThis.localStorage = {getItem() {return null;}, setItem() {}};
globalThis.matchMedia = () => ({matches: false});
globalThis.setInterval = () => 0;
globalThis.fetch = () => new Promise(() => {});
globalThis.CustomEvent = function (type, options) {this.type = type; this.detail = options.detail;};
let lastSummary;
globalThis.dispatchEvent = event => {lastSummary = event.detail;};
if (typeof require === 'function') {
  require('node:vm').runInThisContext(require('node:fs').readFileSync('static/app.js', 'utf8'), {filename: 'static/app.js'});
} else load('static/app.js');
const say = typeof print === 'function' ? print : console.log;
let uiFailures = 0;
function check(name, actual, expected) {
  if (actual === expected) say('PASS ' + name);
  else {uiFailures++; say('FAIL ' + name + ': ' + actual + ' !== ' + expected);}
}
document.getElementById('page-rows').textContent = 'Чужие посещённые страницы';
document.getElementById('people-list').textContent = 'Предыдущая команда';
document.getElementById('tracking-key').value = 'previous-private-key';
window.worktimeSummary = {report: {total_seconds: 300}};
showLogin();
check('logout removes old report from the DOM', document.getElementById('page-rows').textContent, '');
check('logout clears the previous tracking key', document.getElementById('tracking-key').value, '');
check('logout clears the previous employee list', document.getElementById('people-list').textContent, '');
check('logout clears the React summary', window.worktimeSummary, undefined);
check('logout hides the workspace', document.getElementById('workspace').hidden, true);
check('logout shows the login screen', document.getElementById('login-screen').hidden, false);
if (uiFailures) throw new Error(uiFailures + ' interface tests failed');
