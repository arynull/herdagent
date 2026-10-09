import sqlite3

from herdagent.events import log as log_event


def _get(conn: sqlite3.Connection, name: str):
    row = conn.execute("SELECT * FROM sessions WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"session not found: {name}")
    return row


def _pcts(used_tokens, tokens_cap, used_cost, cost_cap):
    if tokens_cap is None:
        token_pct = None
    else:
        try:
            cap = float(tokens_cap)
        except (TypeError, ValueError):
            token_pct = None
        else:
            if cap <= 0:
                token_pct = None
            else:
                token_pct = float(used_tokens or 0) / cap
    if cost_cap is None:
        cost_pct = None
    else:
        try:
            cap = float(cost_cap)
        except (TypeError, ValueError):
            cost_pct = None
        else:
            if cap <= 0:
                cost_pct = None
            else:
                cost_pct = float(used_cost or 0) / cap
    return token_pct, cost_pct


def _row_to_status(row):
    d = dict(row)
    used_tokens = d.get("used_tokens") or 0
    used_cost = d.get("used_cost_usd") or 0
    tokens_cap = d.get("tokens_cap")
    cost_cap = d.get("cost_cap_usd")
    warned = d.get("warned_80") or 0
    token_pct, cost_pct = _pcts(used_tokens, tokens_cap, used_cost, cost_cap)
    return {
        "name": d.get("name"),
        "tokens_cap": tokens_cap,
        "cost_cap_usd": cost_cap,
        "used_tokens": used_tokens,
        "used_cost_usd": used_cost,
        "warned_80": int(warned),
        "token_pct": token_pct,
        "cost_pct": cost_pct,
    }


def set_cap(conn: sqlite3.Connection, name: str, tokens_cap=None, cost_cap_usd=None):
    row = _get(conn, name)
    d = dict(row)
    old_tokens_cap = d.get("tokens_cap")
    new_tokens_cap = old_tokens_cap if tokens_cap is None else tokens_cap
    old_cost_cap = d.get("cost_cap_usd")
    new_cost_cap = old_cost_cap if cost_cap_usd is None else cost_cap_usd
    warned = d.get("warned_80") or 0
    if tokens_cap is not None and tokens_cap != old_tokens_cap:
        warned = 0
    conn.execute(
        "UPDATE sessions SET tokens_cap = ?, cost_cap_usd = ?, warned_80 = ? WHERE name = ?",
        (new_tokens_cap, new_cost_cap, warned, name),
    )
    conn.commit()
    log_event(
        conn,
        "cost_cap_set",
        session=name,
        detail=f"tokens_cap={new_tokens_cap} cost_cap_usd={new_cost_cap}",
    )


def clear_cap(conn: sqlite3.Connection, name: str):
    _get(conn, name)
    conn.execute(
        "UPDATE sessions SET tokens_cap = NULL, cost_cap_usd = NULL, warned_80 = 0 WHERE name = ?",
        (name,),
    )
    conn.commit()
    log_event(conn, "cost_cap_cleared", session=name)


def status_row(conn: sqlite3.Connection, name: str):
    row = _get(conn, name)
    return _row_to_status(row)


def report_usage(conn: sqlite3.Connection, name: str, tokens, cost_usd=None):
    if tokens < 0:
        raise ValueError("tokens must be >= 0")
    row = _get(conn, name)
    d = dict(row)
    used_tokens = (d.get("used_tokens") or 0) + tokens
    used_cost = d.get("used_cost_usd") or 0
    if cost_usd is not None:
        used_cost = float(used_cost) + float(cost_usd)
    conn.execute(
        "UPDATE sessions SET used_tokens = ?, used_cost_usd = ? WHERE name = ?",
        (used_tokens, used_cost, name),
    )
    conn.commit()
    fresh = _get(conn, name)
    fd = dict(fresh)
    tokens_cap = fd.get("tokens_cap")
    cost_cap = fd.get("cost_cap_usd")
    token_pct, cost_pct = _pcts(used_tokens, tokens_cap, used_cost, cost_cap)
    token_hit = token_pct is not None and token_pct >= 1.0
    cost_hit = cost_pct is not None and cost_pct >= 1.0
    if token_hit or cost_hit:
        from herdagent import sessions as sess_mod

        sess_mod.stop(conn, name)
        if token_hit:
            detail = f"tokens {used_tokens}/{tokens_cap}"
        else:
            detail = f"cost {used_cost}/{cost_cap}"
        log_event(conn, "cost_cap_hit", session=name, detail=detail)
        return {"stopped": True, "warned": False}
    warned_flag = fd.get("warned_80") or 0
    if token_pct is not None and token_pct >= 0.8 and not warned_flag:
        conn.execute("UPDATE sessions SET warned_80 = 1 WHERE name = ?", (name,))
        conn.commit()
        log_event(
            conn, "cost_warn", session=name, detail=f"tokens {used_tokens}/{tokens_cap}"
        )
        return {"stopped": False, "warned": True}
    return {"stopped": False, "warned": False}


def summary(conn: sqlite3.Connection):
    rows = conn.execute("SELECT * FROM sessions ORDER BY id").fetchall()
    return [_row_to_status(r) for r in rows]
