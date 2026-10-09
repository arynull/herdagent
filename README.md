# herdagent

Local-first Agent Fleet Command Center. Run, supervise, and coordinate fleets of coding agents on one machine.

All state lives in one SQLite file under `$HERDAGENT_DATA_DIR` (default `~/.herdagent/`). Zero network calls. Python 3.10+, stdlib only.

## Install

```bash
pip install .
herdagent --version   # herdagent 0.3.0
```

## Quickstart

```bash
# Pool two provider accounts with daily token limits
herdagent account add --provider claude --label main --limit-tokens-day 1000000
herdagent account add --provider claude --label backup --limit-tokens-day 500000

# Report usage as it happens; the router tracks headroom per account
herdagent account report backup --tokens 490000
herdagent account quota

# The router picks the account with the most headroom (here: main)
herdagent route --provider claude

# Start a session — the router assigns the account automatically
herdagent session start --name s1 --backend my-agent-cli --cwd ~/work/proj

# Feed the fleet from a task queue
herdagent task add --title "review auth module" --body "check login flow for broken auth"
herdagent task claim 1 --session s1
herdagent task done 1

# Quota hit on main? Migrate the session to backup (audit-logged)
herdagent session migrate s1 --to backup
herdagent session stop s1

# Live TUI dashboard (q quits)
herdagent dashboard
```

## Sandboxed execution

Sessions run under bubblewrap when bwrap is present.

| Profile | Guarantee |
| --- | --- |
| none | no isolation, backend runs directly on host |
| standard | read-only root with writable cwd and tmp plus isolated pid namespace |
| strict | standard isolation plus no network access |

Start with a profile: herdagent session start --name s1 --backend my-agent-cli --cwd ~/work/proj --sandbox-profile strict

If bwrap is missing, the session launches unsandboxed, a warning is printed to stderr, and a sandbox_unavailable event is logged. Use herdagent sandbox check and herdagent sandbox profiles to inspect support.

## Cost guards

Sessions can carry token and USD caps. Set caps at start with --tokens-cap and --cost-cap-usd, or later with session cap. Report usage with session report-usage; use cost summary for a spend-attribution table of used versus cap per session.

At 80% of any token cap the first crossing logs a cost_warn event. At 100% of any cap the session auto-stops (process group terminated, status stopped) and logs a cost_cap_hit event. Raising the token cap via session cap resets the 80% warning. Clearing caps uses session cap --clear. Cap changes log cost_cap_set and cost_cap_cleared events.

## Command reference

Every list/status/route/add command also accepts `--json` for scripting.

**Accounts**

```bash
herdagent account add --provider claude --label main --limit-tokens-day 1000000 [--notes "..."]
herdagent account list                 # headroom shown as % or "unknown"
herdagent account quota                # headroom table for all accounts
herdagent account report main --tokens 250000 [--rpm 40] [--429]
herdagent account enable|disable main
```

**Routing**

```bash
herdagent route --provider claude      # prints the chosen account label; exit 1 when none
herdagent route --provider claude --json
```

Routing rules: among `active` accounts for the provider, the highest headroom wins; accounts with a 429 observed in the last 10 minutes are skipped; accounts with unknown headroom (no limit configured) rank after accounts that still have quota, but before fully exhausted (0.0) accounts. Usage numbers are operator-reported — herdagent never invents them.

**Sessions**

```bash
herdagent session start --name s1 --backend my-agent-cli --cwd ~/work/proj [--branch feat-x] [--account main] [--sandbox-profile none|standard|strict] [--tokens-cap 5000] [--cost-cap-usd 0.5]
herdagent session list
herdagent session status s1                # shows the sandbox profile and cost used/cap
herdagent session stop s1
herdagent session migrate s1 --to backup   # rebinds account, logs an audit event
herdagent session cap s1 --tokens-cap 5000 --cost-cap-usd 0.5
herdagent session report-usage s1 --tokens 250 [--cost-usd 0.01]
herdagent cost summary
```

`sandbox-profile` defaults to `standard`. Profiles are documented under "Sandboxed execution" above; when bwrap is missing the session runs unsandboxed with a stderr warning.

**Sandbox**

```bash
herdagent sandbox profiles                 # list profiles and their guarantees
herdagent sandbox check                    # bwrap available or missing
```

`session start` launches the backend CLI as a local subprocess in `--cwd`. Omit `--account` and the router picks one. `migrate` checkpoints the session (cwd, branch, claimed tasks) into the event log and rebinds it — restart your backend CLI under the new account afterwards.

**Tasks**

```bash
herdagent task add --title "review auth module" [--body "..."]
herdagent task list [--status queued|claimed|done]
herdagent task claim 1 --session s1
herdagent task done 1
```

**Events & dashboard**

```bash
herdagent events [--limit 20]          # newest first: routes, migrations, 429s, status changes, cost_warn, cost_cap_hit
herdagent dashboard                    # curses TUI: sessions, queue, quota bars, event feed
```

## Data & state

`HERDAGENT_DATA_DIR` (default `~/.herdagent/`) holds a single SQLite database with four tables: `accounts`, `sessions`, `tasks`, `events`. No daemons, no servers, no cloud.

## Roadmap

v0.2.0 adds sandboxed execution (bubblewrap profiles per session). v0.3.0 adds per-session cost guards (token/USD caps, warn at 80%, auto-stop at 100%). Next: agent identity & governance (scoped identities, hash-chained audit), swarm planning, skills marketplace client, web dashboard, provider adapters.

## License

MIT
