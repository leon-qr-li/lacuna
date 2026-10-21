"""The site database: one SQLite file, ``<root>/lacuna.db`` (decision 2026-10-21-sqlite-site-data).

Holds what the whole site shares and the admin pages will query: accounts, sessions, invites, settings,
shows and their members, plans, access requests and the event log. Episode files (transcripts, edits,
renders) stay plain files in each show's folder.

One connection per file for the process (``at(root)``), used under one lock; every change is a transaction.
Each table keeps the record as JSON (``data``) next to the columns worth querying, so the code that owns a
record keeps working with plain dicts.

Backups: the nightly backup copies /data, and a copy of a database file taken mid-write can be torn. So
after changes, at most every ``SNAPSHOT_S``, the database is copied with SQLite's own backup API to
``lacuna-snapshot.db`` (written aside, then renamed): the backup always holds one consistent copy.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_FILE = "lacuna.db"
SNAPSHOT_FILE = "lacuna-snapshot.db"
SNAPSHOT_S = 600

SCHEMA = [
    # 1: batch 3
    """
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE users (email TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL, role TEXT NOT NULL, plan TEXT NOT NULL,
                        created REAL NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL);
    CREATE TABLE sessions (hash TEXT PRIMARY KEY, email TEXT NOT NULL, exp REAL NOT NULL, data TEXT NOT NULL);
    CREATE INDEX sessions_email ON sessions(email);
    CREATE TABLE invites (hash TEXT PRIMARY KEY, email TEXT NOT NULL, exp REAL NOT NULL, data TEXT NOT NULL);
    CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE shows (id TEXT PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL, created_by TEXT,
                        archived INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL);
    CREATE TABLE show_members (show_id TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL,
                               PRIMARY KEY (show_id, email));
    CREATE INDEX show_members_email ON show_members(email);
    CREATE TABLE events (id INTEGER PRIMARY KEY, ts REAL NOT NULL, uid TEXT, sid TEXT, ep TEXT, ev TEXT NOT NULL,
                         props TEXT NOT NULL);
    CREATE INDEX events_ts ON events(ts);
    CREATE INDEX events_uid ON events(uid, ts);
    CREATE TABLE access_requests (id TEXT PRIMARY KEY, email TEXT NOT NULL, created REAL NOT NULL,
                                  status TEXT NOT NULL, data TEXT NOT NULL);
    """,
]


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA synchronous = FULL")
        self._dirty = False
        self._snap_at = 0.0
        self._timer: threading.Timer | None = None
        self._migrate()

    def _migrate(self) -> None:
        with self.lock:
            v = self.conn.execute("PRAGMA user_version").fetchone()[0]
            for i, sql in enumerate(SCHEMA[v:], start=v + 1):
                with self.tx() as c:
                    c.executescript_inside(sql)
                    c.execute(f"PRAGMA user_version = {i}")

    @contextmanager
    def tx(self) -> Iterator["_Tx"]:
        """One transaction: everything inside is written together or not at all."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield _Tx(self.conn)
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.conn.execute("COMMIT")
            self._changed()

    def query(self, sql: str, args: tuple | list = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    # -- settings kept in the meta table (migration markers and such)
    def meta(self, key: str) -> str | None:
        r = self.query("SELECT value FROM meta WHERE key = ?", (key,))
        return r[0]["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # -- consistent copy for the nightly backup
    def _changed(self) -> None:
        self._dirty = True
        if self._timer is None:
            wait = max(0.0, self._snap_at + SNAPSHOT_S - time.time())
            self._timer = threading.Timer(wait, self.snapshot)
            self._timer.daemon = True
            self._timer.start()

    def snapshot(self) -> Path:
        out = self.path.with_name(SNAPSHOT_FILE)
        tmp = out.with_suffix(".tmp")
        with self.lock:
            self._timer = None
            self._dirty = False
            self._snap_at = time.time()
            tmp.unlink(missing_ok=True)
            dst = sqlite3.connect(tmp)
            try:
                self.conn.backup(dst)
            finally:
                dst.close()
        os.replace(tmp, out)
        return out

    def close(self) -> None:
        with self.lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self.conn.close()


class _Tx:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def execute(self, sql: str, args: tuple | list = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, args)

    def executemany(self, sql: str, rows) -> sqlite3.Cursor:
        return self.conn.executemany(sql, rows)

    def executescript_inside(self, sql: str) -> None:
        """Statements one by one: ``executescript`` would commit the open transaction first."""
        for stmt in (s.strip() for s in sql.split(";")):
            if stmt:
                self.conn.execute(stmt)


_open: dict[Path, DB] = {}
_open_lock = threading.Lock()


def at(root: str | Path) -> DB:
    """The database of the installation whose folder is `root` (opened once per process)."""
    path = (Path(root).expanduser().resolve() / DB_FILE)
    with _open_lock:
        db = _open.get(path)
        if db is None or not path.exists():
            if db is not None:            # the file was removed (tests reuse folders): start afresh
                db.close()
            db = _open[path] = DB(path)
        return db


def dumps(d) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def loads(s: str):
    return json.loads(s)
