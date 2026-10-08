import sqlite3

from herdagent.db import now_iso


def log(
    conn: sqlite3.Connection,
    kind: str,
    session: str | None = None,
    account: str | None = None,
    detail: str = "",
) -> int:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO events(ts, kind, session, account, detail) VALUES (?, ?, ?, ?, ?)",
        (ts, kind, session, account, detail),
    )
    conn.commit()
    return int(cur.lastrowid)


def recent(conn: sqlite3.Connection, limit: int = 20):
    cur = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
    return cur.fetchall()
