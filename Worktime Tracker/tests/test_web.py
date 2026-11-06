import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from wsgiref.util import setup_testing_defaults

from worktime.store import Store

try:
    from worktime.auth import Auth
    from worktime.web import Application
except ModuleNotFoundError:
    Application = None


class WebTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Application, "Вход и HTTP API ещё не реализованы")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1793966400.0
        self.store = Store(Path(self.tmp.name) / "test.db", clock=lambda: self.now)
        self.auth = Auth(self.store)
        self.admin = self.auth.add_user("Администратор Демо", "admin", "admin-demo-2026", "admin")
        self.anna = self.auth.add_user("Анна Примерова", "anna", "anna-demo-2026", "employee")
        self.oleg = self.auth.add_user("Олег Вымышленный", "oleg", "oleg-demo-2026", "employee")
        self.app = Application(self.store)

    def request(self, path, method="GET", body=None, cookie="", **headers):
        env = {}
        setup_testing_defaults(env)
        url = urlsplit(path)
        data = json.dumps(body).encode() if body is not None else b""
        env.update(REQUEST_METHOD=method, PATH_INFO=url.path, QUERY_STRING=url.query,
                   CONTENT_TYPE="application/json", CONTENT_LENGTH=str(len(data)),
                   HTTP_HOST="127.0.0.1:8765", HTTP_COOKIE=cookie,
                   HTTP_X_REQUESTED_WITH="worktime", **{"wsgi.input": io.BytesIO(data)})
        env.update(headers)
        response = {}
        def start(status, response_headers):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(response_headers)
        content = b"".join(self.app(env, start))
        response["body"] = json.loads(content) if response["headers"].get("Content-Type", "").startswith("application/json") else content
        return response

    def login(self, login="admin", password="admin-demo-2026"):
        result = self.request("/api/login", "POST", {"login": login, "password": password})
        self.assertEqual(result["status"], 200)
        return result["headers"]["Set-Cookie"].split(";", 1)[0]

    def test_without_login_data_is_not_available(self):
        self.assertEqual(self.request("/api/employees")["status"], 401)

    def test_wrong_password_is_rejected(self):
        result = self.request("/api/login", "POST", {"login": "admin", "password": "incorrect"})
        self.assertEqual(result["status"], 401)

    def test_login_sets_httponly_cookie(self):
        result = self.request("/api/login", "POST", {"login": "admin", "password": "admin-demo-2026"})
        self.assertIn("HttpOnly", result["headers"]["Set-Cookie"])
        self.assertIn("SameSite=Strict", result["headers"]["Set-Cookie"])

    def test_employee_only_sees_self(self):
        cookie = self.login("anna", "anna-demo-2026")
        result = self.request("/api/employees", cookie=cookie)
        self.assertEqual([p["name"] for p in result["body"]["employees"]], ["Анна Примерова"])

    def test_employee_cannot_create_employee(self):
        cookie = self.login("anna", "anna-demo-2026")
        result = self.request("/api/employees", "POST", {"name": "Новый", "login": "new", "password": "example-123"}, cookie)
        self.assertEqual(result["status"], 403)

    def test_admin_creates_employee_who_can_log_in(self):
        result = self.request("/api/employees", "POST", {"name": "Ирина Тестовая", "login": "irina", "password": "irina-demo-2026"}, self.login())
        self.assertEqual(result["status"], 201)
        result = self.request("/api/me", cookie=self.login("irina", "irina-demo-2026"))
        self.assertEqual(result["body"]["user"]["role"], "employee")

    def test_duplicate_login_does_not_leave_orphan_employee(self):
        cookie = self.login()
        result = self.request("/api/employees", "POST", {"name": "Дубликат", "login": "anna", "password": "example-123"}, cookie)
        self.assertEqual(result["status"], 409)
        self.assertEqual(len(self.store.employees()), 2)

    def test_employee_cannot_start_for_someone_else(self):
        result = self.request("/api/sessions", "POST", {"employee_id": self.oleg["employee_id"], "description": "Чужая задача"}, self.login("anna", "anna-demo-2026"))
        self.assertEqual(result["status"], 403)

    def test_employee_cannot_stop_someone_elses_timer(self):
        session = self.store.start(self.oleg["employee_id"], "Задача Олега")
        result = self.request(f"/api/sessions/{session['id']}/stop", "POST", {}, self.login("anna", "anna-demo-2026"))
        self.assertEqual(result["status"], 403)
        self.assertIsNone(self.store.session(session["id"])["ended_at"])

    def test_employee_cannot_request_another_employee_report(self):
        result = self.request(f"/api/report?start=2026-11-06&end=2026-11-06&employee_id={self.oleg['employee_id']}", cookie=self.login("anna", "anna-demo-2026"))
        self.assertEqual(result["status"], 403)

    def test_employee_default_report_is_filtered(self):
        self.store.start(self.oleg["employee_id"], "Чужая задача")
        self.now += 60
        result = self.request("/api/report?start=2026-11-06&end=2026-11-06", cookie=self.login("anna", "anna-demo-2026"))
        self.assertEqual(result["body"]["entries"], [])
        self.assertEqual(len(result["body"]["employees"]), 1)

    def test_logout_invalidates_cookie(self):
        cookie = self.login()
        self.request("/api/logout", "POST", {}, cookie)
        self.assertEqual(self.request("/api/me", cookie=cookie)["status"], 401)

    def test_session_expires(self):
        cookie = self.login()
        self.now += 12 * 3600 + 1
        self.assertEqual(self.request("/api/me", cookie=cookie)["status"], 401)

    def test_login_survives_application_restart(self):
        cookie = self.login()
        self.app = Application(self.store)
        self.assertEqual(self.request("/api/me", cookie=cookie)["status"], 200)

    def test_cross_origin_mutation_is_rejected(self):
        result = self.request("/api/login", "POST", {"login": "admin", "password": "admin-demo-2026"}, HTTP_ORIGIN="https://example.org")
        self.assertEqual(result["status"], 403)

    def test_host_rebinding_is_rejected(self):
        self.assertEqual(self.request("/api/me", HTTP_HOST="evil.example:8765")["status"], 403)

    def test_tracker_needs_key_and_does_not_need_browser_cookie(self):
        self.assertEqual(self.request("/api/tracker/state")["status"], 401)
        key = self.store.employees(self.anna["employee_id"])[0]["tracking_key"]
        result = self.request("/api/tracker/state", HTTP_AUTHORIZATION="Bearer " + key)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["body"]["employee"]["name"], "Анна Примерова")

    def test_posting_non_object_json_is_rejected(self):
        self.assertEqual(self.request("/api/login", "POST", [1, 2])["status"], 400)

    def test_password_is_not_returned(self):
        result = self.request("/api/me", cookie=self.login())
        self.assertNotIn("password", json.dumps(result["body"]))

    def test_interface_is_served_with_security_headers(self):
        result = self.request("/")
        self.assertEqual(result["status"], 200)
        self.assertIn("Content-Security-Policy", result["headers"])

    def test_full_employee_flow_with_extension_and_restart(self):
        cookie = self.login("anna", "anna-demo-2026")
        created = self.request("/api/sessions", "POST", {
            "employee_id": self.anna["employee_id"], "description": "Тестовая задача",
        }, cookie)
        self.assertEqual(created["status"], 201)
        session_id = created["body"]["session"]["id"]
        key = self.store.employees(self.anna["employee_id"])[0]["tracking_key"]
        tracker = self.request("/api/tracker/state", HTTP_AUTHORIZATION="Bearer " + key)
        self.assertEqual(tracker["body"]["session"]["id"], session_id)
        self.now += 30
        activity = self.request("/api/tracker/activity", "POST", {
            "session_id": session_id, "event_id": "integration-test",
            "started_at": self.now - 30, "ended_at": self.now,
            "kind": "page", "url": "https://example.org/demo?private=removed",
            "title": "Вымышленная страница",
        }, HTTP_AUTHORIZATION="Bearer " + key)
        self.assertEqual(activity["status"], 200)
        self.assertTrue(activity["body"]["accepted"])
        self.now += 30
        self.assertEqual(self.request(f"/api/sessions/{session_id}/stop", "POST", {}, cookie)["status"], 200)
        self.app = Application(Store(self.store.path, clock=lambda: self.now))
        report = self.request("/api/report?start=2026-11-06&end=2026-11-06", cookie=cookie)
        self.assertEqual(report["body"]["total_seconds"], 60)
        self.assertEqual(report["body"]["page_seconds"], 30)
        self.assertEqual(report["body"]["unobserved_seconds"], 30)
        self.assertEqual(report["body"]["pages"][0]["url"], "https://example.org/demo")

    def test_repeated_start_over_http_returns_conflict(self):
        cookie = self.login("anna", "anna-demo-2026")
        body = {"employee_id": self.anna["employee_id"], "description": "Тест"}
        self.assertEqual(self.request("/api/sessions", "POST", body, cookie)["status"], 201)
        self.assertEqual(self.request("/api/sessions", "POST", body, cookie)["status"], 409)

    def test_broken_json_is_a_client_error(self):
        result = self.request("/api/login", "POST", CONTENT_LENGTH="1", **{"wsgi.input": io.BytesIO(b"{")})
        self.assertEqual(result["status"], 400)


if __name__ == "__main__":
    unittest.main()
