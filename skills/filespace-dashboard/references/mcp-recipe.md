# MCP recipe: building snapshot.json from LucidLink MCP Server calls

Use this when the only route to the filespace is the MCP Server. Each field of
`snapshot.json` (schema in `snapshot-schema.md`) is listed with the tool call
that fills it, grouped by budget so you spend what the user chose. Tool names
are the server's default `core` toolset; check the tool list if a name differs.

Write the result to the agreed output folder, then run `scripts/render.py
--snapshot <that file>`.

## Before collecting

- **Link, confirm, then query.** `link_filespace(name=...)`, then
  `current_filespace`, then the scoped calls. The server's current filespace is
  shared by every session using that server and can change between two of your
  calls; never put `link_filespace` in the same parallel batch as scoped calls,
  and check that `filespace_stats` says `linked: <your filespace>`.
- **Results are capped.** `mode=search` returns at most 1,000 rows, and any
  result over about 128 KiB is truncated with a marker; the last line before the
  marker may be a half row, drop it. Keep `limit` at 500 or below and split by
  action, time or folder.
- **Time ranges.** Always pass `time_range`; the tool defaults to 24 hours.
  `7d` and `30d` are rolling windows. A range written as `<day>/<next day>` is
  bounded by the machine's local midnight, not UTC; write explicit UTC
  timestamps, `2026-09-16T00:00:00+00:00/2026-09-17T00:00:00+00:00`.
- **The shortcut.** If one `mode=search` over the whole window returns fewer
  rows than its `limit`, you already hold every event: derive `by_day`,
  `by_hour`, `by_actor` (with reads, writes and deletes), the folders' activity
  columns, `recent` and the flags from those rows and skip every aggregate call
  below. Quiet filespaces finish in about ten calls this way.
- **Provenance.** Set `stats.provenance` to `hub (MCP filespace_stats)` for the
  figures that came from `filespace_stats` and `tree walk` for anything walked;
  the page treats any value starting with `hub` as a hub figure. Set
  `stats.walk_complete` to `false` when any walk was truncated.

## lite: about 10 calls, 7-day window

| Field | Call |
|---|---|
| `stats.data_bytes`, `storage_bytes`, `external_files`, `external_bytes` | `filespace_stats`. No "external files" line means 0. Its `entries` count includes the audit-log files under `/.lucid_audit`; keep it in a note, the page does not display it. |
| `stats.files`, `stats.dirs` | `count_files` with `path_prefix="/"`. The server stops at its own walk budget (5,000 entries by default) and says `search truncated`; when it does, leave both `null`, set `walk_complete: false`, and mention the hub entry count in a note. A truncated count in the header reads as a census. |
| `folders[].path` | `tree` with `max_depth=1`, `max_entries_per_dir=50`: one row per top-level directory, plus `/` for files sitting at the root. |
| `activity.events`, `activity.by_action` | `read_audit_trail` `mode=aggregate` `group_by=action` `time_range=7d` |
| `activity.by_actor` | `read_audit_trail` `mode=aggregate` `group_by=user` `time_range=7d`. `kind` is `service` when the name has no `@`, unless the config says otherwise. `reads`, `writes`, `deletes`, `last_seen`, `hosts` come from rows (below) or stay `null`. |
| `recent`, `by_day`, `by_hour` | `read_audit_trail` `mode=search` `limit=500` `time_range=7d`. Complete window: derive everything from the rows. Otherwise `recent` from the newest rows, `by_day` from the aggregates in the standard tier, `by_hour` `null`, and a note. |
| `cold`, `extensions`, `largest` | empty lists and a note; the tiles show their empty states. |

## standard: 15 to 40 calls, 7-day window

Everything in lite, plus:

| Field | Call |
|---|---|
| `folders[].files`, `folders[].bytes`, `extensions`, `largest` | `tree` per top-level folder with `max_depth=10`, `max_entries_per_dir=1000`: every file line carries its byte size, so sum per folder, per extension, and keep the largest. The census is bounded by depth, entries per directory and the result cap; compare the entries you saw with the hub's `entries` minus the audit files, and if you fell short set `walk_complete: false` and say which folders were cut. `find_files` and `count_files` do not help here: no sizes, same walk budget. |
| `folders[].reads`, `writes`, `deletes`, `last_write`, `writers` | From the rows when the window is complete. Otherwise one `read_audit_trail` `mode=aggregate` `group_by=action` per folder with `path_prefix=<folder>` and a UTC `time_range`, for the ten largest folders by bytes. `writers` are the users behind write and delete actions, not everyone in a `group_by=user` aggregate (that includes readers); get them from rows or a `mode=search` with `action=FileWritten` per folder. Root-level activity (`/`) can only come from rows, because `path_prefix="/"` matches everything. |
| `activity.by_day` | From rows, or seven `mode=aggregate` `group_by=action` calls with explicit UTC day ranges. One bucket per UTC calendar day the window touches, oldest first. |
| `activity.by_hour` | From rows only; otherwise `null`. |
| `flags` | No service accounts; a single actor; and the delete rule: 100 or more deletes by one actor within any 60-minute span. The delete rule needs rows; without them state the daily delete count and say the hourly check was not made. |

## deep: 60 to 200 calls, 30-day window

Everything in standard with `time_range=30d`, plus:

| Field | Call |
|---|---|
| `activity.by_day`, `by_hour` | Rows for the whole window, paged by UTC day. A day with more rows than the cap: `mode=aggregate` `group_by=action` for that day, then `mode=search` with `action=<X>` per action, then explicit UTC windows of an hour or less until each page is complete. |
| `activity.by_actor[].reads`, `writes`, `deletes` | From rows, or `read_audit_trail` `mode=user_activity` `user=<name>` `time_range=30d` per actor. |
| `cold.candidates`, `cold.buckets`, `largest` with modification times | `get_entry` per file under the folders the user named (`mtime_iso`); without named folders the cold tiles stay empty, and say so. |

## Mapping and derivations

- Actions: reads are `FileRead` and `PreHydrate`; deletes are `FileDelete` and
  `DirectoryDelete`; writes are `FileWritten`, `FileCreate`, `DirectoryCreate`,
  `Move`, `SymlinkCreate`, `ExtendedAttributeSet`, `ExtendedAttributeDelete`,
  `Pin`, `Unpin`; anything else is `other`. This is `snapshot.py`'s rule.
- The folder of an event is its parent directory, cut at `folders.depth`;
  entries directly under the root belong to `/`. A `Move` also credits the
  target folder with a write and appears in the ticker as `old → new`.
- The ticker keeps `FileWritten`, `FileCreate`, `FileDelete`, `Move`,
  `DirectoryCreate`, `DirectoryDelete`; rows with the same path in the same
  second collapse into one line; newest 25.
- `hosts` per actor come from the hostname in parentheses on each search row.
- `locks`: leave `null`. The page does not render it, and `list_locks_held`
  only lists this process's own locks.

## Rules while collecting

- Never call `read_file`, `read_lines` or `grep_files` for this skill. Metadata and audit only.
- One desktop save fans out into create, write, move, move, delete of a temp sibling. Read the sequence when building `recent`; do not count the rows as five changes.
- A change made seconds ago may not be in the trail yet. Do not report it as missing.
- If a walk-based tool reports a clamped budget or partial results, copy that sentence into `notes`.
- Skip `/.lucid_audit` paths and the dashboard's own folder when counting activity, or the dashboard inflates its own numbers.
