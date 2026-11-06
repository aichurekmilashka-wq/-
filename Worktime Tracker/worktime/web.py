"""Small WSGI JSON API. Authorization lives here, never only in the UI."""

import json
import logging
import re
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .auth import Auth, SESSION_SECONDS
from .store import Problem

STATIC = Path(__file__).resolve().parent.parent / "static"
STATIC_FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
                "/widgets.js": ("widgets.js", "text/javascript"), "/widgets.css": ("widgets.css", "text/css")}


def integer(value, label="Идентификатор"):
    try:
        if isinstance(value, bool) or str(int(value)) != str(value) or not 1 <= int(value) <= 2**63 - 1:
            raise ValueError
        return int(value)
    except (ValueError, TypeError, OverflowError):
        raise Problem(f"{label}: нужно положительное целое число") from None


def cookie_token(environ):
    try:
        cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
        return cookies["worktime_session"].value if "worktime_session" in cookies else ""
    except CookieError:
        return ""


class Application:
    def __init__(self, store, public_origin=None, demo_mode=False):
        self.store = store
        self.auth = Auth(store)
        self.public_origin = None
        self.public_host = None
        self.demo_mode = demo_mode
        self.cookie_security = ""
        if public_origin:
            parsed = urlsplit(public_origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
                raise ValueError("Публичный адрес должен быть HTTPS-origin без пути и параметров")
            self.public_origin = "https://" + parsed.netloc.lower()
            self.public_host = parsed.netloc.lower()
            self.cookie_security = "; Secure"

    def __call__(self, environ, start_response):
        headers = [("X-Content-Type-Options", "nosniff"), ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")]
        try:
            status, data, extra = self.dispatch(environ)
            headers += extra
            if isinstance(data, bytes):
                payload = data
            else:
                payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
                headers.append(("Content-Type", "application/json; charset=utf-8"))
        except Problem as error:
            status = error.status
            payload = json.dumps({"error": str(error)}, ensure_ascii=False).encode()
            headers.append(("Content-Type", "application/json; charset=utf-8"))
        except Exception:
            logging.exception("Request failed")
            status = 500
            payload = '{"error":"Внутренняя ошибка сервера"}'.encode()
            headers.append(("Content-Type", "application/json; charset=utf-8"))
        headers.append(("Content-Length", str(len(payload))))
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [payload]

    def dispatch(self, env):
        host = env.get("HTTP_HOST", "")
        try:
            parts = urlsplit("http://" + host)
            permitted = parts.hostname in ("127.0.0.1", "localhost") or (self.public_host and parts.netloc.lower() == self.public_host)
            valid_host = permitted and not parts.username and not parts.path and not parts.query and not parts.fragment
        except ValueError:
            valid_host = False
        if not valid_host:
            raise Problem("Этот адрес сервера не разрешён", 403)
        path, method = env["PATH_INFO"], env["REQUEST_METHOD"]
        tracker = path.startswith("/api/tracker/")
        origin = env.get("HTTP_ORIGIN", "")
        extension_origin = re.fullmatch(r"chrome-extension://[a-p]{32}", origin or "")
        expected_origin = self.public_origin or "http://" + host
        if origin and origin != expected_origin and not (tracker and extension_origin):
            raise Problem("Запрос с постороннего сайта отклонён", 403)
        extra = []
        if tracker and extension_origin:
            extra = [("Access-Control-Allow-Origin", origin), ("Vary", "Origin"),
                     ("Access-Control-Allow-Headers", "Authorization, Content-Type"),
                     ("Access-Control-Allow-Methods", "GET, POST, OPTIONS")]
        if tracker and method == "OPTIONS":
            return 200, {}, extra
        if path == "/healthz" and method == "GET":
            return 200, {"ok": True}, []
        if path in STATIC_FILES and method == "GET":
            filename, mime = STATIC_FILES[path]
            if not (STATIC / filename).is_file():
                raise Problem("Этот дополнительный файл ещё не собран", 404)
            content = (STATIC / filename).read_bytes()
            if filename == "index.html" and self.demo_mode:
                content = content.replace(b'id="demo-banner" class="demo-banner" hidden', b'id="demo-banner" class="demo-banner"')
                content = content.replace("Локальное приложение · данные на вашем компьютере".encode(),
                                          "Онлайн-демо · только вымышленные данные".encode())
            return 200, content, [("Content-Type", mime + "; charset=utf-8")]
        if not path.startswith("/api/"):
            raise Problem("Страница не найдена", 404)
        body = {}
        if method == "POST":
            if not tracker and env.get("HTTP_X_REQUESTED_WITH") != "worktime":
                raise Problem("Отсутствует заголовок приложения", 403)
            if env.get("CONTENT_TYPE", "").split(";")[0] != "application/json":
                raise Problem("Ожидается JSON", 415)
            try:
                length = int(env.get("CONTENT_LENGTH") or 0)
                if not 0 < length <= 16384:
                    raise ValueError
                body = json.loads(env["wsgi.input"].read(length))
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                raise Problem("Некорректный JSON или размер запроса", 400) from None
        if tracker:
            authorization = env.get("HTTP_AUTHORIZATION", "")
            key = authorization[7:] if authorization.startswith("Bearer ") else ""
            if method == "GET" and path == "/api/tracker/state":
                return 200, self.store.tracker_state(key), extra
            if method == "POST" and path == "/api/tracker/activity":
                return 200, self.store.record_activity(key, body), extra
            raise Problem("Маршрут расширения не найден", 404)
        if path == "/api/login" and method == "POST":
            token, user = self.auth.login(body.get("login"), body.get("password"))
            cookie = f"worktime_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}" + self.cookie_security
            return 200, {"user": user, "server_time": self.store.clock(),
                         "widgets_available": (STATIC / "widgets.js").is_file()}, [("Set-Cookie", cookie)]
        token = cookie_token(env)
        user = self.auth.resolve(token)
        if path == "/api/me" and method == "GET":
            return 200, {"user": user, "server_time": self.store.clock(),
                         "widgets_available": (STATIC / "widgets.js").is_file()}, []
        if path == "/api/logout" and method == "POST":
            self.auth.logout(token)
            return 200, {"ok": True}, [("Set-Cookie", "worktime_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + self.cookie_security)]
        if path == "/api/employees":
            if method == "GET":
                people = self.store.employees(None if user["role"] == "admin" else user["employee_id"])
                for person in people:
                    person["active"] = self.store.active(person["id"])
                return 200, {"employees": people, "server_time": self.store.clock()}, []
            if method == "POST":
                if user["role"] != "admin":
                    raise Problem("Добавлять сотрудников может только администратор", 403)
                new_user = self.auth.add_user(body.get("name"), body.get("login"), body.get("password"))
                return 201, {"employee": self.store.employees(new_user["employee_id"])[0]}, []
        if path == "/api/sessions" and method == "POST":
            employee_id = integer(body.get("employee_id"))
            self.require_employee(user, employee_id)
            return 201, {"session": self.store.start(employee_id, body.get("description"))}, []
        match = re.fullmatch(r"/api/sessions/([1-9][0-9]*)/stop", path)
        if match and method == "POST":
            session_id = integer(match[1])
            session = self.store.session(session_id)
            self.require_employee(user, session["employee_id"])
            return 200, {"session": self.store.stop(session_id)}, []
        if path == "/api/report" and method == "GET":
            query = parse_qs(env.get("QUERY_STRING", ""))
            employee_id = integer(query["employee_id"][0]) if query.get("employee_id") else None
            if user["role"] == "employee":
                if employee_id is not None:
                    self.require_employee(user, employee_id)
                employee_id = user["employee_id"]
            return 200, self.store.report(query.get("start", [""])[0], query.get("end", [""])[0], employee_id), []
        raise Problem("Маршрут не найден", 404)

    @staticmethod
    def require_employee(user, employee_id):
        if user["role"] != "admin" and user["employee_id"] != employee_id:
            raise Problem("Нет доступа к данным другого сотрудника", 403)
