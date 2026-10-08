import sqlite3

from herdagent.accounts import headroom, recently_429


def choose(conn: sqlite3.Connection, provider: str):
    rows = conn.execute(
        "SELECT * FROM accounts WHERE provider = ? AND status = 'active'",
        (provider,),
    ).fetchall()
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
    fresh = sorted(
        (item for item in known if item[0] > 0), key=lambda item: item[0], reverse=True
    )
    if fresh:
        return fresh[0][1]
    unknown.sort(key=lambda r: r["id"])
    if unknown:
        return unknown[0]
    spent = sorted(
        (item for item in known if item[0] <= 0), key=lambda item: item[1]["id"]
    )
    if spent:
        return spent[0][1]
    return None
