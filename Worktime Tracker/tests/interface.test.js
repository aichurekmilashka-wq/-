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
document.getElementById('running-description').textContent = 'Задача предыдущего пользователя';
document.getElementById('person-password').value = 'unfinished-employee-password';
document.getElementById('account-name').textContent = 'Предыдущий администратор';
document.getElementById('employee').textContent = 'Чужой список сотрудников';
window.worktimeSummary = {report: {total_seconds: 300}};
showLogin();
check('logout removes old report from the DOM', document.getElementById('page-rows').textContent, '');
check('logout clears the previous tracking key', document.getElementById('tracking-key').value, '');
check('logout clears the previous employee list', document.getElementById('people-list').textContent, '');
check('logout clears the React summary', window.worktimeSummary, undefined);
check('logout hides the workspace', document.getElementById('workspace').hidden, true);
check('logout shows the login screen', document.getElementById('login-screen').hidden, false);
check('logout clears the running task description', document.getElementById('running-description').textContent, '');
check('logout clears an unfinished employee password', document.getElementById('person-password').value, '');
check('logout clears the previous account name', document.getElementById('account-name').textContent, '');
check('logout clears employee selector contents', document.getElementById('employee').textContent, '');
// A request from the old login must not clear a newer user's workspace.
let finishOldRequest;
globalThis.fetch = () => new Promise(resolve => {finishOldRequest = resolve;});
const staleRequest = api('/api/me').catch(() => {});
showLogin();
document.getElementById('workspace').hidden = false;
document.getElementById('login-screen').hidden = true;
document.getElementById('tracking-key').value = 'new-login-key';
finishOldRequest({ok: false, status: 401, json: () => Promise.resolve({error: 'Old session expired'})});
function finishInterfaceTests() {
  check('old 401 does not hide a new workspace', document.getElementById('workspace').hidden, false);
  check('old 401 does not clear a new tracking key', document.getElementById('tracking-key').value, 'new-login-key');
  check('old 401 does not reopen the login screen', document.getElementById('login-screen').hidden, true);
  if (uiFailures) throw new Error(uiFailures + ' interface tests failed');
}
if (typeof drainMicrotasks === 'function') {drainMicrotasks(); finishInterfaceTests();}
else staleRequest.then(finishInterfaceTests);
