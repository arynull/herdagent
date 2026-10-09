import curses
import sqlite3


def _frac(acct):
    limit = acct["limit_tokens_day"]
    if limit is None:
        return None
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        return None
    if lim <= 0:
        return None
    used = acct["used_tokens"] or 0
    val = 1.0 - float(used) / float(lim)
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def _bar(frac, width=20) -> str:
    if frac is None:
        return "[" + "?" * width + "]"
    filled = round(frac * width)
    filled = max(filled, 0)
    filled = min(filled, width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _put(stdscr, y, x, text, max_x) -> None:
    if y < 0 or x < 0 or x >= max_x:
        return
    room = max_x - x - 1
    if room <= 0:
        return
    try:
        stdscr.addnstr(y, x, text[:room], room)
    except curses.error:
        pass


def run_dashboard(conn_factory) -> None:
    def _main(stdscr) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.nodelay(True)
        stdscr.timeout(2000)
        while True:
            stdscr.erase()
            try:
                max_y, max_x = stdscr.getmaxyx()
            except curses.error:
                break
            try:
                conn = conn_factory()
                try:
                    sess_rows = conn.execute(
                        "SELECT * FROM sessions ORDER BY id"
                    ).fetchall()
                    task_rows = conn.execute(
                        "SELECT * FROM tasks ORDER BY id"
                    ).fetchall()
                    acct_rows = conn.execute(
                        "SELECT * FROM accounts ORDER BY id"
                    ).fetchall()
                    event_rows = conn.execute(
                        "SELECT * FROM events ORDER BY id DESC LIMIT 20"
                    ).fetchall()
                finally:
                    conn.close()
            except (sqlite3.Error, OSError):
                sess_rows = []
                task_rows = []
                acct_rows = []
                event_rows = []
            pane = max(4, max_y // 4)
            y = 0
            _put(stdscr, y, 0, "Sessions (name/backend/status/account)", max_x)
            y += 1
            _put(
                stdscr,
                y,
                0,
                "NAME BACKEND STATUS ACCOUNT",
                max_x,
            )
            y += 1
            for r in sess_rows[: max(0, pane - 3)]:
                line = (
                    f"{r['name']} {r['backend']} {r['status']} "
                    f"{r['account_label'] or ''}"
                )
                d = dict(r)
                cap = d.get("tokens_cap")
                try:
                    cap_f = float(cap) if cap is not None else None
                except (TypeError, ValueError):
                    cap_f = None
                if cap_f is not None and cap_f > 0:
                    used = d.get("used_tokens") or 0
                    try:
                        pct = round(float(used) / cap_f * 100)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pct = 0
                    line += f" cost={used}/{cap} {pct}%"
                _put(stdscr, y, 0, line, max_x)
                y += 1
            y = pane
            _put(stdscr, y, 0, "Tasks", max_x)
            y += 1
            queued = [r for r in task_rows if r["status"] == "queued"]
            claimed = [r for r in task_rows if r["status"] == "claimed"]
            done = [r for r in task_rows if r["status"] == "done"]
            _put(
                stdscr,
                y,
                0,
                f"queued={len(queued)} claimed={len(claimed)} done={len(done)}",
                max_x,
            )
            y += 1
            for r in queued[: max(0, pane - 3)]:
                _put(stdscr, y, 0, f"- {r['id']}: {r['title']}", max_x)
                y += 1
            y = pane * 2
            _put(stdscr, y, 0, "Accounts (headroom)", max_x)
            y += 1
            for r in acct_rows[: max(0, pane - 2)]:
                f = _frac(r)
                bar = _bar(f)
                pct = "unknown" if f is None else f"{round(f * 100)}%"
                line = f"{r['label']} {bar} {pct} 429s={r['observed_429s'] or 0}"
                _put(stdscr, y, 0, line, max_x)
                y += 1
            y = pane * 3
            _put(stdscr, y, 0, "Events (recent)", max_x)
            y += 1
            for r in event_rows[: max(0, max_y - y - 1)]:
                line = (
                    f"{r['ts']} {r['kind']} "
                    f"{r['session'] or ''} {r['account'] or ''} "
                    f"{r['detail'] or ''}"
                )
                _put(stdscr, y, 0, line, max_x)
                y += 1
            _put(stdscr, max_y - 1, 0, "q: quit", max_x)
            stdscr.refresh()
            try:
                key = stdscr.getch()
            except curses.error:
                key = -1
            if key == ord("q") or key == ord("Q"):
                break

    curses.wrapper(_main)
