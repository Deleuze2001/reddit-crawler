from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import Settings, get_settings


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@contextmanager
def connection(
    settings: Settings | None = None,
    *,
    autocommit: bool = True,
) -> Iterator[psycopg.Connection]:
    resolved = settings or get_settings()
    if not resolved.database_url:
        raise RuntimeError("DATABASE_URL must be set before the app can connect to PostgreSQL.")
    conn = psycopg.connect(
        resolved.database_url,
        autocommit=autocommit,
        row_factory=dict_row,
    )
    try:
        yield conn
    finally:
        conn.close()


def wait_for_database(settings: Settings | None = None, timeout_seconds: float = 60.0) -> None:
    resolved = settings or get_settings()
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with connection(resolved) as conn:
                conn.execute("SELECT 1")
            return
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(1.0)

    raise RuntimeError(f"database did not become ready within {timeout_seconds:.0f}s") from last_error


def run_migrations(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    wait_for_database(resolved)
    with connection(resolved) as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
