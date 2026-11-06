const syntaxFiles = ['static/app.js', 'extension/core.js', 'extension/background.js', 'extension/popup.js'];
const syntaxLog = typeof print === 'function' ? print : console.log;
for (const file of syntaxFiles) {
  if (typeof require === 'function') {
    new (require('node:vm').Script)(require('node:fs').readFileSync(file, 'utf8'), {filename: file});
  } else checkSyntax(file);
  syntaxLog('Syntax OK: ' + file);
}
