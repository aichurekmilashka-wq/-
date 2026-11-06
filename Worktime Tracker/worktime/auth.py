"""Password authentication and persistent, revocable login sessions."""

import hashlib
import hmac
import re
import secrets
import sqlite3

from .store import Problem, text

ITERATIONS = 260_000
SESSION_SECONDS = 12 * 3600


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row):
    return {key: row[key] for key in ("id", "name", "login", "role", "employee_id")}


class Auth:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    login TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'employee')),
                    employee_id INTEGER UNIQUE REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS logins (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at REAL NOT NULL
                );
            """)

    def has_users(self):
        with self.store.db() as db:
            return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def add_user(self, name, login, password, role="employee"):
        name = text(name, "Имя", 100)
        login = text(login, "Логин", 32).lower()
        if not re.fullmatch(r"[a-z][a-z0-9._-]{2,31}", login):
            raise Problem("Логин: 3–32 латинских символа, цифры, точка, дефис; начинается с буквы")
        if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
            raise Problem("Пароль: от 8 до 128 символов")
        if role not in ("admin", "employee"):
            raise Problem("Неизвестная роль")
        salt = secrets.token_hex(16)
        encoded = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
        try:
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                employee_id = None
                if role == "employee":
                    employee_id = db.execute("INSERT INTO employees(name, tracking_key) VALUES (?, ?)",
                                             (name, secrets.token_urlsafe(32))).lastrowid
                user_id = db.execute("""
                    INSERT INTO users(name, login, password_hash, salt, role, employee_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, login, encoded, salt, role, employee_id)).lastrowid
                row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        except sqlite3.IntegrityError:
            raise Problem("Этот логин уже занят", 409) from None
        return public_user(row)

    def login(self, login, password):
        login = text(login, "Логин", 32).lower()
        if not isinstance(password, str) or len(password) > 128:
            raise Problem("Неверный логин или пароль", 401)
        with self.store.db() as db:
            row = db.execute("SELECT * FROM users WHERE login=?", (login,)).fetchone()
        salt = bytes.fromhex(row["salt"]) if row else bytes(16)
        encoded = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()
        if row is None or not hmac.compare_digest(row["password_hash"], encoded):
            raise Problem("Неверный логин или пароль", 401)
        token = secrets.token_urlsafe(32)
        with self.store.db() as db:
            db.execute("DELETE FROM logins WHERE expires_at <= ?", (self.store.clock(),))
            db.execute("INSERT INTO logins VALUES (?, ?, ?)",
                       (digest(token), row["id"], self.store.clock() + SESSION_SECONDS))
        return token, public_user(row)

    def resolve(self, token):
        if not token or len(token) > 200:
            raise Problem("Войдите в приложение", 401)
        with self.store.db() as db:
            row = db.execute("""
                SELECT u.* FROM users u JOIN logins l ON u.id=l.user_id
                WHERE l.token_hash=? AND l.expires_at > ?
            """, (digest(token), self.store.clock())).fetchone()
        if row is None:
            raise Problem("Сессия завершена. Войдите снова", 401)
        return public_user(row)

    def logout(self, token):
        with self.store.db() as db:
            db.execute("DELETE FROM logins WHERE token_hash=?", (digest(token),))
