"""A log of the database columns each request reads.

Each request's connection gets an authorizer, and SQLite calls it once for each column a
statement reads as the statement is prepared. The rows come back as `Row`, and a `Row` notes
each column the code asks it for. After the response, the site appends one JSON line to the
log with the route, the address, the status and both sets:

    {"at": "...", "endpoint": "listing", "remote": "100.111.61.78", "status": 200,
     "queried": ["listings.ask", ...], "used": ["ask", ...]}

`queried` holds every table.column a statement named, so `SELECT *` lists the whole table.
`used` holds the result columns the code or a template read, by name or by position. A column
counts as read by a route when both sets have it. Some reads count more than they use:
  - iterating a row, or `dict(row)`, marks every column of that row;
  - a row kept in a per-build cache counts only for the request that filled the cache.
So `used` errs toward keeping a column, and a column missing from it went unread.

The site writes the log to SITE_READS_LOG, by default reads.jsonl in the site root, and leaves
it off when SITE_READS_LOG is 0. The log has no rotation: it grows by a line for each page
request that touches the database, and we delete it once the measurement ends.
"""

from __future__ import annotations

import contextvars
import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path

_used: contextvars.ContextVar[set | None] = contextvars.ContextVar(
    "used_columns", default=None
)


class Row(sqlite3.Row):
    """sqlite3.Row that notes each column read by name during a logged request."""

    def __getitem__(self, key):
        seen = _used.get()
        if seen is not None:
            if isinstance(key, str):
                seen.add(key)
            elif isinstance(key, int):
                seen.add(self.keys()[key])
            elif isinstance(key, slice):
                seen.update(self.keys()[key])
        return super().__getitem__(key)

    def __iter__(self):
        seen = _used.get()
        if seen is not None:
            seen.update(self.keys())
        return super().__iter__()


class ReadLog:
    def __init__(self, path: Path | None):
        self.path = path
        self.lock = threading.Lock()
        self.row = Row if path is not None else sqlite3.Row

    @classmethod
    def from_env(cls, root: Path, value: str | None) -> ReadLog:
        if value == "0":
            return cls(None)
        return cls(Path(value) if value else root / "reads.jsonl")

    def start(self) -> tuple[set, contextvars.Token] | None:
        if self.path is None:
            return None
        used: set = set()
        return used, _used.set(used)

    def watch(self, connection: sqlite3.Connection, queried: set) -> None:
        """Record every table.column a statement on this connection reads."""

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and table and column:
                queried.add(f"{table}.{column}")
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)

    def finish(self, state, *, endpoint, remote, status, queried: set) -> None:
        if state is None:
            return
        used, token = state
        _used.reset(token)
        if not queried and not used:
            return
        line = json.dumps(
            {
                "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "endpoint": endpoint,
                "remote": remote,
                "status": status,
                "queried": sorted(queried),
                "used": sorted(used),
            }
        )
        try:
            with self.lock, self.path.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass  # the log is a measurement; a full disk must not fail the page
