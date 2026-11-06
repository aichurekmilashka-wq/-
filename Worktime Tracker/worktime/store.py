"""SQLite persistence and time accounting; all timestamps are UTC seconds."""

import math
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise Problem(f"{label}: от 1 до {limit} символов")
    return value.strip()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Problem("Некорректное время события")
    return float(value)


def period(start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last:
            raise ValueError
        lower = datetime.combine(first, day_time(), timezone.utc).timestamp()
        upper = datetime.combine(last + timedelta(days=1), day_time(), timezone.utc).timestamp()
        return lower, upper
    except (TypeError, ValueError, OverflowError):
        raise Problem("Укажите корректный период: начало не позже окончания") from None


def clean_url(value):
    try:
        parts = urlsplit(text(value, "Адрес страницы", 4096))
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        netloc = host + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, netloc, parts.path[:1024] or "/", "", ""))
    except ValueError:
        raise Problem("Допустимы только адреса http и https") from None


def category(url):
    host = urlsplit(url).hostname or ""
    groups = {
        "Документы": ("docs.google.com", "notion.so", "notion.site"),
        "Разработка": ("github.com", "stackoverflow.com", "developer.mozilla.org"),
        "Видео": ("youtube.com", "youtu.be", "vimeo.com"),
    }
    for label, domains in groups.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return label
    return "Другие"


class Store:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    tracking_key TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    employee_id INTEGER NOT NULL REFERENCES employees(id),
                    description TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    CHECK (ended_at IS NULL OR ended_at >= started_at)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_running_timer
                    ON sessions(employee_id) WHERE ended_at IS NULL;
                CREATE TABLE IF NOT EXISTS activity (
                    session_id INTEGER NOT NULL REFERENCES sessions(id),
                    event_id TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('page', 'idle', 'away')),
                    url TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (session_id, event_id),
                    CHECK (ended_at > started_at)
                );
            """)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def employees(self, employee_id=None):
        with self.db() as db:
            rows = db.execute("SELECT * FROM employees WHERE (? IS NULL OR id=?) ORDER BY id",
                              (employee_id, employee_id)).fetchall()
        return [dict(row) for row in rows]

    def add_employee(self, name):
        name = text(name, "Имя сотрудника", 100)
        with self.db() as db:
            cursor = db.execute("INSERT INTO employees(name, tracking_key) VALUES (?, ?)",
                                (name, secrets.token_urlsafe(32)))
            employee_id = cursor.lastrowid
        return self.employees(employee_id)[0]

    def active(self, employee_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE employee_id=? AND ended_at IS NULL",
                             (employee_id,)).fetchone()
        return dict(row) if row else None

    def session(self, session_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise Problem("Запись не найдена", 404)
        return dict(row)

    def start(self, employee_id, description):
        description = text(description, "Описание задачи", 500)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT id FROM employees WHERE id=?", (employee_id,)).fetchone():
                raise Problem("Сотрудник не найден", 404)
            try:
                cursor = db.execute(
                    "INSERT INTO sessions(employee_id, description, started_at) VALUES (?, ?, ?)",
                    (employee_id, description, self.clock()))
            except sqlite3.IntegrityError:
                raise Problem("У сотрудника уже запущен таймер. Сначала остановите его.", 409) from None
            session_id = cursor.lastrowid
        return self.session(session_id)

    def stop(self, session_id):
        with self.db() as db:
            db.execute("UPDATE sessions SET ended_at=MAX(started_at, ?) WHERE id=? AND ended_at IS NULL",
                       (self.clock(), session_id))
        return self.session(session_id)

    def tracker_state(self, key):
        with self.db() as db:
            row = db.execute("SELECT * FROM employees WHERE tracking_key=?", (key,)).fetchone()
        if row is None:
            raise Problem("Неверный код подключения расширения", 401)
        return {"employee": {"id": row["id"], "name": row["name"]},
                "session": self.active(row["id"]), "server_time": self.clock()}

    def record_activity(self, key, event):
        person = self.tracker_state(key)["employee"]
        event_id = text(event.get("event_id"), "Идентификатор события", 100)
        session_id = event.get("session_id")
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise Problem("Некорректная задача")
        session = self.session(session_id)
        if session["employee_id"] != person["id"]:
            raise Problem("Эта задача принадлежит другому сотруднику", 403)
        begin, end = number(event.get("started_at")), number(event.get("ended_at"))
        if not 0 < end - begin <= 90 or end > self.clock() + 5:
            raise Problem("Интервал должен быть от 0 до 90 секунд и не находиться в будущем")
        kind = event.get("kind")
        if kind not in ("page", "idle", "away"):
            raise Problem("Неизвестный тип активности")
        url = clean_url(event.get("url")) if kind == "page" else ""
        title = event.get("title", "")
        if not isinstance(title, str):
            raise Problem("Некорректное название страницы")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM activity WHERE session_id=? AND event_id=?",
                          (session_id, event_id)).fetchone():
                return {"accepted": False, "duplicate": True}
            # Re-read inside the transaction: stop() may have run concurrently.
            current = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            last = db.execute("SELECT MAX(ended_at) FROM activity WHERE session_id=?", (session_id,)).fetchone()[0]
            begin = max(begin, current["started_at"], last or current["started_at"])
            end = min(end, current["ended_at"] if current["ended_at"] is not None else self.clock())
            if end <= begin:
                return {"accepted": False, "duplicate": False}
            db.execute("INSERT INTO activity VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (session_id, event_id, begin, end, kind, url, title.strip()[:200]))
        return {"accepted": True, "duplicate": False}

    def report(self, start, end, employee_id=None):
        lower, upper = period(start, end)
        now = self.clock()
        upper = min(upper, now)
        with self.db() as db:
            rows = db.execute("""
                SELECT s.*, e.name AS employee_name FROM sessions s
                JOIN employees e ON e.id=s.employee_id
                WHERE s.started_at < ? AND COALESCE(s.ended_at, ?) > ?
                AND (? IS NULL OR s.employee_id=?)
                ORDER BY s.started_at DESC, s.id DESC
            """, (upper, now, lower, employee_id, employee_id)).fetchall()
            events = db.execute("""
                SELECT a.*, s.employee_id FROM activity a
                JOIN sessions s ON s.id=a.session_id
                WHERE a.started_at < ? AND a.ended_at > ?
                AND (? IS NULL OR s.employee_id=?) ORDER BY a.ended_at
            """, (upper, lower, employee_id, employee_id)).fetchall()
        people = {p["id"]: {"id": p["id"], "name": p["name"], "total_seconds": 0,
                             "page_seconds": 0, "idle_seconds": 0, "away_seconds": 0,
                             "unobserved_seconds": 0} for p in self.employees(employee_id)}
        entries, by_session = [], {}
        for row in rows:
            entry = dict(row)
            entry.update(total_seconds=max(0, min(row["ended_at"] or now, upper) - max(row["started_at"], lower)),
                         page_seconds=0, idle_seconds=0, away_seconds=0)
            by_session[entry["id"]] = entry
            entries.append(entry)
        pages = {}
        for event in events:
            entry = by_session.get(event["session_id"])
            if entry is None:
                continue
            session_end = entry["ended_at"] if entry["ended_at"] is not None else now
            seconds = max(0, min(event["ended_at"], upper, session_end)
                          - max(event["started_at"], lower, entry["started_at"]))
            entry[event["kind"] + "_seconds"] += seconds
            if event["kind"] == "page":
                key = (event["employee_id"], event["url"])
                page = pages.setdefault(key, {"employee_id": event["employee_id"], "url": event["url"],
                    "title": event["title"], "domain": urlsplit(event["url"]).hostname,
                    "category": category(event["url"]), "seconds": 0})
                page["seconds"] += seconds
                if event["title"]:
                    page["title"] = event["title"]
        fields = ("total_seconds", "page_seconds", "idle_seconds", "away_seconds", "unobserved_seconds")
        for entry in entries:
            entry["unobserved_seconds"] = max(0, entry["total_seconds"] - sum(entry[k] for k in fields[1:4]))
            for field in fields:
                people[entry["employee_id"]][field] += entry[field]
        result = {field: sum(p[field] for p in people.values()) for field in fields}
        result.update(start=start, end=end, employees=list(people.values()), entries=entries,
                      pages=sorted(pages.values(), key=lambda page: -page["seconds"]), server_time=now)
        return result
