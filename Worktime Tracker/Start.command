#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  print 'Установите Python 3.11 или новее: https://www.python.org/downloads/'
else
  print 'Откройте в браузере: http://127.0.0.1:8765'
  print 'Демо: admin / admin-demo-2026; anna / anna-demo-2026'
  python3 app.py --demo
fi
print '\nНажмите Enter, чтобы закрыть окно.'
read
