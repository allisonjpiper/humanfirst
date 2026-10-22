"""
db.py

A small SQLite database that remembers, per user:
  - every prompt checked, what the gatekeeper decided, and its footprint
  - token usage, for the daily budget and the tokenomics numbers
And, shared across users:
  - a cache of gatekeeper verdicts, so the same question is never classified twice
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from config import DB_PATH

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username   TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    username           TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    source             TEXT NOT NULL,          -- 'claude.ai' (extension) or 'web' (test chat)
    prompt             TEXT NOT NULL,
    decision           TEXT NOT NULL,          -- allow | redirect | repeat | crisis | override
    category           TEXT NOT NULL,
    subtype            TEXT NOT NULL DEFAULT '',
    reason             TEXT,
    ai_kwh             REAL NOT NULL DEFAULT 0, -- footprint of the prompt sent to Claude (0 if blocked)
    ai_gallons         REAL NOT NULL DEFAULT 0,
    saved_kwh          REAL NOT NULL DEFAULT 0, -- footprint avoided because the prompt was redirected
    saved_gallons      REAL NOT NULL DEFAULT 0,
    gate_kwh           REAL NOT NULL DEFAULT 0, -- our own gatekeeper's footprint
    gate_gallons       REAL NOT NULL DEFAULT 0,
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    cached_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    model_calls        INTEGER NOT NULL DEFAULT 0,
    cache_hit          INTEGER NOT NULL DEFAULT 0,
    latency_ms         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_user ON events(username, created_at);
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    rating      INTEGER NOT NULL,          -- 1-5
    keep_using  TEXT NOT NULL DEFAULT '',  -- yes | maybe | no
    comment     TEXT NOT NULL DEFAULT '',
    page        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS verdict_cache (
    prompt_hash TEXT PRIMARY KEY,
    verdict     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_conn = _connect()
_conn.executescript(SCHEMA)


def _add_missing_columns() -> None:
    """Upgrade databases created by earlier versions of the app."""
    wanted = {
        "users": {"code": "TEXT"},  # private sign-in code
        "events": {"answer_input_tokens": "INTEGER NOT NULL DEFAULT 0",  # stand-in answers in the web chat
                   "answer_output_tokens": "INTEGER NOT NULL DEFAULT 0"},
    }
    for table, cols in wanted.items():
        have = {r[1] for r in _conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, decl in cols.items():
            if col not in have:
                _conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


_add_missing_columns()
_conn.commit()


def now() -> datetime:
    return datetime.now(timezone.utc)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def prompt_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


# --- users ---------------------------------------------------------------

def ensure_user(username: str) -> None:
    with _lock:
        _conn.execute(
            "INSERT OR IGNORE INTO users(username, created_at) VALUES (?, ?)",
            (username, now().isoformat()),
        )
        _conn.commit()


def user_code(username: str) -> str | None:
    with _lock:
        row = _conn.execute("SELECT code FROM users WHERE username = ?", (username,)).fetchone()
    return row["code"] if row else None


def user_exists(username: str) -> bool:
    with _lock:
        return _conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None


def set_user_code(username: str, code: str) -> None:
    with _lock:
        _conn.execute("UPDATE users SET code = ? WHERE username = ?", (code, username))
        _conn.commit()


# --- feedback ------------------------------------------------------------

def add_feedback(username: str, rating: int, keep_using: str, comment: str, page: str) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO feedback(username, created_at, rating, keep_using, comment, page) VALUES (?,?,?,?,?,?)",
            (username, now().isoformat(), rating, keep_using, comment, page),
        )
        _conn.commit()


def feedback_count_last_hour(username: str) -> int:
    since = (now() - timedelta(hours=1)).isoformat()
    with _lock:
        return _conn.execute("SELECT COUNT(*) FROM feedback WHERE username = ? AND created_at >= ?",
                             (username, since)).fetchone()[0]


def all_feedback() -> list[dict]:
    with _lock:
        rows = _conn.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


# --- events --------------------------------------------------------------

def add_event(**fields) -> int:
    fields.setdefault("created_at", now().isoformat())
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with _lock:
        cur = _conn.execute(f"INSERT INTO events({cols}) VALUES ({marks})", tuple(fields.values()))
        _conn.commit()
        return cur.lastrowid


def recent_blocks(username: str, days: int = 7) -> list[sqlite3.Row]:
    since = (now() - timedelta(days=days)).isoformat()
    with _lock:
        return _conn.execute(
            "SELECT * FROM events WHERE username = ? AND created_at >= ? "
            "AND decision IN ('redirect', 'repeat') ORDER BY created_at DESC",
            (username, since),
        ).fetchall()


def requests_last_minute(username: str) -> int:
    since = (now() - timedelta(minutes=1)).isoformat()
    with _lock:
        return _conn.execute(
            "SELECT COUNT(*) FROM events WHERE username = ? AND created_at >= ?", (username, since)
        ).fetchone()[0]


def tokens_today(username: str | None = None) -> int:
    since = now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    sql = ("SELECT COALESCE(SUM(input_tokens + output_tokens + answer_input_tokens + answer_output_tokens), 0) "
           "FROM events WHERE created_at >= ?")
    args: tuple = (since,)
    if username:
        sql += " AND username = ?"
        args += (username,)
    with _lock:
        return _conn.execute(sql, args).fetchone()[0]


def add_answer_tokens(event_id: int, input_tokens: int, output_tokens: int) -> None:
    """Record the stand-in answer's tokens so they count toward the daily budgets."""
    with _lock:
        _conn.execute("UPDATE events SET answer_input_tokens = ?, answer_output_tokens = ? WHERE id = ?",
                      (input_tokens, output_tokens, event_id))
        _conn.commit()


def user_events(username: str, limit: int = 200) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM events WHERE username = ? ORDER BY id DESC LIMIT ?", (username, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def user_totals(username: str) -> dict:
    with _lock:
        row = _conn.execute(
            """SELECT COUNT(*) AS prompts,
                      SUM(decision IN ('allow', 'override')) AS sent_to_ai,
                      SUM(decision IN ('redirect', 'repeat', 'crisis')) AS redirected,
                      COALESCE(SUM(ai_kwh), 0) AS ai_kwh,
                      COALESCE(SUM(ai_gallons), 0) AS ai_gallons,
                      COALESCE(SUM(saved_kwh), 0) AS saved_kwh,
                      COALESCE(SUM(saved_gallons), 0) AS saved_gallons,
                      COALESCE(SUM(gate_kwh), 0) AS gate_kwh,
                      COALESCE(SUM(gate_gallons), 0) AS gate_gallons,
                      COALESCE(SUM(input_tokens), 0) AS input_tokens,
                      COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                      COALESCE(SUM(output_tokens), 0) AS output_tokens,
                      COALESCE(SUM(model_calls), 0) AS model_calls,
                      COALESCE(SUM(cache_hit), 0) AS cache_hits
               FROM events WHERE username = ?""",
            (username,),
        ).fetchone()
    return {k: (row[k] or 0) for k in row.keys()}


def category_counts(username: str) -> dict:
    with _lock:
        rows = _conn.execute(
            "SELECT category, COUNT(*) AS n FROM events WHERE username = ? GROUP BY category", (username,)
        ).fetchall()
    return {r["category"]: r["n"] for r in rows}


def all_token_stats() -> list[dict]:
    """Every gatekeeper run with real model calls, for the tokenomics report."""
    with _lock:
        rows = _conn.execute(
            "SELECT decision, category, input_tokens, cached_tokens, output_tokens, model_calls, cache_hit, latency_ms "
            "FROM events WHERE decision != 'override'"
        ).fetchall()
    return [dict(r) for r in rows]


# --- verdict cache -------------------------------------------------------

def cached_verdict(text: str, version: str = "") -> dict | None:
    """A verdict is reused only if it came from the same gatekeeper instructions (version)."""
    with _lock:
        row = _conn.execute(
            "SELECT verdict FROM verdict_cache WHERE prompt_hash = ?", (prompt_hash(version + "|" + text),)
        ).fetchone()
    return json.loads(row["verdict"]) if row else None


def store_verdict(text: str, verdict: dict, version: str = "") -> None:
    with _lock:
        _conn.execute(
            "INSERT OR REPLACE INTO verdict_cache(prompt_hash, verdict, created_at) VALUES (?, ?, ?)",
            (prompt_hash(version + "|" + text), json.dumps(verdict), now().isoformat()),
        )
        _conn.commit()
