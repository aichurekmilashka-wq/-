import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

try:
    from hosted import create_app
except ModuleNotFoundError:
    create_app = None


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(create_app, "Запуск размещённого демо ещё не реализован")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "demo.sqlite3")
        with patch.dict(os.environ, {
            "WORKTIME_DB_PATH": self.db,
            "RENDER_EXTERNAL_URL": "https://worktime-test.onrender.com",
        }, clear=True):
            self.app = create_app()

    def request(self, path, body=None, host="worktime-test.onrender.com", origin=""):
        env = {}
        setup_testing_defaults(env)
        payload = json.dumps(body).encode() if body is not None else b""
        env.update(PATH_INFO=path, QUERY_STRING="", HTTP_HOST=host,
                   HTTP_ORIGIN=origin, REQUEST_METHOD="POST" if body is not None else "GET",
                   CONTENT_TYPE="application/json", CONTENT_LENGTH=str(len(payload)),
                   HTTP_X_REQUESTED_WITH="worktime", **{"wsgi.input": io.BytesIO(payload), "wsgi.url_scheme": "https"})
        result = {}
        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        result["content"] = b"".join(self.app(env, start))
        return result

    def test_hosted_login_uses_https_and_secure_cookie(self):
        result = self.request("/api/login", {"login": "admin", "password": "admin-demo-2026"},
                              origin="https://worktime-test.onrender.com")
        self.assertEqual(result["status"], 200)
        self.assertIn("; Secure", result["headers"]["Set-Cookie"])

    def test_hosted_demo_explains_shared_temporary_data(self):
        result = self.request("/")
        self.assertEqual(result["status"], 200)
        page = result["content"].decode()
        self.assertNotIn('id="demo-banner" class="demo-banner" hidden', page)
        self.assertIn("После перезапуска сервера", page)
        self.assertNotIn("Локальное приложение · данные на вашем компьютере", page)

    def test_hosted_api_rejects_foreign_host(self):
        self.assertEqual(self.request("/api/me", host="attacker.example")["status"], 403)

    def test_hosted_login_rejects_foreign_origin(self):
        result = self.request("/api/login", {"login": "admin", "password": "admin-demo-2026"}, origin="https://attacker.example")
        self.assertEqual(result["status"], 403)

    def test_health_check_does_not_require_a_login(self):
        result = self.request("/healthz", host="127.0.0.1:10000")
        self.assertEqual(result["status"], 200)
        self.assertEqual(json.loads(result["content"]), {"ok": True})

    def test_factory_restart_keeps_existing_database(self):
        self.app.auth.add_user("Ирина Тестовая", "irina", "irina-demo-2026")
        with patch.dict(os.environ, {"WORKTIME_DB_PATH": self.db, "RENDER_EXTERNAL_URL": "https://worktime-test.onrender.com"}, clear=True):
            restarted = create_app()
        self.assertEqual(len(restarted.store.employees()), 3)
        _token, user = restarted.auth.login("irina", "irina-demo-2026")
        self.assertEqual(user["name"], "Ирина Тестовая")

    def test_hosted_public_origin_requires_https(self):
        from worktime.web import Application
        with self.assertRaises(ValueError):
            Application(self.app.store, public_origin="http://worktime-test.onrender.com")


if __name__ == "__main__":
    unittest.main()
