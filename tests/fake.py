"""Fake psycopg connection/cursor for unit tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any


class FakeCursor:
    def __init__(self, rows: list[tuple]):
        self._rows = rows
        self.last_query: str | None = None
        self.last_params: Any = None

    def execute(self, query: str, params: Any = None) -> None:
        self.last_query = query
        self.last_params = params

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class FakeConn:
    """Minimal fake psycopg connection.

    Pass a mapping of section names to canned rows, or a single row list
    if only one cursor is used.

    Usage::

        conn = FakeConn(rows=[("Acme", "ACM", date(2026,6,5), 3, 0, 3, 0, 0)])
    """

    def __init__(self, rows: list[tuple] | None = None):
        self._rows = rows or []
        self.cursors: list[FakeCursor] = []

    @contextmanager
    def cursor(self):
        cur = FakeCursor(self._rows)
        self.cursors.append(cur)
        yield cur

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass
