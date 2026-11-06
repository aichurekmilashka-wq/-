#!/usr/bin/env python3
"""Run: python3 app.py --demo"""

import argparse
import getpass
import logging
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from worktime.auth import Auth
from worktime.store import Problem, Store
from worktime.web import Application

ROOT = Path(__file__).resolve().parent


class LocalServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def initialize(store, demo=False):
    auth = Auth(store)
    if auth.has_users():
        return
    if demo:
        auth.add_user("Администратор Демо", "admin", "admin-demo-2026", "admin")
        anna = auth.add_user("Анна Примерова", "anna", "anna-demo-2026")
        oleg = auth.add_user("Олег Вымышленный", "oleg", "oleg-demo-2026")
        now = store.clock()
        with store.db() as db:
            db.execute("INSERT INTO sessions(employee_id, description, started_at, ended_at) VALUES (?, ?, ?, ?)",
                       (anna["employee_id"], "Пример: подготовка презентации", now - 5400, now - 2700))
            db.execute("INSERT INTO sessions(employee_id, description, started_at, ended_at) VALUES (?, ?, ?, ?)",
                       (oleg["employee_id"], "Пример: проверка макета", now - 3600, now - 1800))
        print("Созданы вымышленные демоаккаунты. Логины и пароли — в README.md.")
    else:
        print("Первый запуск: создайте администратора.")
        login = input("Логин (латиницей): ").strip()
        password = getpass.getpass("Пароль (от 8 символов): ")
        if password != getpass.getpass("Повторите пароль: "):
            raise Problem("Пароли не совпадают")
        auth.add_user("Администратор", login, password, "admin")


def main():
    parser = argparse.ArgumentParser(description="Локальный учёт рабочего времени")
    parser.add_argument("--demo", action="store_true", help="создать вымышленные данные при первом запуске")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "worktime.sqlite3")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("порт должен быть от 1024 до 65535")
    store = Store(args.db)
    try:
        initialize(store, args.demo)
        with make_server("127.0.0.1", args.port, Application(store), server_class=LocalServer) as server:
            print(f"Worktime: http://127.0.0.1:{args.port} — Ctrl+C для остановки", flush=True)
            server.serve_forever()
    except Problem as error:
        parser.exit(1, f"Ошибка: {error}\n")
    except OSError as error:
        parser.exit(1, f"Не удалось запустить сервер: {error}. Попробуйте другой --port.\n")
    except KeyboardInterrupt:
        print("\nПриложение остановлено. Данные сохранены.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
