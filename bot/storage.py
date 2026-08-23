"""Хранилище на SQLite: клиенты, заявки, отложенные сообщения."""

import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id       INTEGER PRIMARY KEY,
    first_name    TEXT,
    username      TEXT,
    state         TEXT NOT NULL DEFAULT 'idle',
    draft         TEXT NOT NULL DEFAULT '{}',
    last_activity INTEGER NOT NULL DEFAULT 0,
    reminded      INTEGER NOT NULL DEFAULT 0,
    blocked       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    salon      TEXT,
    service    TEXT,
    when_text  TEXT,
    name       TEXT,
    phone      TEXT,
    username   TEXT,
    status     TEXT NOT NULL DEFAULT 'new',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind    TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    run_at  INTEGER NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    done    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS jobs_pending ON jobs (done, run_at);

CREATE TABLE IF NOT EXISTS operator_threads (
    admin_message_id INTEGER PRIMARY KEY,
    chat_id          INTEGER NOT NULL
);
"""


def now():
    return int(time.time())


class Storage:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- клиенты ---

    def touch_user(self, chat_id, first_name=None, username=None):
        self.db.execute(
            "INSERT INTO users (chat_id, first_name, username, last_activity) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET "
            "  first_name = COALESCE(excluded.first_name, users.first_name),"
            "  username   = COALESCE(excluded.username, users.username),"
            "  last_activity = excluded.last_activity,"
            "  blocked = 0",
            (chat_id, first_name, username, now()),
        )
        self.db.commit()
        return self.get_user(chat_id)

    def get_user(self, chat_id):
        row = self.db.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def set_state(self, chat_id, state, reset_reminder=True):
        if reset_reminder:
            self.db.execute(
                "UPDATE users SET state = ?, reminded = 0, last_activity = ? WHERE chat_id = ?",
                (state, now(), chat_id),
            )
        else:
            self.db.execute(
                "UPDATE users SET state = ?, last_activity = ? WHERE chat_id = ?",
                (state, now(), chat_id),
            )
        self.db.commit()

    def get_draft(self, chat_id):
        row = self.db.execute("SELECT draft FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return json.loads(row["draft"]) if row else {}

    def save_draft(self, chat_id, draft):
        self.db.execute(
            "UPDATE users SET draft = ?, last_activity = ? WHERE chat_id = ?",
            (json.dumps(draft, ensure_ascii=False), now(), chat_id),
        )
        self.db.commit()

    def clear_draft(self, chat_id):
        self.save_draft(chat_id, {})

    def mark_blocked(self, chat_id):
        self.db.execute("UPDATE users SET blocked = 1, state = 'idle' WHERE chat_id = ?", (chat_id,))
        self.db.commit()

    def abandoned_users(self, states, idle_seconds):
        """Кто начал запись и замолчал: нужен напоминающий пинок."""
        rows = self.db.execute(
            "SELECT * FROM users WHERE reminded = 0 AND blocked = 0 AND last_activity < ? "
            f"AND state IN ({','.join('?' * len(states))})",
            (now() - idle_seconds, *states),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_reminded(self, chat_id):
        self.db.execute("UPDATE users SET reminded = 1 WHERE chat_id = ?", (chat_id,))
        self.db.commit()

    # --- заявки ---

    def create_lead(self, chat_id, draft, username=None):
        cursor = self.db.execute(
            "INSERT INTO leads (chat_id, salon, service, when_text, name, phone, username, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chat_id,
                draft.get("salon"),
                draft.get("service"),
                draft.get("when"),
                draft.get("name"),
                draft.get("phone"),
                username,
                now(),
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def get_lead(self, lead_id):
        row = self.db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None

    def set_lead_status(self, lead_id, status):
        self.db.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        self.db.commit()

    # --- отложенные сообщения ---

    def schedule(self, kind, chat_id, run_at, payload=None):
        self.db.execute(
            "INSERT INTO jobs (kind, chat_id, run_at, payload) VALUES (?, ?, ?, ?)",
            (kind, chat_id, run_at, json.dumps(payload or {}, ensure_ascii=False)),
        )
        self.db.commit()

    def due_jobs(self):
        rows = self.db.execute(
            "SELECT * FROM jobs WHERE done = 0 AND run_at <= ? ORDER BY run_at", (now(),)
        ).fetchall()
        return [dict(row) for row in rows]

    def finish_job(self, job_id):
        self.db.execute("UPDATE jobs SET done = 1 WHERE id = ?", (job_id,))
        self.db.commit()

    def cancel_jobs(self, chat_id, kind):
        self.db.execute("UPDATE jobs SET done = 1 WHERE chat_id = ? AND kind = ? AND done = 0", (chat_id, kind))
        self.db.commit()

    # --- диалог с администратором ---

    def link_operator_message(self, admin_message_id, chat_id):
        self.db.execute(
            "INSERT OR REPLACE INTO operator_threads (admin_message_id, chat_id) VALUES (?, ?)",
            (admin_message_id, chat_id),
        )
        self.db.commit()

    def operator_chat_for(self, admin_message_id):
        row = self.db.execute(
            "SELECT chat_id FROM operator_threads WHERE admin_message_id = ?", (admin_message_id,)
        ).fetchone()
        return row["chat_id"] if row else None
