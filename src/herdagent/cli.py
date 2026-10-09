import argparse
import json
import sys

from herdagent import (
    __version__,
    accounts,
    db,
    events,
    router,
    sandbox,
    sessions,
    tasks,
)


def _conn():
    c = db.connect()
    db.init_db(c)
    return c


def _print_table(headers, rows) -> None:
    widths = [len(h) for h in headers]
    str_rows = [[str(cell) if cell is not None else "" for cell in r] for r in rows]
    for r in str_rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    header_line = "  ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
    print(header_line)
    for r in str_rows:
        print("  ".join(r[i].ljust(widths[i]) for i in range(len(headers))))


def _dump(obj) -> None:
    print(json.dumps(obj, separators=(",", ":")))


def _headroom_display(row) -> str:
    h = accounts.headroom(row)
    if h is None:
        return "unknown"
    return f"{round(h * 100)}%"


def handle_account_add(args, conn) -> int:
    new_id = accounts.add(
        conn,
        args.provider,
        args.label,
        limit_tokens_day=args.limit_tokens_day,
        notes=args.notes,
    )
    if args.json:
        _dump({"id": new_id, "label": args.label, "provider": args.provider})
    else:
        print(f"added account {args.label} (id {new_id})")
    return 0


def handle_account_list(args, conn) -> int:
    rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    if args.json:
        out = []
        for r in rows:
            d = dict(r)
            d["headroom"] = accounts.headroom(r)
            out.append(d)
        _dump(out)
    else:
        headers = [
            "ID",
            "Provider",
            "Label",
            "Status",
            "Used",
            "Limit",
            "Headroom",
            "429s",
        ]
        data = []
        for r in rows:
            limit = r["limit_tokens_day"]
            data.append(
                [
                    r["id"],
                    r["provider"],
                    r["label"],
                    r["status"],
                    r["used_tokens"] or 0,
                    limit if limit is not None else "",
                    _headroom_display(r),
                    r["observed_429s"] or 0,
                ]
            )
        _print_table(headers, data)
    return 0


def handle_account_report(args, conn) -> int:
    accounts.report(
        conn,
        args.label_or_id,
        tokens=args.tokens,
        rpm=args.rpm,
        got_429=args.got_429,
    )
    if args.json if hasattr(args, "json") else False:
        _dump({"label": args.label_or_id, "tokens": args.tokens})
    else:
        print(f"reported {args.tokens} tokens for {args.label_or_id}")
    return 0


def handle_account_quota(args, conn) -> int:
    rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    if args.json:
        out = []
        for r in rows:
            out.append(
                {
                    "label": r["label"],
                    "provider": r["provider"],
                    "headroom": accounts.headroom(r),
                    "used_tokens": r["used_tokens"] or 0,
                    "limit_tokens_day": r["limit_tokens_day"],
                }
            )
        _dump(out)
    else:
        headers = ["Label", "Provider", "Used", "Limit", "Headroom", "429s"]
        data = []
        for r in rows:
            limit = r["limit_tokens_day"]
            data.append(
                [
                    r["label"],
                    r["provider"],
                    r["used_tokens"] or 0,
                    limit if limit is not None else "",
                    _headroom_display(r),
                    r["observed_429s"] or 0,
                ]
            )
        _print_table(headers, data)
    return 0


def handle_account_enable(args, conn) -> int:
    accounts.set_status(conn, args.label_or_id, "active")
    print(f"enabled {args.label_or_id}")
    return 0


def handle_account_disable(args, conn) -> int:
    accounts.set_status(conn, args.label_or_id, "disabled")
    print(f"disabled {args.label_or_id}")
    return 0


def handle_route(args, conn) -> int:
    picked = router.choose(conn, args.provider)
    if picked is None:
        print(f"error: no accounts available for {args.provider}", file=sys.stderr)
        return 1
    h = accounts.headroom(picked)
    if args.json:
        _dump(
            {
                "account": picked["label"],
                "headroom": h,
                "provider": args.provider,
            }
        )
    else:
        print(picked["label"])
    return 0


def handle_session_start(args, conn) -> int:
    new_id = sessions.start(
        conn,
        args.name,
        args.backend,
        args.cwd,
        branch=args.branch,
        account_label=args.account,
        sandbox_profile=args.sandbox_profile,
    )
    row = sessions.get(conn, args.name)
    status = row["status"] if row is not None else "running"
    acct = row["account_label"] if row is not None else args.account
    if args.json:
        _dump(
            {
                "id": new_id,
                "name": args.name,
                "backend": args.backend,
                "account": acct,
                "status": status,
                "sandbox_profile": args.sandbox_profile,
            }
        )
    else:
        print(f"started session {args.name} (id {new_id}) on {acct}")
    if args.sandbox_profile != "none" and not sandbox.available():
        print("warning: bwrap not available, running unsandboxed", file=sys.stderr)
    return 0


def handle_session_list(args, conn) -> int:
    rows = sessions.list(conn)
    if args.json:
        _dump([dict(r) for r in rows])
    else:
        headers = ["ID", "Name", "Backend", "Status", "Account", "PID"]
        data = [
            [
                r["id"],
                r["name"],
                r["backend"],
                r["status"],
                r["account_label"] or "",
                r["pid"] or "",
            ]
            for r in rows
        ]
        _print_table(headers, data)
    return 0


def handle_session_status(args, conn) -> int:
    row = sessions.get(conn, args.name)
    if row is None:
        print(f"error: session not found: {args.name}", file=sys.stderr)
        return 1
    if args.json:
        _dump(dict(row))
    else:
        headers = ["Name", "Backend", "Status", "Account", "PID", "CWD", "Sandbox"]
        data = [
            [
                row["name"],
                row["backend"],
                row["status"],
                row["account_label"] or "",
                row["pid"] or "",
                row["cwd"],
                dict(row).get("sandbox_profile") or "",
            ]
        ]
        _print_table(headers, data)
    return 0


def handle_session_stop(args, conn) -> int:
    sessions.stop(conn, args.name)
    print(f"stopped {args.name}")
    return 0


def handle_session_migrate(args, conn) -> int:
    old, new = sessions.migrate(conn, args.name, args.to_account)
    print(f"migrated {args.name} from {old} to {new}")
    print(f"restart the backend CLI under the new account: {new}")
    return 0


def handle_task_add(args, conn) -> int:
    new_id = tasks.add(conn, args.title, body=args.body)
    if args.json:
        _dump({"id": new_id, "title": args.title})
    else:
        print(f"added task {new_id}")
    return 0


def handle_task_list(args, conn) -> int:
    rows = tasks.list(conn, status=args.status)
    if args.json:
        _dump([dict(r) for r in rows])
    else:
        headers = ["ID", "Title", "Status", "ClaimedBy"]
        data = [[r["id"], r["title"], r["status"], r["claimed_by"] or ""] for r in rows]
        _print_table(headers, data)
    return 0


def handle_task_claim(args, conn) -> int:
    tasks.claim(conn, args.task_id, args.session)
    print(f"claimed task {args.task_id} by {args.session}")
    return 0


def handle_task_done(args, conn) -> int:
    tasks.done(conn, args.task_id)
    print(f"task {args.task_id} done")
    return 0


def handle_events(args, conn) -> int:
    rows = events.recent(conn, limit=args.limit)
    if args.json:
        _dump([dict(r) for r in rows])
    else:
        headers = ["ID", "TS", "Kind", "Session", "Account", "Detail"]
        data = [
            [
                r["id"],
                r["ts"],
                r["kind"],
                r["session"] or "",
                r["account"] or "",
                r["detail"] or "",
            ]
            for r in rows
        ]
        _print_table(headers, data)
    return 0


def handle_sandbox_profiles(args, conn) -> int:
    del args
    del conn
    for profile in sandbox.PROFILES:
        print(f"{profile}: {sandbox.profile_description(profile)}")
    return 0


def handle_sandbox_check(args, conn) -> int:
    del args
    del conn
    if sandbox.available():
        print("bwrap: available")
    else:
        print("bwrap: missing (sessions run unsandboxed)")
    return 0


def handle_dashboard(args, conn) -> int:
    del args
    conn.close()
    if not sys.stdout.isatty():
        print("error: dashboard requires a tty", file=sys.stderr)
        return 1
    from herdagent import tui

    def factory():
        c = _conn()
        return c

    tui.run_dashboard(factory)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="herdagent")
    p.add_argument("--version", action="store_true", help="show version")
    sub = p.add_subparsers(dest="cmd")

    ap = sub.add_parser("account", help="manage accounts")
    ap_sub = ap.add_subparsers(dest="account_cmd", required=True)

    a_add = ap_sub.add_parser("add", help="add account")
    a_add.add_argument("--provider", required=True)
    a_add.add_argument("--label", required=True)
    a_add.add_argument(
        "--limit-tokens-day", dest="limit_tokens_day", type=int, default=None
    )
    a_add.add_argument("--notes", default="")
    a_add.add_argument("--json", action="store_true")
    a_add.set_defaults(func=handle_account_add)

    a_list = ap_sub.add_parser("list", help="list accounts")
    a_list.add_argument("--json", action="store_true")
    a_list.set_defaults(func=handle_account_list)

    a_rep = ap_sub.add_parser("report", help="report usage")
    a_rep.add_argument("label_or_id")
    a_rep.add_argument("--tokens", type=int, default=0)
    a_rep.add_argument("--rpm", type=int, default=None)
    a_rep.add_argument("--429", dest="got_429", action="store_true")
    a_rep.set_defaults(func=handle_account_report)

    a_quota = ap_sub.add_parser("quota", help="show quota")
    a_quota.add_argument("--json", action="store_true")
    a_quota.set_defaults(func=handle_account_quota)

    a_en = ap_sub.add_parser("enable", help="enable account")
    a_en.add_argument("label_or_id")
    a_en.set_defaults(func=handle_account_enable)

    a_dis = ap_sub.add_parser("disable", help="disable account")
    a_dis.add_argument("label_or_id")
    a_dis.set_defaults(func=handle_account_disable)

    r = sub.add_parser("route", help="pick account")
    r.add_argument("--provider", required=True)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=handle_route)

    sp = sub.add_parser("session", help="manage sessions")
    sp_sub = sp.add_subparsers(dest="session_cmd", required=True)

    s_start = sp_sub.add_parser("start", help="start session")
    s_start.add_argument("--name", required=True)
    s_start.add_argument("--backend", required=True)
    s_start.add_argument("--cwd", required=True)
    s_start.add_argument("--branch", default="")
    s_start.add_argument("--account", default=None)
    s_start.add_argument(
        "--sandbox-profile",
        default="standard",
        choices=["none", "standard", "strict"],
    )
    s_start.add_argument("--json", action="store_true")
    s_start.set_defaults(func=handle_session_start)

    s_list = sp_sub.add_parser("list", help="list sessions")
    s_list.add_argument("--json", action="store_true")
    s_list.set_defaults(func=handle_session_list)

    s_status = sp_sub.add_parser("status", help="show session")
    s_status.add_argument("name")
    s_status.add_argument("--json", action="store_true")
    s_status.set_defaults(func=handle_session_status)

    s_stop = sp_sub.add_parser("stop", help="stop session")
    s_stop.add_argument("name")
    s_stop.set_defaults(func=handle_session_stop)

    s_mig = sp_sub.add_parser("migrate", help="migrate session")
    s_mig.add_argument("name")
    s_mig.add_argument("--to", dest="to_account", required=True)
    s_mig.set_defaults(func=handle_session_migrate)

    tp = sub.add_parser("task", help="manage tasks")
    tp_sub = tp.add_subparsers(dest="task_cmd", required=True)

    t_add = tp_sub.add_parser("add", help="add task")
    t_add.add_argument("--title", required=True)
    t_add.add_argument("--body", default="")
    t_add.add_argument("--json", action="store_true")
    t_add.set_defaults(func=handle_task_add)

    t_list = tp_sub.add_parser("list", help="list tasks")
    t_list.add_argument("--status", default=None)
    t_list.add_argument("--json", action="store_true")
    t_list.set_defaults(func=handle_task_list)

    t_claim = tp_sub.add_parser("claim", help="claim task")
    t_claim.add_argument("task_id", type=int)
    t_claim.add_argument("--session", required=True)
    t_claim.set_defaults(func=handle_task_claim)

    t_done = tp_sub.add_parser("done", help="mark done")
    t_done.add_argument("task_id", type=int)
    t_done.set_defaults(func=handle_task_done)

    ev = sub.add_parser("events", help="show events")
    ev.add_argument("--limit", type=int, default=20)
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=handle_events)

    dash = sub.add_parser("dashboard", help="launch dashboard")
    dash.set_defaults(func=handle_dashboard)

    sb = sub.add_parser("sandbox", help="sandbox helpers")
    sb_sub = sb.add_subparsers(dest="sandbox_cmd", required=True)
    sb_prof = sb_sub.add_parser("profiles", help="list sandbox profiles")
    sb_prof.set_defaults(func=handle_sandbox_profiles)
    sb_check = sb_sub.add_parser("check", help="check bwrap availability")
    sb_check.set_defaults(func=handle_sandbox_check)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        print(f"herdagent {__version__}")
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    conn = _conn()
    try:
        code = args.func(args, conn)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        conn.close()
        return 1
    conn.close()
    if isinstance(code, int):
        return code
    return 0
