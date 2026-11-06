#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -v
if command -v node >/dev/null 2>&1; then
  node tests/extension.test.js
  node tests/interface.test.js
  node scripts/syntax-check.js
elif [ -x /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc ]; then
  worktime_jsc=/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc
  "$worktime_jsc" tests/extension.test.js
  "$worktime_jsc" tests/interface.test.js
  "$worktime_jsc" scripts/syntax-check.js
else
  echo 'Для JavaScript-проверок установите Node.js 20.19+.' >&2
  exit 1
fi
