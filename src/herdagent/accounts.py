import sqlite3
from datetime import datetime, timezone

from herdagent.db import now_iso
from herdagent.events import log as log_event


def _find(conn: sqlite3.Connection, label_or_id):
    key = str(label_or_id)
    row = conn.execute("SELECT * FROM accounts WHERE label = ?", (key,)).fetchone()
    if row is not None:
        return row
    if key.isdigit():
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (int(key),)
        ).fetchone()
        if row is not None:
            return row
    return None


def get(conn: sqlite3.Connection, label_or_id):
    return _find(conn, label_or_id)


def list_accounts(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()


def add(
    conn: sqlite3.Connection,
    provider: str,
    label: str,
    limit_tokens_day: int | None = None,
    notes: str = "",
) -> int:
    existing = conn.execute(
        "SELECT id FROM accounts WHERE label = ?", (label,)
    ).fetchone()
    if existing is not None:
        raise ValueError(f"account label already exists: {label}")
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO accounts(provider, label, limit_tokens_day, used_tokens,"
        " observed_429s, status, notes, created_at)"
        " VALUES (?, ?, ?, 0, 0, 'active', ?, ?)",
        (provider, label, limit_tokens_day, notes, ts),
    )
    conn.commit()
    log_event(conn, "account_add", account=label, detail=f"provider={provider}")
    return int(cur.lastrowid)


def report(
    conn: sqlite3.Connection,
    label_or_id,
    tokens: int = 0,
    rpm: int | None = None,
    got_429: bool = False,
):
    row = _find(conn, label_or_id)
    if row is None:
        raise ValueError(f"account not found: {label_or_id}")
    new_used = (row["used_tokens"] or 0) + (tokens or 0)
    new_429s = row["observed_429s"] or 0
    last_429 = row["last_429_at"]
    if got_429:
        new_429s += 1
        last_429 = now_iso()
    if rpm is None:
        conn.execute(
            "UPDATE accounts SET used_tokens = ?, observed_429s = ?,"
            " last_429_at = ? WHERE id = ?",
            (new_used, new_429s, last_429, row["id"]),
        )
    else:
        conn.execute(
            "UPDATE accounts SET used_tokens = ?, observed_429s = ?,"
            " last_429_at = ?, limit_rpm = ? WHERE id = ?",
            (new_used, new_429s, last_429, rpm, row["id"]),
        )
    conn.commit()
    log_event(
        conn,
        "account_report",
        account=row["label"],
        detail=f"tokens={tokens} rpm={rpm} got_429={got_429}",
    )
    return conn.execute("SELECT * FROM accounts WHERE id = ?", (row["id"],)).fetchone()


def headroom(acct_row) -> float | None:
    limit = acct_row["limit_tokens_day"]
    if limit is None:
        return None
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        return None
    if lim <= 0:
        return None
    used = acct_row["used_tokens"] or 0
    val = 1.0 - float(used) / float(lim)
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def recently_429(acct_row, minutes: int = 10) -> bool:
    raw = acct_row["last_429_at"]
    if not raw:
        return False
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (now - parsed).total_seconds()
    if delta < 0:
        return True
    return delta <= float(minutes) * 60.0


def set_status(conn: sqlite3.Connection, label_or_id, status: str):
    row = _find(conn, label_or_id)
    if row is None:
        raise ValueError(f"account not found: {label_or_id}")
    conn.execute("UPDATE accounts SET status = ? WHERE id = ?", (status, row["id"]))
    conn.commit()
    log_event(conn, "account_status", account=row["label"], detail=status)
    return conn.execute("SELECT * FROM accounts WHERE id = ?", (row["id"],)).fetchone()
