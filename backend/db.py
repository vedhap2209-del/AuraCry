"""Tiny SQLite layer (standard library only). One connection per request, rows returned as dicts.
To move to PostgreSQL/MySQL later, replace this one file (the routes only call q/one/execute)."""
import sqlite3
from flask import g

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER', status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS analyses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  audio_filename TEXT NOT NULL, audio_path TEXT NOT NULL, spectrogram_path TEXT,
  predicted_category TEXT NOT NULL, confidence REAL NOT NULL, duration_sec REAL NOT NULL,
  result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS ix_an_user ON analyses(user_id, created_at);
CREATE TABLE IF NOT EXISTS model_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, model_name TEXT, accuracy REAL, balanced_accuracy REAL, macro_f1 REAL,
  metrics_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS login_tickets(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL DEFAULT 'login', password_ok INTEGER NOT NULL DEFAULT 0, otp_ok INTEGER NOT NULL DEFAULT 0,
  otp_hash TEXT, otp_expires INTEGER, otp_attempts INTEGER DEFAULT 0, resend_count INTEGER DEFAULT 0,
  pin_attempts INTEGER DEFAULT 0, last_sent INTEGER, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS baby_memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL, story TEXT NOT NULL DEFAULT '', event_date TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'chat', created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS ix_memories_user ON baby_memories(user_id, event_date DESC, id DESC);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, event TEXT NOT NULL, ip TEXT, detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS ix_audit ON audit_log(created_at);
"""

# columns added to `users` after the first release (SQLite has no "ADD COLUMN IF NOT EXISTS")
USER_COLUMNS = {"failed_logins": "INTEGER NOT NULL DEFAULT 0", "locked_until": "TEXT", "pin_hash": "TEXT"}


def connect():
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def get():
    if "db" not in g:
        g.db = connect()
    return g.db


def close(_exc=None):
    c = g.pop("db", None)
    if c is not None:
        c.close()


def init():
    c = connect()
    c.executescript(SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    for col, decl in USER_COLUMNS.items():
        if col not in have:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
    c.commit()
    c.close()


def q(sql, args=()):
    return [dict(r) for r in get().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = get().execute(sql, args).fetchone()
    return dict(r) if r else None


def execute(sql, args=()):
    cur = get().execute(sql, args)
    get().commit()
    return cur.lastrowid
