# Tile catalog

What ships, what it needs, and what to build next. Each tile names the persona
it serves first; the point of shipping all three rows is to show a customer the
range, then let them keep the tiles that matter to them.

## Shipped

| Tile | Persona | Data | Source needed | Why a plain drive cannot do it |
|---|---|---|---|---|
| Filespace pulse | Production lead | `activity.by_day`, `by_hour` | audit trail | filesystems keep no read log and no actor |
| Who is here, human or agent | Developer | `activity.by_actor` | audit trail | service accounts show up as their own actors |
| Who is working where | Production lead | `folders[]` | tree + audit | writers per folder need attribution |
| Cold and hot | Storage admin | `cold` | tree (mtime) | possible on a drive, but adding audit reads finds data nobody opens |
| What the bytes are | Storage admin | `extensions`, `largest`, `stats.storage_bytes` | tree + MCP or SDK | stored versus logical size is a LucidLink number |
| What just changed | Production lead | `recent` | audit trail | attribution and fan-out collapsing |
| Flags | Storage admin | `flags`, `notes` | derived | heuristics over the above |

## Build next, roughly in order of value

1. **Agent accountability.** One card per service account: files touched,
   read/write ratio, hosts, first and last seen, and a "verify" link that runs
   `read_audit_trail mode=user_activity`. Answers "which files did this agent
   use" without trusting the agent's own log. Needs: `by_actor` at deep budget.
2. **Locks held now.** Table of `list_locks_held` with holder and age. Shows the
   coordination primitive S3 does not have. Needs: MCP.
3. **Live ticker.** `subscribe_changes` on the busiest folder, `poll_changes`
   every few minutes from a small local process, append to `recent`. Later,
   the event stream when it ships.
4. **Trends.** `render.py --publish` already keeps dated snapshots under
   `history/`. A second page that reads them and charts stored size, files and
   events per snapshot. No new collection needed.
5. **Per-project view.** Set `folders.depth: 2` and render one small pulse per
   show or client folder as small multiples. Config only.
6. **Anomalies with thresholds.** Off-hours writes in the customer's timezone,
   read spikes on one folder, a human account behaving like a bot. Extend the
   flag rules in `snapshot.py`.
7. **Workspace tiles.** Members, groups, filespaces, service accounts from the
   admin toolset (`workspace_summary_admin`, `list_service_accounts_admin`).
   Needs admin tools enabled; keep them off by default.

## Not planned

- Anything that reads file contents. Metadata and audit are enough for a dashboard, and content stays inside the customer's zero-knowledge boundary.
- A hosted or public URL. Filespace content has no remote-fetchable URL; the page lives in the filespace or is served locally by the customer.
