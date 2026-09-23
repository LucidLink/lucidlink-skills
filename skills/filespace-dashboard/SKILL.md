---
name: filespace-dashboard
description: >-
  Build a shareable dashboard for a LucidLink filespace and place it inside the
  filespace so the whole team sees it. Tiles cover the activity pulse (reads,
  writes, deletes per day), who is working in which folder, humans versus
  agents (service accounts), cold data and archive candidates, storage mix by
  file type, and the newest changes. Data comes from the filespace audit trail
  and directory tree through the LucidLink MCP Server, a mounted filespace, or
  the Python SDK. Use when someone asks for a filespace dashboard, storage or
  usage report, activity overview, "who touched what", cold-data or archive
  candidates, or wants to see what agents did in a filespace.
---

# LucidLink filespace dashboard

You produce a single self-contained `index.html` plus the `snapshot.json` it was
rendered from, in LucidLink's visual style, and place both inside the
filespace (default `/Dashboards/<name>/`). Anyone with the filespace mounted
opens the page from the drive. No server, no build step, no external calls.

The interesting tiles are the ones a plain file listing cannot give: every read
and write with its actor, and agents as first-class actors. That is what to
lead with when you present the result.

## Before you start

1. **Confirm which filespace, and how you reach it.** The user names the
   filespace; you verify the route before spending anything on it.
   - *Mount:* `ls <root>/.lucid_audit` must succeed. On macOS a live LucidLink
     mount appears in `mount` as `//guest:@127.0.0.1:<port>/<filespace>`; empty
     folders such as `<filespace>-2` under `/Volumes/<workspace>/` are stale
     mount points, not filespaces. If the path is missing, do not guess: fall
     back to the MCP Server, or ask.
   - *MCP Server:* `link_filespace(name=...)`, then `current_filespace`. The
     server's current filespace is shared by every session using that server
     and can change under you, so link, confirm, then make the scoped calls,
     and check that `filespace_stats` says `linked: <your filespace>` before
     trusting a number.
   - *SDK:* a service-account token in an environment variable (default
     `LUCIDLINK_TOKEN`), exported in the shell that runs the script. Never read
     a token out of another tool's configuration (the MCP Server keeps its
     own); ask the user to export one.
2. **Confirm the audit trail is on.** MCP: `read_audit_trail` with
   `mode=aggregate`, `group_by=action`, `time_range=7d`; a `30d` aggregate
   tells a quiet trail from a newly enabled one. Mount: `/.lucid_audit` holds
   `.log` or `.log.active` files. SDK: no pre-check; `snapshot.py` writes
   `No audit trail found` into the notes if it is off. A missing folder can
   also mean this login's role cannot read the trail; `get_audit_trail_status_admin`
   (it takes the `filespace_id` printed by `link_filespace`, under the account
   that owns the workspace) settles it. If it is off, say so plainly: activity
   tiles stay empty until an admin enables it, and only events after that point
   are recorded.
3. **Pick a source** (table below). Prefer the script over hand-built JSON when
   a mount or the SDK is reachable; it costs no tokens and is repeatable.
4. **Stay read-only.** This skill never modifies, moves or deletes filespace
   content. The only write is the dashboard folder, and only after the user
   has agreed to the location.

| Source | When | Cost | Stored size and Connect files |
|---|---|---|---|
| `mount` | filespace is mounted on this machine | one script run; the walk is bounded by the budget | not visible; pass them from MCP `filespace_stats` with `--stats` |
| `sdk` | you have a service-account token and Python | one script run; the SDK walk is several times slower than a mount and keeps a local cache of about 1 GB | fetched automatically |
| `mcp` | only the MCP Server is reachable | 15 to 200 tool calls, by budget and filespace size | yes |

*Connect files* are files linked into the filespace from external object
storage through LucidLink Connect: they count toward the logical size but are
never stored here.

## Interview, one message

Ask everything below in one numbered message, with the defaults shown, then
proceed with the answers. Do not ask anything else.

1. **Which filespace**, and how it is reached: mount path, MCP Server, or SDK
   token.
2. **Who reads this first?** Production lead (who is working where), storage
   admin (cold data, cost), or developer (agent activity). Default: all three,
   one tile row each.
3. **Which folders matter?** Top-level folders by default. Name a subtree to
   focus on, or a grouping depth of 2 for per-show or per-client folders. On the
   mcp source, naming folders is what makes the cold-data and largest-files
   tiles possible: per-file metadata is fetched only for named folders.
4. **How much to spend?** `lite`, `standard` or `deep`. One line each:
   lite is a handful of calls and a 7-day window; standard adds an hourly
   profile and flags; deep widens to 30 days and walks everything. Default:
   `deep` on a mount or the SDK, where the budget only bounds entries and
   wall-clock time (400,000 entries or 15 minutes; through the SDK the time
   limit usually bites) and costs no tokens; `standard` on the mcp source,
   where the budget is a call count.
5. **Where to put it.** Default `/Dashboards/<filespace name>/` inside the
   filespace; offer a local folder if they do not want it in the filespace yet.
   Only a mount can place the page inside the filespace; the sdk and mcp
   sources produce a local copy.

## Procedure, mount or sdk source

1. Copy `config.example.yaml` into your working folder as `config.yaml` (the
   skill folder is read-only when installed as a plugin) and use absolute
   paths for `output.dir` and `output.publish_to`. Mount: `filespace.source:
   mount` and `filespace.root`. SDK: `filespace.source: sdk` (or `--source
   sdk`) and `filespace.name: <filespace>.<workspace>` (the filespace name
   alone also works; a service-account token is scoped to one workspace).
   `filespace.sdk.token_env` is the *name* of the variable that holds the
   token: export it in the shell, never write the token into the config.
   `output.publish_to` is where `render.py --publish` copies the page (mount
   only); `output.filespace_path` is that same folder as a path inside the
   filespace, so the dashboard's own files stay out of the counts on any source.
2. Run `python3 scripts/snapshot.py --config <path>/config.yaml`. Mount: if the
   MCP Server is also available, call `filespace_stats` once and pass all four
   figures with `--stats` (a JSON string or a file), `data_bytes` included: the
   page only computes the dedup ratio from two hub figures.
   ```
   python3 scripts/snapshot.py --config config.yaml --stats '{"data_bytes": <n>, "storage_bytes": <n>, "external_files": <n>, "external_bytes": <n>}'
   ```
   SDK: no `--stats`; the script fetches the hub figures itself. Either way the
   header then mixes provenance, and labels it: sizes are hub figures and
   complete, file counts and folder bytes are walked and may be a sample.
3. Render: `python3 scripts/render.py --snapshot <out>/snapshot.json` writes
   `index.html` beside the snapshot. Add `--publish "<mounted root>/Dashboards/<name>"`
   only when the user agreed to place it in the filespace; it also appends a
   dated copy under `history/` for later trends.
4. Verify. If a browser is available to you, look at it (browser tooling that
   refuses `file://` pages can use `python3 -m http.server 8765 --directory <out>`
   and `http://127.0.0.1:8765/index.html`); otherwise confirm the file exists,
   is larger than `templates/dashboard.html` (about 40 KB), and its
   `<script id="ll-snapshot">` block holds the snapshot rather than `{}`.

## Procedure, mcp source

Follow `references/mcp-recipe.md`. It maps every field of `snapshot.json` to
the MCP call that fills it, grouped by budget, so you spend what the user
chose. Write the JSON to the agreed output folder (not inside the skill folder)
and run `scripts/render.py --snapshot <that file>`. If Python is unavailable,
paste the JSON into the `<script id="ll-snapshot">` block of
`templates/dashboard.html` by hand and save it as `index.html`.

Three facts shape the collection. Results are capped: 1,000 rows per search and
about 128 KiB per result, so keep `limit` at 500 or below and split by time or
folder. Day ranges written as `<day>/<next day>` follow the machine's local
midnight; write UTC ISO timestamps instead. And tool output lands in your
context, so prefer aggregates and small pages over dumping rows.

Two audit-trail facts change how you count. One user-visible save fans out into
several rows (create, write, move, delete of a temp sibling), so read sequences
rather than counting rows. Events can appear a short while after the operation,
so a missing just-made change is lag, not absence.

## Presenting the result

Lead with the path to the dashboard. Then at most three findings from the
data, each one line, drawn from the flags and the folder table. Then the
limits, always, as bullets, worded for the source you used:

- Snapshot, not live. Say when it was taken and how to refresh.
- Audit covers only the period since it was enabled.
- Tree tiles are a sample if the walk budget clamped (the header marks walked
  figures and says so; details under Flags). On the mcp source the tree tools
  are bounded by the server's own walk budget and depth, and cold-data tiles
  need named folders.
- Stored size and Connect files come from the hub (sdk, mcp, or `--stats`); a
  bare mount shows `n/a`.
- Where the page lives: from the drive, a local file, or a local server. There
  is no hosted URL. On the sdk and mcp sources it is not in the filespace until
  someone copies it there through a mount.

## Refresh

`refresh: manual` in the config means you regenerate when asked, which spends
tokens each time. `refresh: script` means the user schedules the two scripts
(cron, launchd, Task Scheduler) and spends none. Offer the script route to
anyone who asks for a second refresh.

## Customizing

Everything the customer might change is in `references/customizing.md`: adding
a tile, regrouping folders, renaming actors, swapping the visual style for their
own, and the schema in `references/snapshot-schema.md`. Ideas for further
tiles, including ones that need MCP-only data such as locks and live change
subscriptions, are in `references/tile-catalog.md`.

## Guardrails

- Never write anywhere in the filespace other than the agreed dashboard folder.
- Never read file contents for this skill. Metadata and the audit trail are enough.
- Never paste tokens or credentials into config files, and never read a token
  out of another tool's configuration. The sdk source reads the token from an
  environment variable for that reason.
- Actor names, and the hostnames recorded per actor, are personal data. Keep
  them inside the customer's filespace; do not copy the snapshot elsewhere
  without asking.
