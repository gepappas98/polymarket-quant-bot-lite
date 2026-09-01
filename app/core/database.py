import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("APP_DATABASE_URL", "sqlite:///data/app.db")
Base = declarative_base()
engine = None
SessionLocal = None


def configure(url: str):
    global DATABASE_URL, engine, SessionLocal
    DATABASE_URL = url
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url in ("sqlite:///:memory:", "sqlite://"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, future=True, **kwargs)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine


configure(DATABASE_URL)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _literal_default(column):
    default = column.default
    if default is None or not default.is_scalar:
        return None
    value = default.arg
    if callable(value):
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _add_missing_columns():
    if not DATABASE_URL.startswith("sqlite"):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        dialect = engine.dialect
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name not in tables:
                    continue
                existing = {c["name"] for c in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing:
                        continue
                    ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(dialect=dialect)}"
                    default = _literal_default(column)
                    if default is not None:
                        ddl += f" DEFAULT {default}"
                    conn.execute(text(ddl))
        return
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(dialect=engine.dialect)}"
                default = _literal_default(column)
                if default is not None:
                    ddl += f" DEFAULT {default}"
                conn.execute(text(ddl))


def init_db():
    import app.models  # noqa: F401
    if DATABASE_URL.startswith("sqlite:///"):
        raw_path = DATABASE_URL.removeprefix("sqlite:///")
        if raw_path != ":memory:":
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _add_missing_columns()
