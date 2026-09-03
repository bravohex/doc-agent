"""SQLite connection lifecycle and transaction helper."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class SqliteDatabase:
    """Open parameterized SQLite connections with foreign keys enabled."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Yield a read connection and always close it after use."""

        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        from doc_agent.adapters.sqlite.migrations import SCHEMA

        connection = sqlite3.connect(self.path)
        try:
            connection.executescript(SCHEMA)
            connection.commit()
        finally:
            connection.close()
