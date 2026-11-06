"""Exercise the real hosted HTTP server after building its Docker image."""

import argparse
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--public-origin", required=True)
    args = parser.parse_args()
    host = urlsplit(args.public_origin).netloc

    def call(path, body=None, cookie=""):
        headers = {"Host": host, "Origin": args.public_origin, "X-Requested-With": "worktime"}
        if cookie:
            headers["Cookie"] = cookie
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = Request(args.base_url.rstrip("/") + path, data=data, headers=headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            value = json.loads(content) if response.headers.get_content_type() == "application/json" else content
            return response.status, value, response.headers.get("Set-Cookie", "")

    deadline = time.monotonic() + 60
    while True:
        try:
            status, data, _cookie = call("/healthz")
            assert status == 200 and data == {"ok": True}
            break
        except (OSError, URLError, AssertionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)

    status, page, _ = call("/")
    assert status == 200 and "После перезапуска сервера".encode() in page
    status, bundle, _ = call("/widgets.js")
    assert status == 200 and len(bundle) > 1000, "React bundle must be present"
    status, data, raw_cookie = call("/api/login", {"login": "admin", "password": "admin-demo-2026"})
    assert status == 200 and "; Secure" in raw_cookie
    admin_cookie = "worktime_session=" + SimpleCookie(raw_cookie)["worktime_session"].value
    login = "check_" + uuid.uuid4().hex[:8]
    password = "fictional-check-2026"
    status, person, _ = call("/api/employees", {"name": "Проверочный Сотрудник", "login": login, "password": password}, admin_cookie)
    assert status == 201
    employee_id = person["employee"]["id"]
    status, data, raw_cookie = call("/api/login", {"login": login, "password": password})
    assert status == 200 and data["user"]["role"] == "employee"
    employee_cookie = "worktime_session=" + SimpleCookie(raw_cookie)["worktime_session"].value
    task = {"employee_id": employee_id, "description": "Вымышленная проверочная задача"}
    status, data, _ = call("/api/sessions", task, employee_cookie)
    assert status == 201
    session_id = data["session"]["id"]
    assert call("/api/sessions", task, employee_cookie)[0] == 409
    assert call(f"/api/sessions/{session_id}/stop", {}, employee_cookie)[0] == 200
    day = datetime.now(timezone.utc).date()
    period = f"start={day - timedelta(days=1)}&end={day + timedelta(days=1)}"
    status, report, _ = call("/api/report?" + period, cookie=employee_cookie)
    assert status == 200 and len(report["employees"]) == 1
    assert report["entries"][0]["description"] == task["description"]
    assert report["entries"][0]["ended_at"] is not None
    assert call("/api/logout", {}, employee_cookie)[0] == 200
    assert call("/api/me", cookie=employee_cookie)[0] == 401
    print("Hosted HTTP smoke passed: HTTPS settings, React bundle, login, employee, timer, report, logout")


if __name__ == "__main__":
    main()
