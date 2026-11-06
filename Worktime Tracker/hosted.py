"""Gunicorn factory for the explicitly selected public, temporary demo."""

import os
from pathlib import Path

from app import ROOT, initialize
from worktime.store import Store
from worktime.web import Application


def create_app():
    origin = os.environ.get("WORKTIME_PUBLIC_ORIGIN") or os.environ.get("RENDER_EXTERNAL_URL")
    if not origin:
        raise RuntimeError("Для онлайн-демо задайте WORKTIME_PUBLIC_ORIGIN или RENDER_EXTERNAL_URL")
    path = Path(os.environ.get("WORKTIME_DB_PATH", str(ROOT / "data" / "hosted-demo.sqlite3")))
    store = Store(path)
    application = Application(store, public_origin=origin, demo_mode=True)
    initialize(store, demo=True)
    return application
