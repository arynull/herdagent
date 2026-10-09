import os
import signal
import sqlite3
import time

from herdagent import sandbox
from herdagent.accounts import headroom, recently_429
from herdagent.db import now_iso
from herdagent.events import log as log_event


def get(conn: sqlite3.Connection, name: str):
    return conn.execute("SELECT * FROM sessions WHERE name = ?", (name,)).fetchone()


def list(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM sessions ORDER BY id").fetchall()


def list_sessions(conn: sqlite3.Connection):
    return list(conn)


def heartbeat(conn: sqlite3.Connection, name: str) -> None:
    row = get(conn, name)
    if row is None:
        raise ValueError(f"session not found: {name}")
    conn.execute(
        "UPDATE sessions SET last_heartbeat = ? WHERE name = ?",
        (now_iso(), name),
    )
    conn.commit()


def _auto_pick(conn: sqlite3.Connection):
    rows = conn.execute("SELECT * FROM accounts WHERE status = 'active'").fetchall()
    eligible = [r for r in rows if not recently_429(r)]
    if not eligible:
        return None
    known = []
    unknown = []
    for r in eligible:
        h = headroom(r)
        if h is None:
            unknown.append(r)
        else:
            known.append((h, r))
    known.sort(key=lambda item: item[0], reverse=True)
    if known:
        return known[0][1]["label"]
    unknown.sort(key=lambda r: r["id"])
    if unknown:
        return unknown[0]["label"]
    return None


def start(
    conn: sqlite3.Connection,
    name: str,
    backend: str,
    cwd: str,
    branch: str = "",
    account_label: str | None = None,
    sandbox_profile: str = "standard",
) -> int:
    if sandbox_profile not in sandbox.PROFILES:
        raise ValueError(f"unknown sandbox profile: {sandbox_profile}")
    if get(conn, name) is not None:
        raise ValueError(f"session already exists: {name}")
    if not os.path.isdir(cwd):
        raise ValueError(f"cwd does not exist: {cwd}")
    chosen = account_label
    if chosen is None:
        chosen = _auto_pick(conn)
        if chosen is None:
            raise ValueError("no accounts available for session")
    else:
        acct = conn.execute(
            "SELECT * FROM accounts WHERE label = ?", (chosen,)
        ).fetchone()
        if acct is None:
            raise ValueError(f"account not found: {chosen}")
        if acct["status"] != "active":
            raise ValueError(f"account not active: {chosen}")
    pid = None
    status = "exited"
    sandboxed = False
    try:
        proc, sandboxed = sandbox.launch(backend.split(), cwd, sandbox_profile)
        pid = proc.pid
        time.sleep(0.2)
        if proc.poll() is None:
            status = "running"
        else:
            status = "exited"
    except OSError:
        pid = None
        status = "exited"
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO sessions(name, backend, cwd, branch, account_label,"
        " status, pid, started_at, last_heartbeat, sandbox_profile)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, backend, cwd, branch, chosen, status, pid, ts, ts, sandbox_profile),
    )
    conn.commit()
    log_event(
        conn,
        "session_start",
        session=name,
        account=chosen,
        detail=f"{backend} sandbox={sandbox_profile}:{'on' if sandboxed else 'off'}",
    )
    if not sandboxed and sandbox_profile != "none":
        log_event(
            conn,
            "sandbox_unavailable",
            session=name,
            account=chosen,
            detail=sandbox_profile,
        )
    return int(cur.lastrowid)


def stop(conn: sqlite3.Connection, name: str) -> None:
    row = get(conn, name)
    if row is None:
        raise ValueError(f"session not found: {name}")
    pid = row["pid"]
    if pid is not None:
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    conn.execute("UPDATE sessions SET status = 'stopped' WHERE name = ?", (name,))
    conn.commit()
    log_event(conn, "session_stop", session=name, account=row["account_label"])


def migrate(conn: sqlite3.Connection, name: str, to_account_label: str):
    row = get(conn, name)
    if row is None:
        raise ValueError(f"session not found: {name}")
    target = conn.execute(
        "SELECT * FROM accounts WHERE label = ?", (to_account_label,)
    ).fetchone()
    if target is None and str(to_account_label).isdigit():
        target = conn.execute(
            "SELECT * FROM accounts WHERE id = ?",
            (int(str(to_account_label)),),
        ).fetchone()
    if target is None:
        raise ValueError(f"account not found: {to_account_label}")
    if target["status"] != "active":
        raise ValueError(f"account not active: {to_account_label}")
    new_label = target["label"]
    old_label = row["account_label"]
    conn.execute(
        "UPDATE sessions SET account_label = ? WHERE name = ?",
        (new_label, name),
    )
    conn.commit()
    old_display = old_label if old_label else "none"
    log_event(
        conn,
        "migrate",
        session=name,
        account=new_label,
        detail=f"{old_display}->{new_label}",
    )
    return (old_label, new_label)
