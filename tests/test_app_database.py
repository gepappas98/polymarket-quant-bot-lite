from types import SimpleNamespace

from app.core import database


def test_configure_postgres_uses_native_engine_options(monkeypatch):
    captured = {}
    previous_engine = database.engine
    previous_session = database.SessionLocal
    previous_url = database.DATABASE_URL

    def fake_create_engine(url, future, **kwargs):
        captured.update(url=url, future=future, kwargs=kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    try:
        database.configure("postgresql+psycopg://user:password@db:5432/app")
        assert captured == {
            "url": "postgresql+psycopg://user:password@db:5432/app",
            "future": True,
            "kwargs": {},
        }
        assert database.DATABASE_URL.startswith("postgresql+")
        assert database.SessionLocal is not None
    finally:
        database.engine = previous_engine
        database.SessionLocal = previous_session
        database.DATABASE_URL = previous_url


def test_configure_sqlite_retains_thread_and_memory_options(monkeypatch):
    captured = {}
    previous_engine = database.engine
    previous_session = database.SessionLocal
    previous_url = database.DATABASE_URL

    def fake_create_engine(url, future, **kwargs):
        captured.update(url=url, future=future, kwargs=kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    try:
        database.configure("sqlite:///:memory:")
        assert captured["kwargs"]["connect_args"] == {"check_same_thread": False}
        assert captured["kwargs"]["poolclass"] is database.StaticPool
    finally:
        database.engine = previous_engine
        database.SessionLocal = previous_session
        database.DATABASE_URL = previous_url
