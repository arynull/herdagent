import sqlite3

from herdagent.db import now_iso
from herdagent.events import log as log_event


def add(conn: sqlite3.Connection, title: str, body: str = "") -> int:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO tasks(title, body, status, created_at) VALUES (?, ?, 'queued', ?)",
        (title, body, ts),
    )
    conn.commit()
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, task_id: int):
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (int(task_id),)).fetchone()


def list(conn: sqlite3.Connection, status: str | None = None):
    if status is None:
        return conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return conn.execute(
        "SELECT * FROM tasks WHERE status = ? ORDER BY id", (status,)
    ).fetchall()


def claim(conn: sqlite3.Connection, task_id: int, session_name: str) -> None:
    sess = conn.execute(
        "SELECT * FROM sessions WHERE name = ?", (session_name,)
    ).fetchone()
    if sess is None:
        raise ValueError(f"session not found: {session_name}")
    task = get(conn, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    if task["status"] != "queued":
        raise ValueError(f"task not queued: {task_id}")
    conn.execute(
        "UPDATE tasks SET status = 'claimed', claimed_by = ? WHERE id = ?",
        (session_name, int(task_id)),
    )
    conn.commit()
    log_event(conn, "task_claim", session=session_name, detail=f"task={task_id}")


def done(conn: sqlite3.Connection, task_id: int) -> None:
    task = get(conn, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    ts = now_iso()
    conn.execute(
        "UPDATE tasks SET status = 'done', done_at = ? WHERE id = ?",
        (ts, int(task_id)),
    )
    conn.commit()
    log_event(conn, "task_done", session=task["claimed_by"], detail=f"task={task_id}")
